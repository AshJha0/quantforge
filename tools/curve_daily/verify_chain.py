#!/usr/bin/env python3
"""Check a daily curve ledger (specifications/12-platform/daily-curve-run.md, KR-103 to KR-105).

  verify_chain.py verify --ledger FILE [--anchors DIR] [--impl python] [--no-calendar] [--summary OUT]
  verify_chain.py anchor --ledger FILE --out-dir DIR [--stamp]
  verify_chain.py rebuild --ledger FILE --date YYYY-MM-DD --treasury-file CSV [--impl python]

verify: the hash chain, the genesis configuration, every row rule (status, error codes, stale inputs, fit and
consistency diagnostics recomputed from the stored differences), the holdout windows of the preregs, and with
the library calendar the business days, timing labels and missing days; then every anchor held. It stops at the
first failure and never repairs. Prints one JSON line; exit 0 if it passes, 1 if not.

anchor: writes anchors/<UTC time>.json (count, head, format, config hash) and, with --stamp, an OpenTimestamps
proof beside it (`ots stamp`, free public calendars, no account).

rebuild: refits one ok day from a copy of the Treasury file whose SHA-256 matches the row, and compares the fit
with the row exactly.
"""
import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import curve_core as core  # noqa: E402
import run_day  # noqa: E402


def load_anchors(folder):
    out = []
    for p in sorted(Path(folder).glob("*.json")) if folder and Path(folder).exists() else []:
        a = json.loads(p.read_text(encoding="utf-8"))
        a["name"] = p.name
        out.append(a)
    return out


def verify(ledger, anchors=None, runner=None, cfg=None, windows=None):
    text = Path(ledger).read_text(encoding="utf-8")
    v = core.verify(text, cfg, runner, windows)
    if v["ok"] and anchors is not None:
        a = core.check_anchors(text, load_anchors(anchors))
        if not a["ok"]:
            return a
        v["anchors"] = a["anchors"]
    return v


def rebuild(ledger, date, treasury_file, runner, cfg=None):
    cfg = cfg or core.load_config()
    rows = core.parse(Path(ledger).read_text(encoding="utf-8"))
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
    if fit != row["body"]["fit"]:
        diff = sorted(k for k in fit if fit[k] != row["body"]["fit"].get(k))
        return {"ok": False, "reason": "REFIT_DIFFERS", "detail": ", ".join(diff)}
    return {"ok": True, "date": date, "row": row["hash"]}


def anchor(ledger, out_dir, stamp=False, cfg=None):
    cfg = cfg or core.load_config()
    a = core.make_anchor(Path(ledger).read_text(encoding="utf-8"), cfg)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    p = out / (dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".json")
    p.write_text(json.dumps(a, sort_keys=True, indent=1) + "\n", encoding="utf-8", newline="\n")
    if stamp:
        subprocess.run(["ots", "stamp", str(p)], check=True)
    return {"ok": True, "anchor": p.name, **a}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("verify")
    v.add_argument("--ledger", required=True)
    v.add_argument("--anchors")
    v.add_argument("--impl", default="python")
    v.add_argument("--no-calendar", action="store_true", help="skip the business-day checks (no CLI needed)")
    v.add_argument("--summary", help="write the latest-fit summary JSON here")
    n = sub.add_parser("anchor")
    n.add_argument("--ledger", required=True)
    n.add_argument("--out-dir", required=True)
    n.add_argument("--stamp", action="store_true")
    b = sub.add_parser("rebuild")
    b.add_argument("--ledger", required=True)
    b.add_argument("--date", required=True)
    b.add_argument("--treasury-file", required=True)
    b.add_argument("--impl", default="python")
    a = ap.parse_args(argv)
    if a.cmd == "verify":
        res = verify(a.ledger, a.anchors, None if a.no_calendar else run_day.cli_runner(a.impl))
        if res["ok"] and a.summary:
            text = Path(a.ledger).read_text(encoding="utf-8")
            Path(a.summary).write_text(json.dumps(core.summary(text, res), indent=1, sort_keys=True) + "\n",
                                       encoding="utf-8", newline="\n")
    elif a.cmd == "anchor":
        res = anchor(a.ledger, a.out_dir, a.stamp)
    else:
        res = rebuild(a.ledger, a.date, a.treasury_file, run_day.cli_runner(a.impl))
    print(json.dumps(res, sort_keys=True))
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
