# Tutorial 27: what costs do to a backtest: a cost sweep, the break-even spread, lag and turnover

The plain idea: a backtest without costs answers a question nobody asked. Every trade pays half the bid-ask spread and a commission, so a rule that trades often has to earn more per trade to keep anything. Two numbers tell you how fragile a result is: how much of the gross P&L each extra basis point of spread takes, and the spread at which the strategy earns nothing at all (the break-even spread). If the break-even spread is close to what you would really pay, the result is not robust, however good the gross number looks.

You will run one simple trend rule on 250 synthetic closes with no costs, sweep the half spread from 0 to 20 basis points, solve for the break-even half spread and check it with a run, see what one more bar of execution delay and a slower signal each cost, and confirm that the two backtest engines agree. Python first, then the same cases through the Rust, Java and C++ command-line programs. Budget 15 minutes. All data is synthetic, drawn from a seeded generator; none of it is a trading claim.

Terms, defined here. A **basis point** (bp) is 0.01 %. The **half spread** is half the gap between the bid and the offer: a buyer pays the mid price plus the half spread, a seller receives the mid minus it. **Turnover** is the money value traded, `sum_t |d_t| p_t` for trades `d_t` at prices `p_t`. The **lag** is the number of bars between the decision and the trade. **Gross** P&L is before costs, **net** after.

## What you need

