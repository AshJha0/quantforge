#!/usr/bin/env python3
"""R6-10 re-judging (ruling R6-10.1): run one implementation on every case `tools/check_tolerance_units.py` flags and
report, per flagged output, the observed error against the golden. Read-only on the goldens; writes a JSON report.

    python conformance/tolerances/rejudge_r6.py --impl python --out conformance/tolerances/R6_REJUDGE_python.json

The report is evidence for the per-suite decisions in specifications/r6-rulings.md (R6-10.2 to R6-10.n): tighten to
class `per_unit` where every build is inside it, or keep a wider bound under a named ruling.
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "conformance" / "runner"))
sys.path.insert(0, str(ROOT / "tools"))
from runner import load_impls, load_policy, resolve_command, run_batch  # noqa: E402
from check_tolerance_units import scan  # noqa: E402


def errs(a, e, out):
    if isinstance(e, list):
        for x, y in zip(a or [], e):
            errs(x, y, out)
    elif isinstance(e, (int, float)) and isinstance(a, (int, float)):
        out.append((abs(a - e), abs(e)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--impl", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--config", default=str(ROOT / "conformance" / "runner" / "implementations.json"))
    a = ap.parse_args()
    classes = load_policy(ROOT / "conformance" / "tolerances" / "policy.yaml")
    flagged, _ = scan(ROOT / "datasets" / "golden", classes)
    want = defaultdict(set)
    for cid, k, _ in flagged:
        want[cid].add(k)
    cases = []
    for p in sorted((ROOT / "datasets" / "golden").rglob("*.json")):
        for c in json.loads(p.read_text(encoding="utf-8")).get("cases", []):
            if c["case_id"] in want:
                cases.append(c)
    base, cwd = resolve_command(load_impls(a.config)[a.impl])
    rep = {}
    for i in range(0, len(cases), 50):
        chunk = cases[i:i + 50]
        res, err, _ = run_batch(base + ["batch"], cwd, chunk, 3600)
        if err:
            raise SystemExit(err)
        for c, r in zip(chunk, res):
            for k in want[c["case_id"]]:
                pts = []
                if r and r.get("status") == "ok":
                    errs(r["outputs"].get(k), c["expected"]["outputs"][k], pts)
                rep[f"{c['case_id']}:{k}"] = {"status": (r or {}).get("status"), "max_abs_error": max((x for x, _ in pts), default=None),
                                              "max_rel_error": max((x / s if s else x for x, s in pts), default=None),
                                              "max_abs_value": max((s for _, s in pts), default=None)}
    Path(a.out).write_text(json.dumps(rep, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{len(rep)} outputs judged")


if __name__ == "__main__":
    main()
