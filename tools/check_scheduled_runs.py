#!/usr/bin/env python3
"""A scheduled workflow whose last run on main failed must be named in the known-issues register (ruling KR-342,
PROPOSED; K-9 review finding 1).

    python tools/check_scheduled_runs.py               ask GitHub (needs gh and a token with actions: read)
    python tools/check_scheduled_runs.py --runs F.json  judge recorded results: {"fuzz.yml": "failure", ...}
    python tools/check_scheduled_runs.py --self-test   planted faults must fail

Plain idea: a weekly job that fails on main tells nobody. The fuzz workflow failed on main at every run from
2026-11-09 to 2026-11-16 while the README said fuzzing had not run since the v0.8.3 fixes, and no row of
docs/known-issues.md named it. This check makes a red scheduled run either visible in the register or a failing
check.

Formal statement. For every file in .github/workflows whose `on:` block has a `schedule:` trigger, take the
conclusion of the most recent run on branch main (any event). Exit 1 if a conclusion is failure, timed_out or
startup_failure and the "## Open" section of docs/known-issues.md does not contain the workflow's file name
(for example `fuzz.yml`). A workflow with no run on main passes. Exit 2 if gh cannot be run or answers
something unreadable: the check never passes for want of data.

What it does not show: why the run failed, or that a named row is still accurate.

Standard library only.
"""
import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RED = {"failure", "timed_out", "startup_failure"}


def scheduled(workflows: Path) -> list[str]:
    out = []
    for p in sorted(workflows.glob("*.yml")):
        if re.search(r"^\s+schedule:\s*$", p.read_text(encoding="utf-8"), re.M):
            out.append(p.name)
    return out


def open_section(register: Path) -> str:
    text = register.read_text(encoding="utf-8")
    m = re.search(r"^## Open\s*$(.*?)(?=^## )", text, re.M | re.S)
    return m.group(1) if m else ""


def last_conclusions(names: list[str], gh: str) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for name in names:
        cmd = [gh, "run", "list", "--workflow", name, "--branch", "main", "--limit", "1", "--json", "conclusion,status"]
        p = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT, check=False)
        if p.returncode != 0:
            raise RuntimeError(f"gh failed for {name}: {p.stderr.strip()[:200]}")
        rows = json.loads(p.stdout)
        out[name] = rows[0].get("conclusion") or None if rows else None
    return out


def problems(conclusions: dict[str, str | None], register_open: str) -> list[str]:
    bad = []
    for name, c in sorted(conclusions.items()):
        if c in RED and name not in register_open:
            bad.append(f"{name}: last run on main is {c} and the Open section of docs/known-issues.md does not name it")
    return bad


def self_test() -> int:
    with tempfile.TemporaryDirectory() as d:
        wf = Path(d) / "wf"
        wf.mkdir()
        (wf / "a.yml").write_text("on:\n  schedule:\n    - cron: '1 1 * * 1'\n", encoding="utf-8")
        (wf / "b.yml").write_text("on:\n  push:\n", encoding="utf-8")
        reg = Path(d) / "known.md"
        reg.write_text("# R\n\n## Open\n\n| x | `b.yml` |\n\n## Closed\n\n| y | `a.yml` closed |\n", encoding="utf-8")
        names = scheduled(wf)
        checks = [
            (names == ["a.yml"], "schedule detection"),
            (bool(problems({"a.yml": "failure"}, open_section(reg))), "red run named only under Closed must fail"),
            (not problems({"a.yml": "success"}, open_section(reg)), "green run passes"),
            (not problems({"a.yml": None}, open_section(reg)), "no run passes"),
            (bool(problems({"a.yml": "timed_out"}, "")), "timed_out counts as red"),
            (not problems({"a.yml": "failure"}, "| KV-F1 | `a.yml` failing |"), "named in Open passes"),
        ]
    failed = [why for ok, why in checks if not ok]
    for why in failed:
        print("self-test FAILED:", why)
    print("self-test", "FAILED" if failed else "passed", f"({len(checks)} checks)")
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--runs", type=Path, help="JSON object: workflow file name to last conclusion on main")
    ap.add_argument("--gh", default="gh")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)
    if a.self_test:
        return self_test()
    names = scheduled(ROOT / ".github" / "workflows")
    try:
        if a.runs:
            recorded = json.loads(a.runs.read_text(encoding="utf-8"))
            conclusions = {n: recorded.get(n) for n in names}
        else:
            conclusions = last_conclusions(names, a.gh)
    except (OSError, RuntimeError, ValueError) as e:
        print(f"cannot check: {e}")
        return 2
    bad = problems(conclusions, open_section(ROOT / "docs" / "known-issues.md"))
    for name in names:
        print(f"{name}: {conclusions.get(name)}")
    for b in bad:
        print("FAIL", b)
    print("scheduled runs:", "FAIL" if bad else "ok", f"({len(names)} scheduled workflows)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
