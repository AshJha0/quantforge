#!/usr/bin/env python3
"""Runs the code blocks of the tutorials and checks they print what each page shows (plan 13.2 E2).

  python tools/check_tutorial.py --lang python [--page docs/getting-started/tutorial-1-swap.md]

With no --page it checks every docs/getting-started/tutorial-*.md in turn.

A block marked <!-- tutorial:run LANG --> is run: a python block through `uv run --project python python -`,
a bash block through bash, both from the repository root. The last lines of its stdout must equal, line for line, the text
block marked <!-- tutorial:expect -->. Every language prints the same lines, so one expected block serves
all four. A python block marked <!-- tutorial:source PATH --> is not run: it must equal the file at PATH
(relative to the repository root), so a page that shows a script cannot drift from the script it runs.
Exit 0 when every page matches, 1 otherwise. Standard library only.
"""
import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGES = sorted((ROOT / "docs" / "getting-started").glob("tutorial-*.md"),
               key=lambda p: int(re.match(r"tutorial-(\d+)", p.name)[1]))  # 2 before 10
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


def sources(text):
    """The blocks marked tutorial:source whose text differs from the file they name."""
    bad = []
    for path, _kind, body in re.findall(r"<!-- tutorial:source (\S+) -->" + FENCE, text, re.S):
        if (ROOT / path).read_text(encoding="utf-8") != body:
            bad.append(path)
    return bad


def check(lang, page):
    text = page.read_text(encoding="utf-8")
    runs, expected = blocks(text)
    stale = sources(text)
    if stale:
        print(f"{page.name}: the listing of {', '.join(stale)} differs from the file", file=sys.stderr)
        return 1
    if lang not in runs:
        print(f"{page.name}: no block marked tutorial:run {lang}", file=sys.stderr)
        return 1
    argv, stdin = command(*runs[lang])
    start = time.monotonic()
    p = subprocess.run(argv, input=stdin, cwd=ROOT, capture_output=True, text=True)
    seconds = time.monotonic() - start
    if p.returncode != 0:
        print(f"{page.name}: {lang} block exited {p.returncode}:\n{p.stderr}", file=sys.stderr)
        return 1
    # Build tools (Ninja) may log to stdout first; the tutorial's own output is the last lines.
    actual = [x for x in p.stdout.splitlines() if x.strip()][-len(expected):]
    if actual != expected:
        print(f"{lang} printed\n" + "\n".join(actual) + "\nbut the page shows\n" + "\n".join(expected),
              file=sys.stderr)
        return 1
    print(f"{page.name}: {lang}: {len(expected)} lines match ({seconds:.0f} s)")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", required=True, choices=("python", "rust", "java", "cpp"))
    ap.add_argument("--page", help="one page; default every tutorial-*.md")
    a = ap.parse_args()
    pages = [Path(a.page)] if a.page else PAGES
    failed = [p.name for p in pages if check(a.lang, p) != 0]
    if failed:
        print(f"{a.lang}: {len(failed)} of {len(pages)} pages failed: {', '.join(failed)}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
