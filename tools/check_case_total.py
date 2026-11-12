#!/usr/bin/env python3
"""Gate: the committed golden totals (all, value, error, invariance) and unique case ids must equal the last
"Expected totals" line stated in program/R6_HANDOVER.md (`TOTALS: N value V error E invariance I`). Added after wave 3B
committed two stray generator files (842 cases) that no count check saw.

    python tools/check_case_total.py
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    t, ids = Counter(), Counter()
    for p in (ROOT / "datasets" / "golden").rglob("*.json"):
        for c in json.loads(p.read_text(encoding="utf-8")).get("cases", []):
            t[c["expected"]["status"]] += 1
            ids[c["case_id"]] += 1
    got = (sum(t.values()), t["ok"], t["error"], t["any"] + t["same_as"])
    dup = [k for k, n in ids.items() if n > 1]
    m = re.findall(r"TOTALS: (\d+) value (\d+) error (\d+) invariance (\d+)", (ROOT / "program" / "R6_HANDOVER.md").read_text(encoding="utf-8"))
    want = tuple(map(int, m[-1])) if m else None
    print(f"golden: {got[0]} cases, value {got[1]}, error {got[2]}, invariance {got[3]}; duplicate ids {len(dup)}; handover states {want}")
    return 0 if want == got and not dup else 1


if __name__ == "__main__":
    sys.exit(main())
