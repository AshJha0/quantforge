# Question bank 7: Credit and correlation

This set checks your understanding of what QuantForge implements for single-name credit, credit options, default correlation and correlation matrices: the ISDA CDS standard model, sector and index curves, CDS and CDS index options, Gaussian and Student t copulas, the large homogeneous pool, nearest-correlation repair, implied correlation and dispersion. It is written for two readers: a newcomer who has done [Tutorial 4](../getting-started/tutorial-4-credit.md), and a practitioner who wants to know exactly which convention QuantForge fixes. Each question is tagged foundation, practitioner or advanced. Try to answer before reading; every number in a worked example was produced by `quantforge_core` and is rechecked by `verify/v07_credit_correlation.py`. All data is synthetic.

## The ISDA CDS model

### Q7.1 How does QuantForge set the maturity and accrual dates of a standard CDS traded on 2026-11-06?

*Level: foundation. Evidence: spec; computed. Source: [Credit spec](../../specifications/04-pricing/credit.md), [Tutorial 4](../getting-started/tutorial-4-credit.md)*

Standard CDS do not mature "trade date plus five years". They mature on fixed roll dates, so that contracts traded on different days are interchangeable.

The spec's rule: the roll date is 20 December of the trade year if `T` is on or after 20 September, 20 June if on or after 20 March, else 20 December of the year before. A tenor `nM` or `nY` matures that many months after the roll date, on the 20th, unadjusted. Premiums accrue ACT/360 between 20 March, June, September and December, starting from the last such date on or before `T`; period ends are moved to the next weekday except maturity itself, and the last period gets one extra day. Step-in is `T + 1` calendar day, cash settlement `T + 3` business days (weekdays only, no holidays).

**Worked example.** `T` = 2026-11-06 is after 20 September, so the roll date is 2026-12-20 and the 5Y quote matures on 2031-12-20. The bootstrap of the Tutorial 4 quotes (golden `credit_d-0001`) puts a survival pillar on exactly that date: `Q(2031-12-20) = 0.898896`.

The pitfall is a maturity of 2031-11-06: the schedule and every survival pillar move, and nothing reprices.

### Q7.2 What is the credit triangle, and how close does it get to QuantForge's bootstrap?

*Level: foundation. Evidence: computed; spec. Source: [Credit spec](../../specifications/04-pricing/credit.md), [Tutorial 4](../getting-started/tutorial-4-credit.md)*

With a flat default intensity, the premium a protection buyer pays per year roughly equals the expected loss per year: default rate times loss given default.

Formally, `s ≈ h (1 - R)`, so `h ≈ s / (1 - R)`, and survival is `Q(t) = exp(-h t)` with `t = (d - T)/365` as the spec measures curve time.

**Worked example.** The 5Y spread is 120 bp and recovery 40%, so `h ≈ 0.012 / 0.6 = 0.02`. From 2026-11-06 to 2031-12-20 is 5.1233 years, and `exp(-0.02 x 5.1233) = 0.902609`. The bootstrap gives `Q(2031-12-20) = 0.898896`: lower, because the spreads rise with maturity, so the hazard on the later pieces is above 2%, and because the full model pays accrual on default and discounts.

The triangle is a sanity check, not a pricer; a validator uses it to catch a recovery or units error, which would miss by a factor rather than a fraction of a percent.

### Q7.3 Why does every `credit.*` operation reject a discount curve that is not `LOG_LINEAR_DF`?

*Level: foundation. Evidence: spec; design. Source: [Credit spec](../../specifications/04-pricing/credit.md), [R1 rulings](../../specifications/r1-rulings.md)*

The ISDA standard model assumes the forward rate is flat between discount-curve nodes. Log-linear interpolation of discount factors gives exactly that, so it is the only interpolation that reproduces the model.

