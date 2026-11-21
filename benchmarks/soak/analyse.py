#!/usr/bin/env python3
"""Applies the frozen K-6 soak rule (KR-218) to a soak CSV and its run summary. Standard library only.

Plain idea: after a warm-up, the memory a long-running `quantforge batch` process keeps should not climb, should not
wander, and every answer should stay the same as the first time the case was run.

Formal rule (frozen before any judged run; `RULES` below is the single source, and the docs quote it):
  * Warm-up: samples before max(600 s, the end of the first full pass over the golden set) are discarded, so every
    case has been run once (caches, JIT and allocator pools filled) before memory is judged.
  * Judged series: `judged_bytes`, one value per 10 s sample. For Python, C++ and Rust it is one memory reading
    taken at the idle point of each sample: soak.py stops sending, waits until every case in flight is answered
    (`quiesce()`), then reads once (committed private bytes on Windows, VmRSS on Linux; see procstat.py). A sample
    whose quiesce did not finish has no judged value. For Java it is the heap used after the most recent full collection, which the soak requests with
    `jcmd <pid> GC.run` every 30 s; Java RSS is reported, not judged.
  * SLOPE: the least-squares slope of the judged series against time is at most 1 MiB per hour.
  * RANGE: max minus min of the judged series is at most 5 % of its median.
  * Samples: at least 660 judged samples after warm-up (200 for the Java heap series); wall time at least 7200 s.
  * NO_FULL_PASS: the whole golden set was answered at least once.
  * DRIFT: zero later answers that differ, byte for byte, from the first answer to the same case.
  * GOLDEN: zero first answers that fail the conformance judgement against the golden file.
  * ERRORS / STDERR / EXIT / DIED: zero unreadable output lines, zero bytes on stderr, exit code 0 after stdin
    closes, and the process alive at every sample.
  * STALL: no 300 s stretch without a completed case (the slowest single golden case takes about 25 s in the
    slowest build, from the conformance logs; 300 s leaves wide room and still catches a hung process).
A run passes only when no reason fires. Anything else is a MISS, written down as such.

The 95 % confidence interval of the slope is reported beside it (from the means of 10-minute blocks, which damps the
correlation between neighbouring 10 s samples; Student t with blocks - 2 degrees of freedom). It is evidence, not a
pass condition.

Planted run (rule 1): the same rule with `--planted` (20 minutes, so SHORT and FEW_SAMPLES are not applied) must fire
SLOPE on the Python build run with QF_SOAK_LEAK=1.

Usage: analyse.py SOAK.csv SUMMARY.json [--planted] [--out FILE]   Exit: 0 PASS (or planted leak caught), 1 MISS.
"""

import argparse
import csv
import json
import statistics
import sys
from pathlib import Path

MIB = 1024 * 1024
RULES = {
    "warmup_s": 600,
    "slope_max_mib_per_h": 1.0,
    "range_max_fraction_of_median": 0.05,
    "min_samples": 660,
    "min_samples_java_heap": 200,
    "min_duration_s": 7200,
    "stall_max_s": 300,
    "block_s": 600,
}
_T975 = {
    1: 12.706,
    2: 4.303,
    3: 3.182,
    4: 2.776,
    5: 2.571,
    6: 2.447,
    7: 2.365,
    8: 2.306,
    9: 2.262,
    10: 2.228,
    11: 2.201,
    12: 2.179,
    13: 2.160,
    14: 2.145,
    15: 2.131,
    16: 2.120,
    17: 2.110,
    18: 2.101,
    19: 2.093,
    20: 2.086,
}


def ols(xs, ys):
    """(slope, intercept) of the least-squares line; slope 0 for fewer than two distinct x."""
    n = len(xs)
    if n < 2:
        return 0.0, (ys[0] if ys else 0.0)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return 0.0, my
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    return b, my - b * mx


