# Question bank 6: Variance, GARCH, exotics and rates models

This set covers the parts of QuantForge that go beyond a single vanilla option: variance swaps and the VIX method, GARCH(1,1) volatility forecasting, the exotic and American option formulas, equity index corporate actions, and the interest-rate models (Vasicek, CIR, Hull-White, Bermudan swaptions, the LIBOR market model). It is written for a newcomer who wants to test their understanding and for a practitioner or validator who wants to know exactly which convention QuantForge pins. Each answer starts with the plain idea, then the rule as the specification states it, then a worked example where numbers help. Every worked-example number was produced by `quantforge_core` (or, where stated, by a scratch formula) and is re-checked by `verify/v06_variance_exotics_rates_models.py`. Levels: foundation, practitioner, advanced. Question bank 5 covers vanillas, smiles and surfaces.

## Variance swaps

### Q6.1 How does `vol.varswap.realized` compute realised variance, and what does it leave out on purpose?

*Level: foundation. Evidence: computed; spec; golden. Source: [Variance swaps](../../specifications/05-volatility/variance-swaps.md), [Tutorial 13](../getting-started/tutorial-13-vol-indices.md)*

A variance swap pays realised variance minus a strike agreed today. Realised variance is the average squared daily log return, annualised.

The spec: `x_i = ln(p_i/p_{i-1})`, `realized_variance = (A/m) sum x_i^2`, "no mean removed, divisor m" (ruling E-B4); `payoff = N_var (realized_variance - K_var)`, at maturity, not discounted.

**Worked example.** Golden `varswap_e-0030`: prices 100, 101, 99.5, 100.25, 102, 101.5, `A = 252`: realised variance 0.0354274, vol 0.188222 (18.82%). Against a strike of 0.04 on `N_var = 1e6`, the payoff is -4,572.61.

No demeaning is the market term-sheet convention, and on daily data the mean is tiny anyway. The goldens catch a demeaned estimate with divisor `m - 1`, the textbook sample variance, which is the wrong number for this contract.

### Q6.2 How does `vol.varswap.fair_strike` replicate the fair variance from an option strip?

*Level: practitioner. Evidence: computed; spec; literature. Source: [Variance swaps](../../specifications/05-volatility/variance-swaps.md), [Stage E rulings B](../../specifications/stage-e-rulings-b.md)*

A log contract pays expected variance, and a log contract can be copied with out-of-the-money puts and calls, each weighted by about `2/K^2`. Pricing that strip gives the fair strike.

The spec (Demeterfi, Derman, Kamal and Zou, reference point `S* = S0`, ruling E-B3): piecewise-linear weights from `f(K) = (2/T)[(K - S0)/S0 - ln(K/S0)]`; `Pi` the weighted sum of Black-Scholes option prices; `fair_variance = (2/T)[(r - q)T - (F/S0 - 1)] + Pi/D`; `pv = N_var D (fair_variance - K_var)`, long variance. `T` is ACT/365F.

**Worked example.** `S0 = 100`, one year (365 days), `r = 3%`, `q = 0`, flat 20% vol, strikes 50 to 150 in steps of 5, `dk = 5`, `K_var = 0.04`, `N_var = 1e6`: fair variance 0.0402385, fair vol 0.200595, PV 231.47. On a step of 1 (same range) the fair variance is 0.0397664, vol 0.199415.

Both errors are visible: the coarse strip overstates (discretisation), the finer one understates because the strip stops at 50 and 150 and misses the wings. Flat vol should give exactly 0.04.

### Q6.3 What weight does the discrete strip put on each option, and how close is it to `2 dK/K^2`?

*Level: advanced. Evidence: computed; spec; golden. Source: [Variance swaps](../../specifications/05-volatility/variance-swaps.md)*

The strip approximates the curved function `f(K)` with straight lines between strikes. Each option's weight is the change in slope at its strike.

The spec: calls sorted up with an extra strike `K_max + dk`, puts sorted down with `K_min - dk`; `s_j = |f(K_{j+1}) - f(K_j)|/|K_{j+1} - K_j|`, `s_{-1} = 0`, weight `w_j = s_j - s_{j-1}`. The extra strikes carry no option.

**Worked example.** Computed with a scratch formula (the library does not expose weights), case `varswap_e-0001`: `S0 = 100`, `T = 1`, calls 100 to 150 step 10. The call at 100 has weight 9.37964e-4; the call at 110 has 1.65976e-3, against the continuous `2 dK/K^2 = 1.65289e-3`.

The first weight is about half of `2 dK/K^2`, because the strip starts at `S0` and each side covers only its own half. The goldens show fair vol falling towards the continuous value as the strip gets finer (27.77%, 23.75%, 22.64%, 22.35% at three months).

