#!/usr/bin/env python3
"""Small source-level mutation run for C++. Standard library only.

It swaps one operator at a time in a private copy of cpp26/, rebuilds, and runs the golden cases.
A mutant the golden cases do not notice is a survivor. The working tree is never changed.

Usage: cpp_mutants.py --file cpp26/src/core/daycount.cpp [--max N] [--seed N] [--suite GLOB] [--compiler g++]
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


def quiet(cmd):
    return subprocess.run(cmd, capture_output=True).returncode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True)
    ap.add_argument("--max", type=int, default=20)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--suite", default="*")
    ap.add_argument("--compiler", default="g++")
    ap.add_argument("--out", help="write the counts and survivors to this JSON file")
    a = ap.parse_args()
    killed, no_build, survived = 0, 0, []
    with tempfile.TemporaryDirectory(prefix="qf-mutants-") as tmp:
        work = Path(tmp)
        shutil.copytree(ROOT / "cpp26", work / "cpp26", ignore=shutil.ignore_patterns("build*"))
        shutil.copytree(ROOT / "specifications", work / "specifications")
        build = work / "cpp26" / "build"
        conf = ["cmake", "-S", str(work / "cpp26"), "-B", str(build), "-G", "Ninja", "-DBUILD_TESTING=OFF",
                f"-DCMAKE_CXX_COMPILER={a.compiler}"]
        make = ["cmake", "--build", str(build), "--parallel"]
        config = work / "impl.json"
        config.write_text(json.dumps({"cpp": {"command": [str(build / "quantforge")]}}), encoding="utf-8")
        check = [sys.executable, str(ROOT / "conformance" / "runner" / "runner.py"), "--impl", "cpp",
                 "--config", str(config), "--suite", a.suite, "--report", str(work / "report")]
        if quiet(conf) or quiet(make) or quiet(check):
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
            else:
                survived.append(f"{a.file}:{site[0] + 1}: {shown}")
    print(f"mutants {min(len(chosen), a.max)} of {len(chosen)} sites: killed {killed}, "
          f"did not build {no_build}, survived {len(survived)}")
    for row in survived:
        print("SURVIVED", row)
    if a.out:
        Path(a.out).write_text(json.dumps({"summary": {"impl": "cpp", "target": a.file, "suite": a.suite, "seed": a.seed,
                                                       "sites": len(chosen), "killed": killed, "no_build": no_build,
                                                       "survived": len(survived)}, "survivors": survived}, indent=1) + "\n",
                               encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
