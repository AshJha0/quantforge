#!/usr/bin/env python3
"""Verify the daily paper ledger, or make and check its anchors (paper-ledger-daily.md, acceptance P1 to P14).

  verify_ledger.py verify --ledger FILE [--impl python | --no-cli] [--anchors DIR] [--forward-log FILE]
                          [--bitcoin-headers FILE] [--require-days N] [--summary FILE]
  verify_ledger.py anchor --ledger FILE --out-dir DIR [--stamp] [--if-uncovered]
  verify_ledger.py heights --anchors DIR

verify: hash chain; genesis configuration against tools/paper_daily/config.json; every date a business day of the
library calendar, none missing, none inside a prereg holdout window, timing label against the row's time; an
exact replay of every day's cash, positions, P&L and explain terms from the ledger alone; and, unless --no-cli,
a rebuild of every day through the CLI (marks, rule, limit check, simulated fills, TCA). --no-cli skips the
calendar and the rebuild and says so. --anchors DIR checks every anchor against the ledger. --forward-log FILE
checks every DAY row's five yields against the recorder's log (reason SOURCE). --bitcoin-headers FILE (with
--anchors and the CLI) counts the recorded trading days from outside evidence: a day counts only if an anchor
over its row has a Bitcoin block time, plus a two hour margin, before the day's cut-off (KR-200 to KR-202). The
row's own "on_time" label is the runner's clock; it is reported as `declared_on_time_days` and never used as
the count. --require-days N (the v1.0.0 gate uses 20) fails unless N days are recorded, and refuses to run
without the CLI, --anchors, --forward-log and --bitcoin-headers. Never repairs. Exit 1 on any failure.

anchor: writes DIR/<UTC time>.json with (count, head) and, with --stamp, stamps it with OpenTimestamps. With
--if-uncovered it writes nothing when an anchor for the current head is already held.

heights: the Bitcoin block heights named by the proofs held (the headers --bitcoin-headers needs) and the
anchors still pending. A header is 80 bytes; any Bitcoin node or public block explorer serves it by height.
"""
import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "forward-log"))
import paper_core as core  # noqa: E402

evidence = core.evidence
GATE_NEEDS = "--require-days needs the CLI (no --no-cli), --anchors, --forward-log and --bitcoin-headers"


def read_log(path):
    """The recorder log after its own chain check (tools/forward-log/forward_log.py)."""
    import forward_log as fl
    fl.verify(path)
    return fl.read(path)


def verify(a, cfg, runner=None, max_target=evidence.MAX_TARGET, log_reader=read_log):
    """The whole check as one function, so the tests can call it with an in-process runner."""
    text = core.read_text(a.ledger)
    if a.require_days > 0 and (a.no_cli or not (a.anchors and a.forward_log and a.bitcoin_headers)):
        return {"ok": False, "first_bad_seq": None, "reason": "GATE", "detail": GATE_NEEDS}
    if a.bitcoin_headers and (a.no_cli or not a.anchors):
        return {"ok": False, "first_bad_seq": None, "reason": "GATE",
                "detail": "--bitcoin-headers needs --anchors and the CLI (the calendar gives each day's cut-off)"}
    runner = None if a.no_cli else (runner or core.cli_runner(a.impl))
    try:
        v = core.verify(text, cfg, runner)
        if v["ok"] and a.anchors:
            v["anchors"] = core.anchor_check(text, cfg, a.anchors)
        if v["ok"] and a.forward_log:
            fault = core.check_sources(text, cfg, log_reader(a.forward_log))
            if fault:
                return fault
            v["sources_checked"] = True
        if v["ok"]:
            v["recorded_trading_days"] = None  # not computed without outside evidence (KR-200)
        if v["ok"] and a.bitcoin_headers:
            v.update(core.recorded_days(text, cfg, runner, a.anchors, evidence.load_headers(a.bitcoin_headers),
                                        max_target))
        if v["ok"] and a.require_days > 0 and v["recorded_trading_days"] < a.require_days:
            v = {"ok": False, "first_bad_seq": None, "reason": "DAYS",
                 "detail": f"{v['recorded_trading_days']} recorded trading days, {a.require_days} required "
                           f"({v['declared_on_time_days']} rows are labelled on time; not proven: "
                           f"{json.dumps(v['not_proven'], sort_keys=True)})"}
    except (core.PaperError, subprocess.CalledProcessError) as e:
        v = {"ok": False, "first_bad_seq": None, "reason": "ANCHOR", "detail": str(e)}
    except evidence.EvidenceError as e:
        v = {"ok": False, "first_bad_seq": None, "reason": "EVIDENCE", "detail": str(e)}
    except (OSError, ValueError, KeyError) as e:
        v = {"ok": False, "first_bad_seq": None, "reason": "INPUT", "detail": f"{type(e).__name__}: {e}"}
    return v


def main(argv=None, runner=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("command", choices=["verify", "anchor", "heights"])
    ap.add_argument("--ledger")
    ap.add_argument("--config", default=str(HERE / "config.json"))
    ap.add_argument("--impl", default="python")
    ap.add_argument("--no-cli", action="store_true")
    ap.add_argument("--require-days", type=int, default=0)
    ap.add_argument("--anchors")
    ap.add_argument("--forward-log", help="recorder log file (actions/log.jsonl on branch forward-log)")
    ap.add_argument("--bitcoin-headers", help="JSON {height: 80-byte block header as hex}")
    ap.add_argument("--summary", help="write the result as JSON (for a dashboard)")
    ap.add_argument("--out-dir")
    ap.add_argument("--stamp", action="store_true")
    ap.add_argument("--if-uncovered", action="store_true", help="anchor: write nothing if the head is anchored")
    a = ap.parse_args(argv)
    cfg = core.load_config(a.config)
    if a.command == "heights":
        if not a.anchors:
            ap.error("heights needs --anchors")
        try:
            need, pending = evidence.needed_heights(a.anchors)
        except evidence.EvidenceError as e:
            print(json.dumps({"ok": False, "reason": "EVIDENCE", "detail": str(e)}, sort_keys=True))
            return 1
        print(json.dumps({"ok": True, "heights": need, "pending": pending}, sort_keys=True))
        return 0
    if not a.ledger:
        ap.error(f"{a.command} needs --ledger")
    if a.command == "anchor":
        if not a.out_dir:
            ap.error("anchor needs --out-dir")
        try:
            when = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
            p = core.anchor_make(core.read_text(a.ledger), cfg, a.out_dir, when, a.if_uncovered)
        except core.PaperError as e:
            print(f"REFUSED: {e}", file=sys.stderr)
            return 1
        if p is None:
            print("covered: the head already has an anchor; nothing written")
            return 0
        if a.stamp:
            subprocess.run(["ots", "stamp", str(p)], check=True)
        print(p)
        return 0
    v = verify(a, cfg, runner)
    v["label"] = cfg["label"]
    if a.summary:
        Path(a.summary).write_text(json.dumps(v, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(v, sort_keys=True))
    return 0 if v["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
