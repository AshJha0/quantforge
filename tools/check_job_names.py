#!/usr/bin/env python3
"""CI job names are unique and the required-check list is satisfiable (R6-15, review finding 15). Standard library only.

At v0.8.0 the required checks were job ids such as `python`, `rust` and `test`, each shared by jobs in several
workflows, so a required check could be satisfied by the wrong job. This check fails if:
  - two jobs in .github/workflows share a name (the `name:` key, else the job id);
  - a name in .github/required-checks.json is not a job name;
  - a required job's workflow does not run on every pull request (a paths filter would leave it pending).

    python tools/check_job_names.py [WORKFLOW_DIR]
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def jobs(wf_dir):
    """[(file, job id, name, runs on every PR)]"""
    out = []
    for f in sorted(Path(wf_dir).glob("*.yml")):
        lines = f.read_text(encoding="utf-8").split("\n")
        text = "\n".join(lines)
        pr = re.search(r"^  pull_request:(.*)$", text, re.M)
        every_pr = bool(pr) and not re.search(r"^  pull_request:[^\n]*\n    (paths|branches)", text, re.M) and "paths:" not in (pr.group(1) or "")
        if "jobs:" not in lines:
            continue
        i = lines.index("jobs:") + 1
        while i < len(lines):
            m = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", lines[i])
            if m:
                name, j = m.group(1), i + 1
                while j < len(lines) and (lines[j].startswith("    ") or not lines[j].strip()):
                    mm = re.match(r"^    name: (.*)$", lines[j])
                    if mm:
                        name = mm.group(1).strip()
                    j += 1
                out.append((f.name, m.group(1), re.sub(r"\s*\(\$\{\{.*$", "", name), every_pr))
            i += 1
    return out


def problems(wf_dir, required_file):
    js = jobs(wf_dir)
    by = defaultdict(list)
    for f, jid, name, _ in js:
        by[name].append(f"{f}:{jid}")
    out = [f"job name {n!r} is used by {', '.join(v)}" for n, v in by.items() if len(v) > 1]
    every = {name: e for _, _, name, e in js}
    req = json.loads(Path(required_file).read_text(encoding="utf-8"))["required"]
    for r in req:
        if r not in every:
            out.append(f"required check {r!r} is not a job name")
        elif not every[r]:
            out.append(f"required check {r!r} comes from a workflow that does not run on every pull request")
    return out


def main(argv=None):
    argv = argv or []
    wf = Path(argv[0]) if argv else ROOT / ".github" / "workflows"
    req = Path(argv[1]) if len(argv) > 1 else ROOT / ".github" / "required-checks.json"
    bad = problems(wf, req)
    for b in bad:
        print("error:", b)
    print(f"{len(jobs(wf))} jobs, {len(bad)} problem(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
