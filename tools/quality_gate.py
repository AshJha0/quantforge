#!/usr/bin/env python3
"""Stage code-quality gate over conformance/quality/stage_<x>.json. Standard library only.

    python tools/quality_gate.py --check-config [--config FILE]
        Every filled path exists; Rust files sit in a workspace member crate (so clippy and cargo test
        see them); C++ files are listed in cpp26/CMakeLists.txt (so they build, and the sanitizer and
        fuzz builds include them); Python files are in a package that ruff and mutmut cover; Python
        test files are in mutmut's tests_dir (a warning). Lists the entries still TODO; a test missing from mutmut is a warning. Exit 1 on a broken entry.

    python tools/quality_gate.py --coverage REPORT --lang LANG [--config FILE]
        Line coverage per module for one language from its report, against coverage_min. Reads
        coverage.py JSON (python), JaCoCo XML (java), LCOV (rust, cargo llvm-cov --lcov) or Cobertura XML
        (cpp, gcovr --cobertura). Exit 1 if a filled module is below the minimum or has no lines in the report.

    python tools/quality_gate.py --coverage REPORT --lang LANG --floor
        Also gates line coverage over the whole library of that language against
        conformance/quality/floors.json (plan 12.2 G6, the per-language fail_under).

    python tools/quality_gate.py --check-dsr --trials N [--ledger research/trials.csv] [--expect-family 24]
        Research gate (plan 13.1 R6). A deflated Sharpe ratio for an R3 study must be computed with at
        least the family trial count, which is the number of rows in the trial ledger. Exit 1 if N is
        smaller, if the ledger has duplicate trial ids, or if its row count differs from --expect-family.

    python tools/quality_gate.py --check-register --check-specs [--baseline FILE] | --write-baseline
        Model register (plan 12.2 A2): every docs/model-inventory.md entry has the A2 fields, and every
        model spec page has an entry. Convergence rule (Q5b): a spec page with a numerical method has a
        filled "## Convergence and limit cases" table. Ratchets over a baseline; see tools/governance_gate.py.

Entries left as TODO are skipped, so the gate passes before the language sessions land.
"""
import argparse
import csv
import fnmatch
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import governance_gate as gov  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "research" / "trials.csv"
DEFAULT = ROOT / "conformance" / "quality" / "stage_e.json"
LANGS = ("java", "cpp", "python", "rust")


def filled(v):
    if isinstance(v, list):
        return bool(v) and all(filled(x) for x in v)
    return isinstance(v, str) and bool(v.strip()) and not v.startswith("TODO")


def globs(v):
    return v if isinstance(v, list) else [v]


def norm(p):
    p = p.replace("\\", "/")
    root = ROOT.as_posix() + "/"
    return p[len(root):] if p.startswith(root) else p.lstrip("./")


def matches(path, pattern):
    path = norm(path)
    return fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(path, "*/" + pattern.lstrip("*/"))


# ---- config check -------------------------------------------------------------------------------

def check_config(cfg, root=ROOT):
    bad, todo, warn = [], [], []
    members = re.findall(r'"(crates/[^"]+)"', (root / "rust" / "Cargo.toml").read_text(encoding="utf-8")) if (root / "rust" / "Cargo.toml").is_file() else []
    cmake = (root / "cpp26" / "CMakeLists.txt").read_text(encoding="utf-8") if (root / "cpp26" / "CMakeLists.txt").is_file() else ""
    pyproject = (root / "python" / "pyproject.toml").read_text(encoding="utf-8") if (root / "python" / "pyproject.toml").is_file() else ""
    for m in cfg["modules"]:
        for lang in LANGS:
            pat = m.get(lang)
            if not filled(pat):
                todo.append(f"{m['module']}/{lang}")
                continue
            hits = []
            for g in globs(pat):
                found = sorted(p for p in root.glob(g) if p.is_file())
                if not found:
                    bad.append(f"{m['module']}/{lang}: no file matches {g}")
                hits += found
            for h in hits:
                rel = h.relative_to(root).as_posix()
                if lang == "rust" and not any(rel.startswith(f"rust/{c}/") for c in members):
                    bad.append(f"{m['module']}/rust: {rel} is not in a workspace member crate")
                if lang == "cpp" and rel.endswith(".cpp") and rel.removeprefix("cpp26/") not in cmake:  # .inc files are included, not listed
                    bad.append(f"{m['module']}/cpp: {rel} is not listed in cpp26/CMakeLists.txt")
                if lang == "python" and not rel.startswith("python/quantforge_"):
                    bad.append(f"{m['module']}/python: {rel} is outside the python/quantforge_* packages")
                if lang == "python" and rel.startswith("python/") and rel.split("/")[1] + "/" not in pyproject:
                    bad.append(f"{m['module']}/python: package {rel.split('/')[1]} is not in mutmut source_paths")
    for t in cfg.get("python_tests", []):
        if not filled(t):
            todo.append("python_tests")
        elif t.removeprefix("python/") not in pyproject:
            warn.append(f"python test {t} is not in mutmut tests_dir in python/pyproject.toml, so mutation testing does not run it")
        elif not (root / t).is_file():
            bad.append(f"python test {t} does not exist")
    return bad, todo, warn


