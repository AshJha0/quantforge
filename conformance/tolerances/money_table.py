#!/usr/bin/env python3
"""Writes conformance/tolerances/money.md: every tolerance class, and every per-case limit in use, stated in money
on a 10,000,000 notional. Standard library only; plain arithmetic, no libm.

python conformance/tolerances/money_table.py

Reference instruments are read from the goldens, so the table moves when they do:
- rate outputs: the 10Y SOFR OIS in stage_d/ois_d (annuity A), DV01 = N A 1e-4;
- price outputs (per 100 face): the 2036 4.5% bond in stage_d/bonds_d at 4.10%, DV01 per 100 = MD x dirty x 1e-4,
  with a US Treasury tick of 1/32 and the finest quoted fraction 1/256;
- discount factors: a cash flow of N at the 10Y pillar of the SOFR curve in stage_d/ois_d;
- CDS spreads: the 5Y IG trade in stage_d/credit_d (rpv01).
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "conformance" / "runner"))
from runner import load_policy  # noqa: E402

N = 10_000_000.0


def cases(name):
    return json.loads((ROOT / "datasets" / "golden" / "stage_d" / f"{name}.json").read_text(encoding="utf-8"))["cases"]


def refs():
    sw = next(c for c in cases("ois_d") if c["operation"] == "rates.ois.pv" and c["inputs"]["trade"]["convention"] == "SOFR" and c["inputs"]["trade"]["tenor"] == "10Y")
    A = sw["expected"]["outputs"]["annuity"]
    bd = next(c for c in cases("bonds_d") if c["operation"] == "bond.price.from_yield" and c["inputs"]["bond"]["maturity"] == "2036-08-15" and c["inputs"]["yield"] == .041)
    o = bd["expected"]["outputs"]
    dv01_100 = o["modified_duration"] * o["dirty"] * 1e-4
    boot = next(c for c in cases("ois_d") if c["operation"] == "rates.ois.bootstrap" and c["inputs"]["convention"] == "SOFR")
    p10 = next(p for p in boot["expected"]["outputs"]["pillars"] if p["date"].startswith("2036"))
    from datetime import date
    t10 = (date.fromisoformat(p10["date"]) - date.fromisoformat(boot["inputs"]["as_of"])).days / 365
    cds = next(c for c in cases("credit_d") if c["operation"] == "credit.cds.price" and c["inputs"]["trade"]["maturity"] == "2031-12-20" and c["inputs"]["trade"]["coupon"] == .01)
    return {"A": A, "dv01_100": dv01_100, "dirty": o["dirty"], "df10": p10["discount_factor"], "t10": t10, "rpv01": cds["expected"]["outputs"]["rpv01"],
            "ids": [sw["case_id"], bd["case_id"], boot["case_id"], cds["case_id"]]}


def row(name, a, r, R, note=""):
    rate = a + r * 0.04                      # a rate output near 4%
    price = a + r * R["dirty"]               # a price per 100 near par
    df = a + r * R["df10"]                   # a 10Y discount factor
    return (f"| {name} | {a:.0e} | {r:.0e} | {rate / 1e-4:.1e} bp, {rate * R['A'] * N:.2e} | "
            f"{price * N / 100:.2e}, {price / (1 / 32):.1e} ticks, {price / R['dv01_100']:.1e} bp | "
            f"{df * N:.2e}, {df / (R['df10'] * R['t10'] * 1e-4):.1e} bp | {note} |")


def main():
    R = refs()
    pol = load_policy(HERE / "policy.yaml")
    L = ["# Tolerances in money", "",
         "Written by `conformance/tolerances/money_table.py`. Every tolerance in `policy.yaml`, and every per-case `tolerance_limit` in use, restated as money on a",
         "10,000,000 notional, so a desk can judge it. The comparison is `|a - e| <= absolute + relative x max(|a|, |e|)`.", "",
         "Reference instruments, read from the goldens (" + ", ".join(f"`{i}`" for i in R["ids"]) + "):",
         f"- rate: 10Y SOFR OIS, annuity {R['A']:.4f}, so DV01 on 10m = {N * R['A'] * 1e-4:,.0f};",
         f"- price per 100 face: 2036 4.5% bond at 4.10%, DV01 per 100 = {R['dv01_100']:.5f}, or {R['dv01_100'] * N / 100:,.0f} on 10m face; a Treasury tick is 1/32;",
         f"- discount factor: a cash flow of 10m at the 10Y SOFR pillar, D = {R['df10']:.6f}, t = {R['t10']:.4f};",
         f"- CDS: 5Y IG trade, rpv01 {R['rpv01']:.4f}, so 1 bp of spread is {N * R['rpv01'] * 1e-4:,.0f} on 10m.", "",
         "How to read a row: the same tolerance applied to three kinds of output. Columns give the money error on 10m it allows, and the same error in",
         "basis points of the instrument's DV01 or in price ticks. Every class allows far less than 1/100 of a bp, and far less than 1 currency unit, on these trades.", "",
         "| Class or limit | absolute | relative | Rate output near 4%: bp, money on the 10Y swap | Price per 100: money on 10m face, 32nds, bp of DV01 | 10Y discount factor: money on a 10m flow, bp | Note |",
         "|---|---|---|---|---|---|---|"]
    for k, v in pol.items():
        if "absolute" in v:
            L.append(row(f"`{k}`", float(v["absolute"]), float(v["relative"]), R))
        else:
            L.append(f"| `{k}` | - | - | - | - | - | {'exact' if v.get('exact') else 'judged per case: ' + ', '.join(f'{a}={b}' for a, b in v.items())} |")
    # Per-case limits in use, grouped.
    seen = {}
    for p in sorted((ROOT / "datasets" / "golden").rglob("*.json")):
        for c in json.loads(p.read_text(encoding="utf-8"))["cases"]:
            lim = c.get("tolerance_limit")
            if lim:
                key = (lim.get("absolute", 0.0), lim.get("relative", 0.0))
                seen.setdefault(key, [0, lim.get("reason", "")])[0] += 1
    L += ["", "## Per-case limits in use", "",
          "A case may set its own `tolerance_limit`. Limits stated per unit of notional are scaled to the case's notional when the golden is written, so on a",
          "10m notional the money column is what the limit means. The rows below apply each limit, as written, to the same outputs as above.", "",
          "| Limit | absolute | relative | Rate output near 4% | Price per 100 | 10Y discount factor | Cases, and the reason given |", "|---|---|---|---|---|---|---|"]
    for (a, r), (n, why) in sorted(seen.items(), key=lambda kv: -kv[1][0]):
        if a >= 1e-6:  # a currency limit, already scaled to the case's notional: read it on a PV of 100,000 on 10m
            m = a + r * 1e5
            L.append(f"| case limit | {a:.0e} | {r:.0e} | currency output: {m:.2e} on a PV of 1e5, {m / (N * R['A'] * 1e-4):.1e} bp of the 10Y swap DV01 | - | - | {n}: {why[:90]} |")
        else:
            L.append(row("case limit", a, r, R, f"{n}: {why[:90]}"))
    L += ["", "## Notional-scaled PV limits", "",
          "PV outputs in currency use `absolute = 1e-9 x notional` (ruling D60 and the stage B and D targets). On 10m that is 0.01 currency units,",
          f"or {0.01 / (N * R['A'] * 1e-4):.1e} bp of the 10Y swap's DV01. CDS PVs use 0.01 absolute plus 1e-9 relative: on 10m that is at most "
          f"{0.01 + 1e-9 * N:.2f}, or {(0.01 + 1e-9 * N) / (N * R['rpv01'] * 1e-4):.1e} bp of spread.", ""]
    (HERE / "money.md").write_text("\n".join(L), encoding="utf-8", newline="\n")
    print(f"wrote money.md: {len(pol)} classes, {len(seen)} distinct case limits")


if __name__ == "__main__":
    main()
