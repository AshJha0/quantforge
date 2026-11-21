#!/usr/bin/env python3
"""Lists the golden suites whose cases call a function of one Python module. Standard library only.

Plain idea: a Python mutant can only change the answer of a golden case that runs the mutated function, so the
golden run of a module's mutants needs only the suites that call that module. This script finds them.

Each golden file runs in its own process (as the runner does: one batch process per file), through the Python CLI's
`run_case`, with `sys.monitoring` PY_START events set on every code object of the module (nested ones included).
A suite is listed when any of its cases starts one of them. Module-level code is not mutated by mutmut, so it is not
traced. Prints one JSON line per suite, then a summary with the comma-separated `python_suite` value.

    cd python && uv run python ../conformance/mutation/trace_suites.py quantforge_core.daycount [--workers 4]

Used for stages.json `python_suite` of daycount (2026-11-21); roots, compounding and interp were traced the same
way in H-0 (python-h0-2026-11-18.md). Needs Python 3.12 or later (sys.monitoring).
"""
import argparse
import importlib
import json
import subprocess
import sys
import time
import types
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def code_objects(co):
    yield co
    for k in co.co_consts:
        if isinstance(k, types.CodeType):
            yield from code_objects(k)


def trace_one(module, path):
    mod = importlib.import_module(module)
    from quantforge_core.cli.main import run_case

    targets = {}
    for obj in vars(mod).values():
        f = getattr(obj, "__wrapped__", obj)
        if isinstance(f, types.FunctionType) and f.__module__ == mod.__name__:
            for co in code_objects(f.__code__):
                targets[co] = co.co_qualname
    called = set()
    mon = sys.monitoring
    mon.use_tool_id(mon.PROFILER_ID, "trace_suites")

    def on_start(code, offset):
        called.add(targets.get(code, code.co_qualname))
        return mon.DISABLE

    mon.register_callback(mon.PROFILER_ID, mon.events.PY_START, on_start)
    for co in targets:
        mon.set_local_events(mon.PROFILER_ID, co, mon.events.PY_START)
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    start = time.monotonic()
    for c in doc["cases"]:
        run_case(json.dumps({"schema_version": "1.0", "case_id": c["case_id"], "operation": c["operation"],
                             "inputs": c["inputs"]}))
    return {"stem": Path(path).stem, "cases": len(doc["cases"]), "seconds": round(time.monotonic() - start, 2),
            "called": sorted(called), "functions": sorted(set(targets.values()))}


def golden_files(golden):
    out = []
    for f in sorted(Path(golden).rglob("*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if isinstance(d, dict) and "cases" in d:
            out.append(f)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("module")
    ap.add_argument("--golden", default=str(ROOT / "datasets" / "golden"))
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--one", help=argparse.SUPPRESS)  # internal: trace one file in this process
    a = ap.parse_args(argv)
    if a.one:
        print(json.dumps(trace_one(a.module, a.one)))
        return 0

    def run(f):
        p = subprocess.run([sys.executable, __file__, a.module, "--one", str(f)], capture_output=True, text=True,
                           check=False)
        if p.returncode:
            raise SystemExit(f"{f}: exit {p.returncode}\n{p.stderr[-2000:]}")
        return json.loads(p.stdout.strip().splitlines()[-1])

    with ThreadPoolExecutor(a.workers) as ex:
        rows = list(ex.map(run, golden_files(a.golden)))
    for r in rows:
        print(json.dumps(r))
    callers = sorted(r["stem"] for r in rows if r["called"])
    stems = [r["stem"] for r in rows]
    functions = set(rows[0]["functions"]) if rows else set()
    covered = set().union(*(set(r["called"]) for r in rows))
    print(json.dumps({"suites": len(rows), "calling_suites": len(callers), "duplicate_stems": len(stems) - len(set(stems)),
                      "traced_seconds_all": round(sum(r["seconds"] for r in rows)),
                      "traced_seconds_callers": round(sum(r["seconds"] for r in rows if r["called"])),
                      "functions_never_called": sorted(functions - covered), "python_suite": ",".join(callers)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
