#!/usr/bin/env python3
"""The version string is the same in the four builds, their lock files and the site facts (K-7 release runbook).

    python tools/check_versions.py                  print each file's version; exit 1 if they differ
    python tools/check_versions.py --expect 1.0.0   also exit 1 unless every file says 1.0.0 (the release job runs this)
    python tools/check_versions.py --self-test      planted faults must fail

Plain idea: a tag names one version, so every artefact built from it must say that version. The places that hold it
were found by `git grep` for the previous version at the v0.10.0 bump (commit 2f4e51e4) and on main at 0.10.1.
Standard library only.
"""
import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# (file, regex whose group 1 is the version, how many matches the file must have)
PLACES = (
    ("python/pyproject.toml", r'(?m)^version = "([^"]+)"', 1),
    ("python/quantforge_core/__init__.py", r'__version__ = "([^"]+)"', 1),
    ("python/uv.lock", r'(?m)^name = "quantforge-core"\nversion = "([^"]+)"', 1),
    ("rust/Cargo.toml", r'(?m)^version = "([^"]+)"', 1),
    ("rust/Cargo.lock", r'(?m)^name = "quantforge[a-z-]*"\nversion = "([^"]+)"', None),
    ("java25/pom.xml", r"<artifactId>quantforge</artifactId><version>([^<]+)</version>", 1),
    ("java25/src/main/java/org/quantforge/cli/Main.java", r'String VERSION = "([^"]+)"', 1),
    ("cpp26/CMakeLists.txt", r"project\(quantforge_cpp26 VERSION ([0-9.]+)", 1),
    ("tools/site_facts.json", r'"version": "([^"]+)"', 1),
)


def found(root=ROOT):
    out = {}
    for rel, rx, n in PLACES:
        text = (root / rel).read_text(encoding="utf-8")
        hits = re.findall(rx, text)
        out[rel] = (hits, n)
    return out


def problems(versions, expect=None):
    out, seen = [], set()
    for rel, (hits, n) in versions.items():
        if not hits or (n is not None and len(hits) != n):
            out.append(f"{rel}: expected {n or 'at least 1'} version line(s), found {len(hits)}")
        seen.update(hits)
        if expect and any(h != expect for h in hits):
            out.append(f"{rel}: {', '.join(sorted(set(hits)))}, not {expect}")
    if len(seen) > 1:
        out.append(f"the files disagree: {', '.join(sorted(seen))}")
    return out


def self_test():
    good = {rel: (["1.0.0"], n) if n else (["1.0.0", "1.0.0"], n) for rel, _, n in PLACES}
    planted = {"one file behind": {**good, "java25/pom.xml": (["0.10.1"], 1)},
               "a file with no version line": {**good, "cpp26/CMakeLists.txt": ([], 1)},
               "the Java CLI constant behind": {**good, "java25/src/main/java/org/quantforge/cli/Main.java": (["0.10.1"], 1)},
               "a lock entry not bumped": {**good, "rust/Cargo.lock": (["1.0.0", "0.10.1"], None)}}
    bad = [k for k, v in planted.items() if not problems(v, "1.0.0")]
    wrong_tag = not problems(good, "1.0.1")
    if problems(good, "1.0.0") or bad or wrong_tag:
        print(f"self-test FAILED: {problems(good, '1.0.0')}, not caught: {bad}, wrong tag passed: {wrong_tag}", file=sys.stderr)
        return 1
    print(f"self-test: consistent files pass and {len(planted) + 1} planted faults fail")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--expect")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)
    if a.self_test:
        return self_test()
    v = found()
    for rel, (hits, _) in v.items():
        print(f"{rel}: {', '.join(hits) or 'none'}")
    p = problems(v, a.expect)
    for x in p:
        print(f"versions: {x}", file=sys.stderr)
    return 1 if p else 0


if __name__ == "__main__":
    sys.exit(main())
