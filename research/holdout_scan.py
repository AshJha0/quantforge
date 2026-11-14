#!/usr/bin/env python3
"""List every forward-log row and tracked file that carries an observation inside an R3 study's holdout window.

Finding 1 of the 2026-11-12 review, reproduced by script (R6-19). Holdout windows are read from the prereg files;
study inputs from tools/recorder/studies.json.

What counts as an observation:
- forward log: an entry in a row's `observations` whose date key (YYYY-MM-DD or YYYY-MM) falls inside the holdout
  window of a study that lists the row's source as an input;
- tracked file (.json, .jsonl, .csv, .md, .html): a date inside a study's window in a file that also names one of
  that study's real sources (MARKERS below). Synthetic test dates in files that name no real study source are not
  observations of study data and are not reported.

  python research/holdout_scan.py [--log FILE | --log-ref origin/forward-log] [--files]

Prints one line per hit: <location>\t<study>\t<count>\t<first date>\t<last date>. research/test_preregs.py fails on
any hit not listed in research/preregs/DEVIATION-2026-11-12.md.
"""
import argparse
import json
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PREREGS = {"R3-01": "R3-01-treasury-fly.md", "R3-02": "R3-02-bill-repo-spread.md", "R3-03": "R3-03-breakeven-seasonality.md"}
# Words that tie a tracked file to a study's real input data.
MARKERS = {
    "R3-01": r"home\.treasury\.gov|daily_treasury_yield_curve|us-treasury-par-yields|Treasury par",
    "R3-02": r"newyorkfed|nyfed-|\bSOFR\b|\bTGCR\b|\bBGCR\b|daily_treasury_bill_rates|us-treasury-bill-rates",
    "R3-03": r"home\.treasury\.gov|us-treasury-par-yields|us-treasury-real-yields|daily_treasury_real|bls\.gov|bls-cpi|CUUR0000SA0",
}
DATE = re.compile(r"(?<![\d-])(\d{4}-\d{2}(?:-\d{2})?)(?![\d-])")
SKIP = ("research/preregs/", "program/", "CHANGELOG.md", "ROADMAP.md")  # prose about the studies, not data
# The R3 download log: its `url` (request ranges) and `sha256` columns carry no observed value and are blanked
# before the scan; every other column of it is scanned as usual.
DATA_LOG = "research/r3/data_log.csv"
BLANKED = ("url", "sha256")


def strip_log_columns(text):
    import csv
    import io
    rows = list(csv.DictReader(io.StringIO(text)))
    return "\n".join(",".join("" if k in BLANKED else (v or "") for k, v in r.items()) for r in rows)


def windows():
    out = {}
    for sid, name in PREREGS.items():
        t = (ROOT / "research" / "preregs" / name).read_text(encoding="utf-8")
        m = re.search(r"Holdout: (\d{4}-\d{2}-\d{2}) to (\d{4}-\d{2}-\d{2})", t)
        out[sid] = (m.group(1), m.group(2))
    return out


def inside(d, w):
    lo, hi = w
    if len(d) == 7:  # a month overlaps the window
        return lo[:7] <= d <= hi[:7]
    return lo <= d <= hi


def study_inputs():
    st = json.loads((ROOT / "tools" / "recorder" / "studies.json").read_text(encoding="utf-8"))["studies"]
    return {s["id"]: set(s["inputs"]) for s in st}


def scan_log(lines, w=None, inputs=None):
    w, inputs = w or windows(), inputs or study_inputs()
    hits = []
    for n, line in enumerate(lines, 1):
        if not line.strip():
            continue
        r = json.loads(line)["record"]
        sid = r["series_id"]
        if not sid.startswith("recorder/"):
            continue
        v = r["value"]
        obs = (v.get("payload", v) or {}).get("observations") or {}
        src = sid.split("/", 1)[1]
        for study, ins in inputs.items():
            if src not in ins:
                continue
            ds = sorted(k.split("|")[0] for k in obs if inside(k.split("|")[0], w[study]))
            if ds:
                hits.append((f"forward-log:actions/log.jsonl#row{n}:{src}", study, len(ds), ds[0], ds[-1]))
    return hits


def scan_text(path, text, w=None):
    w = w or windows()
    hits = []
    for study, mk in MARKERS.items():
        if not re.search(mk, text):
            continue
        ds = sorted(d for d in DATE.findall(text) if inside(d, w[study]))
        if ds:
            hits.append((path, study, len(ds), ds[0], ds[-1]))
    return hits


