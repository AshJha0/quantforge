# Question bank 5: Options, smiles and volatility surfaces

This set is for two readers: someone who has met Black-Scholes once and wants to check they can use it, and a practitioner who wants to confirm how QuantForge states each convention before trusting a number from it. It runs from vanilla pricing and Greeks through smile parameterisations (SVI, SSVI, SABR), arbitrage checks, local and forward vol, the Heston family, FX smile conventions and the rates vol layer (caps, swaptions, caplet stripping, the SABR cube). Each answer gives the plain idea first, then the rule as the specification states it, then a worked example where numbers help. Every number in a worked example was produced by `quantforge_core` (or, where stated, a scratch formula) and is re-checked by `verify/v05_options_vol_surfaces.py`. Levels: foundation (you should know this before using the library), practitioner (what a desk or validator checks), advanced (the edge cases and design choices). Try to answer before reading.

## Black-Scholes, Black-76 and Bachelier

### Q5.1 What does QuantForge return for a one-year at-the-money Black-Scholes call, and how does put-call parity check it?

*Level: foundation. Evidence: computed; spec. Source: [Black models](../../specifications/05-volatility/black-models.md), [Tutorial 3](../getting-started/tutorial-3-options-vol.md)*

The Black-Scholes model turns a volatility into a price by working on the forward: grow the spot at the rate less the dividend yield, price a lognormal option on that forward, and discount.

The spec writes every lognormal model the same way: `F = S exp((r-q)T)`, `D = exp(-rT)`, `d1 = (ln(F/K) + v^2 T/2)/(v sqrt T)`, `d2 = d1 - v sqrt T`, `V = D phi (F N(phi d1) - K N(phi d2))`, with `phi = +1` for a call and `-1` for a put.

**Worked example.** `S = K = 100`, `T = 1`, `r = 3%`, `q = 1%`, `v = 20%`. The call is 8.827321 and the put 6.866891. Their difference, 1.960430, equals `D (F - K)` to rounding, which is put-call parity.

Parity is the cheapest sanity check a validator has: it holds for any volatility, so a gap points at the forward or the discounting, not at the model.

### Q5.2 How do the three models in `vol.option.price` differ in what they take as inputs?

*Level: foundation. Evidence: spec. Source: [Black models](../../specifications/05-volatility/black-models.md)*

They share one pricing kernel but disagree on where the forward and the discount factor come from, and on what "volatility" means.

The spec's table: `BLACK_SCHOLES` takes `spot`, `rate`, `yield` and builds `F` and `D` itself; `BLACK_76` takes `forward` and `discount_factor` as given, with an optional `shift` that turns `F` and `K` into `F+s`, `K+s`; `BACHELIER` takes `forward` and `discount_factor` and allows a negative forward. An input listed for another model, or a missing one, is `E_SCHEMA`. For the lognormal models `vol` is a relative volatility; for Bachelier it is in price units per square root of a year.

The practical consequence is that a vol number cannot move between models unchanged. A 20% Black vol and a 0.7% (70bp) normal vol may describe the same option; reading one as the other gives nonsense, and the schema check exists so that a request cannot silently mix them.

### Q5.3 How is a Bachelier option priced, and what does it give for an at-the-money option and for one on a negative forward?

*Level: practitioner. Evidence: computed; spec. Source: [Black models](../../specifications/05-volatility/black-models.md)*

Bachelier assumes the forward moves by normal (additive) shocks, so it has no trouble with zero or negative rates.

Formal rule: `d = (F-K)/(v sqrt T)`, `V = D (phi (F-K) N(phi d) + v sqrt T n(d))`. At the money `d = 0`, so the price collapses to `D v sqrt T n(0) = D v sqrt(T/(2 pi))`.

**Worked example.** `F = K = 1%`, `T = 1`, `D = 0.97`, normal vol 0.7% (70bp a year): the call is 0.00270882 per unit notional, matching `0.97 x 0.007 / sqrt(2 pi)`. With `F = -0.10%` and `K = -0.20%` (same vol, `D`, `T`) the call is 0.00322141; the lognormal models would refuse these inputs with `E_DOMAIN`.

The desk point: the ATM Bachelier price is linear in vol, which is why normal vols are the natural quote for rates near zero.

### Q5.4 What does a shift do in Black-76, and what does it price for a negative forward?

*Level: practitioner. Evidence: computed; spec. Source: [Black models](../../specifications/05-volatility/black-models.md), [SABR](../../specifications/05-volatility/sabr.md)*

A shift moves the lognormal model's floor from zero to `-s`, so a forward of `-0.1%` can still have a lognormal vol.

The spec: with `shift` `s`, `F` and `K` become `F+s` and `K+s`; the domain checks then require `forward + shift > 0` and `strike + shift > 0`, else `E_DOMAIN`. The output `forward` is the unshifted one.

**Worked example.** `F = -0.10%`, `K = 0`, `s = 2%`, `T = 2`, `D = 0.95`, shifted vol 20%: the call is 0.00164230.

The pitfall is treating a shifted vol as comparable across different shifts. A 20% vol at a 2% shift and a 20% vol at a 3% shift are different smiles, so the shift is part of the quote and must travel with it.

### Q5.5 How does `vol.option.implied` decide that a price has no implied volatility?

*Level: foundation. Evidence: computed; spec. Source: [Black models](../../specifications/05-volatility/black-models.md)*

Implied volatility runs the pricer backwards. It exists only for prices between the discounted intrinsic value and the price at infinite volatility.

The spec checks, all `E_DOMAIN`: `expiry_years = 0`; `price < I` with `I = D max(phi (F-K), 0)`; for lognormal models `price >= U`, with `U = D F` for a call and `D K` for a put. A price exactly at `I` returns `vol = 0`. Any solver is allowed; the result is judged, not the path, and must stop at `|V(v) - price| <= 1e-13 max(1, price)` or better. A failed solve is `E_NO_CONVERGENCE`, which a correct build never meets on valid inputs.

**Worked example.** Feeding the Q5.1 call price 8.827321 back in returns a vol of 0.200000.

Why the upper bound matters: a lognormal call can never be worth more than the discounted forward, so a quote above it is a data error, not a high-vol market.

### Q5.6 Why do the goldens stop where vega falls below `1e-3 max(price, 1)`?

*Level: advanced. Evidence: computed; spec. Source: [Black models](../../specifications/05-volatility/black-models.md)*

