# FRTB standardised approach: GIRR delta

Spec version 1.0.0. Status: Specified (stage F, slice F4, plan item Q2 "FRTB-SA SBM"). Ruling: `stage-f-rulings.md` F-33. Suite `stage_f/frtb_f`, written by `oracle/python/gen_stage_f_w2.py` (slice `F4`).

**Plain idea.** Under the Basel market risk standard, a bank's capital for interest rate moves is not a model's VaR but a fixed recipe: weight each sensitivity by a regulator's risk weight, add them up within a currency allowing for correlation between tenors, then across currencies, and do it three times with correlations scaled up, as given, and down. The capital is the worst of the three. This page implements that recipe for general interest rate risk (GIRR) delta, the largest piece for a rates book.

All parameters are from the Basel Framework chapter MAR21 (in force 1 January 2023, page version of 23 March 2026) [S1]. Paragraph numbers are given with each one.

## `risk.frtb.girr_delta`

### Inputs

- `sensitivities`: at least one, else `E_INPUT`. Each is `{currency, curve, risk_factor, sensitivity}`. `risk_factor` is a tenor (`0.25Y`, `0.5Y`, `1Y`, `2Y`, `3Y`, `5Y`, `10Y`, `15Y`, `20Y`, `30Y`), `INFLATION` or `XCCY_BASIS`; another value is `E_SCHEMA`. `sensitivity` is the delta sensitivity `s_k` of MAR21 in money (value change for a 1 bp rise, divided by 0.0001), computed by the caller. The same (`currency`, `curve`, `risk_factor`) twice is `E_INPUT`.
- `specified_currency_reduction` (default `false`) and `reporting_currency` (optional).

### Recipe

- **Buckets:** one per currency (MAR21, GIRR buckets).
- **Risk weights (MAR21.42 Table 1):** 1.7% at 0.25Y and 0.5Y, 1.6% at 1Y, 1.3% at 2Y, 1.2% at 3Y, 1.1% from 5Y to 30Y. Inflation and cross-currency basis: 1.6% (MAR21.43). With `specified_currency_reduction`, weights for EUR, USD, GBP, AUD, JPY, SEK, CAD and the `reporting_currency` are divided by `sqrt(2)` (MAR21.44 and its footnote); the reduction applies to every weight above, inflation and cross-currency basis included (R6-28.4). `WS_k = RW_k s_k`.
- **Correlation within a bucket:**
  - Same curve, tenors `T_k`, `T_l` in years: `rho = max(exp(-theta |T_k - T_l| / min(T_k, T_l)), 40%)`, `theta = 3%` (MAR21.46 and footnote 13). Ruling F-33: the formula sits in an image on the BIS page; it is confirmed against Table 2 of MAR21.46, whose printed values it reproduces (for example 97.0% for 0.25Y against 0.5Y, 91.4% against 1Y, and the 40.0% floor).
  - Different curves: the same-curve value times 99.9% (MAR21.45, MAR21.47); same tenor on two curves is 99.9%.
  - Inflation against a tenor: 40% (MAR21.48). Inflation against inflation on another curve of the same currency: 99.9% (the FAQ to MAR21.47).
  - Cross-currency basis against anything else, including another basis: 0% (MAR21.49).
- **Correlation across buckets:** `gamma = 50%` (MAR21.50).
- **Aggregation (MAR21.4):** `K_b = sqrt(max(0, sum_k WS_k^2 + sum_{k != l} rho_kl WS_k WS_l))`, `S_b = sum_k WS_k`, `Delta = sqrt(sum_b K_b^2 + sum_{b != c} gamma S_b S_c)`. If the sum under that root is negative, it is recomputed with `S_b = max(min(sum_k WS_k, K_b), -K_b)` (MAR21.4(5)(b)) and, if still negative, floored at 0.
- **Correlation scenarios (MAR21.6):** `medium` uses the values above; `high` uses `min(1.25 x, 100%)` for every `rho` and `gamma`; `low` uses `max(2 x - 100%, 75% x)`. The class capital reported here is the largest of the three for this class alone. Ties go to the first of `high`, `medium`, `low`. This is not the MAR21.7 total: MAR21.7 adds the delta, vega and curvature charges of every risk class within one scenario first and only then takes the largest scenario. Adding the `capital` outputs of several class operations overstates the total whenever their binding scenarios differ (review finding 12); use `risk.frtb.sbm_total` below (ruling R6-4.1).

