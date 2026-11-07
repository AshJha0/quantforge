#!/usr/bin/env python3
"""Gap monitor and reconciler for recorder logs. Neutral tooling: standard library, no financial logic.

  gap_monitor.py gaps --log FILE [--log FILE ...] [--since DATE] [--until DATE] [--holidays FILE] [--recent N] [--out FILE]
  gap_monitor.py reconcile --log A --log B [--out FILE]

gaps: for each recorder series, lists business days (Monday to Friday, minus any dates in --holidays) that have no
successful recording in any of the given logs. Exit 1 if a gap falls in the last --recent business days (default 3),
so a scheduled run fails loudly; older gaps are reported but cannot be fixed by rerunning.

reconcile: compares two logs (the Actions log and the local backup log) by (series, UTC date). Each pair is
"both", "first only" or "second only"; for "both" it says whether any sha256 matched. Differing hashes on one day
are normal for sources whose URL ends "to now" or that republish, so they are listed, not treated as errors.
"""
import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path


def rows(paths):
    for p in paths:
        path = Path(p)
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)["record"]
                if r["series_id"].startswith("recorder/"):
                    yield r


def by_day(paths):
    """{series: {date: {"ok": set(sha), "failed": int}}}"""
    out = {}
    for r in rows(paths):
        d = date.fromisoformat(r["event_time"][:10])
        p = r["value"]["payload"]
        cell = out.setdefault(r["series_id"], {}).setdefault(d, {"ok": set(), "failed": 0})
        if p.get("kind") == "recording":
            cell["ok"].add(p["sha256"])
        else:
            cell["failed"] += 1
    return out


def business_days(start, end, holidays):
    d = start
    while d <= end:
        if d.weekday() < 5 and d not in holidays:
            yield d
        d += timedelta(days=1)


def load_holidays(path):
    if not path:
        return set()
    return {date.fromisoformat(x.strip()) for x in Path(path).read_text(encoding="utf-8").splitlines()
            if x.strip() and not x.startswith("#")}


def gaps(a):
    data = by_day(a.log)
    holidays = load_holidays(a.holidays)
    until = date.fromisoformat(a.until) if a.until else date.today()
    report, recent_bad = [], []
    for series in sorted(data):
        days = data[series]
        start = date.fromisoformat(a.since) if a.since else min(days)
        expected = list(business_days(start, until, holidays))
        missing = [d for d in expected if not days.get(d, {}).get("ok")]
        recent = set(expected[-a.recent:])
        stale = stale_run(days, expected)
        report.append({"series": series, "from": start.isoformat(), "expected": len(expected),
                       "missing": [d.isoformat() for d in missing], "unchanged_run": stale})
        recent_bad += [f"{series} {d}" for d in missing if d in recent]
    md = ["# Recorder gaps", "", f"Business days Monday to Friday up to {until}, holidays from "
          f"{a.holidays or 'none'}. A gap is a day with no successful recording in any log given.", "",
          "| Series | From | Expected | Missing | Longest run of unchanged bytes |", "|---|---|---:|---|---:|"]
    for r in report:
        miss = ", ".join(r["missing"][-10:]) + (" ..." if len(r["missing"]) > 10 else "") if r["missing"] else "none"
        md.append(f"| {r['series']} | {r['from']} | {r['expected']} | {miss} | {r['unchanged_run']} |")
    md += ["", f"Recent gaps (last {a.recent} business days): {', '.join(recent_bad) or 'none'}", ""]
    text = "\n".join(md)
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
        Path(a.out).with_suffix(".json").write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    print(text)
    return 1 if recent_bad else 0


def stale_run(days, expected):
    """Longest run of consecutive expected days whose only hash equals the previous day's: the source stopped updating."""
    best = run = 0
    prev = None
    for d in expected:
        ok = days.get(d, {}).get("ok", set())
        if ok and prev and ok == prev:
            run += 1
            best = max(best, run)
        else:
            run = 0
        prev = ok or prev
    return best


def reconcile(a):
    if len(a.log) != 2:
        raise SystemExit("reconcile needs exactly two --log files: first the Actions log, then the local log")
    first, second = by_day([a.log[0]]), by_day([a.log[1]])
    md = ["# Recorder reconciliation", "", f"First: `{a.log[0]}`. Second: `{a.log[1]}`.", "",
          "| Series | Date | Status | Hashes |", "|---|---|---|---|"]
    counts = {}
    for series in sorted(set(first) | set(second)):
        f, s = first.get(series, {}), second.get(series, {})
        for d in sorted(set(f) | set(s)):
            fo, so = f.get(d, {}).get("ok", set()), s.get(d, {}).get("ok", set())
            if fo and so:
                status = "both"
                hashes = "match" if fo & so else "differ"
            elif fo:
                status, hashes = "first only", "-"
            elif so:
                status, hashes = "second only", "-"
            else:
                status, hashes = "neither (failures only)", "-"
            counts[(status, hashes)] = counts.get((status, hashes), 0) + 1
            md.append(f"| {series} | {d} | {status} | {hashes} |")
    md += ["", "Totals: " + "; ".join(f"{k[0]}{'/' + k[1] if k[1] != '-' else ''}: {v}" for k, v in sorted(counts.items())), ""]
    text = "\n".join(md)
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
    print(text)
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["gaps", "reconcile"])
    ap.add_argument("--log", action="append", required=True)
    ap.add_argument("--since")
    ap.add_argument("--until")
    ap.add_argument("--holidays")
    ap.add_argument("--recent", type=int, default=3)
    ap.add_argument("--out")
    a = ap.parse_args()
    return gaps(a) if a.command == "gaps" else reconcile(a)


if __name__ == "__main__":
    sys.exit(main())