When vega is tiny, a large change in vol barely moves the price, so the price carries almost no information about vol and the inverse problem is ill-conditioned.

The spec's limit: "Implied vol is ill-conditioned when vega is tiny: goldens stop at `vega >= 1e-3 max(price, 1)`." The solver still runs below that line; the conformance suite just does not judge vols there, because two correct builds can return different vols that both reprice to within the tolerance.

**Worked example.** A 0.1-year call struck at 160 on a spot of 100 (`r = 3%`, `v = 20%`) is worth 8.03e-14 with vega 2.30e-11, eight orders below the threshold. A rounding of the price in the 14th digit moves the implied vol by a visible amount.

What a validator cares about: deep out-of-the-money quotes should be fitted in price (or with vega weights), not in vol.

## Greeks and vol Greeks

### Q5.7 In what units does `risk.vol.greeks` report vega, theta and rho?

*Level: foundation. Evidence: computed; spec. Source: [Vol Greeks](../../specifications/06-risk/vol-greeks.md)*

QuantForge reports every Greek per unit of option, with vol per 1.00 (not per vol point) and time per year.

The spec: "All per unit of option, vol per 1.00 (not per point), time per year." `theta` is `-dV/dT` with other inputs fixed. For Black-Scholes, `delta = Q phi N(phi d1)`, `gamma = Q n(d1)/(S v sqrt T)`, `vega = S Q n(d1) sqrt T`, `Q = exp(-qT)`.

**Worked example.** The Q5.1 call: delta 0.573496, gamma 0.0193576, vega 38.7152 per 1.00 of vol, so 0.387152 per vol point; theta -4.75369 per year (about -0.013 a calendar day); rho 48.5223 per 1.00 of rate.

The usual mistake is to read vega 38.7 as "38.7 per vol point" and overstate vega risk a hundredfold. Divide by 100 for a point, by 10,000 for a basis point of rate.

### Q5.8 Why does Black-76 report `rho = -T V`, and what does theta leave out?

*Level: practitioner. Evidence: computed; spec. Source: [Vol Greeks](../../specifications/06-risk/vol-greeks.md)*

In Black-76 the forward is an input, so moving the rate only moves the discount factor `D = exp(-rT)`; the option value scales with `D`, and the derivative of `exp(-rT)` is `-T exp(-rT)`.

The spec: for `BLACK_76` and `BACHELIER`, "`theta` holds `D` as a number, so has no `r` term; `rho` is `dV/dr` with `D = exp(-rT)` and `F` fixed". So `theta = -D F n(d1) v/(2 sqrt T)` and `rho = -T V`.

**Worked example.** `F = 102`, `K = 100`, `T = 1`, `D = 0.97`, `v = 25%`: price 10.7461, rho -10.7461 (exactly `-T V`), theta -4.83211.

The pitfall is comparing this rho with a Black-Scholes rho, which also moves the forward. The two answer different questions: one holds the forward, the other holds the spot.

### Q5.9 What are vanna and volga, and when are they close to zero?

*Level: practitioner. Evidence: computed; spec. Source: [Vol Greeks](../../specifications/06-risk/vol-greeks.md)*

Vanna is how delta changes when vol moves (equivalently, how vega changes with the underlying); volga is how vega changes with vol. They measure the risk a smile adds on top of flat-vol Black.

The spec: `vanna = d delta/d vol`, `volga = d vega/d vol`; for Black-76 `vanna = -D n(d1) d2/v` and `volga = vega d1 d2/v`.

**Worked example.** The Black-76 option of Q5.8 has vanna 0.0694148 and volga -1.44587. For the Q5.1 Black-Scholes call `d1 = 0.2` and `d2 = 0`, so vanna is zero to rounding: any option with `d2 = 0` has no vanna, and its volga vanishes too because volga carries the factor `d1 d2`.

Desk use: risk reversals carry vanna and strangles carry volga, which is why vanna-volga style smile pricing hedges with exactly those two structures.

### Q5.10 How does `risk.vol.bump_greeks` bump, and how close does it come to the analytic Greeks?

*Level: advanced. Evidence: computed; spec. Source: [Vol Greeks](../../specifications/06-risk/vol-greeks.md), [Stage C targets](../../specifications/05-volatility/stage-c-targets.md)*

Bump-and-revalue reprices with the input moved up and down and divides; it needs no formula for the Greek, so it is the independent check on the analytic one.

The spec fixes the bumps: `hu = 1e-4 U` on the spot or forward (`1e-4 max(|U|, 1)` for Bachelier), `hv = 1e-3 v` on vol, central differences for delta, gamma, vega, volga and a four-point cross difference for vanna.

**Worked example.** For the Q5.1 call, analytic delta 0.57349598 against bumped 0.57349597; analytic and bumped vega both 38.715175 to six decimals. Where the true value is zero (vanna and volga here), the bump returns rounding noise of order 1e-7 and 1e-6, which is the floor of a central difference at these step sizes.

The point for a validator: agreement of analytic and bump Greeks is a stage C acceptance target, and a near-zero Greek should be judged on absolute error, never relative.

### Q5.11 How does `risk.vol.surface_vega` bucket vega, and why does the bucket sum differ from the parallel vega?

*Level: practitioner. Evidence: computed; spec. Source: [Vol Greeks](../../specifications/06-risk/vol-greeks.md), [Smile and surface](../../specifications/05-volatility/smile-and-surface.md)*

Bucketed vega moves one surface node at a time and records the PV change, so the trader sees which expiries and strikes the book is exposed to.

The spec: `bucket_vega[j][i] = (pv(v[j][i] + 1e-4) - pv(v[j][i] - 1e-4))/2e-4`, one node at a time; `parallel_vega` moves all nodes together. `bucket_sum` agrees with `parallel_vega` only to first order, because the surface interpolates total variance `w = v^2 T`, which is not linear in `v`.

**Worked example.** Surface nodes at 0.5 and 1.0 years, log-moneyness -0.2, 0, 0.2, ATM vol 20% on both slices; one ATM call, `F = K = 100`, `D = 0.98`, expiry 0.75 years. PV 6.76323; vega 11.2439 on the 0.5-year ATM node and 22.4878 on the 1-year node, zero elsewhere; parallel 33.731695 against a bucket sum of 33.731694.

The weights follow total variance: the 0.75-year point takes a third of its `w` from the earlier slice and two thirds from the later one.

