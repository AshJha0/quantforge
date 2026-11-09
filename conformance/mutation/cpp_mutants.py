#!/usr/bin/env python3
"""Small source-level mutation run for C++. Standard library only.

It swaps one operator at a time in a private copy of cpp26/, rebuilds, and runs the golden cases.
A mutant the golden cases do not notice is a survivor. The working tree is never changed.

Usage: cpp_mutants.py --file cpp26/src/core/daycount.cpp [--max N] [--seed N] [--suite GLOB] [--compiler g++] [--unit]

With --unit a mutant the golden cases miss is also run against the unit tests (quantforge_core_tests),
and counts as killed if they fail; the summary then splits kills into golden and unit.
Exit status: 0 the run finished, whatever survived; 2 the unmutated build failed.
"""
import argparse
import json
import random
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SWAPS = [(r" \+ ", " - "), (r" - ", " + "), (r" \* ", " / "), (r" / ", " * "), (r" < ", " <= "),
         (r" <= ", " < "), (r" > ", " >= "), (r" >= ", " > "), (r" == ", " != "), (r" != ", " == "),
         (r" && ", " || "), (r" \|\| ", " && ")]


def sites(text):
    found = []
    for at, line in enumerate(text.splitlines(keepends=True)):
        if line.lstrip().startswith(("//", "#", "*")):
            continue
        for pattern, new in SWAPS:
            for m in re.finditer(pattern, line):
                found.append((at, m.start(), m.end(), new))
    return found


def apply(text, site):
    lines = text.splitlines(keepends=True)
    at, a, b, new = site
    lines[at] = lines[at][:a] + new + lines[at][b:]
    return "".join(lines), lines[at].strip()


TIMED_OUT = []


def quiet(cmd, timeout=None):
    try:
        return subprocess.run(cmd, capture_output=True, timeout=timeout).returncode
    except subprocess.TimeoutExpired:
        TIMED_OUT.append(cmd)
        return 124  # a mutant that hangs is caught (counted in timed_out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True)
    ap.add_argument("--max", type=int, default=20)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--suite", default="*")
    ap.add_argument("--compiler", default="g++")
    ap.add_argument("--out", help="write the counts and survivors to this JSON file")
    ap.add_argument("--unit", action="store_true", help="also run the unit tests on golden survivors")
    a = ap.parse_args()
    killed, unit_killed, no_build, survived = 0, 0, 0, []
    with tempfile.TemporaryDirectory(prefix="qf-mutants-") as tmp:
        work = Path(tmp)
        shutil.copytree(ROOT / "cpp26", work / "cpp26", ignore=shutil.ignore_patterns("build*"))
        shutil.copytree(ROOT / "specifications", work / "specifications")
        build = work / "cpp26" / "build"
        conf = ["cmake", "-S", str(work / "cpp26"), "-B", str(build), "-G", "Ninja", f"-DBUILD_TESTING={'ON' if a.unit else 'OFF'}",
                f"-DCMAKE_CXX_COMPILER={a.compiler}"]
        make = ["cmake", "--build", str(build), "--parallel"]
        config = work / "impl.json"
        config.write_text(json.dumps({"cpp": {"command": [str(build / "quantforge")]}}), encoding="utf-8")
        check = [sys.executable, str(ROOT / "conformance" / "runner" / "runner.py"), "--impl", "cpp",
                 "--config", str(config), "--suite", a.suite, "--report", str(work / "report")]
        unit = [str(build / "quantforge_core_tests")]
        if quiet(conf) or quiet(make) or quiet(check) or (a.unit and quiet(unit)):
            print("the unmutated build does not pass", file=sys.stderr)
            return 2
        target = work / a.file
        original = target.read_text(encoding="utf-8")
        chosen = sites(original)
        random.Random(a.seed).shuffle(chosen)
        for site in chosen[:a.max]:
            mutated, shown = apply(original, site)
            target.write_text(mutated, encoding="utf-8")
            if quiet(make):
                no_build += 1
            elif quiet(check):
                killed += 1
            elif a.unit and quiet(unit, timeout=900):
                unit_killed += 1
            else:
                survived.append(f"{a.file}:{site[0] + 1}: {shown}")
    killed_total = killed + unit_killed
    print(f"mutants {min(len(chosen), a.max)} of {len(chosen)} sites: killed {killed_total} (golden {killed}, unit {unit_killed}), "
          f"did not build {no_build}, survived {len(survived)}, timed out {len(TIMED_OUT)}")
    for row in survived:
        print("SURVIVED", row)
    if a.out:
        Path(a.out).write_text(json.dumps({"summary": {"impl": "cpp", "target": a.file, "suite": a.suite, "seed": a.seed,
                                                       "sites": len(chosen), "killed": killed_total, "golden_killed": killed,
                                                       "unit_killed": unit_killed, "unit": a.unit, "no_build": no_build, "timed_out": len(TIMED_OUT),
                                                       "survived": len(survived)}, "survivors": survived}, indent=1) + "\n",
                               encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
