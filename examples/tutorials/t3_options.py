"""Tutorial 3: Black-Scholes price and Greeks, implied volatility, a SABR smile and a vol surface.

  uv run --project python python examples/tutorials/t3_options.py            # Python
  python examples/tutorials/t3_options.py rust/target/release/quantforge     # or any other build
"""
import sys

from qf import connect

call = connect(sys.argv[1:])

# 1. A one-year at-the-money call on a stock at 100: 3% rate, 1% dividend yield, 20% volatility.
option = {"model": "BLACK_SCHOLES", "option_type": "CALL", "strike": 100.0, "expiry_years": 1.0,
          "spot": 100.0, "rate": 0.03, "yield": 0.01}
g = call("risk.vol.greeks", {**option, "vol": 0.2})
print(f"price {g['price']:.6f}  delta {g['delta']:.6f}  gamma {g['gamma']:.6f}")
print(f"vega  {g['vega']:.6f}  theta {g['theta']:.6f}  rho {g['rho']:.6f}")

# 2. Implied volatility: the market quotes the same call at 9.50. Which volatility gives that price?
iv = call("vol.option.implied", {**option, "price": 9.5})
print(f"implied vol at 9.50  {iv['vol']:.8f}")

# 3. A SABR smile (beta = 0.5) fitted to seven quoted vols, one-year expiry, forward 100.
strikes = [60.0, 75.0, 90.0, 100.0, 110.0, 125.0, 150.0]
vols = [0.4277311493595516, 0.3703805829578223, 0.32676467971358686, 0.30442125000000003,
        0.28724831699910025, 0.27059495038968, 0.26158130822689635]
fit = call("vol.sabr.calibrate", {"forward": 100.0, "expiry_years": 1.0, "beta": 0.5,
                                  "strikes": strikes, "vols": vols})
print(f"SABR  alpha {fit['alpha']:.4f}  rho {fit['rho']:.4f}  nu {fit['nu']:.4f}")
smile = call("vol.sabr.hagan", {"forward": 100.0, "expiry_years": 1.0, "beta": 0.5, "alpha": fit["alpha"],
                                "rho": fit["rho"], "nu": fit["nu"], "strikes": [80.0, 100.0, 120.0]})
print("smile at 80, 100, 120  " + "  ".join(f"{v:.5f}" for v in smile["vols"]))

# 4. A vol surface: a grid of vols by expiry (years) and log-moneyness ln(K/F); read three points.
surface = {"expiry_years": [0.2, 0.4, 1.0, 2.0], "log_moneyness": [-0.4, -0.2, 0.0, 0.2, 0.4],
           "vols": [[0.32, 0.27, 0.23, 0.22, 0.23], [0.3, 0.26, 0.225, 0.215, 0.22],
                    [0.285, 0.25, 0.22, 0.21, 0.215], [0.27, 0.24, 0.215, 0.205, 0.21]]}
points = [{"expiry_years": 1.0, "log_moneyness": 0.0}, {"expiry_years": 0.7, "log_moneyness": 0.0},
          {"expiry_years": 0.7, "log_moneyness": -0.1}]
q = call("vol.surface.query", {"surface": surface, "points": points})
for pt, v, w in zip(points, q["vols"], q["total_variance"]):
    print(f"surface T={pt['expiry_years']} k={pt['log_moneyness']:+.1f}  vol {v:.6f}  total variance {w:.6f}")
