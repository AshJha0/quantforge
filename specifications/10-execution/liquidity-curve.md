# Liquidity cost curve: spread, square-root impact and timing risk by size and horizon

Spec version 1.0.0. Status: Specified and implemented in all four builds (stage J curves lane, v0.9.0). Rulings: `stage-j-rulings-curves.md` J-C-1 and J-C-6 to J-C-9. Suite `stage_j/liqcurve_j`. Built so that stage H reuses it: at a one-day horizon with exponent 1/2 the impact term is the draft `exec.impact.sqrt` of stage H (`10-execution/impact.md` on branch `h-spec`, golden `imp_h-0001`), and the timing-risk term is the variance of the linear Almgren-Chriss schedule that H-3b builds (J-C-8).

**Plain idea.** Selling a position costs more than the screen price. You cross half the bid-ask spread, and the selling itself pushes the price away; the push is larger when you sell more and when you sell faster. Selling slowly cuts the push but leaves you exposed to the market for longer. A liquidity curve puts numbers on that trade-off: for each order size and each liquidation horizon, the expected cost per unit, the risk from waiting, and the horizon where their sum is smallest.

**Formal statement.** For an order of `Q` units traded evenly over `h` trading days in a stock with daily volume `V`, daily volatility `sigma` (a fraction of price), half spread `s` (fraction of price; input in basis points), impact coefficient `Y`, exponent `delta` in `(0, 1]` and a risk multiplier `z >= 0`, the cost per unit as a fraction of the arrival price is

`c(Q, h) = s + I(Q, h) + R(h)`, with `I(Q, h) = Y sigma (Q / (V h))^delta` and `R(h) = z sigma sqrt(h / 3)`.

`I` is the square-root law of [TLD11] (`delta = 1/2`) written with the daily participation `Q/(V h)`, which is the form [AFTHL05] fit (they report `delta` near 3/5). `R` is `z` standard deviations of the average execution price against arrival for a linear liquidation over `h` days: the continuous-time variance of the Almgren-Chriss linear trajectory is `sigma^2 X^2 T / 3` [AC00], so per unit the standard deviation is `sigma sqrt(h/3)` (J-C-7).

With `a = Y sigma (Q/V)^delta` and `b = z sigma / sqrt 3`, `c = s + a h^{-delta} + b h^{1/2}` is strictly convex in `h > 0` when `a, b > 0`, and setting the derivative to zero gives the cost-minimising horizon in closed form:

`h* = (2 delta a / b)^{1 / (delta + 1/2)}`, `c* = s + a h*^{-delta} + b sqrt(h*)`.

## `liq.curve.cost`

Inputs: `half_spread_bps` (`>= 0`), `daily_volume` (`> 0`), `daily_vol` (`>= 0`), optional `coefficient` `Y` (default 1, `>= 0`; labelled assumed, as stage H ruling H-10), optional `exponent` `delta` (default 0.5, in `(0, 1]`), optional `risk_multiplier` `z` (default 0, `>= 0`), `sizes` (non-empty, each `>= 0`), `horizons_days` (non-empty, each `> 0`; any order).

Outputs: `spread_cost` (`s`), `impact` (matrix, row per size, column per horizon), `timing_risk` (per horizon), `total_cost` (matrix), `optimal_horizon` and `min_cost` (per size). When `b = 0` (no risk term) or `Y = 0` there is no interior optimum and both are `null` (J-C-8). A zero size gives `h* = 0` and `c* = s`.

Checks, in order (after `E_PARSE`, `E_SCHEMA`, `E_LIMIT` and F-2): empty `sizes` or `horizons_days`: `E_INPUT`; any value outside its domain above: `E_DOMAIN`.

## Worked example (golden `liqcurve_j-0001`, hand)

`sigma = 0.02`, `V = 10^7`, `Y = 1`, `delta = 1/2`, half spread 5 bp, `z = 0`.

1. `Q = 10^5`, `h = 1`: `I = 0.02 sqrt(10^5 / 10^7) = 0.02 x 0.1 = 0.002` (20 bp), the stage H value `imp_h-0001`. Total `0.0005 + 0.002 = 0.0025`.
2. `Q = 4 x 10^5`, `h = 1`: four times the size, twice the impact, `0.004`.
3. `Q = 10^5`, `h = 4`: a quarter of the daily participation, half the impact, `0.001`.

Optimal horizon (golden `liqcurve_j-0002`, hand): set `z = sqrt 3`, so `b = sigma = 0.02`; `a = 0.002`; `h* = (2 x 0.5 x 0.002 / 0.02)^1 = 0.1` day, and `c* = 0.0005 + 0.002/sqrt(0.1) + 0.02 sqrt(0.1) = 0.0131491106`.

## Acceptance

Class `simple_analytic`. Evidence (J-C-9): `liqcurve_j-0001` and `-0002` are hand derivations; the rest are reference-computed by `oracle/python/gen_stage_j_curves.py` (mpmath, 50 digits). No outside library implements this curve and the sources print no fully specified example with these inputs, so it is self-assessed. Property tests in each language: the one-day square-root value, impact increasing in size, `h*` a minimum (cost at `0.9 h*` and `1.1 h*` not lower).

## Limitations

- A formula curve with assumed parameters (`Y`, `delta`, `z`), not a calibration: no claim about any real stock or venue. Calibration is stage H item H-1 (crypto book, research lane).
- Even trading only; the optimal schedule under risk aversion (Almgren-Chriss `sinh` trajectory) is stage H item H-3b. Permanent impact, decay and resilience (Obizhaeva-Wang) are not in the curve.
- FRTB liquidity horizons (MAR33.12, the 10/20/40/60/120-day cascade for expected shortfall) are a regulatory scaling of market risk, not a cost curve; they are not built here.

## Sources

- [TLD11] B. Toth, Y. Lemperiere, C. Deremble, J. de Lataillade, J. Kockelkoren, J.-P. Bouchaud, "Anomalous price impact and the critical nature of liquidity in financial markets", *Physical Review X* 1 (2011) 021006, open access. `I = Y sigma sqrt(Q/V)`, `Y` of order one. Evidence class: paper, read 2026-11-18 (arXiv:1105.1694v3, eq. (1); see `impact.md`). [TLD11]'s impact depends on Q/V on the day, not on the execution horizon; the 1/h scaling used here is the rate form of [AFTHL05], not of [TLD11] (audit HA-25).
- [AFTHL05] R. Almgren, C. Thum, E. Hauptmann, H. Li, "Direct estimation of equity market impact", *Risk* July 2005, 57-62 (free preprint). Temporary impact a power of the trading rate, exponent near 3/5. Evidence class: paper, recalled.
- [AC00] R. Almgren, N. Chriss, "Optimal execution of portfolio transactions", *Journal of Risk* 3(2) 2000, 5-39 (free preprint). Variance of the linear trajectory, continuous limit `sigma^2 X^2 T / 3`. Evidence class: paper, recalled; checked here by integrating `sigma^2 x(t)^2` with `x(t) = X (1 - t/T)` over `[0, T]`, which gives `sigma^2 X^2 T / 3`.
