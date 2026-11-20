#!/usr/bin/env python3
"""Check a daily curve ledger (specifications/12-platform/daily-curve-run.md, KR-103 to KR-105, KR-203 to KR-209).

  verify_chain.py verify --ledger FILE [--anchors DIR [--bitcoin-headers FILE]] [--impl python] [--no-calendar]
                         [--summary OUT]
  verify_chain.py anchor --ledger FILE --out-dir DIR [--stamp] [--if-uncovered]
  verify_chain.py heights --anchors DIR
  verify_chain.py rebuild --ledger FILE --date YYYY-MM-DD --treasury-file CSV [--impl python]

verify: the hash chain, the genesis configuration, every row rule (dates strictly in order with at most one
unsettled date, status, error codes, stale inputs, gap causes, fit and consistency diagnostics recomputed from
the stored differences), the holdout windows of the preregs, and with the library calendar the business days,
timing labels and missing days; then every anchor held. With --bitcoin-headers it also says, for every DAY row
labelled on time, whether an anchor's Bitcoin block time proves it (the label itself is the runner's clock). It
stops at the first failure and never repairs. Prints one JSON line; exit 0 if it passes, 1 if not.

anchor: writes anchors/<UTC time>.json (count, head, format, config hash) and, with --stamp, an OpenTimestamps
proof beside it (`ots stamp`, free public calendars, no account). With --if-uncovered it writes nothing when an
anchor for the current head is already held.

heights: the Bitcoin block heights the held proofs name (the headers --bitcoin-headers needs), and the anchors
still pending.

rebuild: refits one ok day from a copy of the Treasury file whose SHA-256 matches the row, and compares the fit
with the row: text fields exactly, numbers within 1e-6 relative to max(1, value) (KR-207).
"""
import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "paper_daily"))  # for anchor_evidence only (shared by both daily jobs)
sys.path.insert(0, str(HERE))  # this folder first: both folders hold a run_day.py
import anchor_evidence as evidence  # noqa: E402
import curve_core as core  # noqa: E402
import run_day  # noqa: E402


def load_anchors(folder):
    out = []
    for p in sorted(Path(folder).glob("*.json")) if folder and Path(folder).exists() else []:
        a = json.loads(p.read_text(encoding="utf-8"))
        a["name"] = p.name
        out.append(a)
    return out


def verify(ledger, anchors=None, runner=None, cfg=None, windows=None, headers=None, max_target=evidence.MAX_TARGET):
    text = core.read_ledger(ledger)
    v = core.verify(text, cfg, runner, windows)
    if v["ok"] and anchors is not None:
        held = load_anchors(anchors)
        a = core.check_anchors(text, held)
        if not a["ok"]:
            return a
        v["anchors"] = a["anchors"]
        if headers is not None:
            if runner is None:
                return core.bad(0, "EVIDENCE", "the anchored timing check needs the calendar")
            try:
                v["anchored_timing"] = anchored_timing(text, held, anchors, headers, runner, cfg, max_target)
            except evidence.EvidenceError as e:
                return core.bad(0, "EVIDENCE", str(e))
    return v


def anchored_timing(text, held, anchors_dir, headers, runner, cfg=None, max_target=evidence.MAX_TARGET):
    """For every DAY row labelled on time: is it proven by a Bitcoin block time before its cut-off (KR-201)?"""
    cfg = cfg or core.load_config()
    cal = core.Calendar(runner, cfg["calendar"])
    times = evidence.anchor_times(anchors_dir, headers, max_target)
    pairs = [(a["name"], int(a["count"])) for a in held]
    proven, unproven = [], {}
    for r in core.parse(text):
        if r["kind"] != "DAY" or r["body"].get("timing") != "on_time":
            continue
        bound = int(core.cutoff(core.day(r["body"]["date"]), cal, cfg).timestamp())
        ok, why, _ = evidence.proven_before(r["seq"], bound, pairs, times)
        if ok:
            proven.append(r["body"]["date"])
        else:
            unproven[r["body"]["date"]] = why
    return {"proven_on_time": len(proven), "labelled_on_time_without_proof": unproven,
            "margin_seconds": evidence.MARGIN_SECONDS}


def close(a, b, path=""):
    """First path where a refit differs from a row: numbers within REBUILD_TOL, the rest exactly (KR-207)."""
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                return f"{path}.{k}"
            e = close(a[k], b[k], f"{path}.{k}")
            if e:
                return e
        return None
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return path
        return next((e for e in (close(x, y, f"{path}[{n}]") for n, (x, y) in enumerate(zip(a, b))) if e), None)
    if a == b:
        return None
    if path.endswith((".tau", ".taus_ok", ".max_at", ".within_fit_flag", ".operation", ".weighting")):
        return path
    try:
        x, y = float(a), float(b)
    except (TypeError, ValueError):
        return path
    return None if abs(x - y) <= core.REBUILD_TOL * max(1.0, abs(x), abs(y)) else path


