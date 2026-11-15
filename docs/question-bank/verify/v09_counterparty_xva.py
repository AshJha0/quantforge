"""Recompute every worked-example number in 09-counterparty-xva.md and check it appears there.

Run from the repository's python directory:
    PYTHONPATH=. python ../docs/question-bank/verify/v09_counterparty_xva.py
Add --dump to print the expected strings without checking.
"""
import json
import math
import sys
from pathlib import Path

from quantforge_core.cli.main import run_case

HERE = Path(__file__).resolve()
MD = HERE.parents[1] / "09-counterparty-xva.md"
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

CURVE = {"times": [0.4986301369863014, 1.0, 2.0, 3.0, 5.002739726027397, 7.005479452054795,
                   10.005479452054795, 15.01095890410959, 20.013698630136986, 30.019178082191782],
         "discount_factors": [0.98085, 0.9619, 0.9254, 0.8906, 0.8242, 0.762, 0.6787, 0.561, 0.467, 0.332]}


def P(t):  # log-linear discount factor on CURVE (scratch formula, as tutorial 7)
    ts, ds = [0.0] + CURVE["times"], [1.0] + CURVE["discount_factors"]
    for k in range(1, len(ts)):
        if t <= ts[k]:
            w = (t - ts[k - 1]) / (ts[k] - ts[k - 1])
            return math.exp((1 - w) * math.log(ds[k - 1]) + w * math.log(ds[k]))
    raise ValueError(t)


# Q9.1, Q9.2, Q9.3, Q9.5: tutorial 7 swap
swap = {"notional": 10_000_000.0, "fixed_rate": 0.039, "side": "PAY", "start_years": 0.0,
        "payment_times": [1.0, 2.0, 3.0, 4.0, 5.0]}
dates = [1.0, 2.0, 3.0, 4.0]
base = {"curve": CURVE, "mean_reversion": 0.03, "sigma": 0.005, "exposure_times": dates, "pfe_quantiles": [0.95],
        "hazard_rate": 0.02, "recovery": 0.4}
x = run("xva.exposure.portfolio_hw", {**base, "trades": [swap]})
chk("discounted EE " + ", ".join(f"{v:,.2f}" for v in x["discounted_ee"]))
chk("discounted ENE " + ", ".join(f"{v:,.2f}" for v in x["discounted_ene"]))
chk(f"EE + ENE = {x['discounted_ee'][0] + x['discounted_ene'][0]:,.2f}")
fv1 = 1e7 * (P(1) - P(5) - 0.039 * sum(P(j) for j in (2, 3, 4, 5)))
chk(f"forward value {fv1:,.2f}")
chk(f"deflated_pfe_95 {x['deflated_pfe_95'][0]:,.2f}")
chk(f"EPE {x['epe']:,.2f}")
chk(f"CVA {x['cva']:,.2f}")
guess = 0.6 * (1 - math.exp(-0.02)) * sum(x["discounted_ee"])
chk(f"first guess {guess:,.0f}")

# Q9.4 netting
times = [0.0, 0.5, 1.0]
ta = [[0.0, 4.0, 6.0], [0.0, -3.0, -5.0]]
tb = [[0.0, -3.0, -4.0], [0.0, 2.0, 3.0]]
one = run("xva.exposure.collateralised", {"times": times, "pfe_quantile": 1.0,
                                          "trades": [{"netting_set": "NS1", "values": ta},
                                                     {"netting_set": "NS1", "values": tb}]})
two = run("xva.exposure.collateralised", {"times": times, "pfe_quantile": 1.0,
                                          "trades": [{"netting_set": "NS1", "values": ta},
                                                     {"netting_set": "NS2", "values": tb}]})
chk("netted total_ee " + ", ".join(f"{v:.2f}" for v in one["total_ee"]))
chk("unnetted total_ee " + ", ".join(f"{v:.2f}" for v in two["total_ee"]))

# Q9.6, Q9.13, Q9.14, Q9.15: collateral (tutorial 7 paths)
ci, c1 = rung("stage_g/collexp_g.json", "collexp_g-0001")
_, c4 = rung("stage_g/collexp_g.json", "collexp_g-0004")
_, c5 = rung("stage_g/collexp_g.json", "collexp_g-0005")
_, c7 = rung("stage_g/collexp_g.json", "collexp_g-0007")
n1, n4, n5, n7 = (c["netting_sets"]["NS1"] for c in (c1, c4, c5, c7))
chk("no CSA EE " + ", ".join(f"{v:.3f}" for v in n1["ee"]))
chk("CSA EE " + ", ".join(f"{v:.3f}" for v in n4["ee"]))
chk(f"no-CSA EPE {n1['epe']:.5f}")
chk(f"lagged CSA EPE {n4['epe']:.5f}")
chk(f"no-lag EPE {n5['epe']:.5f}")
chk(f"zero-threshold EPE {n7['epe']:.5f}")
chk(f"PFE at 0.75 years {n1['pfe'][3]:.3f}")
chk(f"effective EPE {n5['effective_epe']:.5f}")
chk(f"EPE {n5['epe']:.5f}")
dfs = [math.exp(-0.03 * t) for t in ci["times"][1:]]
names = {"counterparty": {"hazard_rate": 0.02, "recovery": 0.4}, "own": {"hazard_rate": 0.0, "recovery": 0.4},
         "funding": {"borrow_spread": 0.0, "lend_spread": 0.0, "exclude_dva_overlap": False}}
