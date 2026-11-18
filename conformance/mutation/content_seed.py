"""Print a sample seed derived from the content of the mutated source file(s).

Pull-request runs used the run number as the seed, so every push or re-run drew a fresh 40-mutant
sample: the same code could pass on one run and fail on the next, and a kill round fixed only the
draw it was written against (stage J and PR #50, 9 of 10 code-touching runs red). Seeding from the
source content makes the verdict a function of the code: the same source gives the same sample, a
re-run cannot fish for a luckier draw, and adding tests does not move the sample. The weekly sweep
keeps a fresh seed (the run number), so no sample is frozen for long (owner decision 2026-11-18).

Usage: content_seed.py --lang cpp|rust|python|java --target TARGET
"""
import argparse
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def files(lang, target, root=ROOT):
    if lang == "cpp":
        return [root / target]
    if lang == "rust":
        return sorted((root / "rust").glob(target))
    if lang == "python":  # mutmut target such as quantforge_core.shortrate*
        mod = target.split(".", 1)[1] if "." in target else target
        return sorted((root / "python" / "quantforge_core").glob(mod.replace(".", "/") + ".py"))
    return []  # java: PIT mutates every class in the target, no sample


def seed(lang, target, root=ROOT):
    h = hashlib.sha256()
    for f in files(lang, target, root):
        h.update(f.relative_to(root).as_posix().encode())
        h.update(f.read_bytes().replace(b"\r\n", b"\n"))
    return int(h.hexdigest()[:8], 16)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", required=True)
    ap.add_argument("--target", required=True)
    a = ap.parse_args(argv)
    print(seed(a.lang, a.target))


if __name__ == "__main__":
    main()
