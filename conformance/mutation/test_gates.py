#!/usr/bin/env python3
"""Planted-fault self-test for the mutation gate (R6-14, plan 14.10 rule 1). Standard library only.

    python conformance/mutation/test_gates.py

Each check shows the gate failing on a planted fault and passing on the real content:
  1. every stage in stages.json plans a non-empty matrix; a planted empty stage F makes plan_matrix exit 1;
  2. check_stages.py passes on the committed file and fails on an empty stage and on a target naming no file;
  3. stage_report --gate fails a 17/20 module (85%, Wilson lower bound 64%) and passes a 39/40 module;
  4. a countersigned reason clears a listed module; an unsigned one does not;
  5. semantic_changes drops formatting/comment-only edits and keeps real, new and unknown changes;
  6. the pull-request sample in mutation-stage.yml is large enough to pass a good module: at least 3
     survivors allowed per module and a pass probability of at least 0.9 at a true 90% kill rate (a
     12-mutant sample allowed none and passed a 90% module 28% of the time).
"""
import contextlib
import io
import json
import math
import re
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import check_stages  # noqa: E402
import plan_matrix  # noqa: E402
import semantic_changes  # noqa: E402
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


def semantic_checks():
    py0 = "def f(a,b):\n    return a+b  # sum\n"
    py_fmt = "def f(a, b):\n\n    # sum of the two\n    return a + b\n"
    py_real = "def f(a, b):\n    return a - b\n"
    rs0 = "fn f(a: f64) -> f64 { a * 2.0 } // twice\n"
    rs_cmt = "/* doubled */\nfn f(a: f64) -> f64 {\n    a * 2.0\n}\n"
    rs_real = "fn f(a: f64) -> f64 { a * 3.0 }\n"
    rs_str = 'fn f() -> &str { "a // b" }\n'
    rs_str2 = 'fn f() -> &str { "a // c" }\n'
    files = {
        ("B", "fmt.py"): py0, ("H", "fmt.py"): py_fmt,
        ("B", "real.py"): py0, ("H", "real.py"): py_real,
        ("B", "cmt.rs"): rs0, ("H", "cmt.rs"): rs_cmt,
        ("B", "real.rs"): rs0, ("H", "real.rs"): rs_real,
        ("B", "str.rs"): rs_str, ("H", "str.rs"): rs_str2,
        ("H", "new.rs"): rs0,
        ("B", "bad.py"): py0, ("H", "bad.py"): "def f(:\n",
        ("B", "x.toml"): "a = 1\n", ("H", "x.toml"): "a  = 1\n",
    }
    kept = set(semantic_changes.filter_paths([p for (r, p) in files if r == "H"], "B", "H",
                                             lambda r, p: files.get((r, p))))
    check("formatting-only Python change: not selected", "fmt.py" not in kept)
    check("real Python change: selected", "real.py" in kept)
    check("comment-only Rust change: not selected", "cmt.rs" not in kept)
    check("real Rust change: selected", "real.rs" in kept)
    check("comment marker inside a string literal: change selected", "str.rs" in kept)
    check("new file: selected", "new.rs" in kept)
    check("unparsable Python: selected", "bad.py" in kept)
    check("unknown extension: selected", "x.toml" in kept)
    check("unclosed block comment: tokenizer refuses", semantic_changes.c_tokens("a /* b") is None)


def pr_sample_checks():
    wf = (HERE.parents[1] / ".github" / "workflows" / "mutation-stage.yml").read_text(encoding="utf-8")
    m = re.search(r"MAX:\s*\$\{\{\s*github\.event_name == 'pull_request' && '(\d+)'", wf)
    check("PR MAX found in mutation-stage.yml", m is not None)
    if m is None:
        return
    n = int(m.group(1))
    target = min(v for v in json.loads((HERE / "stages.json").read_text(encoding="utf-8"))["target"].values() if v is not None)

    def passes(k):  # the stage_report gate for k killed out of n scored
        return k / n >= target and stage_report.wilson(k, n)[0] >= stage_report.LOWER_BOUND

    allowed = max((n - k for k in range(n + 1) if passes(k)), default=-1)
    p90 = sum(math.comb(n, k) * 0.9 ** k * 0.1 ** (n - k) for k in range(n + 1) if passes(k))
    check(f"PR sample n={n} >= MIN_FOR_GATE={stage_report.MIN_FOR_GATE}", n >= stage_report.MIN_FOR_GATE)
    check(f"PR sample n={n} allows >= 3 survivors (allows {allowed})", allowed >= 3)
    check(f"PR sample n={n} passes a 90% module with probability >= 0.9 ({p90:.3f})", p90 >= 0.9)


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
    semantic_checks()
    pr_sample_checks()
    lo, hi = stage_report.wilson(17, 20)
    check("Wilson 17/20 is 64% to 95%", round(lo, 2) == 0.64 and round(hi, 2) == 0.95)
    print(f"{len(FAILS)} failure(s)")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
