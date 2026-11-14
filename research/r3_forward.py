"""R3 forward-log signal writer (amendment 3 rules 3-4, as amended by amendment 6).

Reads the forward log (`actions/log.jsonl` on branch `forward-log`) and writes one companion row per `study/<id>`
row to `research/r3/forward_signals.jsonl`, in the forward log's chained format. The forward log is never edited.
Signals use the recorded inputs a study row had when it was written (amendment 6 Change 2), the frozen parameters
in `research/r3/params/`, and, for R3-03 only, the frozen in-sample month means (Change 3). Study formulas come
from `r3_runner.py` and `r3_in_sample.py` unchanged; both are SHA-pinned and checked before any row is built.

  python research/r3_forward.py backfill --data DIR [--log-ref origin/forward-log | --log FILE]
  python research/r3_forward.py daily [--log-ref origin/forward-log | --log FILE]

No P&L, return or Sharpe is written. Label: signal on a fitted curve; tradability not established.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterable
from datetime import UTC, date, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import r3_data as d
import r3_in_sample as s
import r3_runner as r


def _load_fl() -> ModuleType:
    spec = importlib.util.spec_from_file_location("forward_log", ROOT / "tools" / "forward-log" / "forward_log.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


fl = _load_fl()

OUT = HERE / "r3" / "forward_signals.jsonl"
RUNS = HERE / "r3" / "forward_runs.csv"
FIT = HERE / "r3" / "forward_fit.json"
PARAMS = HERE / "r3" / "params"
RUN_LOG = HERE / "holdout_runs.csv"
AMENDMENT = HERE / "preregs" / "R3-01-amendment-6.md"
LABEL = "signal on a fitted curve; tradability not established"
STUDIES = ("R3-01", "R3-02", "R3-03")
INPUTS = {"R3-01": ["us-treasury-par-yields"],
          "R3-02": ["us-treasury-bill-rates", "nyfed-sofr", "nyfed-tgcr", "nyfed-bgcr"],
          "R3-03": []}
RUN_FIELDS = ["utc", "mode", "script", "script_sha256", "commit", "forward_log_ref", "forward_log_commit",
              "forward_log_head", "rows_r3_01", "rows_r3_02", "rows_r3_03"]
Entry = dict[str, Any]
Payload = dict[str, Any]
State = dict[str, dict[str, float]]
Signal = tuple[float | None, float | None, str, str | None]  # signal, position, status, as_of


class Refused(RuntimeError):
    pass


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def run_lines(text: str) -> dict[str, dict[str, str]]:
    return {row["study"]: row for row in csv.DictReader(io.StringIO(text))}


def check_pins(runs: dict[str, dict[str, str]], amendment: str) -> None:
    """Amendment 6 Changes 1-2: the runner equals the run lines; two modules equal the signed header."""
    for st in STUDIES:
        if st not in runs:
            raise Refused(f"{st}: no line in holdout_runs.csv")
        if runs[st]["script_sha256"] != sha(HERE / "r3_runner.py"):
            raise Refused(f"{st}: r3_runner.py differs from its run line")
    for name in ("r3_in_sample.py", "r3_data.py"):
        m = re.search(rf"`research/{re.escape(name)}` \(whole file\): `([0-9a-f]{{64}})`", amendment)
        if not m or m.group(1) != sha(HERE / name):
            raise Refused(f"{name} differs from the SHA-256 pinned by amendment 6")


# --- recorded inputs (Change 2) -----------------------------------------------------------------

def state_hash(state: dict[str, float]) -> str:
    return hashlib.sha256(str(fl.canon(state)).encode("utf-8")).hexdigest()


def study_rows_with_state(entries: Iterable[Entry]) -> list[tuple[Entry, State]]:
    """Each study row with the replayed recorder state of its inputs at that row (lower sequence only)."""
    state: State = {}
    out: list[tuple[Entry, State]] = []
    for e in entries:
        rec = e["record"]
        sid = rec["series_id"]
        if sid.startswith("recorder/"):
            src = sid.split("/", 1)[1]
            pay = rec["value"]["payload"]
            state.setdefault(src, {}).update(pay.get("observations") or {})
            want = pay.get("state_sha256")
            if want is not None and state_hash(state[src]) != want:
                raise Refused(f"{sid} sequence {rec['sequence']}: replayed state does not match state_sha256")
        elif sid.startswith("study/") and sid.split("/", 1)[1] in STUDIES:
            ins = INPUTS[sid.split("/", 1)[1]]
            out.append((e, {k: dict(v) for k, v in state.items() if k in ins}))
    return out


def _put(series: dict[str, d.Series], key: str, day: date, col: str, v: float) -> None:
    series.setdefault(key, {}).setdefault(day, {})[col] = v


def to_series(state: State, until: date) -> dict[str, d.Series]:
    """Replayed observations in the shape `r3_data` loads (values in percent), dated on or before `until`."""
    out: dict[str, d.Series] = {d.NOMINAL: {}, d.BILL: {}, "SOFR": {}, "TGCR": {}, "BGCR": {}}
    for src, obs in state.items():
        for k, v in obs.items():
            ds, field = k.split("|", 1)
            if len(ds) != 10:
                continue
            day = date.fromisoformat(ds)
            if day > until:
                continue
            if src == "us-treasury-par-yields" and field in ("2 Yr", "5 Yr", "10 Yr"):
                _put(out, d.NOMINAL, day, field.upper(), float(v))
            elif src == "us-treasury-bill-rates" and field == "13 WEEKS COUPON EQUIVALENT":
                _put(out, d.BILL, day, field, float(v))
            elif src.startswith("nyfed-") and field == "percentRate":
                rate = src.split("-", 1)[1].upper()
                _put(out, rate, day, rate, float(v))
    return out


def n_aligned(series: dict[str, d.Series], cols: list[tuple[str, str]]) -> int:
    return len(set.intersection(*({x for x, v in series.get(k, {}).items() if c in v} for k, c in cols)))


# --- signals (Change 3) -------------------------------------------------------------------------

def _f(x: float) -> float:
    return float(round(x, 12))


def r301_signal(series: dict[str, d.Series], L: int, k: float) -> Signal:
    cols = [(d.NOMINAL, "2 YR"), (d.NOMINAL, "5 YR"), (d.NOMINAL, "10 YR")]
    n = n_aligned(series, cols)
    if n < L:
        return None, None, f"insufficient recorded history: {n} of {L} business days", None
    days, fly, _, _ = s.r301_inputs(series)
    z = r.zscore(fly, L)
    pos = r.hysteresis(z, k)
    return _f(float(z[-1])), float(pos[-1]), "computed", days[-1].isoformat()


def r302_signal(series: dict[str, d.Series], L: int, k: float, funding: str, trail: int = 20) -> Signal:
    cols = [(d.BILL, "13 WEEKS COUPON EQUIVALENT"), ("SOFR", "SOFR"), ("TGCR", "TGCR"), ("BGCR", "BGCR")]
    msg = "insufficient recorded history: {} of " + f"{L} spread values"
    if n_aligned(series, cols) == 0:
        return None, None, msg.format(0), None
    days, v = s.r302_inputs(series)
    col = {"SOFR": 1, "TGCR": 2, "BGCR": 3}[funding]
    bill, fund = v[:, 0], v[:, col]
    # As in r3_runner.bill_month_returns (amendment 4, R3-02 items 1 and 3).
    mm = np.array([bill[i] * 360 / r.bill_basis(x) for i, x in enumerate(days)])
    trailing = np.array([fund[max(0, i - trail + 1):i + 1].mean() if i >= trail - 1 else np.nan
                         for i in range(len(days))])
    sp = (mm - trailing) * 1e4
    starts = r.month_starts(days)
    if not starts:
        return None, None, msg.format(int((~np.isnan(sp)).sum())), days[-1].isoformat()
    e = starts[-1]
    hist = sp[:e]
    hist = hist[~np.isnan(hist)]
    if len(hist) < L:
        return None, None, msg.format(len(hist)), days[e - 1].isoformat()
    w = hist[-L:]
    sd = w.std(ddof=1)
    z = float((w[-1] - w.mean()) / sd) if sd > 0 else 0.0
    pos = 1.0 if z > k else (-1.0 if z < -k else 0.0)
    return _f(z), pos, "computed", days[e - 1].isoformat()


def r303_month_means(ends: list[date], b_bp: r.Arr, in_sample_end: date) -> dict[int, float]:
    """The month means of r3_runner.seasonal_returns: month-end changes by month of the end date, in-sample."""
    dd = np.diff(b_bp)
    months = np.array([x.month for x in ends[1:]])
    ins = np.array([x <= in_sample_end for x in ends[1:]])
    return {m: float(dd[ins & (months == m)].mean()) for m in range(1, 13) if (ins & (months == m)).any()}


def r303_fit(data: Path) -> dict[str, Any]:
    ends, b, _, _, _ = s.r303_inputs(d.load_in_sample("R3-03", data=data))
    means = r303_month_means(ends, b, r.IN_SAMPLE_END["R3-03"])
    return {"study": "R3-03", "trial": "R3-03-T01", "lambda": 0,
            "month_mean_bp": {str(m): _f(v) for m, v in sorted(means.items())},
            "in_sample_month_ends": len(ends), "first_month_end": ends[0].isoformat(),
            "last_month_end": ends[-1].isoformat(),
            "modules_sha256": {n: sha(HERE / n) for n in ("r3_runner.py", "r3_in_sample.py", "r3_data.py")},
            "data_log_sha256": sha(d.LOG), "label": LABEL}


def r303_signal(fit: dict[str, Any], day: date) -> Signal:
    f = float(fit["month_mean_bp"].get(str(day.month), 0.0)) * (1 - float(fit["lambda"]))
    return _f(f), float(np.sign(f)), "computed", None


# --- rows (Changes 1 and 4) ---------------------------------------------------------------------

def row_date(e: Entry) -> date:
    return date.fromisoformat(e["record"]["event_time"][:10])


def build(entries: list[Entry], runs: dict[str, dict[str, str]], mode: str, done: set[str],
          fit: dict[str, Any], fit_sha: str, commit: str, shas: dict[str, str],
          params_dir: Path = PARAMS) -> list[tuple[str, str, Payload]]:
    head = entries[-1]["hash"] if entries else fl.ZERO
    params = {st: json.loads((params_dir / f"{st}.json").read_text(encoding="utf-8")) for st in STUDIES}
    out: list[tuple[str, str, Payload]] = []
    for e, state in study_rows_with_state(entries):
        rec = e["record"]
        st = rec["series_id"].split("/", 1)[1]
        if e["hash"] in done:
            continue
        day = row_date(e)
        back = day < date.fromisoformat(runs[st]["utc_date"])
        if mode == "daily" and back:
            continue
        p = params[st]["params"]
        if st == "R3-01":
            sig = r301_signal(to_series(state, day), int(p["L"]), float(p["k"]))
        elif st == "R3-02":
            sig = r302_signal(to_series(state, day), int(p["L"]), float(p["k"]), str(p["funding"]))
        else:
            sig = r303_signal(fit, day)
        pay: Payload = {
            "kind": "study_signal", "fills": e["hash"], "fills_sequence": rec["sequence"],
            "signal": sig[0], "position": sig[1], "signal_status": sig[2], "as_of": sig[3],
            "position_basis": "decided" if st == "R3-01" else "held",
            "params_sha256": sha(params_dir / f"{st}.json"),
            "inputs": {i: (state_hash(state[i]) if i in state else None) for i in INPUTS[st]},
            "forward_log_head": head, "writer_sha256": shas["writer"], "runner_sha256": shas["runner"],
            "backfilled": back, "label": LABEL}
        if st == "R3-03":
            pay["fit_sha256"] = fit_sha
        if back:
            pay["backfill_commit"] = commit
        out.append((rec["series_id"], rec["event_time"], pay))
    return out


CUTOFF = date(2027, 11, 5)  # amendment 8 Change 1


def judgement(rows: Iterable[Entry], holidays: set[str], need: int = 250, as_of: date | None = None,
              cutoff: date = CUTOFF) -> dict[str, dict[str, Any]]:
    """Amendment 7 Change 1: counted days per study (US business days with a companion row whose position is
    defined) and the judgement date, the counted day on which the count reaches `need`. Amendment 8: only rows
    dated on or before `cutoff` and written by its end count; `status` is `judged on <date>`, `not yet judged`
    (before the cut-off) or `not judged: insufficient data`. Reads no return."""
    written = cutoff.isoformat() + "T23:59:59Z"
    days: dict[str, set[date]] = {}
    for e in rows:
        rec = e["record"]
        st = rec["series_id"].split("/", 1)[1]
        if rec["value"]["payload"].get("position") is None:
            continue
        kt = rec.get("knowledge_time")
        if kt is not None and kt > written:
            continue
        x = row_date(e)
        if x <= cutoff and x.weekday() < 5 and x.isoformat() not in holidays:
            days.setdefault(st, set()).add(x)
    out: dict[str, dict[str, Any]] = {}
    for st in STUDIES:
        ds = sorted(days.get(st, set()))
        jd = ds[need - 1].isoformat() if len(ds) >= need else None
        if jd is not None:
            status = f"judged on {jd}"
        elif as_of is None or as_of <= cutoff:
            status = "not yet judged"
        else:
            status = "not judged: insufficient data"
        out[st] = {"counted_days": len(ds), "judgement_date": jd, "status": status}
    return out


def load_holidays(path: Path = ROOT / "tools" / "recorder" / "holidays.txt") -> set[str]:
    return {x.strip() for x in path.read_text(encoding="utf-8").splitlines() if x.strip() and not x.startswith("#")}


def existing(path: Path) -> tuple[set[str], bool]:
    """Rows already in the companion file: the forward-log hashes they fill, and whether any is back-filled."""
    rows = fl.read(path)
    if rows:
        fl.verify(path)
    pays = [x["record"]["value"]["payload"] for x in rows]
    fills = [p["fills"] for p in pays]
    if len(fills) != len(set(fills)):
        raise Refused("companion file has a duplicate fills")
    return set(fills), any(p.get("backfilled") for p in pays)


def append_all(path: Path, rows: list[tuple[str, str, Payload]], now: str) -> None:
    """All or none: append to a copy, verify it, then replace the file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(suffix=".jsonl", dir=path.parent)
    os.close(fd)
    tmp = Path(name)
    try:
        if path.exists():
            shutil.copyfile(path, tmp)
        for sid, et, pay in rows:
            fl.append(tmp, sid, et, pay, knowledge_time=now)
        fl.verify(tmp)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=True).stdout


