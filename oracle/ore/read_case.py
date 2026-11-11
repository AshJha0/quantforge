"""Read an ORE case's raw cube (deflated NPVs per sample) and return, per netting set and grid date, the discounted EE
with its Monte Carlo standard error, the discounted ENE, and the PFE quantiles of the deflated exposure (ruling G-42).

    python read_case.py <case dir>
"""
import csv
import json
import math
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

ASOF = date(2026, 11, 10)


def read(case_dir, quantiles=(0.95, 0.99)):
    vals = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))  # ns -> date -> sample -> value (summed over trades)
    for row in csv.reader(open(Path(case_dir) / "Output" / "netcube.csv")):
        if row[0].startswith("#"):
            continue
        ns, dt, smp, v = row[0], row[3], int(row[4]), float(row[6])
        vals[ns][dt][smp] += v
    out = {}
    for ns, by_date in vals.items():
        rows = []
        for dt in sorted(by_date):
            if dt == ASOF.isoformat():
                continue
            xs = list(by_date[dt].values())
            n = len(xs)
            pos = [max(x, 0.0) for x in xs]
            m = sum(pos) / n
            se = math.sqrt(sum((p - m) ** 2 for p in pos) / (n - 1) / n)
            s = sorted(pos)
            t = (date.fromisoformat(dt) - ASOF).days / 365
            rows.append({"time": t, "ee": m, "ee_se": se, "ene": sum(min(x, 0.0) for x in xs) / n,
                         **{f"pfe_{int(q * 100)}": s[max(0, math.ceil(q * n) - 1)] for q in quantiles}, "samples": n})
        out[ns] = rows
    return out


if __name__ == "__main__":
    print(json.dumps(read(sys.argv[1]), indent=1))