for label, r in (("no-CSA CVA", n1), ("CSA CVA", n4)):
    a = run("xva.adjustments.value", {"times": ci["times"][1:], "discount_factors": dfs, "ee": r["ee"][1:],
                                      "ene": r["ene"][1:], **names})
    chk(f"{label} {a['cva']:.6f}")

# Q9.7, Q9.11, Q9.12, Q9.18 adjustments
_, a1 = rung("stage_g/xvaadj_g.json", "xvaadj_g-0001")
_, a2 = rung("stage_g/xvaadj_g.json", "xvaadj_g-0002")
_, a3 = rung("stage_g/xvaadj_g.json", "xvaadj_g-0003")
_, a4 = rung("stage_g/xvaadj_g.json", "xvaadj_g-0004")
_, a5 = rung("stage_g/xvaadj_g.json", "xvaadj_g-0005")
chk(f"CVA {a1['cva']:.6f}")
chk(f"DVA {a1['dva']:.6f}")
chk(f"FCA {a1['fca']:.6f}")
chk(f"FBA {a1['fba']:.6f}")
chk(f"FVA {a1['fva']:.6f}")
chk(f"FBA falls to {a2['fba']:.6f}")
chk(f"FVA rises to {a2['fva']:.6f}")
chk(f"own hazard 0: CVA {a5['cva']:.6f}")
chk(f"DVA {a5['dva']:.1f}")
chk(f"MVA {a3['mva']:.6f}")
chk(f"KVA {a4['kva']:.6f}")

# Q9.8, Q9.9 swap EE under Hull-White
ei, e1 = rung("stage_g/exposure_g.json", "exposure_g-0001")
chk("Jamshidian EE " + ", ".join(f"{v:,.2f}" for v in e1["discounted_ee"]))
chk(f"cva {e1['cva']:,.2f}")
rec = run("xva.exposure.swap_ee_hw", {**ei, "side": "RECEIVE"})
diff = e1["discounted_ee"][0] - rec["discounted_ee"][0]
chk(f"receiver EE at 1 year {rec['discounted_ee'][0]:,.2f}")
chk(f"PAY minus RECEIVE {diff:,.2f}")
fv = 1e7 * (P(1) - P(5) - 0.03 * sum(P(j) for j in (2, 3, 4, 5)))
chk(f"forward value of the remaining swap {fv:,.2f}")

# Q9.16 WWR
for cid in ("wwr_g-0001", "wwr_g-0002", "wwr_g-0003", "wwr_g-0004"):
    wi, w = rung("stage_g/wwr_g.json", cid)
    chk(f"b = {wi['wwr_b']:g}: CVA {w['cva']:.6f}")

# Q9.17 SIMM
_, s2 = rung("stage_g/simm_g.json", "simm_g-0002")
si = golden("stage_g/simm_g.json", "simm_g-0002")["inputs"]
chk(f"margin {s2['margin']:,.2f}")
sc = run("xva.simm.ir_delta", {**si, "concentration_threshold": 2500.0})
chk(f"concentration_factor {sc['concentration_factor']:.6f}")
chk(f"margin rises to {sc['margin']:,.2f}")
_, s1 = rung("stage_g/simm_g.json", "simm_g-0001")
chk(f"mixed-sign margin {s1['margin']:,.2f}")

# Q9.20 portfolio netting under Hull-White
recv = {**swap, "side": "RECEIVE", "fixed_rate": 0.035, "notional": 5_000_000.0}
xr = run("xva.exposure.portfolio_hw", {**base, "trades": [recv]})
xb = run("xva.exposure.portfolio_hw", {**base, "trades": [swap, recv]})
chk(f"payer alone CVA {x['cva']:,.2f}")
chk(f"receiver alone CVA {xr['cva']:,.2f}")
chk(f"netted CVA {xb['cva']:,.2f}")
chk(f"netted EE at 1 year {xb['discounted_ee'][0]:,.2f}")
chk(f"netted ENE at 1 year {xb['discounted_ene'][0]:,.2f}")
s = xb["discounted_ee"][0] + xb["discounted_ene"][0]
s_sum = x["discounted_ee"][0] + x["discounted_ene"][0] + xr["discounted_ee"][0] + xr["discounted_ene"][0]
chk(f"EE + ENE {s:,.2f}")
chk(f"sum of the two trades' EE + ENE {s_sum:,.2f}")

if "--dump" in sys.argv:
    print("\n".join(checks))
    sys.exit(0)
text = MD.read_text(encoding="utf-8")
missing = [s for s in checks if s not in text]
assert not missing, "missing in md:\n" + "\n".join(missing)
print(f"v09 OK: {len(checks)} checks")
