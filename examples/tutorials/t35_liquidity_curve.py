"""Tutorial 35: a liquidity cost curve by order size and liquidation horizon: half spread,
square-root impact, timing risk and the cost-minimising horizon.

  uv run --project python python examples/tutorials/t35_liquidity_curve.py         # Python
  python examples/tutorials/t35_liquidity_curve.py rust/target/release/quantforge  # or any other build

It sends the cases of docs/getting-started/tutorial-35-liquidity-curve.md through
examples/tutorials/qf.py, to the Python package or to the build named, and prints the page's lines.
"""
import sys

from qf import connect


def bp(values):
    return " ".join(f"{x * 1e4:.2f}" for x in values)


def main(cli):
    call = connect(cli)  # the Python package with no arguments, else that build's batch command
    stock = {"half_spread_bps": 5.0, "daily_volume": 1.0e7, "daily_vol": 0.02}

    # 1. The hand case: 1 % of a day's volume in one day costs 20 bp of impact.
    r = call("liq.curve.cost", {**stock, "sizes": [1.0e5, 4.0e5], "horizons_days": [1.0, 4.0]})
    print(f"impact (bp), rows 1e5 and 4e5, columns 1 and 4 days: {bp(r['impact'][0])} | {bp(r['impact'][1])}")
    print(f"total (bp): {bp(r['total_cost'][0])} | {bp(r['total_cost'][1])}  optimum {r['optimal_horizon']}")

    # 2. Add timing risk at z = 1.645 and read the curve over horizons for one order of 1e6.
    h = [0.25, 0.5, 1, 2, 5, 10, 20]
    r = call("liq.curve.cost", {**stock, "risk_multiplier": 1.645, "sizes": [1.0e6], "horizons_days": h})
    print(f"horizons (days):  {' '.join(str(x) for x in h)}")
    print(f"impact (bp):      {bp(r['impact'][0])}")
    print(f"timing risk (bp): {bp(r['timing_risk'])}")
    print(f"total (bp):       {bp(r['total_cost'][0])}")
    print(f"optimal horizon {r['optimal_horizon'][0]:.4f} days  minimum {r['min_cost'][0] * 1e4:.2f} bp")

    # 3. The optimum by size: larger orders should be worked for longer.
    r = call("liq.curve.cost", {**stock, "risk_multiplier": 1.645, "sizes": [1e4, 1e5, 1e6, 5e6], "horizons_days": [1]})
    print(f"optimal horizon by size (days): {' '.join(f'{x:.4f}' for x in r['optimal_horizon'])}")
    print(f"minimum cost by size (bp):      {bp(r['min_cost'])}")

    # 4. The 3/5 exponent of Almgren et al.: the optimum moves.
    r = call("liq.curve.cost", {**stock, "risk_multiplier": 1.645, "exponent": 0.6, "sizes": [1.0e6], "horizons_days": [1]})
    print(f"delta 0.6: optimal horizon {r['optimal_horizon'][0]:.4f} days  minimum {r['min_cost'][0] * 1e4:.2f} bp")


if __name__ == "__main__":
    main(sys.argv[1:])
