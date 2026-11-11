# Portfolio risk tools: reverse stress, limits, concentration, liquidity-adjusted VaR, volatility by horizon (F4 carry-over)

Spec version 1.0.0. Status: Specified (stage F carry-over wave 2b, landed in stage G). Ruling: `stage-g-rulings.md` G-46. Suite `stage_f/risk_f4b` (25 cases), written by `oracle/python/gen_stage_f_w2b.py`. The F4 model-risk reserve item is `06-risk/model-reserve.md` (Q9 part 2).

**Plain idea.** Value at risk answers "how much could we lose?". A risk desk also asks the reverse ("how big a move along this scenario costs us a given amount?"), checks each measure against its limit, watches whether exposure sits in a few names, adds the cost of getting out of positions when markets are thin, and converts a one-day volatility to a longer horizon without assuming that daily returns are independent. Each tool here is a closed form on its inputs.

Sources (pointers, not opened in this session):
- [Breuer] T. Breuer, M. Jandacka, K. Rheinberger, M. Summer, "How to find plausible, severe and useful stress scenarios", *International Journal of Central Banking* 5(3), 2009 (reverse stress along a scenario direction).
- [BCBS-LE] Basel Committee, *Supervisory framework for measuring and controlling large exposures*, 2014; Herfindahl-Hirschman index as the standard concentration measure (S. Rhoades, "The Herfindahl-Hirschman index", *Federal Reserve Bulletin* 79, 1993).
- [Bangia] A. Bangia, F. Diebold, T. Schuermann, J. Stroughair, "Modeling liquidity risk, with implications for traditional market risk measurement and management", 1999 (exogenous spread cost `1/2 P (mu + z sigma)`).
- [Lo-MacKinlay] A. Lo, C. MacKinlay, "Stock market prices do not follow random walks", *Review of Financial Studies* 1(1), 1988 (variance of multi-period sums under autocorrelation); F. Diebold, A. Hickman, A. Inoue, T. Schuermann, "Converting 1-day volatility to h-day volatility: scaling by sqrt(h) is worse than you think", 1997.

## `risk.stress.reverse`

Inputs: `direction` `d`, `delta` `delta`, `gamma` `Gamma` (square, matching lengths, else `E_INPUT`), `target_loss` `L > 0` (else `E_DOMAIN`).

Formal statement: delta-gamma P&L along `k d` is `PnL(k) = b k + a k^2` with `b = delta . d`, `a = d' Gamma d / 2`. The output `scale` is the smallest `k > 0` with `PnL(k) = -L`; no such root is `E_DOMAIN`. Outputs `scale`, `shocks = k d`, `pnl` (equal to `-L`, asserted). Builds solve the quadratic with the cancellation-free form `q = -(b + sign(b) sqrt(b^2 - 4 a L))/2`, roots `q/a` and `L/q`.

Worked example (`risk_f4b-0001`): `b = -1,275`, `a = -1,107.8`; the loss of 50 is reached at `k = 0.037942`; without gamma (`-0002`) at `50/1,275 = 0.039216`.

## `risk.limits.check`

Inputs: `measures` (name to value), `limits` (name to `{soft, hard}`, `0 <= soft <= hard`, else `E_DOMAIN`; every measure needs a limit, else `E_INPUT`). Per measure: `utilisation = |value|/hard`; status `BREACH` if `|value| > hard`, `WARN` if `|value| >= soft`, else `OK`. `overall` is the worst status. Names in code-point order.

## `risk.concentration.measures`

Inputs: `exposures` (at least one, not all zero, else `E_DOMAIN`), `top_n` (1 to the count, else `E_INPUT`). Weights `w_i = |x_i| / sum |x|`; `hhi = sum w_i^2` [BCBS-LE]; `effective_number = 1/hhi`; `top_n_share` = sum of the `top_n` largest weights. Example: four equal names give `hhi = 0.25`, effective number 4.

## `risk.var.liquidity_adjusted`

Inputs: `var` (>= 0), `z`, `position_values`, `spread_mean`, `spread_vol` (relative bid-ask spreads, `>= 0`, else `E_DOMAIN`; same lengths, else `E_INPUT`). `liquidity_cost = (1/2) sum |P_i| (mu_i + z sigma_i)`, `lvar = var + liquidity_cost` [Bangia]. Example (`-0017`): cost 22,874.50 on a VaR of 1.2 million.

## `risk.vol.horizon`

Inputs: `daily_vol` `sigma > 0`, `ar1` `rho` with `|rho| < 1` (else `E_DOMAIN`), `horizon_days` `h >= 1` (else `E_DOMAIN`). With AR(1) daily returns, `Var(sum of h) = sigma^2 (h + 2 sum_(k=1)^(h-1) (h - k) rho^k)` [Lo-MacKinlay]. Outputs `vol`, `sqrt_rule_vol = sigma sqrt(h)`, `variance_ratio`. Example: `rho = 0.2`, 10 days: ratio 1.4375, so the square-root rule understates 10-day volatility by about 17%.

## Tolerances and outside share

1e-12 absolute plus 1e-12 relative. Outside: none (stage F share unchanged in count; its denominator grows by these 25 cases if they are counted in stage F).

## Convergence and limit cases

| Method | Asserted order | Measured on | Limit case | Reference |
|---|---|---|---|---|
| Reverse stress quadratic | exact | `risk_f4b` | `Gamma = 0`: `k = L / (-b)` (`-0002`) | closed form |
| Horizon scaling | exact | `risk_f4b` | `rho = 0`: square-root rule (`-0020`) | [Lo-MacKinlay] |
