# Question bank 9: Counterparty risk and xVA

This set covers what QuantForge implements for counterparty credit risk: exposure profiles (EE, ENE, EPE, effective EPE and the deflated PFE quantile), netting and collateral on given paths, the closed-form swap exposure under Hull-White, portfolio exposure by one-dimensional integration checked against ORE, and the valuation adjustments CVA, DVA, FVA, MVA and KVA, with the sensitivity-based margin (on placeholder weights) and the Hull-White wrong-way-risk model. It is for a newcomer who has done [Tutorial 7](../getting-started/tutorial-7-counterparty.md), and for a practitioner who wants the exact bucket, sign and measure conventions. Questions are tagged foundation, practitioner or advanced. Every number in a worked example was produced by `quantforge_core` and is rechecked by `verify/v09_counterparty_xva.py`. All data is synthetic.

## Exposure basics

### Q9.1 What are discounted EE and ENE, and what simple check links them?

*Level: foundation. Evidence: computed; spec; literature. Source: [Portfolio exposure spec](../../specifications/06-risk/xva-exposure-portfolio.md), [Tutorial 7](../getting-started/tutorial-7-counterparty.md)*

At a future date the trade's value is uncertain. Expected exposure (EE) is the average of its positive part, what you would lose if the counterparty defaulted then; expected negative exposure (ENE) is the average of the negative part, what the counterparty would lose if you defaulted.

The spec: with `f` the netting set's value at `t` divided by the model numeraire, `discounted_ee(t) = E[max(f, 0)]` and `discounted_ene(t) = E[min(f, 0)]`, both in today's money (Gregory 2015). Since `max(f, 0) + min(f, 0) = f`, their sum is the value today of the cash flows after `t`.

**Worked example.** Tutorial 7's 5-year payer at 3.9% on 10 million, Hull-White `a = 3%`, `sigma = 0.5%`, at reset dates 1 to 4: discounted EE 73,697.96, 74,187.68, 59,889.67, 33,616.93 and discounted ENE -61,436.62, -66,020.34, -52,388.32, -29,938.80. At year 1, EE + ENE = 12,261.34, and the forward value 12,261.34 of the last four payments off the curve agrees (scratch log-linear formula, not the library).

That identity is the first test a validator runs on any exposure engine.

### Q9.2 Why is QuantForge's PFE output called `deflated_pfe_95`, and how does it differ from a desk PFE?

*Level: foundation. Evidence: computed; spec; design. Source: [Portfolio exposure spec](../../specifications/06-risk/xva-exposure-portfolio.md), [R6 rulings](../../specifications/r6-rulings.md)*

Potential future exposure is a high quantile of exposure: the amount exceeded only with, say, 5% probability. QuantForge's quantile is taken on the exposure divided by the numeraire, not on the exposure in currency at the future date.

The spec (ruling R6-5.1): `deflated_pfe_q(t)` is the smallest `y >= 0` with `P(max(f, 0) <= y) >= q` under the LGM measure, the quantity ORE's cube holds. It is not a desk PFE (an undeflated quantile in currency under the real-world or `t`-forward measure); the outputs were renamed from `pfe_95` in v0.8.0 for that reason, and an undeflated PFE is not built.

**Worked example.** For the Tutorial 7 payer at one year, deflated_pfe_95 285,775.34, about four times the EE of 73,697.96.

Comparing this number with a limit set on real-world PFE is a units and measure error, not a small discounting difference.

### Q9.3 How does QuantForge compute EPE from an exposure profile?

*Level: foundation. Evidence: computed; spec. Source: [Portfolio exposure spec](../../specifications/06-risk/xva-exposure-portfolio.md), [Tutorial 7](../getting-started/tutorial-7-counterparty.md)*

Expected positive exposure is the time average of the EE profile: one number that summarises how much is at risk over the life.

The spec: `epe = sum_i discounted_ee(t_i)(t_i - t_(i-1)) / t_n` with `t_0 = 0`. In `xva.exposure.collateralised` the same average runs from `t_0` on the input grid.

