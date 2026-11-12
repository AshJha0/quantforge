#!/usr/bin/env python3
"""Gate for ruling R6-10.1 (plan 14.1 R6-10, review finding 14): a per-unit output never inherits a money tolerance.

A per-unit output is a rate, spread, volatility, ratio or per-unit-notional factor, named in PER_UNIT below. For every
`ok` golden case, the effective absolute tolerance of each such output (its `output_classes` class, else the case's
`tolerance_limit`, else the case class) must be at most 1e-8, unless the case's `tolerance_limit` carries
`"per_unit_ruling"` naming a ruling of `specifications/r6-rulings.md` (R6-10.x) that says why.

    python tools/check_tolerance_units.py            # gate: exit 1 on any unexplained loose per-unit output
    python tools/check_tolerance_units.py --list     # every flagged (case, output, absolute)
    python tools/check_tolerance_units.py --self-test  # shows the gate red on a planted case (process rule 1)

Standard library only.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "conformance" / "runner"))
from runner import load_policy  # noqa: E402

LIMIT = 1e-8
PER_UNIT = {
    # rates and spreads (decimal)
    "par_rate", "par_spread", "forward_swap_rate", "swap_rate", "forward_rate", "forward_rates", "zero_rates", "zero_rate",
    "implied_repo", "yield", "z_spread", "spread", "spreads", "breakeven",
    # volatilities
    "black_vol", "black_vols", "vol", "implied_vol", "normal_vol",
    # ratios and per-unit factors
    "index_ratio", "premium_pct_foreign", "jacobian", "annuity", "conversion_factor", "discount_factor", "discount_factors",
    "forward", "forwards", "survival_probability", "survival_probabilities",
}
RULING = re.compile(r"^R6-10\.\d+$")


def effective_abs(case, key, classes):
    per = case.get("output_classes", {})
    if key in per:
        cl = classes[per[key]]
        return None if cl.get("exact") else cl.get("absolute")
    cl = classes[case["tolerance_class"]]
    if cl.get("exact"):
        return None
    lim = case.get("tolerance_limit") or {}
    return lim.get("absolute", cl.get("absolute"))


def scan(golden, classes):
    flagged, explained = [], 0
    for p in sorted(Path(golden).rglob("*.json")):
        doc = json.loads(p.read_text(encoding="utf-8"))
        for c in doc.get("cases", []):
            if c["expected"]["status"] != "ok":
                continue
            for k in c["expected"]["outputs"]:
                if k not in PER_UNIT:
                    continue
                ab = effective_abs(c, k, classes)
                if ab is None or ab <= LIMIT:
                    continue
                r = (c.get("tolerance_limit") or {}).get("per_unit_ruling")
                if r and RULING.match(r):
                    explained += 1
                    continue
                flagged.append((c["case_id"], k, ab))
    return flagged, explained


def self_test(classes):
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        case = {"case_id": "planted-0001", "operation": "rates.ois.par", "inputs": {}, "tolerance_class": "simple_analytic",
                "expected": {"status": "ok", "outputs": {"par_rate": 0.04}}, "tolerance_limit": {"absolute": 1e-3, "relative": 0.0}}
        Path(d, "planted.json").write_text(json.dumps({"cases": [case]}), encoding="utf-8")
        bad, _ = scan(d, classes)
        assert bad == [("planted-0001", "par_rate", 1e-3)], bad
        case["tolerance_limit"]["per_unit_ruling"] = "R6-10.2"
        Path(d, "planted.json").write_text(json.dumps({"cases": [case]}), encoding="utf-8")
        assert scan(d, classes)[0] == []
    print("self-test: planted par_rate at 1e-3 absolute is flagged; with a per_unit_ruling it passes")
    return 0


def main():
    classes = load_policy(ROOT / "conformance" / "tolerances" / "policy.yaml")
    if "--self-test" in sys.argv:
        return self_test(classes)
    flagged, explained = scan(ROOT / "datasets" / "golden", classes)
    if "--list" in sys.argv:
        for row in flagged:
            print(*row)
    print(f"per-unit outputs above {LIMIT:g} absolute: {len(flagged)} unexplained, {explained} under an R6-10 ruling")
    return 1 if flagged else 0


if __name__ == "__main__":
    sys.exit(main())
