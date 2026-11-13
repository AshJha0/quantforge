#!/usr/bin/env python3
"""Microbenchmark regression gate (plan 12.2 G2). Standard library only.

    python tools/bench_gate.py --current benchmarks/micro/out [--baseline benchmarks/micro/baseline.json]
    python tools/bench_gate.py --current benchmarks/micro/out --write-baseline --machine github-ubuntu-24.04

Reads every <lang>.json in --current (schema: {"lang", "benchmarks": {id: {"ns_per_op", "allocs_per_op",
["alloc_bytes_per_op"]}}}) and compares each benchmark with the baseline:
  * time: fails if ns_per_op is more than --time-ratio (default 1.5) times the baseline. Checked only when the
    baseline's "machine" equals --machine, since timings from another machine class say nothing;
  * allocations: fails if allocs_per_op or alloc_bytes_per_op grows by more than --alloc-ratio (default 1.10)
    plus 1 allocation (or 64 bytes). Also only on the same machine class: allocator, runtime and OS change counts;
  * a benchmark in the baseline that is missing from the results fails;
  * with --require-baseline (R6-15, review finding 15): fails unless the stored baseline was recorded on --machine
    and holds every language in the results. At v0.8.0 the baseline was empty and the gate compared nothing.
Prints a Markdown table (ns/op and allocs/op per language) for the job summary. Exit 1 on any failure.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "benchmarks" / "micro" / "baseline.json"
IDS = ("bootstrap", "swap_pv", "implied_vol")


def load_results(path):
    p = Path(path)
    files = sorted(p.glob("*.json")) if p.is_dir() else [p]
    out = {}
    for f in files:
        d = json.loads(f.read_text(encoding="utf-8"))
        out[d["lang"]] = d["benchmarks"]
    return out


def grew(cur, base, ratio, slack):
    return cur is not None and base is not None and cur > base * ratio + slack


def compare(current, baseline, machine, time_ratio=1.5, alloc_ratio=1.10):
    """Returns (table lines, failures)."""
    timed = baseline.get("machine") == machine
    fails, rows = [], []
    for lang, benches in sorted(baseline.get("results", {}).items()):
        # Each CI job benchmarks one language: gate the languages this run measured. A missing
        # benchmark inside a measured language still fails.
        if current and lang not in current:
            continue
        for bid, b in sorted(benches.items()):
            c = current.get(lang, {}).get(bid)
            if c is None:
                fails.append(f"{lang} {bid}: no result")
                continue
            flags = []
            if timed and grew(c["ns_per_op"], b["ns_per_op"], time_ratio, 0):
                flags.append(f"time {c['ns_per_op'] / b['ns_per_op']:.2f}x")
            if timed and grew(c.get("allocs_per_op"), b.get("allocs_per_op"), alloc_ratio, 1):
                flags.append(f"allocs {b['allocs_per_op']:g} -> {c['allocs_per_op']:g}")
            if timed and grew(c.get("alloc_bytes_per_op"), b.get("alloc_bytes_per_op"), alloc_ratio, 64):
                flags.append(f"bytes {b['alloc_bytes_per_op']:g} -> {c['alloc_bytes_per_op']:g}")
            if flags:
                fails.append(f"{lang} {bid}: {', '.join(flags)}")
            rows.append(f"| {lang} | {bid} | {c['ns_per_op']:,.0f} | {b['ns_per_op']:,.0f} | "
                        f"{fmt(c.get('allocs_per_op'))} | {fmt(c.get('alloc_bytes_per_op'))} | {'; '.join(flags) or 'ok'} |")
    head = [f"Baseline machine `{baseline.get('machine')}`, this run `{machine}`: time "
            + (f"time gated at {time_ratio}x, allocations at {alloc_ratio}x." if timed
               else "not gated: different machine class (allocator, runtime and OS differ). Refresh the baseline from CI."), "",
            "| Language | Benchmark | ns/op | baseline ns/op | allocs/op | bytes/op | Result |", "|---|---|---:|---:|---:|---:|---|"]
    return head + rows, fails


def fmt(x):
    return "" if x is None else f"{x:,.1f}"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--current", required=True)
    ap.add_argument("--baseline", default=str(BASELINE))
    ap.add_argument("--machine", default="local")
    ap.add_argument("--time-ratio", type=float, default=1.5)
    ap.add_argument("--alloc-ratio", type=float, default=1.10)
    ap.add_argument("--write-baseline", action="store_true")
    ap.add_argument("--require-baseline", action="store_true")
    a = ap.parse_args(argv)
    current = load_results(a.current)
    if a.write_baseline:
        Path(a.baseline).write_text(json.dumps({"machine": a.machine, "results": current}, indent=1, sort_keys=True) + "\n",
                                    encoding="utf-8")
        print(f"baseline written for {', '.join(sorted(current))} on {a.machine}")
        return 0
    baseline = json.loads(Path(a.baseline).read_text(encoding="utf-8"))
    lines, fails = compare(current, baseline, a.machine, a.time_ratio, a.alloc_ratio)
    if a.require_baseline:
        if baseline.get("machine") != a.machine:
            fails.append(f"stored baseline machine is {baseline.get('machine')!r}, not {a.machine!r}: the gate compares nothing")
        for lang in sorted(set(current) - set(baseline.get("results", {}))):
            fails.append(f"{lang}: no stored baseline")
    print("\n".join(lines))
    for f in fails:
        print("BAD", f)
    print(f"bench gate: {len(fails)} regressions")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