The spec states that `discount` must have `interpolation` `LOG_LINEAR_DF`, and any other value is `E_INPUT` in every `credit.*` operation, checked before any other rule check (ruling R1-4). The leg integrals rely on it: on each piece between nodes `f = ln(P0/P1)/(t1 - t0)` is a constant, and the closed forms for the protection leg and the accrual on default use `k = f + h` as a constant.

There is no worked number here: the answer is the error code. The real ISDA convention builds this curve from deposit and swap rates; QuantForge takes the curve directly, so a desk comparing with Markit must feed the same nodes.

### Q7.4 For a standard CDS with a 100 bp coupon, what are the par spread, the upfront and the PV, and how do they differ?

*Level: foundation. Evidence: computed; golden (`credit_d-0004`); spec. Source: [Credit spec](../../specifications/04-pricing/credit.md), [Tutorial 4](../getting-started/tutorial-4-credit.md)*

Since the 2009 conventions, CDS trade with a fixed running coupon (100 or 500 bp). The quoted spread is still the par spread, and the gap between the two is settled as an upfront payment.

The spec defines, per unit notional: `par_spread = protection_leg / (rpv01 - (accrued/coupon) Pcs)`; `upfront = (protection_leg - coupon rpv01)/Pcs + accrued`, the clean upfront paid by the buyer at cash settlement; and `pv = sign notional (protection_leg - coupon rpv01 + accrued Pcs)`, +1 for the buyer, valued at the trade date.

**Worked example.** Buy 10 million of 5Y protection (to 2031-12-20) on the bootstrapped curve. QuantForge gives protection leg 0.053986, rpv01 4.629357, accrued 0.001306, upfront 0.009003 per unit, PV 89,977.43, and par spread 0.012000, the 5Y quote itself, as it must be.

Common mistake: reading the upfront as the PV. The upfront is per unit and paid at `T + 3` business days; the PV is money, signed for the buyer, at `T`.

### Q7.5 What makes a matrix a valid correlation matrix, and how does `risk.corr.validate` report it?

*Level: foundation. Evidence: computed; golden (`corr_e-0001`); spec; literature. Source: [Correlation spec](../../specifications/06-risk/correlation.md)*

A correlation matrix must be symmetric, have ones on the diagonal, entries in `[-1, 1]`, and be positive semidefinite, because no portfolio can have negative variance. Matrices built pair by pair often fail the last test while passing the other three.

The operation reports `symmetric` (exact `m_ij == m_ji`), `unit_diagonal` (exact `m_ii == 1`), `in_range`, `min_eigenvalue` of `(M + M^T)/2`, `psd` (`min_eigenvalue >= -1e-10`) and `valid` (all four).

**Worked example.** Higham's 3 by 3 `M = [[1,1,0],[1,1,1],[0,1,1]]` has eigenvalues `1 + sqrt 2`, 1 and `1 - sqrt 2`. QuantForge returns `min_eigenvalue = -0.414214`, so `psd` and `valid` are false although every entry is in range.

A validator wants the eigenvalue, not only the flag: a value of `-1e-12` is rounding, `-0.4` is a broken input.

### Q7.6 How does QuantForge compute the implied correlation of an index from its members' volatilities?

*Level: foundation. Evidence: computed; golden (`corr_e-0036`); spec. Source: [Correlation spec](../../specifications/06-risk/correlation.md), [Stage E rulings (spec B)](../../specifications/stage-e-rulings-b.md)*

If the index variance is known from index options and each member's variance from its own options, one average pairwise correlation makes the two consistent.

The spec's formula: `correlation = (sigma_I^2 - sum_i w_i^2 sigma_i^2) / (sum_{i != j} w_i w_j sigma_i sigma_j)`, where the sum over `i != j` counts each pair twice. The result is not clipped to `[-1, 1]` (ruling E-B20); weights must be non-negative with at least two positive (E-B33).

