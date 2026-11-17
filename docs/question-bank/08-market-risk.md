# Question bank 8: Market risk: sensitivities, VaR, ES and backtests

This set covers what QuantForge implements for market risk: bump-and-rebuild sensitivities, par and zero-rate risk, key-rate buckets, the curve Jacobian, P&L explain, book sensitivities by AAD and the implicit function theorem, VaR and ES by four methods, VaR and ES backtests, the FRTB standardised approach (GIRR, FX, equity, vega, curvature and the scenario total), the model reserve and the portfolio risk tools. It is for a newcomer who has worked through [Tutorial 5](../getting-started/tutorial-5-risk.md), and for a practitioner or validator who needs to know which sign, unit, bump and estimator QuantForge fixes. Questions are tagged foundation, practitioner or advanced. Every worked-example number was produced by `quantforge_core` and is rechecked by `verify/v08_market_risk.py`. All data is synthetic.

## Sensitivities

### Q8.1 What sign and unit does QuantForge use for DV01, and what is the DV01 of a receiver swap?

*Level: foundation. Evidence: computed; golden (`risk_r2-0001`); spec; design. Source: [Par and key-rate spec](../../specifications/06-risk/par-and-key-rate.md), [R2 rulings](../../specifications/r2-rulings.md)*

DV01 is how much the position's value changes when rates go up by one basis point, in the position's currency, with the sign of that change.

The spec states that every number is money per basis point and risk is `dV/d(bp)` for rates **up** 1 bp; a receiver of fixed loses when rates rise, so its DV01 is negative, a payer's positive, a long bond's negative (ruling R2-A1). All risk is bump and revalue (ADR-0010).

**Worked example.** A 2-year SOFR OIS receiving 3.45% on 25 million (golden `risk_r2-0001`), with all thirteen par quotes bumped together: par_dv01 = -4,806.94 per bp. Almost all of it sits in the 2Y bucket -4,808.13.

The pitfall is importing risk from a system that quotes DV01 as a positive "loss per bp": hedge ratios come out with the wrong sign.

### Q8.2 What is the difference between the `CENTRAL` and `FORWARD` bump schemes, and why is the result divided by `bump_bp`?

*Level: foundation. Evidence: computed; spec. Source: [Par and key-rate spec](../../specifications/06-risk/par-and-key-rate.md)*

A forward difference reprices once with the rate up; a central difference reprices with the rate up and down and takes half the difference, which cancels the second-order (convexity) term.

The spec: `CENTRAL: risk = (V(+h) - V(-h)) / (2 bump_bp)`, `FORWARD: risk = (V(+h) - V(0)) / bump_bp`, with `0 < bump_bp <= 100` (else `E_DOMAIN`) and default 1. Dividing by `bump_bp` puts every result in money per 1 bp whatever the bump size.

**Worked example.** On the swap of Q8.1, FORWARD gives -4,806.2312 per bp and CENTRAL gives -4,806.9447; a 10 bp central bump gives -4,806.9540, still per 1 bp. The forward-central gap is the convexity term, the central result moves only in the fifth significant figure with a ten times larger bump.

A validator asks which scheme a reported DV01 uses before comparing two systems; for long-dated or optional products the forward gap is larger.

### Q8.3 What are duration and convexity in `risk.cashflows`, and how do they predict a price change?

*Level: foundation. Evidence: computed; spec. Source: [Rates sensitivities spec](../../specifications/06-risk/rates-sensitivities.md)*

Duration is the value-weighted average time of the cash flows; it tells you the percentage price change per unit change in yield. Convexity is the next term.

The spec, at a continuously compounded yield: `pv = sum c exp(-y t)`, `duration = sum t c exp(-y t) / pv`, `convexity = sum t^2 c exp(-y t) / pv`. Under continuous compounding Macaulay and modified duration coincide. An empty list is `E_INPUT`, `t < 0` or `pv = 0` `E_DOMAIN`.

**Worked example.** Annual cash flows 5, 5 and 105 at 1, 2 and 3 years, yield 4%: QuantForge gives pv 102.546175, duration 2.861297 years and convexity 8.400178. A 1 bp rise changes the price by `-D x pv x 0.0001`, about -0.029342 per bp per 102.55 of value.

The pitfall is mixing compounding bases: an annually compounded yield needs the modified-duration correction that the continuous form does not.

### Q8.4 How does `risk.var.historical` pick the VaR from 250 days of P&L?

*Level: foundation. Evidence: computed; golden (`risk_f4-0003`); spec; literature. Source: [VaR, ES and backtests spec](../../specifications/06-risk/var-es-and-backtests.md), [Tutorial 5](../getting-started/tutorial-5-risk.md)*

Line up the past days' P&L as if each could happen tomorrow; the 99% VaR is the loss exceeded on only about 1% of them.

The spec (ruling F-31): losses `L = -pnl` sorted ascending, `k = ceil(n c)` with `n c` one binary64 multiply, `var = L_(k)`, the inverted empirical distribution (Hyndman and Fan type 1). VaR is reported as a positive number for a loss; `confidence` must be in `[0.5, 1)`, else `E_DOMAIN`.