def slope_ci(xs, ys, block_s):
    """95 % interval of the slope from block means: (low, high) in y units per x unit, or None if under 3 blocks."""
    if not xs:
        return None
    blocks = {}
    for x, y in zip(xs, ys):
        blocks.setdefault(int((x - xs[0]) // block_s), []).append((x, y))
    pts = [(statistics.fmean(p[0] for p in v), statistics.fmean(p[1] for p in v)) for v in blocks.values() if v]
    if len(pts) < 3:
        return None
    bx, by = [p[0] for p in pts], [p[1] for p in pts]
    b, a = ols(bx, by)
    resid = [y - (a + b * x) for x, y in zip(bx, by)]
    df = len(pts) - 2
    mx = statistics.fmean(bx)
    sxx = sum((x - mx) ** 2 for x in bx)
    se = (sum(r * r for r in resid) / df / sxx) ** 0.5 if sxx else 0.0
    t = _T975.get(df, 1.96)
    return b - t * se, b + t * se


def analyse(rows, summary, planted=False, rules=RULES):
    """Returns the verdict dict. `rows` are CSV dicts (strings), `summary` the soak driver's summary JSON."""
    java = summary.get("implementation") == "java"
    reasons = []
    t = [float(r["t_s"]) for r in rows]
    first_pass = next((float(r["t_s"]) for r in rows if int(r["passes"]) >= 1), None)
    warmup = max(rules["warmup_s"], first_pass if first_pass is not None else float("inf"))
    judged = [
        (float(r["t_s"]), float(r["judged_bytes"]))
        for r in rows
        if float(r["t_s"]) >= warmup and r.get("judged_bytes") not in ("", None)
    ]
    xs, ys = [p[0] for p in judged], [p[1] for p in judged]
    b, _ = ols([x / 3600 for x in xs], [y / MIB for y in ys])
    ci = slope_ci([x / 3600 for x in xs], [y / MIB for y in ys], rules["block_s"] / 3600)
    med = statistics.median(ys) if ys else 0.0
    rng = (max(ys) - min(ys)) if ys else 0.0
    need = rules["min_samples_java_heap"] if java else rules["min_samples"]
    if not planted:
        if len(ys) < need:
            reasons.append("FEW_SAMPLES")
        if (t[-1] if t else 0) < rules["min_duration_s"]:
            reasons.append("SHORT")
    if first_pass is None:
        reasons.append("NO_FULL_PASS")
    if ys and b > rules["slope_max_mib_per_h"]:
        reasons.append("SLOPE")
    if ys and rng > rules["range_max_fraction_of_median"] * med:
        reasons.append("RANGE")
    if summary.get("drift", 0):
        reasons.append("DRIFT")
    if summary.get("golden_failures", 0):
        reasons.append("GOLDEN")
    if summary.get("errors", 0):
        reasons.append("ERRORS")
    if summary.get("stderr_bytes", 0):
        reasons.append("STDERR")
    if summary.get("exit_code") != 0:
        reasons.append("EXIT")
    if any(r.get("alive") == "0" for r in rows) or summary.get("died"):
        reasons.append("DIED")
    last, stall = 0.0, 0.0
    for r in rows:
        if int(r["cases_window"]) > 0:
            last = float(r["t_s"])
        stall = max(stall, float(r["t_s"]) - last)
    if stall > rules["stall_max_s"]:
        reasons.append("STALL")
    out = {
        "implementation": summary.get("implementation"),
        "host": summary.get("host"),
        "commit": summary.get("commit"),
        "planted": planted,
        "judged_series": "heap after full GC" if java else summary.get("judged_key"),
        "warmup_end_s": warmup if first_pass is not None else None,
        "samples_after_warmup": len(ys),
        "duration_s": t[-1] if t else 0,
        "slope_mib_per_h": round(b, 4),
        "slope_ci95_mib_per_h": [round(ci[0], 4), round(ci[1], 4)] if ci else None,
        "median_mib": round(med / MIB, 3),
        "range_mib": round(rng / MIB, 3),
        "range_fraction_of_median": round(rng / med, 5) if med else None,
        "longest_stall_s": stall,
        "cases": summary.get("cases"),
        "drift": summary.get("drift"),
        "golden_failures": summary.get("golden_failures"),
        "reasons": reasons,
        "rules": rules,
    }
    if planted:
        out["verdict"] = "LEAK CAUGHT" if "SLOPE" in reasons else "LEAK MISSED"
    else:
        out["verdict"] = "PASS" if not reasons else "MISS"
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("summary")
    ap.add_argument("--planted", action="store_true")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    with open(a.csv, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    summary = json.loads(Path(a.summary).read_text(encoding="utf-8"))
    v = analyse(rows, summary, a.planted)
    text = json.dumps(v, indent=1)
    if a.out:
        Path(a.out).write_text(text + "\n", encoding="utf-8")
    print(
        f"{v['implementation']}: {v['verdict']} slope {v['slope_mib_per_h']} MiB/h (95% CI {v['slope_ci95_mib_per_h']}), "
        f"range {v['range_mib']} MiB of median {v['median_mib']} MiB, reasons {v['reasons']}"
    )
    return 0 if v["verdict"] in ("PASS", "LEAK CAUGHT") else 1


if __name__ == "__main__":
    sys.exit(main())
