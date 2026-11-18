"""H-20 central-bank curve consistency checks (docs/validation/central-bank-consistency.md).

Circular by construction for A1, A2 and B2: they rebuild a published curve from the publisher's own
parameters or levels. Consistency checks, not validation. Inputs are real public downloads kept
outside the repository; read with `python -I`. The output is a reconciliation record, never a golden.

    python -I tools/validation/cb_consistency.py --gsw feds200628.csv --ons ons_d7bt_mm23.csv \
        --retrieved 2026-11-18 --out docs/validation/data/cb-consistency.json
"""

import argparse
import csv
import hashlib
import json
import math
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from quantforge_core import curve_fits, inflation  # noqa: E402

GSW_URL = "https://www.federalreserve.gov/data/yield-curve-tables/feds200628.csv"
ONS_URL = "https://www.ons.gov.uk/generator?format=csv&uri=/economy/inflationandpriceindices/timeseries/d7bt/mm23"
MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def gsw_rows(path):
    rows = list(csv.reader(open(path, encoding="utf-8")))
    hi = next(i for i, r in enumerate(rows) if r and r[0] == "Date")
    head = rows[hi]
    out = []
    for r in rows[hi + 1:]:
        if not r or r[0][:2] not in ("19", "20"):
            continue
        v = dict(zip(head, r, strict=False))
        try:
            p = [float(v[k]) for k in ("BETA0", "BETA1", "BETA2", "BETA3", "TAU1", "TAU2")]
        except (KeyError, ValueError):
            continue
        if any(math.isnan(x) for x in p) or p[4] <= 0 or p[5] <= 0:
            continue
        out.append((v["Date"], p, v))
    return out


def svensson(p, t):
    b0, b1, b2, b3, t1, t2 = p
    a, b = t / t1, t / t2
    f1, f2 = -math.expm1(-a) / a, -math.expm1(-b) / b
    zero = b0 + b1 * f1 + b2 * (f1 - math.exp(-a)) + b3 * (f2 - math.exp(-b))
    fwd = b0 + b1 * math.exp(-a) + b2 * a * math.exp(-a) + b3 * b * math.exp(-b)
    return zero, fwd  # percent


def num(v, k):
    s = v.get(k, "NA")
    try:
        x = float(s)
    except ValueError:
        return None
    return None if math.isnan(x) else x


def gate(diffs_bp):
    n = len(diffs_bp)
    within = sum(1 for d in diffs_bp if d <= 0.05)
    return {"points": n, "share_within_0.05bp": within / n, "max_bp": max(diffs_bp),
            "pass": within / n >= 0.999 and max(diffs_bp) <= 0.5}


def check_gsw(rows):
    dz, df = [], []
    for _, p, v in rows:
        for n in range(1, 31):
            z, f = svensson(p, n)
            pz, pf = num(v, f"SVENY{n:02d}"), num(v, f"SVENF{n:02d}")
            if pz is not None:
                dz.append(abs(z - pz) * 100)
            if pf is not None:
                df.append(abs(f - pf) * 100)
    a1, a2 = gate(dz), gate(df)
    # A3: library three-factor NS fitted to the 30 published zeros, month-end rows since 2000.
    month_end = {}
    for d, _, v in rows:
        if d >= "2000-01-01":
            month_end[d[:7]] = v
    taus = [0.25 * k for k in range(1, 41)]
    rmses = []
    for v in month_end.values():
        ms = [n for n in range(1, 31) if num(v, f"SVENY{n:02d}") is not None]
        if len(ms) < 30:
            continue
        ys = [num(v, f"SVENY{n:02d}") / 100 for n in ms]
        best = min((curve_fits.robust(ms, ys, t, 1.0) for t in taus), key=lambda r: r[3])
        rmses.append(math.sqrt(statistics.fmean(r * r for r in best[1])) * 1e4)
    rmses.sort()
    med, p95 = statistics.median(rmses), rmses[min(len(rmses) - 1, int(0.95 * len(rmses)))]
    a3 = {"dates": len(rmses), "median_rmse_bp": med, "p95_rmse_bp": p95, "max_rmse_bp": rmses[-1],
          "pass": med <= 5 and p95 <= 15}
    return {"rows": len(rows), "first": rows[0][0], "last": rows[-1][0], "A1_zeros": a1, "A2_forwards": a2,
            "A3_library_ns_fit": a3}


def ons_months(path):
    out = {}
    for r in csv.reader(open(path, encoding="utf-8")):
        if len(r) == 2 and len(r[0]) == 8 and r[0][5:] in MONTHS:
            out[inflation.index(int(r[0][:4]), MONTHS.index(r[0][5:]) + 1)] = float(r[1])
    return out


def check_ons(path):
    m = ons_months(path)
    y2015 = [m[inflation.index(2015, k)] for k in range(1, 13)]
    b1 = {"mean_2015": statistics.fmean(y2015), "pass": abs(statistics.fmean(y2015) - 100) <= 0.05}
    base = inflation.index(2016, 1)
    years = [y for y in range(1, 100) if base + 12 * y in m]
    quotes = tuple((float(y), (m[base + 12 * y] / m[base]) ** (1 / y) - 1) for y in years)
    curve = inflation.CpiCurve(inflation.CpiCurveData(base, m[base], quotes, None))
    base_err = abs(curve.cpi(base) - m[base])
    pillar_err = max(abs(curve.cpi(base + 12 * y) - m[base + 12 * y]) for y in years)
    b2 = {"base": "2016-01", "base_cpi": m[base], "pillars": len(years), "base_abs_err": base_err,
          "max_pillar_abs_err": pillar_err, "pass": base_err <= 1e-9 and pillar_err <= 1e-6}
    last = base + 12 * years[-1]
    gaps = [abs(curve.cpi(k) - m[k]) for k in range(base, last + 1) if k in m and (k - base) % 12]
    b3 = {"months": len(gaps), "max_abs_gap": max(gaps), "mean_abs_gap": statistics.fmean(gaps),
          "gate": "informational, none"}
    return {"latest_month": f"{max(m) // 12}-{max(m) % 12 + 1:02d}", "B1_base_year": b1,
            "B2_library_base_pillars": b2, "B3_between_pillars": b3}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gsw", required=True)
    ap.add_argument("--ons", required=True)
    ap.add_argument("--retrieved", required=True)
    ap.add_argument("--out")
    a = ap.parse_args()
    rec = {
        "generator": "tools/validation/cb_consistency.py",
        "nature": "consistency checks, not validation; A1, A2, B2 are circular by construction",
        "golden": False,
        "sources": {
            "gsw": {"url": GSW_URL, "retrieved": a.retrieved, "sha256": sha(a.gsw),
                    "terms": "Federal Reserve Board public data"},
            "ons_d7bt": {"url": ONS_URL, "retrieved": a.retrieved, "sha256": sha(a.ons),
                         "terms": "Open Government Licence v3.0"},
        },
        "gsw": check_gsw(gsw_rows(a.gsw)),
        "ons_cpi": check_ons(a.ons),
    }
    text = json.dumps(rec, indent=1) + "\n"
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8", newline="\n")
    print(text)


if __name__ == "__main__":
    main()
