#!/usr/bin/env python3
"""T6/T7 timing (plan 14.7 H-8): wall time per `hedge.qp.solve` case of r6/hedgeqp_large_r6.

Runs each golden case in one warm process, checks x against the golden, and prints a markdown table.
`--gate` exits 1 when a case misses the Python target (T7: n = 50 within 2 s; T6: n = 200 within 20 s)
or x moves by more than 1e-6 relative. `--profile CASE_ID` prints a cProfile of one case.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

import quantforge_core.cli.operations  # noqa: E402,F401  (registers the operations)
from quantforge_core.cli.registry import execute  # noqa: E402

GOLDEN = ROOT / "datasets" / "golden" / "r6" / "hedgeqp_large_r6.json"
TARGET_S = {50: 2.0, 200: 20.0}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gate", action="store_true")
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--profile")
    args = ap.parse_args()
    cases = json.loads(GOLDEN.read_text())["cases"]
    if args.profile:
        import cProfile
        import pstats

        c = next(c for c in cases if c["case_id"] == args.profile)
        prof = cProfile.Profile()
        prof.runcall(execute, c["operation"], c["inputs"])
        pstats.Stats(prof).sort_stats("tottime").print_stats(25)
        return 0
    rows, failed = [], False
    for c in cases:
        n = len(c["inputs"]["a"][0])
        best = float("inf")
        out = None
        for _ in range(args.repeat):
            t0 = time.perf_counter()
            out = execute(c["operation"], c["inputs"])
            best = min(best, time.perf_counter() - t0)
        err = max(abs(g - w) / max(1.0, abs(w)) for g, w in zip(out["x"], c["expected"]["x"]))
        miss = best > TARGET_S[n]
        failed |= miss or err > 1e-6
        rows.append(f"| {c['case_id']} | {n} | {best:.3f} | {TARGET_S[n]:.0f} | {err:.1e} | {'MISS' if miss else 'ok'} |")
    print("| case | n | wall s (best) | Python target s | max rel err x | T6/T7 |\n|---|---|---|---|---|---|")
    print("\n".join(rows))
    return 1 if (args.gate and failed) else 0


if __name__ == "__main__":
    sys.exit(main())
