#!/usr/bin/env python3
"""Guards specifications/tables/stage_k/sbim-placeholder.json (K-8h, KR-130). Standard library only.

  1. the committed file is byte for byte the output of tools/gen_sbim_placeholder.py, so a hand edit or a file
     replaced by any other parameter set (a licensed calibration included) fails;
  2. the header says placeholder (placeholder: true, label "placeholder weights", notice stating no relation to any
     industry or regulatory margin model's parameters);
  3. every number follows the stated artificial rule, recomputed here independently of the generator;
  4. planted fault: a table with one weight changed is rejected by check 1 and check 3.
"""
import json
import sys
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gen_sbim_placeholder as G  # noqa: E402


def rule_errors(doc):
    """Independent recomputation of every number from the rules (not from G.build)."""
    err = []
    F = Fraction
    tenors = doc["tenors"]
    if [(t["label"], t["index"], t["days"]) for t in tenors] != [("1W", 1, 7), ("1Y", 2, 365), ("5Y", 3, 1825), ("10Y", 4, 3650)]:
        err.append("tenors")
    ir = doc["IR"]["delta"]
    for t in tenors:
        if F(ir["rw"][t["label"]]) != 10 * t["index"]:
            err.append(f"IR rw {t['label']}")
    m = ir["rho"]["matrix"]
    for i in range(4):
        for j in range(4):
            want = 1 if i == j else 1 - F(abs(i - j), 10)
            if F(m[i][j]) != want:
                err.append(f"IR rho {i},{j}")
    if F(ir["gamma"]) != F(1, 4) or F(ir["threshold"]) != 100:
        err.append("IR gamma/threshold")
    if F(doc["IR"]["vega"]["rw"]) != 2 or F(doc["IR"]["vega"]["threshold"]) != 1000:
        err.append("IR vega")
    fx = doc["FX"]["delta"]
    if (F(fx["rw"]), F(fx["rho"]), F(fx["threshold"])) != (5, F(1, 2), 1000):
        err.append("FX")
    eq = doc["EQ"]["delta"]
    for b in ("1", "2", "3"):
        if F(eq["rw"][b]) != 10 * int(b) or F(eq["rho"][b]) != F(1, 2):
            err.append(f"EQ bucket {b}")
    if F(eq["rw"]["RESIDUAL"]) != 40 or F(eq["rho"]["RESIDUAL"]) != F(1, 4):
        err.append("EQ residual")
    if F(eq["gamma"]) != F(1, 4) or F(eq["threshold"]) != 100:
        err.append("EQ gamma/threshold")
    if F(doc["EQ"]["vega"]["rw"]) != 3 or F(doc["EQ"]["vega"]["threshold"]) != 1000:
        err.append("EQ vega")
    c = doc["curvature"]
    if (F(c["sf_scale"]), F(c["sf_days"]), F(c["z"])) != (F(1, 4), 20, 2):
        err.append("curvature")
    if F(doc["rho_class"]["value"]) != F(1, 5):
        err.append("rho_class")
    return err


def main():
    checks = []
    committed = G.OUT.read_text(encoding="utf-8")
    checks.append(("committed file equals generator output", committed == G.text()))
    doc = json.loads(committed)
    checks.append(("header says placeholder", doc.get("placeholder") is True and doc.get("label") == "placeholder weights"
                   and "no relation" in doc.get("notice", "") and "project definition" in doc.get("notice", "")))
    checks.append(("every number follows the stated rule", rule_errors(doc) == []))
    bad = json.loads(committed)
    bad["IR"]["delta"]["rw"]["5Y"] = "31"
    bad_text = json.dumps(bad, indent=1, ensure_ascii=True) + "\n"
    checks.append(("planted fault: changed weight differs from generator output", bad_text != G.text()))
    checks.append(("planted fault: changed weight breaks the rule", rule_errors(bad) == ["IR rw 5Y"]))
    ok = True
    for name, good in checks:
        print(f"{'PASS' if good else 'FAIL'}\t{name}")
        ok &= good
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
