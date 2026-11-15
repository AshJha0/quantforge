#!/usr/bin/env python3
"""Checks that mutmut can mutate every module of a package into valid Python.

mutmut 3.8.1 writes all mutants of a file into one trampolined module. If a single mutant is not
valid syntax (it dropped the outer parentheses of a wrapped `if (not ...)` when it removed the
`not`, see shortrate.py), mutmut aborts the whole run and the CI job reports no mutants. This
script runs mutmut's own generator on each file and compiles the result, so such a construct is
found before a mutation job is spent on it.

It takes about six minutes for quantforge_core on a laptop, too slow for the unit tests, so it is
a manual check: run it after reformatting or adding long boolean guards. Needs Linux or WSL and
mutmut 3.8.1 (the version mutation.yml pins).

    cd python && uv run --with mutmut==3.8.1 python ../conformance/mutation/mutmut_syntax_check.py
Exit status: 0 every file mutates to valid syntax, 1 at least one does not.
"""
import sys
import time
import warnings
from pathlib import Path

from mutmut.mutation.file_mutation import mutate_file_contents


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("quantforge_core")
    warnings.simplefilter("ignore")
    start, ok, bad = time.time(), 0, 0
    for path in sorted(root.rglob("*.py")):
        try:
            compile(mutate_file_contents(str(path), path.read_text(encoding="utf-8")).code, str(path), "exec")
            ok += 1
        except SyntaxError as exc:
            bad += 1
            print(f"invalid mutant syntax: {path}: {exc}")
    print(f"{ok} files ok, {bad} with invalid mutants, {time.time() - start:.0f}s")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
