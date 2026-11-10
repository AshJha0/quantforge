#!/usr/bin/env python3
"""Convert JMH -rf json output (run with -prof gc) to benchmarks/micro/out/<lang>.json."""
import json
import os
import sys


def main(src, dst, lang="java"):
    with open(src, encoding="utf-8") as f:
        runs = json.load(f)
    out = {}
    for r in runs:
        name = r["benchmark"].rsplit(".", 1)[-1]
        prim = r["primaryMetric"]
        if prim["scoreUnit"] != "ns/op":
            sys.exit(f"unexpected unit {prim['scoreUnit']} for {name}")
        alloc = r.get("secondaryMetrics", {}).get("gc.alloc.rate.norm", {}).get("score")
        out[name] = {"ns_per_op": float(prim["score"]), "allocs_per_op": None,
                     "alloc_bytes_per_op": None if alloc is None else float(alloc)}
    missing = {"bootstrap", "swap_pv", "implied_vol"} - out.keys()
    if missing:
        sys.exit(f"missing benchmarks: {sorted(missing)}")
    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
    with open(dst, "w", encoding="utf-8") as f:
        json.dump({"lang": lang, "benchmarks": out}, f, indent=2)
        f.write("\n")


if __name__ == "__main__":
    main(*sys.argv[1:])
