#!/usr/bin/env python3
"""Every scheduled workflow whose last run on main failed is named in an open known-issues row (K-9 review finding 1).

    python tools/check_scheduled_runs.py              read the runs from the GitHub API and check the register
    python tools/check_scheduled_runs.py --self-test  planted faults must fail (no network)

Plain idea: the README once said fuzzing had not run on main when four scheduled fuzz runs had run and failed. Nobody
reads the Actions tab every day, so a red scheduled job must show up where readers look: docs/known-issues.md.

Formal statement. A workflow is scheduled if its file under .github/workflows has an `on.schedule` entry. For each
one, the check reads the most recent completed run on branch main whose event is `schedule` or `workflow_dispatch`
(GitHub REST API, `GET /repos/{repo}/actions/workflows/{file}/runs`). If its conclusion is failure, timed_out or
startup_failure, the workflow is red, and the check fails unless a line in the "Open" or "Recorded misses" section
of docs/known-issues.md names the workflow file in backticks (for example `fuzz.yml`). A workflow with no completed
run is listed as "no run yet" and passes. A green workflow that still has a row passes too (the row is closed by a
person's edit that names its evidence, as for every other row). An API error fails the check: a guard that passes
when it cannot see is no guard.

Worked example: fuzz.yml's last run on main (2026-11-16, schedule) concluded failure, so the check passes only while
the register's Open table has a row that contains `fuzz.yml`.

Token: GITHUB_TOKEN or GH_TOKEN from the environment (in CI, the job's GITHUB_TOKEN with `actions: read`), else the
output of `gh auth token` if gh is installed, else unauthenticated (public repository, 60 requests an hour; the
check makes one request per scheduled workflow). Standard library only.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTER = Path("docs") / "known-issues.md"
REPO = os.environ.get("GITHUB_REPOSITORY", "AshJha0/quantforge")
RED = {"failure", "timed_out", "startup_failure"}
OPEN_SECTIONS = ("## Open", "## Recorded misses")


def scheduled_workflows(root=ROOT):
    """File names of workflows with an `on.schedule` trigger (a `schedule:` key followed by a `- cron:` line)."""
    out = []
    for p in sorted((Path(root) / ".github" / "workflows").glob("*.yml")):
        text = p.read_text(encoding="utf-8")
        if re.search(r"^\s+schedule:\s*\n(\s*#.*\n)*\s+- cron:", text, re.M):
            out.append(p.name)
    return out


def open_text(root=ROOT):
    """The text of the register's open sections (everything from an open heading to the next level-2 heading)."""
    lines = (Path(root) / REGISTER).read_text(encoding="utf-8").splitlines()
    keep, on = [], False
    for line in lines:
        if line.startswith("## "):
            on = line.startswith(OPEN_SECTIONS)
        elif on:
            keep.append(line)
    return "\n".join(keep)


def token():
    for k in ("GITHUB_TOKEN", "GH_TOKEN"):
        if os.environ.get(k):
            return os.environ[k]
    if shutil.which("gh"):
        r = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=False)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    return None


def last_run(workflow, tok):
    """(conclusion, created_at, html_url) of the last completed schedule or workflow_dispatch run on main, or None."""
    url = f"https://api.github.com/repos/{REPO}/actions/workflows/{workflow}/runs?branch=main&status=completed&per_page=20"
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "quantforge-check"})
    if tok:
        req.add_header("Authorization", f"Bearer {tok}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        runs = json.load(resp)["workflow_runs"]
    for r in runs:
        if r["event"] in ("schedule", "workflow_dispatch"):
            return r["conclusion"], r["created_at"], r["html_url"]
    return None


def judge(runs, register_open):
    """runs: {workflow: (conclusion, created_at, url) or None}. Returns (problems, report lines)."""
    problems, report = [], []
    for wf, run in sorted(runs.items()):
        if run is None:
            report.append(f"{wf}: no completed scheduled or manual run on main yet")
            continue
        concl, when, url = run
        named = f"`{wf}`" in register_open
        report.append(f"{wf}: {concl} ({when[:10]}){'; named in the register' if named else ''}")
        if concl in RED and not named:
            problems.append(f"{wf}: last run on main {when[:10]} concluded {concl} ({url}), and no open row of {REGISTER.as_posix()} names `{wf}`")
    return problems, report


def self_test():
    failures = []
    reg_with = "# K\n\n## Open\n\n| Id | x |\n|---|---|\n| F1 | `fuzz.yml` fails |\n\n## Closed\n\n| `bench.yml` |\n"
    reg_closed_only = "# K\n\n## Open\n\n| Id |\n|---|\n\n## Closed\n\n| F1 | `fuzz.yml` fixed |\n"
    red = ("failure", "2026-11-16T11:33:00Z", "u")
    green = ("success", "2026-11-17T05:17:00Z", "u")
    cases = {
        "red workflow with an open row": ({"fuzz.yml": red, "bench.yml": green}, reg_with, False),
        "green workflows and a never-run one": ({"bench.yml": green, "paper-ledger.yml": None}, reg_closed_only, False),
        "red workflow with no row": ({"mutation-stage.yml": red}, reg_with, True),
        "red workflow named only under Closed": ({"fuzz.yml": red}, reg_closed_only, True),
        "timed-out run counts as red": ({"bench.yml": ("timed_out", "2026-11-17T05:17:00Z", "u")}, reg_with, True),
    }
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        (t / "docs").mkdir()
        for name, (runs, reg, should_fail) in cases.items():
            (t / REGISTER).write_text(reg, encoding="utf-8")
            got, _ = judge(runs, open_text(t))
            if bool(got) != should_fail:
                failures.append(f"{name}: expected {'a failure' if should_fail else 'a pass'}, got {got}")
        wf = t / ".github" / "workflows"
        wf.mkdir(parents=True)
        (wf / "a.yml").write_text("on:\n  schedule:\n    - cron: '1 2 * * 1'\n", encoding="utf-8")
        (wf / "b.yml").write_text("on:\n  push:\n# schedule: not this\n", encoding="utf-8")
        if scheduled_workflows(t) != ["a.yml"]:
            failures.append(f"schedule parse: expected ['a.yml'], got {scheduled_workflows(t)}")
    if failures:
        print("self-test FAILED:\n" + "\n".join(failures), file=sys.stderr)
        return 1
    print(f"self-test: 2 passing cases pass, {len(cases) - 2} planted faults fail, the schedule parser finds only scheduled files")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)
    if a.self_test:
        return self_test()
    tok = token()
    runs = {}
    try:
        for wf in scheduled_workflows():
            runs[wf] = last_run(wf, tok)
    except Exception as e:  # noqa: BLE001 - any API failure fails the gate, with the reason
        print(f"scheduled runs: could not read the GitHub API ({type(e).__name__}: {e}); failing, because a guard that cannot see must not pass", file=sys.stderr)
        return 1
    problems, report = judge(runs, open_text())
    for line in report:
        print(f"scheduled runs: {line}")
    for p in problems:
        print(f"::error::scheduled runs: {p}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