### Q6.4 Why does QuantForge keep the dividend yield in the variance swap drift term when QuantLib omits it?

*Level: practitioner. Evidence: spec; design. Source: [Variance swaps](../../specifications/05-volatility/variance-swaps.md), [Stage E rulings B](../../specifications/stage-e-rulings-b.md)*

The drift term corrects for the forward not equalling the spot. If the underlying pays dividends, the forward grows at `r - q`, and the correction must use that.

The spec: QuantLib's engine writes the term as `(2/T)(rT - (e^{rT} - 1))`, which omits `q`; "with `q != 0` it is not the value of the log contract on a dividend-paying underlying". QuantForge keeps `q` (ruling E-B3), uses QuantLib only on the `q = 0` cases, and uses QuantLib's form as a wrong-convention check on the `q != 0` cases. The strip is grown at the rate (`Pi/D`, not `Pi`), another check. A negative fair variance after replication, possible on a coarse strip with a large carry, is `E_DOMAIN` (ruling E-B36).

This is a case where an outside library is treated as evidence for some cases and as a known wrong answer for others, and the spec says which.

## The VIX method

### Q6.5 How does `vol.vix.term_variance` find the forward and `K0`, and why is `K0` 95 in the worked case?

*Level: foundation. Evidence: computed; spec; golden. Source: [VIX index](../../specifications/05-volatility/vix-index.md), [Tutorial 13](../getting-started/tutorial-13-vol-indices.md)*

The VIX method is the variance-swap strip applied to real quotes. First it finds the forward from put-call parity at the strike where call and put mids are closest, then picks the strike just below the forward as the pivot `K0`.

The spec (Cboe methodology 3(a)): `K*` minimises `|C_mid - P_mid|`, lowest strike on a tie; `F = K* + e^{RT}(C_mid - P_mid)`; `K0` is the largest strike `<= F`. Then `variance = (2/T) e^{RT} sum (dK_i/K_i^2) Q(K_i) - (1/T)(F/K0 - 1)^2`, with `T = N/525600` minutes.

**Worked example.** Golden `vix_e-0001`: rate 0, 43,200 minutes, strikes 90 to 110. Forward 99.9, so `K0 = 95`, not 100; variance 0.0818816.

Choosing `K0 = 100` (above `F`) is a wrong convention the goldens catch.

### Q6.6 What does the `(F/K0 - 1)^2` correction do, and how large is it in the worked case?

*Level: practitioner. Evidence: computed; spec; golden. Source: [VIX index](../../specifications/05-volatility/vix-index.md)*

At `K0` the method uses the average of the call and the put, and one of them is in the money. The correction removes the in-the-money part, which is not variance.

The spec, formula (1) of the Cboe methodology: subtract `(1/T)(F/K0 - 1)^2`. A negative variance is returned as computed; the index refuses it.

**Worked example.** In `vix_e-0001`, the strip term alone is 0.114250; the correction removes 0.0323681 to leave 0.0818816. The correction is large here because `F = 99.9` is far from `K0 = 95` on a strip with 5-point gaps and only 30 days to expiry.

Dropping the correction is a wrong convention the goldens catch; on the real Cboe sample (strikes 5 points apart around 1960) it is small but still visible in the published digits.

### Q6.7 How does the strike selection treat zero bids and null quotes?

*Level: practitioner. Evidence: spec; design. Source: [VIX index](../../specifications/05-volatility/vix-index.md), [Stage F rulings](../../specifications/stage-f-rulings.md)*

Deep out-of-the-money options with no bid tell you little, so the method walks outwards from `K0` and stops when the market runs dry.

The spec: walking down through puts and up through calls, an option with bid 0 is skipped; the walk on that side stops at the second consecutive zero bid ([S1] 3(a)(iii)). `dK` uses the selected strikes only. Stage F (ruling F-15): a `null` bid or ask makes a null series; null series are not candidates for `K*`, a null series at `K0` is `E_INPUT`, and a null put is removed from the put walk as if not listed: it neither counts as a zero bid nor breaks a run. A bid above its ask stays `E_INPUT` (ruling F-16).

The Cboe sample calculation is a golden: the method reproduces every published digit, VIX 13.9278424 against the printed 13.93. The goldens catch `dK` from the full strip and a missing stop after two zero bids.

### Q6.8 How does `vol.vix.index` interpolate to 30 days?

*Level: advanced. Evidence: computed; spec. Source: [VIX index](../../specifications/05-volatility/vix-index.md), [Stage E rulings B](../../specifications/stage-e-rulings-b.md)*

The index is a constant 30-day measure, so it interpolates total variance (variance times time) between a near and a next expiry that bracket 30 days, then annualises.

