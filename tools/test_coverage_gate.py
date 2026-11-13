#!/usr/bin/env python3
"""Planted-fault self-test for the R6-26 per-file coverage gate (plan 14.10 rule 1). Standard library only.

Builds tiny coverage reports in each of the four formats with one planted under-covered file (50%) in a
stage that the stage_e.json module gate never saw, and shows: the gate fails; an allow-list entry with a reason
clears it; an entry without a reason does not; a fully covered report passes; test files are not gated.
"""
import contextlib
import io
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import quality_gate as Q  # noqa: E402

FAILS = []
BAD = {"python": "quantforge_core/hedge_solvers.py", "java": "org/quantforge/hedging/HedgeSolver.java",
       "rust": "rust/crates/quantforge-core/src/hedge_solvers.rs", "cpp": "cpp26/src/core/hedging.cpp"}
CANON = {"python": "python/quantforge_core/hedge_solvers.py", "java": "java25/src/main/java/org/quantforge/hedging/HedgeSolver.java",
         "rust": BAD["rust"], "cpp": BAD["cpp"]}


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


def report(lang, hit):
    """hit of 10 lines covered in the planted file; one other file fully covered."""
    if lang == "python":
        f = {BAD[lang]: {"summary": {"covered_lines": hit, "num_statements": 10}},
             "quantforge_core/daycount.py": {"summary": {"covered_lines": 10, "num_statements": 10}},
             "tests/test_x.py": {"summary": {"covered_lines": 0, "num_statements": 10}}}
        return json.dumps({"files": f})
    if lang == "rust":
        recs = []
        for name, h in ((BAD[lang], hit), ("rust/crates/quantforge-core/src/daycount.rs", 10)):
            recs += [f"SF:{name}"] + [f"DA:{i},{1 if i <= h else 0}" for i in range(1, 11)] + ["end_of_record"]
        return "\n".join(recs) + "\n"
    if lang == "java":
        return ('<report><package name="org/quantforge/hedging"><sourcefile name="HedgeSolver.java">'
                f'<counter type="LINE" missed="{10 - hit}" covered="{hit}"/></sourcefile></package></report>')
    lines = "".join(f'<line number="{i}" hits="{1 if i <= hit else 0}"/>' for i in range(1, 11))
    return f'<coverage><packages><package><classes><class filename="{BAD[lang]}"><lines>{lines}</lines></class></classes></package></packages></coverage>'


def run(lang, text, allow):
    with tempfile.TemporaryDirectory() as d:
        r, a = Path(d) / "r", Path(d) / "a.json"
        r.write_text(text, encoding="utf-8")
        a.write_text(json.dumps(allow), encoding="utf-8")
        c = Path(d) / "c.json"  # no stage modules: only the per-file gate decides
        c.write_text(json.dumps({"stage": "T", "coverage_min": 0.85, "modules": []}), encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            return Q.main(["--coverage", str(r), "--lang", lang, "--per-file", "--allow", str(a), "--config", str(c)])


def main():
    for lang in Q.LANGS:
        rows = Q.READERS[lang](report(lang, 5))
        _, fails = Q.per_file_gate(lang, rows, {})
        check(f"{lang}: planted 50% file fails the per-file gate", fails == [CANON[lang]])
        _, fails = Q.per_file_gate(lang, rows, {lang: [{"path": CANON[lang], "reason": "entry point"}]})
        check(f"{lang}: allow-list entry with a reason clears it", fails == [])
        _, fails = Q.per_file_gate(lang, rows, {lang: [{"path": CANON[lang], "reason": ""}]})
        check(f"{lang}: allow-list entry without a reason does not", fails == [CANON[lang]])
        _, fails = Q.per_file_gate(lang, Q.READERS[lang](report(lang, 10)), {})
        check(f"{lang}: fully covered report passes", fails == [])
    check("python: test files are not gated", all("tests/" not in f for f in
          Q.per_file_gate("python", Q.READERS["python"](report("python", 10)), {})[1]))
    check("python end to end: quality_gate.py --per-file exits 1 on the planted file", run("python", report("python", 5), {}) == 1)
    check("python end to end: exits 0 when covered", run("python", report("python", 10), {}) == 0)
    print(f"{len(FAILS)} failure(s)")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