### Outputs

- `scenarios`: for each of `high`, `medium`, `low`: `buckets` (`[{currency, k, s, s_used}]`, currencies in ascending code order), `delta`, `alternative_used` (boolean).
- `capital` and `binding_scenario`.

Class `simple_analytic`; `binding_scenario` and `alternative_used` exact.

## Convergence and limit cases

| Method | Asserted order | Measured on | Limit case | Reference |
|---|---|---|---|---|
| SBM aggregation | closed form, no iteration | none | one tenor: `capital = RW |s|` in every scenario (`high` binds by the tie rule) | `frtb_f-0001` |
| Alternative `S_b` | closed form | none | two offsetting buckets of uncorrelated basis factors: the alternative `S_b` is used in all three scenarios | `frtb_f` "alternative S_b" case |
| Tenor correlation | closed form | none | reproduces the printed MAR21.46 Table 2 (97.0% for 0.25Y against 0.5Y, the 40% floor) | MAR21.46 |

## Acceptance

- Every case of `frtb_f` passes in all four languages.
- No outside oracle: MAR21 and MAR23 contain no numeric worked example (checked on the BIS pages, 2026-11-10), and no free library implements the SBM with these parameters. The suite does not count toward the 60% floor (known issue).
- The `low` scenario formula is an image on the BIS page and is not in its text. It was confirmed by the owner on 2026-11-10 against the MAR21.6 formula images (BIS page of 2026-03-23): rho_low = max(2 x rho - 100%; 75% x rho) and gamma_low = max(2 x gamma - 100%; 75% x gamma) (ruling F-33).
- Vega, curvature, the other risk classes (CSR, equity, commodity, FX), the default risk charge and the residual risk add-on are not in stage F. The equity risk weights and correlations (MAR21.77 to MAR21.80) were read only in summary and need checking against the PDF before an equity slice uses them.

## Sources

- [S1] Basel Committee on Banking Supervision, *Basel Framework*, chapter MAR21 "Standardised approach: sensitivities-based method", in force 1 January 2023, page version published 23 March 2026, bis.org (MAR21.4, MAR21.6, MAR21.7 and MAR21.42 to MAR21.50 read; formulas in images)
- [S2] Basel Committee on Banking Supervision, *Minimum capital requirements for market risk*, January 2019 (d457), the text MAR21 consolidates (not opened)

## `risk.frtb.sbm_total` (ruling R6-4.1, MAR21.7)

**Plain idea.** Each class operation gives three charges, one per correlation scenario. The total is the sum of every class's charge within the same scenario, and then the worst scenario. Taking each class's own worst scenario and adding those is larger whenever the classes disagree on which scenario is worst.

Inputs: `components`, at least one (else `E_INPUT`): each `{risk_class, measure, scenarios: {high, medium, low}}`. `risk_class` is one of `GIRR`, `CSR_NONSEC`, `EQ`, `COMM`, `FX`; `measure` is one of `DELTA`, `VEGA`, `CURVATURE`; any other value, or a missing scenario key, is `E_SCHEMA`. Each scenario charge is the matching output of the class operation (`scenarios.<s>.delta`, `.vega` or `.curvature`). A charge below 0 is `E_DOMAIN` (after the finite rule F-2). The same (`risk_class`, `measure`) twice is `E_INPUT`.

Outputs: `scenario_totals` (`{high, medium, low}`, each the sum over components), `capital` (the largest total), `binding_scenario` (ties to the first of `high`, `medium`, `low`), and `sum_of_component_capitals` (the sum of each component's own largest charge, the overstated figure, reported so the difference is visible).

Class `simple_analytic`; `binding_scenario` exact. Suite `r6/sbm_total_r6` (`oracle/python/gen_r6_w1.py`): hand cases, and one built from the oracle outputs of `frtb_f-0003` (GIRR, binds `high`) and `frtb_f2b-0002` (FX, binds `low`), whose total is strictly below the sum of the two class capitals.

Not built (stated in README, ROADMAP and the model inventory): the default risk charge (MAR22), the residual risk add-on (MAR23.8) and CSR securitisation classes; `sbm_total` is the sensitivities-based method only, not the full standardised approach. Source: MAR21.7 (BIS Basel Framework page as cited in [S1]; read 2026-11-10 by the stage F session, not re-opened in R6).