## Delta conventions and quoted smiles

### Q5.12 What strike does a 25-delta call have under forward and spot delta?

*Level: foundation. Evidence: computed; spec. Source: [Smile and surface](../../specifications/05-volatility/smile-and-surface.md)*

Smiles are often quoted by delta rather than strike. To use a quote you have to turn the delta back into a strike, and the answer depends on which delta was meant.

The spec: `Delta = phi s N(phi d1)`, with `s = 1` for `FORWARD` (and `scale` must be `null`) and `s = scale` for `SPOT` (on an equity `D(T)/C(T)`). Then `d1 = phi Ninv(phi delta/s)` and `strike = F exp(-d1 v sqrt T + v^2 T/2)`.

**Worked example.** `F = 100`, `v = 20%`, `T = 1`: the 25-delta call strike is 116.754 under forward delta and 116.570 under spot delta with scale `exp(-0.01)`.

The pitfall is not the size of this gap but its source: two systems that agree on "25 delta" can still disagree on the strike by the scale factor, so the convention is a required input, not a default.

### Q5.13 How does `vol.smile.rr_bf` turn ATM, risk reversal and butterfly quotes into two wing vols and strikes?

*Level: practitioner. Evidence: computed; spec. Source: [Smile and surface](../../specifications/05-volatility/smile-and-surface.md)*

A risk reversal is the call vol minus the put vol at one delta (the skew); a butterfly is how far the wings sit above ATM on average (the curvature).

The spec: `call_vol = atm + bf + rr/2`, `put_vol = atm + bf - rr/2`; `bf` is the smile strangle, with no broker-strangle iteration. `atm_strike` is `F` for `ATM_FORWARD` and `F exp(atm^2 T/2)` for `DELTA_NEUTRAL`; the wing strikes come from `vol.delta.to_strike` with `+delta` and `-delta`, each at its own vol.

**Worked example.** `F = 100`, `T = 1`, ATM 20% delta-neutral, `rr = -3%`, `bf = 0.5%`, 25 delta forward: ATM strike 102.020, call vol 0.19, put vol 0.22, call strike 115.743, put strike 88.3214.

A negative risk reversal (puts richer than calls) is the usual equity shape. Reading `rr` with the opposite sign flips the skew, and the FX goldens catch exactly that.

## SVI and SSVI

### Q5.14 What is raw SVI, and what does it give at the money and in the wing?

*Level: foundation. Evidence: computed; spec. Source: [Smile and surface](../../specifications/05-volatility/smile-and-surface.md)*

SVI is a five-parameter formula for total implied variance across log-moneyness at one expiry. It is linear in both far wings and smooth near the money, which matches how equity smiles look.

The spec: `w(k) = a + b (rho (k-m) + R)`, `R = sqrt((k-m)^2 + sigma^2)`, with `k = ln(K/F)` and `w = v^2 T`. The domain is refused with `E_DOMAIN` when `b < 0`, `|rho| >= 1`, `sigma <= 0`, or `a + b sigma sqrt(1-rho^2) <= 0` (the minimum of `w` must be positive).

**Worked example.** `a = 0.04`, `b = 0.4`, `rho = -0.4`, `m = 0`, `sigma = 0.1`, `T = 1`: at `k = 0`, `w = 0.08` and implied vol 0.282843; at `k = -0.5`, `w = 0.323961` and vol 0.569176.

Working in total variance rather than vol is what makes the arbitrage conditions in the next questions simple to state.

### Q5.15 What is Gatheral's function `g`, and what does a negative value mean?

*Level: practitioner. Evidence: computed; spec; literature. Source: [Smile and surface](../../specifications/05-volatility/smile-and-surface.md), [Arbitrage-free surfaces](../../specifications/05-volatility/arb-free-surfaces.md)*

The second derivative of the call price in strike is the risk-neutral density. Written in total variance, its sign is the sign of a function `g`, so `g < 0` means a negative density: a butterfly with a negative price.

The spec: `g = (1 - k w'/(2w))^2 - (w'^2/4)(1/w + 1/4) + w''/2`, with `w' = b (rho + (k-m)/R)` and `w'' = b sigma^2/R^3`. `g < 0` at any `k` is butterfly arbitrage; `vol.svi.evaluate` returns `g`, `min_g` and `butterfly_free`.

**Worked example.** The Q5.14 slice has `min_g = 0.0899844` on the points -0.5, 0, 0.5: arbitrage-free there. A steep slice (`a = 0.001`, `b = 1.5`, `rho = -0.9`, `m = 0`, `sigma = 0.05`) has `min_g = -3.40156` at `k = -0.2`.

`butterfly_free` only covers the points supplied: a coarse grid can miss a dip, so the check grid should be fine where the smile bends.

### Q5.16 Are the SSVI no-butterfly conditions in `vol.ssvi.evaluate` necessary, sufficient, or both?

*Level: practitioner. Evidence: spec; design; literature. Source: [Smile and surface](../../specifications/05-volatility/smile-and-surface.md), [R6 rulings](../../specifications/r6-rulings.md)*

SSVI is a whole surface in three parameters plus the ATM total variance per expiry. Gatheral and Jacquier give simple parameter inequalities that rule out butterfly arbitrage.

The spec: `butterfly_free` tests `theta phi (1+|rho|) < 4` and `theta phi^2 (1+|rho|) <= 4` at every theta. These are sufficient, not necessary (ruling R6-25): `true` proves the slice free of butterfly arbitrage, but `false` can be a false alarm. "Check the density (`vol.svi.evaluate` `g`) before acting on a `false`." `calendar_free` tests `rho^2 (1-gamma)/(1+theta) <= 1 + sqrt(1-rho^2)`.

**Worked example.** `rho = -0.7`, `eta = 1.5`, `gamma = 0.5`, thetas 0.04 and 0.1: both flags true; the first slice has `w = 0.160182` at `k = -0.5`.

The validator's reading: a `false` is a prompt to check `g` (map the slice with `vol.ssvi.to_svi`), not grounds to reject the surface.

### Q5.17 How does `vol.ssvi.to_svi` map an SSVI slice to raw SVI, and which sign error do the goldens catch?

*Level: advanced. Evidence: computed; spec; literature. Source: [Arbitrage-free surfaces](../../specifications/05-volatility/arb-free-surfaces.md)*

Every SSVI slice is a raw SVI slice in disguise, so the SVI tools (density, wing checks) apply to SSVI after a change of parameters.

