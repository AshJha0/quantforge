"""Writes datasets/scenarios/k5a_intraday_moves.json: the K-5a acceptance book and its 1,000 moves, written in
full so every build tests the same moves (coordinator request on K-5, 2026-11-20).

Same draws as python/tests/test_stage_k_w1.py::test_intraday_bound_acceptance_1000_moves: numpy
default_rng(20261118), 50 positions (notional U[-5e6, 5e6], maturity U[0.1, 30], yield U[-0.01, 0.08]), then
1,000 shifts h ~ U[-0.02, 0.02]. Values are binary64, written with the shortest round-trip repr. Simulated
data; latency-aware analytics on simulated data.

    python datasets/scenarios/build_k5a_moves.py          # rewrite
    python datasets/scenarios/build_k5a_moves.py --check  # fail if the file differs
"""

import json
import sys
from pathlib import Path

import numpy as np

OUT = Path(__file__).resolve().parent / "k5a_intraday_moves.json"


def make() -> dict:
    rng = np.random.default_rng(20261118)
    book = [
        [
            float(rng.uniform(-5e6, 5e6)),
            float(rng.uniform(0.1, 30)),
            float(rng.uniform(-0.01, 0.08)),
        ]
        for _ in range(50)
    ]
    moves = [float(h) for h in rng.uniform(-0.02, 0.02, 1000)]
    return {
        "label": "latency-aware analytics on simulated data",
        "spec": "specifications/06-risk/intraday-risk-bounds.md (acceptance: 1,000 random moves)",
        "seed": "numpy default_rng(20261118): 50 x (notional U[-5e6,5e6], maturity U[0.1,30], yield U[-0.01,0.08]), then 1,000 h ~ U[-0.02,0.02]",
        "book_columns": ["notional", "maturity", "yield"],
        "book": book,
        "moves": moves,
        "pass_rule": "abs(estimate_pnl - full revaluation) <= bound on every move, in each build's binary64",
        "reviewer": "none: self-assessment; no second review (owner decision 2026-11-18)",
    }


def main() -> int:
    text = json.dumps(make(), indent=1) + "\n"
    if "--check" in sys.argv:
        if OUT.read_text(encoding="utf-8") != text:
            print(f"{OUT} is stale: rerun datasets/scenarios/build_k5a_moves.py")
            return 1
        return 0
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