def clean(paths: list[Path], g: Callable[..., str] = git) -> bool:
    return g("status", "--porcelain", "--", *(str(p) for p in paths)).strip() == ""


def read_log(text: str) -> list[Entry]:
    fd, name = tempfile.mkstemp(suffix=".jsonl")
    os.close(fd)
    tmp = Path(name)
    try:
        tmp.write_text(text, encoding="utf-8", newline="\n")
        fl.verify(tmp)
        entries: list[Entry] = fl.read(tmp)
    finally:
        tmp.unlink()
    return entries


def run(mode: str, log_text: str, log_ref: str, log_commit: str, data: Path | None,
        out: Path = OUT, runs_csv: Path = RUNS, fit_path: Path = FIT, g: Callable[..., str] = git,
        now: str | None = None, also_done: tuple[Path, ...] = ()) -> dict[str, int]:
    runs = run_lines(RUN_LOG.read_text(encoding="utf-8"))
    check_pins(runs, AMENDMENT.read_text(encoding="utf-8"))
    guarded = [Path(__file__), HERE / "r3_runner.py", HERE / "r3_in_sample.py", HERE / "r3_data.py", PARAMS,
               out, runs_csv, fit_path, RUN_LOG, *also_done]
    guarded = [p for p in guarded if p.resolve().is_relative_to(ROOT)]  # files on forward-log are outside
    if not clean(guarded, g):
        raise Refused("uncommitted changes to the writer, runner, params or companion files")
    commit = g("rev-parse", "HEAD").strip()
    done, any_back = existing(out)
    for extra in also_done:  # amendment 7 Change 2: one companion row per study row across both files
        more, back2 = existing(extra)
        done |= more
        any_back = any_back or back2
    if mode == "backfill":
        if any_back:
            raise Refused("back-fill already done (rule 4: once)")
        if data is None:
            raise Refused("backfill needs --data for the R3-03 in-sample fit")
        fit = r303_fit(data)
    elif not fit_path.exists():
        raise Refused("daily needs research/r3/forward_fit.json from the back-fill")
    else:
        fit = json.loads(fit_path.read_text(encoding="utf-8"))
    fit_text = json.dumps(fit, indent=1) + "\n"
    entries = read_log(log_text)
    shas = {"writer": sha(Path(__file__)), "runner": sha(HERE / "r3_runner.py")}
    fit_sha = hashlib.sha256(fit_text.encode("utf-8")).hexdigest()
    rows = build(entries, runs, mode, done, fit, fit_sha, commit, shas)
    stamp = now or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    if mode == "backfill":
        fit_path.write_text(fit_text, encoding="utf-8", newline="\n")
    if rows:
        append_all(out, rows, stamp)
    counts = {st: sum(1 for x in rows if x[0] == f"study/{st}") for st in STUDIES}
    new = not runs_csv.exists()
    with runs_csv.open("a", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        if new:
            w.writerow(RUN_FIELDS)
        w.writerow([stamp, mode, "research/r3_forward.py", shas["writer"], commit, log_ref, log_commit,
                    entries[-1]["hash"] if entries else fl.ZERO, *counts.values()])
    return counts


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["backfill", "daily"])
    ap.add_argument("--log", help="forward-log file; default: actions/log.jsonl at --log-ref")
    ap.add_argument("--log-ref", default="origin/forward-log")
    ap.add_argument("--data", type=Path, help="directory holding the R3 in-sample files (backfill only)")
    ap.add_argument("--out", type=Path, default=OUT, help="companion file (amendment 7: actions/signals.jsonl)")
    ap.add_argument("--runs", type=Path, default=RUNS, help="run log (amendment 7: actions/signals_runs.csv)")
    ap.add_argument("--also-done", type=Path, action="append", default=[],
                    help="other companion files whose filled rows are skipped")
    a = ap.parse_args(argv)
    if a.log:
        text, ref, cm = Path(a.log).read_text(encoding="utf-8"), a.log, ""
    else:
        text, ref, cm = git("show", f"{a.log_ref}:actions/log.jsonl"), a.log_ref, git("rev-parse", a.log_ref).strip()
    try:
        counts = run(a.mode, text, ref, cm, a.data, out=a.out, runs_csv=a.runs, also_done=tuple(a.also_done))
    except Refused as e:
        print(f"refused: {e}", file=sys.stderr)
        return 2
    print(json.dumps(counts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
