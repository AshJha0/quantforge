# Tolerances in money

Written by `conformance/tolerances/money_table.py`. Every tolerance in `policy.yaml`, and every per-case `tolerance_limit` in use, restated as money on a
10,000,000 notional, so a desk can judge it. The comparison is `|a - e| <= absolute + relative x max(|a|, |e|)`.

Reference instruments, read from the goldens (`ois_d-0022`, `bonds_d-0009`, `ois_d-0005`, `credit_d-0004`):
- rate: 10Y SOFR OIS, annuity 8.3569, so DV01 on 10m = 8,357;
- price per 100 face: 2036 4.5% bond at 4.10%, DV01 per 100 = 0.08133, or 8,133 on 10m face; a Treasury tick is 1/32;
- discount factor: a cash flow of 10m at the 10Y SOFR pillar, D = 0.685839, t = 10.0274;
- CDS: 5Y IG trade, rpv01 4.6294, so 1 bp of spread is 4,629 on 10m.

How to read a row: the same tolerance applied to three kinds of output. Columns give the money error on 10m it allows, and the same error in
basis points of the instrument's DV01 or in price ticks. Every class allows far less than 1/100 of a bp, and far less than 1 currency unit, on these trades.

| Class or limit | absolute | relative | Rate output near 4%: bp, money on the 10Y swap | Price per 100: money on 10m face, 32nds, bp of DV01 | 10Y discount factor: money on a 10m flow, bp | Note |
|---|---|---|---|---|---|---|
| `date_and_convention` | - | - | - | - | - | exact |
| `bit_exact` | - | - | - | - | - | exact |
| `simple_analytic` | 1e-12 | 1e-10 | 5.0e-08 bp, 4.18e-04 | 1.04e-03, 3.3e-07 ticks, 1.3e-07 bp | 6.96e-04, 1.0e-07 bp |  |
| `interpolation` | 1e-10 | 1e-08 | 5.0e-06 bp, 4.18e-02 | 1.04e-01, 3.3e-05 ticks, 1.3e-05 bp | 6.96e-02, 1.0e-05 bp |  |
| `root_finding` | 1e-10 | 1e-10 | 1.0e-06 bp, 8.69e-03 | 1.05e-03, 3.4e-07 ticks, 1.3e-07 bp | 1.69e-03, 2.5e-07 bp |  |
| `quadrature` | 1e-11 | 1e-10 | 1.4e-07 bp, 1.17e-03 | 1.04e-03, 3.3e-07 ticks, 1.3e-07 bp | 7.86e-04, 1.1e-07 bp |  |
| `statistics` | 1e-11 | 1e-10 | 1.4e-07 bp, 1.17e-03 | 1.04e-03, 3.3e-07 ticks, 1.3e-07 bp | 7.86e-04, 1.1e-07 bp |  |
| `numerical_scheme` | 1e-08 | 1e-08 | 1.0e-04 bp, 8.69e-01 | 1.05e-01, 3.4e-05 ticks, 1.3e-05 bp | 1.69e-01, 2.5e-05 bp |  |
| `fourier` | 1e-09 | 1e-09 | 1.0e-05 bp, 8.69e-02 | 1.05e-02, 3.4e-06 ticks, 1.3e-06 bp | 1.69e-02, 2.5e-06 bp |  |
| `common_rng` | 1e-09 | 1e-09 | 1.0e-05 bp, 8.69e-02 | 1.05e-02, 3.4e-06 ticks, 1.3e-06 bp | 1.69e-02, 2.5e-06 bp |  |
| `calibration` | - | - | - | - | - | judged per case: judged_on=repricing_error, per_case_target_required=True |
| `monte_carlo` | - | - | - | - | - | judged per case: method=confidence interval against the oracle value, common_rng_spec=specifications/01-core/rng.md |

## Per-case limits in use

A case may set its own `tolerance_limit`. Limits stated per unit of notional are scaled to the case's notional when the golden is written, so on a
10m notional the money column is what the limit means. The rows below apply each limit, as written, to the same outputs as above.

