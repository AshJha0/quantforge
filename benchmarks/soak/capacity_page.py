#!/usr/bin/env python3
"""Writes the measured tables of docs/capacity.md from the raw K-6 files. Standard library only.

    python benchmarks/soak/capacity_page.py           rewrite the block between the markers
    python benchmarks/soak/capacity_page.py --check   exit 1 if the block is stale

Plain idea: no figure on the capacity page is typed by hand. Every number in the generated block is read from a
file in benchmarks/results/k6/ (capacity-*.json, soak-*.verdict.json), and each table row names its file, host
and commit. Files whose names end in -ci (runner artifacts) are listed if present; none are committed yet.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RES = ROOT / "benchmarks" / "results" / "k6"
PAGE = ROOT / "docs" / "capacity.md"
BEGIN = "<!-- capacity-generated: begin (benchmarks/soak/capacity_page.py) -->"
END = "<!-- capacity-generated: end -->"


def fmt(x, nd=1):
    if x is None:
        return "n/a"
    if isinstance(x, float):
        return f"{x:,.{nd}f}"
    if isinstance(x, int):
        return f"{x:,}"
    return str(x)


def block():
    out = []
    caps = [p for p in sorted(RES.glob("capacity-*.json")) if "planted" not in p.name]
    out.append("### Throughput, latency and batch size\n")
    out.append(
        "| Build | Row | Status | Cases | Processes | Cases per second | p50 (us) | p99 (us) | Peak memory (MiB) | File |"
    )
    out.append("|---|---|---|---|---|---|---|---|---|---|")
    for p in caps:
        d = json.loads(p.read_text(encoding="utf-8"))
        for r in d["rows"]:
            if not r["row"].startswith(("mix/", "batch/")):
                continue
            ok = r["status"] == "pass"
            out.append(
                f"| {d['implementation']} | `{r['row']}` | {r['status']} | {fmt(r['cases'])} | {r['processes']} | "
                f"{fmt(r['cases_per_s']) if ok else 'no figure'} | {fmt(r['p50_us']) if ok else ''} | "
                f"{fmt(r['p99_us']) if ok else ''} | {fmt(r['peak_judged_mib']) if ok else ''} | `{p.name}` |"
            )
    out.append("\n### Input-size ceilings (documented limits from `specifications/01-core/limits.md`)\n")
    out.append(
        "| Build | Operation | Size | Limit | Status | Answer | Wall time (s) | Extra memory (MiB) | Request (bytes) |"
    )
    out.append("|---|---|---|---|---|---|---|---|---|")
    for p in caps:
        d = json.loads(p.read_text(encoding="utf-8"))
        for r in d["rows"]:
            if r["row"].startswith("ceiling/"):
                ans = r["answer"][1] or r["answer"][0]
                out.append(
                    f"| {d['implementation']} | `{r['operation']}` | {fmt(r['size'])} | {fmt(r['limit'])} | "
                    f"{r['status']} | {ans} | {fmt(r['wall_s'], 3)} | {fmt(r['extra_memory_mib'], 2)} | "
                    f"{fmt(r['request_bytes'])} |"
                )
    out.append("\n### Hosts and commits of the capacity files\n")
    out.append("| File | Host | Commit | Platform | Logical CPUs | Memory figure | Verdict |")
    out.append("|---|---|---|---|---|---|---|")
    for p in sorted(RES.glob("capacity-*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        out.append(
            f"| `{p.name}` | {d['host']} | `{d['commit'][:8]}` | {d['platform']} | {d['logical_cpus']} | "
            f"{d['memory_key']} | {d['verdict']} |"
        )
    out.append("\n### Soak verdicts\n")
    out.append(
        "| File | Build | Host | Commit | Verdict | Reasons | Slope (MiB/h) | Slope 95 % CI | Range / median | "
        "Median (MiB) | Samples | Cases |"
    )
    out.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    verdicts = sorted(RES.glob("soak-*.verdict.json"))
    for p in verdicts:
        v = json.loads(p.read_text(encoding="utf-8"))
        ci = v["slope_ci95_mib_per_h"]
        out.append(
            f"| `{p.name}` | {v['implementation']} | {v['host']} | `{(v['commit'] or '')[:8]}` | {v['verdict']} | "
            f"{', '.join(v['reasons']) or 'none'} | {v['slope_mib_per_h']} | {ci if ci else 'n/a'} | "
            f"{v['range_fraction_of_median']} | {v['median_mib']} | {v['samples_after_warmup']} | {fmt(v['cases'])} |"
        )
    if not verdicts:
        out.append("| none yet | | | | | | | | | | | |")
    return "\n".join(out) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    text = PAGE.read_text(encoding="utf-8")
    head, _, rest = text.partition(BEGIN)
    _, _, tail = rest.partition(END)
    new = f"{head}{BEGIN}\n{block()}{END}{tail}"
    if a.check:
        if new != text:
            print("docs/capacity.md: generated block is stale; run benchmarks/soak/capacity_page.py", file=sys.stderr)
            return 1
        print("docs/capacity.md: generated block is current")
        return 0
    PAGE.write_text(new, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
