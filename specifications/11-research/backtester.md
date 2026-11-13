# Backtester: event loop, order and fill model, costs, P&L and attribution

Spec version 1.0.0. Status: specified, not implemented (wave 1 code lands in v0.9.0; no build implements these operations and their goldens are not in this release). Rulings: `stage-j-rulings-w1.md` J-1 to J-6. Suite in `datasets/golden/stage_j/`: `backtest_j`, written by `oracle/python/gen_stage_j_w1.py`. Plan items Q7 and J-3 (plan 12.5, 14.6).

**Plain idea.** A strategy says, at the close of each bar, how many units it wants to hold. The backtester holds that target from a later close (the execution lag), pays costs on every change, and books the price move on what it held over each bar. Every number it reports is a sum of per-bar numbers, so the P&L explain closes exactly.

Sources:
- [LdP18] M. Lopez de Prado, *Advances in Financial Machine Learning*, Wiley, 2018, chapter 11 ("The dangers of backtesting") and chapter 12 (backtesting through cross-validation) (not opened in this session; used for the look-ahead and lag discussion only, no number is taken from it). Evidence class: textbook, recalled.
- [Kis93] R. Kissell, *The Science of Algorithmic Trading and Portfolio Management*, Academic Press, 2013, chapter 3 (half-spread, commission and fixed-fee cost components) (not opened). Evidence class: textbook, recalled.
- Hand check: the ten-trade example below, computed line by line, equals `backtest_j-0001` and `-0002` exactly (the generator works in rational arithmetic). Evidence class: hand calculation.

## Common rules

- Check order: `E_PARSE`, `E_SCHEMA` (an `engine` value not listed), `E_LIMIT` (bars, J-5), the finite rule F-2 (`E_DOMAIN`), then the checks below. F-3 (negative zero) holds.
- Time is the bar index `t = 0 .. T-1`. Prices are closes. No calendar is used; bar spacing is the caller's.
- Determinism: the outputs are sums and products of the inputs in a fixed order; there is no randomness and nothing to converge (a single pass over the bars).

## `research.backtest.run`

### Inputs

- `prices` (length `T >= 2`, each `> 0`): close of each bar.
- `targets` (length `T`): the position, in units, the strategy wants after the close of bar `t`, computed with information up to that close.
- `lag` (Integer, default 1, `0 <= lag < T`): bars between decision and execution. `lag = 0` executes at the same close as the decision; it is allowed only so that a look-ahead canary can be built (ruling J-2).
- `half_spread_bps` (default 0, `>= 0`), `commission_per_unit` (default 0, `>= 0`), `fixed_per_trade` (default 0, `>= 0`).
- `multiplier` (default 1, `> 0`): money per unit per unit of price.
- `engine` (`EVENT` default, or `VECTOR`): both engines must return the same outputs (J-3).

### Checks, in order

1. `len(targets) != T`, `T < 2`, `lag < 0` or `lag >= T`: `E_INPUT`.
2. A price `<= 0`, a negative cost input, or `multiplier <= 0`: `E_DOMAIN`.

### Event loop (normative definition)

With `q_{-1} = 0`, for `t = 0 .. T-1`:
1. Position held after bar `t`'s close: `q_t = targets[t - lag]` for `t >= lag`, else `0`.
2. Trade at the close of bar `t`: `d_t = q_t - q_{t-1}`. It fills in full at `p_t` plus or minus the half spread (no partial fills, no queue; the fill model of stage H replaces this later, ruling J-1).
3. Holding P&L over bar `t`: `g_t = q_{t-1} (p_t - p_{t-1}) m` for `t >= 1`, `g_0 = 0`. The position that earns bar `t`'s move is the one held **before** the bar's trade.
4. Costs: spread `s_t = |d_t| p_t (half_spread_bps / 10^4) m`; commission `c_t = |d_t| commission_per_unit`; fixed `f_t = fixed_per_trade` if `d_t != 0`, else 0. Cost `k_t = s_t + c_t + f_t`.
5. Net `n_t = g_t - k_t`; equity `E_t = sum_{u <= t} n_u`.

The `VECTOR` engine computes the same quantities as whole arrays (shifted targets, differences, element-wise products, cumulative sum). It must equal `EVENT` to 1e-10 relative on every output (J-3), which holds trivially when both follow the definition above.

### Outputs

- Per bar (length `T`): `positions` (`q_t`), `trades` (`d_t`), `pnl_gross` (`g_t`), `cost` (`k_t`), `pnl_net` (`n_t`), `equity` (`E_t`).
- Totals (attribution): `total_gross`, `total_spread_cost`, `total_commission`, `total_fixed_cost`, `total_net`, with `total_gross - total_spread_cost - total_commission - total_fixed_cost = total_net` (an identity; the generator asserts it in exact arithmetic).
- `turnover = sum_t |d_t| p_t m`; `trade_count` (Integer) = number of `t` with `d_t != 0`; `max_drawdown = max_t (max_{u <= t} max(E_u, 0) - E_t)`, peak taken with a starting equity of 0.

### Worked ten-trade example (`backtest_j-0001`, J-3 hand check)

Prices 100, 101, 99.5, 102, 103, 101.5, 100, 104, 105.5, 103, 106, 107; targets 1, 2, -1, 0, 3, 3, -2, 1, 0, 2, 0, 0; lag 1; half spread 5 bp; commission 0.01 per unit; fixed 1 per trade.

| t | q | d | g | cost | net |
|---|---|---|---|---|---|
| 1 | 1 | 1 | 0 | 101 x 0.0005 + 0.01 + 1 = 1.0605 | -1.0605 |
| 2 | 2 | 1 | 1 x (99.5 - 101) = -1.5 | 1.05975 | -2.55975 |
| 3 | -1 | -3 | 2 x 2.5 = 5 | 3 x 102 x 0.0005 + 0.03 + 1 = 1.183 | 3.817 |
| 7 | -2 | -5 | q_6 (104 - 100) = 3 x 4 = 12 | 5 x 104 x 0.0005 + 0.05 + 1 = 1.31 | 10.69 |

(Rows 4 to 6 and 8 to 11 follow the same lines; the full table is the golden.) Totals: gross 6.5, spread 1.13975, commission 0.22, fixed 10 (ten trades), net -4.85975; turnover 2,279.5; maximum drawdown 8.87575 (equity 3.143 at t = 7 to -5.73275 at t = 10).

### Property tests (each language, own data)

- `EVENT` equals `VECTOR` to 1e-10 on random strategies (J-3).
- Attribution identity to 1e-12 relative of the largest term.
- Look-ahead canary (Q7, ruling J-2): a target equal to `sign(p_{t+1} - p_t)` has a large positive gross P&L at `lag = 0` shifted by one bar and none at `lag = 1` on a driftless random walk; the test asserts the canary is detected.
- Zero costs give `pnl_net = pnl_gross`; doubling every cost input doubles `total_*_cost` exactly.

## Limitations

One instrument per call; a portfolio is the sum of calls. No partial fills, market impact, borrow cost, financing or dividends (stage H adds impact and queue fills). No survivorship issue arises inside the operation; the study that feeds it must state its universe (Q7 survivorship statement).
