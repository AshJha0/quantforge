"""Writes datasets/scenarios/k5_snapshot.json, the shared K-5 snapshot scenario (KR-287).

The book is drawn once here from random.Random(20261120) and written out in full, so no other build needs
this generator's random number stream. The expected values at the check versions come from the Python
reference build (`quantforge_core.snapshot.build`); every build compares its own values with them at
1e-9 relative (the stage K golden tolerance). Simulated data; latency-aware analytics on simulated data.

    python datasets/scenarios/build_k5_snapshot.py          # rewrite
    python datasets/scenarios/build_k5_snapshot.py --check  # fail if the file differs
"""

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from quantforge_core import snapshot as sn
from quantforge_core import stage_k as sk

OUT = ROOT / "datasets" / "scenarios" / "k5_snapshot.json"
CHECK_VERSIONS = [0, 1, 2, 3, 200, 401, 402, 500, 999, 1000]


def make() -> dict:
    rng = random.Random(20261120)
    book = []
    for _ in range(20):
        n = float(rng.randrange(-1_000_000, 1_000_001, 1_000))
        t = round(rng.uniform(0.25, 30.0), 2)
        y = round(rng.uniform(0.01, 0.06), 4)
        book.append({"notional": n, "maturity": t, "yield": y})
    hedge = {"maturity": 10.0, "yield": 0.04}
    positions = [sk.ZeroPosition(p["notional"], p["maturity"], p["yield"]) for p in book]
    instr = sn.HedgeInstrument(hedge["maturity"], hedge["yield"])
    expected = []
    for k in CHECK_VERSIONS:
        s = sn.build(k, k, positions, instr, sn.scenario_shift(k))
        expected.append(
            {
                "version": k,
                "shift": s.shift,
                "estimate_pnl": s.estimate_pnl,
                "bound": s.bound,
                "book_delta": s.book_delta,
                "hedge_unit_delta": s.hedge_unit_delta,
                "hedge_notional": s.hedge_notional,
            }
        )
    return {
        "label": sk.LABEL,
        "spec": "specifications/12-platform/lock-free-snapshots.md",
        "rulings": "specifications/stage-k-rulings-k5.md (KR-280 to KR-288, PROPOSED)",
        "data": "simulated; book drawn from random.Random(20261120); no market data",
        "shift_rule": "version 0: 0; version k >= 1: ((k * 7919) mod 401 - 200) * 5e-5",
        "checksum": {"seed": "0x9E3779B97F4A7C15", "mul": "0x94D049BB133111EB", "rotl": 27},
        "book": book,
        "hedge": hedge,
        "race": {"publishes_default": 20000, "publishes_long": 1000000, "readers": [1, 4, 16], "verify_every": 64},
        "exactness_publishes": 1000,
        "tolerance_relative": 1e-9,
        "expected": expected,
        "reviewer": "none: self-assessment; no second review (owner decision 2026-11-18)",
    }


def main() -> int:
    text = json.dumps(make(), indent=1) + "\n"
    if "--check" in sys.argv:
        if OUT.read_text(encoding="utf-8") != text:
            print(f"{OUT} is stale: rerun datasets/scenarios/build_k5_snapshot.py")
            return 1
        return 0
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
