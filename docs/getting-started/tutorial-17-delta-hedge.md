# Tutorial 17: delta-hedge an option and watch the P&L

The plain idea: an option's value moves with the price of its underlying, and for small moves it moves by the option's delta times the price change. Hold minus that many shares and the two moves cancel. They cancel only for small moves and only for a moment, so a hedger does two things: neutralises more than one Greek at once with other options (a static hedge), and rebalances the shares as the price moves (a dynamic hedge). After the fact, the question is how well the hedge worked, and hedge accountants ask it with two numbers, the dollar offset and a regression.

This tutorial makes an option book delta-, gamma- and vega-neutral, replays a delta hedge of 100 short calls on a 63-day price path with daily and weekly rebalancing, and then measures the effectiveness of a hedge relationship from 24 monthly value changes. Python first, then the same in Rust, Java and C++. All data is synthetic: the inputs are `examples/hedge_greeks_i.json`, `examples/hedge_backtest_i.json` and `examples/hedge_effectiveness_i.json`, which are golden cases `hedgegreeks_i-0003`, `hedgebt_i-0001` and `hedgeeff_i-0001`. Budget 15 minutes. Every number shown is a real output.

Terms: delta, gamma and vega are in the [glossary, stage C section](../../GLOSSARY.md#stage-c-equity-vol-slice). Two more, defined here. The **dollar offset** of a hedge is minus the total change of the hedge divided by the total change of the hedged item; 1 is a perfect offset. **Self-financing** means that after the start no money is added or taken out: every share bought is paid for from the cash account.

## What you need

- A clone of the repository, with commands run from its root in Git Bash or a Unix shell.
- [uv](https://docs.astral.sh/uv/): `uv sync --locked --project python`.
- For step 2, the three builds made in [Tutorial 1](tutorial-1-swap.md).

## Step 1: Python

Save the next block as `hedge17.py` and run it from the repository root (or paste it into `uv run --project python python -`). It calls the `quantforge_core` modules `hedge_solvers` and `dynamic_hedge` directly.

<!-- tutorial:run python -->
```python
import json

from quantforge_core import dynamic_hedge, hedge_solvers


def inputs(name):
    with open(f"examples/{name}.json", encoding="utf-8") as f:
        return json.load(f)["inputs"]


def num(value, places):
    return f"{round(value, places) + 0.0:.{places}f}"  # + 0.0 prints -0.0 as 0.0


# 1. A static Greek hedge: make an option book delta-, gamma- and vega-neutral.
g = inputs("hedge_greeks_i")
book = [(p["instrument"], p.get("strike"), p.get("expiry_years"), p["quantity"]) for p in g["portfolio"]]
hedges = [(h["instrument"], h.get("strike"), h.get("expiry_years")) for h in g["hedges"]]
greeks = hedge_solvers.greeks_neutralise(g["spot"], g["rate"], g["dividend_yield"], g["volatility"],
                                         book, hedges, g["targets"])
before, after, q = greeks["greeks_before"], greeks["greeks_after"], greeks["quantities"]
print(f"book   delta {num(before['delta'], 4)}  gamma {num(before['gamma'], 4)}  vega {num(before['vega'], 2)}")
print(f"hedge  shares {num(q[0], 4)}  105 calls {num(q[1], 4)}  95 puts {num(q[2], 4)}")
print(f"after  delta {num(after['delta'], 4)}  gamma {num(after['gamma'], 4)}  vega {num(after['vega'], 2)}")

# 2. A dynamic delta hedge of 100 short calls, replayed on a 63-day path, daily and weekly.
bt = inputs("hedge_backtest_i")
opt = bt["option"]
weekly = list(range(0, len(bt["times"]), 5)) + [len(bt["times"]) - 1]
for label, keep in (("daily ", range(len(bt["times"]))), ("weekly", weekly)):
    r = dynamic_hedge.backtest_delta(opt["type"], opt["strike"], opt["expiry_years"], bt["quantity"],
                                     bt["rate"], bt["dividend_yield"], bt["hedge_volatility"],
                                     [bt["times"][k] for k in keep], [bt["spots"][k] for k in keep])
    print(f"{label} final P&L {num(r['final_pnl'], 2)}  dollar offset {num(r['dollar_offset'], 4)}"
          f"  slope {num(r['regression_slope'], 4)}  R2 {num(r['regression_r2'], 4)}")

# 3. Effectiveness of a hedge relationship from 24 monthly value changes.
e = inputs("hedge_effectiveness_i")
s = dynamic_hedge.effectiveness(e["item_changes"], e["hedge_changes"])
print(f"monthly dollar offset {num(s['dollar_offset'], 4)}  slope {num(s['regression_slope'], 4)}"
      f"  R2 {num(s['regression_r2'], 4)}  variance reduction {num(s['variance_reduction'], 4)}")
```

```bash
uv run --project python python hedge17.py
```

Real output, 2026-11-12, Windows 11:

<!-- tutorial:expect -->
```text
book   delta -686.2112  gamma -15.7597  vega -11508.40
hedge  shares 504.8326  105 calls 502.7646  95 puts 38.2748
after  delta 0.0000  gamma 0.0000  vega 0.00
daily  final P&L 32.52  dollar offset 1.3050  slope -0.9919  R2 0.9963
weekly final P&L 66.92  dollar offset 1.6277  slope -0.9893  R2 0.9981
monthly dollar offset 0.9712  slope -0.9924  R2 0.9964  variance reduction 0.9964
```

`num` rounds before it prints, so a Greek of `-1e-14` after the hedge prints as `0.0000` in every language rather than `-0.0000` in some.

### Reading the numbers

- **The book.** Spot 100, rate 3%, dividend yield 1%, volatility 25%. The book is short 1,000 six-month 100 calls and long 500 one-year 90 puts. Its delta is -686.21: the short calls contribute about -1,000 x 0.55 and the long puts about 500 x -0.26, with the at-the-money call delta near `e^{-qT} N(d1)` = 0.995 x N(0.15) = 0.555. Vega is -11,508 per unit of volatility, so -115.08 per volatility point.
- **The hedge.** Three targets need three instruments: the shares, a three-month 105 call and a two-year 95 put. The answer buys 504.83 shares, 502.76 calls and 38.27 puts. Shares carry no gamma or vega, so the two options alone must cancel the book's gamma and vega, and the shares then mop up whatever delta is left. That is the order in which to check it by hand: a 2x2 solve for the options, then one subtraction.
- **After.** Every targeted Greek is zero to rounding (the raw values are near 1e-14). This holds at today's spot and volatility only; the hedge must be redone as they move.
- **Daily backtest, final P&L 32.52.** The bank sold 100 calls (strike 100, 63 days) at the hedge volatility of 20%, a premium of 100 x 3.4773 = 347.73, and delta-hedged every day. The path ends at 104.54, so the calls pay 454.36, more than the premium, yet the hedged position made 32.52. The reason is volatility: the path's realised volatility is 18.2% (root mean square of the daily log returns, annualised over 365 days), below the 20% the bank sold. A short-gamma position that is delta-hedged earns, step by step, about `-(1/2) Gamma S^2 (realised variance - hedge variance) dt`, which is positive when realised volatility is below the hedge volatility [Hull ch. 19].
- **Weekly, 66.92.** Rebalancing every fifth day leaves the position unhedged for longer, so the result depends more on the path. On these weekly points the realised volatility is 16.1%, so this one path happens to pay more. One path proves nothing about frequency: the spec asserts no such relation on a single path, and Hull's tables show the hedging error's standard deviation falling as rebalancing becomes more frequent.
- **Dollar offset 1.3050 against R² 0.9963.** The regression says the hedge tracked the option very closely; the dollar offset says it "over-hedged" by 30%. Both are right. The dollar offset is a ratio of the two total changes, and the option's total change is small compared with its daily moves, so a small absolute difference (here the 32.52) becomes a large ratio. Finnerty and Grant (2002) describe exactly this instability. Under IAS 39 a hedge was highly effective with a dollar offset in 80% to 125%; this one would have failed that test while hedging well.
- **Monthly hedge relationship.** 24 monthly changes of an item and its hedge: the total item change is -6,236.58 and the total hedge change 6,057.18, so the dollar offset is 6,057.18 / 6,236.58 = 0.9712. The slope -0.9924 and R² 0.9964 say the hedge moves almost one for one against the item, and the variance of the hedged position is 0.36% of the unhedged variance.

### Formal statement, checked against the spec

From [`08-hedging/hedge-solvers.md`](../../specifications/08-hedging/hedge-solvers.md) and [`08-hedging/dynamic-hedge-and-effectiveness.md`](../../specifications/08-hedging/dynamic-hedge-and-effectiveness.md) (rulings I-4, I-9, I-29 to I-31, I-43).

Greek hedge: Black-Scholes-Merton with flat inputs. With `d1 = (ln(S/K) + (r - q + v^2/2) T) / (v sqrt T)`, call delta `e^{-qT} N(d1)`, put delta `-e^{-qT} N(-d1)`, gamma `e^{-qT} n(d1) / (S v sqrt T)`, vega `S e^{-qT} n(d1) sqrt T` per unit of volatility. The square matrix `G` has a row per target and a column per hedge, and `quantities` solves `G q = -g_book`. At most three hedges, as many targets as hedges; a nearly singular `G` (smallest singular value at most `1e-12` times the largest) is `E_SINGULAR`.

Backtest (I-29): `V_i` and `Delta_i` are the BSM value and delta at the hedge volatility; the shares held over `[t_i, t_{i+1}]` are `h_i = -quantity Delta_i`. Start with `cash = -quantity V_0 - h_0 S_0`, so `Pi_0 = 0`. Each step: `cash <- cash e^{r dt} + h_i S_i (e^{q dt} - 1)`, then `Pi_{i+1} = quantity V_{i+1} + h_i S_{i+1} + cash`, then rebalance `cash <- cash - (h_{i+1} - h_i) S_{i+1}` except on the last date. `item_i = quantity (V_{i+1} - V_i)` and `hedge_i = (Pi_{i+1} - Pi_i) - item_i`.

Effectiveness (I-30, I-31), with `x` the item changes, `y` the hedge changes and sample statistics over `n - 1`: `dollar_offset = -sum(y)/sum(x)`, `regression_slope = cov(x, y)/var(x)`, `regression_r2 = cov(x, y)^2/(var(x) var(y))`, `variance_reduction = 1 - var(x + y)/var(x)`. A near-zero `sum(x)` or variance is `E_DOMAIN` by the relative tests of I-43.

The outside check (ruling I-2): QuantLib 1.44's `AnalyticEuropeanEngine` reprices and re-deltas the option on every date of seven backtest cases, and numpy's `polyfit`, `corrcoef` and `var(ddof=1)` recompute five effectiveness cases.

## Step 2: the same in Rust, Java and C++

`examples/tutorial_hedge_17.py` sends the same four cases, `hedge.greeks.neutralise`, `hedge.backtest.delta` (daily and weekly) and `hedge.effectiveness`, to the CLI you name and prints the same six lines. It reads the same three example files, builds the weekly path the same way, and uses only the Python standard library.

Rust:

<!-- tutorial:run rust -->
```bash
(cd rust && cargo build --release -p quantforge-cli)
python examples/tutorial_hedge_17.py rust/target/release/quantforge
```

Java 25 and Maven:

<!-- tutorial:run java -->
```bash
(cd java25 && mvn -B -q -DskipTests package)
python examples/tutorial_hedge_17.py java -jar java25/target/quantforge-cli.jar
```

C++26 (GCC 16 or Clang 23, CMake and Ninja):

<!-- tutorial:run cpp -->
```bash
cmake -S cpp26 -B cpp26/build -G Ninja -DBUILD_TESTING=OFF && cmake --build cpp26/build
python examples/tutorial_hedge_17.py cpp26/build/quantforge
```

Each prints the six lines of step 1, digit for digit. The full check is the conformance suite: `python conformance/runner/runner.py --impl rust --suite hedgebt_i`.

## For practitioners

- **Flat volatility.** One volatility marks the option and computes its delta for the whole path. A desk marks to the moving implied volatility and must choose which delta to hedge with (implied or its own forecast); the P&L then has a vega part this replay does not have.
- **No costs here.** This replay trades for free. [Tutorial 21](tutorial-21-hedge-costs.md) runs the same path with a 2 cent half-spread and shows the bill.
- **Continuous dividends.** The shares earn a continuous yield. Discrete cash dividends would change both the option values and the cash account on the ex-dates.
- **Hedge accounting today.** IFRS 9 (2014) replaced IAS 39's 80% to 125% bright line with a qualitative "economic relationship" test for most hedges, but the dollar offset and regression are still the common quantitative evidence. Report the regression next to the dollar offset, for the reason the daily backtest shows.
- **Outside check.** QuantLib's `AnalyticEuropeanEngine` is the oracle for the option marks and deltas; the cash arithmetic is the spec's.

## Common mistakes

- **Vega per volatility point.** `vega` here is per unit of volatility (I-9): divide by 100 for a quote per point.
- **Reading a single path as a law.** The weekly hedge made more than the daily one on this path because its realised volatility was lower, not because weekly hedging is better.
- **Judging a hedge by the dollar offset alone.** It is unstable when the item's total change is small; look at the regression too.
- **Forgetting the dividends on the shares.** Leaving them out of the cash account moves the final P&L by 13 on one golden case; it is the mutant the suite catches.
- **Rebalancing on the last date.** There is no trade on the last date; the shares held are marked at the last spot.

## What you just did

You made an option book neutral in delta, gamma and vega with three instruments, replayed a self-financing delta hedge of 100 short calls daily and weekly and explained its P&L by realised against hedge volatility, measured hedge effectiveness the two ways hedge accountants do, and saw why the dollar offset and the regression can disagree. Python, Rust, Java and C++ gave the same digits.

## Try next

- Change the hedges to just `UNDERLYING` and the targets to `["DELTA"]`: the share count becomes 686.21, the book's delta with the sign changed.
- Set `hedge_volatility` to 0.182, the path's realised volatility, and run the daily backtest again: the P&L falls from 32.52 to -2.88, near zero (the premium is lower too).
- Rebalance every 3 days instead of 5 and compare.
- Read [LEARN: judging a hedge after the fact](../../LEARN.md#judging-a-hedge-after-the-fact), then go on to [Tutorial 18](tutorial-18-minvar-qp.md).

## References and further reading

The specs list most of these as sources; "not opened" there means the spec authors cited them from memory.

- J. C. Hull, *Options, Futures, and Other Derivatives*, 10th ed., Pearson, 2018, chapter 19, "The Greek letters": delta, gamma and vega hedging and the effect of rebalancing frequency. Not opened (the spec's [H18]); no link given.
- J. D. Finnerty, D. Grant, "Alternative approaches to testing hedge effectiveness under SFAS No. 133", *Accounting Horizons* 16(2), 2002, 95-108, [doi:10.2308/acch.2002.16.2.95](https://doi.org/10.2308/acch.2002.16.2.95) (paywalled). The spec's [FG02] gives the first author as "K. Finnerty"; Crossref lists John D. Finnerty and Dwight Grant.
- IFRS Foundation, [IAS 39 *Financial Instruments: Recognition and Measurement*](https://www.ifrs.org/issued-standards/list-of-standards/ias-39-financial-instruments-recognition-and-measurement/), application guidance AG105 to AG107 (the 80% to 125% range); and [IFRS 9 *Financial Instruments*](https://www.ifrs.org/issued-standards/list-of-standards/ifrs-9-financial-instruments/), chapter 6, which replaced it for most hedges. The standards' full text needs a free registration.
- QuantLib, [`AnalyticEuropeanEngine`](https://www.quantlib.org/reference/class_quant_lib_1_1_analytic_european_engine.html), the outside oracle for the backtest's marks and deltas; numpy, [`polyfit`](https://numpy.org/doc/stable/reference/generated/numpy.polyfit.html), the outside oracle for the regression.
- This project: [`08-hedging/hedge-solvers.md`](../../specifications/08-hedging/hedge-solvers.md), [`08-hedging/dynamic-hedge-and-effectiveness.md`](../../specifications/08-hedging/dynamic-hedge-and-effectiveness.md), rulings in [`stage-i-rulings.md`](../../specifications/stage-i-rulings.md); [LEARN, stage I: hedging](../../LEARN.md#stage-i-hedging).

Links checked 2026-11-12: the ifrs.org, quantlib.org and numpy.org pages returned HTTP 200; the Finnerty-Grant DOI returned 403 to a scripted request (publisher bot block) and its title, authors, volume and pages were confirmed through the Crossref API.
