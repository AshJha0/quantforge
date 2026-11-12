# Tutorial 21: what a hedge costs: spread, impact, margin, and a backtest with costs

The plain idea: every hedge in Tutorials 17 to 20 traded for free. Real trades pay half the bid-offer spread on every unit, move the price against the trader when they are large (market impact), and tie up margin. Put those costs into the hedge problem and the answer changes: an expensive instrument may be dropped entirely, positions shrink, and you choose how much risk to keep in exchange for paying less. After the trades, the other half of the question is how much they really cost compared with what the model expected.

You will add a spread cost to a hedge and watch one instrument drop out exactly, add impact and a margin limit, trace the risk-against-cost frontier, rerun the delta-hedge backtest of [Tutorial 17](tutorial-17-delta-hedge.md) paying a 2 cent half-spread, and decompose the cost of two orders after the fact into implementation shortfall and slippage. Python first, then Rust, Java and C++. All data is synthetic: `examples/hedge_cost_i.json`, `hedge_frontier_i.json`, `hedge_backtest_i.json` and `hedge_slippage_i.json`, with variants built in the code. Budget 15 minutes. Every number shown is a real output.

Terms, defined here. The **half-spread** is half the difference between the offer and the bid: the cost per unit of crossing from the mid price. **Market impact** is the move in price caused by your own trade; linear impact makes it proportional to size, so its cost grows with the square of size. **Margin** is collateral a broker or clearing house requires per position. **Implementation shortfall** is the difference between the value of the trade decided on, at the decision price, and what was actually achieved, including the part not filled (Perold 1988).

## What you need