| Limit | absolute | relative | Rate output near 4% | Price per 100 | 10Y discount factor | Cases, and the reason given |
|---|---|---|---|---|---|---|
| case limit | 1e-09 | 0e+00 | 1.0e-05 bp, 8.36e-02 | 1.00e-04, 3.2e-08 ticks, 1.2e-08 bp | 1.00e-02, 1.5e-06 bp | 83: tol is 1e-10; the error estimate is not a bound |
| case limit | 1e-12 | 0e+00 | 1.0e-08 bp, 8.36e-05 | 1.00e-07, 3.2e-11 ticks, 1.2e-11 bp | 1.00e-05, 1.5e-09 bp | 67: stage-d-targets: exact-rational compounding; only the final division rounds |
| case limit | 1e-03 | 1e-09 | currency output: 1.10e-03 on a PV of 1e5, 1.3e-07 bp of the 10Y swap DV01 | - | - | 62: 1e-9 per unit of notional on 1e6: the curve solve's tolerance carried through |
| case limit | 1e-02 | 1e-09 | currency output: 1.01e-02 on a PV of 1e5, 1.2e-06 bp of the 10Y swap DV01 | - | - | 42: curve tolerance on notional |
| case limit | 1e-04 | 1e-06 | currency output: 1.00e-01 on a PV of 1e5, 1.2e-05 bp of the 10Y swap DV01 | - | - | 21: volga divides rounding of about 1e-15 by a bump squared |
| case limit | 1e-08 | 0e+00 | 1.0e-04 bp, 8.36e-01 | 1.00e-03, 3.2e-07 ticks, 1.2e-07 bp | 1.00e-01, 1.5e-05 bp | 20: rounding over 10^7 additions; the rule's own error is far below this |
| case limit | 1e-06 | 0e+00 | currency output: 1.00e-06 on a PV of 1e5, 1.2e-10 bp of the 10Y swap DV01 | - | - | 18: solver stops by its own test; judged on objective and a unique minimiser |
| case limit | 1e-10 | 1e-10 | 1.0e-06 bp, 8.69e-03 | 1.05e-03, 3.4e-07 ticks, 1.3e-07 bp | 1.69e-03, 2.5e-07 bp | 10: strike came through Ninv |
| case limit | 1e-03 | 1e-08 | currency output: 2.00e-03 on a PV of 1e5, 2.4e-07 bp of the 10Y swap DV01 | - | - | 9: difference of two curve solves on 1e6, each good to 1e-13 in rate |
| case limit | 1e-09 | 1e-10 | 1.0e-05 bp, 8.39e-02 | 1.14e-03, 3.7e-07 ticks, 1.4e-07 bp | 1.07e-02, 1.6e-06 bp | 9: normal vol in price units |
| case limit | 1e-10 | 0e+00 | 1.0e-06 bp, 8.36e-03 | 1.00e-05, 3.2e-09 ticks, 1.2e-09 bp | 1.00e-03, 1.5e-07 bp | 8: repricing, not parameters: Nelson-Siegel is poorly identified |
| case limit | 3e-02 | 1e-09 | currency output: 2.51e-02 on a PV of 1e5, 3.0e-06 bp of the 10Y swap DV01 | - | - | 6: curve tolerance on notional |
| case limit | 1e-10 | 1e-08 | 5.0e-06 bp, 4.18e-02 | 1.04e-01, 3.3e-05 ticks, 1.3e-05 bp | 6.96e-02, 1.0e-05 bp | 4: linear solve; condition number up to about 1e3 |
| case limit | 1e-04 | 0e+00 | currency output: 1.00e-04 on a PV of 1e5, 1.2e-08 bp of the 10Y swap DV01 | - | - | 3: f underflows to rounding noise within about 1e-5 of a triple root |
| case limit | 1e-05 | 1e-06 | currency output: 1.00e-01 on a PV of 1e5, 1.2e-05 bp of the 10Y swap DV01 | - | - | 3: second difference: rounding of 1e-16 over h squared |
| case limit | 5e-02 | 1e-09 | currency output: 5.01e-02 on a PV of 1e5, 6.0e-06 bp of the 10Y swap DV01 | - | - | 3: curve tolerance on notional |
| case limit | 1e-05 | 0e+00 | currency output: 1.00e-05 on a PV of 1e5, 1.2e-09 bp of the 10Y swap DV01 | - | - | 2: gradient test at 1e-8 |
| case limit | 1e-07 | 0e+00 | 1.0e-03 bp, 8.36e+00 | 1.00e-02, 3.2e-06 ticks, 1.2e-06 bp | 1.00e+00, 1.5e-04 bp | 2: basis in bp |
| case limit | 2e-02 | 1e-09 | currency output: 2.01e-02 on a PV of 1e5, 2.4e-06 bp of the 10Y swap DV01 | - | - | 2: curve tolerance on notional |
| case limit | 5e-03 | 1e-09 | currency output: 5.10e-03 on a PV of 1e5, 6.1e-07 bp of the 10Y swap DV01 | - | - | 2: ISDA replay against QuantLib within 2e-10 per unit |
| case limit | 8e-03 | 1e-09 | currency output: 7.60e-03 on a PV of 1e5, 9.1e-07 bp of the 10Y swap DV01 | - | - | 2: 1e-9 per unit of notional on 1e6: the curve solve's tolerance carried through |
| case limit | 1e-09 | 0e+00 | 9.7e-06 bp, 8.07e-02 | 9.66e-05, 3.1e-08 ticks, 1.2e-08 bp | 9.66e-03, 1.4e-06 bp | 1: rounding bound in differentiation-and-linalg.md; any correct form of f passes |
| case limit | 4e-06 | 0e+00 | currency output: 3.86e-06 on a PV of 1e5, 4.6e-10 bp of the 10Y swap DV01 | - | - | 1: rounding bound in differentiation-and-linalg.md; any correct form of f passes |
| case limit | 2e-10 | 0e+00 | 2.1e-06 bp, 1.75e-02 | 2.10e-05, 6.7e-09 ticks, 2.6e-09 bp | 2.10e-03, 3.0e-07 bp | 1: rounding bound in differentiation-and-linalg.md; any correct form of f passes |
| case limit | 8e-07 | 0e+00 | 8.4e-03 bp, 7.00e+01 | 8.38e-02, 2.7e-05 ticks, 1.0e-05 bp | 8.38e+00, 1.2e-03 bp | 1: rounding bound in differentiation-and-linalg.md; any correct form of f passes |
| case limit | 3e-09 | 0e+00 | 3.2e-05 bp, 2.70e-01 | 3.23e-04, 1.0e-07 ticks, 4.0e-08 bp | 3.23e-02, 4.7e-06 bp | 1: rounding bound in differentiation-and-linalg.md; any correct form of f passes |
| case limit | 1e-05 | 0e+00 | currency output: 1.29e-05 on a PV of 1e5, 1.5e-09 bp of the 10Y swap DV01 | - | - | 1: rounding bound in differentiation-and-linalg.md; any correct form of f passes |
| case limit | 8e-11 | 0e+00 | 7.6e-07 bp, 6.34e-03 | 7.59e-06, 2.4e-09 ticks, 9.3e-10 bp | 7.59e-04, 1.1e-07 bp | 1: rounding bound in differentiation-and-linalg.md; any correct form of f passes |
| case limit | 3e-07 | 0e+00 | 3.0e-03 bp, 2.54e+01 | 3.04e-02, 9.7e-06 ticks, 3.7e-06 bp | 3.04e+00, 4.4e-04 bp | 1: rounding bound in differentiation-and-linalg.md; any correct form of f passes |
| case limit | 2e-06 | 0e+00 | currency output: 2.00e-06 on a PV of 1e5, 2.4e-10 bp of the 10Y swap DV01 | - | - | 1: x_tol is 1e-6 |
| case limit | 1e-03 | 0e+00 | currency output: 1.00e-03 on a PV of 1e5, 1.2e-07 bp of the 10Y swap DV01 | - | - | 1: asymmetry of 1e-7 is inside the rule; which triangle is read is free |
| case limit | 0e+00 | 1e-13 | 4.0e-11 bp, 3.34e-07 | 1.04e-06, 3.3e-10 ticks, 1.3e-10 bp | 6.86e-07, 1.0e-10 bp | 1: tail values near 1e-300: relative accuracy is the point |
| case limit | 1e-05 | 1e-04 | currency output: 1.00e+01 on a PV of 1e5, 1.2e-03 bp of the 10Y swap DV01 | - | - | 1: analytic or bumped Jacobians both pass; bump error is about 1e-7 |
| case limit | 1e-02 | 1e-06 | currency output: 1.10e-01 on a PV of 1e5, 1.3e-05 bp of the 10Y swap DV01 | - | - | 1: bumped solves on 1e7 notional |
| case limit | 2e-04 | 0e+00 | currency output: 2.00e-04 on a PV of 1e5, 2.4e-08 bp of the 10Y swap DV01 | - | - | 1: noisy fit: flat directions in the minimum; rmse itself is held by the extra check |
| case limit | 1e-07 | 1e-08 | 1.0e-03 bp, 8.39e+00 | 1.14e-01, 3.7e-05 ticks, 1.4e-05 bp | 1.07e+00, 1.6e-04 bp | 1: central difference over 2e-4 of prices near 100 |
| case limit | 2e-03 | 1e-07 | currency output: 1.20e-02 on a PV of 1e5, 1.4e-06 bp of the 10Y swap DV01 | - | - | 1: SVI fit on quotes: 1e-6 in parameters carried through vega near 1400 by quantity 3 |
| case limit | 1e-03 | 1e-10 | currency output: 1.01e-03 on a PV of 1e5, 1.2e-07 bp of the 10Y swap DV01 | - | - | 1: 360 months of products; errors grow with length |
| case limit | 3e-03 | 1e-10 | currency output: 2.51e-03 on a PV of 1e5, 3.0e-07 bp of the 10Y swap DV01 | - | - | 1: 360 months of products; errors grow with length |
| case limit | 5e-04 | 1e-10 | currency output: 5.10e-04 on a PV of 1e5, 6.1e-08 bp of the 10Y swap DV01 | - | - | 1: 360 months of products; errors grow with length |

## Notional-scaled PV limits

PV outputs in currency use `absolute = 1e-9 x notional` (ruling D60 and the stage B and D targets). On 10m that is 0.01 currency units,
or 1.2e-06 bp of the 10Y swap's DV01. CDS PVs use 0.01 absolute plus 1e-9 relative: on 10m that is at most 0.02, or 4.3e-06 bp of spread.
