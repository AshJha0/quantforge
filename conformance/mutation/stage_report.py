#!/usr/bin/env python3
"""Per-stage mutation report (plan 11.5.6). Standard library only.

Reads one result file per (language, module) from a folder, as written by the per-language tools:
  <lang>--<module>.json   golden_mutants.py --out (python, rust) or cpp_mutants.py --out (cpp)
  java--<module>.xml      PIT's mutations.xml

  stage_report.py --stage D --results DIR [--out REPORT.md] [--gate]

Score = killed / (killed + survived). Unviable, non-building and not-sampled mutants are left out,
and timeouts count as killed, matching golden_mutants.py. Python and Rust count a sampled mutant killed if the
unit tests or the golden cases catch it. A module scores its own languages separately; the stage figure
pools every mutant. --gate exits 1 if a mapped result is missing, or if the pooled score, or any module-language score with at least 10
mutants, is below the stage target in stages.json.
"""
import argparse
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
LANGS = ("java", "cpp", "python", "rust")
MIN_FOR_GATE = 10


def score_file(lang, path):
    """Returns (killed, survived, note)."""
    if lang == "java":
        muts = ET.parse(path).getroot().findall("mutation")
        status = [m.get("status") for m in muts]
        killed = sum(s in ("KILLED", "TIMED_OUT", "MEMORY_ERROR") for s in status)
        survived = sum(s in ("SURVIVED", "NO_COVERAGE") for s in status)
        return killed, survived, f"PIT, {len(muts)} mutants, {status.count('NO_COVERAGE')} without coverage"
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    s = d["summary"]
    if lang == "cpp":
        return s["killed"], s["survived"], f"golden only, {s['killed'] + s['survived'] + s['no_build']} of {s['sites']} sites, {s['no_build']} did not build"
    return (s["sample_either_killed"], s["sampled"] - s["sample_either_killed"],
            f"unit or golden, sample {s['sampled']} of {s['mutants']}; unit-only {s['sample_unit_killed']}, golden-only {s['sample_golden_killed']}")


def pct(k, s):
    return f"{100 * k / (k + s):.1f}%" if k + s else "-"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="D")
    ap.add_argument("--results", required=True)
    ap.add_argument("--stages", default=str(HERE / "stages.json"))
    ap.add_argument("--out")
    ap.add_argument("--gate", action="store_true")
    a = ap.parse_args()
    cfg = json.loads(Path(a.stages).read_text(encoding="utf-8"))
    target = cfg["target"].get(a.stage)
    res = Path(a.results)
    rows, tk, ts, below, missing = [], 0, 0, [], []
    for m in cfg["stages"][a.stage]:
        for lang in LANGS:
            if not m.get(lang):
                rows.append([m["module"], lang, "not mapped", "", "", "no module for this language in stages.json"])
                continue
            f = res / f"{lang}--{m['module']}.{'xml' if lang == 'java' else 'json'}"
            if not f.is_file():
                missing.append(f.name)
                rows.append([m["module"], lang, "no result", "", "", f"`{m[lang]}`"])
                continue
            k, s, note = score_file(lang, f)
            tk, ts = tk + k, ts + s
            flag = ""
            if target is not None and k + s >= MIN_FOR_GATE and k / (k + s) < target:
                below.append(f"{lang} {m['module']}")
                flag = " (below target)"
            rows.append([m["module"], lang, pct(k, s) + flag, k, s, note])
    lines = [f"# Mutation report, stage {a.stage}", "",
             f"Target: {target:.0%} per module and language with at least {MIN_FOR_GATE} scored mutants, and pooled." if target is not None else "No target set.",
             f"Pooled: **{pct(tk, ts)}** ({tk} killed, {ts} survived). Below target: {', '.join(below) or 'none'}. "
             f"Missing results: {len(missing)}.", "",
             "Survivors have not been sorted into equivalent mutants and real gaps, so the score is a lower bound on test strength.", "",
             "| Module | Language | Score | Killed | Survived | Basis |", "|---|---|---|---:|---:|---|"]
    lines += ["| " + " | ".join(str(x) for x in r) + " |" for r in rows]
    text = "\n".join(lines) + "\n"
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
    print(text)
    if a.gate and target is not None and (below or missing or not tk + ts or tk / (tk + ts) < target):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
