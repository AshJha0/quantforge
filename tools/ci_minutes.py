#!/usr/bin/env python3
"""CI minutes used over the last N days, as a Markdown section for the release notes (plan 13.2 E10).

    GH_TOKEN=... python tools/ci_minutes.py --repo OWNER/NAME [--days 7]

Sums job wall-clock time (started_at to completed_at) over every workflow run created in the window, per
workflow, from the GitHub REST API. Standard library only. Public-repository minutes are free; the number is
there so a cost regression is visible. Prints a note and exits 0 if the API is unreachable, so it never
blocks a release.
"""
import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

API = "https://api.github.com"


def get(url, token):
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "Authorization": f"Bearer {token}",
                                               "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "quantforge-ci-minutes"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


def job_minutes(jobs):
    total = 0.0
    for j in jobs:
        a, b = ts(j.get("started_at")), ts(j.get("completed_at"))
        if a and b and b > a:
            total += (b - a).total_seconds() / 60
    return total


def summarise(per_workflow, days):
    lines = [f"\n### CI minutes, last {days} days\n", "| Workflow | Runs | Job minutes |", "|---|---:|---:|"]
    for name, (runs, mins) in sorted(per_workflow.items(), key=lambda kv: -kv[1][1]):
        lines.append(f"| {name} | {runs} | {mins:.0f} |")
    lines.append(f"| **Total** | {sum(r for r, _ in per_workflow.values())} | {sum(m for _, m in per_workflow.values()):.0f} |")
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", required=True)
    ap.add_argument("--days", type=int, default=7)
    a = ap.parse_args(argv)
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN", "")
    since = (datetime.now(timezone.utc) - timedelta(days=a.days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    per = {}
    try:
        page = 1
        while True:
            d = get(f"{API}/repos/{a.repo}/actions/runs?created=>={since}&per_page=100&page={page}", token)
            for run in d["workflow_runs"]:
                jobs = get(f"{API}/repos/{a.repo}/actions/runs/{run['id']}/jobs?per_page=100", token)["jobs"]
                r, m = per.get(run["name"], (0, 0.0))
                per[run["name"]] = (r + 1, m + job_minutes(jobs))
            if len(d["workflow_runs"]) < 100 or page >= 10:
                break
            page += 1
    except Exception as e:  # never block a release on a reporting step
        print(f"\n_CI minutes unavailable: {e}_\n")
        return 0
    print(summarise(per, a.days))
    return 0


if __name__ == "__main__":
    sys.exit(main())
