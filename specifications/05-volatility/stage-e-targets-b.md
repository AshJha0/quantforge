# Stage E numeric targets, spec B

Spec version 1.0.0. One table per slice, added as each slice lands. Tolerances are stated in money where an output is money, and every class has its reason; `conformance/tolerances/policy.yaml` gives the base classes, and a case's `tolerance_limit` overrides them for its outputs.

## E7 GARCH, variance swaps, VIX

| Suite | Operation | Cases (ok / error) | Tolerance | In money | Oracle |
|---|---|---|---|---|---|
| `garch_e` | `vol.garch.loglik` | 9 / 7 | `loglik` class `likelihood_sum` (1e-9 abs + 1e-10 rel), `statistics` on short series; variances 1e-16 abs + 1e-11 rel | n/a (a likelihood) | mpmath-50 replica; float replay; hand case `garch_e-0009` |
| `garch_e` | `vol.garch.forecast` | 6 / 4 | 1e-16 abs + 1e-11 rel on variances | under 1e-9 in annualised vol: under 0.01 currency of vega on 10m vega notional | mpmath-50; float replay |
| `garch_e` | `vol.garch.fit` | 2 / 1 | `loglik` within 1e-6 abs (class `root_finding` with limit, E-B16) | a 5% `omega` error costs more (checked) | multi-start Nelder-Mead, 50-digit Newton polish, gradient and Hessian checked |
| `varswap_e` | `vol.varswap.fair_strike` | 20 / 9 | variance and vol 1e-12 abs + 1e-10 rel; `pv` 1e-12 per unit variance notional + 1e-10 rel | 1e-6 currency on `N_var = 1e6` | mpmath-50; all 18 `q = 0` cases outside-checked by QuantLib `ReplicatingVarianceSwapEngine` (`oracle/outside_register_e_b.json`) |
| `varswap_e` | `vol.varswap.realized` | 2 / 2 | variance and vol 1e-12 abs + 1e-10 rel; `payoff` 1e-12 per unit notional | 1e-6 currency per 1e6 | hand case `varswap_e-0030`; mpmath-50 |
| `vix_e` | `vol.vix.term_variance` | 8 / 8 | 1e-12 abs + 1e-10 rel on variance | under 1e-5 index points | hand case `vix_e-0001`; exact rationals; float replay |
| `vix_e` | `vol.vix.index` | 4 / 2 | index 1e-8 abs + 1e-10 rel; term variances 1e-12 abs + 1e-10 rel | index points, published to 0.01 | exact rationals; float replay |

E7 outside-oracle share: 18 of 84 (21.4%). Wrong-convention checks: 78 for E7, each with a gap above its tolerance (`gen_stage_e_b.py` stops otherwise). None of the goldens depend on unseeded Monte Carlo, on a solver path, or on the last digit of a maths-library call. Seeds are used only to make input series (GARCH returns, a realized price path), which are then fixed in the case.

## E4 rates and inflation vol

| Suite | Operation | Cases (ok / error) | Tolerance | In money | Oracle |
|---|---|---|---|---|---|
| `ratesvol_e` | `rates.swaption.price_cube` | 42 / 6 | 1e-9 per unit notional + 1e-9 rel | 0.01 currency on 10m | mpmath-50; QuantLib `BilinearInterpolation` + `SabrSmileSection` + `BlackSwaptionEngine`, all 42 |
| `ratesvol_e` | `rates.cap.strip` | 8 / 6 | caplet vols class `root_finding`; cap prices 1e-9 per unit notional | 0.01 currency on 10m | mpmath-50 root; QuantLib cap-engine reprice check, all 8 (4 with non-annual caps) |
| `ratesvol_e` | `rates.bondfut.option_price` | 5 / 1 | 1e-9 per 100 face + 1e-10 rel | 1e-6 currency per 100k contract | mpmath-50; QuantLib `blackFormula`, all 5 |
| `ratesvol_e` | `rates.bondfut.implied_vol` | 5 / 1 | class `root_finding` | 1e-10 in vol | mpmath-50 root; QuantLib `blackFormulaImpliedStdDev`, all 5 |
| `ratesvol_e` | `infl.cap.yoy_price` | 4 / 1 | 1e-12 per unit notional + 1e-10 rel | 1e-5 currency on 10m | mpmath-50; QuantLib formulas, all 4 |
| `ratesvol_e` | `infl.cap.zc_price` | 5 / 1 | 1e-12 per unit notional + 1e-10 rel | 1e-5 currency on 10m | mpmath-50; QuantLib `blackFormula` on the price; not counted, since `strike_ratio` is the spec's algebra (E-B28) |