**Worked example.** With annual dates, the Tutorial 7 EPE is the plain mean of the four EEs: EPE 60,348.06.

The profile is humped: early on rates have had little time to move, late on few payments remain. EPE hides the hump, so a desk reports the profile as well.

### Q9.4 What does netting do to exposure, and how does QuantForge treat different netting sets?

*Level: foundation. Evidence: computed; spec; literature. Source: [xVA framework spec](../../specifications/06-risk/xva-framework.md)*

Trades under one legal netting agreement are closed out as one amount, so positive and negative values offset before the positive part is taken. Across agreements there is no offset.

The spec (ruling G-40): per set, `V_p(t_i)` is the sum of its trades' values on path `p`, and exposure is `max(V - C, 0)`; `total_ee` is the sum of the sets' EE, with no netting across sets.

**Worked example.** Two trades on two paths at 0, 0.5 and 1 year: A is `(0, 4, 6)` and `(0, -3, -5)`, B is `(0, -3, -4)` and `(0, 2, 3)`. In one netting set QuantForge gives netted total_ee 0.00, 0.50, 1.00; in two sets the unnetted total_ee 0.00, 3.00, 4.50.

`max` of a sum is never more than the sum of `max`es, so netting can only reduce exposure; whether a set is enforceable is a legal input, not something the library decides.

### Q9.5 How is CVA computed from the EE profile, and how close is the one-line estimate?

*Level: foundation. Evidence: computed; spec; literature. Source: [Portfolio exposure spec](../../specifications/06-risk/xva-exposure-portfolio.md), [Swap exposure spec](../../specifications/06-risk/xva-exposure.md), [Stage G rulings](../../specifications/stage-g-rulings.md)*

CVA is the expected loss from counterparty default: loss given default times the discounted exposure times the probability of default in each period.

The spec (G-16 buckets): `cva = (1 - R) sum_i discounted_ee(t_i)(e^(-h t_(i-1)) - e^(-h t_i))`; default in `(t_(i-1), t_i]` takes the exposure at `t_i`; default and rates are independent.

**Worked example.** Tutorial 7, `h = 2%`, `R = 40%`: QuantForge gives CVA 2,799.32. The one-line first guess `0.6 x (1 - e^(-0.02)) x sum EE` gives a first guess 2,868: too high, because each later year's default probability is that of surviving to it times 0.0198.

The convention that default takes the bucket-end exposure is a choice; a mid-point or start-point rule gives a different number on a coarse grid.

### Q9.6 What do threshold, minimum transfer amount and margin period of risk do in `xva.exposure.collateralised`?

*Level: foundation. Evidence: computed; golden (`collexp_g-0001`, `-0004`); spec; literature. Source: [xVA framework spec](../../specifications/06-risk/xva-framework.md), [Tutorial 7](../getting-started/tutorial-7-counterparty.md)*

Under a CSA, collateral is called once the value passes a threshold, only in steps of at least the minimum transfer amount (MTA), and after a default it takes some time (the MPoR) to close out, so the collateral held lags the exposure.

The spec (G-40): target `T(V) = max(V - H_r, 0) - max(-V - H_p, 0) + IA`; calls `K_j = T(V_j)` if `|T(V_j) - K_(j-1)| >= MTA`, else `K_(j-1)`; held `C_i = K_(max(i - l, 0))` with `l = mpor_steps`; exposure `max(V - C, 0)`.

**Worked example.** Tutorial 7's four hand-written paths, thresholds 1, MTA 0.5, one-step lag: no CSA EE 0.000, 1.125, 2.750, 3.375, 2.750 against CSA EE 0.000, 1.125, 2.250, 1.625, 1.875. EPE falls from no-CSA EPE 2.50000 to lagged CSA EPE 1.71875.

At 3 months both profiles are equal: the first call is made then but, with a one-step lag, only held from the next date.

