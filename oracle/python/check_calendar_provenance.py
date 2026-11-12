#!/usr/bin/env python3
"""Calendar provenance test (plan 11.2.3). Fails when any calendar's confirmed coverage ends within 12 months.

Amber, not red (R6-15, review finding 15): a calendar whose next schedule is not yet published carries
`awaiting_publication_until` (ISO date) in datasets/calendar_provenance.json. Until that date a short coverage is
printed as AMBER (a GitHub warning) and the check passes; after it, the check fails. Exit 0 green or amber, 1 red.

python oracle/python/check_calendar_provenance.py [--today YYYY-MM-DD]
Standard library only. Data: datasets/calendar_provenance.json; text: specifications/01-core/calendar-provenance.md.
"""
import argparse, json, sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def problems(doc, today, amber=None):
    out = []
    amber = [] if amber is None else amber
    horizon = date(today.year + 1, today.month, min(today.day, 28))
    for name, c in sorted(doc["calendars"].items()):
        for k in ("source", "url", "checked", "confirmed_through"):
            if not c.get(k):
                out.append(f"{name}: no {k}")
        if c.get("confirmed_through") and date.fromisoformat(c["confirmed_through"]) < horizon:
            wait = c.get("awaiting_publication_until")
            (amber if wait and today <= date.fromisoformat(wait) else out).append(f"{name}: confirmed only through {c['confirmed_through']}, within 12 months of {today}; refresh from {c.get('url')}")
        if c.get("checked") and (today - date.fromisoformat(c["checked"])).days > 366:
            out.append(f"{name}: last checked {c['checked']}, more than a year ago")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--today", default=date.today().isoformat())
    a = ap.parse_args()
    doc = json.loads((ROOT / "datasets" / "calendar_provenance.json").read_text(encoding="utf-8"))
    amber = []
    p = problems(doc, date.fromisoformat(a.today), amber)
    for x in amber:
        print("AMBER", x)
        print(f"::warning::calendar provenance amber: {x}")
    for x in p:
        print("FAIL", x)
    print("calendar provenance:", f"{len(p)} problem(s)" if p else ("amber" if amber else "ok"))
    return 1 if p else 0


if __name__ == "__main__":
    sys.exit(main())
