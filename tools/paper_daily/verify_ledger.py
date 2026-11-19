#!/usr/bin/env python3
"""Verify the daily paper ledger, or make and check its anchors (paper-ledger-daily.md, acceptance P1 to P10).

  verify_ledger.py verify --ledger FILE [--impl python | --no-cli] [--require-days N] [--anchors DIR] [--summary FILE]
  verify_ledger.py anchor --ledger FILE --out-dir DIR [--stamp]

verify: hash chain; genesis configuration against tools/paper_daily/config.json; every date a business day of the
library calendar, none missing, none inside a prereg holdout window, timing label against the row's time; an
exact replay of every day's cash, positions, P&L and explain terms from the ledger alone; and, unless --no-cli,
a rebuild of every day through the CLI (marks, rule, limit check, simulated fills, TCA). --no-cli skips the
calendar and the rebuild and says so. --require-days N fails unless N trading days are recorded (the v1.0.0
gate uses 20). --anchors DIR also checks every anchor. Never repairs. Exit 1 on any failure.

anchor: writes DIR/<UTC time>.json with (count, head) and, with --stamp, stamps it with OpenTimestamps.
"""
import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import paper_core as core  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("command", choices=["verify", "anchor"])
    ap.add_argument("--ledger", required=True)
    ap.add_argument("--config", default=str(HERE / "config.json"))
    ap.add_argument("--impl", default="python")
    ap.add_argument("--no-cli", action="store_true")
    ap.add_argument("--require-days", type=int, default=0)
    ap.add_argument("--anchors")
    ap.add_argument("--summary", help="write the result as JSON (for a dashboard)")
    ap.add_argument("--out-dir")
    ap.add_argument("--stamp", action="store_true")
    a = ap.parse_args(argv)
    cfg = core.load_config(a.config)
    text = core.read_text(a.ledger)
    try:
        if a.command == "anchor":
            if not a.out_dir:
                ap.error("anchor needs --out-dir")
            p = core.anchor_make(text, cfg, a.out_dir, dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H%M%SZ"))
            if a.stamp:
                subprocess.run(["ots", "stamp", str(p)], check=True)
            print(p)
            return 0
        v = core.verify(text, cfg, None if a.no_cli else core.cli_runner(a.impl))
        if v["ok"] and a.anchors:
            v["anchors"] = core.anchor_check(text, cfg, a.anchors)
        if v["ok"] and v["recorded_trading_days"] < a.require_days:
            v = {"ok": False, "first_bad_seq": None, "reason": "DAYS",
                 "detail": f"{v['recorded_trading_days']} recorded trading days, {a.require_days} required"}
    except (core.PaperError, subprocess.CalledProcessError) as e:
        v = {"ok": False, "first_bad_seq": None, "reason": "ANCHOR", "detail": str(e)}
    v["label"] = cfg["label"]
    if a.summary:
        Path(a.summary).write_text(json.dumps(v, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(v, sort_keys=True))
    return 0 if v["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
