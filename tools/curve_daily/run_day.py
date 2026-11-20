#!/usr/bin/env python3
"""Daily curve run: append every row that is due (specifications/12-platform/daily-curve-run.md).

  run_day.py --ledger FILE [--now INSTANT] [--commit SHA] [--dry-run]
  run_day.py --ledger-ref origin/curve-daily --dry-run
  run_day.py --ledger FILE --treasury-file CSV --gsw-file CSV --now INSTANT     (offline, files in place of fetches)

One run: work out which US business days are due (library calendar USGS), check each date against the prereg
holdout windows, fetch the Treasury par yield file for the year, fit the library Nelson-Siegel operation, and
append one DAY row per date (ok, fit_failed, stale_input, fetch_failed or holdout_blocked) or a GAP row; then
compare settled fits with the Federal Reserve's GSW curve once the Fed has posted that date. The whole new
ledger is verified before the file is written. Raw downloads are held in memory only and never written.
--dry-run prints the rows it would add and writes nothing. Exit 0 also when nothing is due; 1 on a refusal
(nothing written); 2 when rows were written and one records a problem (gap, failed fetch or fit, stale input,
holdout block).
"""
import argparse
import datetime as dt
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import curve_core as core  # noqa: E402

USER_AGENT = "quantforge-curve-daily (public research code)"


def git_show(ref, path):
    r = subprocess.run(["git", "show", f"{ref}:{path}"], cwd=core.ROOT, capture_output=True)
    return r.stdout.decode("utf-8") if r.returncode == 0 else ""


def http_fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=120) as resp:  # noqa: S310 - fixed https URLs from config.json
        if resp.status != 200:
            raise OSError(f"HTTP {resp.status}")
        return resp.read()


def file_fetch(treasury, gsw, cfg):
    """Offline fetcher: any Treasury URL reads `treasury`, the GSW URL reads `gsw`."""
    def go(url):
        if url == cfg["gsw"]["url"]:
            if not gsw:
                raise OSError("no --gsw-file given")
            return Path(gsw).read_bytes()
        if not treasury:
            raise OSError("no --treasury-file given")
        return Path(treasury).read_bytes()
    return go


def cli_runner(impl):
    """Cases through one `quantforge --batch` process of the chosen build (tools/workflows/common.py); error
    results are returned, not raised, so a failed fit keeps its error code."""
    sys.path.insert(0, str(core.ROOT / "tools" / "workflows"))
    import common

    def go(cases):
        return common.batch(cases, impl) if cases else {}
    return go


def contract_version(impl):
    sys.path.insert(0, str(core.ROOT / "tools" / "workflows"))
    sys.path.insert(0, str(core.ROOT / "conformance" / "runner"))
    import os
    from runner import resolve_command
    impls = json.loads(Path(os.environ.get("QF_IMPLEMENTATIONS", core.ROOT / "conformance/runner/implementations.json")).read_text(encoding="utf-8"))
    base, cwd = resolve_command(impls[impl])
    p = subprocess.run(base + ["version"], cwd=cwd, capture_output=True, timeout=300)
    return json.loads(p.stdout.decode("utf-8").splitlines()[-1])["contract_version"]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ledger", help="ledger file (ledger/curves.jsonl on branch curve-daily)")
    ap.add_argument("--ledger-ref", help="read the ledger from this git ref instead (dry runs only)")
    ap.add_argument("--now", help="UTC instant YYYY-MM-DDTHH:MM:SSZ (default: the clock)")
    ap.add_argument("--impl", default="python")
    ap.add_argument("--commit", default="unknown")
    ap.add_argument("--config", default=str(HERE / "config.json"))
    ap.add_argument("--treasury-file", help="offline: read this file instead of fetching the Treasury CSV")
    ap.add_argument("--gsw-file", help="offline: read this file instead of fetching feds200628.csv")
    ap.add_argument("--summary", help="write the latest-fit summary JSON here (site stub data)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    if bool(a.ledger) == bool(a.ledger_ref):
        ap.error("give exactly one of --ledger / --ledger-ref")
    if a.ledger_ref and not a.dry_run:
        ap.error("--ledger-ref is read-only: use it with --dry-run")
    cfg = core.load_config(a.config)
    now = core.instant(a.now) if a.now else dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    offline = a.treasury_file or a.gsw_file
    fetch = file_fetch(a.treasury_file, a.gsw_file, cfg) if offline else http_fetch
    try:
        text = core.read_ledger(a.ledger) if a.ledger else git_show(a.ledger_ref, "ledger/curves.jsonl")
        runner = cli_runner(a.impl)
        out, new, notes = core.run(cfg, runner, text, now, fetch, a.commit, contract_version(a.impl), a.impl)
        v = core.verify(out, cfg, runner)
        if not v["ok"]:
            raise core.CurveError(f"the new ledger does not verify: seq {v['first_bad_seq']} {v['reason']} {v['detail']}")
    except (core.CurveError, ValueError) as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 1
    print(f"label: {cfg['label']}")
    for n in notes:
        print(n)
    print(json.dumps({"now": core.stamp(now), "rows_added": len(new), "dry_run": a.dry_run, "offline": bool(offline),
                      "records": v["records"], "head": v["head"], "last_date": v["last_date"], "counts": v["counts"]},
                     sort_keys=True))
    if a.dry_run:
        for r in new:
            print(core.line(r))
        return problems(new)
    if new:
        p = Path(a.ledger)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_bytes(out.encode("ascii"))  # rows are ASCII with LF endings on every platform (KR-208)
        tmp.replace(p)
    if a.summary:
        Path(a.summary).write_text(json.dumps(core.summary(out, v), indent=1, sort_keys=True) + "\n", encoding="utf-8",
                                   newline="\n")
    return problems(new)


def problems(new):
    """Exit 2 when a written row records a problem (a gap, a failed fetch or fit, a stale input, a holdout
    block), so the scheduled run turns red after the rows are pushed; 0 otherwise."""
    bad = [f"{r['body']['date']} {r['kind']} {r['body'].get('status', '')}".strip() for r in new
           if r["kind"] == "GAP" or (r["kind"] == "DAY" and r["body"]["status"] != "ok")]
    for b in bad:
        print(f"problem row: {b}", file=sys.stderr)
    return 2 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
