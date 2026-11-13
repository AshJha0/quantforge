#!/usr/bin/env python3
"""Outside-checked counts in docs/model-inventory.md for stages G and I, generated from the registers (R6-17).

The counts come from oracle/OUTSIDE_SHARES.json, which tools/outside_shares.py builds from the
outside registers under the tight rule D6 (a case counts only as library-object or library-primitive, and
only if every compared output is checked; error cases stay in the denominator; generated sweeps excluded).
This script rewrites the last cell of each MG and MI row of the summary table. Typed counts are not allowed
there any more: `--check` fails if a row differs from the registers. Standard library only.

    python tools/inventory_counts.py           # rewrite the cells
    python tools/inventory_counts.py --check   # fail if a cell differs
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "docs" / "model-inventory.md"
SHARES = ROOT / "oracle" / "OUTSIDE_SHARES.json"

# Inventory entry -> (stage, operations it covers). An operation listed under no entry is reported.
ENTRIES = {
    "MG-1": ("G", ["rates.shortrate.zcb", "rates.shortrate.zcb_option", "rates.shortrate.swaption", "rates.shortrate.capfloor",
                   "rates.shortrate.hw_calibrate", "rates.shortrate.bermudan_swaption", "rates.shortrate.callable_bond",
                   "rates.g2pp.zcb", "rates.g2pp.zcb_option"]),
    "MG-2": ("G", ["exotic.barrier.price"]),
    "MG-3": ("G", ["risk.mc.greeks"]),
    "MG-4": ("G", ["xva.exposure.swap_ee_hw"]),
    "MG-5": ("G", ["rates.lmm.capfloor", "rates.lmm.swaption_rebonato"]),
    "MG-6": ("G", ["rates.shortrate.bermudan_ladder"]),
    "MG-7": ("G", ["risk.model_reserve.dispersion"]),
    "MG-8": ("G", ["xva.adjustments.value", "xva.exposure.collateralised", "xva.simm.ir_delta", "xva.wwr.cva_hw"]),
    "MG-9": ("G", ["xva.exposure.portfolio_hw"]),
    "MI-1": ("I", ["hedge.qp.solve", "hedge.integer.solve", "hedge.minvar.ratio", "hedge.greeks.neutralise", "hedge.beta.futures",
                   "hedge.residual.report"]),
    "MI-2": ("I", ["hedge.credit.cds", "hedge.correlation.neutralise"]),
    "MI-3": ("I", ["hedge.crossasset.solve"]),
    "MI-4": ("I", ["hedge.frontier.solve"]),
    "MI-5": ("I", ["hedge.backtest.delta", "hedge.effectiveness"]),
    "MI-6": ("I", ["hedge.select.solve"]),
    "MI-7": ("I", ["hedge.slippage.report"]),
}
NOT_IN_G_REGISTER = "not in the stage G register (suites outside `datasets/golden/stage_g`); see entry"


def cell(stage_ops, ops):
    rows = [stage_ops[o] for o in ops if o in stage_ops]
    if not rows:
        return NOT_IN_G_REGISTER
    n = sum(r["cases"] for r in rows)
    obj = sum(r["library-object"] for r in rows)
    prim = sum(r["library-primitive"] for r in rows)
    return f"{obj + prim} of {n} ({obj} library object, {prim} numpy or scipy primitive; D6, generated)"


def render(text, shares):
    out, unused = [], {s: set(shares["stages"][s]["per_operation"]) for s in "GI"}
    for line in text.splitlines():
        m = re.match(r"^\| (M[GI]-\d+) \|", line)
        if m and m.group(1) in ENTRIES:
            stage, ops = ENTRIES[m.group(1)]
            unused[stage] -= set(ops)
            cells = line.split(" | ")
            cells[-1] = cell(shares["stages"][stage]["per_operation"], ops) + " |"
            line = " | ".join(cells)
        out.append(line)
    return "\n".join(out) + ("\n" if text.endswith("\n") else ""), unused


def main(argv):
    text = PAGE.read_text(encoding="utf-8")
    new, unused = render(text, json.loads(SHARES.read_text(encoding="utf-8")))
    problems = [f"operation {o} (stage {s}) is in the register but under no inventory entry" for s in unused for o in sorted(unused[s])]
    if "--check" in argv:
        if new != text:
            problems.append("docs/model-inventory.md: outside-checked counts differ from the registers; run python tools/inventory_counts.py")
        for p in problems:
            print(p)
        print("inventory counts: " + ("current" if not problems else f"{len(problems)} problems"))
        return 1 if problems else 0
    PAGE.write_text(new, encoding="utf-8", newline="\n")
    for p in problems:
        print(p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