### Q9.7 What is DVA, and what happens to it when the bank's own hazard rate is zero?

*Level: foundation. Evidence: computed; golden (`xvaadj_g-0001`, `-0005`); spec; literature. Source: [xVA framework spec](../../specifications/06-risk/xva-framework.md)*

DVA is CVA seen from the other side: the expected value to the bank of its own default, on the trades where it owes the counterparty money.

The spec (ruling G-41): `DVA = (1 - R_b) sum D_i |ene_i| (S_b(t_(i-1)) - S_b(t_i)) S_c(t_(i-1))`, the counterparty alive at the bucket start (first-to-default weighting).

**Worked example.** Golden `xvaadj_g-0001`: four half-year buckets, counterparty hazard 2%, own hazard 1%, both 40% recovery: CVA 2.709862 and DVA 0.899796. With own hazard 0: CVA 2.727866 and DVA 0.0.

DVA is a gain from the bank's own worsening credit, which accounting standards recognise but many desks do not hedge; QuantForge reports it separately so it can be shown or left out.

## Exposure models and adjustments

### Q9.8 Why is the EE of a swap at a reset date a swaption price under Hull-White?

*Level: practitioner. Evidence: computed; golden (`exposure_g-0001`); spec; literature. Source: [Swap exposure spec](../../specifications/06-risk/xva-exposure.md), [Short-rate models spec](../../specifications/04-pricing/short-rate-models.md)*

At a reset date the floating leg is worth par, so the remaining swap is a bond position, and its positive part is exactly the payoff of a European swaption on it. Its discounted expectation is that swaption's price.

The spec: `discounted_ee(t) = E[D(0,t) max(V(t), 0)]`, the price of the European swaption expiring at `t` on the remaining swap (payer for `PAY`), by Jamshidian; `exposure_times` must be reset dates before the last payment, else `E_INPUT`.

**Worked example.** Golden `exposure_g-0001`, a 5-year payer at 3% on 10 million, `a = 5%`, `sigma = 1%`: Jamshidian EE 352,680.98, 285,620.69, 204,079.27, 107,026.77 and, with `h = 2%`, `R = 40%`, cva 11,043.40.

This closed form is the anchor for the simulated engine: the portfolio integral and ORE must reproduce it (Q9.19).

### Q9.9 What does PAY minus RECEIVE EE equal at each date, and why is it a good test?

*Level: practitioner. Evidence: computed; spec. Source: [Swap exposure spec](../../specifications/06-risk/xva-exposure.md)*

A payer's positive part minus a receiver's positive part is the payer's value itself, as payer minus receiver swaption equals the forward swap.

The spec asserts, as a property test in every language, that `PAY` minus `RECEIVE` EE at each date equals the deterministic forward value of the remaining swap, to 1e-6 on 1e7 notional.

**Worked example.** For the swap of Q9.8 at year 1, the receiver EE at 1 year 25,681.56, so PAY minus RECEIVE 326,999.42, and the forward value of the remaining swap 326,999.42, computed from the curve with log-linear discount factors (scratch formula, not the library).

The spec's caught wrong convention is "a receiver swaption for a pay-fixed swap"; parity catches it immediately.

### Q9.10 What is effective EPE, and why is it at least EPE?

*Level: practitioner. Evidence: computed; golden (`collexp_g-0005`); spec; literature. Source: [xVA framework spec](../../specifications/06-risk/xva-framework.md)*

Regulatory exposure assumes maturing trades are replaced, so it never lets the EE profile fall within the first year.

The spec (Basel CRE53): `eee_i = max(eee_(i-1), ee_i)` with `eee_0 = ee_0`, then the time average over grid points within one year of `t_0`.

**Worked example.** Tutorial 7's paths under a CSA with no lag (golden `collexp_g-0005`): EE `(0, 0.625, 0.5, 0.75, 0.5)`, so EPE 0.59375 but effective EPE 0.68750, because the running maximum keeps 0.625 and then 0.75.

