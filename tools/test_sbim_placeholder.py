#!/usr/bin/env python3
"""Guards specifications/tables/stage_k/sbim-placeholder.json (K-8h, KR-130). Standard library only.

  1. the committed file is byte for byte the output of tools/gen_sbim_placeholder.py, so a hand edit or a file
     replaced by any other parameter set (a licensed calibration included) fails;
  2. the header says placeholder (placeholder: true, label "placeholder weights", notice stating no relation to any
     industry or regulatory margin model's parameters);
  3. every number follows the stated artificial rule, recomputed here independently of the generator;
  4. planted fault: a table with one weight changed is rejected by check 1 and check 3;
  5. the same three checks and a planted fault for specifications/tables/stage_k/sbim-ir-delta-g.json, the stage G
     table of xva.sbim.ir_delta (KR-150, KR-151: RW = 10 x k, rho(k, l) = 1 - 0.1 |k - l|);
  6. no tracked file outside the history files named in HISTORY still holds the hand-typed stage G weight vector or
     the old tenor-correlation constant that KR-150 replaced (needs git; skipped with a note outside a checkout).
"""
import json
import re
import subprocess
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


# The replaced stage G values (KR-150), as they were written in v0.7.0 to v0.10.0. Built from pieces so that this
# file does not match its own pattern.
OLD = re.compile("|".join(["10" + r"9(\.0)?, ?10" + r"5(\.0)?, ?90", "0" + r"\.659754", "exp" + r"\(-0\.3 "]))
# History and audit records that name the old values on purpose (KR-155: not rewritten).
HISTORY = {"program/STAGE_K_ISDA_AUDIT.md", "program/STAGE_K_MARGIN_REPLACEMENT.md", "specifications/stage-k-rulings-margin.md"}


def rule_errors_g(doc):
    """Independent recomputation of the stage G table from KR-150 (not from G.build_g)."""
    err = []
    F = Fraction
    if doc.get("tenors_years") != ["0.25", "1", "2", "5", "10", "30"]:
        err.append("tenors")
    rw, m = doc["risk_weights"], doc["correlations"]
    if len(rw) != 6 or any(F(w) != 10 * (k + 1) for k, w in enumerate(rw)):
        err.append("RW")
    if len(m) != 6 or any(len(r) != 6 for r in m):
        err.append("shape")
    else:
        for k in range(6):
            for l in range(6):
                if F(m[k][l]) != 1 - F(abs(k - l), 10):
                    err.append(f"rho {k},{l}")
    return err


def old_value_hits():
    """Tracked files (outside HISTORY) that still hold a replaced value; None when git is not available."""
    root = G.ROOT
    try:
        out = subprocess.run(["git", "grep", "-l", "-E", OLD.pattern], cwd=root, capture_output=True, text=True, check=False)
    except OSError:
        return None
    if out.returncode not in (0, 1):
        return None
    return sorted(f for f in out.stdout.split() if f not in HISTORY)


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
    committed_g = G.OUT_G.read_text(encoding="utf-8")
    checks.append(("stage G table equals generator output", committed_g == G.text_g()))
    doc_g = json.loads(committed_g)
    checks.append(("stage G table header says placeholder", doc_g.get("placeholder") is True and doc_g.get("label") == "placeholder weights"
                   and "no relation" in doc_g.get("notice", "")))
    checks.append(("stage G table follows KR-150", rule_errors_g(doc_g) == []))
    bad_g = json.loads(committed_g)
    bad_g["risk_weights"][2] = "90"
    checks.append(("planted fault: changed stage G weight breaks the rule", rule_errors_g(bad_g) == ["RW"]
                   and json.dumps(bad_g, indent=1, ensure_ascii=True) + "\n" != G.text_g()))
    checks.append(("planted fault: the old pattern finds the old vector", OLD.search("[1" + "09.0, 105.0, 90.0, 71.0]") is not None))
    hits = old_value_hits()
    if hits is None:
        print("NOTE\tgit not available: old-value scan skipped")
    else:
        if hits:
            print("old stage G values still in: " + ", ".join(hits))
        checks.append(("no replaced stage G value outside the history files", hits == []))
    ok = True
    for name, good in checks:
        print(f"{'PASS' if good else 'FAIL'}\t{name}")
        ok &= good
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