def tracked(ref=None):
    """Tracked data files of the working tree, or of a git ref (for the forward-log branch)."""
    if ref:
        names = subprocess.run(["git", "ls-tree", "-r", "--name-only", ref], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
        get = lambda n: subprocess.run(["git", "show", f"{ref}:{n}"], cwd=ROOT, capture_output=True, check=True).stdout.decode("utf-8", "replace")
        prefix = ref.split("/")[-1] + ":"
    else:
        names = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
        get = lambda n: (ROOT / n).read_text(encoding="utf-8", errors="replace")
        prefix = ""
    for n in names:
        if n.endswith((".json", ".jsonl", ".csv", ".md", ".html")) and not n.startswith(SKIP) and n != "actions/log.jsonl":
            if ref or (ROOT / n).exists():
                yield prefix + n, get(n)


def scan_all(log_ref="origin/forward-log"):
    w = windows()
    hits = []
    for p, t in tracked():
        hits += scan_text(p, strip_log_columns(t) if p == DATA_LOG else t, w)
    have = subprocess.run(["git", "rev-parse", "--verify", "-q", log_ref], cwd=ROOT, capture_output=True).returncode == 0
    if have:
        log = subprocess.run(["git", "show", f"{log_ref}:actions/log.jsonl"], cwd=ROOT, capture_output=True, check=True).stdout.decode()
        hits += scan_log(log.splitlines(), w)
        for p, t in tracked(log_ref):
            hits += scan_text(p, t, w)
    return hits, have


# --- R3 amendment 3 rule 5, as amended by amendment 6 Change 5 -------------------------------------------------
SIGNALS = "research/r3/forward_signals.jsonl"
RUN_LOG = "research/holdout_runs.csv"


def run_studies(text: str | None) -> dict[str, str]:
    import csv
    import io
    return {row["study"]: row["utc_date"] for row in csv.DictReader(io.StringIO(text or ""))}


def show_runs(commit: str) -> str | None:
    """research/holdout_runs.csv at a commit, or None when the commit or file cannot be shown."""
    p = subprocess.run(["git", "show", f"{commit}:{RUN_LOG}"], cwd=ROOT, capture_output=True, check=False)
    return p.stdout.decode("utf-8") if p.returncode == 0 else None


def signal_check(entries: list[dict[str, Any]], runs: dict[str, str], show: Callable[[str], str | None] = show_runs,
                 where: str = "log") -> list[tuple[str, str]]:
    """Failures for study rows with a non-null signal or position: (a) no run line; (b) written before the J-2 run
    date; (c) dated before it without backfilled and backfill_commit; (d) the writing commit lacks the run line."""
    bad: list[tuple[str, str]] = []
    for n, e in enumerate(entries, 1):
        r = e["record"]
        if not r["series_id"].startswith("study/"):
            continue
        p = r["value"].get("payload", {})
        if p.get("signal") is None and p.get("position") is None:
            continue
        st, loc = r["series_id"].split("/", 1)[1], f"{where}#row{n}:{r['series_id']}"
        j2 = runs.get(st)
        if j2 is None:
            bad.append((loc, "a: no holdout-run line"))
            continue
        if r["knowledge_time"][:10] < j2:
            bad.append((loc, "b: written before the J-2 run date"))
        if r["event_time"][:10] < j2 and not (p.get("backfilled") is True and p.get("backfill_commit")):
            bad.append((loc, "c: dated before the J-2 run date and not back-filled"))
        if st not in run_studies(show(r["value"].get("commit") or "")):
            bad.append((loc, "d: writing commit does not hold the run line"))
    return bad


def signal_scan_all(log_ref: str = "origin/forward-log") -> list[tuple[str, str]]:
    runs = run_studies((ROOT / RUN_LOG).read_text(encoding="utf-8"))
    bad: list[tuple[str, str]] = []
    comp = ROOT / SIGNALS
    if comp.exists():
        rows = [json.loads(x) for x in comp.read_text(encoding="utf-8").splitlines() if x.strip()]
        bad += signal_check(rows, runs, where=SIGNALS)
    if subprocess.run(["git", "rev-parse", "--verify", "-q", log_ref], cwd=ROOT, capture_output=True,
                      check=False).returncode == 0:
        log = subprocess.run(["git", "show", f"{log_ref}:actions/log.jsonl"], cwd=ROOT, capture_output=True,
                             check=True).stdout.decode()
        bad += signal_check([json.loads(x) for x in log.splitlines() if x.strip()], runs, where="forward-log")
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", help="scan this log file only")
    ap.add_argument("--log-ref", default="origin/forward-log")
    ap.add_argument("--signals", action="store_true", help="run the rule-5 signal check instead")
    a = ap.parse_args()
    if a.signals:
        for b in signal_scan_all(a.log_ref):
            print("	".join(b))
        return
    if a.log:
        hits = scan_log(Path(a.log).read_text(encoding="utf-8").splitlines())
    else:
        hits, have = scan_all(a.log_ref)
        if not have:
            print(f"note: {a.log_ref} not found; forward log not scanned", file=sys.stderr)
    for h in hits:
        print("\t".join(map(str, h)))


if __name__ == "__main__":
    main()
