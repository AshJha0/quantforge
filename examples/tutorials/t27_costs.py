"""Tutorial 27: what costs do to a backtest. One rule, a cost sweep, the break-even spread,
the price of a slower execution and of trading less often.

  uv run --project python python examples/tutorials/t27_costs.py         # Python
  python examples/tutorials/t27_costs.py rust/target/release/quantforge  # or any other build

It sends the cases of docs/getting-started/tutorial-27-what-costs-do-to-a-backtest.md through
examples/tutorials/qf.py, to the Python package or to the build named, and prints the page's lines.
"""
import math
import random
import sys

from qf import connect


def num(value, places):
    return f"{round(value, places) + 0.0:.{places}f}"  # + 0.0 prints -0.0 as 0.0


def prices():
    # 250 synthetic closes: a slow cycle of period 50 bars plus noise from a seeded generator. Not market data.
    rng = random.Random(27)
    return [round(100.0 + 3.0 * math.sin(2 * math.pi * t / 50) + rng.gauss(0.0, 0.6), 4) for t in range(250)]


def trend_rule(p, lookback):
    # Hold +10 units after a rise over the last `lookback` bars, -10 after a fall: uses closes up to t only.
    return [0.0 if t < lookback else (10.0 if p[t] > p[t - lookback] else -10.0) for t in range(len(p))]


def main(cli):
    call = connect(cli)
    p = prices()
    targets = trend_rule(p, 5)

    # 1. No costs, then a sweep of the half spread with a fixed commission.
    base = {"prices": p, "targets": targets, "lag": 1}
    r = call("research.backtest.run", base)
    print(f"no costs: gross {num(r['total_gross'], 2)}  trades {r['trade_count']}"
          f"  turnover {num(r['turnover'], 1)}  max drawdown {num(r['max_drawdown'], 2)}")
    gross, turnover = r["total_gross"], r["turnover"]
    units = sum(abs(d) for d in r["trades"])
    for bps in (0.0, 5.0, 10.0, 20.0):
        r = call("research.backtest.run", {**base, "half_spread_bps": bps, "commission_per_unit": 0.01})
        print(f"half spread {num(bps, 0)} bp: spread {num(r['total_spread_cost'], 2)}"
              f"  commission {num(r['total_commission'], 2)}  net {num(r['total_net'], 2)}")

    # 2. Break-even: spread cost is linear in the half spread, so solve net = 0 for it.
    commission = 0.01 * units
    breakeven = (gross - commission) / (turnover * 1e-4)
    r = call("research.backtest.run", {**base, "half_spread_bps": breakeven, "commission_per_unit": 0.01})
    print(f"break-even half spread {num(breakeven, 2)} bp: net {num(r['total_net'], 6)}")

    # 3. Execute one bar later (lag 2), and trade only on a slower signal (lookback 10).
    for name, run in (("lag 2", {**base, "lag": 2}),
                      ("lookback 10", {**base, "targets": trend_rule(p, 10)})):
        r = call("research.backtest.run", {**run, "half_spread_bps": 5.0, "commission_per_unit": 0.01})
        print(f"{name}: gross {num(r['total_gross'], 2)}  cost"
              f" {num(r['total_spread_cost'] + r['total_commission'], 2)}  net {num(r['total_net'], 2)}"
              f"  trades {r['trade_count']}")

    # 4. The two engines agree on the costed run (J-3).
    run = {**base, "half_spread_bps": 5.0, "commission_per_unit": 0.01, "fixed_per_trade": 0.5}
    e, v = call("research.backtest.run", run), call("research.backtest.run", {**run, "engine": "VECTOR"})
    same = all(abs(a - b) <= 1e-10 * max(1.0, abs(a)) for a, b in zip(e["equity"], v["equity"]))
    print(f"EVENT and VECTOR: net {num(e['total_net'], 2)} and {num(v['total_net'], 2)}"
          f"  equity agrees to 1e-10 on every bar: {same}")


if __name__ == "__main__":
    main(sys.argv[1:])
