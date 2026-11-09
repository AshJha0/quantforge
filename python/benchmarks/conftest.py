"""Microbenchmark harness: injected slowdown, allocation counts, and the summary JSON.

allocs_per_op is the net change in live allocation blocks (sys.getallocatedblocks) across
N untimed calls, divided by N, measured with the cyclic GC disabled. CPython has no
cheap gross-allocation counter, so this counts blocks a call leaves alive (caches, interned
objects, results kept by the caller), not every temporary it allocates and frees.
"""

import gc
import json
import os
import sys
import time
from pathlib import Path

import pytest

ALLOC_CALLS = 50
OUT = Path(__file__).resolve().parents[2] / "benchmarks" / "micro" / "out" / "python.json"
_allocs: dict[str, float] = {}


def _inject_ns() -> int:
    raw = os.environ.get("QF_BENCH_INJECT_NS", "")
    try:
        return max(int(raw), 0)
    except ValueError:
        return 0


def _allocs_per_op(fn) -> float:
    fn()  # warm caches so one-time setup is not counted
    keep = [None] * ALLOC_CALLS
    gc.collect()
    gc.disable()
    try:
        before = sys.getallocatedblocks()
        for k in range(ALLOC_CALLS):
            keep[k] = fn()
        keep = None
        after = sys.getallocatedblocks()
    finally:
        gc.enable()
    return max(after - before, 0) / ALLOC_CALLS


@pytest.fixture
def qf_bench(benchmark):
    """Returns run(bench_id, fn): counts allocations, then times fn (plus any injected spin)."""

    def run(bench_id: str, fn) -> None:
        _allocs[bench_id] = _allocs_per_op(fn)
        spin = _inject_ns()
        if spin:
            clock = time.perf_counter_ns

            def timed():
                result = fn()
                end = clock() + spin  # spin after the op, so the added cost is exactly `spin`
                while clock() < end:
                    pass
                return result
        else:
            timed = fn
        benchmark(timed)

    return run


def pytest_sessionfinish(session):
    bs = getattr(session.config, "_benchmarksession", None)
    if bs is None or not bs.benchmarks:
        return
    out = {}
    for b in bs.benchmarks:
        name = b.name.removeprefix("test_")
        if name in _allocs and b.stats is not None:
            out[name] = {"ns_per_op": b.stats.median * 1e9, "allocs_per_op": _allocs[name]}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"lang": "python", "benchmarks": out}, indent=2) + "\n")
