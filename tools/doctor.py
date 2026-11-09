#!/usr/bin/env python3
"""Checks the local toolchains against the versions the repository pins (CONTRIBUTING.md, plan 13.1 E5).

  python tools/doctor.py [--only python,rust,java,cpp]

Expected versions are read from the repository, not written here: python/.python-version, rust/rust-toolchain.toml,
the java-version in .github/workflows/java25.yml, cmake_minimum_required in cpp26/CMakeLists.txt and the GCC image
tag in .github/workflows/cpp26.yml. Exit 0 when everything asked for is present at the right version; otherwise exit 1
with one line per problem. Standard library only.
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def expected(root=ROOT):
    read = lambda p: (root / p).read_text(encoding="utf-8")
    return {
        "python": read("python/.python-version").strip(),
        "rust": re.search(r'channel\s*=\s*"([^"]+)"', read("rust/rust-toolchain.toml")).group(1),
        "java": re.search(r'java-version:\s*"([^"]+)"', read(".github/workflows/java25.yml")).group(1),
        "cmake": re.search(r"cmake_minimum_required\(VERSION ([\d.]+)\)", read("cpp26/CMakeLists.txt")).group(1),
        "gcc": re.search(r"container: gcc:([\d.]+)", read(".github/workflows/cpp26.yml")).group(1),
        "clang": "23",
    }


def run(cmd, cwd=ROOT):
    """Combined stdout and stderr, or None when the tool is missing."""
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return (p.stdout + p.stderr) if p.returncode == 0 else None


def version_of(text, pattern=r"(\d+(?:\.\d+)+)"):
    m = re.search(pattern, text or "")
    return m.group(1) if m else None


def at_least(have, want):
    t = lambda v: tuple(int(x) for x in v.split("."))
    return have is not None and t(have)[:len(t(want))] >= t(want)


def checks(exp, runner=run):
    """[(language, tool, ok, detail)]"""
    out = []

    def add(lang, tool, ok, detail):
        out.append((lang, tool, ok, detail))

    uv = version_of(runner(["uv", "--version"]))
    add("python", "uv", uv is not None, uv or "not found: install uv from https://docs.astral.sh/uv/")
    py = runner(["uv", "python", "find", exp["python"]]) if uv else None
    add("python", f"Python {exp['python']}", py is not None,
        py.strip().splitlines()[-1] if py else f"not found: uv python install {exp['python']}")

    rc = version_of(runner(["rustc", "--version"], cwd=ROOT / "rust"))
    add("rust", f"rustc {exp['rust']}", rc == exp["rust"],
        rc and f"found {rc}" or "not found: install rustup; it reads rust/rust-toolchain.toml")

    jv = version_of(runner(["java", "-version"]), r'version "([\d.]+)"')
    add("java", f"JDK {exp['java']}", jv is not None and jv.split(".")[0] == exp["java"].split(".")[0],
        f"found {jv}" + ("" if jv == exp["java"] else f" (CI uses {exp['java']})") if jv else "not found: install Temurin JDK 25")
    mvn = version_of(runner(["mvn", "-v"]), r"Apache Maven ([\d.]+)")
    add("java", "Maven", mvn is not None, f"found {mvn}" if mvn else "not found: install Apache Maven 3.9 or later")

    cm = version_of(runner(["cmake", "--version"]))
    add("cpp", f"CMake >= {exp['cmake']}", at_least(cm, exp["cmake"]), f"found {cm}" if cm else "not found")
    nj = version_of(runner(["ninja", "--version"]))
    add("cpp", "Ninja", nj is not None, f"found {nj}" if nj else "not found")
    gcc = version_of(runner(["g++", "-dumpfullversion"]))
    clang = version_of(runner(["clang++", "--version"]), r"clang version ([\d.]+)")
    ok = at_least(gcc, exp["gcc"].split(".")[0]) or at_least(clang, exp["clang"])
    add("cpp", f"GCC >= {exp['gcc'].split('.')[0]} or Clang >= {exp['clang']}", ok,
        f"g++ {gcc or 'missing'}, clang++ {clang or 'missing'}")
    return out


def main(argv=None, runner=run):
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="python,rust,java,cpp")
    a = ap.parse_args(argv)
    want = set(a.only.split(","))
    rows = [r for r in checks(expected(), runner) if r[0] in want]
    for lang, tool, ok, detail in rows:
        print(f"{'ok  ' if ok else 'FAIL'} {lang:<7} {tool:<28} {detail}")
    bad = [r for r in rows if not r[2]]
    if bad:
        print(f"\n{len(bad)} problem(s): " + "; ".join(f"{r[0]}: {r[1]}" for r in bad), file=sys.stderr)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
