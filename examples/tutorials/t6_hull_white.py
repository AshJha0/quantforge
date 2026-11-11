"""Tutorial 6: Hull-White bond option, a Jamshidian swaption, sigma calibrated to swaptions, a Bermudan.

  uv run --project python python examples/tutorials/t6_hull_white.py         # Python
  python examples/tutorials/t6_hull_white.py rust/target/release/quantforge  # or any other build
"""
import sys

from qf import connect

call = connect(sys.argv[1:])

# 1. Today's discount curve by time in years (ACT/365F), and Hull-White with a = 5%, sigma = 1%.
curve = {"times": [0.4986301369863014, 1.0, 2.0, 3.0, 5.002739726027397, 7.005479452054795,
                   10.005479452054795, 15.01095890410959, 20.013698630136986, 30.019178082191782],
         "discount_factors": [0.98085, 0.9619, 0.9254, 0.8906, 0.8242, 0.762, 0.6787, 0.561, 0.467, 0.332]}
hw = {"curve": curve, "mean_reversion": 0.05, "sigma": 0.01}

# 2. A one-year call, strike 0.86, on a zero-coupon bond maturing in year 5; notional 1 million.
z = call("rates.shortrate.zcb_option", {"model": "HULL_WHITE", **hw, "option_type": "CALL", "strike": 0.86,
                                        "expiry_years": 1.0, "maturity_years": 5.0, "notional": 1_000_000.0})
print(f"bond option {z['price']:.4f}  P(0,1) {z['bond_price_expiry']:.6f}  P(0,5) {z['bond_price_maturity']:.6f}")

# 3. A European payer swaption, 1 year into a 5-year annual swap, struck at 3.4462%: Jamshidian's method.
swap = {"payment_times": [2.0, 3.0, 4.0, 5.0, 6.0], "fixed_rate": 0.034462, "swaption_type": "PAYER",
        "notional": 1_000_000.0}
e = call("rates.shortrate.swaption", {**hw, "expiry_years": 1.0, **swap})
print(f"European {e['price']:.4f}  forward swap rate {e['forward_swap_rate']:.8f}  annuity {e['annuity']:.2f}")

# 4. Calibrate sigma (a fixed at 5%) to five co-terminal swaption prices per unit notional.
strip = [(1.0, 0.03948, 0.027739189051503528), (2.0, 0.039486, 0.03302750501350072),
         (3.0, 0.039554, 0.035288652993578785), (5.0, 0.039604, 0.030395873006313835),
         (7.0, 0.039345, 0.021061314962415565)]
swaptions = [{"expiry_years": t, "payment_times": [float(y) for y in range(int(t) + 1, 11)], "fixed_rate": k,
              "swaption_type": "PAYER", "target_price": p} for t, k, p in strip]
cal = call("rates.shortrate.hw_calibrate", {"curve": curve, "mean_reversion": 0.05, "swaptions": swaptions})
print(f"calibrated sigma {cal['sigma']:.8f}  rmse {cal['rmse']:.8f}")
for s, fitted in zip(swaptions, cal["fitted_prices"]):
    print(f"  {s['expiry_years']:.0f}Y expiry  target {s['target_price']:.6f}  fitted {fitted:.6f}")

# 5. The Bermudan: the same swap, but exercisable on every reset date from year 1 to year 5.
grid = {"nx": 201, "steps_per_year": 100, "width": 6.0}
b = call("rates.shortrate.bermudan_swaption", {**hw, "start_years": 1.0, **swap,
                                               "exercise_times": [1.0, 2.0, 3.0, 4.0, 5.0], "grid": grid})
print(f"Bermudan {b['price']:.4f}  exercise premium over the European {b['price'] - e['price']:.4f}")
