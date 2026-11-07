#!/usr/bin/env python3
"""Seeded sample swap book (benchmarks/targets.md). Synthetic, never real positions. Standard library only.

  python tools/workflows/sample_book.py --trades 10000 [--seed 20261107] [--out book.json]
"""
import argparse
import hashlib
import json
import math
import random
import sys

TENORS = ["1Y", "2Y", "3Y", "5Y", "7Y", "10Y", "15Y", "20Y", "30Y"]


def book(n, seed=20261107, convention="SOFR"):
    """Fixed rates are an offset in [-100bp, +100bp] around a par rate the caller supplies per tenor."""
    rng = random.Random(seed)
    out = []
    for i in range(n):
        out.append({"id": f"T{i + 1:05d}", "convention": convention, "tenor": rng.choice(TENORS),
                    "notional": round(math.exp(rng.uniform(math.log(1e6), math.log(1e8))), -3),
                    "side": rng.choice(["PAY", "RECEIVE"]), "offset": round(rng.uniform(-0.01, 0.01), 6)})
    return out


def digest(trades):
    return hashlib.sha256(json.dumps(trades, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trades", type=int, default=10000)
    ap.add_argument("--seed", type=int, default=20261107)
    ap.add_argument("--out")
    a = ap.parse_args()
    b = book(a.trades, a.seed)
    text = json.dumps({"seed": a.seed, "sha256": digest(b), "trades": b}, indent=1)
    if a.out:
        open(a.out, "w", encoding="utf-8").write(text + "\n")
    else:
        print(text)
    print(f"sha256 {digest(b)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