The spec, with `phi = eta theta^-gamma (1+theta)^(gamma-1)`: `a = theta (1 - rho^2)/2`, `b = theta phi/2`, `rho = rho`, `m = -rho/phi`, `sigma = sqrt(1 - rho^2)/phi` ([GJ14] section 4). The goldens catch `m = +rho/phi`.

**Worked example.** `rho = -0.7`, `eta = 1.5`, `gamma = 0.5`, `theta = 0.04`: `a = 0.0102`, `b = 0.147087`, `m = 0.0951817`, `sigma = 0.0971048`. Both forms give `w = 0.0224521` at `k = 0.3`.

Because the identity is exact, a test that evaluates both forms at a handful of `k` is the quickest way to catch the sign of `m`.

### Q5.18 How does `vol.surface.query` interpolate between grid nodes and outside the grid?

*Level: practitioner. Evidence: computed; spec. Source: [Smile and surface](../../specifications/05-volatility/smile-and-surface.md)*

The grid surface stores vols at fixed log-moneyness for each expiry. Queries interpolate total variance, not vol, so the term structure stays sensible.

The spec: on each slice `w` is linear in `k`, with `k` clamped to the grid; between slices `w` is linear in `T`; before the first slice `w = w_1(k) T/T_1` and after the last `w = w_n(k) T/T_n`, so vol is flat in both directions.

**Worked example.** Slices at 0.5 and 1.0 years with vols (24%, 20%, 18%) and (23%, 20%, 19%) at `k = -0.2, 0, 0.2`. At `(0.75, 0)`: `w = 0.03`, vol 0.2. At `(0.75, 0.1)`: `w = 0.028075`, vol 0.193477. At `(2.0, 0)`, beyond the last slice: `w = 0.08`, vol 0.2.

The stage C limit is explicit: linear interpolation can create butterfly arbitrage between nodes, and the check covers nodes only. Stage E's SVI slice surface is the arbitrage-aware route.

### Q5.19 Why does QuantForge test calendar arbitrage on total variance rather than on implied vol?

*Level: foundation. Evidence: computed; spec. Source: [Smile and surface](../../specifications/05-volatility/smile-and-surface.md), [Arbitrage-free surfaces](../../specifications/05-volatility/arb-free-surfaces.md)*

A later option at the same forward moneyness must be worth at least as much as an earlier one, and that is the statement that total variance `w = v^2 T` does not fall with expiry. Vol itself may fall.

The spec: `vol.surface.check` flags `{expiry_index, k_index}` where `w[j][i] < w[j-1][i] - 1e-12`; the stage E check has the same rule without tolerance. "Calendar compared on implied vol instead of total variance" is listed as a wrong convention the goldens catch.

**Worked example.** A 0.5-year ATM vol of 20% and a 1-year ATM vol of 15%: vol falls, yet `w` rises from 0.02 to 0.0225, and `vol.surface.check` returns `arbitrage_free = true`.

A falling vol term structure is common after an event; a check on vol would reject a sound surface.

## Arbitrage-free surfaces, local and forward vol

### Q5.20 What wing checks does `vol.svi.surface_check` run, and why is a slope of exactly 2 flagged?

*Level: advanced. Evidence: computed; spec; literature. Source: [Arbitrage-free surfaces](../../specifications/05-volatility/arb-free-surfaces.md), [Stage E rulings](../../specifications/stage-e-rulings.md)*

