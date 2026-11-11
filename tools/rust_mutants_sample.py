#!/usr/bin/env python3
"""Seeded sample of cargo-mutants mutants for one Rust file, with a Wilson score interval.

The full credit.rs run is about 400 mutants and takes most of a day on a laptop, so the score is
estimated from a simple random sample drawn without replacement with a fixed seed:

    python tools/rust_mutants_sample.py list  '**/credit.rs' --n 60 --seed 20261111 > sample.txt
    tools/rust_mutants_sample.sh ...           (or: tools/rust_mutants.sh '**/credit.rs' -F <regex>)
    python tools/rust_mutants_sample.py score <scratch>/repo/rust/mutants.out

`list` runs `cargo mutants --list` (no build) inside rust/, sorts the names, draws the sample
with `random.Random(seed).sample` and prints one `-F` regex that matches exactly those names.
`score` reads caught/missed/timeout/unviable from mutants.out; the score is
caught / (caught + missed), timeouts counted as caught (as the C++ wrapper does), unviable
mutants excluded, with a 95% Wilson interval. With a sample from a finite population the
interval is conservative (no finite-population correction).
"""
import json
import math
import random
import re
import subprocess
import sys
from pathlib import Path


def names(glob: str) -> list[str]:
    root = Path(__file__).resolve().parents[1] / "rust"
    out = subprocess.run(
        ["cargo", "mutants", "--list", "--json", "-p", "quantforge-core", "-f", glob],
        cwd=root, capture_output=True, text=True, check=True).stdout
    return sorted(m["name"] if "name" in m else str(m) for m in json.loads(out))


def wilson(k: int, n: int, z: float = 1.959964) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)


def main() -> int:
    cmd = sys.argv[1]
    if cmd == "list":
        glob = sys.argv[2]
        n = int(sys.argv[sys.argv.index("--n") + 1])
        seed = int(sys.argv[sys.argv.index("--seed") + 1])
        all_names = names(glob)
        pick = sorted(random.Random(seed).sample(all_names, n))
        print(f"# population {len(all_names)}, sample {n}, seed {seed}", file=sys.stderr)
        for p in pick:
            print(p, file=sys.stderr)
        print("^(" + "|".join(re.escape(p) for p in pick) + ")$")
        return 0
    if cmd == "score":
        d = Path(sys.argv[2])
        cnt = {k: len([l for l in (d / f"{k}.txt").read_text().splitlines() if l.strip()])
               for k in ("caught", "missed", "timeout", "unviable")}
        killed = cnt["caught"] + cnt["timeout"]
        tested = killed + cnt["missed"]
        lo, hi = wilson(killed, tested)
        print(json.dumps({**cnt, "score": killed / tested if tested else None,
                          "wilson95": [lo, hi]}, indent=1))
        return 0
    return 64


if __name__ == "__main__":
    sys.exit(main())
