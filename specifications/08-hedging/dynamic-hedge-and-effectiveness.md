# Dynamic delta-hedge backtest and hedge effectiveness

Spec version 1.0.0. Status: Specified (stage I, wave 4b). Rulings: `stage-i-rulings.md` I-29 to I-32. Suites in `datasets/golden/stage_i/`: `hedgebt_i`, `hedgeeff_i`, written by `oracle/python/gen_stage_i_w4b.py`.

**Plain idea.** A static hedge is solved once. A dynamic hedge is rebalanced as the market moves. The backtest replays a given spot path: at each date it marks the option at the hedge volatility, holds minus the option's delta in shares, and keeps the remaining money in a cash account that earns interest. The shares earn dividends. Rebalancing is self-financing, so no money enters or leaves after the start. What is left at the end is the hedging error. The effectiveness statistics measure how well the hedge leg offsets the hedged item. They come in the two forms used in hedge accounting: the dollar-offset ratio and a regression of the hedge's changes on the item's changes.

Sources:
- [H18] J. C. Hull, *Options, Futures, and Other Derivatives*, 10th ed., Pearson, 2018, chapter 19 (delta hedging, rebalancing) (not opened in this session).
- [IAS39] IASB, *IAS 39 Financial Instruments: Recognition and Measurement*, application guidance AG105 (the 80% to 125% effectiveness range) and AG107 (dollar-offset and regression methods); superseded for most hedges by IFRS 9 (2014), which removed the bright line (not opened).
- [FG02] J. D. Finnerty, D. Grant, "Alternative approaches to testing hedge effectiveness under SFAS No. 133", *Accounting Horizons* 16(2), 2002, 95-108 (the dollar-offset ratio's instability when the hedged item's change is small) (not opened).

## `hedge.backtest.delta`

### Inputs

- `option`: `{type, strike, expiry_years}`, a European `CALL` or `PUT`.
- `quantity`: options held (negative is short).
- `rate`, `dividend_yield` (continuous), `hedge_volatility` (used for both marks and deltas).
- `times` (years, `times[0] = 0`, strictly increasing, last at or before `expiry_years`) and `spots` (the path, same length).

### Checks, in order

1. `times` and `spots` of different lengths, fewer than 4 points, `times[0] != 0`, times not strictly increasing, or a last time after expiry: `E_INPUT`.
2. A spot, the strike, the expiry or the hedge volatility at or below 0: `E_DOMAIN`.
3. The effectiveness statistics' domain (below), for example `quantity = 0`: `E_DOMAIN`.

### The replay (I-29)

`m` dates. `V_i` is the Black-Scholes-Merton value at `S_i` with time to expiry `T - t_i`, and `Delta_i` its delta (with `e^{-q tau}`). At `tau = 0` the value is the payoff and no delta is needed. Shares held over `[t_i, t_{i+1}]`: `h_i = -quantity Delta_i`, for `i = 0..m-2`.

