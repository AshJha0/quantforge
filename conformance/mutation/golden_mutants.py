#!/usr/bin/env python3
"""Scores Rust and Python mutants against the golden cases as well as the unit tests.

The mutants come from the same tools as before: cargo-mutants and mutmut. For Python, mutmut runs the
unit tests on every mutant first, which gives the unit verdict. For Rust, cargo-mutants only lists the
mutants and this script runs `cargo test -p quantforge-core` on the sampled ones (testing all of them
took over three hours per module in CI). A sample of the mutants then also goes through the neutral
runner, so each sampled mutant has two verdicts and the two scores are comparable.
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
import signal
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
    """Returns the exit code, with None for a timeout. Output is kept out of the way.

    The command runs in its own process group so a timeout also kills what it started (a hung test
    binary under cargo), not just the direct child."""
    posix = os.name == "posix"
    p = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=posix)
    try:
        return p.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        if posix:
            os.killpg(p.pid, signal.SIGKILL)
        else:
            p.kill()
        p.wait()
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
    """Every mutant cargo-mutants would make in the target file, listed but not run.

    Running cargo-mutants itself tests every mutant (1258 in exotics.rs), which took more than 180
    minutes per module on a CI runner, while the report scores only the sample. So the unit verdict
    is taken for the sampled mutants alone, in score_rust."""
    out = run_capture(["cargo", "mutants", "--list", "--json", "-p", "quantforge-core", "-f", target], cwd=repo / "rust")
    if out is None:
        raise SystemExit("cargo mutants --list failed")
    return [{"id": m["name"], "mutant": m} for m in json.loads(out)]


def run_capture(cmd, cwd=None):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


def splice(text, span, replacement):
    lines = text.splitlines(keepends=True)

    def offset(at):
        return sum(len(x) for x in lines[:at["line"] - 1]) + at["column"] - 1

    return text[:offset(span["start"])] + replacement + text[offset(span["end"]):]


def score_rust(a, work):
    """Unit verdict (cargo test -p quantforge-core, as cargo-mutants runs it) and golden verdict for a
    seeded sample of live mutants. A mutant whose tests do not build is unviable and the next one in
    the shuffled order takes its slot, so the sample matches sample() on a full cargo-mutants run."""
    repo = copy_tree(work)
    rust = repo / "rust"
    rows = rust_mutants(repo, a.target)
    build = ["cargo", "build", "--release", "-p", "quantforge-cli"]
    tests = ["cargo", "test", "-p", "quantforge-core"]
    golden = Golden("rust", [str(rust / "target" / "release" / "quantforge")], repo, work, a.suite)
    if run(build, cwd=rust) or golden.baseline()[0] or run(tests + ["--no-run"], cwd=rust):
        raise SystemExit("the unmutated build does not pass")
    start = time.monotonic()
    if run(tests, cwd=rust):
        raise SystemExit("the unmutated unit tests do not pass")
    unit_limit = max(60.0, 5 * (time.monotonic() - start))
    order = list(rows)
    random.Random(a.seed).shuffle(order)
    k, n = a.shard
    order = order[k::n]  # shard k of n takes every n-th mutant of the shuffled order, and its share of MAX
    quota = a.max // n + (k < a.max % n)
    live = 0
    for row in order:
        if live >= quota:
            break
        path = rust / row["mutant"]["file"]
        original = path.read_bytes().decode("utf-8")
        path.write_bytes(splice(original, row["mutant"]["span"], row["mutant"]["replacement"]).encode("utf-8"))
        try:
            if run(tests + ["--no-run"], cwd=rust):
                row["unit"] = "unviable"
                continue
            code = run(tests, cwd=rust, timeout=unit_limit)
            row["unit"] = "timeout" if code is None else "survived" if code == 0 else "killed"
            row["golden"] = "unviable" if run(build, cwd=rust) else verdict(golden.check())
            live += 1
        finally:
            path.write_bytes(original.encode("utf-8"))
    for row in rows:
        row.setdefault("unit", "not run")
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

    unit_all = [r for r in rows if r["unit"] not in ("unviable", "not run")]
    both = {"mutants": len(rows), "unviable": sum(r["unit"] == "unviable" for r in rows),
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


def shard(text):
    k, n = (int(x) for x in text.split("/"))
    if not 0 <= k < n:
        raise argparse.ArgumentTypeError("shard is K/N with 0 <= K < N")
    return k, n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--impl", required=True, choices=["rust", "python"])
    ap.add_argument("--target", required=True, help="rust: file glob. python: mutant name glob")
    ap.add_argument("--suite", default="*")
    ap.add_argument("--max", type=int, default=20)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--shard", type=shard, default=(0, 1),
                    help="rust: K/N runs only shard K (0-based) of N; stage_report.py merges the shards")
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
