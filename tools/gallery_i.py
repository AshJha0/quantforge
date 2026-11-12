"""Stage I page for the gallery: hedging against trading costs (tools/build_gallery.py).

Holds no financial logic. It sends two things to each CLI: the risk-against-cost frontier of
`examples/hedge_frontier_i.json` (`hedge.frontier.solve`), and a sweep of one instrument's half-spread through
`hedge.qp.solve` on the inputs of golden case `hedgecost_i-0023`, which sits exactly on a switch point. It stores
what comes back, draws it, and compares the Python result with the golden cases. Its only sums are differences
between outputs.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SLUG = "hedging-costs"
EXAMPLE = "hedge_frontier_i.json"
EXAMPLE_CASE = "hedgefrontier_i-0001"
GOLDEN = ROOT / "datasets" / "golden" / "stage_i"
SWITCH_CASE = "hedgecost_i-0023"
SPREADS = [0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5, 3.0]


def _cases(suite):
    return {c["case_id"]: c for c in json.loads((GOLDEN / f"{suite}.json").read_text(encoding="utf-8"))["cases"]}


def requests(example):
    base = _cases("hedgecost_i")[SWITCH_CASE]["inputs"]
    out = [{"schema_version": "1.0", "case_id": "gallery-i-frontier", "operation": "hedge.frontier.solve", "inputs": example["inputs"]}]
    for i, h in enumerate(SPREADS):
        out.append({"schema_version": "1.0", "case_id": f"gallery-i-switch-{i:02d}", "operation": "hedge.qp.solve",
                    "inputs": {**base, "half_spreads": [h, base["half_spreads"][1]]}})
    return out


def run(lang, batch, read_example):
    rows = batch(lang, requests(read_example(EXAMPLE)))
    return {"frontier": rows[0]["outputs"]["points"], "switch": [{"half_spread": h, **r["outputs"]} for h, r in zip(SPREADS, rows[1:])]}


def _flat(res):
    vals = []
    for p in res["frontier"]:
        vals += p["x"] + [p["risk"], p["cost"]]
    for p in res["switch"]:
        vals += p["x"] + [p["risk"], p["cost"], p["objective"]]
    return vals


def agreement(results, langs):
    ref = _flat(results[langs[0]])
    worst = max(abs(a - b) for lang in langs for a, b in zip(_flat(results[lang]), ref))
    return {"values": len(ref), "largest_difference": worst}


def against_golden(reference, example_case):
    """Largest difference from the golden cases the page reproduces: the frontier case the example copies, and the switch case."""
    fr = _cases("hedgefrontier_i")[example_case]["expected"]["outputs"]["points"]
    d1 = max(abs(a - b) for p, q in zip(reference["frontier"], fr) for a, b in zip(p["x"] + [p["risk"], p["cost"]], q["x"] + [q["risk"], q["cost"]]))
    sw = _cases("hedgecost_i")[SWITCH_CASE]["expected"]["outputs"]
    at = next(p for p in reference["switch"] if p["half_spread"] == 2.0)
    d2 = max(abs(a - b) for a, b in zip(at["x"] + [at["risk"], at["cost"], at["objective"]], sw["x"] + [sw["risk"], sw["cost"], sw["objective"]]))
    return [{"case": example_case, "largest_difference": d1}, {"case": SWITCH_CASE, "largest_difference": d2}]


def evidence():
    reg = json.loads((ROOT / "oracle" / "outside_register_i.json").read_text(encoding="utf-8"))
    rows = [{"suite": s, "cases": reg[s]["total"], "outside": reg[s]["counted"]} for s in ("hedgecost_i", "hedgefrontier_i", "hedgeqp5_i")]
    st = reg["_stage"]
    return {"suites": rows, "stage_cases": st["total"], "stage_outside": st["counted"]}


def page(d, table, lines, status_block):
    ref = d["reference"]
    cap = "Synthetic inputs. From the Python CLI; exact values are in the data file."
    front = [("Frontier", [(p["cost"], p["risk"]) for p in ref["frontier"]])]
    sw = [("Instrument 1", [(p["half_spread"], p["x"][0]) for p in ref["switch"]]),
          ("Instrument 2", [(p["half_spread"], p["x"][1]) for p in ref["switch"]])]
    frows = [[repr(p["cost_weight"]), f"{p['cost']:.6f}", f"{p['risk']:.6f}"] + [f"{v:.6f}" for v in p["x"]] for p in ref["frontier"]]
    srows = [[repr(p["half_spread"]), f"{p['x'][0]:.6f}", f"{p['x'][1]:.6f}", f"{p['objective']:.6f}"] for p in ref["switch"]]
    gold = [[f"`{r['case']}`", f"{r['largest_difference']:.2g}"] for r in d["against_golden"]]
    e = d["evidence"]
    ev = [[f"`{r['suite']}`", r["cases"], r["outside"]] for r in e["suites"]]
    a = d["agreement"]
    return f"""# Hedging against trading costs