# ---- coverage reports: (file, covered lines, total lines) ---------------------------------------

def read_coverage_py(text):
    d = json.loads(text)
    return [(f, v["summary"]["covered_lines"], v["summary"]["num_statements"]) for f, v in d["files"].items()]


def read_lcov(text):
    rows, f, hit, total = [], None, 0, 0
    for line in text.splitlines():
        if line.startswith("SF:"):
            f, hit, total = line[3:], 0, 0
        elif line.startswith("DA:"):
            total += 1
            hit += int(line[3:].split(",")[1]) > 0
        elif line == "end_of_record" and f:
            rows.append((f, hit, total))
            f = None
    return rows


def read_jacoco(text):
    rows = []
    for pkg in ET.fromstring(text).iter("package"):
        for sf in pkg.iter("sourcefile"):
            c = next((x for x in sf.findall("counter") if x.get("type") == "LINE"), None)
            if c is not None:
                cov, miss = int(c.get("covered")), int(c.get("missed"))
                rows.append((f"java25/src/main/java/{pkg.get('name')}/{sf.get('name')}", cov, cov + miss))
    return rows


def read_cobertura(text):
    rows = []
    for cls in ET.fromstring(text).iter("class"):
        ls = list(cls.iter("line"))
        rows.append((cls.get("filename"), sum(int(x.get("hits", "0")) > 0 for x in ls), len(ls)))
    return rows


READERS = {"python": read_coverage_py, "java": read_jacoco, "rust": read_lcov, "cpp": read_cobertura}


def gate(cfg, lang, rows):
    """Returns (report lines, failures). Python reports are relative to python/, so paths are tried both ways."""
    out, fails, minimum = [], [], cfg["coverage_min"]
    for m in cfg["modules"]:
        pat = m.get(lang)
        if not filled(pat):
            continue
        sel = [(f, c, t) for f, c, t in rows if any(matches(f, g) or matches("python/" + norm(f), g) for g in globs(pat))]
        cov, tot = sum(r[1] for r in sel), sum(r[2] for r in sel)
        if not tot:
            fails.append(m["module"])
            out.append(f"{m['module']}: no lines for {pat} in the report")
            continue
        ok = cov / tot >= minimum
        out.append(f"{m['module']}: {cov}/{tot} lines, {cov / tot:.1%}{'' if ok else f' (below {minimum:.0%})'}")
        if not ok:
            fails.append(m["module"])
    return out, fails


# ---- research: DSR trial count against the ledger ----------------------------------------------

def read_ledger(path=LEDGER):
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def check_dsr_trials(rows, n_used, expect_family=None):
    """Returns a list of problems; empty means the DSR trial count is acceptable."""
    bad = []
    ids = [r["trial_id"] for r in rows]
    if len(set(ids)) != len(ids):
        bad.append("ledger has duplicate trial ids")
    if expect_family is not None and len(rows) != expect_family:
        bad.append(f"ledger has {len(rows)} trials, expected {expect_family}")
    if n_used < len(rows):
        bad.append(f"DSR computed with {n_used} trials; the ledger has {len(rows)}, so the deflation is too weak")
    return bad


# ---- whole-language floor (plan 12.2 G6) ----------------------------------------------------------

FLOORS = ROOT / "conformance" / "quality" / "floors.json"
LIBRARY = {"python": ("quantforge_*/*.py", "python/quantforge_*/*.py"), "java": ("java25/src/main/java/*",),
           "rust": ("rust/crates/*/src/*",), "cpp": ("cpp26/src/*", "cpp26/include/*")}


