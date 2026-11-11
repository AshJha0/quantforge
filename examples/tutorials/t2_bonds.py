"""Tutorial 2: a fixed-rate bond off a curve, its yield, duration and convexity, then a repo forward.

  uv run --project python python examples/tutorials/t2_bonds.py              # Python
  python examples/tutorials/t2_bonds.py rust/target/release/quantforge       # or any other build
"""
import sys

from qf import connect

call = connect(sys.argv[1:])

# 1. The discount curve of tutorial 1: SOFR swap quotes, bootstrapped (synthetic, not market data).
quotes = [{"tenor": t, "rate": r} for t, r in
          [("1Y", 0.035), ("2Y", 0.0335), ("3Y", 0.033), ("5Y", 0.0335), ("7Y", 0.0345), ("10Y", 0.036)]]
built = call("rates.ois.bootstrap", {"convention": "SOFR", "as_of": "2026-11-06", "quotes": quotes,
                                     "interpolation": "LOG_LINEAR_DF", "method": "SEQUENTIAL"})
curve = {"as_of": "2026-11-06", "interpolation": "LOG_LINEAR_DF", "pillars": built["pillars"]}

# 2. The bond: 4.25% coupon paid twice a year, maturing 2029-11-15; trade settles 2026-11-09.
bond = {"maturity": "2029-11-15", "coupon": 0.0425, "frequency": 2}
settle = "2026-11-09"
p = call("bond.price.from_curve", {"bond": bond, "settlement": settle, "curve": curve})
print(f"curve price  dirty {p['dirty']:.6f}  accrued {p['accrued']:.6f}  clean {p['clean']:.6f}")

# 3. The yield that gives the same clean price, then duration and convexity at that yield.
y = call("bond.yield.from_price", {"bond": bond, "settlement": settle, "clean_price": p["clean"]})
r = call("bond.price.from_yield", {"bond": bond, "settlement": settle, "yield": y["yield"]})
print(f"yield        {y['yield']:.10f}")
print(f"duration     Macaulay {r['macaulay_duration']:.6f}  modified {r['modified_duration']:.6f}")
print(f"convexity    {r['convexity']:.6f}")

# 4. Repo: finance the bond for 30 days at 3.85%, then recover the rate from the forward price.
term = {"bond": bond, "start": settle, "end": "2026-12-09", "clean_price": p["clean"]}
f = call("repo.forward", {**term, "repo_rate": 0.0385, "gc_rate": None})
back = call("repo.implied_rate", {**term, "forward_clean": f["forward_clean"]})
print(f"repo forward dirty {f['forward_dirty']:.6f}  clean {f['forward_clean']:.6f}  interest {f['interest']:.6f}")
print(f"implied repo {back['repo_rate']:.10f}")
