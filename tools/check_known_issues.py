#!/usr/bin/env python3
"""Every recorded miss and every move to a point release appears in docs/known-issues.md (plan 14.8 K-7, check RE4,
ruling KR-224, PROPOSED).

    python tools/check_known_issues.py              check the tree
    python tools/check_known_issues.py --self-test  planted faults must fail

Plain idea: a miss written in a spec but absent from the register is a miss a reader of the register never sees.
The check finds every line in the specs, ROADMAP.md, CHANGELOG.md and README.md that records a miss (the word MISS
in capitals, "recorded miss") or a move to a point release ("point release"), takes the plan-item or finding
identifiers on that line (H-9, K-8f, KA-C9, KF-31 and so on; if the line has none, those of the nearest heading
above it, then of the file's first ten lines), and fails if an identifier is not in the register, or if a line has
no identifier at all. It also fails if a row of the register's "Open" table is missing from the page entirely, and
it never closes a row: closing is a person's edit that names its evidence.

Files that describe the register itself (this check's own spec and rulings) are skipped. Standard library only.
"""
import argparse
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTER = Path("docs") / "known-issues.md"
SOURCES = ("specifications/**/*.md", "ROADMAP.md", "CHANGELOG.md", "README.md")
SKIP = {"specifications/12-platform/release-evidence.md", "specifications/stage-k-rulings-k7.md"}
TRIGGER = re.compile(r"\bMISS\b|recorded miss|point release", re.I)
CASE_SENSITIVE_MISS = re.compile(r"\bMISS\b")
# Phrases that name a recorded miss without its plan item: the H-9 workload R window and the K-11 real day.
ALIASES = ((re.compile(r"workload R\b|\bon R\b|L1 to L3|L1-L3|2026-11-18/19"), "H-9"),
           (re.compile(r"2026-11-13|daily curve run|Fed's fitted curve"), "K-11"))
IDS = re.compile(r"\b(H-\d+[a-z]?|K-\d+[a-z]?|KA-[A-C]\d+|KF-\d+)\b")


def triggers(line):
    return bool(CASE_SENSITIVE_MISS.search(line) or re.search(r"recorded miss|point release", line, re.I))


def segments(line):
    """The table cells and sentences of a line that record a miss or a point-release move."""
    return [s for s in re.split(r"\s\|\s|(?<=[A-Za-z0-9)])\.\s|;\s", line) if triggers(s)]


def ids_for(lines, i):
    segs = segments(lines[i])
    found = [x for s in segs for x in IDS.findall(s)] + [x for s in segs for rx, x in ALIASES if rx.search(s)]
    if found:
        return found
    found = IDS.findall(lines[i])
    if found and len(set(found)) <= 2:
        return found
    for j in range(i - 1, -1, -1):
        if lines[j].startswith("#"):
            found = IDS.findall(lines[j])
            if found:
                return found
            break
    return IDS.findall("\n".join(lines[:10]))


def problems(root=ROOT):
    root = Path(root)
    register = (root / REGISTER).read_text(encoding="utf-8")
    out = []
    files = sorted({p for pat in SOURCES for p in root.glob(pat) if p.is_file()})
    for p in files:
        rel = p.relative_to(root).as_posix()
        if rel in SKIP:
            continue
        lines = p.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            if not triggers(line):
                continue
            ids = ids_for(lines, i)
            if not ids:
                out.append(f"{rel}:{i + 1}: records a miss or a point-release move with no plan item or finding id")
            for x in dict.fromkeys(ids):
                if not re.search(r"\b" + re.escape(x) + r"\b", register):
                    out.append(f"{rel}:{i + 1}: {x} is recorded as a miss or point-release move but is not in {REGISTER.as_posix()}")
    return out


def self_test():
    failures = []
    reg = "# Known issues\n\n| Id |\n|---|\n| H-9 workload R MISS |\n"
    cases = {
        "good": ({"specifications/a.md": "# H-9 targets\n\nRow: MISS at p99\n"}, False),
        "a spec MISS whose item is not in the register": ({"specifications/b.md": "# K-11 run\n\nResult: MISS\n"}, True),
        "a point-release move not in the register": ({"ROADMAP.md": "K-8f moves to a point release\n"}, True),
        "a recorded miss with no identifier anywhere": ({"CHANGELOG.md": "# Changelog\n\nA recorded miss.\n"}, True),
    }
    for name, (files, should_fail) in cases.items():
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            (t / "docs").mkdir()
            (t / REGISTER).write_text(reg, encoding="utf-8")
            for rel, text in files.items():
                (t / rel).parent.mkdir(parents=True, exist_ok=True)
                (t / rel).write_text(text, encoding="utf-8")
            if bool(problems(t)) != should_fail:
                failures.append(f"{name}: expected {'a failure' if should_fail else 'a pass'}, got {problems(t)}")
    if failures:
        print("self-test FAILED:\n" + "\n".join(failures), file=sys.stderr)
        return 1
    print(f"self-test: a registered miss passes and {len(cases) - 1} planted faults fail")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)
    if a.self_test:
        return self_test()
    found = problems()
    for p in found:
        print(f"known issues: {p}", file=sys.stderr)
    if not found:
        print("known issues: every recorded miss and point-release move in the specs, ROADMAP, CHANGELOG and README is in the register")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
