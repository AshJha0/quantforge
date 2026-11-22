#!/usr/bin/env python3
"""Stage K pre-tag audit PT-6 (2026-11-22): G-41 `xva.adjustments.value` at tiny and zero hazard.

    cd oracle/python && uv run python gen_stage_k_pt6.py

Plain idea: the bucket default probability `S(t_(i-1)) - S(t_i)` loses digits to cancellation when `h dt` is
tiny (h = 1e-9: about 9 of 16 digits gone; the audit measured builds 2.7e-7 relative apart). KR-350 writes it as
`S(t_(i-1)) (1 - e^(-h dt_i))` with `expm1`. These cases pin the result at h = 1e-9 and at h = 0 (where CVA or DVA
is exactly 0) against an independent 50-digit evaluation.

Oracle: mpmath at 50 significant digits on the exact binary64 values of the inputs (each float converted
exactly), evaluating G-41 as written in `specifications/06-risk/xva-framework.md`, then rounded once to binary64.
The tolerance below was committed before any expected value was computed (commit "PT-6: tolerance first").
"""
import json
from pathlib import Path

GOLDEN = Path(__file__).resolve().parents[2] / "datasets" / "golden"
OUT = GOLDEN / "stage_k" / "g41tiny_k.json"
# Committed before the values: G-41 is a short sum of products; with the cancellation-free form each term carries
# a few ulps of error, so 1e-13 relative (about 450 ulps) with a 1e-300 absolute floor (h = 0 gives an exact 0).
TOLERANCE = {"absolute": 1e-300, "relative": 1e-13,
             "reason": "short sums of products; cancellation-free bucket probability (KR-350); exact 0 at h = 0"}

BASE = {"times": [0.5, 1.0, 1.5, 2.0], "discount_factors": [0.985, 0.97, 0.955, 0.94],
        "ee": [120.0, 150.0, 130.0, 80.0], "ene": [-60.0, -90.0, -100.0, -70.0]}
CASES = [
    ("both names h = 1e-9", 1e-9, 1e-9, False, False),
    ("both names h = 0: CVA and DVA exactly 0", 0.0, 0.0, False, False),
    ("counterparty h = 1e-9, own h = 0.02, overlap excluded, im and capital", 1e-9, 0.02, True, True),
    ("counterparty h = 0, own h = 1e-9", 0.0, 1e-9, False, False),
]


def inputs(hc, hb, excl, extra):
    x = {**json.loads(json.dumps(BASE)), "counterparty": {"hazard_rate": hc, "recovery": 0.4},
         "own": {"hazard_rate": hb, "recovery": 0.4},
         "funding": {"borrow_spread": 0.008, "lend_spread": 0.012, "exclude_dva_overlap": excl}}
    if extra:
        x.update({"im": [50.0, 55.0, 60.0, 40.0], "im_spread": 0.005,
                  "capital": [30.0, 32.0, 28.0, 20.0], "hurdle_rate": 0.1})
    return x


def oracle(x):
    import mpmath as mp
    mp.mp.dps = 50
    f = mp.mpf
    t = [f(0)] + [f(v) for v in x["times"]]
    d = [f(v) for v in x["discount_factors"]]
    hc, rc = f(x["counterparty"]["hazard_rate"]), f(x["counterparty"]["recovery"])
    hb, rb = f(x["own"]["hazard_rate"]), f(x["own"]["recovery"])
    sc = [mp.exp(-hc * v) for v in t]
    sb = [mp.exp(-hb * v) for v in t]
    n = len(d)
    w = [d[i] * sc[i] * sb[i] * (t[i + 1] - t[i]) for i in range(n)]
    cva = (1 - rc) * mp.fsum(d[i] * f(x["ee"][i]) * (sc[i] - sc[i + 1]) * sb[i] for i in range(n))
    dva = (1 - rb) * mp.fsum(d[i] * abs(f(x["ene"][i])) * (sb[i] - sb[i + 1]) * sc[i] for i in range(n))
    sbor, sl = f(x["funding"]["borrow_spread"]), f(x["funding"]["lend_spread"])
    if x["funding"]["exclude_dva_overlap"]:
        sl = max(sl - hb * (1 - rb), f(0))
    fca = sbor * mp.fsum(w[i] * f(x["ee"][i]) for i in range(n))
    fba = sl * mp.fsum(w[i] * abs(f(x["ene"][i])) for i in range(n))
    out = {"cva": cva, "dva": dva, "fca": fca, "fba": fba, "fva": fca - fba}
    if "im" in x:
        out["mva"] = f(x["im_spread"]) * mp.fsum(w[i] * f(x["im"][i]) for i in range(n))
        out["kva"] = f(x["hurdle_rate"]) * mp.fsum(w[i] * f(x["capital"][i]) for i in range(n))
    return {k: float(v) for k, v in out.items()}


def main():
    cases = []
    for k, (desc, hc, hb, excl, extra) in enumerate(CASES, 1):
        x = inputs(hc, hb, excl, extra)
        cases.append({"case_id": f"g41tiny_k-{k:04d}", "operation": "xva.adjustments.value", "inputs": x,
                      "expected": {"status": "ok", "outputs": oracle(x)}, "tolerance_class": "simple_analytic",
                      "verified_by": ["mpmath-50"], "tags": ["xva", "adjustments", "tiny-hazard", "synthetic"],
                      "description": f"PT-6 / KR-350: {desc}", "tolerance_limit": TOLERANCE})
    doc = {"schema_version": "1.0", "suite": "g41tiny_k", "spec": "specifications/06-risk/xva-framework.md",
           "spec_version": "1.0.0", "generator": "oracle/python/gen_stage_k_pt6.py",
           "reviewer": "none: self-assessment; no second review (owner decision 2026-11-18)", "cases": cases}
    OUT.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(f"{OUT.name}: {len(cases)} cases")


if __name__ == "__main__":
    main()
