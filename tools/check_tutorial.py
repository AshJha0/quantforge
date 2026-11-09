#!/usr/bin/env python3
"""Runs the code blocks of a tutorial and checks they print what the page shows (plan 13.2 E2).

  python tools/check_tutorial.py --lang python [--page docs/getting-started/tutorial-1-swap.md]

A block marked <!-- tutorial:run LANG --> is run: a python block through `uv run --project python python -`,
a bash block through bash, both from the repository root. Its stdout must equal, line for line, the text
block marked <!-- tutorial:expect -->. Every language prints the same lines, so one expected block serves
all four. Exit 0 on a match, 1 otherwise. Standard library only.
"""
import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "docs" / "getting-started" / "tutorial-1-swap.md"
FENCE = r"\s*```(\w+)\n(.*?)```"


def blocks(text):
    runs = {lang: (kind, body) for lang, kind, body in
            re.findall(r"<!-- tutorial:run (\w+) -->" + FENCE, text, re.S)}
    expect = re.findall(r"<!-- tutorial:expect -->" + FENCE, text, re.S)
    if len(expect) != 1 or expect[0][0] != "text":
        raise ValueError("the page needs exactly one text block marked tutorial:expect")
    return runs, expect[0][1].splitlines()


def command(kind, body):
    if kind == "python":
        return ["uv", "run", "--locked", "--project", "python", "python", "-"], body
    if kind == "bash":
        # The page says `python`; some runners only have python3, so it means this interpreter.
        shim = f'python() {{ "{Path(sys.executable).as_posix()}" "$@"; }}\n'
        return ["bash", "-e"], shim + body
    raise ValueError(f"cannot run a {kind} block")


def check(lang, page):
    runs, expected = blocks(page.read_text(encoding="utf-8"))
    if lang not in runs:
        print(f"no block marked tutorial:run {lang}", file=sys.stderr)
        return 1
    argv, stdin = command(*runs[lang])
    start = time.monotonic()
    p = subprocess.run(argv, input=stdin, cwd=ROOT, capture_output=True, text=True)
    seconds = time.monotonic() - start
    if p.returncode != 0:
        print(f"{lang} block exited {p.returncode}:\n{p.stderr}", file=sys.stderr)
        return 1
    actual = [x for x in p.stdout.splitlines() if x.strip()]
    if actual != expected:
        print(f"{lang} printed\n" + "\n".join(actual) + "\nbut the page shows\n" + "\n".join(expected),
              file=sys.stderr)
        return 1
    print(f"{lang}: {len(expected)} lines match ({seconds:.0f} s)")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", required=True, choices=("python", "rust", "java", "cpp"))
    ap.add_argument("--page", default=str(PAGE))
    a = ap.parse_args()
    return check(a.lang, Path(a.page))


if __name__ == "__main__":
    sys.exit(main())