The spec: `index = 100 sqrt([T1 s1^2 (N2 - N30)/(N2 - N1) + T2 s2^2 (N30 - N1)/(N2 - N1)] N365/N30)`, `N30 = 43200`, `N365 = 525600` minutes. Unless `N1 < N2` and `N1 <= N30 <= N2`: `E_INPUT`, no extrapolation (ruling E-B6), checked before either term.

**Worked example.** A toy using the `vix_e-0001` strip for both terms at 30,240 minutes (21 days) and 50,400 minutes (35 days): near variance 0.116974, next 0.0701842, index 28.6150. The same prices give different variances because `T` differs, which is why real use needs each expiry's own strip.

A 360-day year in minutes is a wrong convention the goldens catch.

## GARCH(1,1)

### Q6.9 How does `vol.garch.loglik` run the GARCH recursion, and what does it return for the two-return worked case?

*Level: foundation. Evidence: computed; spec; golden. Source: [GARCH](../../specifications/05-volatility/garch.md)*

GARCH(1,1) says tomorrow's variance is a constant plus a weight on today's squared return plus a weight on today's variance. Big moves raise tomorrow's variance; the effect fades.

The spec: returns as given, no mean removed (ruling E-B1). `sigma2_1` is the initial variance (`"SAMPLE"` = `(1/n) sum r_t^2`), `sigma2_{t+1} = omega + alpha r_t^2 + beta sigma2_t`, and the Gaussian log-likelihood sums every term from `t = 1`: `-1/2 sum [ln(2 pi) + ln sigma2_t + r_t^2/sigma2_t]`.

**Worked example.** Golden `garch_e-0009`: `r = (0.01, -0.02)`, `omega = 1e-5`, `alpha = 0.1`, `beta = 0.8`: variances 2.5e-4 and 2.2e-4, next variance 2.26e-4, log-likelihood 5.410998.

`alpha + beta >= 1` is allowed in the likelihood; only the forecast refuses it.

### Q6.10 What is the GARCH long-run variance, and how does `vol.garch.forecast` decay towards it?

*Level: foundation. Evidence: computed; spec; literature. Source: [GARCH](../../specifications/05-volatility/garch.md)*

With persistence `p = alpha + beta < 1`, variance forecasts decay geometrically to a long-run level.

The spec: `V_L = omega/(1 - p)`, `E[sigma2_{n+h}] = V_L + p^(h-1)(sigma2_{n+1} - V_L)`, `annualized_vol = sqrt(total_variance periods_per_year / H)`. `alpha + beta >= 1`: `E_DOMAIN` (ruling E-B2).

**Worked example.** From Q6.9 (`next_variance = 2.26e-4`, `p = 0.9`), `H = 5`, 252 periods: `V_L = 1e-4`; forecasts 2.26e-4, 2.134e-4, 2.0206e-4, 1.91854e-4, 1.826686e-4; total 1.01598e-3; annualised vol 0.226286. The half-life of a shock, `ln 0.5 / ln p`, is 6.58 periods (scratch formula, not a library output).

The goldens catch the exponent `h` instead of `h - 1`: the first forecast must equal `next_variance` itself.

### Q6.11 What do the initial-variance convention and the first likelihood term change?

*Level: practitioner. Evidence: computed; spec. Source: [GARCH](../../specifications/05-volatility/garch.md)*

The recursion needs a starting variance, and the likelihood can count or drop the first term. Both are conventions, and both change the number.

The spec: `"SAMPLE"` is the mean square with divisor `n` and no demeaning, or a positive number given by the caller; the first term is not dropped. The wrong conventions caught: initial variance `r_1^2`, the `ln(2 pi)` constant dropped, the same-day return in the recursion.

**Worked example.** The Q6.9 case with initial variance 1e-4 (which here equals `r_1^2`) instead of `"SAMPLE"` gives log-likelihood 4.872463 instead of 5.410998.

For `vol.garch.fit` the initial variance is held fixed, not estimated, so a fit is only comparable across systems that agree on it.

### Q6.12 What does `vol.garch.estimate` add over `vol.garch.fit`, and which standard errors does it report?

*Level: advanced. Evidence: spec; design; literature. Source: [GARCH](../../specifications/05-volatility/garch.md), [Stage F rulings](../../specifications/stage-f-rulings.md)*

`fit` returns only the maximised log-likelihood and is judged on that alone. `estimate` returns the parameters, their standard errors, Student-t innovations and an optional mean.

The spec: maximum likelihood over `omega > 0`, `alpha, beta >= 0`, `alpha + beta < 1`, and `2 < nu <= 500` for Student-t (t scaled to unit variance, using `nu - 2`). An answer is accepted only at an interior maximum, polished by Newton steps until the relative step is below 1e-12 (ruling F-11); a maximum on or near a bound is `E_NO_CONVERGENCE`. Standard errors are observed information, `sqrt(diag((-H)^-1))`, "Not the sandwich (QML) form, and not the expected information" (ruling F-13). With `demean`, the sample mean is removed first and held fixed, so its error is not in the standard errors (ruling F-12).

