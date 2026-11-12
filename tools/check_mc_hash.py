#!/usr/bin/env python3
"""E9: recompute the fixed-seed Monte Carlo hashes from the golden (R6-15). Standard library only.

    python tools/check_mc_hash.py [--self-test]

Fails if datasets/golden/core/mc_hash.json no longer hashes to oracle/MC_HASH_E9.json. --self-test also shows
the check failing on a planted one-ulp change to one uniform (plan 14.10 rule 1).
"""
import hashlib
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def digest(values):
    lines = [v if isinstance(v, str) else float(v).hex() for v in values]
    return hashlib.sha256(("\n".join(lines) + "\n").encode("ascii")).hexdigest()


def hashes(golden):
    out = {}
    for c in golden["cases"]:
        kind = c["operation"].rsplit(".", 1)[1]
        out[f"stream {c['inputs']['stream']} {kind}"] = digest(c["expected"]["outputs"]["values"])
    return out


def problems(golden, ref):
    got = hashes(golden)
    return [f"{k}: {got.get(k)} != {v}" for k, v in ref["sha256"].items() if got.get(k) != v]


def main(argv):
    golden = json.loads((ROOT / "datasets" / "golden" / "core" / "mc_hash.json").read_text(encoding="utf-8"))
    ref = json.loads((ROOT / "oracle" / "MC_HASH_E9.json").read_text(encoding="utf-8"))
    bad = problems(golden, ref)
    for b in bad:
        print("error:", b)
    print(f"E9 hash: {len(ref['sha256'])} hashes, {len(bad)} mismatch(es)")
    if "--self-test" in argv:
        for c in golden["cases"]:
            if c["operation"].endswith("uniforms"):
                v = c["expected"]["outputs"]["values"]
                v[0] = math.nextafter(v[0], 2.0)
                break
        planted = problems(golden, ref)
        print("self-test: planted one-ulp change", "caught" if planted else "NOT caught")
        if not planted:
            return 1
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
