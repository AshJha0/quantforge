#!/usr/bin/env python3
"""Scores Rust and Python mutants against the golden cases as well as the unit tests.

The mutants come from the same tools as before: cargo-mutants and mutmut. Those tools run the unit
tests first, which gives the unit verdict. This script then runs a sample of the same mutants
through the neutral runner, so each mutant has two verdicts and the two scores are comparable.
Everything happens in a private copy; the working tree is never changed.

Usage: golden_mutants.py --impl rust --target '**/compounding.rs' [--suite GLOB] [--max N] [--seed N]
       golden_mutants.py --impl python --target 'quantforge_core.compounding*' [...]
Python needs Linux or WSL, because mutmut forks. It needs uv; Rust needs cargo-mutants 27.1.0.
Exit status: 0 the run finished, whatever survived; 2 the unmutated build failed or a tool failed.
"""
import argparse
import fnmatch
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "conformance" / "runner" / "runner.py"
MUTMUT = "mutmut==3.8.1"
SKIP = shutil.ignore_patterns(".git", "target", "build", "build-*", ".venv", "mutants", "mutants.out*",
                              "__pycache__", "reports", "java25", "cpp26")
# mutmut exit codes: 0 survived, 1 and 3 killed. Anything else (no tests, timeout) is kept by number.
MUTMUT_VERDICT = {0: "survived", 1: "killed", 3: "killed"}
RUST_VERDICT = {"CaughtMutant": "killed", "MissedMutant": "survived", "Unviable": "unviable", "Timeout": "timeout"}


# QF_MUTANT_AS (bytes) caps the address space of the golden run and the CLI it starts. A mutant that
# turns a loop into `loop { v.push(..) }` then aborts on a failed allocation (counted as killed)
# instead of exhausting the CI runner's memory, which kills the runner agent (exit 143).
MEMCAP = (["prlimit", f"--as={os.environ['QF_MUTANT_AS']}", "--"]
          if os.environ.get("QF_MUTANT_AS") and shutil.which("prlimit") else [])


def run(cmd, cwd=None, env=None, timeout=None):
    """Returns the exit code, with None for a timeout. Output is kept out of the way."""
    try:
        return subprocess.run(cmd, cwd=cwd, env=env, timeout=timeout, capture_output=True).returncode
    except subprocess.TimeoutExpired:
        return None


class Golden:
    """Runs the neutral runner against one command, and says whether the cases noticed."""

    def __init__(self, impl, command, cwd, work, suite):
        self.config = work / "impl.json"
        self.config.write_text(json.dumps({impl: {"command": command, "cwd": str(cwd)}}), encoding="utf-8")
        self.impl, self.work, self.suite, self.limit = impl, work, suite, 900.0

    def baseline(self, env=None):
        start = time.monotonic()
        code = self.check(env)
        took = time.monotonic() - start
        self.limit = max(30.0, 5 * took)
        return code, took

    def check(self, env=None):
        return run(MEMCAP + [sys.executable, str(RUNNER), "--impl", self.impl, "--config", str(self.config),
                             "--suite", self.suite, "--report", str(self.work / "report"), "--timeout", str(self.limit)],
                   env=env, timeout=4 * self.limit)


def copy_tree(work):
    shutil.copytree(ROOT, work / "repo", ignore=SKIP)
    return work / "repo"


def rust_mutants(repo, target):
    out = repo / "rust" / "cm"
    code = run(["cargo", "mutants", "--in-place", "-p", "quantforge-core", "-f", target, "-o", str(out)], cwd=repo / "rust")
    if code not in (0, 2, 3):  # 2 means some were missed, 3 some timed out
        raise SystemExit(f"cargo mutants failed with exit code {code}")
    rows = []
    for o in json.loads((out / "mutants.out" / "outcomes.json").read_text(encoding="utf-8"))["outcomes"]:
        scenario = o["scenario"]
        if isinstance(scenario, dict) and "Mutant" in scenario:
            m = scenario["Mutant"]
            rows.append({"id": m["name"], "mutant": m, "unit": RUST_VERDICT.get(o["summary"], o["summary"])})
    return rows


def splice(text, span, replacement):
    lines = text.splitlines(keepends=True)

    def offset(at):
        return sum(len(x) for x in lines[:at["line"] - 1]) + at["column"] - 1

    return text[:offset(span["start"])] + replacement + text[offset(span["end"]):]


