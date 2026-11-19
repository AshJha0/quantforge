"""Packet builder's recheck of the K-5a hidden expected values (hidden side; our own second computation, no outside
check). For each of idr_k-0001..0005, recomputes at 50 digits with mpmath, on the binary64 inputs (exact as mpf):
  estimate_pnl = sum N exp(-yT) (-T h + T^2 h^2 / 2)
  bound        = sum |h|^3 T^3 |N| exp(-T min(y, y + h)) / 6        (KR-7, KR-15, KR-17)
rounds once to binary64 and reports the relative difference to k5a_expected.json. Also prints the exact
remainder |estimate - revaluation| over the bound, which must be at most 1 (Taylor's theorem).

    python -I program/stage_h_blind_w2/k5a_recheck.py <checkout>
Exit 1 if a field differs by more than 1e-15 relative or a remainder exceeds its bound.
"""

import json
import sys
from pathlib import Path

import mpmath as mp

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from k5a_cases import CASES

mp.mp.dps = 50


def exact(inp):
    h = mp.mpf(inp["shift"])
    est = rev = bnd = mp.mpf(0)
    for p in inp["positions"]:
        n, t, y = mp.mpf(p["notional"]), mp.mpf(p["maturity"]), mp.mpf(p["yield"])
        v = n * mp.exp(-y * t)
        est += v * (-t * h + t * t * h * h / 2)
        rev += n * mp.exp(-(y + h) * t) - v
        bnd += abs(h) ** 3 * t**3 * abs(n) * mp.exp(-t * min(y, y + h)) / 6
    return est, rev, bnd


def main():
    root = Path(sys.argv[1])
    exp = json.loads(
        (root / "program/stage_h_blind_w2/k5a_expected.json").read_text(
            encoding="utf-8"
        )
    )["cases"]
    bad = 0
    print("case\tfield\texpected\trecomputed\trel diff")
    for cid, _, _, inp in CASES:
        est, rev, bnd = exact(inp)
        got = {"estimate_pnl": float(est), "bound": float(bnd)}
        for f in exp[cid]["fields"]:
            if f["path"] not in got:
                continue
            e, g = f["value"], got[f["path"]]
            rel = abs(g - e) / abs(e)
            bad += rel > 1e-15
            print(f"{cid}\t{f['path']}\t{e!r}\t{g!r}\t{rel:.1e}")
        ratio = abs(est - rev) / bnd
        bad += ratio > 1
        print(
            f"{cid}\tremainder/bound\t-\t{mp.nstr(ratio, 6)}\t{'OK' if ratio <= 1 else 'VIOLATION'}"
        )
    print(f"# {bad} problems")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
