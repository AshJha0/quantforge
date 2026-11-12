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
# R6-14 acceptance: no module-language with a lower 95% Wilson bound under 65% or a point estimate under 80%,
# unless conformance/mutation/reasons.json lists it with a reason and a second reviewer.
LOWER_BOUND = 0.65
Z95 = 1.959963984540054


def wilson(k, n, z=Z95):
    """95% Wilson score interval for k successes out of n."""
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return (max(0.0, c - h), min(1.0, c + h))


def load_reasons(path):
    """{(lang, module): reason} for countersigned exceptions; an entry without a second reviewer does not count."""
    path = Path(path)
    if not path.is_file():
        return {}
    out = {}
    for r in json.loads(path.read_text(encoding="utf-8")).get("exceptions", []):
        if r.get("second_reviewer"):
            out[(r["lang"], r["module"])] = r["reason"]
    return out


SUMMED = ("mutants", "unviable", "unit_killed_all", "sampled", "sample_unit_killed", "sample_golden_killed",
          "sample_either_killed", "sample_golden_timeouts")


def shard_files(path):
    """<lang>--<module>.json, or its shards <lang>--<module>--s<K>.json (Rust, see plan_matrix.py)."""
    path = Path(path)
    return [path] if path.is_file() else sorted(path.parent.glob(path.stem + "--s*" + path.suffix))


def merged_summary(path):
    """One summary from the module file or its shards. Each shard lists every mutant, so `mutants` is not summed."""
    parts = [json.loads(f.read_text(encoding="utf-8"))["summary"] for f in shard_files(path)]
    if len(parts) == 1:
        return parts[0]
    s = {k: sum(p.get(k, 0) for p in parts) for k in SUMMED}
    s["mutants"] = parts[0]["mutants"]
    verdicts = {}
    for p in parts:
        for k, v in p.get("unit_verdicts", {}).items():
            if k != "not run":
                verdicts[k] = verdicts.get(k, 0) + v
    s["unit_verdicts"] = verdicts
    return s


def score_file(lang, path):
    """Returns (killed, survived, note)."""
    if lang == "java":
        muts = ET.parse(path).getroot().findall("mutation")
        status = [m.get("status") for m in muts]
        killed = sum(s in ("KILLED", "TIMED_OUT", "MEMORY_ERROR") for s in status)
        survived = sum(s in ("SURVIVED", "NO_COVERAGE") for s in status)
        return killed, survived, f"PIT, {len(muts)} mutants, {status.count('NO_COVERAGE')} without coverage"
    s = merged_summary(path)
    if lang == "cpp":
        basis = (f"unit or golden, golden {s.get('golden_killed', s['killed'])}, unit {s['unit_killed']}" if s.get("unit")
                 else "golden only")
        return s["killed"], s["survived"], (f"{basis}, {s['killed'] + s['survived'] + s['no_build']} of {s['sites']} sites, "
                                            f"{s['no_build']} did not build, {s.get('timed_out', 0)} timed out")
    note = ""
    if set(s.get("unit_verdicts", {})) == {"mutmut code 33"}:
        note = "; NO unit tests mapped (mutmut 33 on every mutant): golden only"
    return (s["sample_either_killed"], s["sampled"] - s["sample_either_killed"],
            f"unit or golden, sample {s['sampled']} of {s['mutants']}; unit-only {s['sample_unit_killed']}, golden-only {s['sample_golden_killed']}{note}")


def pct(k, s):
    return f"{100 * k / (k + s):.1f}%" if k + s else "-"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="D")
    ap.add_argument("--results", required=True)
    ap.add_argument("--stages", default=str(HERE / "stages.json"))
    ap.add_argument("--out")
    ap.add_argument("--gate", action="store_true")
    ap.add_argument("--reasons", default=str(HERE / "reasons.json"))
    a = ap.parse_args(argv)
    cfg = json.loads(Path(a.stages).read_text(encoding="utf-8"))
    if a.stage == "ALL":
        mods, seen = [], set()
        for st in cfg["stages"].values():
            for m in st:
                if m["module"] not in seen:
                    seen.add(m["module"])
                    mods.append(m)
        target = 0.80
    else:
        mods = cfg["stages"][a.stage]
        target = cfg["target"].get(a.stage)
    reasons = load_reasons(a.reasons)
    res = Path(a.results)
    rows, tk, ts, below, missing = [], 0, 0, [], []
    for m in mods:
        for lang in LANGS:
            if not m.get(lang):
                rows.append([m["module"], lang, "not mapped", "", "", "", "no module for this language in stages.json"])
                continue
            f = res / f"{lang}--{m['module']}.{'xml' if lang == 'java' else 'json'}"
            if not shard_files(f):
                missing.append(f.name)
                rows.append([m["module"], lang, "no result", "", "", "", f"`{m[lang]}`"])
                continue
            k, s, note = score_file(lang, f)
            tk, ts = tk + k, ts + s
            flag = ""
            lo, hi = wilson(k, k + s)
            if target is not None and k + s >= MIN_FOR_GATE and (k / (k + s) < target or lo < LOWER_BOUND):
                if (lang, m["module"]) in reasons:
                    flag = " (below; countersigned reason)"
                else:
                    below.append(f"{lang} {m['module']}")
                    flag = " (below target)"
            rows.append([m["module"], lang, pct(k, s) + flag, k, s, f"{lo:.0%} to {hi:.0%}" if k + s else "", note])
    lines = [f"# Mutation report, stage {a.stage}", "",
             f"Target: {target:.0%} per module and language with at least {MIN_FOR_GATE} scored mutants, and pooled." if target is not None else "No target set.",
             f"Pooled: **{pct(tk, ts)}** ({tk} killed, {ts} survived). Below target: {', '.join(below) or 'none'}. "
             f"Missing results: {len(missing)}.", "",
             "Survivors have not been sorted into equivalent mutants and real gaps, so the score is a lower bound on test strength.", "",
             f"Each module-language also needs a lower 95% Wilson bound of at least {LOWER_BOUND:.0%} (R6-14).", "",
             "| Module | Language | Score | Killed | Survived | 95% Wilson | Basis |", "|---|---|---|---:|---:|---|---|"]
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
