"""Recompute every worked-example number in 07-credit-correlation.md and check it appears there.

Run from the repository's python directory:
    PYTHONPATH=. python ../docs/question-bank/verify/v07_credit_correlation.py
Add --dump to print the expected strings without checking.
"""
import json
import math
import sys
from datetime import date
from pathlib import Path

import numpy as np

from quantforge_core.cli.main import run_case

HERE = Path(__file__).resolve()
MD = HERE.parents[1] / "07-credit-correlation.md"
REPO = HERE.parents[3]


def golden(suite, case_id):
    with open(REPO / "datasets" / "golden" / suite, encoding="utf-8") as f:
        [c] = [c for c in json.load(f)["cases"] if c["case_id"] == case_id]
    return c


def run(op, inputs):
    r = run_case(json.dumps({"schema_version": "1.0", "case_id": "qb", "operation": op, "inputs": inputs}))
    assert r["status"] == "ok", r
    return r["outputs"]


def rung(suite, case_id):
    c = golden(suite, case_id)
    return c["inputs"], run(c["operation"], c["inputs"])


checks = []
chk = checks.append

# Q7.1, Q7.2, Q7.8: bootstrap (credit_d-0001) and a 25% recovery variant
i, boot = rung("stage_d/credit_d.json", "credit_d-0001")
surv = {p["date"]: p["survival"] for p in boot["pillars"]}
chk(f"Q(2031-12-20) = {surv['2031-12-20']:.6f}")
t5 = (date(2031, 12, 20) - date(2026, 11, 6)).days / 365
chk(f"{t5:.4f} years")
chk(f"exp(-0.02 x {t5:.4f}) = {math.exp(-0.02 * t5):.6f}")
b25 = run("credit.cds.bootstrap", {**i, "recovery": 0.25})
s25 = {p["date"]: p["survival"] for p in b25["pillars"]}
chk(f"rises to {s25['2031-12-20']:.6f}")
chk(f"10-year survival {surv['2036-12-20']:.6f}")

# Q7.4, Q7.9: price (credit_d-0004)
_, p = rung("stage_d/credit_d.json", "credit_d-0004")
chk(f"protection leg {p['protection_leg']:.6f}")
chk(f"rpv01 {p['rpv01']:.6f}")
chk(f"accrued {p['accrued']:.6f}")
chk(f"upfront {p['upfront']:.6f}")
chk(f"PV {p['pv']:,.2f}")
chk(f"par spread {p['par_spread']:.6f}")

# Q7.10 composite (credit_d-0011)
_, comp = rung("stage_d/credit_d.json", "credit_d-0011")
chk(f"5Y sector spread {comp['spreads'][3]:.6f}")
chk(f"sector 5Y survival {comp['pillars'][3]['survival']:.6f}")

# Q7.11 index intrinsic (credit_d-0009)
ii, ix = rung("stage_d/credit_d.json", "credit_d-0009")
chk("name upfronts " + ", ".join(f"{u:.6f}" for u in ix["name_upfronts"]))
chk(f"intrinsic upfront {ix['intrinsic_upfront']:.6f}")
chk(f"quoted upfront {ii['quoted_upfront']:.6f}")
chk(f"basis {ix['basis']:.6f}")

# Q7.5 validate, Q7.13 nearest
_, v = rung("stage_e_b/corr_e.json", "corr_e-0001")
chk(f"min_eigenvalue = {v['min_eigenvalue']:.6f}")
_, n = rung("stage_e_b/corr_e.json", "corr_e-0002")
chk(f"pairs 1-2 and 2-3 {n['matrix'][0][1]:.6f}")
chk(f"pair 1-3 {n['matrix'][0][2]:.6f}")
chk(f"Frobenius distance {n['frobenius_distance']:.6f}")
M = np.array([[1.0, 1, 0], [1, 1, 1], [0, 1, 1]])
w, V = np.linalg.eigh(M)
C = V @ np.diag(np.maximum(w, 0)) @ V.T
d = np.sqrt(np.diag(C))
C = C / np.outer(d, d)
chk(f"clip-and-rescale gives {C[0, 1]:.6f} and {C[0, 2]:.6f}")
chk(f"at distance {np.linalg.norm(C - M):.6f}")

# Q7.6 implied, Q7.14 dispersion
_, im = rung("stage_e_b/corr_e.json", "corr_e-0036")
chk(f"correlation = {im['correlation']:.6f}")
_, dp = rung("stage_e_b/corr_e.json", "corr_e-0046")
chk(f"P&L {dp['pnl']:,.2f}")
chk(f"implied correlation {dp['implied_correlation']:.6f}")
chk(f"realised correlation {dp['realized_correlation']:.6f}")
chk(f"N_2 = {dp['constituent_variance_notionals'][1]:,.2f}")
chk(f"N_I = {dp['index_variance_notional']:,.2f}")