Recovery is tested: 200 simulated series, coverage of `+-2 SE` must lie in [0.90, 0.99]. A validator should remember that observed-information errors are wrong under misspecified innovations; the sandwich form is named in the spec only as the form not used.

## Exotic options

### Q6.13 How are cash-or-nothing and asset-or-nothing digitals priced?

*Level: foundation. Evidence: computed; spec. Source: [Exotics](../../specifications/04-pricing/exotics.md), [Tutorial 12](../getting-started/tutorial-12-exotics.md)*

A digital pays a fixed amount (cash) or the asset itself if it ends in the money. The probabilities come straight out of Black-Scholes.

The spec: cash-or-nothing `cash e^{-rT} N(phi d2)`; asset-or-nothing `S e^{-qT} N(phi d1)`, with `d1`, `d2` at cost of carry `b = r - q`.

**Worked example.** `S = K = 100`, `T = 1`, `r = 5%`, `q = 2%`, `v = 25%`: a cash call paying 1 is worth 0.473717; the asset call is worth 58.4955.

The goldens catch a cash digital priced on `N(d1)`. A vanilla call is the asset digital minus `K` cash digitals, which is a quick identity to test.

### Q6.14 How does QuantForge price barrier options, and how do knock-in and knock-out relate?

*Level: practitioner. Evidence: computed; spec; literature. Source: [Exotics](../../specifications/04-pricing/exotics.md), [Stage E rulings](../../specifications/stage-e-rulings.md)*

A knock-out dies if the barrier is touched; a knock-in comes alive only then. Holding both is the same as holding the vanilla, when there is no rebate.

The spec: the Reiner-Rubinstein formulas, built from six pieces `A` to `F` with a table by type and by `K > H` or `K <= H`. Continuous monitoring. Spot on or beyond the barrier is `E_DOMAIN` (ruling E-A19). "With no rebate, in plus out equals the vanilla (checked in the generator)." The goldens catch `mu` built with `r` for `b` and a dropped knock-in rebate.

**Worked example.** Q6.13 market, barrier 90: down-and-in call 2.98495, down-and-out call 8.13881, sum 11.1238, equal to the vanilla call 11.1238.

The knock-out rebate is paid at the hit, the knock-in rebate at expiry if never hit; these are different contracts, not a sign convention.

### Q6.15 How does discrete barrier monitoring work in QuantForge, and where does it refuse to answer?

*Level: practitioner. Evidence: computed; spec; design. Source: [Exotics](../../specifications/04-pricing/exotics.md), [R6 rulings](../../specifications/r6-rulings.md), [Stage G rulings](../../specifications/stage-g-rulings.md)*

A barrier observed once a day is touched less often than a continuous one. Broadie, Glasserman and Kou showed this is close to a continuous barrier moved away from spot.

The spec: with `DISCRETE`, the barrier becomes `H exp(-beta v sqrt(dt))` (down) or `H exp(+beta v sqrt(dt))` (up), `beta = 0.5826`, `dt = T/n` (ruling G-7). Ruling R6-2.1 adds an envelope: the BGK price is returned only for a regular knock-out (down-and-out call with `H <= K`, up-and-out put with `H >= K`), no rebate, and `|ln(S/H)| >= 1.25 v sqrt(dt)`; everything else is `E_DOMAIN`, because Monte Carlo showed reverse barriers off by 1.6% to 120%.

**Worked example.** Q6.13 market, `H = 90`, daily (`m = 252`): the shifted barrier is 89.1780 and the down-and-out call is 8.51904, against 8.13881 continuous. The matching down-and-out put is refused with `E_DOMAIN`.

Refusing a known-bad answer is a design choice the validator should welcome, not route around.

### Q6.16 What is the volatility of a continuous geometric Asian, and why are arithmetic Asians missing?

*Level: foundation. Evidence: computed; spec. Source: [Exotics](../../specifications/04-pricing/exotics.md)*

Averaging smooths the path, so an Asian behaves like a vanilla on a less volatile asset. For a geometric average the result is exactly lognormal.

The spec: continuous (Kemna-Vorst) `GBS(type, S, K, T, r, b_A, v/sqrt 3)` with `b_A = (b - v^2/6)/2`; discrete with `n` fixings uses the exact mean and variance of the log average. Fixings are from today, no past fixings. "Arithmetic Asians are not in stage E (they need Monte Carlo or an approximation; register row EA16)."

**Worked example.** Q6.13 market: the continuous geometric call is 5.98020; with quarterly fixings (0.25, 0.5, 0.75, 1.0) it is 7.21829, closer to the vanilla 11.1238 because four points average less.

