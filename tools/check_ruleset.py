#!/usr/bin/env python3
"""G1k check (plan 12.7, ruling KR-225, PROPOSED): the main-branch ruleset requires branches to be up to date.

    python tools/check_ruleset.py --file benchmarks/results/k7/ruleset-2026-11-20.json
    gh api repos/AshJha0/quantforge/rulesets/26732064 > ruleset.json && python tools/check_ruleset.py --file ruleset.json
    python tools/check_ruleset.py --self-test

Plain idea: a pull request that is behind main has passed its checks against an old main, so the merge result was
never tested. The "strict" policy of a required-status-checks rule makes GitHub refuse such a merge until the branch
is brought up to date. This script reads a saved ruleset (the JSON that `gh api` returns) and passes only if the rule
is enforced and strict. It never changes the setting: the ruleset is the owner's repository setting.

Exit 0: strict on and enforcement active. Exit 1: anything else, with the reason. Standard library only.
"""
import argparse
import json
import sys
from pathlib import Path


def problems(doc):
    out = []
    if doc.get("enforcement") != "active":
        out.append(f"enforcement is {doc.get('enforcement')!r}, not 'active'")
    rules = [r for r in doc.get("rules", []) if r.get("type") == "required_status_checks"]
    if not rules:
        out.append("no required_status_checks rule")
    for r in rules:
        if (r.get("parameters") or {}).get("strict_required_status_checks_policy") is not True:
            out.append("required_status_checks: strict_required_status_checks_policy is not true "
                       "(a pull request behind main can merge)")
    return out


def self_test():
    good = {"enforcement": "active", "rules": [{"type": "required_status_checks",
                                                "parameters": {"strict_required_status_checks_policy": True}}]}
    planted = {"strict false": {**good, "rules": [{"type": "required_status_checks",
                                                   "parameters": {"strict_required_status_checks_policy": False}}]},
               "no rule": {**good, "rules": []},
               "evaluate only": {**good, "enforcement": "evaluate"}}
    bad = [name for name, doc in planted.items() if not problems(doc)]
    if problems(good) or bad:
        print(f"self-test FAILED: good={problems(good)}, planted faults not caught: {bad}", file=sys.stderr)
        return 1
    print(f"self-test: the good ruleset passes and {len(planted)} planted faults fail")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", help="a ruleset JSON as returned by gh api repos/OWNER/REPO/rulesets/ID")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)
    if a.self_test:
        return self_test()
    if not a.file:
        ap.error("--file or --self-test")
    found = problems(json.loads(Path(a.file).read_text(encoding="utf-8")))
    for p in found:
        print(f"G1k: {p}", file=sys.stderr)
    if not found:
        print("G1k: strict rule on")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
