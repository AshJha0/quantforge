"""Convert Google Benchmark JSON from qf_micro to benchmarks/micro/out/cpp.json. Stdlib only.

Usage: python gbench_to_json.py <raw.json> <out.json>
"""
import json
import os
import sys

NAMES = ("bootstrap", "swap_pv", "implied_vol")
UNIT_NS = {"ns": 1.0, "us": 1e3, "ms": 1e6, "s": 1e9}


def main(raw_path, out_path):
    with open(raw_path, encoding="utf-8") as f:
        raw = json.load(f)
    found = {}
    for b in raw["benchmarks"]:
        name = b.get("run_name", b["name"])
        if name not in NAMES or b.get("run_type", "iteration") != "iteration":
            continue
        found[name] = {
            "ns_per_op": float(b["real_time"]) * UNIT_NS[b.get("time_unit", "ns")],
            "allocs_per_op": float(b.get("allocs_per_op", 0.0)),
        }
    missing = [n for n in NAMES if n not in found]
    if missing:
        sys.exit("missing benchmarks: " + ", ".join(missing))
    out = {"lang": "cpp", "benchmarks": {n: found[n] for n in NAMES}}
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f)
        f.write("\n")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