The goldens catch a continuous vol of `v/2`. A trader quoting an arithmetic Asian cannot use these prices directly; the geometric price is at best a control variate.

### Q6.17 How does `exotic.lookback.floating` price a floating-strike lookback, and when does it refuse?

*Level: advanced. Evidence: computed; spec; literature. Source: [Exotics](../../specifications/04-pricing/exotics.md), [Stage E rulings](../../specifications/stage-e-rulings.md)*

A floating-strike lookback call pays the final price minus the minimum seen, so it always ends in the money. Its value depends on the running minimum so far.

The spec: Goldman-Sosin-Gatto, continuous monitoring, `running_extreme` the minimum so far for a call (`<= S`) or the maximum for a put. The formula divides by `b`, so `|b| <= 1e-8 v^2` is `E_DOMAIN` (rulings E-A20, E-A28); near that bound binary64 loses digits and the golden at `b = 1e-5` is judged to 1e-8.

**Worked example.** Q6.13 market, call: with a running minimum of 95 the price is 19.6806; with a fresh option (minimum 100) it is 19.2981.

The goldens catch the formula without its reflection term. A desk with zero carry (`r = q`) needs a different route, since the library refuses that point rather than return a value with few correct digits.

### Q6.18 Which way does the quanto adjustment move the drift?

*Level: practitioner. Evidence: computed; spec; literature. Source: [Exotics](../../specifications/04-pricing/exotics.md)*

A quanto pays a foreign asset's return in domestic currency at a fixed rate. Under the domestic measure the asset's drift picks up a correlation term with the FX rate.

The spec: `GBS(type, S, K, T, rd, rf - q - rho v fx_vol, v)`, with `rho` the correlation between the asset and the FX rate quoted domestic per foreign [Haug ch. 5].

**Worked example.** `S = K = 100`, `T = 1`, `rd = 5%`, `rf = 3%`, `q = 2%`, `v = 25%`, FX vol 10%: with `rho = -0.3` the call is 10.4089; with `rho = 0` it is 9.99561. Negative correlation raises the carry by `0.3 x 0.25 x 0.10 = 0.75%`.

The goldens catch the adjustment with the wrong sign. The correlation's sign depends on how the FX rate is quoted, so the quote direction is part of the input.

### Q6.19 Why is a simple chooser cheaper than a call plus a put?

*Level: foundation. Evidence: computed; spec; literature. Source: [Exotics](../../specifications/04-pricing/exotics.md)*

A chooser lets the holder pick, at a set date, whether the option is a call or a put. They get one option, not both, so it is worth less than a straddle.

The spec: Rubinstein's simple chooser (same strike and expiry): `price = S e^{(b-r)T} N(d) - K e^{-rT} N(d - v sqrt T) - S e^{(b-r)T} N(-y) + K e^{-rT} N(-y + v sqrt t)`, `t` the choice date in `(0, T]`.

**Worked example.** Q6.13 market with the choice at 0.5 years: chooser 16.5745, against call 11.1238 plus put 8.22684 = 19.3506.

The goldens catch the chooser priced as call plus put. At `t = T` the chooser is the straddle; at `t` near 0 it approaches the more valuable of the two vanillas.

### Q6.20 What is Kirk's approximation, and what does it reduce to at zero strike?

*Level: practitioner. Evidence: computed; spec; literature. Source: [Exotics](../../specifications/04-pricing/exotics.md), [Stage E rulings](../../specifications/stage-e-rulings.md)*

A spread option pays `F1 - F2 - K` if positive. Kirk treats `F2 + K` as one lognormal asset with an adjusted vol, which gives a Black-like formula.

The spec: `f = F2/(F2 + K)`, `s = sqrt(v1^2 - 2 rho v1 v2 f + v2^2 f^2)`, price `e^{-rT}(F1 N(d1) - (F2 + K) N(d1 - s sqrt T))`. Strike any sign with `F2 + K > 0` (ruling E-A39). At `K = 0` it is Margrabe's exchange option, exact.

**Worked example.** `F1 = 50`, `F2 = 45`, `T = 1`, `r = 5%`, vols 30% and 25%, correlation 0.6: strike 3 gives 5.57790; strike 0 (Margrabe) gives 7.26362.

The goldens catch Kirk without the `F2/(F2+K)` weight. Kirk is an approximation away from `K = 0`, and its error grows with the strike.

### Q6.21 How does `exotic.basket.moment` price a basket option, and why does it refuse negative weights?

*Level: practitioner. Evidence: computed; spec; literature. Source: [Exotics](../../specifications/04-pricing/exotics.md), [Stage E rulings](../../specifications/stage-e-rulings.md)*

A basket of lognormal assets is not lognormal, but its first two moments can be matched by one lognormal, which Black then prices.

