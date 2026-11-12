"""Tutorial 7: a swap's exposure profile (EE, PFE), its CVA, then what a collateral agreement changes.

  uv run --project python python examples/tutorials/t7_counterparty.py       # Python
  python examples/tutorials/t7_counterparty.py rust/target/release/quantforge  # or any other build
"""
import math
import sys

from qf import connect

call = connect(sys.argv[1:])

# 1. Hull-White (a = 3%, sigma = 0.5%) on tutorial 6's curve. We pay 3.9% fixed on 10 million for 5 years,
#    annual payments; the counterparty has a 2% a year default intensity and 40% recovery.
curve = {"times": [0.4986301369863014, 1.0, 2.0, 3.0, 5.002739726027397, 7.005479452054795,
                   10.005479452054795, 15.01095890410959, 20.013698630136986, 30.019178082191782],
         "discount_factors": [0.98085, 0.9619, 0.9254, 0.8906, 0.8242, 0.762, 0.6787, 0.561, 0.467, 0.332]}
swap = {"notional": 10_000_000.0, "fixed_rate": 0.039, "side": "PAY", "start_years": 0.0,
        "payment_times": [1.0, 2.0, 3.0, 4.0, 5.0]}
dates = [1.0, 2.0, 3.0, 4.0]  # the reset dates: each just after a payment
x = call("xva.exposure.portfolio_hw", {"curve": curve, "mean_reversion": 0.03, "sigma": 0.005, "trades": [swap],
                                       "exposure_times": dates, "pfe_quantiles": [0.95],
                                       "hazard_rate": 0.02, "recovery": 0.4})
print("  t    discounted EE   discounted ENE   PFE 95%")
for t, ee, ene, pfe in zip(dates, x["discounted_ee"], x["discounted_ene"], x["deflated_pfe_95"]):
    print(f"{t:4.1f} {ee:15.2f} {ene:16.2f} {pfe:10.2f}")
print(f"EPE {x['epe']:.2f}  CVA {x['cva']:.2f}")

# 2. Collateral, shown on four hand-written scenarios so every number can be checked by hand:
#    the netting set's value on each path at 0, 3, 6, 9 and 12 months.
times = [0.0, 0.25, 0.5, 0.75, 1.0]
paths = [[0.0, 3.0, 5.0, 2.0, -1.0], [0.0, -2.0, -4.0, -6.0, -3.0],
         [0.0, 1.0, 6.0, 9.0, 4.0], [0.0, 0.5, -1.0, 2.5, 7.0]]
trades = [{"netting_set": "NS1", "values": paths}]
csa = {"NS1": {"threshold_receive": 1.0, "threshold_post": 1.0, "minimum_transfer_amount": 0.5, "mpor_steps": 1}}
bare = call("xva.exposure.collateralised", {"times": times, "trades": trades, "pfe_quantile": 0.75})["netting_sets"]["NS1"]
held = call("xva.exposure.collateralised", {"times": times, "trades": trades, "pfe_quantile": 0.75,
                                            "csa": csa})["netting_sets"]["NS1"]
for name, r in [("no CSA", bare), ("CSA   ", held)]:
    print(f"{name}  EE " + " ".join(f"{v:.3f}" for v in r["ee"]) + f"  EPE {r['epe']:.5f}")

# 3. CVA of each profile: counterparty 2% intensity, 40% recovery, flat 3% continuous discounting.
#    Our own default intensity is set to 0, so this is the unilateral CVA.
dfs = [math.exp(-0.03 * t) for t in times[1:]]
names = {"counterparty": {"hazard_rate": 0.02, "recovery": 0.4}, "own": {"hazard_rate": 0.0, "recovery": 0.4},
         "funding": {"borrow_spread": 0.0, "lend_spread": 0.0, "exclude_dva_overlap": False}}
for name, r in [("no CSA", bare), ("CSA   ", held)]:
    a = call("xva.adjustments.value", {"times": times[1:], "discount_factors": dfs, "ee": r["ee"][1:],
                                       "ene": r["ene"][1:], **names})
    print(f"{name}  CVA {a['cva']:.6f}")
