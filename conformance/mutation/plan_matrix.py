#!/usr/bin/env python3
"""Job matrix for mutation-stage.yml (plan 12.2 G6, 13.2 E10). Standard library only.

    plan_matrix.py --stage F                       every module of one stage (the weekly and manual full run)
    plan_matrix.py --changed changed.txt           PR mode: only modules, from any stage, whose target file is
                                                   in the list of changed paths (one per line)

Writes `matrix=<json>` and `any=true|false` lines for $GITHUB_OUTPUT on stdout. With --stages-out FILE it also
writes a stages.json holding just the selected modules under the stage name "PR" (target 80%), so
stage_report.py --stage PR --gate scores exactly what ran.
"""
import argparse
import fnmatch
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LANGS = ("java", "cpp", "python", "rust")
PR_TARGET = 0.8


def target_glob(lang, target):
    """The repository path glob a module target covers."""
    if lang == "java":  # class name or class glob
        return "java25/src/main/java/" + target.replace(".", "/") + ("" if target.endswith("*") else ".java")
    if lang == "python":  # dotted mutant glob, e.g. quantforge_core.vol_e1*
        return "python/" + target.replace(".", "/") + ("" if target.endswith("*") else ".py")
    if lang == "rust":
        return "rust/" + target.lstrip("/") if not target.startswith(("rust/", "**")) else target
    return target  # cpp: a path


def touched(lang, target, changed):
    g = target_glob(lang, target)
    return any(fnmatch.fnmatch(c, g) or fnmatch.fnmatch(c, "*/" + g.lstrip("*/")) for c in changed)


def entries(mods, langs_filter=None):
    return [{"lang": l, "module": m["module"], "target": m[l], "suite": m.get(l + "_suite", m["suite"])}
            for m in mods for l in LANGS if m.get(l) and (langs_filter is None or (m["module"], l) in langs_filter)]


def plan(cfg, stage=None, changed=None):
    """(matrix include list, stages.json fragment for the report)."""
    if changed is None:
        mods = cfg["stages"].get(stage, [])
        return entries(mods), None
    picked, sel, seen = [], set(), set()
    for st, mods in cfg["stages"].items():
        for m in mods:
            if m["module"] in seen:
                continue
            hit = {(m["module"], l) for l in LANGS if m.get(l) and touched(l, m[l], changed)}
            if hit:
                seen.add(m["module"])
                sel |= hit
                picked.append({k: v for k, v in m.items() if k not in LANGS or (m["module"], k) in hit})
    return entries(picked, sel), {"target": {"PR": PR_TARGET}, "stages": {"PR": picked}}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--stages", default=str(HERE / "stages.json"))
    ap.add_argument("--stage")
    ap.add_argument("--changed")
    ap.add_argument("--stages-out")
    a = ap.parse_args(argv)
    cfg = json.loads(Path(a.stages).read_text(encoding="utf-8"))
    changed = None
    if a.changed:
        changed = [x.strip() for x in Path(a.changed).read_text(encoding="utf-8").splitlines() if x.strip()]
    inc, frag = plan(cfg, a.stage, changed)
    if a.stages_out and frag is not None:
        Path(a.stages_out).write_text(json.dumps(frag, indent=1), encoding="utf-8")
    print("matrix=" + json.dumps({"include": inc}))
    print("any=" + ("true" if inc else "false"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