The spec (Levy 1992): `M1 = sum w_i F_i`, `M2 = sum_i sum_j w_i w_j F_i F_j e^{rho_ij v_i v_j T}`, `v_B = sqrt(ln(M2/M1^2)/T)`, price `GBS(type, M1, K, T, r, 0, v_B)`. Negative weights (spreads) are refused: use Kirk (ruling E-A21).

**Worked example.** Two forwards at 100, weights 0.5 each, vols 20% and 30%, correlation 0.5, `T = 1`, `r = 3%`, ATM call: basket vol 0.218660, price 8.44862.

The goldens catch a basket vol taken as the weighted average of vols (25% here), which ignores diversification. With negative weights `M1` can approach zero and moment matching fails, hence the refusal.

## American options

### Q6.22 How does `exotic.american.crr` value an American put, and what is its early exercise premium?

*Level: foundation. Evidence: computed; spec; literature. Source: [Exotics](../../specifications/04-pricing/exotics.md), [Tutorial 12](../getting-started/tutorial-12-exotics.md)*

A binomial tree steps the stock up or down; at each node the American holder takes the larger of exercising now and holding on.

The spec: Cox-Ross-Rubinstein with Hull's dividend-yield probability, `u = e^{v sqrt dt}`, `d = 1/u`, `p = (e^{(r-q)dt} - d)/(u - d)`; `p` outside `(0, 1)` is `E_DOMAIN`. The exercise test runs at every node, including `i = 0`. Outputs `american`, `european` (same tree), and their difference.

**Worked example.** `S = K = 100`, `T = 1`, `r = 5%`, `q = 0`, `v = 25%`, 500 steps, put: American 7.97237, European 7.45400, early exercise premium 0.518373.

Taking the difference on the same tree cancels most of the tree's own error, which is why the premium is more accurate than either price alone. The goldens catch a tree probability without `q`.

### Q6.23 How does Barone-Adesi-Whaley compare with the tree, and what does QuantForge refuse?

*Level: practitioner. Evidence: computed; spec; design. Source: [Exotics](../../specifications/04-pricing/exotics.md), [Stage E rulings](../../specifications/stage-e-rulings.md)*

BAW is a fast analytic approximation: the European price plus an early-exercise term fitted at a critical stock price found by a one-dimensional root.

The spec: `M = 2r/v^2`, `N = 2b/v^2`, `K_T = 1 - e^{-rT}`; the put uses root `q1 = (-(N-1) - sqrt((N-1)^2 + 4M/K_T))/2` and critical price `S**`. `r <= 0` is `E_DOMAIN` (rulings E-A22, E-A30); a call with `b >= r` is European. Judged to 1e-5 per unit.

**Worked example.** The Q6.22 put: BAW 7.98252 against the 500-step tree's 7.97237.

The goldens catch a BAW put using the call root. The `r <= 0` refusal matters in negative-rate markets: there BAW's formula breaks down, and the tree or finite-difference route is the one to use.

### Q6.24 What is the pinned finite-difference scheme in `exotic.american.fd`, and what does it return?

*Level: advanced. Evidence: computed; spec; design. Source: [Exotics](../../specifications/04-pricing/exotics.md), [Stage E rulings](../../specifications/stage-e-rulings.md)*

The PDE route solves the Black-Scholes equation backwards on a grid in log-spot, projecting onto the payoff after each step for American exercise.

The spec (ruling E-A23): `x = ln S`, grid centred on `ln S` with half-width `width v sqrt T`, `nx` odd; backward Euler in time-to-expiry with central differences; American boundary rows hold intrinsic value; after each solve `V = max(V, payoff)`. Outputs at the centre node: `price`, `delta = (V_{i+1} - V_{i-1})/(2 dx S)`, and `gamma` with the log-grid correction term.

**Worked example.** The Q6.22 put on `nx = 201`, `nt = 200`, width 5: price 7.95708, delta -0.409299, gamma 0.0177448.

The scheme is pinned so four languages agree to rounding; it is first order in time, and here sits about 0.015 below the 500-step tree. The goldens catch the scheme without the exercise projection, which returns the European price.

## Equity index

### Q6.25 How does `eq.corporate_action.adjust` adjust an option for a rights issue?

*Level: foundation. Evidence: computed; spec. Source: [Equity index](../../specifications/04-pricing/equity-index.md)*

After a corporate action the share price jumps for a reason that is not market risk. Options are adjusted so that their holders are neither richer nor poorer.

The spec: rights factor `f = TERP/P`, `TERP = (P + m K)/(1 + m)`; `ex_price = f P`, `adjusted_shares = shares/f`, `adjusted_strike = f strike`. Splits use `1/ratio`; a special dividend `(P - amount)/P`. A ratio, `m` or `K` `<= 0`, or an amount `>= P` or `<= 0`, is `E_DOMAIN`.

