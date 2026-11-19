#!/usr/bin/env python3
"""Daily paper ledger: append every row that is due (specifications/12-platform/paper-ledger-daily.md).

  run_day.py --ledger FILE --forward-log FILE [--now INSTANT] [--impl python] [--commit SHA] [--dry-run]
  run_day.py --ledger-ref origin/paper-ledger --forward-log-ref origin/forward-log --dry-run

One run: read the recorded Treasury par curve from the forward log (no network), mark yesterday's par bonds,
re-strike, decide the rule's order, check its limits, simulate its fills, write TCA for it, explain the day's
P&L, reconcile, and append one DAY row (or a GAP row for a business day with no recorded curve). The whole new
ledger is verified, including a rebuild of every day through the CLI, before the file is written. --dry-run
prints the rows it would add and writes nothing. Exit 0 also when nothing is due; exit 1 on a refusal.
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
import core  # noqa: E402
import forward_log as fl  # noqa: E402


def git_show(ref, path):
    """A file from a git ref, or an empty string if the ref or file does not exist."""
    r = subprocess.run(["git", "show", f"{ref}:{path}"], cwd=core.ROOT, capture_output=True)
    return r.stdout.decode("utf-8") if r.returncode == 0 else ""


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ledger", help="ledger file (ledger/ledger.jsonl on branch paper-ledger)")
    ap.add_argument("--ledger-ref", help="read the ledger from this git ref instead (dry runs)")
    ap.add_argument("--forward-log", help="recorder log file (actions/log.jsonl on branch forward-log)")
    ap.add_argument("--forward-log-ref", help="read the recorder log from this git ref instead")
    ap.add_argument("--now", help="UTC instant YYYY-MM-DDTHH:MM:SSZ (default: the clock)")
    ap.add_argument("--impl", default="python")
    ap.add_argument("--commit", default="unknown")
    ap.add_argument("--config", default=str(HERE / "config.json"))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    if bool(a.ledger) == bool(a.ledger_ref) or bool(a.forward_log) == bool(a.forward_log_ref):
        ap.error("give exactly one of --ledger / --ledger-ref and one of --forward-log / --forward-log-ref")
    if a.ledger_ref and not a.dry_run:
        ap.error("--ledger-ref is read-only: use it with --dry-run")
    cfg = core.load_config(a.config)
    now = core.instant(a.now) if a.now else dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    try:
        if a.forward_log:
            fl.verify(a.forward_log)  # the recorder's own chain check
            entries = fl.read(a.forward_log)
        else:
            entries = [json.loads(x) for x in git_show(a.forward_log_ref, "actions/log.jsonl").splitlines() if x.strip()]
        if not entries:
            raise core.PaperError("the recorder log is empty or missing")
        text = core.read_text(a.ledger) if a.ledger else git_show(a.ledger_ref, "ledger/ledger.jsonl")
        runner = core.cli_runner(a.impl)
        out, new, notes = core.run(cfg, runner, text, entries, now, a.commit, a.impl)
        v = core.verify(out, cfg, runner)
        if not v["ok"]:
            raise core.PaperError(f"the new ledger does not verify: seq {v['first_bad_seq']} {v['reason']} {v['detail']}")
    except (core.PaperError, ValueError) as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 1
    print(f"label: {cfg['label']}")
    print(f"note: {cfg['statement']} {cfg['ceiling']}")
    for n in notes:
        print(n)
    print(json.dumps({"now": core.stamp(now), "rows_added": len(new), "dry_run": a.dry_run,
                      **{k: v[k] for k in ("records", "recorded_trading_days", "late_days", "gaps", "head", "last_date")}},
                     sort_keys=True))
    if a.dry_run:
        for r in new:
            print(core.line(r))
        return 0
    if new:
        p = Path(a.ledger)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(out, encoding="utf-8", newline="\n")
        tmp.replace(p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
