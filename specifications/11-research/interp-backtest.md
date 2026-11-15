# Interpolation backtests: leave-one-out and held-out strikes

Spec version 1.0.0. Status: specified (stage J, wave 3); Python reference first. Target CLI contract 1.15.0 (J-W3-1). Rulings: `stage-j-rulings-w3.md` J-W3-8, J-W3-9, J-W3-14 to J-W3-16. Suite: `datasets/golden/stage_j/interpbt_j`, written by `oracle/python/gen_stage_j_w3.py`. Plan 14.5 row J ("held-out-strike surface backtest; leave-one-out interpolation backtest").

**Plain idea.** An interpolation scheme is only as good as its guesses between the points it was given. Hide a point, rebuild the curve from the rest, and see how far the guess lands from the hidden value. Do that for every point and you have an honest error figure for the scheme on that kind of data.

## `research.backtest.interp_loo`

Inputs `method` (`linear`, `log_linear`, `cubic_natural`, `monotone_pchip`), `x` (strictly increasing), `y`. Outputs `errors` (length `n - 2`, interior knots in order), `max_abs_error`, `rmse` (root mean square of `errors`). Conventions of `core.interp.evaluate` (`01-core/interpolation.md`). Errors: J-W3-8 (`E_INPUT`); `log_linear` with `y <= 0`: `E_DOMAIN`.

Worked example (hand): linear, `x = (0, 1, 2)`, `y = (0, 1, 0)`: knot 1 left out, the line from (0,0) to (2,0) gives 0, error `-1`; `max_abs_error = rmse = 1`.

## `research.backtest.surface_holdout`

Inputs `method` (as above, not `log_linear`), `expiries` (`T > 0`), `strikes` (log-moneyness, strictly increasing), `vols` (rows by expiry, columns by strike), `holdout` (interior strike indices, 0-based). Outputs `errors` (rows by expiry, columns by held-out index, vol units), `max_abs_error`, `rmse`. J-W3-9.

## Pass rules (fixed before any run, J-W3-16)

Both backtests are method tests, run once by `research/interp_backtest/run_interp_backtest.py`, output `research/interp_backtest/RESULTS.md`. Thresholds were chosen from prior knowledge only (stated below); no backtest had been run at the commit that adds this section.

**B1, held-out-strike surface (synthetic).** Truth: SSVI ([GJ14]) with power-law `phi(theta) = eta theta^-gamma (1 + theta)^(gamma - 1)`, `eta = 1.0`, `gamma = 0.5`, `rho = -0.4`, `theta(T) = 0.04 T`; expiries `T = 0.25, 0.5, 1, 2`; strikes `k = -0.4, -0.3, .., 0.4` (9). Two designs: (a) leave each interior strike out in turn (7 per expiry, 28 errors); (b) hold out `k = -0.3, -0.1, 0.1, 0.3` together and fit on the other 5 (16 errors). Primary method `cubic_natural` on total variance. **Pass if** max |error| at most **0.25 vol points** (0.0025) in (a) **and** at most **0.50 vol points** in (b). `linear` and `monotone_pchip` reported for information. Reason for the thresholds: a guess inside a typical half bid-ask spread on liquid index options (about 0.25 to 0.5 vol points, prior knowledge, not sourced here) is as good as a quote; spacing doubles from (a) to (b), so the allowance doubles.

**B2, leave-one-out on the real Treasury par curve.** Data: the Treasury daily par yield files stored for the shock library (2008, 2013, 2020, 2021, 2022; `datasets/scenarios/raw/`), every row with all 11 tenors 1M, 3M, 6M, 1Y, 2Y, 3Y, 5Y, 7Y, 10Y, 20Y, 30Y present (rows with any blank are skipped and counted). `interp_loo` in tenor (years), primary method `monotone_pchip`. Judged tenors: interior 3M, 6M, 1Y, 2Y, 3Y, 5Y, 7Y, 10Y, pooled over all rows. **Pass if** the pooled median |error| is at most **3 bp** **and** the pooled 95th percentile |error| at most **15 bp**. 20Y is reported separately and not judged: prior knowledge says the 20Y par yield has often sat above both 10Y and 30Y since 2020, which no interpolant through 10Y and 30Y can guess. `linear` and `cubic_natural` reported for information. Prior knowledge: the author has general knowledge of US curve shapes in these years; no file of these years had been opened for wave 3 at the commit of this section (R3 read Treasury data of all years for its own studies, which are closed).

A fail is published with the same prominence as a pass; no threshold, grid or method changes after the run without a new dated entry here labelled exploratory.

[GJ14] J. Gatheral, A. Jacquier, "Arbitrage-free SVI volatility surfaces", *Quantitative Finance* 14(1), 2014 (SSVI form, power-law example) (recalled; the surface here is a test truth, not a claim about the paper's numbers).

## Property tests

- A linear `y` gives zero error under `linear`, `cubic_natural` and `monotone_pchip`; adding a constant to `y` leaves `errors` unchanged; scaling `y` scales `errors`.

## Limitations

Synthetic truth for B1 (no free option quotes); the result says how the scheme handles a smooth SSVI smile, not a real one. B2 tests par yields, not zero or forward rates.
