#!/usr/bin/env python3
"""Runs the COOKBOOK recipes that carry expectations and checks their output, so a recipe cannot go stale.

  python tools/check_cookbook.py [--file COOKBOOK.md] [--only SUBSTRING] [--list]

A bash block preceded by the marker <!-- cookbook:run --> is run through bash from the repository root. The
HTML comment that follows it,

  <!-- cookbook:expect
  "rrao":10000.0
  "case_id":"sec","status":"ok"
  -->

lists one literal string per line; every one must occur in the block's standard output. The strings are short
pieces of the JSON a build prints (or of a tool's printed line), so the check is exact about the numbers it names
and ignores everything else. A run block without an expect comment, or an expect comment without a run block, is
an error, so a marker cannot be forgotten half way.

Two shims are put in front of each block. `python` means this interpreter, as in tools/check_tutorial.py. And a
`uv run ... quantforge ...` line runs `python -m quantforge_core.cli.main ...` instead of the `quantforge`
launcher: the same entry point (python/quantforge_core/cli/main.py), and the launcher is blocked by Windows Smart
App Control on some machines. Recipes without markers are not run; this tool does not judge them.

Exit 0 when every marked recipe matches, 1 otherwise. Standard library only. Not wired into a workflow.
"""
import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = re.compile(r"<!-- cookbook:run -->\s*```bash\n(.*?)```", re.S)
EXPECT = re.compile(r"<!-- cookbook:expect\n(.*?)-->", re.S)
HEADING = re.compile(r"^#{2,6} (.+)$", re.M)


def shims():
    py = Path(sys.executable).as_posix()
    return (
        f'python() {{ "{py}" "$@"; }}\n'
        'uv() {\n'
        '  local a=()\n'
        '  for x in "$@"; do\n'
        '    if [ "$x" = quantforge ]; then a+=(python -m quantforge_core.cli.main); else a+=("$x"); fi\n'
        '  done\n'
        '  command uv "${a[@]}"\n'
        '}\n'
    )


def recipes(text):
    """[(title, body, [expected strings])] in page order. Raises ValueError on an unpaired marker."""
    runs = [(m.start(), m.end(), m.group(1)) for m in RUN.finditer(text)]
    expects = [(m.start(), m.group(1)) for m in EXPECT.finditer(text)]
    if len(runs) != len(expects):
        raise ValueError(f"{len(runs)} cookbook:run blocks but {len(expects)} cookbook:expect comments")
    out = []
    for (start, end, body), (estart, ebody) in zip(runs, expects):
        nxt = text.find("<!-- cookbook:run -->", end)
        if estart < end or (nxt != -1 and estart > nxt):
            raise ValueError(f"the cookbook:run block at offset {start} has no cookbook:expect comment after it")
        heads = [h.group(1) for h in HEADING.finditer(text, 0, start)]
        want = [line for line in ebody.splitlines() if line.strip()]
        if not want:
            raise ValueError(f"the cookbook:expect comment after offset {start} is empty")
        out.append((heads[-1] if heads else "(no heading)", body, want))
    return out


def check(title, body, want, run=subprocess.run):
    t0 = time.monotonic()
    p = run(["bash", "-e"], input=shims() + body, capture_output=True, text=True, cwd=ROOT, encoding="utf-8")
    missing = [w for w in want if w not in p.stdout]
    seconds = time.monotonic() - t0
    if p.returncode != 0 or missing:
        print(f"FAIL {title}: exit {p.returncode}; missing {missing}\n--- stderr ---\n{p.stderr[-2000:]}"
              f"\n--- stdout (last 2000 chars) ---\n{p.stdout[-2000:]}", file=sys.stderr)
        return False
    print(f"ok   {title}: {len(want)} strings found ({seconds:.0f} s)")
    return True


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--file", default=str(ROOT / "COOKBOOK.md"))
    ap.add_argument("--only", help="run only recipes whose heading contains this text")
    ap.add_argument("--list", action="store_true", help="list the marked recipes and exit")
    a = ap.parse_args(argv)
    items = recipes(Path(a.file).read_text(encoding="utf-8"))
    if a.only:
        items = [r for r in items if a.only in r[0]]
    if a.list:
        for title, _, want in items:
            print(f"{title} ({len(want)} strings)")
        return 0
    failed = [title for title, body, want in items if not check(title, body, want)]
    print(f"cookbook: {len(items) - len(failed)} of {len(items)} marked recipes match")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
