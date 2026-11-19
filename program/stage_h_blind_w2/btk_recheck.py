"""Packet builder's own recheck of the 12 hidden K-8e expected values from the inputs (exact rational binomial sums).

Hidden side. This is our second computation of our own goldens; it counts as no outside check. It shows that the
expected file and the rules agree before the deriver starts, so a later mismatch points at the reading, not at a
copy slip.
    python -I program/stage_h_blind_w2/btk_recheck.py <checkout>
"""
import json
import sys
from fractions import Fraction
from math import comb
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from btk_compare import load_expected, same  # noqa: E402
from btk_make_packet import CASES  # noqa: E402

MULT = [Fraction(x) for x in ("1.50", "1.50", "1.50", "1.50", "1.50", "1.70", "1.76", "1.83", "1.88", "1.92")]


def cdf(n, p, k):
    return sum(comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k + 1))


def first(n, p, level):
    acc = Fraction(0)
    for k in range(n + 1):
        acc += comb(n, k) * p ** k * (1 - p) ** (n - k)
        if acc >= level:
            return k
    raise AssertionError


def zone(i):
    n, p = i["observations"], Fraction(1, 100)
    x = max(i["exceptions_actual"], i["exceptions_hypothetical"])
    a, r = first(n, p, Fraction(95, 100)), first(n, p, Fraction(9999, 10000))
    m = None if n != 250 else float(MULT[x] if x < 10 else Fraction(2))
    return {"exceptions": x, "cumulative_probability": float(cdf(n, p, x)),
            "zone": "RED" if x >= r else "AMBER" if x >= a else "GREEN", "amber_from": a, "red_from": r, "multiplier": m}


def desk(i):
    n = i["observations"]
    x99 = max(i["exceptions_99_actual"], i["exceptions_99_hypothetical"])
    x975 = max(i["exceptions_975_actual"], i["exceptions_975_hypothetical"])
    return {"exceptions_99": x99, "exceptions_975": x975,
            "cumulative_probability_99": float(cdf(n, Fraction(1, 100), x99)),
            "cumulative_probability_975": float(cdf(n, Fraction(25, 1000), x975)),
            "breach_99": x99 > 12, "breach_975": x975 > 30, "eligible": not (x99 > 12 or x975 > 30)}


def count(i):
    def days(pl):
        return [t for t, (v, q) in enumerate(zip(i["var"], pl)) if v is None or q is None or -q > v]
    da, dh = days(i["actual"]), days(i["hypothetical"])
    return {"observations": len(i["var"]), "exceptions_actual": len(da), "exceptions_hypothetical": len(dh),
            "exceptions": max(len(da), len(dh)), "days_actual": da, "days_hypothetical": dh}


def main():
    exp = load_expected(sys.argv[1] if len(sys.argv) > 1 else ".")
    fn = {"risk.frtb.backtest.zone": zone, "risk.frtb.backtest.desk": desk, "risk.frtb.backtest.count": count}
    bad = 0
    for cid, op, inp in CASES:
        got = fn[op](inp)
        for f in exp[cid]["fields"]:
            ok = same(got[f["path"]], f["value"], f["class"], set())
            bad += not ok
            if not ok:
                print(f"DIFF\t{cid}\t{f['path']}\t{f['value']!r}\t{got[f['path']]!r}")
    print(f"# recheck: {sum(len(e['fields']) for e in exp.values())} fields, {bad} DIFF")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
