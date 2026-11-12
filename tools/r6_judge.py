#!/usr/bin/env python3
"""Judge one build on chosen golden files without the contract-version stop (R6 lanes run v0.8.0 builds against
contract 1.12.0 goldens while they move). Evidence tool only; CI uses conformance/runner/runner.py.

    python tools/r6_judge.py --impl python [--config FILE] datasets/golden/r6/*.json datasets/golden/stage_f/risk_f4.json
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "conformance" / "runner"))
from runner import judge, load_impls, load_policy, resolve_command, run_batch  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--impl", required=True)
    ap.add_argument("--config", default=str(ROOT / "conformance" / "runner" / "implementations.json"))
    ap.add_argument("files", nargs="+")
    a = ap.parse_args()
    classes = load_policy(ROOT / "conformance" / "tolerances" / "policy.yaml")
    base, cwd = resolve_command(load_impls(a.config)[a.impl])
    for f in a.files:
        cases = json.loads(Path(f).read_text(encoding="utf-8"))["cases"]
        res, err, _ = run_batch(base + ["batch"], cwd, cases, 3600)
        if err:
            print(f"{Path(f).name}: CRASH {err}")
            continue
        peers = {c["case_id"]: r for c, r in zip(cases, res)}
        n = Counter()
        fails = []
        for c, r in zip(cases, res):
            st, msg = judge(c, r, classes, peers)
            n[st] += 1
            if st == "fail":
                fails.append(f"{c['case_id']}: {msg[0][:110]}")
        print(f"{Path(f).name}: {dict(n)}")
        for x in fails[:4]:
            print("   ", x)


if __name__ == "__main__":
    main()