- A clone of the repository, with commands run from its root in Git Bash or a Unix shell.
- [uv](https://docs.astral.sh/uv/): `uv sync --locked --project python`.
- For step 2, the three builds made in [Tutorial 1](tutorial-1-swap.md).

## Step 1: Python

Save the next block as `hedge21.py` and run it from the repository root (or paste it into `uv run --project python python -`). It calls `quantforge_core.hedge_solvers`, `dynamic_hedge` and `slippage` directly.

<!-- tutorial:run python -->
```python
import json

from quantforge_core import dynamic_hedge, hedge_solvers, slippage


def inputs(name):
    with open(f"examples/{name}.json", encoding="utf-8") as f:
        return json.load(f)["inputs"]


def num(value, places):
    return f"{round(value, places) + 0.0:.{places}f}"  # + 0.0 prints -0.0 as 0.0


def nums(values, places):
    return " ".join(num(v, places) for v in values)


# 1. A hedge with a spread cost: the expensive second instrument is dropped exactly.
c = inputs("hedge_cost_i")
free = hedge_solvers.qp_solve(c["a"], c["b"], c["weights"])
r = hedge_solvers.qp_solve(c["a"], c["b"], c["weights"], half_spreads=c["half_spreads"])
print(f"no cost     x {nums(free['x'], 4)}  risk {num(free['objective'], 4)}")
print(f"with spread x {nums(r['x'], 4)}  risk {num(r['risk'], 4)}  cost {num(r['cost'], 4)}")

# 2. Market impact and a margin limit on the same hedge.
r = hedge_solvers.qp_solve(c["a"], c["b"], c["weights"], half_spreads=c["half_spreads"],
                           impact=[0.05, 0.05, 0.05], margin_rates=[0.1, 0.1, 0.1], margin_limit=0.15)
print(f"impact+margin x {nums(r['x'], 4)}  risk {num(r['risk'], 4)}  cost {num(r['cost'], 4)}  margin {num(r['margin'], 4)}")

# 3. The risk-against-cost frontier.
f = inputs("hedge_frontier_i")
pts = hedge_solvers.frontier_solve(f["a"], f["b"], f["weights"], f["cost_weights"],
                                   half_spreads=f["half_spreads"])["points"]
for p in pts:
    print(f"frontier weight {num(p['cost_weight'], 1):>5}  risk {num(p['risk'], 4)}  cost {num(p['cost'], 4)}")

# 4. The delta-hedge backtest of tutorial 17, paying a 2 cent half-spread on every share traded.
bt = inputs("hedge_backtest_i")
opt = bt["option"]
weekly = list(range(0, len(bt["times"]), 5)) + [len(bt["times"]) - 1]
for label, keep in (("daily ", range(len(bt["times"]))), ("weekly", weekly)):
    r = dynamic_hedge.backtest_delta(opt["type"], opt["strike"], opt["expiry_years"], bt["quantity"],
                                     bt["rate"], bt["dividend_yield"], bt["hedge_volatility"],
                                     [bt["times"][k] for k in keep], [bt["spots"][k] for k in keep],
                                     half_spread=0.02)
    print(f"{label} with costs: final P&L {num(r['final_pnl'], 2)}  trading cost {num(r['trading_cost'], 2)}")

# 5. After the trades: implementation shortfall and slippage against the cost model.
s = inputs("hedge_slippage_i")
orders = [(o["quantity"], o["decision_price"], o["final_price"], o["half_spread"], o["impact"],
           [(x["quantity"], x["price"]) for x in o["fills"]]) for o in s["orders"]]
t = slippage.slippage_report(orders)["total"]
print(f"shortfall {num(t['shortfall'], 2)} = execution {num(t['execution_cost'], 2)}"
      f" + opportunity {num(t['opportunity_cost'], 2)};  model {num(t['model_cost'], 2)}  slippage {num(t['slippage'], 2)}")
```

```bash
uv run --project python python hedge21.py
```

Real output, 2026-11-12, Windows 11:

<!-- tutorial:expect -->
```text
no cost     x 1.2389 -0.5792 -0.7518  risk 8.7174
with spread x 0.9594 0.0000 -1.0037  risk 9.5210  cost 0.0196
impact+margin x 0.7151 0.0000 -0.7849  risk 9.6134  cost 0.0714  margin 0.1500
frontier weight   0.0  risk 8.7174  cost 0.1349
frontier weight   0.5  risk 8.7180  cost 0.1327
frontier weight   1.0  risk 8.7196  cost 0.1305
frontier weight   2.0  risk 8.7262  cost 0.1262
frontier weight   5.0  risk 8.7720  cost 0.1131
frontier weight  10.0  risk 8.9358  cost 0.0912
frontier weight  50.0  risk 10.7773  cost 0.0047
daily  with costs: final P&L 25.76  trading cost 6.75
weekly with costs: final P&L 63.17  trading cost 3.74
shortfall 261.00 = execution 101.00 + opportunity 160.00;  model 141.00  slippage -40.00
```

### Reading the numbers

- **A spread drops an instrument exactly.** Five risks, three instruments. Free, the hedge holds all three, with the weighted squared residual 8.7174. With half-spreads of 0.01, 5.0 and 0.01, the second instrument costs 500 times more per unit than the others, and the answer holds exactly 0 of it: not a small number, zero. The others move to cover part of its job, the risk rises to 9.5210 and the cost is 0.0196 = 0.01 x (0.9594 + 1.0037). This is the absolute value in the cost at work: at `x_2 = 0` the cost has a kink, and the solver stays there as long as the marginal risk reduction of the second instrument is below its spread (the subgradient condition).
- **Impact and margin.** An impact of 0.05 per instrument adds `0.05 x^2` to each position's cost, and a margin of 10% of each position's size is capped at 0.15. The margin limit binds: 0.1 x (0.7151 + 0.7849) = 0.15 exactly. Both positions shrink, and the risk rises to 9.6134. A liquidity limit, by contrast, needs no new input: it is a bound on `x`, as in [Tutorial 18](tutorial-18-minvar-qp.md).
- **The frontier.** One hedge problem with half-spreads 0.05, 0.1 and 0.02, solved for seven weights on cost. At weight 0 it is the risk-only hedge. As the weight rises, the risk never falls and the cost never rises, which is the shape any convex trade-off has (Boyd and Vandenberghe). The useful part is the slope: going from weight 0 to 2 saves 0.0087 in cost for 0.0088 of risk, and from 10 to 50 saves 0.0865 in cost for 1.84 of risk. Where to stop is a desk decision; the frontier shows what each choice gives up.
- **The backtest pays.** The daily delta hedge of Tutorial 17 made 32.52 before costs; paying 2 cents per share on every share traded costs 6.75 and leaves 25.76. Weekly rebalancing trades less: 3.74 of costs. The final P&L falls by a little more than the costs (32.52 - 25.76 = 6.76) because costs paid early also lose interest on the cash account. On this path the weekly hedge also made more before costs, for the reason Tutorial 17 explains, so do not read the ranking as general.
- **Shortfall and slippage.** The first order buys 1,000 at a decision price of 100 and fills in two pieces at an average of 100.092: execution cost 1,000 x 0.092 = 92. The second sells 500 at 50 but only 300 fill, at 49.97: execution cost 300 x 0.03 = 9, and the 200 not sold are valued at the final price 49.2, an opportunity cost of 200 x 0.8 = 160. Shortfall 92 + 9 + 160 = 261. The cost model expected `half_spread |q| + impact q^2` on the filled sizes, 20 + 100 for the buy and 3 + 18 for the sell, 141 in all. The fills cost 101, so the slippage against the model is -40: execution was cheaper than the model said. The larger cost here was not trading: the unfilled part of the sell cost more than both executions together.

### Formal statement, checked against the spec

From [`08-hedging/hedge-costs-and-frontier.md`](../../specifications/08-hedging/hedge-costs-and-frontier.md), [`08-hedging/dynamic-hedge-and-effectiveness.md`](../../specifications/08-hedging/dynamic-hedge-and-effectiveness.md) ("Costs in the backtest") and [`08-hedging/hedge-slippage.md`](../../specifications/08-hedging/hedge-slippage.md) (rulings I-24 to I-28, I-36 to I-40, I-54).

Costs in the hedge: `f(x) = sum_i w_i (A x + b)_i^2 + ridge |x|^2 + cost_weight C(x)`, with `C(x) = sum_j (half_spreads_j |x_j| + impact_j x_j^2)` [Almgren and Chriss: linear temporary impact, so quadratic cost], subject to the earlier constraints and `sum_j margin_rates_j |x_j| <= margin_limit` when given. The hedge starts from no position (I-24). The minimiser is unique; at `x_j = 0` inside its bounds, optimality is `|g_j| <= cost_weight half_spreads_j + mu margin_rates_j`, with `g` the gradient of the smooth part and `mu >= 0` the margin multiplier. Outputs add `risk` (the objective without the cost term), `cost` and `margin` (I-27).

Frontier: the same problem for each `cost_weights` value (strictly increasing, 1 to 50 of them); `risk` is non-decreasing and `cost` non-increasing in the weight, which the generator asserts on every golden.

Backtest with costs (I-39, I-40): a trade of `dq` shares costs `half_spread |dq| + impact dq^2`. The initial purchase is a trade, so `Pi_0 = -cost(h_0)`; each rebalance is paid from cash after `Pi_{i+1}` is recorded; there is no unwind at the end. `trading_cost` is the undiscounted sum of all costs.

Slippage (I-36, I-37), per order with decision price `d`, filled quantity `q_f` and order `Q`: `execution_cost = sum q (p - d)`, `opportunity_cost = (Q - q_f)(final_price - d)`, `shortfall = execution_cost + opportunity_cost` [Perold], `model_cost = half_spread |q_f| + impact q_f^2`, `slippage = execution_cost - model_cost`. Positive is a cost for buys and sells alike.

The outside checks (I-2, I-28): scipy's `lsq_linear`, `lstsq`, and `minimize` (trust-constr and SLSQP on the split form `x = p - n`) for the cost and frontier cases; QuantLib for the backtest marks. Slippage has no outside check: no library computes implementation shortfall, and the spec records 0 of 12.

## Step 2: the same in Rust, Java and C++

`examples/tutorial_hedge_21.py` sends seven cases, `hedge.qp.solve` three times, `hedge.frontier.solve`, `hedge.backtest.delta` twice with `half_spread` and `hedge.slippage.report`, to the CLI you name and prints the same thirteen lines. It uses only the Python standard library.

Rust:

<!-- tutorial:run rust -->
```bash
(cd rust && cargo build --release -p quantforge-cli)
python examples/tutorial_hedge_21.py rust/target/release/quantforge
```

Java 25 and Maven:

<!-- tutorial:run java -->
```bash
(cd java25 && mvn -B -q -DskipTests package)
python examples/tutorial_hedge_21.py java -jar java25/target/quantforge-cli.jar
```

C++26 (GCC 16 or Clang 23, CMake and Ninja):

<!-- tutorial:run cpp -->
```bash
cmake -S cpp26 -B cpp26/build -G Ninja -DBUILD_TESTING=OFF && cmake --build cpp26/build
python examples/tutorial_hedge_21.py cpp26/build/quantforge
```

Each prints the thirteen lines of step 1, digit for digit. The full checks are the conformance suites `hedgecost_i`, `hedgefrontier_i`, `hedgebtcost_i` and `hedgeslip_i`.

## Use case 6: hedging an option book in whole lots

Plain idea: a desk holding options hedges with listed contracts that trade in lots, so the hedge must be a whole number of lots, and rounding to whole lots leaves some risk and some cost behind. Use case 6 (`usecase.option_hedge_lots`, spec `specifications/04-pricing/use-cases.md`, ruling R6-11.20) takes the book, the hedge instruments with lot size and half-spread, and the Greeks to neutralise; it weights each Greek by `1/max(1, |b_t|)^2`, solves `hedge.integer.solve` with lot bounds of plus or minus `max_lots`, and reports the Greeks before and after, the lots, `hedge_cost` and `rounding_cost`.

Worked example, golden case `uc6_r6-0001` (synthetic; expected outputs from the oracle at 50 digits with an exact integer search): a book short 1,500 six-month 105 calls, long 800 one-year 92 puts and long 600 three-month 100 calls (spot 100, rate 3%, dividend yield 1%, vol 22%), hedged in the underlying in lots of 100 with a half-spread of 0.01.

| Output | Value |
|---|---|
| Delta before | -543.96 |
| Lots bought | 5 (500 units) |
| Delta after | -43.96 |
| Gamma and vega | unchanged (-3.98 and -2,902.44): the underlying has neither |
| `hedge_cost` | 5.0 (500 units times the 0.01 half-spread) |
| `rounding_cost` | 0.0065, the objective lost by rounding to whole lots |

The CLI run of this case in each language is not shown yet: the operation is new in contract 1.12.0, and the page gains a runnable block once the four builds pass `datasets/golden/r6/uc6_r6.json`.

## For practitioners

- **Square-root impact is not here.** Empirical impact is often closer to the square root of size than linear in it. That cost grows as `|x|^{3/2}`, which is not a quadratic program; linear impact is the QP-compatible approximation the spec chose.
- **Hedges start from flat.** The traded size is the whole position. Rebalancing an existing hedge, with cost on `x - x_0`, is a later input (spec question Q-I11).
- **Margin is per position.** Linear in `|x|`, with no netting and no portfolio margin model, so it overstates margin for offsetting positions.
- **Choosing `cost_weight`.** It converts cost into units of weighted squared risk. Tie it to something real, such as the desk's price of risk, or read the answer off the frontier instead of fixing one weight.
- **Slippage needs a decision price.** Record it when the decision is made. Measuring against the arrival price or a VWAP gives different numbers, each with its own bias.
- **The costs are inputs, not estimates.** Nothing here fits spreads or impact to market data.

## Common mistakes

- **Expecting a costly instrument to get a small position.** A spread cost sets it to exactly zero until its benefit exceeds its spread; an impact cost only shrinks it.
- **Reading `objective` as the risk.** With costs, `objective = risk + cost_weight x cost`; read `risk` and `cost` separately.
- **Ignoring the unfilled part.** The opportunity cost of an order that did not complete can be larger than the cost of the part that did, as here.
- **Comparing backtest costs across paths.** The cost depends on how much the delta moved on that path, not only on the frequency.
- **Giving `margin_rates` without `margin_limit`.** It is `E_INPUT`; they come together.

## What you just did

You put a spread cost into a hedge and watched it drop an instrument exactly, added impact and a binding margin limit, traced the risk-against-cost frontier, paid for the trades of a delta hedge daily and weekly, and decomposed two orders' cost into execution, opportunity and slippage against the model. Python, Rust, Java and C++ gave the same digits. That completes the hedging series.

## Try next

- Lower the second instrument's half-spread from 5.0 to 0.1 in the first hedge and find the value at which it comes back into the hedge.
- Raise `margin_limit` to 1.0: the margin constraint stops binding, and the answer becomes the spread-and-impact hedge.
- Rerun the backtest with `impact=0.0001` added and see how much the large first trade costs.
- Read [LEARN, stage I: hedging](../../LEARN.md#stage-i-hedging), and the series index in the [tutorials README](README.md).

## References and further reading

The specs list these as sources; "not opened" there means the spec authors cited them from memory.

- R. Almgren, N. Chriss, "Optimal execution of portfolio transactions", *Journal of Risk* 3(2), 2001, 5-39, [doi:10.21314/JOR.2001.041](https://doi.org/10.21314/JOR.2001.041) (paywalled): linear temporary impact.
- A. F. Perold, "The implementation shortfall: paper versus reality", *Journal of Portfolio Management* 14(3), 1988, 4-9, [doi:10.3905/jpm.1988.409150](https://doi.org/10.3905/jpm.1988.409150) (paywalled).
- S. Boyd, L. Vandenberghe, *Convex Optimization*, Cambridge University Press, 2004, [free PDF on the authors' page](https://web.stanford.edu/~boyd/cvxbook/): section 4.7 (vector optimization and Pareto optimal points) and section 6.3 (trade-off curves).
- J. Nocedal, S. J. Wright, *Numerical Optimization*, 2nd ed., Springer, 2006, [doi:10.1007/978-0-387-40065-5](https://doi.org/10.1007/978-0-387-40065-5) (paywalled), chapter 12: optimality conditions, used here with the subgradient of `|x|`.
- R. Kissell, *The Science of Algorithmic Trading and Portfolio Management*, Academic Press, 2014, chapter 3: execution and opportunity cost. Not opened per the spec; no link given.
- This project: [`08-hedging/hedge-costs-and-frontier.md`](../../specifications/08-hedging/hedge-costs-and-frontier.md), [`08-hedging/hedge-slippage.md`](../../specifications/08-hedging/hedge-slippage.md), [`08-hedging/dynamic-hedge-and-effectiveness.md`](../../specifications/08-hedging/dynamic-hedge-and-effectiveness.md), rulings in [`stage-i-rulings.md`](../../specifications/stage-i-rulings.md).

Links checked 2026-11-12: the Almgren-Chriss and Springer DOIs and the Stanford book page returned HTTP 200; the Perold DOI returned 429 (rate limit) to a scripted request and its title, journal, volume and pages were confirmed through the Crossref API. The book's section numbers are from the spec and the plan and were not checked against the PDF.
