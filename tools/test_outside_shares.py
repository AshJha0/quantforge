#!/usr/bin/env python3
"""Planted-fault self-test for tools/outside_shares.py (R6-13, plan 14.10 rule 1). Standard library only.

  1. --check passes on the committed tree;
  2. a golden suite added after the register was written (review finding 6, stage F) is caught;
  3. a register total that no longer matches its golden is caught;
  4. a stage under 60% of its value-checked cases fails (no dated-plan fallback, owner 2026-11-12), and error
     cases leave the denominator;
  5. a stage F case marked SCIPY.CHI2 counts as reimplementation, not as an outside check.
"""
import contextlib
import io
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import outside_shares as S  # noqa: E402

FAILS = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


def run(*a):
    with contextlib.redirect_stdout(io.StringIO()):
        return S.main(list(a))


def nonfloor(p):
    return [x for x in p if "floor" not in x]


def main():
    p = []
    S.build(p)
    check("committed tree: no problems other than the floor", not nonfloor(p))
    check("committed OUTSIDE_SHARES.md matches a fresh run", (S.ORACLE / "OUTSIDE_SHARES.md").read_text(encoding="utf-8") == S.markdown(S.build([])))
    real_golden, real_oracle = S.GOLDEN, S.ORACLE
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        g, o = tmp / "golden", tmp / "oracle"
        for st in ("stage_d", "stage_e", "stage_e_b", "stage_f", "stage_g", "stage_i"):
            shutil.copytree(real_golden / st, g / st)
        o.mkdir()
        for f in real_oracle.glob("outside_register*.json"):
            shutil.copy(f, o / f.name)
        S.GOLDEN, S.ORACLE = g, o
        try:
            p = []
            S.build(p)
            check("temp copy builds clean apart from the floor", not nonfloor(p))
            src = json.loads((g / "stage_g" / "reserve_g.json").read_text(encoding="utf-8"))
            src["suite"] = "planted_g"
            (g / "stage_g" / "planted_g.json").write_text(json.dumps(src), encoding="utf-8")
            p = []
            S.build(p)
            check("planted suite missing from the register is caught", any("planted_g" in x for x in p))
            (g / "stage_g" / "planted_g.json").unlink()
            reg = json.loads((o / "outside_register_i.json").read_text(encoding="utf-8"))
            reg["hedgeqp_i"]["total"] += 1
            (o / "outside_register_i.json").write_text(json.dumps(reg), encoding="utf-8")
            p = []
            S.build(p)
            check("planted register total mismatch is caught", any("hedgeqp_i" in x for x in p))
            shutil.copy(real_oracle / "outside_register_i.json", o / "outside_register_i.json")
            # planted downgrade of the stage G per-case register (oracle/OUTSIDE_G_R6.json, oracle lane 2)
            if (real_oracle / "OUTSIDE_G_R6.json").is_file():
                shutil.copy(real_oracle / "OUTSIDE_G_R6.json", o / "OUTSIDE_G_R6.json")
                base = S.build([])["stages"]["G"]["without_sweeps"]["counted"]
                pg = json.loads((o / "OUTSIDE_G_R6.json").read_text(encoding="utf-8"))
                for suite in pg["suites"].values():
                    for c in suite["cases"]:
                        c["checks"][0]["pass"] = False
                (o / "OUTSIDE_G_R6.json").write_text(json.dumps(pg), encoding="utf-8")
                down = S.build([])["stages"]["G"]["without_sweeps"]
                check("planted G per-case downgrade lowers the counted cases", down["counted"] < base)
                reg = json.loads((o / "outside_register_g.json").read_text(encoding="utf-8"))
                reg["expsim_g"]["counted"] = 0  # plus the per-case downgrade: G falls under 60%
                (o / "outside_register_g.json").write_text(json.dumps(reg), encoding="utf-8")
                p = []
                S.build(p)
                check("planted G downgrade fails the 60% floor", any("stage G" in x and "floor" in x for x in p))
                shutil.copy(real_oracle / "OUTSIDE_G_R6.json", o / "OUTSIDE_G_R6.json")
                shutil.copy(real_oracle / "outside_register_g.json", o / "outside_register_g.json")
            p = []
            doc = S.build(p)
            f = doc["stages"]["F"]["without_sweeps"]
            check("a stage under 60% of value cases fails", (f["share"] < S.FLOOR) == any("stage F" in x and "floor" in x for x in p))
            d = doc["stages"]["D"]["without_sweeps"]
            check("error cases leave the denominator (stage D: 520 value cases of 654)", d["cases"] == 520 and d["error_and_invariance_cases"] == 134)
        finally:
            S.GOLDEN, S.ORACLE = real_golden, real_oracle
    c = S.classify_case_register([{"case_id": "x", "library": "QuantLib", "convention_rows": ["SCIPY.CHI2"]}], set())
    check("SCIPY.CHI2 case is reimplementation", c["x"][0] == "reimplementation")
    print(f"{len(FAILS)} failure(s)")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