Effective EPE is a capital input; using it in CVA would overstate the price.

### Q9.11 How is FVA split into FCA and FBA, and what is the DVA overlap?

*Level: practitioner. Evidence: computed; golden (`xvaadj_g-0001`, `-0002`); spec; literature. Source: [xVA framework spec](../../specifications/06-risk/xva-framework.md), [Stage G rulings](../../specifications/stage-g-rulings.md)*

An uncollateralised in-the-money trade must be funded at the bank's borrowing spread (a cost); an out-of-the-money one provides funding (a benefit). Part of that benefit is the bank's own credit spread, which DVA already counts.

The spec (G-41): `FCA = s_b sum D_i ee_i S_c S_b(t_(i-1)) dt_i`, `FBA = s_l sum D_i |ene_i| S_c S_b(t_(i-1)) dt_i`, `FVA = FCA - FBA`. With `exclude_dva_overlap`, `s_l` becomes `max(s_l - h_b (1 - R_b), 0)`.

**Worked example.** Golden `xvaadj_g-0001`, spreads 0.8%: FCA 1.815622, FBA 1.202730, FVA 0.612893. Excluding the overlap (own `h_b = 1%`, `R_b = 40%`) leaves a 0.2% lending spread: FBA falls to 0.300682 and FVA rises to 1.514940.

Which convention to use is a policy decision; reporting DVA and full FBA together counts the bank's own credit twice.

### Q9.12 Why does CVA fall slightly when the bank's own default risk is added?

*Level: practitioner. Evidence: computed; golden (`xvaadj_g-0001`, `-0005`); spec; literature. Source: [xVA framework spec](../../specifications/06-risk/xva-framework.md)*

If the bank defaults first, the counterparty's later default no longer costs it anything. Bilateral CVA therefore weights each bucket by the chance that both are still alive at its start.

The spec: `CVA = (1 - R_c) sum D_i ee_i (S_c(t_(i-1)) - S_c(t_i)) S_b(t_(i-1))`, the first-to-default weighting of Brigo, Morini and Pallavicini (2013).

**Worked example.** Same inputs as Q9.7: with own hazard 1%, CVA 2.709862; with own hazard 0, own hazard 0: CVA 2.727866, the unilateral value.

The effect is small at low hazard rates but grows with the bank's own spread; a unilateral CVA (own hazard 0) is what Tutorial 7 uses.

### Q9.13 How is the PFE quantile chosen on a small number of paths?

*Level: practitioner. Evidence: computed; golden (`collexp_g-0001`); spec. Source: [xVA framework spec](../../specifications/06-risk/xva-framework.md), [VaR, ES and backtests spec](../../specifications/06-risk/var-es-and-backtests.md)*

The quantile is read off the sorted path exposures with no interpolation, the same rule QuantForge uses for historical VaR.

The spec: `pfe_i` is the `ceil(q P)`-th smallest exposure (inverted-CDF rule of stage F), `q` in `(0, 1]`.

**Worked example.** No CSA, four paths, `q = 0.75`, at 0.75 years the exposures are 2, 0, 9 and 2.5. Sorted, the `ceil(3) = 3`rd is the PFE at 0.75 years 2.500.

On a few thousand paths a 99% quantile rests on a handful of scenarios; that is the instability that sinks some ORE comparisons (Q9.19).

### Q9.14 How do the lag and the thresholds change collateralised EPE?

*Level: practitioner. Evidence: computed; golden (`collexp_g-0001`, `-0004`, `-0005`, `-0007`); spec. Source: [xVA framework spec](../../specifications/06-risk/xva-framework.md)*

Collateral removes exposure above the threshold, but the lag lets the value move away from the collateral before close-out. Removing the lag and the thresholds removes the exposure.

The spec's limit case: zero thresholds, MTA 0 and no lag give exposure 0 (asserted in the oracle).

