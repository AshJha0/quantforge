#!/usr/bin/env python3
"""Measures CLI batch throughput per language. Standard library only. Holds no financial logic.

Each implementation gets the same JSON Lines workload, built from the inputs of golden cases, through
`quantforge batch`. The clock runs from process start to end of output, so start-up is included.
Start-up is measured apart with `quantforge version`. A batch of one fifth the size gives the marginal
rate, (N - N/5) / (t(N) - t(N/5)), which leaves fixed start-up costs out. The script checks the line count, and that every
language gave the same status on every line, so a fast wrong run is not reported.

Usage: cli_throughput.py [--impl NAME ...] [--suite GLOB] [--cases N] [--repeats N] [--out FILE]
Exit status: 0 finished; 1 an implementation failed or disagreed; 2 bad usage.
"""
import argparse
import datetime
import json
import os
import platform
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "conformance" / "runner"))
from runner import load_impls, resolve_command  # noqa: E402


def workload(suite, count):
    """The golden inputs in file order, repeated until there are `count` lines. Expected values stay out."""
    cases = []
    for path in sorted((ROOT / "datasets" / "golden").rglob(f"{suite}.json")):
        cases += json.loads(path.read_text(encoding="utf-8"))["cases"]
    if not cases:
        raise SystemExit("no golden files matched")
    lines = []
    for i in range(count):
        c = cases[i % len(cases)]
        lines.append(json.dumps({"schema_version": "1.0", "case_id": f"bench-{i}", "operation": c["operation"],
                                 "inputs": c["inputs"]}, ensure_ascii=False))
    return ("\n".join(lines) + "\n").encode("utf-8"), len(cases)


def timed(argv, cwd, data):
    start = time.perf_counter()
    p = subprocess.run(argv, cwd=cwd, input=data, capture_output=True)
    return time.perf_counter() - start, p


def measure(name, cfg, data, small, count, repeats):
    argv, cwd = resolve_command(cfg)
    took, p = timed(argv + ["version"], cwd, b"")
    if p.returncode:
        raise RuntimeError(f"{name}: version exited {p.returncode}")
    version = json.loads(p.stdout)
    starts = [timed(argv + ["version"], cwd, b"")[0] for _ in range(repeats)]
    timed(argv + ["batch"], cwd, data)  # warm the file cache; not counted
    runs, statuses = [], None
    for _ in range(repeats):
        took, p = timed(argv + ["batch"], cwd, data)
        out = p.stdout.decode("utf-8").splitlines()
        if p.returncode or len(out) != count:
            raise RuntimeError(f"{name}: exit {p.returncode}, {len(out)} lines for {count} cases")
        runs.append(took)
        statuses = [json.loads(line)["status"] for line in out]
    best = statistics.median(runs)
    short = statistics.median(timed(argv + ["batch"], cwd, small)[0] for _ in range(repeats))
    marginal = (count - count // 5) / (best - short) if best > short else None
    return {"implementation": name, "version": version, "startup_seconds_median": round(statistics.median(starts), 4),
            "batch_seconds": [round(x, 4) for x in runs], "batch_seconds_median": round(best, 4),
            "cases_per_second_median": round(count / best), "small_batch_seconds_median": round(short, 4),
            "marginal_cases_per_second": round(marginal) if marginal else None}, statuses


def machine():
    info = {"os": platform.platform(), "machine": platform.machine(), "logical_cpus": os.cpu_count(),
            "python": platform.python_version()}
    try:
        if sys.platform == "win32":
            q = "(Get-CimInstance Win32_Processor).Name; (Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory"
            cpu, mem = subprocess.run(["powershell", "-NoProfile", "-Command", q], capture_output=True,
                                      text=True).stdout.split("\n")[:2]
            info.update(cpu=cpu.strip(), memory_gib=round(int(mem) / 2**30, 1))
        elif sys.platform == "linux":
            text = Path("/proc/cpuinfo").read_text()
            info["cpu"] = next(x.split(":")[1].strip() for x in text.splitlines() if x.startswith("model name"))
            kib = int(Path("/proc/meminfo").read_text().split()[1])
            info["memory_gib"] = round(kib / 2**20, 1)
    except (OSError, ValueError, StopIteration):
        pass
    return info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--impl", action="append")
    ap.add_argument("--suite", default="*")
    ap.add_argument("--cases", type=int, default=20000)
    ap.add_argument("--repeats", type=int, default=5)
    ap.add_argument("--out")
    a = ap.parse_args()
    impls = load_impls(ROOT / "conformance" / "runner" / "implementations.json")
    names = a.impl or sorted(impls)
    if any(n not in impls for n in names):
        print(f"known implementations: {sorted(impls)}", file=sys.stderr)
        return 2
    data, distinct = workload(a.suite, a.cases)
    small = workload(a.suite, a.cases // 5)[0]
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    report = {"run_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"), "commit": commit,
              "machine": machine(), "suite": a.suite, "cases": a.cases, "distinct_cases": distinct,
              "repeats": a.repeats, "results": []}
    first, code = None, 0
    for name in names:
        try:
            row, statuses = measure(name, impls[name], data, small, a.cases, a.repeats)
        except (RuntimeError, OSError, ValueError) as e:
            print(e, file=sys.stderr)
            code = 1
            continue
        first = first or statuses
        if statuses != first:
            print(f"{name}: statuses differ from {names[0]}", file=sys.stderr)
            code = 1
        report["results"].append(row)
        print(f"{name:<8} {row['cases_per_second_median']:>9} cases/s   batch {row['batch_seconds_median']:.3f}s   "
              f"marginal {row['marginal_cases_per_second']} cases/s   start-up {row['startup_seconds_median']:.3f}s")
    if a.out:
        Path(a.out).write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    return code


if __name__ == "__main__":
    sys.exit(main())
