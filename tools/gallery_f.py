"""Stage F page for the curves gallery: one curve under five interpolation methods (tools/build_gallery.py).

Holds no financial logic. It builds five `rates.curve.inspect` requests from one example file by setting the
`interpolation` key (and `tension` or `step_end`), sends them to each CLI, stores what comes back and draws the
instantaneous forwards. Its only sums are curve time, (date - as_of) / 365, percent units and differences between
outputs. It also compares each result with the matching golden case of `datasets/golden/stage_f/curve_f.json`.
"""
import datetime as dt
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SLUG = "interpolation-methods"
EXAMPLE = "curve_methods_f.json"
# (label, curve keys, golden case with the same pillars and dates)
METHODS = [("Log-linear in D", {"interpolation": "LOG_LINEAR_DF"}, "curve_f-0068"),
           ("Monotone convex", {"interpolation": "MONOTONE_CONVEX"}, "curve_f-0070"),
           ("Monotonic log cubic", {"interpolation": "MONOTONIC_LOG_CUBIC"}, "curve_f-0071"),
           ("Tension spline, tension 1", {"interpolation": "TENSION_SPLINE", "tension": 1.0}, "curve_f-0073"),
           ("Hybrid, steps to 1y", {"interpolation": "HYBRID", "step_end": "2027-11-09"}, "curve_f-0075")]
GOLDEN = ROOT / "datasets" / "golden" / "stage_f" / "curve_f.json"


def requests(example):
    out = []
    for label, keys, _ in METHODS:
        curve = {k: v for k, v in example["inputs"]["curve"].items() if k not in ("interpolation", "tension", "step_end")}
        out.append({"schema_version": "1.0", "case_id": f"gallery-f-{keys['interpolation'].lower()}", "operation": "rates.curve.inspect",
                    "inputs": {"curve": {**curve, **keys}, "dates": example["inputs"]["dates"]}})
    return out


def run(lang, batch, read_example):
    rows = batch(lang, requests(read_example(EXAMPLE)))
    return {label: r["outputs"] for (label, _, _), r in zip(METHODS, rows)}


def _diff(a, b):
    m = 0.0
    for x, y in zip(a, b):
        if x is None or y is None:
            if x != y:
                return None
            continue
        m = max(m, abs(x - y))
    return m


def agreement(results, langs):
    """Largest difference between any two languages, per method and output."""
    rows = []
    for label, _, _ in METHODS:
        for key in ("discount_factors", "zero_rates", "instantaneous_forwards"):
            worst = 0.0
            for a in langs:
                for b in langs:
                    d = _diff(results[a][label][key], results[b][label][key])
                    worst = None if d is None or worst is None else max(worst, d)
            rows.append({"method": label, "output": key, "largest_difference": worst})
    return rows


def against_golden(reference):
    """Largest difference between the reference CLI and the golden case, per method."""
    cases = {c["case_id"]: c for c in json.loads(GOLDEN.read_text(encoding="utf-8"))["cases"]}
    out = []
    for label, _, cid in METHODS:
        exp = cases[cid]["expected"]["outputs"]
        out.append({"method": label, "case": cid,
                    "largest_difference": max((_diff(reference[label][k], exp[k]) or 0.0) for k in ("discount_factors", "zero_rates", "instantaneous_forwards"))})
    return out


def evidence():
    reg = json.loads((ROOT / "oracle" / "outside_register_f.json").read_text(encoding="utf-8"))
    outside = {c["case_id"] for c in reg["cases"]}
    by = {}
    total = n_out = 0
    for c in json.loads(GOLDEN.read_text(encoding="utf-8"))["cases"]:
        if c["operation"] != "rates.curve.inspect" or c["expected"]["status"] != "ok":
            continue
        kind = c["inputs"]["curve"]["interpolation"]
        by.setdefault(kind, [0, 0])
        by[kind][0] += 1
        total += 1
        if c["case_id"] in outside:
            by[kind][1] += 1
            n_out += 1
    return {"operation": "rates.curve.inspect", "cases": total, "outside": n_out, "by_method": by}