- Start: `cash = -quantity V_0 - h_0 S_0`, so the portfolio is worth `Pi_0 = 0`.
- Step `i` to `i+1`, with `dt = t_{i+1} - t_i`: `cash <- cash e^{r dt} + h_i S_i (e^{q dt} - 1)` (interest on cash, then dividends on the shares held, as a continuous yield on the value at the start of the step). Then `Pi_{i+1} = quantity V_{i+1} + h_i S_{i+1} + cash`. Then, unless `i+1` is the last date, rebalance: `cash <- cash - (h_{i+1} - h_i) S_{i+1}`.
- `item_i = quantity (V_{i+1} - V_i)` (the hedged item's change) and `hedge_i = (Pi_{i+1} - Pi_i) - item_i` (the shares and cash).

### Outputs

`option_values` (`V`, length `m`), `shares` (`h`, length `m - 1`), `portfolio_values` (`Pi`, length `m`), `final_pnl` (`Pi_{m-1}`), and the effectiveness statistics of `item` and `hedge` (below).

## `hedge.effectiveness`

### Inputs

`item_changes` and `hedge_changes`: series of the same length, at least 3.

### Checks, in order

1. Unequal lengths, or fewer than 3 values: `E_INPUT`.
2. `sum(item_changes) = 0`, or either series with zero sample variance: `E_DOMAIN` (I-31).

### Outputs (I-30, I-31)

With `x` the item changes, `y` the hedge changes, and sample (co)variances over `n - 1`:
- `dollar_offset = -sum(y) / sum(x)`: 1 is a perfect offset. Under IAS 39 a hedge was highly effective in `[0.80, 1.25]` [IAS39 AG105].
- `regression_slope = cov(x, y) / var(x)` (about -1 for a good hedge) and `regression_r2 = cov(x, y)^2 / (var(x) var(y))`.
- `variance_reduction = 1 - var(x + y) / var(x)`.

The dollar offset is a ratio of sums. It swings widely when the item's total change is small even for a good hedge [FG02]: `hedgebt_i-0001` has R² 0.996 and a dollar offset of 1.31. The regression measures are reported next to it for that reason.

## Validation cases and oracle

| Suite | Cases (value + error) | Oracle and self-checks | Outside (I-2) |
|---|---|---|---|
| `hedgebt_i` | 7 + 8 | 50-digit replay; daily hedge R² above 0.8 asserted. Paths are input data from a seeded log-normal generator (seeds 20261111 to 20261114), rounded to 4 decimals | 7 of 15: QuantLib 1.44 `AnalyticEuropeanEngine` NPV and delta on each date (the evaluation date moves; the exercise date is fixed; all dates are whole ACT/365F days), then the cash-account arithmetic above; every output within the case limit |
| `hedgeeff_i` | 5 + 5 | 50-digit statistics; the over-hedge case gives exactly 1.25 and -1.25 | 5 of 10: numpy 2.5 `polyfit`, `corrcoef`, `var(ddof=1)` |

Stage I so far: 98 of 234 = 41.9% outside.

Mutant caught: dividends on the hedge shares left out of the cash account (`final_pnl` moves by 13).

## Convergence and limit cases

| Method | Asserted behaviour | Measured on | Limit case | Reference |
|---|---|---|---|---|
| Delta-hedge replay | Exact arithmetic, no iteration. The hedging error falls as rebalancing becomes more frequent (Hull ch. 19); this is not asserted on one path | Daily, 3-day and weekly paths in `hedgebt_i` | A path that stops before expiry marks the option at its value, not its payoff | QuantLib values on each date |
| Effectiveness statistics | Closed form | `hedgeeff_i` | Perfect hedge: offset 1, slope -1, R² 1, variance reduction 1 (`-0003`) | numpy |

## Limitations

- One option per backtest, a flat hedge volatility and no transaction costs in the replay. A cost-aware rebalance would add the wave 4a costs per trade, which is a new input for a later wave.
- Dividends are a continuous yield, not discrete cash dividends.
- The path is input data: the backtest does not simulate. A Monte Carlo study of hedging error against rebalancing frequency is research (stage J), not a golden.

## Spec questions and rulings

| # | Question | Ruling |
|---|---|---|
| Q-I14 | Interest and dividends: on which value, and in which order? | Cash earns `e^{r dt}`; shares earn `h_i S_i (e^{q dt} - 1)`, on the value at the start of the step; both are credited before the rebalance (I-29). Other conventions (dividends on the end value, or reinvested in shares) change the result at about `q dt` relative per step |
| Q-I15 | Dollar offset period by period, or cumulative? | Cumulative over the whole series (I-30). A period-by-period ratio divides by single changes, which can be zero |
| Q-I16 | Population or sample variance? | Sample (`n - 1`), as `hedge.minvar.ratio` (I-8). The ratios do not depend on the choice; only a future variance output would |

## Costs in the backtest (wave 4e)

Added in wave 4e (rulings I-39, I-40) for the stage I tutorials' "dynamic hedge backtest with costs". It changes nothing above: without the new inputs `hedge.backtest.delta` returns exactly the wave 4b result. The generator re-derives every `hedgebt_i` golden and asserts they are equal.

New optional inputs: `half_spread` and `impact` (each `>= 0`, else `E_DOMAIN`, checked after the wave 4b domain checks). They are the wave 4a cost model per share traded: a trade of `dq` shares costs `half_spread |dq| + impact dq^2`.

Replay with costs (I-39):
- The initial purchase of `h_0` shares is a trade. Its cost is paid from cash at `t_0`, so `Pi_0 = -cost(h_0)`.
- Each rebalance at `t_{i+1}` (not on the last date) pays `cost(h_{i+1} - h_i)` from cash after `Pi_{i+1}` is recorded, so it shows in the next step's change.
- No unwind at the end: the final shares are marked at the last spot, and the option at its value or payoff.

New output, present only with a cost input (I-40): `trading_cost`, the undiscounted sum of every cost paid. `final_pnl` and the effectiveness statistics include the costs through the cash account.

Suite `hedgebtcost_i` (5 value, 3 error), written by `oracle/python/gen_stage_i_w4e.py`. The value cases are daily and weekly rebalancing with a 2 cent half-spread, spread plus impact, zero cost parameters (equal to the cost-free replay, with `trading_cost = 0`) and impact only. Weekly rebalancing pays less than daily (2.35 against 6.75 on the same option), which is asserted. Outside: 5 of 8, the QuantLib check of wave 4b with the same cost arithmetic. Mutant caught: costs ignored.

## Amendment after the builds

Ruling I-43 replaces the exact tests of I-31 with relative ones: `E_DOMAIN` when `|sum(x)| <= 1e-12 sum|x|`, `var(x) <= 1e-20 var(y)` or `var(y) <= 1e-20 var(x)`. A constant-spot backtest with zero rates and dividends is therefore `E_DOMAIN` in every build (`hedgebt_i-0016`).

## R6 amendments (R6-11.11, item 19)

- IAS 39: AG105(b) sets the 80% to 125% range. IAS 39 does not prescribe one method of assessment; dollar offset and regression are common practice and are not cited here as IAS 39 text (the AG107 attribution could not be verified on 2026-11-12: the EUR-Lex copy returned an empty page).
- Cost timing is a convention (Q-I14): each trade's cost is paid at the next recorded step, and `Pi_0 = -cost(h_0)` records the initial trade.
