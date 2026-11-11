"""Tutorial 5: AAD against bump-and-revalue, historical VaR and ES with a backtest, an FRTB delta charge.

  uv run --project python python examples/tutorials/t5_risk.py               # Python
  python examples/tutorials/t5_risk.py rust/target/release/quantforge        # or any other build
"""
import json
import sys

from qf import connect

call = connect(sys.argv[1:])

# 1. A Bermudan payer swaption under Hull-White (a = 5%, sigma = 1%), exercisable yearly from year 1
#    into a swap ending in year 6. Price and full sensitivity ladder in one reverse (AAD) sweep.
curve = {"times": [0.4986301369863014, 1.0, 2.0, 3.0, 5.002739726027397, 7.005479452054795,
                   10.005479452054795, 15.01095890410959, 20.013698630136986, 30.019178082191782],
         "discount_factors": [0.98085, 0.9619, 0.9254, 0.8906, 0.8242, 0.762, 0.6787, 0.561, 0.467, 0.332]}
deal = {"mean_reversion": 0.05, "sigma": 0.01, "curve": curve, "notional": 1_000_000.0, "start_years": 1.0,
        "payment_times": [2.0, 3.0, 4.0, 5.0, 6.0], "fixed_rate": 0.039462, "swaption_type": "PAYER",
        "exercise_times": [1.0, 2.0, 3.0, 4.0, 5.0], "grid": {"nx": 101, "steps_per_year": 50, "width": 6.0}}
aad = call("rates.shortrate.bermudan_ladder", deal)
print(f"Bermudan price {aad['price']:.4f}")
print(f"AAD   dV/dsigma {aad['d_price_d_sigma']:.2f}  dV/da {aad['d_price_d_mean_reversion']:.2f}")

# 2. The same two numbers by bump-and-revalue: reprice with the input 0.01% up and down (central difference).
def bumped(key):
    h = deal[key] * 1e-4
    up = call("rates.shortrate.bermudan_swaption", {**deal, key: deal[key] + h})["price"]
    down = call("rates.shortrate.bermudan_swaption", {**deal, key: deal[key] - h})["price"]
    return (up - down) / (2 * h)

print(f"bump  dV/dsigma {bumped('sigma'):.2f}  dV/da {bumped('mean_reversion'):.2f}")

# 3. Historical VaR and ES at 99% from 250 days of daily P&L (synthetic; golden case risk_f4-0003).
with open("datasets/golden/stage_f/risk_f4.json", encoding="utf-8") as f:
    [case] = [c for c in json.load(f)["cases"] if c["case_id"] == "risk_f4-0003"]
pnl = case["inputs"]["pnl"]
first, second = pnl[:250], pnl[250:]
v = call("risk.var.historical", {"pnl": first, "confidence": 0.99})
print(f"VaR 99% {v['var']:.2f}  ES 99% {v['es']:.2f}  tail days {v['tail_count']}")

# 4. Backtest: on the next 250 days, count the losses larger than that VaR, then test the count.
exceptions = sum(1 for x in second if -x > v["var"])
k = call("risk.backtest.kupiec", {"observations": 250, "exceptions": exceptions, "confidence": 0.99})
t = call("risk.backtest.traffic_light", {"observations": 250, "exceptions": exceptions, "confidence": 0.99})
print(f"exceptions {exceptions} of 250  Kupiec LR {k['lr_uc']:.4f}  p-value {k['p_value']:.4f}")
print(f"traffic light {t['zone']}  cumulative probability {t['cumulative_probability']:.4f}  plus factor {t['plus_factor']:.2f}")

# 5. FRTB GIRR delta: tutorial 1's swap key-rate DV01s, as MAR21 sensitivities (DV01 / 0.0001).
quotes = [{"tenor": n, "rate": r} for n, r in
          [("1Y", 0.035), ("2Y", 0.0335), ("3Y", 0.033), ("5Y", 0.0335), ("7Y", 0.0345), ("10Y", 0.036)]]
swap = {"convention": "SOFR", "tenor": "5Y", "fixed_rate": 0.034, "notional": 10_000_000.0, "side": "PAY"}
kr = call("risk.ois.dv01", {"as_of": "2026-11-06", "quotes": quotes, "interpolation": "LOG_LINEAR_DF",
                            "trade": swap})["key_rate"]
rows = [{"currency": "USD", "curve": "SOFR", "risk_factor": q["tenor"], "sensitivity": d / 0.0001}
        for q, d in zip(quotes, kr) if d != 0.0]
frtb = call("risk.frtb.girr_delta", {"sensitivities": rows, "specified_currency_reduction": False})
print("GIRR sensitivities " + " ".join(f"{r['risk_factor']}:{r['sensitivity']:.0f}" for r in rows))
print(f"GIRR delta capital {frtb['capital']:.2f}  binding scenario {frtb['binding_scenario']}")