Wrong-convention checks: 98 for E4, each caught. Outside-oracle share: 64 of 85 (75%; error cases are in the denominator and never count).

## E6 correlation

| Suite | Operation | Cases (ok / error) | Tolerance | In money | Oracle |
|---|---|---|---|---|---|
| `corr_e` | `risk.corr.validate` | 15 / 2 | booleans exact; `min_eigenvalue` 1e-10 | n/a | mpmath eigenvalues; QuantLib `SymmetricSchurDecomposition` on the symmetrised matrix, all 15 |
| `corr_e` | `risk.corr.nearest` | 15 / 3 | 2e-5 on entries and distance (convergence tolerance) | under 1e-5 relative on a basket vol | Higham-Dykstra and dual solve agree to 1e-7; QuantLib Higham on the 10 cases where it converges |
| `corr_e` | `risk.corr.implied` | 6 / 4 | 1e-12 abs + 1e-10 rel | n/a | hand, mpmath-50 |
| `corr_e` | `risk.corr.dispersion` | 3 / 1 | 1e-12 per unit vega notional + 1e-10 rel | 1e-7 currency on 100k | hand, mpmath-50 |

Wrong-convention checks: 30 for E6, each caught. Outside-oracle share: 25 of 49 (51%).

## E8 credit options and copulas

| Suite | Operation | Cases (ok / error) | Tolerance | In money | Oracle |
|---|---|---|---|---|---|
| `creditopt_e` | `credit.cdsoption.price` | 108 / 6 | price 1e-9 per unit notional + 1e-9 rel; spread and annuity class `simple_analytic` | 0.01 currency on 10m | mpmath-50; QuantLib `CdsOption` + `BlackCdsOptionEngine`, all 108 (72 on month-end, leap-day and stub schedules) |
| `creditopt_e` | `credit.cdsoption.implied_vol` | 60 / 2 | class `root_finding` | 1e-10 in vol | QuantLib `CdsOption.impliedVolatility`, all 60 |
| `creditopt_e` | `credit.copula.joint_default` | 9 / 5 | 1e-12 abs + 1e-9 rel | n/a | mpmath-50 quadrature; QuantLib bivariate normal re-evaluates the 5 Gaussian cases, partly outside, not counted (E-B28) |
| `creditopt_e` | `credit.lhp.tranche_loss` | 18 / 4 | 1e-12 abs + 1e-9 rel | 1e-5 currency on a 10m tranche | closed form, split Gauss-Legendre cross-check; QuantLib bivariate normal, partly outside, not counted (E-B28) |
| `creditopt_e` | `credit.lhp.loss_cdf` | 3 / 1 | 1e-12 abs + 1e-9 rel | n/a | closed form; QuantLib normal functions, partly outside, not counted (E-B28) |

Wrong-convention checks: 290 for E8, each caught. Outside-oracle share: 168 of 216 (78%).

## Spec B outside-oracle share (rule 11.2.5)

| Slice | Suites | Outside / cases | Share |
|---|---|---|---|
| E7 | `garch_e`, `varswap_e`, `vix_e` | 18 / 84 | 21.4% |
| E4 | `ratesvol_e` | 64 / 85 | 75.3% |
| E6 | `corr_e` | 25 / 49 | 51.0% |
| E8 | `creditopt_e` | 168 / 216 | 77.8% |
| Rulings | `rulings_e_b` | 2 / 15 | 13.3% |
| **Spec B** | | **277 / 449** | **61.7%** |

Counted under ruling E-B28 (as E-A17): every output a QuantLib value or plain arithmetic on QuantLib values; 31 partly-outside cases are listed in the register and not counted. Error cases are in every denominator and never count. Stage-wide with spec A (280 / 446 at spec A commit dc16b77, from its own register and goldens): 557 / 895 = 62.2%, 20 cases above the 60% floor.