Far from the money, total variance can grow at most linearly with slope 2 (Lee's moment formula). Raw SVI is linear in both wings, so the slopes can be read from the parameters without any grid.

The spec: left slope `sL = b(1-rho)`, right slope `sR = b(1+rho)`. A slope `>= 2` is a `LEE` violation; 2 itself is flagged because [GJ14] Lemma 2.2 also needs `d_+ -> -inf`, which fails at exactly 2 (ruling E-A15). Between slices, a later slice with a smaller wing slope (or equal slope and smaller constant) is a wing `CALENDAR` violation: it crosses below the earlier slice far out, wherever the grid ends (ruling E-A2). The goldens catch a misread bound of 4.

**Worked example.** `b = 1.2`, `rho = 0.7`: `sR = 2.04`, `sL = 0.36`. The check returns one violation, `{0, RIGHT, LEE}`, even on a one-point grid at `k = 0`.

These grid-free checks catch what no finite grid can: arbitrage that only appears beyond the last quoted strike.

### Q5.21 How does `vol.forward.vol` compute forward volatility, and what does a negative radicand mean?

*Level: foundation. Evidence: computed; spec; literature. Source: [Local and forward vol](../../specifications/05-volatility/local-and-forward-vol.md)*

Variances add over time, vols do not. The vol for the period between two expiries is whatever makes the variances add up.

The spec: `forward_vols[0] = vols[0]` and `forward_vols[i] = sqrt((vols[i]^2 T_i - vols[i-1]^2 T_{i-1}) / (T_i - T_{i-1}))` [Hull]. A negative radicand is calendar arbitrage, `E_ARBITRAGE`; zero is allowed and gives 0 (ruling E-A5).

**Worked example.** Expiries 0.5, 1, 2 years at vols 20%, 22%, 21%: forward vols 0.2, 0.238328, 0.199499. The small rise from 20% to 22% implies a 23.8% vol over the second half-year.

The goldens catch forward vol computed linearly in vol; that version understates the forward vol whenever the term structure rises.

### Q5.22 How does `vol.local.dupire` compute local vol from SVI slices?

*Level: practitioner. Evidence: computed; spec; literature. Source: [Local and forward vol](../../specifications/05-volatility/local-and-forward-vol.md)*

Local vol is the volatility, as a function of time and spot level, that reproduces every vanilla price on the surface. Dupire's formula reads it from the surface's slopes.

The spec, in Gatheral's total-variance form: `local_vol = sqrt(w_T / g)`, with `g` the butterfly function of Q5.15 evaluated with the surface's `w`, `w_k`, `w_kk`. Between slices `w` is linear in `T` (ruling E-A4), so `w_T` is the interval slope. `w_T <= 0` or `g <= 0` at any point is `E_ARBITRAGE`; no point is skipped. In forward log-moneyness, rates and dividends do not appear.

**Worked example.** Slices at 0.5 years (`a = 0.01`, `b = 0.1`, `rho = -0.5`, `m = 0`, `sigma = 0.1`) and 1 year (`a = 0.02`, `b = 0.12`, `rho = -0.4`, `m = 0`, `sigma = 0.15`). At `T = 0.75`, `k = 0`: implied vol 0.196638, local vol 0.158713. At `k = -0.2`: implied 0.260718, local 0.266050.

The goldens catch local variance as `w_T` alone; the smile terms in `g` are what make local vol differ from implied.

### Q5.23 Why does local vol jump at each slice expiry, and why was that not smoothed away?

*Level: advanced. Evidence: computed; spec; design. Source: [Local and forward vol](../../specifications/05-volatility/local-and-forward-vol.md), [Stage F rulings](../../specifications/stage-f-rulings.md)*

`w` is continuous in `T` but its slope `w_T` is piecewise constant, so local vol, which depends on `w_T`, steps at every slice.

The spec (stage F, ruling F-17): `w`, implied vol, `w_k` and `w_kk` are continuous; `w_T` jumps, so local vol jumps. At `T_1` the left value uses `w_1(k)/T_1` (flat-vol extrapolation) and the right value `(w_2 - w_1)/(T_2 - T_1)`; `g` is the same on both sides; a node uses the interval to its right. A C1 interpolation would remove the jump but change every stage E local-vol and SLV golden, so the route taken is "documented with a continuity test".

**Worked example.** The Q5.22 surface at `k = 0`: local vol 0.165036 just before 0.5 years and 0.156567 at 0.5 years, while implied vol is 0.2 on both sides.

For a desk this matters in SLV or local-vol Monte Carlo: paths that cross a slice date see a vol step, so forward-starting products near slice dates deserve a check.

### Q5.24 How does `vol.smile.dynamics` move the smile under sticky strike and sticky delta?

*Level: practitioner. Evidence: computed; spec; literature. Source: [Local and forward vol](../../specifications/05-volatility/local-and-forward-vol.md)*

When spot moves, either each strike keeps its vol (sticky strike), or the smile slides with the forward so each moneyness keeps its vol (sticky delta). The choice changes the hedge.

The spec: `STICKY_STRIKE` keeps `v1(K) = v0(K)`; `STICKY_DELTA` sets `v1(K) = sqrt(w(ln(K/F1))/T)`, fixed in forward moneyness (ruling E-A6). Deltas are smile-consistent: `delta = Delta_BS + vega dv/dS`, with `dv/dS = 0` for sticky strike and `-(w'(k)/(2 v0 T))/S` for sticky delta.

**Worked example.** The 1-year slice of Q5.22, spot 100 to 105, `r = 2%`, `q = 0`, calls at 90, 100, 110. Sticky strike keeps vols 0.222432, 0.197786, 0.191119; sticky delta moves them to 0.236518, 0.207616, 0.192370. Deltas: 0.750101, 0.579265, 0.382665 (sticky strike) against 0.839339, 0.642393, 0.376832 (sticky delta).

The goldens catch sticky delta on spot moneyness `K/S`, and the sticky-delta delta without the smile term.

### Q5.25 How is vol of vol measured in `vol.volofvol.measure`?

*Level: foundation. Evidence: computed; spec. Source: [Local and forward vol](../../specifications/05-volatility/local-and-forward-vol.md)*

Vol of vol is the volatility of an implied vol series: how much the vol itself moves.

The spec: changes `x_i = ln(v_i/v_{i-1})` (`LOG`) or `v_i - v_{i-1}` (`ABSOLUTE`); `mean_change` is the plain mean (not annualised), and `vol_of_vol = sqrt(periods_per_year) s`, with `s` the sample standard deviation, divisor `n - 1` (ruling E-A7).

**Worked example.** Daily vols 20%, 21%, 19.5%, 20.5%, 22%, 21.5% with 252 periods a year, `LOG`: vol of vol 0.967004 (about 97% a year), mean change 0.0144641.

The goldens catch divisor `n` and a missing annualisation. A 97% vol of vol is not unusual for short-dated equity vol, which is why SABR's `nu` and Heston's `xi` often calibrate to large values.

## SABR

### Q5.26 What do the four SABR parameters control, and what smile does the Hagan formula give?

*Level: foundation. Evidence: computed; spec; literature. Source: [SABR](../../specifications/05-volatility/sabr.md), [Tutorial 3](../getting-started/tutorial-3-options-vol.md)*

SABR lets the forward's volatility itself be random. `alpha` sets the level, `beta` the backbone (how vol moves with the forward), `rho` the skew, `nu` the curvature.

The spec: `dF = a C(F) dW`, `da = nu a dZ`, `dW dZ = rho dt`, `C(F) = (F+s)^beta`, `a(0) = alpha`. `vol.sabr.hagan` returns Hagan's lognormal expansion. Checks, `E_DOMAIN`: `alpha <= 0`, `beta` outside `[0, 1]`, `|rho| >= 1`, `nu < 0`, a non-positive shifted forward or strike.

**Worked example.** `F = 3%`, `T = 2`, `alpha = 0.04`, `beta = 0.5`, `rho = -0.3`, `nu = 0.4`: vols 0.295320, 0.234924, 0.211226 at strikes 2%, 3%, 4%.

The negative `rho` tilts the smile down to the right, as rates skews usually are.

### Q5.27 Why can Hagan SABR vols imply a negative density, and how does `vol.sabr.density` report it?

*Level: practitioner. Evidence: computed; spec. Source: [SABR](../../specifications/05-volatility/sabr.md)*

Hagan's formula is an expansion, accurate near the money and for short expiries. At low strikes and long expiries it can give call prices that are not convex in strike, which is a negative density.

The spec, in bold: "The Hagan expansion is not arbitrage-free, and neither is its shifted form." `vol.sabr.density` takes the second difference of undiscounted Black calls at the Hagan vols, `density_i = (c(K_i+h) - 2 c(K_i) + c(K_i-h))/h^2`, sets `negative_density` when `min_density < -1e-9`, and with `REJECT` raises `E_ARBITRAGE`. Density is checked only on the given strikes.

**Worked example.** `F = 1%`, `T = 10`, `alpha = 0.03`, `beta = 0.5`, `rho = -0.3`, `nu = 0.6`, `h = 0.02%`, strikes 0.05% to 1%: `min_density = -297.403` at 0.05%, so `negative_density` is true.

A shift moves the point where the density turns negative; it does not remove it. Low-strike payoffs (floors, CMS) are where this bites.

### Q5.28 How does `vol.sabr.arbfree` remove the negative density, and what does it conserve?

*Level: advanced. Evidence: computed; spec; literature. Source: [SABR](../../specifications/05-volatility/sabr.md), [Stage C rulings](../../specifications/stage-c-rulings.md)*

Instead of an expansion for the vol, it solves a one-dimensional forward equation for the density of the forward, with an absorbing boundary at zero. A density built that way cannot go negative.

The spec pins the recipe (Hagan, Kumar, Lesniewski and Woodward 2014) so every language runs the same grid: cell-centred grid with `cells_below` cells under the forward, fully implicit steps (one tridiagonal solve each), probability absorbed at zero tracked as `P_L` and at the top as `P_R`. "The scheme conserves mass and mean to rounding." Backward Euler is first order in time on purpose, to keep `Q >= 0`. `beta = 1` is not offered.

**Worked example.** The Q5.27 parameters on 400 cells (100 below the forward) and 400 steps: mass 1.000000, mean 0.010000 (the forward), absorbed mass 0.315006, minimum density 0.00199429 (positive). Implied vols 0.434595, 0.330233, 0.300876 at 0.5%, 1%, 2%.

A third of the probability absorbed at zero is the model's honest answer for a 1% forward over ten years; the expansion has no way to express it.

### Q5.29 Why is `beta` fixed in `vol.sabr.calibrate`?

*Level: practitioner. Evidence: computed; spec. Source: [SABR](../../specifications/05-volatility/sabr.md)*

`beta` and `rho` both tilt the smile, so a single smile cannot tell them apart. Fitting both lets the optimiser wander along a ridge of near-equal fits.

The spec: `vol.sabr.calibrate` minimises `sum weight (vol_hagan - vol)^2` over `alpha`, `rho`, `nu` with `beta` given, "Any solver, several starts. `beta` and `rho` are nearly exchangeable, which is why `beta` is fixed." Fewer than 3 strikes or mismatched lengths: `E_INPUT`.

**Worked example.** Vols generated from the Q5.26 parameters at five strikes 2% to 4%, refitted with `beta = 0.5`: `alpha = 0.040000`, `rho = -0.300000`, `nu = 0.400000`, RMSE about 4e-17.

On a desk `beta` is chosen from the backbone (how ATM vol moved historically with the forward) or set by convention, then held fixed so that `rho` and `nu` are stable day to day.

## Heston, Bates, Merton and SLV

### Q5.30 How does QuantForge price a Heston option, and what is the small vol-of-variance limit?

*Level: practitioner. Evidence: computed; spec; literature. Source: [Heston family](../../specifications/05-volatility/heston-family.md)*

Heston lets variance mean-revert randomly. Prices come from the characteristic function of log-spot through a single Fourier integral (Lewis's form).

The spec: `{v0, kappa, theta, xi, rho}` with `dv = kappa(theta - v)dt + xi sqrt(v) dW2`; the "little Heston trap" form of the characteristic function; Gauss-Legendre with 1024 nodes on `[0, U]`, `U = 200/sqrt(min(T, 1))`. The Feller condition is not required. As `xi -> 0` the price tends to Black-Scholes at `vbar = theta + (v0 - theta)(1 - e^{-kappa T})/(kappa T)`, not at `v0` or `theta`.

**Worked example.** `S = 100`, `T = 1`, `r = 3%`, `q = 0`, `v0 = theta = 0.04`, `kappa = 1.5`, `xi = 0.5`, `rho = -0.7`: calls 15.7672, 8.80266, 3.74911 at 90, 100, 110. Small-`xi` check (`v0 = 0.09`, `theta = 0.04`, `kappa = 2`, `xi = 1e-3`, `r = q = 0`): Heston 9.87708, `vbar = 0.0616166`, Black-Scholes at `sqrt(vbar)` 9.87746, at `sqrt(v0)` 11.9235.

The goldens catch the limit taken at `sqrt(v0)` or `sqrt(theta)`.

### Q5.31 How do Bates and Merton add jumps, and why does the compensator matter?

*Level: advanced. Evidence: computed; spec; literature. Source: [Heston family](../../specifications/05-volatility/heston-family.md)*

Both add lognormal jumps to the diffusion. Without a drift correction the jumps would change the forward, so each model subtracts the expected jump growth.

The spec: jumps `{intensity, mean_log_jump, log_jump_vol}`, `ln(1+J) ~ N(mu, delta^2)`, `kbar = e^{mu + delta^2/2} - 1`. Bates multiplies the Heston characteristic function by `exp(lambda T (e^{i u mu - delta^2 u^2/2} - 1 - i u kbar))`. Merton is a Poisson-weighted series of Black-Scholes prices with `lambda' = lambda(1 + kbar)`, `v_n^2 = v^2 + n delta^2/T`, `r_n = r - lambda kbar + n ln(1 + kbar)/T`, stopped when the weights sum to `1 - 1e-16` or at 200 terms.

**Worked example.** Jumps `lambda = 0.5`, `mu = -0.1`, `delta = 0.15`. Bates on the Q5.30 Heston: 16.7893, 10.2700, 5.30742 at 90, 100, 110. Merton with `v = 20%`, `r = 3%`: 16.5302, 10.6269, 6.39252; plain Black-Scholes at 90 is 15.4292.

The goldens catch an omitted compensator and Merton weights at `lambda` mixed with terms at `r_n`.

### Q5.32 What does `vol.slv.leverage` compute, and how much should you trust its output?

*Level: advanced. Evidence: spec; design; literature. Source: [Heston family](../../specifications/05-volatility/heston-family.md), [Stage E rulings](../../specifications/stage-e-rulings.md)*

Stochastic-local vol multiplies Heston's random vol by a leverage function `L(t, x)` chosen so the model still reprices every vanilla on the local-vol surface.

The spec: `L(t,x)^2 = sigma_LV(t,x)^2 / E[v | x_t = x]` (Gyongy's mimicking result), with `sigma_LV` from `vol.local.dupire`. `E[v | x]` comes from the joint density of `(x, v)` stepped forward on a fixed grid: explicit mixed term, implicit `x` and `v` sweeps (no-flux in `v`), a floor at zero, and an `eps` term that keeps the far tail finite. Outputs are the grid, the leverage at `T` and the mass.

The spec is plain about its status: "This is a reference scheme, not a converged answer: goldens test that four builds run the same recipe (class `numerical_scheme`)." Accuracy is checked only as stated in the stage E targets (ruling E-A14). `mass` below 1 shows probability lost through the `x` ends; above 1, what the floor added.

A validator should therefore treat the leverage as a reproducible reference, run a grid refinement before using it for prices, and note that the local-vol jumps of Q5.23 feed straight into `L`.

## FX smile conventions

### Q5.33 How does `fx.option.price` quote a Garman-Kohlhagen option, and in which currency is each output?

*Level: foundation. Evidence: computed; spec; literature. Source: [FX smile](../../specifications/05-volatility/fx-smile.md), [Tutorial 9](../getting-started/tutorial-9-fx.md)*

An FX option is Black-Scholes with the foreign interest rate playing the dividend yield. The pair quote fixes which currency is which.

The spec: `spot` is domestic per unit of foreign (EURUSD 1.0850 is USD per EUR, USD domestic). `F = S e^{(rd-rf)T}`; per unit foreign `p = phi Dd (F N(phi d1) - K N(phi d2))` in domestic. Outputs: `price = notional p` (domestic), `premium_pct_foreign = p/S`, spot `delta = notional phi Df N(phi d1)` in foreign units, `vega` per unit vol in domestic.

**Worked example.** EURUSD spot 1.0850, strike 1.10, `T = 0.5`, `rd = 4.5%`, `rf = 3%`, vol 8%, EUR 1m call: price USD 21,000.02, premium 0.0193549 of foreign notional, forward 1.093168, delta EUR 460,424, vega USD 300,508 per 1.00 of vol.

The goldens catch swapped rates and spot delta discounted at `rd` instead of `rf`.

### Q5.34 What are the four FX delta types, and when is premium adjustment used?

*Level: practitioner. Evidence: computed; spec; literature. Source: [FX smile](../../specifications/05-volatility/fx-smile.md)*

A delta hedge is in foreign currency. If the premium is also paid in foreign currency, part of the hedge is already done by the premium, so the quoted delta is reduced: that is premium adjustment.

The spec [RW12 1.3]: `SPOT = phi Df N(phi d1)`, `FORWARD = phi N(phi d1)`, `SPOT_PA = phi Df (K/F) N(phi d2)`, `FORWARD_PA = phi (K/F) N(phi d2)`. Which pairs use which is a market convention the caller chooses; the library has no pair table (ruling E-A9).

**Worked example.** The Q5.33 option: SPOT 0.460424, FORWARD 0.467383, SPOT_PA 0.441069, FORWARD_PA 0.447735.

Two points of delta is a large strike error at 25 delta, so getting the type wrong shows up directly in the wing strikes.

### Q5.35 Why can a premium-adjusted call delta have two strikes, and which ATM strike goes with each delta type?

*Level: advanced. Evidence: computed; spec; literature. Source: [FX smile](../../specifications/05-volatility/fx-smile.md), [Stage E rulings](../../specifications/stage-e-rulings.md)*

A premium-adjusted call delta rises from zero at very high strikes, peaks, then falls again at low strikes (the deep in-the-money premium eats the hedge). Any delta below the peak is hit twice.

The spec: a PA call delta must be below the maximum `delta(K*)`, `K*` solving `v sqrt T N(d2) = n(d2)`; the result is the strike above `K*` (ruling E-A10, [RW12 1.5]). For ATM, `fx.atm.strike` gives `S`, `F`, or delta-neutral straddle `F e^{+v^2 T/2}` for non-PA and `F e^{-v^2 T/2}` for PA deltas.

**Worked example.** Q5.33 market: the 25-delta call strike is 1.135001 under SPOT_PA and 1.136741 under SPOT. ATM strikes: forward 1.093168; DNS 1.094919 (SPOT delta) and 1.091420 (SPOT_PA).

The goldens catch the low-strike branch and a PA DNS with `+v^2 T/2`.

### Q5.36 How does `fx.smile.from_quotes` build a smile from ATM, risk reversal and butterfly quotes, and what does it leave out?

*Level: practitioner. Evidence: computed; spec; design. Source: [FX smile](../../specifications/05-volatility/fx-smile.md), [Stage E rulings](../../specifications/stage-e-rulings.md)*

FX desks quote three numbers per tenor and delta: ATM, the risk reversal and the butterfly. These fix three points of the smile.

The spec: `call_vol = atm_vol + bf + rr/2`, `put_vol = atm_vol + bf - rr/2` [Cla11 ch. 3]; strikes from `fx.atm.strike` and `fx.delta.to_strike`. `bf` is the smile strangle; the broker (market) strangle needs a fitted smile and is out of scope (ruling E-A11). `delta` must be in `(0, 0.5)`.

**Worked example.** Q5.33 market, ATM 8% DNS, `rr = -1%`, `bf = 0.25%`, 25 delta SPOT: call vol 0.0775, put vol 0.0875, ATM strike 1.094919, call strike 1.135298, put strike 1.051266.

What a validator checks: whether the quoted butterfly is the smile strangle or the broker strangle. Feeding a broker strangle in as `bf` mis-states the wings, and the library cannot detect it.

## Caps, swaptions and the rates vol layer

### Q5.37 How is a caplet priced in `rates.cap.price`, and what is stylised about the conventions?

*Level: foundation. Evidence: computed; spec; design. Source: [Caps and swaptions](../../specifications/05-volatility/caps-and-swaptions.md), [R1 rulings](../../specifications/r1-rulings.md)*

A caplet is a call on one forward rate, paid at the end of its period. Black-76 on the forward, scaled by notional, accrual and the payment discount factor, prices it.

The spec: `alpha = ACT_360(a_i, e_i)`, `F = (P(a_i)/P(e_i) - 1)/alpha` on the projection curve, fixing at `a_i` with no lag, paid at `e_i`: `N alpha D(e_i) option(F, K, vol_i, t(a_i))`, with `t = (fixing - as_of)/365`. Conventions are stylised (ruling R1-5): a synthetic index, no fixing lag, an annual 30/360 swaption fixed leg. "They test the option machinery only."

**Worked example.** Computed with `black.price` directly (not the curve-based operation): `F = 3.5%`, `K = 3.7%`, `t = 1`, vol 24%, accrual 0.25, `D = 0.955`, notional 10m: caplet 6,040.14.

The note on R1-5 matters: QuantForge's cap prices are not market prices for any real index, and a reader should not compare them with a broker screen.

### Q5.38 What does `rates.cap.strip` assume about caplet vols, and what do the golden caplet vols show?

*Level: practitioner. Evidence: golden; spec. Source: [Rates vol cube](../../specifications/05-volatility/rates-vol-cube.md), [Stage E rulings B](../../specifications/stage-e-rulings-b.md)*

Caps are quoted with one flat vol each, but a long cap contains the short cap's caplets. Stripping finds caplet vols that reprice every cap.

The spec: caplet vols are piecewise constant, one value `v_k` on the caplets of cap `k` not in cap `k-1` (ruling E-B9). Each `v_k` solves a monotone one-dimensional equation, searched in `[1e-10, 5]` (Black) or `[1e-10, 0.5]` (Bachelier). Left side already above the target at the lower bound: `E_ARBITRAGE` (E-B10); still below at the upper bound: `E_DOMAIN`.

**Worked example.** Golden `ratesvol_e-0049` (Black, strike 3.70%, flat vols 24.0, 23.5, 22.8, 22.2, 21.5%): caplet vols 24.000, 23.143, 21.956, 21.096, 19.706% on the five yearly segments. These values are quoted from the spec's worked example, not recomputed here.

The first segment equals the first flat vol; later segments fall faster than the flat vols, as they must when flat vols fall. Using the flat vol as the caplet vol is a wrong convention the goldens catch.

### Q5.39 Why does the SABR swaption cube interpolate parameters rather than vols?

*Level: practitioner. Evidence: golden; spec. Source: [Rates vol cube](../../specifications/05-volatility/rates-vol-cube.md)*

A swaption vol depends on expiry, swap tenor and strike. The cube stores four SABR parameters at each (expiry, tenor) node and reads the smile at the strike after interpolating them.

The spec: each parameter is bilinear in `(t, L)`, `t` the ACT/365F time to the node expiry date and `L` the tenor in years (ruling E-B8); outside the grid `E_INPUT`. The vol is Hagan's at the interpolated parameters; `price = N A Black(F, K, vol, t)`. Interpolating parameters keeps every interpolated smile a SABR smile, so its shape stays consistent; interpolating vols strike by strike does not.

**Worked example.** Golden `ratesvol_e-0001`, payer 12M x 5Y at 3.70%: the parameters are the node's (`alpha 0.048, beta 0.5, rho -0.27, nu 0.44`), forward 3.5718%, annuity 4.35104, Hagan vol 25.265%. In `ratesvol_e-0006` (18M x 5Y), `rho = -0.27995`, weighted by time, not by months. Both are quoted from the spec.

The goldens catch interpolated vols and an expiry axis in months/12.

### Q5.40 How does `rates.bondfut.implied_vol` turn a price vol into a yield vol?

*Level: foundation. Evidence: computed; golden; spec. Source: [Rates vol cube](../../specifications/05-volatility/rates-vol-cube.md)*

Bond futures options are quoted in price vol (Black-76 on the futures price); traders think in yield vol. A relative price move is about modified duration times yield times the relative yield move.

The spec: `price_vol` solves `Black(...) D = premium`, then `yield_vol = price_vol / (Dm y)` (ruling E-B11), with `Dm` the cheapest-to-deliver's modified duration and `y` its yield. `ctd_yield <= 0` or `ctd_modified_duration <= 0`: `E_DOMAIN`.

**Worked example.** Golden `ratesvol_e-0064`: price vol 5.5%, CTD yield 4.25%, modified duration 6.4: `yield_vol = 0.055/(6.4 x 0.0425) = 0.202206`, or 20.22%.

This is a first-order link only. The goldens catch the yield vol computed without the yield factor, which would read as 0.86%.

### Q5.41 Which European rates options does QuantForge price, and which vol inputs and models does each take?

*Level: practitioner. Evidence: spec. Source: [Caps and swaptions](../../specifications/05-volatility/caps-and-swaptions.md), [Rates vol cube](../../specifications/05-volatility/rates-vol-cube.md), [LMM](../../specifications/04-pricing/lmm.md)*

The rates vol layer has four routes, from quoted vols to model-implied ones.

From the specs: `rates.cap.price` and `rates.swaption.price` take a flat or per-caplet quoted vol under `BLACK_76` or `BACHELIER` (stage D, D7); `rates.swaption.price_cube` reads a SABR cube; `rates.cap.strip` produces caplet vols from flat cap vols; `infl.cap.yoy_price` and `infl.cap.zc_price` price inflation caps on given YoY forwards or a forward index ratio, with ZC strike ratio `(1+K)^T` (ruling E-B13). Model-based prices (Hull-White, LMM) are in Question bank 6.

The swaption is European and physically settled, exercising at the swap start (ruling D28 in [Stage D rulings](../../specifications/stage-d-rulings.md)), which is why QuantLib's `SabrSwaptionVolatilityCube` (forward starting two business days after expiry) is not used as the oracle.

What is not there: none of these specs defines a cash-settled (annuity-mapped) swaption, a smile-aware caplet strip, or CMS convexity. A desk needing those must add them.

### Q5.42 How does `infl.cap.yoy_price` differ from `infl.cap.zc_price`, and why does a 0% YoY floor need Bachelier?

*Level: advanced. Evidence: spec; design. Source: [Rates vol cube](../../specifications/05-volatility/rates-vol-cube.md), [Stage E rulings B](../../specifications/stage-e-rulings-b.md)*

A year-on-year caplet is an option on one year's inflation rate; a zero-coupon cap pays once, on cumulative inflation, so it is an option on the forward index ratio.

The spec: YoY caplet `= N accrual option(yoy_forward, K, vol, expiry_years) DF`, time to the fixing, not payment (ruling E-B12). ZC: `strike_ratio = (1+K)^T` (compounded, E-B13), `price = N D option(F_I, strike_ratio, vol, T)`. `BLACK_76` refuses a strike `<= 0` (YoY), so a 0% YoY floor needs `BACHELIER` (ruling E-B32); a ZC strike of 0% gives a ratio of 1, which Black accepts. Under Bachelier, `vol` is a normal vol of the quantity optioned: the YoY rate, or the index ratio.

The goldens catch YoY time to payment and the ZC strike `1 + KT`. The YoY forwards are inputs; building them from a CPI curve (with the ZC-to-YoY convexity) belongs to the inflation curve spec.
