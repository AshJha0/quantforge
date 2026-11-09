#!/usr/bin/env python3
"""Repository hygiene gate (plan 13.2 E11). Standard library only.

    python tools/check_hygiene.py

Fails (exit 1) when
  * a tracked file is over 1 MB (1 048 576 bytes) and is not in tools/large_files_allow.txt;
  * an allow-list entry names a file that is no longer tracked or is now under the limit (stale entry);
  * a tracked directory under a language source root holds nothing but placeholders (.gitkeep,
    an empty __init__.py), which is an empty placeholder package.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOW = ROOT / "tools" / "large_files_allow.txt"
LIMIT = 1 << 20
SOURCE_ROOTS = ("cpp26/include/", "cpp26/src/", "java25/src/", "python/", "rust/crates/")
PLACEHOLDERS = {".gitkeep", ".keep", "__init__.py"}


def tracked(root=ROOT):
    out = subprocess.run(["git", "ls-files", "-z"], cwd=root, check=True, capture_output=True).stdout
    return [p for p in out.decode("utf-8").split("\0") if p]


def read_allow(path=ALLOW):
    if not path.exists():
        return {}
    allow = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            allow[line] = True
    return allow


def large_files(files, sizes, allow):
    """Returns problems for files over LIMIT that are not allow-listed, and stale allow-list entries."""
    bad = [f"{f}: {sizes[f]} bytes is over 1 MB and not in {ALLOW.relative_to(ROOT).as_posix()}"
           for f in files if sizes[f] > LIMIT and f not in allow]
    for f in allow:
        if f not in sizes:
            bad.append(f"allow-list entry {f} is not a tracked file")
        elif sizes[f] <= LIMIT:
            bad.append(f"allow-list entry {f} is {sizes[f]} bytes, under 1 MB: remove the entry")
    return bad


def empty_packages(files, sizes):
    """A directory under a source root whose tracked files are all placeholders (an __init__.py only if empty)."""
    dirs = {}
    for f in files:
        if f.startswith(SOURCE_ROOTS):
            d, _, name = f.rpartition("/")
            dirs.setdefault(d, []).append((name, sizes[f]))
    bad = []
    for d, entries in sorted(dirs.items()):
        if all(n in PLACEHOLDERS and (n != "__init__.py" or s == 0) for n, s in entries):
            if not any(o.startswith(d + "/") for o in dirs if o != d):
                bad.append(f"{d}/: empty placeholder package ({', '.join(n for n, _ in entries)})")
    return bad


def main():
    files = tracked()
    sizes = {f: (ROOT / f).stat().st_size for f in files if (ROOT / f).is_file()}
    files = [f for f in files if f in sizes]
    bad = large_files(files, sizes, read_allow()) + empty_packages(files, sizes)
    for b in bad:
        print("BAD", b)
    print(f"hygiene: {len(files)} tracked files, {len(bad)} problems")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