**Worked example.** `w = (0.5, 0.5)`, `sigma = (20%, 30%)`, `sigma_I = 22%`. The numerator is `0.0484 - 0.25 (0.04 + 0.09) = 0.0159`, the denominator `2 x 0.25 x 0.2 x 0.3 = 0.03`, and QuantForge returns `correlation = 0.530000`.

Because nothing is clipped, a result above 1 is reported as is: it tells you the index vol is inconsistent with the member vols, which a clipped value would hide.

### Q7.7 What does a default copula do, and what does the Gaussian copula give at zero correlation?

*Level: foundation. Evidence: computed; golden (`creditopt_e-0155`); spec; literature. Source: [CDS options and copulas spec](../../specifications/04-pricing/credit-options-and-copulas.md)*

Each name has its own default probability. A copula joins them: draw two correlated variables and call a name defaulted when its variable falls below the matching quantile.

The spec: `GAUSSIAN: joint = Phi_2(Phi^-1(p1), Phi^-1(p2); rho)` and `default_correlation = (joint - p1 p2) / sqrt(p1 (1 - p1) p2 (1 - p2))`. Inputs are exactly two probabilities in `(0, 1)` and `|rho| < 1`, else `E_INPUT` or `E_DOMAIN` (Li 2000 [S3]).

**Worked example.** `p = (2%, 3%)`, `rho = 0`: QuantForge gives joint = 0.000600, which is `p1 p2`, independence, and a default correlation of zero to rounding.

Keep the two correlations apart: `rho` is the correlation of the latent variables, the default correlation is that of the default indicators, and the second is much smaller (Q7.15).

## Curves, indices and options

### Q7.8 How does the bootstrap solve the survival curve, and what happens to it if recovery is lowered to 25%?

*Level: practitioner. Evidence: computed; spec. Source: [Credit spec](../../specifications/04-pricing/credit.md), [Stage D rulings](../../specifications/stage-d-rulings.md)*

The bootstrap takes the quotes in tenor order and, for each, solves the one hazard rate on the new piece that makes that CDS worth zero at its par spread, keeping the pieces already fitted.

Formally, hazard is flat between pillars (`-ln Q` linear in time), pillars sit at each quote's maturity date, not maturity plus one day (ruling D20), and each quote's `par_spread` is matched below 1e-13 in the oracle's replay. Checks: recovery outside `[0, 1)` is `E_DOMAIN`, maturities not increasing `E_INPUT`, a spread `<= 0` `E_DOMAIN`.

**Worked example.** With the Tutorial 4 quotes and 40% recovery, 5Y survival is 0.898896 and the 10-year survival 0.763567. Rerun with recovery 25% and the 5Y survival rises to 0.918441: each default now costs 75% of notional, so less default probability explains the same spreads.

The point for a desk: survival probabilities are not observed, they are conditional on the recovery assumption, so a recovery change moves CS01 and jump-to-default even when the spreads do not.

### Q7.9 What goes into the risky annuity `rpv01`, and why is accrual on default included?

*Level: practitioner. Evidence: computed; spec; literature. Source: [Credit spec](../../specifications/04-pricing/credit.md), [Tutorial 4](../getting-started/tutorial-4-credit.md)*

The risky annuity is the value of paying 1 a year while the name survives. On default the buyer still owes the premium accrued since the last coupon date, so that piece belongs in the annuity.