**Worked example.** Tutorial 7's four paths: no-CSA EPE 2.50000; CSA with thresholds 1, MTA 0.5 and a one-step lag, lagged CSA EPE 1.71875; same CSA with no lag, no-lag EPE 0.59375; zero thresholds and no lag, zero-threshold EPE 0.00000.

The MPoR is usually the largest driver once thresholds are small; a quarterly grid with a one-step lag is a coarse stand-in for a 10-day MPoR.

### Q9.15 How much CVA does the collateral agreement of Tutorial 7 save?

*Level: practitioner. Evidence: computed; spec. Source: [xVA framework spec](../../specifications/06-risk/xva-framework.md), [Tutorial 7](../getting-started/tutorial-7-counterparty.md)*

CVA is linear in EE, so lower EE under a CSA gives lower CVA with the same counterparty credit.

The spec: `xva.adjustments.value` takes the EE profile with discount factors and survival curves; with own hazard 0 it is the unilateral CVA.

**Worked example.** Counterparty hazard 2%, recovery 40%, flat 3% continuous discounting, on the EE profiles of Q9.6: no-CSA CVA 0.029052 and CSA CVA 0.020013, about 31% less.

The saving is not 100%: with thresholds and a lag the residual exposure is real, and a desk prices it.

## Advanced

### Q9.16 How does QuantForge model wrong-way risk, and what does it do to CVA?

*Level: advanced. Evidence: computed; golden (`wwr_g-0001` to `-0004`); spec; literature. Source: [xVA framework spec](../../specifications/06-risk/xva-framework.md), [Stage G rulings](../../specifications/stage-g-rulings.md)*

Wrong-way risk is when the counterparty becomes more likely to default exactly when you are owed more. Hull and White link the hazard rate to the exposure on each path.

The spec (ruling G-44): on path `p` the hazard in bucket `i` is `exp(a_i + b V_p(t_i))`; `a_i` solves `mean_p S_p(t_i) = e^(-h t_i)` so the average survival still matches the market; `CVA = (1 - R) sum D_i mean_p[max(V_p(t_i), 0)(S_p(t_(i-1)) - S_p(t_i))]`.

**Worked example.** Tutorial 7's four paths, `h = 3%`, `R = 40%`: b = 0: CVA 0.043628 (equal to the independent CVA, asserted), b = 0.1: CVA 0.061148, b = 0.3: CVA 0.086487 (wrong way), b = -0.2: CVA 0.015569 (right way).

The calibration of `b` is not provided: it is an input, and with four paths the example is a mechanism check, not a calibrated estimate.

### Q9.17 How does the sensitivity-based IR delta margin aggregate, and what does the concentration factor do?

*Level: advanced. Evidence: computed; golden (`sbim_g-0001`, `-0002`); spec; literature. Source: [xVA framework spec](../../specifications/06-risk/xva-framework.md), [Tutorial 15](../getting-started/tutorial-15-advanced-risk.md)*

Initial margin weights each sensitivity, scales it up when the net position is large relative to a concentration threshold, and aggregates with correlations.