- A clone of the repository, with commands run from its root in Git Bash or a Unix shell.
- [uv](https://docs.astral.sh/uv/), as in [Tutorial 1](tutorial-1-swap.md): `uv sync --locked --project python`.
- For step 2, the three builds made in Tutorial 1. [Tutorial 23](tutorial-23-backtest-honestly.md) introduces the backtester and is useful first.

## Step 1: Python

The script `examples/tutorials/t27_costs.py`, in full (CI checks this listing equals the file):

<!-- tutorial:source examples/tutorials/t27_costs.py -->
```python
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
```

<!-- tutorial:run python -->
```bash
uv run --project python python examples/tutorials/t27_costs.py
```

Real output, 2026-11-15, Windows 11 (Python build):

<!-- tutorial:expect -->
```text
no costs: gross 461.73  trades 47  turnover 93055.8  max drawdown 49.90
half spread 0 bp: spread 0.00  commission 9.30  net 452.43
half spread 5 bp: spread 46.53  commission 9.30  net 405.91
half spread 10 bp: spread 93.06  commission 9.30  net 359.38
half spread 20 bp: spread 186.11  commission 9.30  net 266.32
break-even half spread 48.62 bp: net 0.000000
lag 2: gross 289.79  cost 55.82  net 233.97  trades 47
lookback 10: gross 256.17  cost 22.10  net 234.07  trades 19
EVENT and VECTOR: net 382.41 and 382.41  equity agrees to 1e-10 on every bar: True
```

### Reading the numbers

- **No costs.** The rule holds +10 units after a five-bar rise and -10 after a five-bar fall. It trades 47 times: once to open (10 units) and 46 reversals of 20 units, 930 units in all, with turnover 93,055.8 in money. Gross P&L is 461.73 with a worst drawdown of 49.90. The prices contain a 50-bar cycle by construction, so a trend rule is bound to find something; that is the point of synthetic data with a known answer, not a finding.
- **Each basis point costs the same.** Spread cost is `turnover x half_spread_bps / 10^4`: 93,055.8 x 0.0005 = 46.53 at 5 bp, twice that at 10 bp, four times at 20 bp. Commission is 930 units x 0.01 = 9.30 throughout. Net falls by 9.31 for every extra basis point.
- **Break-even.** Net is zero when `gross - commission = turnover x b / 10^4`, so `b = (461.73 - 9.30) / 9.3056 = 48.62` bp. Running the backtest at that half spread prints a net of 0.000000. On this data the rule survives any spread a liquid market would charge; on real data, with no built-in cycle, the gross figure would be far smaller and the break-even spread with it.
- **One more bar of delay.** With `lag 2` the rule trades the same 47 times one bar later, and the gross P&L falls from 461.73 to 289.79, a loss of 37 %, while costs are almost unchanged (55.82 at 5 bp). For a fast signal, execution delay can cost more than the spread.
- **Trade less often.** A ten-bar lookback trades 19 times instead of 47. Its gross is lower (256.17), but so are its costs (22.10 at 5 bp, against 55.83 for the five-bar rule: 46.53 spread plus 9.30 commission), and its net, 234.07, ends close to that of the delayed fast rule.
- **The engines agree.** With a fixed charge of 0.5 per trade added, 47 trades cost 23.50 more, and net falls from 405.91 to 382.41. The event loop and the vectorised engine give the same equity on every bar to 1e-10, as ruling J-3 requires.

### The formal statement, checked against the spec

From [`11-research/backtester.md`](../../specifications/11-research/backtester.md) (rulings J-1 to J-3 in [`stage-j-rulings-w1.md`](../../specifications/stage-j-rulings-w1.md)). With `q_t = targets[t - lag]` for `t >= lag`, else 0, the trade is `d_t = q_t - q_{t-1}` and the holding P&L `g_t = q_{t-1} (p_t - p_{t-1}) m`. Costs are `s_t = |d_t| p_t (half_spread_bps / 10^4) m`, `c_t = |d_t| commission_per_unit` and `f_t = fixed_per_trade` when `d_t != 0`. The totals satisfy `total_gross - total_spread_cost - total_commission - total_fixed_cost = total_net` exactly, and `turnover = sum_t |d_t| p_t m`.

Because `s_t` is linear in `half_spread_bps` and nothing else depends on it, net P&L is a straight line in the half spread with slope `-turnover / 10^4`; that is what makes the break-even a one-line formula. Fills are at the close plus or minus the half spread, in full: there is no market impact, no partial fill and no queue (ruling J-1), so these costs are a lower bound for any size that moves the market.

## Step 2: the same in Rust, Java and C++

`examples/tutorials/t27_costs.py` sends the same eleven `research.backtest.run` cases to whichever CLI you name and prints the same lines.

Rust:

<!-- tutorial:run rust -->
```bash
(cd rust && cargo build --release -p quantforge-cli)
python examples/tutorials/t27_costs.py rust/target/release/quantforge
```

Java 25 and Maven:

<!-- tutorial:run java -->
```bash
(cd java25 && mvn -B -q -DskipTests package)
python examples/tutorials/t27_costs.py java -jar java25/target/quantforge-cli.jar
```

C++26 (GCC 16 or Clang 23, CMake and Ninja):

<!-- tutorial:run cpp -->
```bash
cmake -S cpp26 -B cpp26/build -G Ninja -DBUILD_TESTING=OFF && cmake --build cpp26/build
python examples/tutorials/t27_costs.py cpp26/build/quantforge
```

Each is to print the nine lines of step 1, digit for digit. The full check is `python conformance/runner/runner.py --impl rust --suite backtest_j`.

## For practitioners

- **Report the break-even spread beside the Sharpe ratio.** It is one number, it needs no model, and it tells a reader at once whether the result survives realistic costs.
- **Costs scale with turnover, not with trade count**, except for fixed charges. Halving the number of trades but doubling their size leaves the spread cost unchanged.
- **The spread is the floor, not the cost.** Impact grows with size relative to volume, and this backtester has none. A strategy whose break-even is only a few times the quoted spread is unlikely to survive impact.
- **Test the delay you will really have.** A daily signal computed after the close usually trades at the next close, which is `lag 1` at best.

## Common mistakes

- **Using `lag 0`.** It trades at the close the decision was made on, which needs that close before it exists. The backtester allows it only to build the look-ahead canary of Tutorial 23.
- **Quoting the full spread as the half spread.** That doubles the cost; the input is half the bid-offer gap, in basis points of price.
- **Tuning the lookback on the net result and reporting it as out of sample.** Every lookback tried is a trial; count them for the deflated Sharpe ratio of [Tutorial 30](tutorial-30-trials-and-power.md).
- **Ignoring the multiplier.** For futures, `multiplier` turns price points into money; leaving it at 1 understates P&L and spread cost by the same factor, but not the per-unit commission.

## What you just did

You priced a backtest at four spreads, found that each basis point took 9.31 of P&L, solved for a break-even half spread of 48.62 bp and confirmed it, saw one bar of delay remove 37 % of the gross, saw a slower rule trade 60 % less and end with a similar net, and checked that both engines agree.

## Try next

- Set `commission_per_unit` to 0.10 and predict the new break-even half spread before running it.
- Replace the price series with one that has no cycle (drop the `sin` term) and see what is left of the gross.
- Combine `lag 2` with the ten-bar lookback: does the slower rule lose as much to delay as the fast one?

## References and further reading

- M. Lopez de Prado, *Advances in Financial Machine Learning*, Wiley, 2018, on backtesting pitfalls. Cited by the stage J specs; not opened in this session.
- This project: [`11-research/backtester.md`](../../specifications/11-research/backtester.md), [Tutorial 23](tutorial-23-backtest-honestly.md), [Tutorial 21](tutorial-21-hedge-costs.md) (costs in a hedge), all sources in [References](../references.md).