The spec: `rpv01 = sum_i alpha_i Q(p_i - 1) P(p_i) + AoD_i`, with `alpha_i` the ACT/360 accrual. The accrual-on-default term integrates over pieces between nodes using `h`, `f` and `k = f + h` constant on each piece: `AoD_i = (365/360) sum h QP(t0) [ (t0 - tacc)(1 - e^{-kD})/k + (1 - e^{-kD}(1 + kD))/k^2 ]`. When `kD < 1e-4` a fourth-order Taylor series may be used (QuantLib's form).

**Worked example.** For the 5Y contract on the Tutorial 4 curve, QuantForge gives rpv01 4.629357 per unit coupon: a little under the 5.12 years to maturity, because of discounting and default.

The wrong-convention checks in the suites include "annuity without accrual on default" and "ACT/365 premium accrual"; each moves the price well outside the 1e-9 per unit tolerance against QuantLib's `IsdaCdsEngine`.

### Q7.10 How does `credit.curve.composite` build a sector curve, and why does the order of averaging matter?

*Level: practitioner. Evidence: computed; golden (`credit_d-0011`); spec. Source: [Credit spec](../../specifications/04-pricing/credit.md), [Tutorial 4](../getting-started/tutorial-4-credit.md)*

When a name has no liquid CDS, desks proxy it with a sector or rating curve built from names that do.

The spec fixes the order: first the weighted average spread at each tenor, `scale x sum w s / sum w`, then a `credit.cds.bootstrap` of those spreads. All constituents must quote the same tenors, else `E_INPUT`; `scale > 0` is a rating multiplier (1 for the sector itself).

**Worked example.** Three names at 1.0, 1.3 and 0.8 times the Tutorial 4 spreads, weights 2, 1 and 1: the average is 1.025 times the curve, so the 5Y sector spread 0.012300, and QuantForge's sector 5Y survival 0.896476, slightly below the single name's 0.898896.

Averaging survival probabilities or hazard rates instead gives a different curve, because the map from spread to survival is not linear; the spec fixes spread averaging so that every build agrees.

### Q7.11 What is the intrinsic upfront of a CDS index, and what is the index basis?

*Level: practitioner. Evidence: computed; golden (`credit_d-0009`); spec. Source: [Credit spec](../../specifications/04-pricing/credit.md)*

An index CDS is, in principle, a portfolio of single-name CDS on its members with the index coupon. Pricing each member on its own curve and averaging gives the intrinsic value; the traded index price usually differs.

The spec: `credit.index.intrinsic` prices each name's `upfront` (as `credit.cds.price`) on the index maturity and coupon, then `intrinsic_upfront = sum w u / sum w` and `basis = quoted_upfront - intrinsic_upfront`. Empty `names` is `E_INPUT`.

**Worked example.** Golden `credit_d-0009` has three names weighted 1, 1 and 0.5, on a 5Y index with a 100 bp coupon: QuantForge returns name upfronts 0.009003, -0.007289, 0.156712 (the third is a distressed name), an intrinsic upfront 0.032028, and with a quoted upfront 0.033528 a basis 0.001500 per unit.

The basis is a real trading quantity (liquidity, technicals, CDS-bond effects); QuantForge reports it but does not model or adjust curves to remove it.

### Q7.12 How is a single-name CDS option priced, and what is the front-end protection?

*Level: practitioner. Evidence: computed; golden (`creditopt_e-0001`, `-0003`); spec; literature. Source: [CDS options and copulas spec](../../specifications/04-pricing/credit-options-and-copulas.md), [Stage E rulings (spec B)](../../specifications/stage-e-rulings-b.md)*

A payer CDS option is the right to buy protection at a fixed spread on a future date. If the name defaults before expiry, a knock-out option dies; a non-knock-out payer also collects the default loss before expiry, the front-end protection.

The spec uses stylised legs (ruling E-B22, not the ISDA model): flat `r` and `h`, quarterly periods from expiry, mid-period default. `F = protection / A`, `price = N A Black(F, K, sigma, T)` with `T` the time to expiry, plus, for a non-knock-out payer only, `front_end_protection = N (1 - R)(1 - S(expiry)) P(expiry)` (E-B23), with `1 - S` computed as `-expm1(-h T)`.

**Worked example.** Golden `creditopt_e-0001`: expiry 2027-03-20, CDS to 2032-03-20, `r = 3.5%`, `h = 2%`, `R = 40%`, payer at 1.20%, vol 50%, knock-out, 10 million. QuantForge gives forward spread 0.011888, risky annuity 4.328652, price 59,847.84, and reports front-end protection 43,333.06; the same option without knock-out is the non-knock-out payer 103,180.90. The receiver at 0.96% 11,581.73 gets no front-end term.

Adding the front-end protection to a knock-out is one of the spec's caught wrong conventions.

### Q7.13 What is the nearest correlation matrix, and why is clipping eigenvalues not good enough?

*Level: practitioner. Evidence: computed; golden (`corr_e-0002`); spec; literature. Source: [Correlation spec](../../specifications/06-risk/correlation.md), [Stage E rulings (spec B)](../../specifications/stage-e-rulings-b.md)*

When a matrix fails validation, replace it by the closest valid correlation matrix. "Closest" is the Frobenius norm, and the answer is unique because the valid set is convex.

The spec: minimise `||X - M||_F` over symmetric PSD matrices with unit diagonal, unweighted (ruling E-B18). The reference is Higham's alternating projections with Dykstra's correction, stopping at `tol <= 1e-12` (E-B31); acceptance is 2e-5 on entries and distance, against goldens refined to 1e-30.

**Worked example.** For Higham's 3 by 3 (Q7.5), QuantForge returns off-diagonals for pairs 1-2 and 2-3 0.760690 and for pair 1-3 0.157298, Frobenius distance 0.527790, the values in Higham (2002). The common shortcut, clip-and-rescale gives 0.739539 and 0.093836 at distance 0.537559 (computed with a scratch numpy formula, not the library): valid, but farther away.

The spec lists clip-and-rescale and projections without Dykstra's correction as wrong-convention checks; both miss by far more than 2e-5.

### Q7.14 What does a dispersion trade pay in QuantForge, and how are its variance notionals set?

*Level: practitioner. Evidence: computed; golden (`corr_e-0046`); spec. Source: [Correlation spec](../../specifications/06-risk/correlation.md), [Stage E rulings (spec B)](../../specifications/stage-e-rulings-b.md)*

A dispersion trade buys variance on the members and sells variance on the index. It profits when members move more than the index, that is when realised correlation is below the correlation implied at the strikes.

The spec (ruling E-B21): `N_i = N w_i / (2 K_i)` long, `N_I = N / (2 K_I)` short, so each leg carries about `N w_i` of vega at its strike, and `pnl = sum_i N_i (s_i^2 - K_i^2) - N_I (s_I^2 - K_I^2)`. Implied and realised correlation use the Q7.6 formula at the strikes and at the realised vols.

**Worked example.** Vega notional 100,000, strikes 25% and 30%, index strike 24%, realised 28%, 35% and 22%. `N_1 = 100,000`, N_2 = 83,333.33, N_I = 208,333.33, and QuantForge gives P&L 6,215.00, with implied correlation 0.519333 and realised correlation -0.037245.

The trade is a correlation bet with vega exposures attached; the realised correlation is reported unclipped, and on two names it can be noisy, as here.

### Q7.15 Why does the Student t copula give more joint defaults than the Gaussian at the same correlation?

*Level: practitioner. Evidence: computed; golden (`creditopt_e-0147`, `-0151`, `-0154`); spec; literature. Source: [CDS options and copulas spec](../../specifications/04-pricing/credit-options-and-copulas.md)*

The Gaussian copula has no tail dependence: very bad outcomes for two names become independent in the limit. The Student t copula shares a common random scale, so extreme draws come together, and joint defaults, which are tail events, become likelier.

The spec: `STUDENT_T: joint = T_2,nu(t_nu^-1(p1), t_nu^-1(p2); rho)`, with `degrees_of_freedom` required (`E_INPUT` if missing) and `nu > 0`. Any method accurate to 1e-12 absolute plus 1e-9 relative is allowed (ruling E-B24).

**Worked example.** `p = (2%, 3%)`, `rho = 0.3`: Gaussian joint 0.002288, Student t joint 0.005102 with 4 degrees of freedom, more than twice as likely. Their default correlation 0.0707 against 0.1885. Even at `rho = 0`, the t with 5 degrees of freedom on `p = (10%, 15%)` gives joint default 0.020354 against `p1 p2 = 0.015`.

For a validator, "uncorrelated" in a t copula does not mean independent; the spec catches "Gaussian in place of t" as a wrong convention.

## Advanced

### Q7.16 How does QuantForge price an option on a CDS index, and why not reuse the single-name formula with front-end protection added?

*Level: advanced. Evidence: computed; golden (`cdsidx_f-0001`, `-0002`); spec; literature. Source: [CDS options and copulas spec](../../specifications/04-pricing/credit-options-and-copulas.md), [Stage F rulings](../../specifications/stage-f-rulings.md)*

An index option is never knocked out: names that default before expiry settle into the index, and a payer who exercises collects those losses. The index also trades with a fixed coupon `C`, so the strike spread is exercised as an upfront `(K - C) A_K`. Pedersen's method puts both into Black's formula through an adjusted forward and strike.

The spec (rulings F-7, F-8): `G = (K - C) A_K`, `F_adj = F + FEP / A`, `K_adj = C + G P(expiry) / A`, `payer = N A Black_call(F_adj, K_adj, sigma sqrt T)`. `A_K` is the annuity of a flat curve at hazard `h_K`, measured from expiry, with `prot'(h_K)/A'(h_K) = K`.

**Worked example.** Golden `cdsidx_f-0001`: strike 55 bp, coupon 100 bp, `h = 1.05%`, vol 45%, 10 million. QuantForge gives F = 0.006242, F_adj = 0.006638, K_adj = 0.005474, A = 4.308406, A_K = 4.377551, h_K = 0.009251, FEP 17,061.64, payer 57,249.29 and receiver 7,083.69. Parity holds: N A (F_adj - K_adj) = 50,165.60, equal to payer minus receiver 50,165.60.

Adding FEP outright to a Black payer overprices it and breaks parity. The Pedersen paper's own example is not reproduced (not freely available); the spec says so and relies on parity, limits and five wrong-convention cases.

### Q7.17 What are the expected tranche losses in the large homogeneous pool, and what identity must they satisfy?

*Level: advanced. Evidence: computed; golden (`creditopt_e-0161` to `-0166`); spec; literature. Source: [CDS options and copulas spec](../../specifications/04-pricing/credit-options-and-copulas.md), [Stage E rulings (spec B)](../../specifications/stage-e-rulings-b.md)*

In a very large pool of identical names under a one-factor Gaussian copula, the defaulted fraction is a known function of the common factor (Vasicek), so the loss distribution and each tranche's expected loss are closed forms.

The spec: `c = Phi^-1(p)`, `P(M) = Phi((c - sqrt(rho) M)/sqrt(1 - rho))`, pool loss `L = (1 - R) P(M)`. With `k = min(x/(1 - R), 1)`, `E[min(P, k)] = p - [Phi_2(c, m*; sqrt(rho)) - k Phi(m*)]`, and `expected_loss_fraction = (1 - R)(E[min(P, k_d)] - E[min(P, k_a)])/(d - a)` (ruling E-B25). `rho` is the asset correlation, not its square root.

**Worked example.** `p = 5%`, `rho = 0.3`, `R = 40%`, pool loss 3%. QuantForge gives, as a share of tranche notional: 0-3%: 54.1058%, 3-7%: 19.5847%, 7-10%: 8.7831%, 10-15%: 4.0621%, 15-30%: 0.8072%, 30-100%: 0.0082%. Weighted by width they give a width-weighted sum 3.000000%, the pool loss, which the goldens check to 1e-18.

Equity tranches carry most of the expected loss; senior tranches are almost pure correlation risk. QuantForge has the LHP only, not a finite-pool or base-correlation model.

### Q7.18 What does `credit.lhp.loss_cdf` return, and how should you read it?

*Level: advanced. Evidence: computed; golden (`creditopt_e-0167`); spec; literature. Source: [CDS options and copulas spec](../../specifications/04-pricing/credit-options-and-copulas.md)*

It gives the probability that the pool loss stays at or below each level: the whole distribution, of which the tranche losses are integrals.

The spec: `cdf_j = P(L <= x_j) = Phi((sqrt(1 - rho) Phi^-1(x_j/(1 - R)) - c)/sqrt(rho))`. Each `x_j` must be in `(0, 1 - R)`, else `E_DOMAIN`; the tranche points are scaled by `1 - R`, and forgetting that scaling is a caught wrong convention.

**Worked example.** Same pool as Q7.17 (`p = 5%`, `rho = 0.3`, `R = 40%`): P(L <= 1%) = 0.402236, P(L <= 5%) = 0.813407, P(L <= 20%) = 0.990490. The mean loss is 3%, yet the median is below 2%: the distribution is very skewed, which is why the equity tranche loses so much and the senior tranche so little.

A risk manager reads the right tail: here about a 1% chance that pool losses exceed 20%, driven entirely by the correlation input.

### Q7.19 When can you back out an implied volatility from a CDS option premium in QuantForge?

*Level: advanced. Evidence: computed; golden (`creditopt_e-0002`); spec. Source: [CDS options and copulas spec](../../specifications/04-pricing/credit-options-and-copulas.md), [Stage E rulings (spec B)](../../specifications/stage-e-rulings-b.md)*

Implied vol inverts the Black price. It is only well posed when the price is Black on the forward spread and nothing else.

The spec: `credit.cdsoption.implied_vol` accepts knock-out options only; `knock_out = false` is `E_INPUT` (ruling E-B23), because the front-end protection is a vol-free add-on that would be wrongly absorbed into the vol. A premium at or below the zero-vol value, or at or above the upper bound, is `E_DOMAIN`. Tolerance class `root_finding`.

**Worked example.** Feed the price of Q7.12, 59,847.84, back as the premium of the knock-out payer (golden `creditopt_e-0002`): QuantForge returns implied vol 0.500000, the 50% that produced it.

For index options the vol is a vol of the adjusted forward (Q7.16), and QuantForge has no implied-vol operation for them.

### Q7.20 How do you hedge a sold CDS so that both CS01 and jump-to-default are zero, and what risk is left?

*Level: advanced. Evidence: computed; spec. Source: [Credit and correlation hedges spec](../../specifications/08-hedging/credit-and-correlation-hedges.md), [Tutorial 19](../getting-started/tutorial-19-credit-correlation.md), [Stage I rulings](../../specifications/stage-i-rulings.md)*

A CDS position has a small, continuous spread risk (CS01) and a large, sudden default risk (JTD). Two hedge contracts with different ratios of CS01 to JTD can cancel both, as two options can cancel delta and gamma.

The spec (ruling I-15), per unit of bought protection: hazard bump `eps = 1e-4/(1 - R)`, about 1 bp of spread by the credit triangle; `CS01 = (pv(h + eps) - pv(h - eps))/2` with every section shifted, buckets one section at a time; `JTD = (1 - R) - pv`; notionals solve `G n = -book`.

**Worked example.** Tutorial 19's book: 10 million of sold 7-year protection, 1% coupon, `R = 40%`. QuantForge gives CS01 -5,634.25 per bp and JTD -5,793,983.80. Buying protection on the 3-year 3,574,641.02 and the 10-year 6,476,350.56 makes both zero, but leaves buckets -0.18, -1.14, -573.32, -516.02, 1,090.66.

That residual is a curve position: a steepening still costs money. The CS01 here is a hazard bump, not a quote re-bootstrap, and recovery is held fixed.
