#!/usr/bin/env python3
"""Planted-fault self-test for the mutation gate (R6-14, plan 14.10 rule 1). Standard library only.

    python conformance/mutation/test_gates.py

Each check shows the gate failing on a planted fault and passing on the real content:
  1. every stage in stages.json plans a non-empty matrix; a planted empty stage F makes plan_matrix exit 1;
  2. check_stages.py passes on the committed file and fails on an empty stage and on a target naming no file;
  3. stage_report --gate fails a 17/20 module (85%, Wilson lower bound 64%) and passes a 39/40 module;
  4. a countersigned reason clears a listed module; an unsigned one does not.
"""
import contextlib
import io
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import check_stages  # noqa: E402
import plan_matrix  # noqa: E402
import stage_report  # noqa: E402

FAILS = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


def quiet(fn, *a):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return fn(*a)


def result(tmp, lang, module, killed, survived):
    s = {"mutants": killed + survived, "sampled": killed + survived, "sample_either_killed": killed,
         "sample_unit_killed": killed, "sample_golden_killed": 0, "unit_verdicts": {}}
    (tmp / f"{lang}--{module}.json").write_text(json.dumps({"summary": s}), encoding="utf-8")


def main():
    cfg = json.loads((HERE / "stages.json").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        for st in cfg["stages"]:
            check(f"stage {st} plans mutants", quiet(plan_matrix.main, ["--stage", st]) == 0)
        check("ALL plans every module", quiet(plan_matrix.main, ["--stage", "ALL"]) == 0)
        bad = json.loads(json.dumps(cfg))
        bad["stages"]["F"] = []
        bp = tmp / "bad.json"
        bp.write_text(json.dumps(bad), encoding="utf-8")
        check("planted empty stage F: plan_matrix exits 1", quiet(plan_matrix.main, ["--stages", str(bp), "--stage", "F"]) == 1)
        check("check_stages passes on stages.json", quiet(check_stages.main, []) == 0)
        check("planted empty stage F: check_stages fails", quiet(check_stages.main, [str(bp)]) == 1)
        bad2 = json.loads(json.dumps(cfg))
        bad2["stages"]["I"][0]["rust"] = "**/no_such_module.rs"
        bp2 = tmp / "bad2.json"
        bp2.write_text(json.dumps(bad2), encoding="utf-8")
        check("planted missing target: check_stages fails", quiet(check_stages.main, [str(bp2)]) == 1)

        one = {"target": {"T": 0.8}, "stages": {"T": [{"module": "m", "suite": "x", "python": "p"}]}}
        sp = tmp / "one.json"
        sp.write_text(json.dumps(one), encoding="utf-8")
        res = tmp / "res"
        res.mkdir()
        base = ["--stage", "T", "--stages", str(sp), "--results", str(res), "--gate", "--reasons", str(tmp / "none.json")]
        result(res, "python", "m", 17, 3)
        check("planted 17/20 (lower bound 64%): gate fails", quiet(stage_report.main, base) == 1)
        result(res, "python", "m", 39, 1)
        check("39/40 (lower bound 87%): gate passes", quiet(stage_report.main, base) == 0)
        result(res, "python", "m", 17, 3)
        rp = tmp / "r.json"
        rp.write_text(json.dumps({"exceptions": [{"lang": "python", "module": "m", "reason": "r", "second_reviewer": ""}]}))
        check("unsigned reason does not clear", quiet(stage_report.main, base[:-1] + [str(rp)]) == 1)
        rp.write_text(json.dumps({"exceptions": [{"lang": "python", "module": "m", "reason": "r", "second_reviewer": "x 2026-11-12"}]}))
        check("countersigned reason clears", quiet(stage_report.main, base[:-1] + [str(rp)]) == 0)
        empty = tmp / "empty"
        empty.mkdir()
        check("no results at all: gate fails", quiet(stage_report.main, ["--stage", "T", "--stages", str(sp), "--results", str(empty), "--gate"]) == 1)
    lo, hi = stage_report.wilson(17, 20)
    check("Wilson 17/20 is 64% to 95%", round(lo, 2) == 0.64 and round(hi, 2) == 0.95)
    print(f"{len(FAILS)} failure(s)")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
