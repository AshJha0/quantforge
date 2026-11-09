#!/usr/bin/env python3
"""Runs the README quick-start command and checks it still prints what the README shows (plan 13.1 E8).

  python tools/check_quickstart.py [--readme README.md]

The block sits between <!-- quickstart:begin --> and <!-- quickstart:end -->: a bash block with one command, then a
json block with the expected lines. Each result line must match on case_id, status, outputs (exactly) and the error
code. Diagnostics and error messages are not part of the CLI contract and may differ, so they are not compared.
Exit 0 on a match, 1 otherwise.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def extract(text):
    m = re.search(r"<!-- quickstart:begin -->(.*?)<!-- quickstart:end -->", text, re.S)
    if not m:
        raise ValueError("README has no quickstart block")
    blocks = re.findall(r"```(\w+)\n(.*?)```", m.group(1), re.S)
    cmd = [b for lang, b in blocks if lang == "bash"]
    out = [b for lang, b in blocks if lang == "json"]
    if len(cmd) != 1 or len(out) != 1:
        raise ValueError("the quickstart block needs exactly one bash block and one json block")
    return cmd[0].strip(), [json.loads(x) for x in out[0].splitlines() if x.strip()]


def contract(r):
    return {"case_id": r.get("case_id"), "status": r.get("status"), "outputs": r.get("outputs"),
            "error": (r.get("error") or {}).get("code")}


def compare(expected, actual_text):
    actual = [json.loads(x) for x in actual_text.splitlines() if x.strip()]
    problems = []
    if len(actual) != len(expected):
        problems.append(f"expected {len(expected)} lines, got {len(actual)}")
    for i, (e, a) in enumerate(zip(expected, actual), 1):
        if contract(e) != contract(a):
            problems.append(f"line {i}: README {contract(e)} but the command printed {contract(a)}")
    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--readme", default=str(ROOT / "README.md"))
    a = ap.parse_args()
    cmd, expected = extract(Path(a.readme).read_text(encoding="utf-8"))
    p = subprocess.run(cmd, shell=True, cwd=ROOT, capture_output=True, text=True)
    if p.returncode != 0:
        print(f"quick start exited {p.returncode}:\n{p.stderr}", file=sys.stderr)
        return 1
    problems = compare(expected, p.stdout)
    for x in problems:
        print(x, file=sys.stderr)
    print(f"quick start: {len(expected)} lines, {'OK' if not problems else 'MISMATCH'}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
