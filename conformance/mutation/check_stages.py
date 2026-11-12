#!/usr/bin/env python3
"""Check conformance/mutation/stages.json against the tree (R6-14, review finding 5). Standard library only.

Fails if a stage the library ships (A to I, from datasets/golden and the stage list below) has no modules,
if a module target matches no source file, or if a suite glob matches no golden file. A gate that mutates
nothing must fail loudly: plan_matrix.py --stage F returned an empty matrix at v0.8.0 and the run passed.

    python conformance/mutation/check_stages.py
"""
import fnmatch
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
from plan_matrix import LANGS, target_glob  # noqa: E402

REQUIRED_STAGES = ("A", "D", "E", "F", "G", "I")


def files_under(prefix):
    base = ROOT / prefix
    return [p.relative_to(ROOT).as_posix() for p in base.rglob("*") if p.is_file()] if base.is_dir() else []


def problems(cfg):
    out = []
    src = files_under("cpp26/src") + files_under("java25/src/main") + files_under("python/quantforge_core") + files_under("rust/crates")
    goldens = [p.stem for p in (ROOT / "datasets" / "golden").rglob("*.json")]
    for st in REQUIRED_STAGES:
        mods = cfg["stages"].get(st) or []
        if not mods:
            out.append(f"stage {st}: no modules")
        if st not in cfg.get("target", {}):
            out.append(f"stage {st}: no target")
    for st, mods in cfg["stages"].items():
        for m in mods:
            for lang in LANGS:
                t = m.get(lang)
                if not t:
                    continue
                g = target_glob(lang, t)
                if lang == "python":  # a mutmut name glob: quantforge_core.credit.* covers credit.py
                    g = "python/" + t.rstrip("*").rstrip(".").replace(".", "/") + "*"
                if not any(fnmatch.fnmatch(f, g) or fnmatch.fnmatch(f, "*/" + g.lstrip("*/")) for f in src):
                    out.append(f"stage {st} module {m['module']} {lang}: target {t!r} matches no file")
            for key in [k for k in m if k == "suite" or k.endswith("_suite")]:
                if not any(fnmatch.fnmatch(s, m[key]) for s in goldens):
                    out.append(f"stage {st} module {m['module']}: {key} {m[key]!r} matches no golden file")
    return out


def main(argv=None):
    path = Path(argv[0]) if argv else HERE / "stages.json"
    cfg = json.loads(path.read_text(encoding="utf-8"))
    bad = problems(cfg)
    for b in bad:
        print("error:", b)
    print(f"{len(bad)} problem(s) in {path.name}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