# Q7.7, Q7.15 copulas
_, g0 = rung("stage_e_b/creditopt_e.json", "creditopt_e-0155")
chk(f"joint = {g0['joint_default_probability']:.6f}")
_, g = rung("stage_e_b/creditopt_e.json", "creditopt_e-0147")
_, t = rung("stage_e_b/creditopt_e.json", "creditopt_e-0151")
chk(f"Gaussian joint {g['joint_default_probability']:.6f}")
chk(f"Student t joint {t['joint_default_probability']:.6f}")
chk(f"default correlation {g['default_correlation']:.4f}")
chk(f"against {t['default_correlation']:.4f}")
_, t0 = rung("stage_e_b/creditopt_e.json", "creditopt_e-0154")
chk(f"joint default {t0['joint_default_probability']:.6f}")

# Q7.12 CDS option, Q7.19 implied vol
oi, o = rung("stage_e_b/creditopt_e.json", "creditopt_e-0001")
chk(f"forward spread {o['forward_spread']:.6f}")
chk(f"risky annuity {o['risky_annuity']:.6f}")
chk(f"price {o['price']:,.2f}")
chk(f"front-end protection {o['front_end_protection']:,.2f}")
nk = run("credit.cdsoption.price", {**oi, "knock_out": False})
chk(f"non-knock-out payer {nk['price']:,.2f}")
_, r = rung("stage_e_b/creditopt_e.json", "creditopt_e-0003")
chk(f"receiver at 0.96% {r['price']:,.2f}")
_, iv = rung("stage_e_b/creditopt_e.json", "creditopt_e-0002")
chk(f"implied vol {iv['vol']:.6f}")

# Q7.16 index option (cdsidx_f-0001, -0002)
ci, cp = rung("stage_f/cdsidx_f.json", "cdsidx_f-0001")
_, cr = rung("stage_f/cdsidx_f.json", "cdsidx_f-0002")
chk(f"F = {cp['forward_spread']:.6f}")
chk(f"F_adj = {cp['adjusted_forward']:.6f}")
chk(f"K_adj = {cp['adjusted_strike']:.6f}")
chk(f"A = {cp['risky_annuity']:.6f}")
chk(f"A_K = {cp['strike_annuity']:.6f}")
chk(f"h_K = {cp['strike_hazard']:.6f}")
chk(f"payer {cp['price']:,.2f}")
chk(f"receiver {cr['price']:,.2f}")
par = ci["notional"] * cp["risky_annuity"] * (cp["adjusted_forward"] - cp["adjusted_strike"])
chk(f"N A (F_adj - K_adj) = {par:,.2f}")
chk(f"payer minus receiver {cp['price'] - cr['price']:,.2f}")
chk(f"FEP {cp['front_end_protection']:,.2f}")

# Q7.17 LHP tranches
base = golden("stage_e_b/creditopt_e.json", "creditopt_e-0161")["inputs"]
total = 0.0
for a, dd in [(0, 0.03), (0.03, 0.07), (0.07, 0.10), (0.10, 0.15), (0.15, 0.30), (0.30, 1.0)]:
    el = run("credit.lhp.tranche_loss", {**base, "attachment": a, "detachment": dd})["expected_loss_fraction"]
    total += el * (dd - a)
    chk(f"{a * 100:g}-{dd * 100:g}%: {el * 100:.4f}%")
chk(f"width-weighted sum {total * 100:.6f}%")

# Q7.18 LHP cdf
_, lc = rung("stage_e_b/creditopt_e.json", "creditopt_e-0167")
chk(f"P(L <= 1%) = {lc['cdf'][1]:.6f}")
chk(f"P(L <= 5%) = {lc['cdf'][3]:.6f}")
chk(f"P(L <= 20%) = {lc['cdf'][5]:.6f}")

# Q7.20 credit hedge (tutorial 19 inputs)
from quantforge_core import credit_correlation_hedges as cch  # noqa: E402
from quantforge_core.curves import CurveData  # noqa: E402

with open(REPO / "examples" / "hedge_credit_i.json", encoding="utf-8") as f:
    c = json.load(f)["inputs"]
day = date.fromisoformat
disc = c["discount"]
discount = CurveData(day(disc["as_of"]), disc["interpolation"], tuple(day(q["date"]) for q in disc["pillars"]),
                     tuple(q["discount_factor"] for q in disc["pillars"]))
hz = c["hazard"]
res = cch.credit_cds(day(c["trade_date"]), discount, day(hz["as_of"]), [day(q["date"]) for q in hz["pillars"]],
                     [q["survival"] for q in hz["pillars"]], c["recovery"],
                     [(day(x["maturity"]), x["coupon"], x["notional"], x["side"]) for x in c["book"]],
                     [(day(h["maturity"]), h["coupon"]) for h in c["hedges"]], c["targets"])
chk(f"CS01 {res['book']['cs01']:,.2f}")
chk(f"JTD {res['book']['jtd']:,.2f}")
chk(f"3-year {res['notionals'][0]:,.2f}")
chk(f"10-year {res['notionals'][1]:,.2f}")
chk("buckets " + ", ".join(f"{b + 0.0:,.2f}" for b in res["after"]["buckets"]))

if "--dump" in sys.argv:
    print("\n".join(checks))
    sys.exit(0)
text = MD.read_text(encoding="utf-8")
missing = [s for s in checks if s not in text]
assert not missing, "missing in md:\n" + "\n".join(missing)
print(f"v07 OK: {len(checks)} checks")