def rebuild(ledger, date, treasury_file, runner, cfg=None):
    cfg = cfg or core.load_config()
    rows = core.parse(core.read_ledger(ledger))
    row = next((r for r in rows if r["kind"] == "DAY" and r["body"]["date"] == date and r["body"]["status"] == "ok"), None)
    if row is None:
        return {"ok": False, "reason": "NO_ROW", "detail": f"no ok DAY row for {date}"}
    data = Path(treasury_file).read_bytes()
    if core.sha256(data) != row["body"]["input"]["sha256"]:
        return {"ok": False, "reason": "INPUT_HASH", "detail": "the file is not the one the row was fitted from"}
    table = core.treasury_rows(data)
    try:
        fit = core.fit_day(core.day(date), table[date], cfg, runner)
    except core.FitFailed as e:
        return {"ok": False, "reason": "REFIT_FAILED", "detail": f"{e.code}: {e.detail}"}
    diff = close(fit, row["body"]["fit"])
    if diff:
        return {"ok": False, "reason": "REFIT_DIFFERS", "detail": diff}
    return {"ok": True, "date": date, "row": row["hash"], "exact": fit == row["body"]["fit"],
            "tolerance": str(core.REBUILD_TOL)}


def anchor(ledger, out_dir, stamp=False, cfg=None, if_uncovered=False, when=None):
    cfg = cfg or core.load_config()
    a = core.make_anchor(core.read_ledger(ledger), cfg)
    out = Path(out_dir)
    if if_uncovered and any(h.get("count") == a["count"] and h.get("head") == a["head"] for h in load_anchors(out)):
        return {"ok": True, "anchor": None, "covered": True, **a}
    out.mkdir(parents=True, exist_ok=True)
    p = out / ((when or dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")) + ".json")
    if p.exists():
        return {"ok": False, "reason": "ANCHOR", "detail": f"{p.name} exists; an anchor is never overwritten"}
    p.write_text(json.dumps(a, sort_keys=True, indent=1) + "\n", encoding="utf-8", newline="\n")
    if stamp:
        subprocess.run(["ots", "stamp", str(p)], check=True)
    return {"ok": True, "anchor": p.name, "covered": False, **a}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("verify")
    v.add_argument("--ledger", required=True)
    v.add_argument("--anchors")
    v.add_argument("--bitcoin-headers", help="JSON {height: 80-byte header hex} for the anchored timing check")
    v.add_argument("--impl", default="python")
    v.add_argument("--no-calendar", action="store_true", help="skip the business-day checks (no CLI needed)")
    v.add_argument("--summary", help="write the latest-fit summary JSON here")
    n = sub.add_parser("anchor")
    n.add_argument("--ledger", required=True)
    n.add_argument("--out-dir", required=True)
    n.add_argument("--stamp", action="store_true")
    n.add_argument("--if-uncovered", action="store_true", help="write nothing if the head already has an anchor")
    h = sub.add_parser("heights")
    h.add_argument("--anchors", required=True)
    b = sub.add_parser("rebuild")
    b.add_argument("--ledger", required=True)
    b.add_argument("--date", required=True)
    b.add_argument("--treasury-file", required=True)
    b.add_argument("--impl", default="python")
    a = ap.parse_args(argv)
    if a.cmd == "verify":
        if a.bitcoin_headers and (not a.anchors or a.no_calendar):
            ap.error("--bitcoin-headers needs --anchors and the calendar")
        try:
            headers = evidence.load_headers(a.bitcoin_headers) if a.bitcoin_headers else None
            res = verify(a.ledger, a.anchors, None if a.no_calendar else run_day.cli_runner(a.impl), headers=headers)
        except (evidence.EvidenceError, ValueError) as e:
            res = core.bad(0, "EVIDENCE", str(e))
        if res["ok"] and a.summary:
            text = core.read_ledger(a.ledger)
            Path(a.summary).write_text(json.dumps(core.summary(text, res), indent=1, sort_keys=True) + "\n",
                                       encoding="utf-8", newline="\n")
    elif a.cmd == "anchor":
        res = anchor(a.ledger, a.out_dir, a.stamp, if_uncovered=a.if_uncovered)
    elif a.cmd == "heights":
        try:
            need, pending = evidence.needed_heights(a.anchors)
            res = {"ok": True, "heights": need, "pending": pending}
        except evidence.EvidenceError as e:
            res = core.bad(0, "EVIDENCE", str(e))
    else:
        res = rebuild(a.ledger, a.date, a.treasury_file, run_day.cli_runner(a.impl))
    print(json.dumps(res, sort_keys=True))
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