**Worked example.** `P = 50`, one new share per four old (`m = 0.25`) at 40, option on 1,000 shares struck at 48: factor 0.96, theoretical ex price 48, adjusted shares 1,041.67, adjusted strike 46.08.

The check a validator runs: `adjusted_shares x adjusted_strike` equals the original `1,000 x 48`, so the total strike amount is unchanged.

## Short-rate models

### Q6.26 What does the Vasicek bond formula give, and what small-`a` trap does the spec warn about?

*Level: foundation. Evidence: computed; spec; literature. Source: [Short-rate models](../../specifications/04-pricing/short-rate-models.md), [Tutorial 6](../getting-started/tutorial-6-hull-white.md)*

Vasicek lets the short rate mean-revert to a level with normal shocks. Bond prices then have a closed form `P = A exp(-B r)`.

The spec: `B = (1 - e^{-a tau})/a`, `ln A = (B - tau)(a^2 b - sigma^2/2)/a^2 - sigma^2 B^2/(4a)` [BM 3.10]; risk-neutral, no market price of risk. Small `a` (ruling G-2): `B` and `(B - tau)/a^2` cancel; evaluate `B` with `expm1` and use the series `-a tau^2/2 + a^2 tau^3/6 - ...` when `a tau < 1e-2`.

**Worked example.** `a = 0.1`, `b = 4%`, `sigma = 1%`, `r = 3%`, five-year bond: discount factor 0.852828, zero rate 0.0318394 (continuous).

The goldens catch Vasicek without `-sigma^2 B^2/(4a)`. The small-`a` case is excluded from the QuantLib outside count because QuantLib shows the cancellation itself.

### Q6.27 How does CIR differ from Vasicek, and does QuantForge require the Feller condition?

*Level: advanced. Evidence: computed; spec; literature. Source: [Short-rate models](../../specifications/04-pricing/short-rate-models.md), [Stage G rulings](../../specifications/stage-g-rulings.md)*

CIR scales the shock by `sqrt(r)`, so rates cannot go negative. Bond options then need the noncentral chi-square distribution.

The spec: `dr = a(b - r)dt + sigma sqrt(r) dW`; "The Feller condition `2 a b >= sigma^2` is not required" (ruling G-1). `gamma = sqrt(a^2 + 2 sigma^2)`. Options use the noncentral chi-square CDF, summed from the Poisson mode with log weights (ruling G-32); goldens at `sigma = 0.005`, where a naive `exp(-lambda/2)` returns 0.

**Worked example.** `a = 0.2`, `b = 4%`, `sigma = 5%`, `r = 3%`, five years: discount factor 0.845733, zero rate 0.0335102. Feller holds here: `2ab = 0.016` against `sigma^2 = 0.0025`.

The goldens catch `gamma = sqrt(a^2 + sigma^2)`. CIR swaptions need `r* >= 0`; without such a root the case is `E_DOMAIN`.

### Q6.28 How does Jamshidian's decomposition price a European swaption on Hull-White?

*Level: practitioner. Evidence: computed; spec; literature. Source: [Short-rate models](../../specifications/04-pricing/short-rate-models.md), [Tutorial 6](../getting-started/tutorial-6-hull-white.md)*

In a one-factor model every bond price falls as the short rate rises. So a swaption (an option on a coupon bond) splits into a sum of options on zero-coupon bonds, struck at their values at one critical rate.

The spec: coupons `c_i = K tau_i` plus 1 on the last; find `r*` with `sum c_i P(T0, Ti; r*) = 1`; receiver `= notional sum c_i ZBC(0, T0, Ti, X_i)`, payer the same with puts. Hull-White fits `theta(t)` to the curve (log-linear discount factors, right-hand forward at pillars, ruling G-3); the swaption takes no `short_rate`.

**Worked example.** Flat 3% continuous curve, `a = 0.05`, `sigma = 1%`, 1 into 5 years annual, strike 3%, 1m notional: payer 16,820.35, receiver 14,802.86, forward swap rate 3.04545%. Payer minus receiver, 2,017.49, equals `annuity (F - K)`.

That parity is asserted on every golden pair. The goldens catch Ho-Lee `sigma_p` and a strike of 1 on every bond option.

### Q6.29 Why does the Bermudan swaption scheme sit below Jamshidian for a single exercise date?

*Level: advanced. Evidence: computed; spec; design. Source: [Short-rate models](../../specifications/04-pricing/short-rate-models.md), [Stage G rulings](../../specifications/stage-g-rulings.md)*

The Bermudan is priced on a pinned finite-difference grid in the Hull-White state. Like any first-order scheme it has a bias, and the spec states it rather than hides it.

