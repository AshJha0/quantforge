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
     12-mutant sample allowed none and passed a 90% module 28% of the time);
  7. a mutmut timeout (its own per-mutant CPU limit, as for an endless loop) counts as caught, as a C++
     hang does; a survivor and a segfault do not.
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
import golden_mutants  # noqa: E402
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


def cpp_site_checks():
    """cpp_mutants.sites mutates code only: never a trailing // comment, but '//' inside a literal is code."""
    import cpp_mutants

    def shown(src):
        return [cpp_mutants.apply(src, s)[1] for s in cpp_mutants.sites(src)]

    check("trailing comment not mutated", shown("x = a + b;  // a - b < c\n") == ["x = a - b;  // a - b < c"])
    check("comment-only line skipped", shown("  // a + b\n") == [])
    check("'//' in a string literal is code", len(shown('s = "a//b" + t;  // x * y\n')) == 1)
    check("escaped quote does not end the literal", len(shown('s = "\\"//" + t;\n')) == 1)
    check("'/' operator still mutated", shown("y = a / b;\n") == ["y = a * b;"])


def skip_and_seed_checks():
    """skip-equivalents.json lists only signed Equivalent rows, and every key still names a real mutant;
    content_seed.py is a function of the source content alone (owner decision 2026-11-18)."""
    import content_seed
    import cpp_mutants
    import skips

    root = HERE.parents[1]
    SEP = chr(1)  # stands in for an escaped pipe inside a cell
    NL, CR = bytes([10]), bytes([13])
    data = json.loads(skips.SKIP_FILE.read_text(encoding="utf-8"))
    check("skip-equivalents.json has only cpp, rust and python lists", set(data) <= {"cpp", "rust", "python"})
    rows = {}
    for lang in ("cpp", "rust", "python"):
        for line in (HERE / f"equivalents-{lang}.md").read_text(encoding="utf-8").splitlines():
            cells = [c.strip().replace(SEP, "|") for c in line.replace(chr(92) + "|", SEP).split("|")[1:-1]]
            if len(cells) >= 6 and line.startswith("| "):
                rows.setdefault(f"equivalents-{lang}.md {cells[0]}", []).append(cells)
    for lang, entries in data.items():
        keys = [e["key"] for e in entries]
        check(f"{lang} skip keys are unique", len(keys) == len(set(keys)))
        for e in entries:
            name = "_" + e["key"].rsplit("_", 1)[-1] if lang == "python" else ""

            def signed(c, name=name):
                review = c[-1].lower()
                return (c[3].startswith("Equivalent") and review != "" and "not equivalent" not in review
                        and "reclassif" not in review and name in c[2])

            ok = any(signed(c) for c in rows.get(e["row"], []))
            check(f"skip {lang} {e['row']}: signed Equivalent row", ok)
            if lang == "cpp":
                file, before, after = e["key"].split(skips.SEP)
                src = (root / file).read_text(encoding="utf-8")
                live = {(src.splitlines()[s[0]].strip(), cpp_mutants.apply(src, s)[1]) for s in cpp_mutants.sites(src)}
                check(f"skip cpp {e['row']}: key still names a mutant of the current source", (before, after) in live)
            elif lang == "rust":
                file, _desc, text = e["key"].split(skips.SEP)
                lines = [x.strip() for x in (root / "rust" / file).read_text(encoding="utf-8").splitlines()]
                check(f"skip rust {e['row']}: source line still present", text in lines)
    with tempfile.TemporaryDirectory() as d:
        r = Path(d)
        (r / "cpp26").mkdir()
        f = r / "cpp26" / "a.cpp"
        f.write_bytes(b"int a = 1;" + NL)
        s1 = content_seed.seed("cpp", "cpp26/a.cpp", r)
        f.write_bytes(b"int a = 1;" + CR + NL)
        check("content seed ignores CRLF", content_seed.seed("cpp", "cpp26/a.cpp", r) == s1)
        f.write_bytes(b"int a = 2;" + NL)
        check("content seed changes with the source", content_seed.seed("cpp", "cpp26/a.cpp", r) != s1)
    check("content seed resolves the rust and python targets",
          content_seed.files("rust", "**/shortrate.rs") != [] and content_seed.files("python", "quantforge_core.shortrate*") != [])


def joint_pass_checks():
    """A PR touching one shared file can pull in about 12 module-language cells (PR #50). Print the chance
    that all pass at a given true kill rate, and require it to be reasonable at 90%."""
    n = 40
    target = 0.8

    def p_cell(p):
        return sum(math.comb(n, k) * p ** k * (1 - p) ** (n - k) for k in range(n + 1)
                   if k / n >= target and stage_report.wilson(k, n)[0] >= stage_report.LOWER_BOUND)

    for p in (0.85, 0.9):
        print(f"info 12 cells at a true {p:.0%}: all pass with probability {p_cell(p) ** 12:.2f}")
    check("12 cells at a true 90% all pass with probability >= 0.75", p_cell(0.9) ** 12 >= 0.75)


def timeout_checks():
    """mutmut 3.8.1 files exit 36 and SIGXCPU (24, -24, 152, 255) as "timeout"; cpp_mutants.py counts a hang."""
    for code in (36, 24, -24, 152, 255):
        check(f"mutmut exit {code} is a timeout", golden_mutants.MUTMUT_VERDICT.get(code) == "timeout")
    for code in (0, -11, 5):
        check(f"mutmut exit {code} is not a timeout", golden_mutants.MUTMUT_VERDICT.get(code) != "timeout")
    rows = [{"id": "hang", "unit": golden_mutants.MUTMUT_VERDICT[36], "golden": "survived"},
            {"id": "live", "unit": golden_mutants.MUTMUT_VERDICT[0], "golden": "survived"},
            {"id": "crash", "unit": golden_mutants.MUTMUT_VERDICT.get(-11, "mutmut code -11"), "golden": "survived"}]

    class A:
        impl, target, suite, seed = "python", "t*", "*", 1
    s = quiet(golden_mutants.summarise, A, rows)
    check("planted endless-loop mutant counts as caught (1 of 3)", s["sample_either_killed"] == 1)


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
    cpp_site_checks()
    skip_and_seed_checks()
    joint_pass_checks()
    timeout_checks()
    lo, hi = stage_report.wilson(17, 20)
    check("Wilson 17/20 is 64% to 95%", round(lo, 2) == 0.64 and round(hi, 2) == 0.95)
    print(f"{len(FAILS)} failure(s)")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
