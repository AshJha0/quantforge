"""Tutorial 4: bootstrap an ISDA CDS curve, price a CDS, read survival, build a sector curve.

  uv run --project python python examples/tutorials/t4_credit.py             # Python
  python examples/tutorials/t4_credit.py rust/target/release/quantforge      # or any other build
"""
import sys

from qf import connect

call = connect(sys.argv[1:])

# 1. Market data (synthetic): a flat discount curve, 40% recovery, par spreads for six CDS tenors.
trade_date = "2026-11-06"
discount = {"as_of": trade_date, "interpolation": "LOG_LINEAR_DF",
            "pillars": [{"date": "2046-11-06", "discount_factor": 0.458161174870904}]}
spreads = [("6M", 0.0045), ("1Y", 0.006), ("3Y", 0.009), ("5Y", 0.012), ("7Y", 0.0135), ("10Y", 0.015)]
quotes = [{"tenor": t, "spread": s} for t, s in spreads]
market = {"trade_date": trade_date, "discount": discount, "recovery": 0.4}

# 2. Bootstrap: find the survival curve under which every quoted CDS is worth zero at its par spread.
curve = call("credit.cds.bootstrap", {**market, "quotes": quotes})
for p in curve["pillars"]:
    print(f"survival to {p['date']}  {p['survival']:.8f}")

# 3. Price: buy 10 million of 5Y protection (maturity 2031-12-20) with the standard 100bp coupon.
hazard = {"as_of": trade_date, "pillars": curve["pillars"]}
trade = {"maturity": "2031-12-20", "coupon": 0.01, "notional": 10_000_000.0, "side": "BUY_PROTECTION"}
c = call("credit.cds.price", {**market, "hazard": hazard, "trade": trade, "payout": "STANDARD"})
print(f"CDS pv {c['pv']:.2f}  upfront {c['upfront']:.8f}  par spread {c['par_spread']:.8f}  rpv01 {c['rpv01']:.6f}")

# 4. Sector curve: weighted average of three names' spread curves (weights 2, 1, 1), then bootstrapped.
names = [{"quotes": [{"tenor": t, "spread": s * m} for t, s in spreads], "weight": w}
         for m, w in [(1.0, 2.0), (1.3, 1.0), (0.8, 1.0)]]
sector = call("credit.curve.composite", {**market, "constituents": names, "scale": 1.0})
print("sector spreads " + " ".join(f"{s:.7f}" for s in sector["spreads"]))
print(f"sector 5Y survival {sector['pillars'][3]['survival']:.8f}")