def floor_gate(lang, rows, floor):
    """Line coverage over every library file of one language against its floor. Returns (line, ok)."""
    sel = [(f, c, t) for f, c, t in rows if any(matches(f, g) for g in LIBRARY[lang])]
    cov, tot = sum(r[1] for r in sel), sum(r[2] for r in sel)
    if not tot:
        return f"{lang}: no library lines in the report", False
    ok = cov / tot >= floor
    return f"{lang}: library {cov}/{tot} lines, {cov / tot:.1%} against the floor {floor:.0%}{'' if ok else ' (BELOW)'}", ok


def check_governance(register, specs, baseline, now=None):
    """A2 register and Q5b convergence ratchets (tools/governance_gate.py). Returns the exit code."""
    base = json.loads(baseline.read_text(encoding="utf-8")) if baseline.exists() else {}
    now = now or gov.current()
    rc = 0
    for key, on in (("register", register), ("specs", specs)):
        if not on:
            continue
        new, old, stale = gov.ratchet(now[key], base.get(key, []))
        for x in old:
            print("WARN (baseline)", x)
        for x in new:
            print("BAD", x)
        for x in stale:
            print("WARN stale baseline entry, now fixed (rerun --write-baseline to shrink the list):", x)
        print(f"{key}: {len(new)} new gaps, {len(old)} baseline gaps, {len(stale)} stale")
        rc |= bool(new)
    return int(rc)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", default=str(DEFAULT))
    ap.add_argument("--check-config", action="store_true")
    ap.add_argument("--coverage")
    ap.add_argument("--lang", choices=LANGS)
    ap.add_argument("--check-dsr", action="store_true")
    ap.add_argument("--trials", type=int)
    ap.add_argument("--ledger", default=str(LEDGER))
    ap.add_argument("--expect-family", type=int)
    ap.add_argument("--floor", action="store_true", help="also gate whole-language coverage on floors.json")
    ap.add_argument("--check-register", action="store_true")
    ap.add_argument("--check-specs", action="store_true")
    ap.add_argument("--check-docs", action="store_true", help="curve status table and release wording (tools/check_docs_status.py)")
    ap.add_argument("--write-baseline", action="store_true")
    ap.add_argument("--baseline", default=str(gov.BASELINE))
    a = ap.parse_args(argv)
    if a.write_baseline:
        base = gov.current()
        Path(a.baseline).write_text(json.dumps(base, indent=1) + "\n", encoding="utf-8")
        print(f"baseline: {len(base['register'])} register gaps, {len(base['specs'])} spec gaps")
        return 0
    if a.check_docs:
        import check_docs_status
        docs_rc = check_docs_status.main()
        if not (a.check_register or a.check_specs):
            return docs_rc
        return max(docs_rc, check_governance(a.check_register, a.check_specs, Path(a.baseline)))
    if a.check_register or a.check_specs:
        return check_governance(a.check_register, a.check_specs, Path(a.baseline))
    if a.check_dsr:
        if a.trials is None:
            ap.error("--check-dsr needs --trials")
        bad = check_dsr_trials(read_ledger(a.ledger), a.trials, a.expect_family)
        for b in bad:
            print("BAD", b)
        print(f"dsr trial count {a.trials}: {'rejected' if bad else 'ok'}")
        return 1 if bad else 0
    cfg = json.loads(Path(a.config).read_text(encoding="utf-8"))
    if a.check_config:
        bad, todo, warn = check_config(cfg)
        for w in warn:
            print("WARN", w)
        for b in bad:
            print("BAD", b)
        print(f"stage {cfg['stage']}: {len(bad)} broken, {len(todo)} still TODO" + (f" ({', '.join(todo[:12])}{', ...' if len(todo) > 12 else ''})" if todo else ""))
        return 1 if bad else 0
    if not (a.coverage and a.lang):
        ap.error("--coverage needs --lang")
    rows = READERS[a.lang](Path(a.coverage).read_text(encoding="utf-8"))
    floor_ok = True
    if a.floor:
        line, floor_ok = floor_gate(a.lang, rows, json.loads(FLOORS.read_text(encoding="utf-8"))[a.lang])
        print(line)
    out, fails = gate(cfg, a.lang, rows)
    for line in out:
        print(line)
    print(f"{a.lang}: {len(out)} modules gated at {cfg['coverage_min']:.0%}; {len(fails)} below" if out else f"{a.lang}: no filled modules yet, nothing gated")
    return 1 if fails or not floor_ok else 0


if __name__ == "__main__":
    sys.exit(main())
