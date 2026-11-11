# F3 sensitivities: inflation01, dividend and borrow, correlation (stage F carry-over)

Spec version 1.0.0. Status: Specified (stage F carry-over wave 2b, landed in stage G). Ruling `stage-g-rulings.md` G-47. Suite `stage_f/risk_f3b` (18 cases), written by `oracle/python/gen_stage_f_f3b.py`.

**Plain idea.** A risk report lists, for each market input, how much the book gains or loses for a small move in that input. Three inputs were missing from stage F. Inflation01 is the change in value for a one basis point rise in the market inflation rate. Dividend and borrow sensitivity is the change for a one basis point rise in the dividend yield or in the stock-borrow cost; both reduce the forward, so they have the same size and sign for a European option. Correlation sensitivity is the change for a one percentage point rise in the correlation between two assets, shown on the simplest correlation product, the exchange option.

Sources (pointers): [Hull] J. Hull, *Options, Futures, and Other Derivatives*, 10th ed., Pearson, 2018 (Black-Scholes-Merton with a continuous yield; Greeks) (not opened); [Margrabe] W. Margrabe, "The value of an option to exchange one asset for another", *Journal of Finance* 33(1), 1978; [Kerkhof] J. Kerkhof, *Inflation Derivatives Explained*, 2005 (zero-coupon inflation swap) (not opened). Outside: QuantLib 1.44 `AnalyticEuropeanEngine.dividendRho` and `AnalyticEuropeanMargrabeEngine`.

## `risk.sens.inflation01`

Inputs: `notional`, `years` `n` (integer >= 1), `fixed_rate` `K`, `market_rate` `z` (`1 + z > 0`, else `E_DOMAIN`), `discount_factor` `P > 0` (else `E_DOMAIN`). Receive-inflation zero-coupon swap, as `02-curves/inflation.md`: `pv = N P ((1 + z)^n - (1 + K)^n)`. Outputs `pv`, `inflation01 = N P n (1 + z)^(n-1) x 1e-4` (analytic), `inflation01_bump = pv(z + 1e-4) - pv(z)` (the one-sided bump a desk sees). Example (`-0001`): 10 years, notional 10 million: analytic 9,532.25, bump 9,536.42 (the bump includes the convexity).

## `risk.sens.dividend_borrow`

Inputs: `spot`, `strike`, `expiry_years`, `rate`, `dividend_yield`, `borrow_rate`, `vol` (> 0), `option_type` (`CALL`, `PUT`). Black-Scholes-Merton with yield `y = dividend_yield + borrow_rate` [Hull]. `dividend01 = borrow01 = dV/dy x 1e-4`, with `dV/dy = -T S e^(-yT) N(d1)` (call) and `+T S e^(-yT) N(-d1)` (put). Outputs `price`, `dividend01`, `borrow01`. Example (`-0006`): at-the-money one-year call, `dividend01 = -0.005439` per 100 spot.

## `risk.sens.correlation`

Inputs: `spot1`, `spot2`, `quantity1`, `quantity2`, `yield1`, `yield2`, `vol1`, `vol2`, `correlation` in `[-1, 1]` (else `E_DOMAIN`; a zero spread volatility is `E_DOMAIN`), `expiry_years`. Option to receive `Q1 S1` for `Q2 S2` [Margrabe]: `s = sqrt(v1^2 + v2^2 - 2 rho v1 v2)`, `F_k = Q_k S_k e^(-q_k T)`, `price = F1 N(d1) - F2 N(d1 - s sqrt T)`. `correlation01 = (dV/ds)(ds/drho) x 0.01` with `dV/ds = F1 n(d1) sqrt T`, `ds/drho = -v1 v2 / s`. Outputs `price`, `correlation01`, `spread_vol`. Example (`-0013`): `rho = 0.5`, price 13.832, `correlation01 = -0.0998` (higher correlation narrows the spread).

## Outside share

9 of 18 count: the dividend and borrow cases against QuantLib `dividendRho` (maturities on whole days), and the correlation cases against a central QuantLib Margrabe bump (`h = 1e-4`, agreement 1e-6 relative). inflation01 and the error cases do not count.

## Convergence and limit cases

| Method | Asserted order | Measured on | Limit case | Reference |
|---|---|---|---|---|
| Analytic Greeks | exact | `risk_f3b` | `n = 1` at the money: `pv = 0` (`-0002`) | closed form |
| QuantLib correlation bump (evidence) | `h^2` | `h = 1e-4` | none | QuantLib Margrabe |