{status_block(d)}

## What it is

A hedge that ignores trading costs can buy small amounts of every instrument. Once each trade pays a half-spread, removing a little risk may cost more than it is worth, and the best hedge leaves some instruments out entirely. This page shows two views of that trade-off. Stage I, target v0.8.0 (`specifications/08-hedging/hedge-costs-and-frontier.md`).

Formally, `hedge.qp.solve` minimises `sum_i w_i (A x + b)_i^2 + c sum_j h_j |x_j|`, risk plus a cost weight `c` times cost, and `hedge.frontier.solve` repeats the solve over a list of cost weights. An instrument held at zero stays there while its risk gradient satisfies `|g_j| <= c h_j`; where the two are equal it is at its switch point, and the answer must be exact there (ruling I-54).

## Inputs

The frontier: five risks, three instruments and seven cost weights from 0 to 50, from [`examples/{EXAMPLE}`](../../examples/{EXAMPLE}) (a copy of golden case `{d['example_case']}`). The switch point: the inputs of golden case `{SWITCH_CASE}`, two independent risks `b = (-1, -2)` with one instrument each and half-spread 0.5 on instrument 2, with instrument 1's half-spread swept from 0 to 3. All synthetic.

## Command

Build a CLI as in the [Cookbook](../../COOKBOOK.md), then from the repository root:

```bash
rust/target/release/quantforge run < examples/{EXAMPLE}
```

Raw numbers: [`docs/curves/data/{SLUG}.json`](data/{SLUG}.json).

## Charts

{lines("Risk against cost along the frontier", "Cost", "Risk", front, cap)}

As the cost weight rises the hedge trades less: cost falls and risk rises. The curve is the set of hedges no other hedge beats on both.

{lines("Holding against instrument 1's half-spread", "Half-spread of instrument 1", "Units held", sw, cap)}

Instrument 1's holding is `1 - h/2` while that is positive and exactly 0 from `h = 2`, its switch point; instrument 2 does not move, because the two risks are independent.

## Numbers

Frontier:

{table(['Cost weight', 'Cost', 'Risk', 'x1', 'x2', 'x3'], frows)}

Switch-point sweep:

{table(['Half-spread 1', 'x1', 'x2', 'Objective'], srows)}

## Four-language agreement

Each CLI built these numbers on its own. Largest difference between any language and Java over {a['values']} values: {a['largest_difference']:.2g}. Agreement shows only that the four agree; the golden comparison below is the check against the oracle.

## Against the golden cases

The Python CLI's result against the golden cases it reproduces (class `root_finding`):

{table(['Golden case', 'Largest difference'], gold)}

## Oracle evidence and limits

The golden cases are 50-digit mpmath solves over the sign states with subgradient checks. Outside checks are scipy 1.18 solvers on the same problem (`oracle/outside_register_i.json`):

{table(['Suite', 'Cases', 'Outside-checked'], ev)}

Stage I as a whole: {e['stage_outside']} of {e['stage_cases']} cases outside-checked, error cases in the denominator (ruling I-2). Limits: linear spread cost and synthetic risks, so the page shows the method, not a desk's costs; the hedge starts from no position.
"""