The spec (G-43): `CR = max(1, sqrt(|sum s_k| / T))`, `WS_k = RW_k s_k CR`, `margin = sqrt(max(0, sum sum rho WS WS))`. Weights and correlations are inputs; the operation is `xva.sbim.ir_delta` (the old id `xva.simm.ir_delta` is a deprecated alias until v1.0.0, KR-152). This is a project definition, not an industry margin model; no ISDA material is used (owner decision 2026-11-19; [why](../model-inventory.md#why-there-is-no-isda-simm-here)).

**Worked example**, on placeholder weights (KR-150: risk weight `10 k` for tenor index `k`, correlation `1 - 0.1 |k - l|`). One sensitivity of 10,000 at the 2-year point, risk weight 30: margin 300,000.00. Lower the threshold to 2,500 and concentration_factor 2.000000, so the margin rises to 600,000.00. Tutorial 15's six-tenor mixed-sign book gives the mixed-sign margin 190,937.16. Releases v0.7.0 to v0.10.0 printed other numbers here, from hand-typed weights whose origin was not documented.

QuantForge's stage G operation has the single-bucket IR delta only: no vega, curvature or other risk classes, and no official parameters of any industry model.

### Q9.18 How are MVA and KVA defined in `xva.adjustments.value`?

*Level: advanced. Evidence: computed; golden (`xvaadj_g-0003`, `-0004`); spec; literature. Source: [xVA framework spec](../../specifications/06-risk/xva-framework.md)*

MVA is the cost of funding the initial margin a trade requires; KVA is the cost of holding regulatory capital against it at a hurdle rate. Both are profiles discounted and survival-weighted like FCA.

The spec (Green and Kenyon 2014, 2015): `MVA = s_IM sum D_i IM_i S_c S_b dt_i`, `KVA = hurdle sum D_i capital_i S_c S_b dt_i`; `im` with `im_spread`, `capital` with `hurdle_rate`, each pair together, else `E_INPUT`.

**Worked example.** On the buckets of Q9.7, an IM profile `(200, 210, 190, 150)` at a 0.6% spread gives MVA 2.125651; a capital profile `(40, 42, 38, 30)` at a 10% hurdle gives KVA 7.085503.

QuantForge takes the IM and capital profiles as inputs; projecting future initial margin or SA-CCR along paths is not implemented.

### Q9.19 How was the portfolio exposure engine checked against ORE, and why do some cases not count?

*Level: advanced. Evidence: spec; design. Source: [Portfolio exposure spec](../../specifications/06-risk/xva-exposure-portfolio.md), [Stage G rulings](../../specifications/stage-g-rulings.md)*

QuantForge integrates the one-factor exposure exactly; ORE simulates paths and revalues each trade. If both are right, ORE's averages sit within a few Monte Carlo standard errors of QuantForge's numbers.

The spec (ruling G-42): six ORE 1.8.17 runs over `a` in {0.03, 0.10} and `sigma` in {0.005, 0.01, 0.015}, 5,000 samples each; a case counts when every check lies within `max(3, z_Bonf)` standard errors at a family-wise 1%. The rule was registered before the runs were read.

**Result as recorded.** 80 of the 96 value cases count. The 16 others fail one check each, 15 on the 99% quantile of long payer exposures, where the deflated value has a flat top so a 0.1% value difference moves the empirical CDF by many standard errors, and 1 on a zero standard error in a far tail. Their EE, ENE, EPE and CVA checks pass. The rule was kept as registered; an amendment is left to the owner.

No number here is recomputed by the verify script: this is a recorded validation result, and keeping a rule after seeing its failures is the point.

### Q9.20 How much does netting a payer with a receiver reduce CVA in the Hull-White portfolio engine?

*Level: advanced. Evidence: computed; spec. Source: [Portfolio exposure spec](../../specifications/06-risk/xva-exposure-portfolio.md), [Tutorial 7](../getting-started/tutorial-7-counterparty.md)*

Under a one-factor model the netting set's value at a date is a function of one Gaussian number, so EE, ENE and quantiles of any portfolio of swaps with common reset dates are exact one-dimensional integrals.

The spec: `f(x) = sum_trades sgn N (1 - P(t, T_n, x) - K sum tau_i P(t, T_i, x)) / N(t, x)`; integrals split at every zero of `f`, found on at least 6,001 points over `[-12, 12]` standard deviations (R6-5.5).

**Worked example.** Tutorial 7's payer (3.9% on 10 million) and a receiver of 3.5% on 5 million, same dates and model: payer alone CVA 2,799.32, receiver alone CVA 506.50, netted CVA 608.09. The netted EE at 1 year 11,025.70 and netted ENE at 1 year -74,836.82 give EE + ENE -63,811.12, equal to the sum of the two trades' EE + ENE -63,811.12: values add, exposures do not.

All trades must share reset dates (else `E_INPUT`); mixed-frequency portfolios need the simulated route, which QuantForge leaves to ORE.
