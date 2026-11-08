# Stage E numeric targets, spec B

Spec version 1.0.0. One table per slice, added as each slice lands. Tolerances are stated in money where an output is money, and every class has its reason; `conformance/tolerances/policy.yaml` gives the base classes, and a case's `tolerance_limit` overrides them for its outputs.

## E7 GARCH, variance swaps, VIX

| Suite | Operation | Cases (ok / error) | Tolerance | In money | Oracle |
|---|---|---|---|---|---|
| `garch_e` | `vol.garch.loglik` | 9 / 7 | 1e-9 abs + 1e-10 rel on `loglik` (500-term sums); class `statistics` on 8-return and hand cases | n/a (a likelihood) | mpmath-50 replica; float replay; hand case `garch_e-0009` |
| `garch_e` | `vol.garch.forecast` | 6 / 2 | 1e-16 abs + 1e-11 rel on variances | under 1e-9 in annualised vol: under 0.01 currency of vega on 10m vega notional | mpmath-50; float replay |
| `garch_e` | `vol.garch.fit` | 2 / 1 | `loglik` within 1e-6 abs | a 5% `omega` error costs more (checked) | multi-start Nelder-Mead, 50-digit Newton polish, gradient and Hessian checked |
| `varswap_e` | `vol.varswap.fair_strike` | 20 / 7 | 1e-12 abs per unit variance notional + 1e-10 rel | 1e-6 currency on `N_var = 1e6` | mpmath-50; all 18 `q = 0` cases outside-checked by QuantLib `ReplicatingVarianceSwapEngine` (`oracle/outside_register_e_b.json`) |
| `varswap_e` | `vol.varswap.realized` | 2 / 2 | 1e-12 in variance on the notional + 1e-10 rel | 1e-6 currency per 1e6 | hand case `varswap_e-0028`; mpmath-50 |
| `vix_e` | `vol.vix.term_variance` | 6 / 5 | 1e-12 abs + 1e-10 rel on variance | under 1e-5 index points | hand case `vix_e-0001`; exact rationals; float replay |
| `vix_e` | `vol.vix.index` | 2 / 1 | 1e-8 abs + 1e-10 rel | index points, published to 0.01 | exact rationals; float replay |

Wrong-convention checks: 74 for E7, each with a gap above its tolerance (`gen_stage_e_b.py` stops otherwise). None of the goldens depend on unseeded Monte Carlo, on a solver path, or on the last digit of a maths-library call. Seeds are used only to make input series (GARCH returns, a realized price path), which are then fixed in the case.