The spec (ruling G-18): fully implicit steps on `x = r - alpha(t)`, exercise applied on arriving at each exercise time, never at `t = 0`. The order is 1 in time; at the default grid (201 nodes, 100 steps a year) the scheme is about 0.1% to 0.2% below QuantLib's engines. Ruling G-28: a Bermudan is compared with the scheme's own single-date value on the same grid, never with Jamshidian.

**Worked example.** The Q6.28 payer, exercisable at 1, 2, 3, 4 and 5 years, default grid, width 6: Bermudan 24,213.20. With only the first date on the same grid: 16,795.40, against Jamshidian 16,820.35 (0.15% low).

A property test that asserted "Bermudan at least Jamshidian" would fail in edge cases for reasons that have nothing to do with optionality, which is why G-28 forbids it.

### Q6.30 How does `rates.shortrate.hw_calibrate` fit Hull-White, and what does it hold fixed?

*Level: practitioner. Evidence: spec; design. Source: [Short-rate models](../../specifications/04-pricing/short-rate-models.md), [Stage G rulings](../../specifications/stage-g-rulings.md)*

Calibration chooses the model's volatility so that it reprices a set of market swaptions. QuantForge fits `sigma` only.

The spec (ruling G-17): `a` fixed; minimise `F(sigma) = sum (model_i(sigma) - target_i)^2`, unweighted, prices per unit notional by Jamshidian, on `[1e-4, 1]`; a minimum at an end is `E_NO_CONVERGENCE`. Outputs `sigma`, fitted prices and RMSE. The goldens assert a unique interior minimum by a scan, so the answer does not depend on the solver; one golden recovers `sigma = 0.007` exactly from unperturbed targets.

Limits worth stating: mean reversion is not calibrated (it is notoriously poorly identified from European swaptions alone), the fit is in price not vol, so long expiries with large premiums dominate, and no outside case counts (QuantLib only reprices at the golden `sigma`).

## LIBOR market model

### Q6.31 How does `rates.lmm.capfloor` price a caplet in the LMM, and what flat vol does it report?

*Level: practitioner. Evidence: computed; spec; golden. Source: [LMM](../../specifications/04-pricing/lmm.md), [Tutorial 16](../getting-started/tutorial-16-lmm.md)*

Each forward rate in the LMM is lognormal under its own payment measure, so a caplet is Black's formula with the variance equal to the integral of the forward's squared volatility up to its fixing.

The spec (ruling G-22): abcd volatility `sigma_T(t) = (a + b(T - t)) exp(-c(T - t)) + d`; `v_i^2 = integral_0^{t_(i-1)} sigma^2 dt`; `caplet_i = notional tau_i P(t_i) Black(F_i, K, v_i)`; `black_vols = v_i/sqrt(t_(i-1))`. Forward rates or strikes `<= 0`: `E_DOMAIN` (no shifted LMM).

**Worked example.** Humped abcd `(-0.06, 0.17, 0.54, 0.17)`, flat 3% continuous curve, semi-annual cap to 5 years at 3%, 1m notional: price 17,075.83; first three Black vols 0.154679, 0.186867, 0.208842, matching the spec's 0.1547, 0.1869, 0.2088 for `lmmcap_g-0001` (whose curve differs, but the vols depend only on the abcd shape).

The goldens catch variance integrated to the payment date instead of the fixing date.

### Q6.32 How does correlation enter Rebonato's swaption volatility, and how much does it matter?

*Level: advanced. Evidence: computed; spec; literature. Source: [LMM](../../specifications/04-pricing/lmm.md), [Stage G rulings](../../specifications/stage-g-rulings.md)*

A swap rate is a weighted average of forwards. If the forwards are less than perfectly correlated, the average moves less than its parts, so the swaption vol falls.

The spec [BM 6.13]: frozen weights `w_i = tau_i P(T_i)/A`, `rho_ij = exp(-beta |T_(i-1) - T_(j-1)|)`, `v^2 = (1/S^2) sum_i sum_j w_i w_j F_i F_j rho_ij C(T_(i-1), T_(j-1); T_0)`, price `notional A Black(S, K, v)`.

**Worked example.** Q6.31 curve and abcd, 5 into 5 years annual, payer at 3.5%, 1m notional: at `beta = 0` the Black vol is 0.228102 and the price 17,923.65; at `beta = 0.5` the vol is 0.166780 and the price 11,403.62. The spec's case `lmmswn_g` reports 0.2283 and 0.1670 on its own curve; the small gap is the curve, since the frozen weights and forwards depend on it.

Rebonato is an approximation; the simulated LMM puts its error at 0.41% to 0.47% on this case, inside the stated `3 SE + 1%` band. The goldens catch correlation ignored at `beta = 0.5`.
