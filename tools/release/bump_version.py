#!/usr/bin/env python3
"""Set the build version string in every file that carries it (K-10 close-out), and nothing else.

    python tools/release/bump_version.py --to 1.0.0 --check    show each edit; write nothing; exit 1 if a place is missing
    python tools/release/bump_version.py --to 1.0.0            apply the edits, then verify with tools/check_versions.py
    python tools/release/bump_version.py --self-test           apply to a temporary copy; planted faults must fail

Plain idea: a tag names one version, so every artefact built from it must say that version. The places are the
eight of `tools/check_versions.py` (the release job's gate) plus the Java CLI's own `VERSION` constant, which
`check_versions.py` does not read (found 2026-11-22: it said 0.10.0 while java25/pom.xml said 0.10.1). The CLI
contract number (1.17.0) is a different number and is never touched: every edited file must hold the same count of
"1.17.0" before and after, and 1.17.0 is refused as a target. The full list with line numbers is
program/stage_k_k10/VERSION_BUMP.md. Standard library only.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = "1.17.0"  # the CLI contract number; never edited by this script
SEMVER = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")
# (file, regex whose group 1 is the version, how many matches the file must have; None = at least one)
PLACES: tuple[tuple[str, str, int | None], ...] = (
    ("python/pyproject.toml", r'(?m)^version = "([^"]+)"', 1),
    ("python/quantforge_core/__init__.py", r'__version__ = "([^"]+)"', 1),
    ("python/uv.lock", r'(?m)^name = "quantforge-core"\nversion = "([^"]+)"', 1),
    ("rust/Cargo.toml", r'(?m)^version = "([^"]+)"', 1),
    ("rust/Cargo.lock", r'(?m)^name = "quantforge[a-z-]*"\nversion = "([^"]+)"', None),
    (
        "java25/pom.xml",
        r"<artifactId>quantforge</artifactId><version>([^<]+)</version>",
        1,
    ),
    (
        "java25/src/main/java/org/quantforge/cli/Main.java",
        r'String VERSION = "([^"]+)";',
        1,
    ),
    ("cpp26/CMakeLists.txt", r"project\(quantforge_cpp26 VERSION ([0-9.]+)", 1),
    ("tools/site_facts.json", r'"version": "([^"]+)"', 1),
)


def plan(root: Path, to: str) -> tuple[dict[str, str], list[str]]:
    """New text per file that changes, and the problems found (a missing or extra version line)."""
    new, problems = {}, []
    for rel, rx, n in PLACES:
        text = (root / rel).read_text(encoding="utf-8")
        hits = list(re.finditer(rx, text))
        if not hits or (n is not None and len(hits) != n):
            problems.append(
                f"{rel}: expected {n or 'at least 1'} version line(s), found {len(hits)}"
            )
            continue
        out, last = [], 0
        for m in hits:
            out += [text[last : m.start(1)], to]
            last = m.end(1)
        out.append(text[last:])
        changed = "".join(out)
        if changed.count(CONTRACT) != text.count(CONTRACT):
            problems.append(
                f"{rel}: the edit would change the contract number {CONTRACT}"
            )
        elif changed != text:
            new[rel] = changed
    return new, problems


def edits(root: Path, to: str) -> list[str]:
    lines = []
    for rel, rx, _ in PLACES:
        text = (root / rel).read_text(encoding="utf-8")
        for m in re.finditer(rx, text):
            line = text.count("\n", 0, m.start(1)) + 1
            lines.append(f"{rel}:{line}: {m.group(1)} -> {to}")
    return lines


def apply(root: Path, to: str) -> list[str]:
    if not SEMVER.fullmatch(to) or to == CONTRACT:
        return [
            f"refused target {to!r}: not MAJOR.MINOR.PATCH, or it is the contract number {CONTRACT}"
        ]
    new, problems = plan(root, to)
    if problems:
        return problems
    for rel, text in new.items():
        (root / rel).write_text(text, encoding="utf-8", newline="")
    return verify(root, to)


def verify(root: Path, to: str) -> list[str]:
    out = []
    for rel, rx, _ in PLACES:
        hits = re.findall(rx, (root / rel).read_text(encoding="utf-8"))
        if any(h != to for h in hits) or not hits:
            out.append(f"{rel}: {', '.join(sorted(set(hits))) or 'none'}, not {to}")
    return out


def self_test() -> int:
    fails = []
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        for rel, _, _ in PLACES:
            (t / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / rel, t / rel)
        before = {
            rel: (t / rel).read_text(encoding="utf-8").count(CONTRACT)
            for rel, _, _ in PLACES
        }
        if p := apply(t, "1.0.0"):
            fails.append(f"bump to 1.0.0 failed: {p}")
        if plan(t, "1.0.0")[0]:
            fails.append("a second bump to the same version still changes files")
        after = {
            rel: (t / rel).read_text(encoding="utf-8").count(CONTRACT)
            for rel, _, _ in PLACES
        }
        if before != after:
            fails.append("the contract number count changed")
        if not apply(t, CONTRACT):
            fails.append(f"target {CONTRACT} was accepted")
        if not apply(t, "1.0"):
            fails.append("target 1.0 was accepted")
        main_java = t / PLACES[6][0]
        main_java.write_text(
            main_java.read_text(encoding="utf-8").replace(
                "String VERSION", "String VERS"
            ),
            encoding="utf-8",
        )
        if not plan(t, "1.0.1")[1]:
            fails.append("a file with its version line removed was not caught")
        cmake = t / "cpp26/CMakeLists.txt"
        cmake.write_text(
            cmake.read_text(encoding="utf-8").replace("VERSION 1.0.0", "VERSION 0.9.9"),
            encoding="utf-8",
        )
        if not verify(t, "1.0.0"):
            fails.append("a file left behind was not caught by verify")
    if fails:
        print("self-test FAILED: " + "; ".join(fails), file=sys.stderr)
        return 1
    print(
        "self-test: bump on a copy passes and is idempotent, contract count unchanged, 4 planted faults fail"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--to", help="the new version, MAJOR.MINOR.PATCH")
    ap.add_argument(
        "--check", action="store_true", help="print the edits and write nothing"
    )
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args(argv)
    if a.self_test:
        return self_test()
    if not a.to:
        ap.error("--to is required")
    if a.check:
        for line in edits(ROOT, a.to):
            print(line)
        _, problems = plan(ROOT, a.to)
    else:
        problems = apply(ROOT, a.to)
        if not problems:
            gate = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools/check_versions.py"),
                    "--expect",
                    a.to,
                ],
                check=False,
            )
            problems = ["tools/check_versions.py failed"] if gate.returncode else []
    for p in problems:
        print(f"bump_version: {p}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