**Worked example.** The first 250 days of golden `risk_f4-0003` at 99%: `k = ceil(247.5) = 248`, the third-largest loss, VaR 4,715,737.90. The two larger losses are the largest 5,542,122.75 and the second 4,959,560.16.

Interpolating between order statistics (numpy's default `linear` method) gives a different number on the same data; the outside check uses `method="inverted_cdf"` for that reason.

### Q8.5 What are parametric VaR and ES for a normal P&L with zero mean and a standard deviation of 1 million?

*Level: foundation. Evidence: computed; golden (`risk_f4-0026`); spec. Source: [VaR, ES and backtests spec](../../specifications/06-risk/var-es-and-backtests.md)*

If the P&L is normal, VaR is a multiple of its standard deviation, and ES is the average loss beyond VaR, which for a normal tail is also a fixed multiple.

The spec: with `z = Phi^{-1}(c)`, `var = -mu + sigma z`, `es = -mu + sigma phi(z)/(1 - c)`; `sigma > 0`, else `E_DOMAIN`.

**Worked example.** `mu = 0`, `sigma = 1,000,000`, `c = 0.99`: QuantForge gives var = 2,326,347.87 and es = 2,665,214.22, that is `z = 2.326348` and `phi(z)/0.01 = 2.665214`.

Real P&L has fatter tails than a normal, so a parametric ES usually understates the historical one; this method is a benchmark and a limit case for the Monte Carlo VaR (Q8.19), not a recommended model.

### Q8.6 What does Kupiec's test say about zero exceptions in 250 days at 99%?

*Level: foundation. Evidence: computed; golden (`risk_f4-0042`); spec; literature. Source: [VaR, ES and backtests spec](../../specifications/06-risk/var-es-and-backtests.md), [Tutorial 5](../getting-started/tutorial-5-risk.md)*

Kupiec asks whether the observed rate of VaR breaks is consistent with the promised rate. Too few breaks is evidence too: the model may be too conservative.

The spec: with `p = 1 - c` and `p_hat = x/n`, `LR_uc = -2[(n - x) ln(1 - p) + x ln p] + 2[(n - x) ln(1 - p_hat) + x ln p_hat]` (`0 ln 0 = 0`), `p_value = P(chi^2_1 > LR_uc)`; an LR below 1e-12 is exactly 0 with p-value 1 (ruling F-32).

**Worked example.** `n = 250`, `x = 0`: QuantForge gives LR_uc = 5.025168, p-value 0.024982, a rejection at 5%. On Tutorial 5's out-of-sample year, 4 exceptions give LR_uc 0.769138 and p-value 0.380484: no evidence against the model.

The point a supervisor and a validator share: zero breaks is not a clean bill of health. The Basel traffic light (Q8.7) only penalises too many breaks, Kupiec flags both sides.

### Q8.7 How does QuantForge assign the Basel traffic-light zone and plus factor?

*Level: foundation. Evidence: computed; spec; literature. Source: [VaR, ES and backtests spec](../../specifications/06-risk/var-es-and-backtests.md), [R6 rulings](../../specifications/r6-rulings.md)*

Count the exceptions, then ask how likely that many or fewer would be if the model were right. Green means plausible, red means the model is almost certainly understating risk.

The spec: `cumulative_probability = P(X <= x)`, `X ~ Binomial(n, 1 - c)`; `GREEN` below 0.95, `YELLOW` below 0.9999, else `RED`. At `n = 250`, `c = 0.99` the 1996 Basel Table 2 plus factors are returned (0 for 0 to 4; 0.40 to 0.85 for 5 to 9; 1.00 from 10), on the multiplier base 3 (R6-28.1). The FRTB backtesting table is a different test and not implemented.

**Worked example.** 4 exceptions: GREEN, P(X <= 4) = 0.892188, plus factor 0.00. 5 exceptions: YELLOW, P(X <= 5) = 0.958817, plus factor 0.40. 10 exceptions: RED, P(X <= 10) = 0.999946, plus factor 1.00. For any other window, say 500 days, the zone is still given but the plus_factor None (JSON `null`).

The pitfall is applying the 250-day plus factors to a different window; QuantForge refuses by returning `null` rather than guessing.

### Q8.8 What does the Acerbi-Szekely Z2 statistic measure that a VaR backtest does not?

*Level: foundation. Evidence: computed; golden (`esbt_j-0001`); spec; literature. Source: [ES backtest spec](../../specifications/06-risk/es-backtest.md), [Stage J wave 2 rulings](../../specifications/stage-j-rulings-w2.md)*

A VaR backtest counts breaks but ignores their size. ES claims to measure the average size of tail losses, so its test compares the size of the breaks with the ES forecast.

The spec (J-W2-10): `I_t = 1` when `L_t > VaR_t` (strict), `Z2 = 1 - sum_t L_t I_t / (T alpha ES_t)`. About 0 when the model is right, clearly negative when ES was too small. Lengths must match and `es > 0`, else `E_INPUT` or `E_DOMAIN`.

**Worked example.** Losses `(1, 3, 0.5, 4)`, VaR 2, ES 2.5, `alpha = 0.25`, so `T alpha = 1`. Breaks at 3 and 4: `Z2 = 1 - (3/2.5 + 4/2.5)`, and QuantForge returns z2 = -1.800000.

QuantForge reports the statistic only: no p-value or zone, because its null distribution depends on the tail model. The paper's critical values are recalled in the spec, not used.

### Q8.9 How does `risk.concentration.measures` measure concentration?

*Level: foundation. Evidence: computed; spec; literature. Source: [Portfolio risk tools spec](../../specifications/06-risk/portfolio-risk-tools.md)*

Concentration asks whether exposure sits in a few names. The Herfindahl-Hirschman index sums squared shares; its inverse is the number of equal names that would give the same concentration.

The spec: `w_i = |x_i| / sum |x|`, `hhi = sum w_i^2`, `effective_number = 1/hhi`, `top_n_share` the sum of the `top_n` largest weights. Exposures must not all be zero (`E_DOMAIN`), `top_n` between 1 and the count (`E_INPUT`).

**Worked example.** Exposures 50, -30 and 20 (absolute values are used, so the short counts as exposure), `top_n = 1`: QuantForge gives hhi = 0.380000, effective_number = 2.631579, top_n_share = 0.500000.

Signs are dropped on purpose: a long and a short in different names are two concentrations, not a hedge.

### Q8.10 How does `risk.limits.check` classify a measure against its soft and hard limits?

*Level: foundation. Evidence: computed; spec. Source: [Portfolio risk tools spec](../../specifications/06-risk/portfolio-risk-tools.md)*

Each risk measure has a warning (soft) level and a breach (hard) level, compared on absolute value.

The spec: `utilisation = |value|/hard`; `BREACH` if `|value| > hard`, `WARN` if `|value| >= soft`, else `OK`; `overall` is the worst status. `0 <= soft <= hard`, else `E_DOMAIN`; every measure needs a limit, else `E_INPUT`.

**Worked example.** VaR 4.2 million against soft 4 and hard 5 million, DV01 -95,000 against 80,000 and 90,000, vega 30,000 against 50,000 and 60,000. QuantForge returns DV01 BREACH at utilisation 1.0556, VAR WARN at utilisation 0.8400, VEGA OK at utilisation 0.5000, and overall BREACH.

The absolute value matters: a short DV01 of -95,000 breaches a 90,000 limit just as a long one would.

### Q8.11 What does the model-reserve dispersion report compute?

*Level: foundation. Evidence: computed; golden (`reserve_g-0001`); spec; literature. Source: [Model reserve spec](../../specifications/06-risk/model-reserve.md), [Tutorial 15](../getting-started/tutorial-15-advanced-risk.md)*

Models that fit the same vanilla smile can still disagree on an exotic. A desk books one model and holds a reserve against the chance that another reasonable model is right.

The spec (ruling G-36): `range = max p_m - min p_m` (Cont 2006), `reserve = max_m |p_m - p_ref|` from the booked price, `worst_model` the model that attains it, `relative_reserve = reserve/|p_ref|` (`null` when `p_ref = 0`).

**Worked example.** A down-and-out call: Heston 4.1832, local vol 4.6021, SLV 4.3907, booked on SLV. QuantForge gives range 0.4189, reserve 0.2114 (local vol is furthest) and relative_reserve 4.8147%.

The reserve is measured from the booked model, not from the mean: booking the middle model halves it compared with booking an extreme one. The registered multi-product report is not yet run.

### Q8.12 What is jump-to-default in `risk.credit.jtd`, and what is it for a bond bought at 98.5?

*Level: foundation. Evidence: computed; golden (`risk_f3-0046`); spec. Source: [Book sensitivities spec](../../specifications/06-risk/book-sensitivities.md)*

Jump-to-default is the instant change in value if the issuer defaults now: the position drops from its market value to what is recovered.

The spec: `jtd = value_after_default - market_value`, with `value_after_default` equal to `recovery x notional` for a bond holder, `(1 - recovery) x notional` for a CDS protection buyer and minus that for a seller. Accrued premium is left out (the CDS market value is taken clean).

**Worked example.** A bond, notional 1,000,000, recovery 40%, market value 985,000: jtd = -585,000.00, that is `400,000 - 985,000`.

The FRTB default risk charge (MAR22), which nets and weights these, is not implemented; this is the raw input to it.

## Curve risk and P&L

### Q8.13 Why does the swap's zero-rate DV01 differ from its par DV01?

*Level: practitioner. Evidence: computed; golden (`risk_r2-0001`, `-0002`, `-0031`); spec. Source: [Par and key-rate spec](../../specifications/06-risk/par-and-key-rate.md), [Tutorial 8](../getting-started/tutorial-8-multicurve.md)*

Par risk bumps the market quotes and rebuilds the curve; zero risk bumps the zero rates of a given curve. A 1 bp move in a par quote is not a 1 bp move in the zero rates, so the two answers differ.

The spec: `risk.curve.par` reports `par_dv01` with every quote bumped and the curve rebuilt by `rates.ois.bootstrap`; `risk.curve.key_rate` reports `zero_dv01` for `D(t) exp(-h t)`, a parallel shift of continuously compounded zeros with no rebuild.

**Worked example.** The 2Y receiver of Q8.1 has par_dv01 = -4,806.94 and zero_dv01 = -4,913.22. The par number is smaller because the 2Y zero moves less than the 2Y quote, and the short pillars move differently, so the products of the two shapes differ by about 2%.

Desks hedge in par terms (they trade quotes); reporting the zero DV01 as the hedge amount misses by that difference.

### Q8.14 What do the `TRIANGULAR` and `PILLAR` key-rate modes bump, and do the buckets add up?

*Level: practitioner. Evidence: computed; golden (`risk_r2-0002`); spec. Source: [Par and key-rate spec](../../specifications/06-risk/par-and-key-rate.md)*

Key-rate risk splits a parallel zero-rate move into pieces, one per key date, so you can see where on the curve the risk sits.

The spec: `TRIANGULAR` weights in curve time `t = (d - as_of)/365` fall linearly from 1 at key `k_i` to 0 at its neighbours, flat beyond the ends, and bucket `i` revalues on `D(t) exp(-w_i(t) h t)` at every date; `PILLAR` bumps one pillar's zero rate and re-interpolates. In both modes the buckets sum to `zero_dv01` to first order (goldens: below 1e-6 relative).

**Worked example.** On the 2Y receiver, the sum of TRIANGULAR key rates -4,913.22 and the sum of PILLAR key rates -4,913.22 both match `zero_dv01`, but the 2Y buckets differ: TRIANGULAR 2Y bucket -4,802.59 against PILLAR 2Y bucket -4,828.70, because the two shapes move the curve differently between pillars.

The sum is a check, not a definition: the spec promises first order only, and only `PILLAR` buckets feed the par-from-zero chain rule (Q8.16).

### Q8.15 What basis does `risk.curve.jacobian` use, and why is it lower triangular for `LOG_LINEAR_DF`?

*Level: practitioner. Evidence: computed; golden (`risk_r2-0031`); spec. Source: [Par and key-rate spec](../../specifications/06-risk/par-and-key-rate.md), [R6 rulings](../../specifications/r6-rulings.md)*

The Jacobian tells you how each bootstrapped zero rate moves when one par quote moves.

The spec (ruling R2-A8): rows are continuously compounded ACT/365F zeros `z_i = -ln D(p_i)/t_i`, columns the par quotes as decimal rates on their own day counts; `J[i][j] = (z_i(q + h e_j) - z_i(q - h e_j))/(2h)`, every entry computed (R6-1.1). Local methods (`LOG_LINEAR_DF`, `LINEAR_ZERO`) give a lower-triangular matrix, since a pillar depends only on quotes up to its own; global methods do not.

**Worked example.** On the 13-quote SOFR curve: J[0][0] = 1.013127, J[5][5] = 0.995739, and the largest entry above the diagonal 0.0e+00.

Known limit (R6-1.3): the output is the 1 bp difference quotient, which under `MONOTONE_CONVEX` and `HYBRID` can differ from the derivative by up to 1.5e-3 bp per bp; use a smaller `bump_bp` for the local derivative.

### Q8.16 How do zero-rate key rates and the Jacobian combine into par risk?

*Level: practitioner. Evidence: computed; spec. Source: [Par and key-rate spec](../../specifications/06-risk/par-and-key-rate.md)*

By the chain rule: the value moves with each zero, and each zero moves with each quote, so the value's sensitivity to a quote is the sum over zeros.

The spec: with `PILLAR` key rates on the bootstrapped curve, `par_buckets[j] ≈ sum_i key_rates[i] J[i][j]` to first order. The oracle checks this on every product (gap below 1e-3 of `par_dv01`). It does not hold for `TRIANGULAR` buckets.

**Worked example.** For the 2Y receiver, multiplying the PILLAR key rates by column 5 (the 2Y quote) of the Jacobian, the chain rule gives -4,808.1269, against the bump-and-rebuild par bucket -4,808.1269.

This identity is the standard test that the curve, the risk engine and the Jacobian agree; a break usually means mismatched bases (simple against continuous zeros, or wrong day counts).

### Q8.17 How does `risk.pnl.explain` decide whether a day's P&L is explained?

*Level: practitioner. Evidence: computed; golden (`pnl_r2-0001`); spec; design. Source: [P&L explain spec](../../specifications/06-risk/pnl-explain.md), [R2 rulings](../../specifications/r2-rulings.md)*

Predict the P&L from the par risk times the quote moves, revalue in full, and compare. A large gap means the risk is missing something.

The spec: `risk_pnl = sum_j par_buckets[j] (q_end[j] - q_start[j])/0.0001`; `unexplained = full_pnl - risk_pnl`; `threshold = 0.05 max(|full_pnl|, gross_risk_pnl) + 1e-8 N`, where `gross_risk_pnl` adds every term in absolute value; `explained` when `|unexplained| <= threshold`. No time passes: no carry or theta. The 5% level is a project choice (R2-A4), not the FRTB attribution test.

**Worked example.** The 2Y receiver under a 1 bp parallel rise: full_pnl -4,806.23, risk_pnl -4,806.94, unexplained 0.71, threshold 240.72, so explained.

The gross term stops offsetting buckets from hiding a move; the real-data run also reports Spearman and Kolmogorov-Smirnov statistics, unjudged.

## VaR, ES and backtests in depth

### Q8.18 How does filtered historical simulation rescale past returns?

*Level: practitioner. Evidence: computed; golden (`risk_f4-0019`); spec; literature. Source: [VaR, ES and backtests spec](../../specifications/06-risk/var-es-and-backtests.md)*

Plain historical simulation treats a calm day from last year and a stressed day from last week alike. FHS rescales each past return by the ratio of today's volatility to the volatility at the time.

The spec: `sigma_1^2 = (1/T) sum r_t^2`, `sigma_{t+1}^2 = lambda sigma_t^2 + (1 - lambda) r_t^2` (EWMA, RiskMetrics), scenario `pnl_t = P r_t sigma_{T+1}/sigma_t`, then the order statistic rule. All-zero returns are `E_DOMAIN` (F-39).

**Worked example.** Golden `risk_f4-0019`: 500 daily returns, lambda 0.94, 99%. QuantForge gives sigma_next 0.004757, FHS VaR 11,510.92 and FHS ES 13,924.96. The same returns without rescaling give plain historical VaR 17,325.40: current volatility is below the sample's average, so FHS is lower.

FHS reacts quickly in both directions; a desk that wants a stressed VaR cannot use it as one.

### Q8.19 How is Monte Carlo VaR simulated, and what should it converge to?

*Level: practitioner. Evidence: computed; golden (`risk_f4-0037`); spec. Source: [VaR, ES and backtests spec](../../specifications/06-risk/var-es-and-backtests.md), [RNG spec](../../specifications/01-core/rng.md)*

Draw many correlated normal returns, compute the portfolio P&L on each, and read VaR and ES off the simulated sample.

The spec: `core.rng` with the given `seed`, stream 0, normals by AS 241 path by path, `r = mean + L z` with the lower Cholesky factor (non-positive pivot `E_NOT_POSITIVE_DEFINITE`), `pnl = weights . r`, then the order statistic rule. Tolerance class `common_rng`: every build draws the same numbers.

**Worked example.** Two assets, daily variances 1e-4 and 4e-4, covariance 5e-5, positions 1,000,000 and -500,000, 10,000 paths, seed 7: MC VaR 28,999.14 and MC ES 33,421.39. The portfolio standard deviation 12,247.45 gives parametric VaR 28,491.83 and parametric ES 32,642.07, the values the simulation converges to as `n^{-1/2}`.

A difference of about 2% at 10,000 paths is sampling noise, not a bug; the spec's convergence table measures it at 1,000, 5,000 and 10,000 paths.

### Q8.20 What does Christoffersen's test add to Kupiec's?

*Level: practitioner. Evidence: computed; golden (`risk_f4-0064`); spec; literature. Source: [VaR, ES and backtests spec](../../specifications/06-risk/var-es-and-backtests.md)*

Kupiec checks how many breaks there were; Christoffersen also checks whether they bunch together, since breaks on consecutive days suggest the model reacts too slowly.

The spec: transitions `n_ij` over the `n - 1` consecutive day pairs, `pi_01 = n01/(n00 + n01)`, `pi_11 = n11/(n10 + n11)`, `pi = (n01 + n11)/(n - 1)`; `LR_ind` compares the Markov chain with independence, `LR_cc = LR_uc + LR_ind`, p-values from chi-square with 1, 1 and 2 degrees of freedom.

**Worked example.** Golden `risk_f4-0064`, 250 days with 3 isolated breaks: n00 = 243, n01 = 3, n10 = 3, n11 = 0. QuantForge gives LR_uc 0.094940, LR_ind 0.073173, LR_cc 0.168113 and p_cc 0.919379: right count, no clustering.

With so few breaks the independence test has little power; a validator reads it alongside the count, not alone.

### Q8.21 Which ES estimator does QuantForge use, and why did it change in v0.8.1?

*Level: practitioner. Evidence: computed; spec; literature. Source: [VaR, ES and backtests spec](../../specifications/06-risk/var-es-and-backtests.md), [R6 rulings](../../specifications/r6-rulings.md), [Tutorial 5](../getting-started/tutorial-5-risk.md)*

ES is the average of the worst `1 - c` share of outcomes. With 250 days at 99% that share is 2.5 days, so the half day must be handled.

The spec (ruling R6-3.1, Acerbi and Tasche 2002): `w = n - n c`, `m = floor(w)`, `es = (L_(n) + ... + L_(n-m+1) + (w - m) L_(n-m))/w`; `tail_count = ceil(w)`. Before v0.8.1 ES was the plain mean of `L_(k)..L_(n)`, which is biased low (review finding 11: -6.0% at `n = 500`, 99%).

**Worked example.** On Q8.4's sample, `w = 2.5`: ES = (5,542,122.75 + 4,959,560.16 + 0.5 x 4,715,737.90)/2.5, which QuantForge reports as ES 5,143,820.74 with tail_count 3. The old estimator 5,072,473.60 was 1.4% lower.

When `n (1 - c)` is a whole number, the VaR scenario gets weight 0: at `n = 500`, 99%, ES is the mean of the five largest losses and VaR is the sixth.

## FRTB standardised approach

### Q8.22 How does QuantForge compute the FRTB GIRR delta charge?

*Level: practitioner. Evidence: computed; golden (`frtb_f-0001`); spec; literature. Source: [FRTB GIRR spec](../../specifications/06-risk/frtb-sa-girr.md), [Tutorial 5](../getting-started/tutorial-5-risk.md)*

The regulator's recipe weights each rate sensitivity by a fixed risk weight, adds them within a currency allowing for correlation between tenors, then across currencies, under three correlation scenarios, and takes the worst.

The spec (MAR21): `s_k` is the value change for +1 bp divided by 0.0001; `WS_k = RW_k s_k` with RW 1.6% at 1Y, 1.3% at 2Y, 1.2% at 3Y, 1.1% from 5Y; `rho = max(exp(-0.03 |T_k - T_l|/min(T_k, T_l)), 40%)`; `K_b = sqrt(sum WS^2 + sum rho WS WS)`; scenarios high `min(1.25 rho, 1)`, low `max(2 rho - 1, 0.75 rho)`; ties go to high.

**Worked example.** One 5Y sensitivity of 1,000,000 gives capital 11,000.00 in every scenario. Tutorial 5's 5Y payer swap has 5Y sensitivity 45,944,422 plus three small same-sign short tenors: GIRR delta capital 505,810.25, binding scenario high (medium 505,792.56), because same-sign risks cost more when more correlated.

The pitfall is the sensitivity unit: MAR21 wants DV01 divided by 0.0001, not DV01.

### Q8.23 Why does the low-correlation scenario bind for an FX book with offsetting pairs?

*Level: practitioner. Evidence: computed; golden (`frtb_f2b-0002`); spec. Source: [FRTB FX and equity spec](../../specifications/06-risk/frtb-sa-fx-equity.md)*

Each currency pair is its own bucket. When two buckets have opposite signs, correlation offsets them, so less correlation means less offset and more capital.

The spec: `RW = 15%` (MAR21.87, divided by `sqrt 2` for elected pairs under MAR21.88), one factor per bucket so `K_b = |WS_b|`, cross-bucket `gamma = 60%` (MAR21.89), aggregation and scenarios as GIRR.

**Worked example.** EURUSD 1,000,000 and USDJPY -400,000 give WS 150,000 and -60,000. QuantForge reports medium 123,693.17, low 134,164.08 (gamma 45%) and high 112,249.72. Capital is the low scenario.

The binding scenario depends on the book's signs, so the class charges cannot simply be added across classes (Q8.28).

### Q8.24 How are an equity spot and repo sensitivity on the same issuer aggregated?

*Level: practitioner. Evidence: computed; golden (`frtb_f2b-0008`); spec. Source: [FRTB FX and equity spec](../../specifications/06-risk/frtb-sa-fx-equity.md), [Stage G rulings](../../specifications/stage-g-rulings.md)*

Spot price risk and repo-rate risk on the same stock are two risk factors that move almost together, so they are aggregated with a correlation just below 1.

The spec (MAR21.77, 21.78): bucket 5 weights are 30% spot and 0.30% repo; same issuer, spot against repo, correlation 99.90%; high scenario caps correlation at 100%.

**Worked example.** Issuer A in bucket 5 with spot 1,000,000 (WS 300,000) and repo 50,000,000 (WS 150,000): medium K = 449,899.99, high K = 450,000.00, the simple sum, which binds.

Bucket 11 (other sector) has no correlation at all: its charge is the simple sum of absolute net weighted sensitivities (ruling G-49).

### Q8.25 How does liquidity-adjusted VaR add the cost of exit?

*Level: practitioner. Evidence: computed; golden (`risk_f4b-0017`); spec; literature. Source: [Portfolio risk tools spec](../../specifications/06-risk/portfolio-risk-tools.md)*

VaR assumes you can trade at mid. Closing a position costs half the bid-ask spread, and spreads widen in stress, so a cost at a stressed spread is added.

The spec (Bangia et al. 1999): `liquidity_cost = (1/2) sum |P_i| (mu_i + z sigma_i)` with relative spreads, `lvar = var + liquidity_cost`.

**Worked example.** VaR 1.2 million, positions 5, -3 and 2 million with mean spreads 0.1%, 0.2%, 0.4% and spread vols 0.05%, 0.1%, 0.3%, `z = 2.326`: liquidity_cost 22,874.50 and lvar 1,222,874.50.

This is the exogenous spread cost only; price impact from the position's own size is not modelled.

### Q8.26 How does `risk.vol.horizon` scale a daily volatility when returns are autocorrelated?

*Level: practitioner. Evidence: computed; spec; literature. Source: [Portfolio risk tools spec](../../specifications/06-risk/portfolio-risk-tools.md)*

The square-root-of-time rule assumes independent days. With positive autocorrelation, moves continue and multi-day variance grows faster.

The spec (Lo and MacKinlay 1988): with AR(1) coefficient `rho`, `Var(sum of h) = sigma^2 (h + 2 sum_{k=1}^{h-1} (h - k) rho^k)`; outputs `vol`, `sqrt_rule_vol = sigma sqrt h` and `variance_ratio`. `|rho| < 1`, `h >= 1`, else `E_DOMAIN`.

**Worked example.** Daily vol 1%, `rho = 0.2`, 10 days: variance_ratio 1.437500, vol 0.037914 against sqrt_rule_vol 0.031623, so the square-root rule understates 10-day vol by about 17%.

Negative autocorrelation (mean reversion) does the opposite; at `rho = 0` the two agree exactly (`risk_f4b-0020`).

### Q8.27 What do Euler risk contributions add up to, and why?

*Level: practitioner. Evidence: computed; spec; literature. Source: [Optimisation spec](../../specifications/07-portfolio/optimisation.md), [Stage J wave 2 rulings](../../specifications/stage-j-rulings-w2.md)*

Euler contributions split a portfolio's volatility into one piece per asset that adds up exactly to the total, so you can say which position the risk comes from.

The spec (Tasche 1999): `sigma = sqrt(w' S w)`, marginal `dsigma/dw_i = (S w)_i / sigma`, contribution `w_i (S w)_i / sigma`, share `contribution / sigma`. They sum to `sigma` (to 1e-10 relative) because volatility is homogeneous of degree 1 in `w` (Euler's theorem).

**Worked example.** Weights 0.7 and 0.3, variances 0.04 and 0.09, covariance 0.012: volatility 0.180942, contributions 0.122249, 0.058693, shares 0.675626, 0.324374.

A contribution can be negative for a hedge; that is the information, not an error.

## Advanced

### Q8.28 Why must FRTB class charges be totalled with `risk.frtb.sbm_total` rather than added?

*Level: advanced. Evidence: computed; golden (`sbm_total_r6-0001`); spec; literature. Source: [FRTB GIRR spec](../../specifications/06-risk/frtb-sa-girr.md), [R6 rulings](../../specifications/r6-rulings.md)*

MAR21.7 adds every class's charge within the same correlation scenario first, and only then takes the worst scenario. Adding each class's own worst charge overstates the total when classes disagree on the worst scenario.

The spec (ruling R6-4.1): `scenario_totals` sum each scenario over components; `capital` is the largest; `sum_of_component_capitals` is the overstated figure, reported so the difference is visible.

**Worked example.** GIRR delta binds high, the FX delta of Q8.23 binds low. QuantForge gives capital 138,518.07 (low) against sum_of_component_capitals 138,564.08.

QuantForge implements the sensitivities-based method only: no default risk charge (MAR22), residual risk add-on or securitisation classes, so `sbm_total` is not the full standardised capital.

### Q8.29 How does FRTB vega correlate two GIRR vegas with different option and underlying maturities?

*Level: advanced. Evidence: computed; golden (`frtb_f2c-0001`); spec. Source: [FRTB vega and curvature spec](../../specifications/06-risk/frtb-sa-vega-curvature.md), [Tutorial 15](../getting-started/tutorial-15-advanced-risk.md)*

Vega is charged like delta, but GIRR vega factors have two maturities, the option's and the underlying swap's, and correlation falls with distance in both.

The spec (MAR21.93): `rho = min(exp(-a |T_k - T_l|/min(T_k, T_l)) x exp(-a |U_k - U_l|/min(U_k, U_l)), 1)`, `a = 1%`; risk weight 100% (77.78% for large-cap equity and indices); cross-bucket `gamma` of the delta class.

**Worked example.** EUR 1y-into-5y +1,000,000 and 5y-into-10y -600,000, USD 1y-into-5y 800,000: `rho = 0.951229`, K_EUR = 467,466.25 in the medium scenario, vega capital 1,095,445.12 (high).

The two maturities enter as a product, so a pair far apart in both is less correlated than either factor alone suggests.

### Q8.30 How is FRTB curvature computed and how is the up or down direction chosen?

*Level: advanced. Evidence: computed; golden (`frtb_f2c-0010`); spec. Source: [FRTB vega and curvature spec](../../specifications/06-risk/frtb-sa-vega-curvature.md), [Tutorial 15](../getting-started/tutorial-15-advanced-risk.md)*

Curvature charges the loss under a large up and a large down shock, after removing what delta already counts. Each bucket keeps its worse direction; pairs that both gain are ignored.

The spec (MAR21.5): `CVR^+ = -(V(x up) - V(x) - RW s)`, likewise down; `K^± = sqrt(max(0, sum max(CVR^±, 0)^2 + sum rho^2 CVR CVR psi))`, `K_b = max(K^+, K^-)`, upward if `K^+ > K^-` (ties by the sums); across buckets `gamma^2` (GIRR 25%) with `psi = 0` when both are negative. A long-gamma position has `CVR^± <= 0` and no charge (`frtb_f2c-0010`).

**Worked example.** GIRR, EUR `CVR^+ = 500,000`, `CVR^- = 300,000`; USD `-200,000` and `400,000`: QuantForge gives curvature capital 731,436.94 with selected EUR UP, USD DOWN.

The inputs are the bank's CVRs, already summed over instruments; QuantForge does not revalue the book under the shocks.

### Q8.31 How do AAD and bump-and-revalue compare on a Bermudan swaption under Hull-White?

*Level: advanced. Evidence: computed; spec; literature. Source: [AAD core spec](../../specifications/06-risk/aad-core.md), [Tutorial 5](../getting-started/tutorial-5-risk.md)*

Bumping costs two pricings per input. AAD records one pricing and runs the chain rule backwards, giving every sensitivity for a small multiple of one pricing.

The spec: `rates.shortrate.bermudan_ladder` returns `dV/dθ` for the discount factors, `a` and `sigma`, the derivative of the discrete grid scheme as computed, exercise `max` on its active branch. Bump reference: central difference with `h = 1e-4 x` input; goldens use Richardson extrapolation and a tolerance `1e-10 + 1e-8 |ref|` per unit notional (G-9).

**Worked example.** A payer Bermudan on 1 million, exercisable yearly from 1 to 5 years into a swap to year 6 at 3.9462%, `a = 5%`, `sigma = 1%`: price 22,697.8097, AAD dV/dsigma 2,269,594.61 and bump dV/dsigma 2,269,594.61 per 1.00 of `sigma`; dV/da -52,528.10.

Agreement is not guaranteed in principle: a bump that moves an exercise decision across a grid node breaks the central difference, which is why the goldens use Richardson.

### Q8.32 What is the limit case for the IFT book sensitivity of a par payer swap?

*Level: advanced. Evidence: computed; golden (`risk_f3-0005`); spec; literature. Source: [Book sensitivities spec](../../specifications/06-risk/book-sensitivities.md), [Stage F rulings](../../specifications/stage-f-rulings.md)*

A swap at its par rate is worth zero, and raising its own quote raises the fixed rate the market would pay, so a payer gains its annuity per unit of quote.

The spec: `quote_sensitivity.matrix[i][j] = d pv_i / d q_j` per unit quote, curve rebuilt in the derivative, by the IFT `dx/dq = (dR/dx)^{-1}` with `x_i = ln D(p_i)`. The Rust reference uses a tape with the curve adjoint through the IFT; the others use the chain rule exactly. Tolerance `1e-10 + 1e-8 |ref|` (class `aad_sensitivity`).

**Worked example.** Golden `risk_f3-0005`: one 5-year SOFR payer at par, notional 1. QuantForge gives book_pv 0.000000 and d pv / d q_5Y = 4.561889 on the quote 5Y, which is the swap's own annuity; the other eleven quotes give exactly 0, since a par swap on a sequential build depends only on quotes up to its own tenor and its value is zero on that curve.

Central differences on `x` are not exact enough here (1e-9 relative against a 1e-8 bound); the spec requires an exact method.

### Q8.33 What does PCA of daily curve changes return, and how does QuantForge fix the sign of a loading?

*Level: advanced. Evidence: computed; golden (`risk_f3-0010`); spec; literature. Source: [Book sensitivities spec](../../specifications/06-risk/book-sensitivities.md)*

Principal components find the few shapes that explain most curve moves; for rates the first two are usually level and slope (Litterman and Scheinkman 1991).

The spec: demean each column, sample covariance with divisor `T - 1`, symmetric eigen decomposition; eigenvalues descending; loadings are unit eigenvectors with the entry of largest absolute value positive (ties: lowest index). Near-equal eigenvalues (within `1e-6 lambda_1`) make loadings non-unique, so the result is `E_DOMAIN`.

**Worked example.** Golden `risk_f3-0010`, five tenors: explained_ratio 0.886271, 0.108480; first loading 0.4373, 0.4378, 0.4411, 0.4519, 0.4672 (level); second loading 0.6558, 0.3180, 0.0005, -0.3143, -0.6083 (slope).

Without a sign rule, two correct solvers can return opposite-signed loadings; the rule makes goldens comparable.

### Q8.34 How does `risk.stress.reverse` find the size of move that loses a target amount?

*Level: advanced. Evidence: computed; golden (`risk_f4b-0001`); spec; literature. Source: [Portfolio risk tools spec](../../specifications/06-risk/portfolio-risk-tools.md)*

Instead of asking what a scenario costs, ask how far along a chosen scenario direction the market must move to cost a given loss.

The spec (Breuer et al. 2009): delta-gamma P&L `PnL(k) = b k + a k^2`, `b = delta . d`, `a = d' Gamma d / 2`; `scale` is the smallest `k > 0` with `PnL(k) = -L`, solved in the cancellation-free form; no root is `E_DOMAIN`.

**Worked example.** `b = -1,275`, `a = -1,107.8`, loss 50: scale 0.037942. Without gamma the answer is `50/1,275`, without gamma 0.039216: negative gamma makes the loss arrive sooner.

The result is only as good as the delta-gamma approximation; for large `k` a validator reprices in full along the found scenario.

### Q8.35 Pathwise or likelihood ratio: which Monte Carlo Greek is less noisy for a vanilla call?

*Level: advanced. Evidence: computed; spec; literature. Source: [MC Greeks spec](../../specifications/06-risk/mc-greeks.md), [Tutorial 15](../getting-started/tutorial-15-advanced-risk.md)*

Pathwise differentiates the payoff along each path; likelihood ratio differentiates the probability density instead. Pathwise needs a continuous payoff, likelihood ratio does not but is noisier.

The spec: `risk.mc.greeks` returns `delta`, `vega` and their standard errors for each method on the same random draws (seeded `core.rng`).

**Worked example.** One-year at-the-money call, `r = 3%`, `q = 1%`, vol 20%, 10,000 paths: pathwise delta 0.567128 +- 0.005831, likelihood-ratio delta 0.568857 +- 0.013621, pathwise vega 38.4717 +- 0.7349, likelihood-ratio vega 38.1801 +- 2.4982. The Black-Scholes delta 0.573496 is within about 1.1 standard errors of both.

On a digital the pathwise derivative is zero almost everywhere, and the likelihood ratio earns its place.
