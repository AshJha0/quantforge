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

Entries left as TODO are skipped, so the gate passes before the language sessions land.
"""
import argparse
import fnmatch
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
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


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", default=str(DEFAULT))
    ap.add_argument("--check-config", action="store_true")
    ap.add_argument("--coverage")
    ap.add_argument("--lang", choices=LANGS)
    a = ap.parse_args(argv)
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
    out, fails = gate(cfg, a.lang, READERS[a.lang](Path(a.coverage).read_text(encoding="utf-8")))
    for line in out:
        print(line)
    print(f"{a.lang}: {len(out)} modules gated at {cfg['coverage_min']:.0%}; {len(fails)} below" if out else f"{a.lang}: no filled modules yet, nothing gated")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