def page(d, table, lines, status_block, langs):
    as_of = dt.date.fromisoformat(d["inputs"]["curve"]["as_of"])
    t = [(dt.date.fromisoformat(s) - as_of).days / 365 for s in d["inputs"]["dates"]]
    cap = "Synthetic pillars. From the Python CLI; exact values are in the data file."
    series = [(label, [(x, 100 * f) for x, f in zip(t, d["reference"][label]["instantaneous_forwards"])]) for label, _, _ in METHODS]
    by = dict(series)
    # the chart helper draws at most four series: two charts that share monotone convex as the reference line
    a = [(k, by[k]) for k in ("Log-linear in D", "Monotone convex", "Monotonic log cubic")]
    b = [(k, by[k]) for k in ("Monotone convex", "Tension spline, tension 1", "Hybrid, steps to 1y")]
    short = [(k, [(x, y) for x, y in s if x <= 3.0]) for k, s in b]
    agree = [[r["method"], r["output"], "differ" if r["largest_difference"] is None else f"{r['largest_difference']:.2g}"] for r in d["agreement"]]
    gold = [[r["method"], f"`{r['case']}`", f"{r['largest_difference']:.2g}"] for r in d["against_golden"]]
    e = d["evidence"]
    ev = [[k, n, o] for k, (n, o) in sorted(e["by_method"].items())]
    return f"""# One curve, five interpolation methods

{status_block(d)}

## What it is

Between quoted dates a curve has to be filled in, and the method decides what forward rate a trader sees on any day in between. This page takes one set of 12 SOFR pillar discount factors and asks each method for the instantaneous forward rate along the curve. The discount factors at the pillars are the same in every method; only the space between them changes. Stage F, released in v0.6.0 (`specifications/02-curves/curve-framework.md`, section "Stage F: pluggable interpolation").

What to look for: log-linear in `D` gives flat forwards that jump at every pillar. Monotone convex (Hagan and West) and the monotonic log cubic give continuous forwards. The tension spline sits between a cubic spline and log-linear as its tension moves from 0 to infinity. The hybrid is stepwise up to its `step_end` and smooth behind it.

## Inputs

Twelve pillars from one month to 30 years, as of {d['inputs']['curve']['as_of']}, the pillars of the fixed-pillar golden cases (`curve_f-0068` to `curve_f-0076`), evaluated at {len(t)} dates. Synthetic. Input: [`examples/{EXAMPLE}`](../../examples/{EXAMPLE}); the gallery sets `interpolation` (and `tension` or `step_end`) for each method.

## Command

Build a CLI as in the [Cookbook](../../COOKBOOK.md), then from the repository root:

```bash
rust/target/release/quantforge run < examples/{EXAMPLE}
```

Raw numbers: [`docs/curves/data/{SLUG}.json`](data/{SLUG}.json).

## Charts

{lines("Forwards: log-linear, monotone convex, monotonic log cubic", "Years", "Forward, %", a, cap)}

{lines("Forwards: monotone convex, tension spline, hybrid", "Years", "Forward, %", b, cap)}

{lines("The first 3 years, where the hybrid steps", "Years", "Forward, %", short, cap)}

## Four-language agreement

Each CLI built these numbers on its own. Agreement shows only that the four agree; the golden comparison below is the check against the oracle.

{table(['Method', 'Output', 'Largest difference between any two languages'], agree)}

## Against the golden cases

The Python CLI's result against the oracle's golden case with the same pillars and dates (the class `interpolation` allows 1e-10 plus 1e-8 relative):

{table(['Method', 'Golden case', 'Largest difference'], gold)}

## Oracle evidence and limits

{e['cases']} golden cases with status ok for `{e['operation']}`, {e['outside']} of them reproduced by an outside library (QuantLib 1.44, with SciPy quadrature for the monotone convex integral; `oracle/outside_register_f.json`):

{table(['Method', 'Cases', 'Outside-checked'], ev)}

The tension spline and the hybrid have no outside library (`oracle/OUTSIDE_GAPS_F.md`). Limits: one synthetic pillar set, so the page shows the methods, not a market.
"""