def score_rust(a, work):
    repo = copy_tree(work)
    rows = rust_mutants(repo, a.target)
    build = ["cargo", "build", "--release", "-p", "quantforge-cli"]
    golden = Golden("rust", [str(repo / "rust" / "target" / "release" / "quantforge")], repo, work, a.suite)
    if run(build, cwd=repo / "rust") or golden.baseline()[0]:
        raise SystemExit("the unmutated build does not pass")
    for row in sample(rows, a):
        path = repo / "rust" / row["mutant"]["file"]
        original = path.read_bytes().decode("utf-8")
        path.write_bytes(splice(original, row["mutant"]["span"], row["mutant"]["replacement"]).encode("utf-8"))
        row["golden"] = "unviable" if run(build, cwd=repo / "rust") else verdict(golden.check())
        path.write_bytes(original.encode("utf-8"))
    return rows


def python_mutants(project, target):
    uv = ["uv", "run", "--with", MUTMUT]
    run(uv + ["mutmut", "run", target], cwd=project)
    rows = []
    for meta in sorted((project / "mutants").rglob("*.meta")):
        for name, code in json.loads(meta.read_text(encoding="utf-8"))["exit_code_by_key"].items():
            if fnmatch.fnmatchcase(name, target):
                rows.append({"id": name, "unit": MUTMUT_VERDICT.get(code, f"mutmut code {code}")})
    if not rows:
        raise SystemExit("mutmut produced no mutants for that target")
    return rows


def score_python(a, work):
    repo = copy_tree(work)
    project = repo / "python"
    rows = python_mutants(project, a.target)
    # The mutated copy has every mutant compiled in. MUTANT_UNDER_TEST picks one in the CLI process too.
    command = ["uv", "run", "--project", str(project), "--with", MUTMUT, "python", "-c", "import sys; from quantforge_core.cli.main import main; sys.exit(main())"]
    golden = Golden("python", command, project / "mutants", work, a.suite)
    env = dict(os.environ, PYTHONPATH=str(project / "mutants"), MUTANT_UNDER_TEST="")
    if golden.baseline(env)[0]:
        raise SystemExit("the unmutated build does not pass")
    for row in sample(rows, a):
        row["golden"] = verdict(golden.check(dict(env, MUTANT_UNDER_TEST=row["id"])))
    return rows


def verdict(code):
    return "timeout" if code is None else "survived" if code == 0 else "killed"


def sample(rows, a):
    """Unviable mutants never reach a test, so they are not worth a slot in the sample."""
    live = [r for r in rows if r["unit"] != "unviable"]
    random.Random(a.seed).shuffle(live)
    return live[:a.max]


def summarise(a, rows):
    done = [r for r in rows if "golden" in r and r["golden"] != "unviable"]

    def caught(r, key):
        return r[key] in ("killed", "timeout")

    unit_all = [r for r in rows if r["unit"] != "unviable"]
    both = {"mutants": len(rows), "unviable": len(rows) - len(unit_all),
            "unit_killed_all": sum(caught(r, "unit") for r in unit_all), "sampled": len(done),
            "sample_unit_killed": sum(caught(r, "unit") for r in done),
            "sample_golden_killed": sum(caught(r, "golden") for r in done),
            "sample_either_killed": sum(caught(r, "unit") or caught(r, "golden") for r in done),
            "sample_golden_timeouts": sum(r["golden"] == "timeout" for r in done),
            "unit_verdicts": dict(Counter(r["unit"] for r in rows))}
    print(json.dumps({"impl": a.impl, "target": a.target, "suite": a.suite, "seed": a.seed, **both}))
    for r in done:
        if not caught(r, "unit") and not caught(r, "golden"):
            print("SURVIVED", r["id"])
    return both


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--impl", required=True, choices=["rust", "python"])
    ap.add_argument("--target", required=True, help="rust: file glob. python: mutant name glob")
    ap.add_argument("--suite", default="*")
    ap.add_argument("--max", type=int, default=20)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", help="write every mutant and both verdicts to this JSON file")
    a = ap.parse_args()
    with tempfile.TemporaryDirectory(prefix="qf-golden-mutants-") as tmp:
        try:
            rows = (score_rust if a.impl == "rust" else score_python)(a, Path(tmp))
        except SystemExit as e:
            print(e, file=sys.stderr)
            return 2
    summary = summarise(a, rows)
    if a.out:
        for r in rows:
            r.pop("mutant", None)
        Path(a.out).write_text(json.dumps({"summary": summary, "rows": rows}, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
