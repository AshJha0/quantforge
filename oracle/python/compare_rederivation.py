"""Judge an independent re-derivation (owner decision 2026-11-12, plan R6-13) against the stage F goldens.

    python oracle/python/compare_rederivation.py RESULTS.json [--source "model, date"] [--write]

RESULTS.json: a list (or {"cases": [...]}) of {"case_id": ..., "outputs": {...}} produced blind to the goldens.
Each case is judged at the golden's OWN tolerance by the conformance runner's comparison (conformance/runner);
a case counts only if every golden output is present and agrees. Only the four value classes with no free outside
library may count (CDS index option, FRTB SA, book lifecycle and marks, traffic light); entries for any other
operation are listed and ignored. Every disagreement is printed with both values.

--write records the verdicts in oracle/REDERIVATION_REGISTER.json, which tools/outside_shares.py reads.
Standard library plus the repo's runner only.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "conformance" / "runner"))
sys.path.insert(0, str(ROOT / "tools"))
import runner  # noqa: E402
from outside_shares import rederive_allowed  # noqa: E402

POLICY = runner.load_policy(ROOT / "conformance" / "tolerances" / "policy.yaml")


def goldens():
    out = {}
    for f in sorted((ROOT / "datasets" / "golden" / "stage_f").glob("*.json")):
        if f.name.startswith("e1_"):
            continue
        for c in json.loads(f.read_text(encoding="utf-8"))["cases"]:
            out[c["case_id"]] = c
    return out


def judge(case, outputs):
    """(ok, reasons). Uses the runner's own comparison so the tolerance is exactly the golden's."""
    exp = case["expected"]["outputs"]
    missing = [k for k in exp if k not in outputs]
    if missing:
        return False, [f"missing outputs {missing}"]
    status, msgs = runner.judge(case, {"case_id": case["case_id"], "status": "ok", "outputs": {k: outputs[k] for k in exp}}, POLICY)
    return status == "pass", msgs


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("results")
    ap.add_argument("--source", default="independent re-derivation")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args(argv)
    doc = json.loads(Path(a.results).read_text(encoding="utf-8"))
    rows = doc["cases"] if isinstance(doc, dict) else doc
    gold = goldens()
    verdicts, ignored, bad = [], [], []
    for r in rows:
        c = gold.get(r["case_id"])
        if c is None:
            bad.append((r["case_id"], "not a stage F golden"))
            continue
        if not rederive_allowed(c["operation"]):
            ignored.append((r["case_id"], c["operation"]))
            continue
        if c["expected"]["status"] != "ok":
            ignored.append((r["case_id"], "error or invariance case (outside the value denominator)"))
            continue
        ok, why = judge(c, r.get("outputs", {}))
        verdicts.append({"case_id": c["case_id"], "operation": c["operation"], "pass": ok})
        if not ok:
            bad.append((c["case_id"], "; ".join(why)))
    print(f"judged {len(verdicts)}: {sum(v['pass'] for v in verdicts)} agree, {len(verdicts) - sum(v['pass'] for v in verdicts)} disagree; ignored {len(ignored)}")
    for cid, why in bad:
        print(f"  DISAGREE {cid}: {why}")
    for cid, why in ignored:
        print(f"  ignored {cid}: {why}")
    if a.write:
        (ROOT / "oracle" / "REDERIVATION_REGISTER.json").write_text(json.dumps(
            {"source": a.source, "rule": "owner 2026-11-12: counts only for the four no-library classes; every output at the golden's own tolerance",
             "cases": verdicts}, indent=1) + "\n", encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
