# CDS options, default copulas and the large homogeneous pool

Spec version 1.0.0. Status: Specified (stage E, E8, spec B). Rulings: `stage-e-rulings-b.md` E-B22 to E-B26. Builds on `credit.md` (stage D) for vocabulary; the CDS legs here are a separate, stylised model (ruling E-B22).

## `credit.cdsoption.price`

**Plain idea.** A CDS option (a "credit swaption") gives the right to enter a CDS at a fixed spread on a future date. A payer option buys protection. If the name defaults before expiry, a knock-out option dies; a non-knock-out payer instead receives the protection that a forward CDS would not have covered, the *front-end protection*.

Inputs: `as_of`, `expiry`, `maturity` (dates), `rate` and `hazard_rate` (flat, continuous, ACT/365F), `recovery` `R`, `type` (`PAYER`, `RECEIVER`), `strike` `K`, `notional` `N`, `vol` `sigma`, `knock_out` (boolean).

Underlying legs (rulings E-B22, E-B30): dates `x_0 = expiry`, `x_k = expiry + 3k months`, each counted from `expiry` (not chained), the day clipped to the month end (2027-01-31 + 3 months = 2027-04-30), unadjusted, no calendar; the first `x_k` at or after `maturity` is replaced by `maturity`, so a non-multiple of 3 months gives a short final period. With `t(d) = (d - as_of)/365`, `S(d) = e^{-h t(d)}`, `P(d) = e^{-r t(d)}`, and for each period `(a, b)` the mid date `m = a + floor((b - a)/2)` days:

```
protection = sum (1 - R) P(m) (S(a) - S(b))
annuity A  = sum [ (b - a)/360 P(b) S(b) + (m - a)/360 P(m) (S(a) - S(b)) ]
forward_spread F = protection / A
```

Option, with `T = t(expiry)`: `price = N A Black(F, K, sigma, T)`, a call for payers and a put for receivers, plus, for a payer with `knock_out = false`, `front_end_protection = N (1 - R) (1 - S(expiry)) P(expiry)` (ruling E-B23). Receivers get no front-end term.

Outputs: `price`, `forward_spread`, `risky_annuity` (`A`, per unit notional), `front_end_protection` (always reported).

Checks, in order: `expiry <= as_of` or `maturity <= expiry`: `E_INPUT`; `R` outside `[0, 1)`, `hazard_rate < 0`, `strike <= 0`, `vol < 0`: `E_DOMAIN`.

## `credit.cdsoption.implied_vol`

Inputs as above with `premium` in place of `vol`. Output `vol` solving `price(vol) = premium`. Knock-out options only (`knock_out = false`: `E_INPUT`, ruling E-B23). A premium at or below the zero-vol value, or at or above the upper bound: `E_DOMAIN`.

## `credit.copula.joint_default`

**Plain idea.** Two names each have a default probability. A copula joins them: draw two correlated variables and call a name defaulted when its variable is below the matching quantile. The Gaussian copula has no tail dependence; the Student-t copula has some, so joint defaults are likelier, even at zero correlation.

Inputs: `copula` (`GAUSSIAN` or `STUDENT_T`), `default_probabilities` `(p1, p2)`, `correlation` `rho`, `degrees_of_freedom` `nu` (required for `STUDENT_T`). Outputs:

```
GAUSSIAN:  joint = Phi_2( Phi^-1(p1), Phi^-1(p2); rho )
STUDENT_T: joint = T_2,nu( t_nu^-1(p1), t_nu^-1(p2); rho )
default_correlation = (joint - p1 p2) / sqrt(p1 (1 - p1) p2 (1 - p2))
```

`Phi_2` and `T_2,nu` are the bivariate normal and bivariate Student t CDFs with correlation `rho` (for the t: scale matrix with off-diagonal `rho`). Any method accurate to the tolerance may be used (ruling E-B24). Checks: `copula` not listed: `E_SCHEMA`; `default_probabilities` not exactly two values: `E_INPUT`; `STUDENT_T` without `degrees_of_freedom`: `E_INPUT` (it is ignored for `GAUSSIAN`, ruling E-B40); `p` outside `(0, 1)`, `|rho| >= 1`, `nu <= 0`: `E_DOMAIN`.

## `credit.lhp.tranche_loss`, `credit.lhp.loss_cdf`

**Plain idea.** In a very large pool of identical names under a one-factor Gaussian copula, the fraction that defaults is a known function of the common factor (Vasicek). That gives the loss distribution in closed form, and a tranche's expected loss follows.

Inputs: `default_probability` `p` (to the horizon), `correlation` `rho` (asset correlation), `recovery` `R`. With `c = Phi^-1(p)`, the conditional default probability is `P(M) = Phi((c - sqrt(rho) M) / sqrt(1 - rho))`, `M` standard normal, and the pool loss is `L = (1 - R) P(M)`.

`loss_cdf`: input `losses` `x_j`, output `cdf_j = P(L <= x_j) = Phi((sqrt(1 - rho) Phi^-1(x_j/(1 - R)) - c) / sqrt(rho))`.

`tranche_loss`: inputs `attachment` `a`, `detachment` `d`. With `k = min(x/(1 - R), 1)` and

```
E[min(P(M), k)] = p - [ Phi_2(c, m*; sqrt(rho)) - k Phi(m*) ],   m* = (c - sqrt(1 - rho) Phi^-1(k)) / sqrt(rho),   (= p when k = 1)
expected_loss_fraction = (1 - R) ( E[min(P, k_d)] - E[min(P, k_a)] ) / (d - a)      (the second term 0 when a = 0)
```

(ruling E-B25). The tranches of any partition of `[0, 1]`, weighted by width, add up to the pool loss `(1 - R) p`; the goldens check this to 1e-18. A fixed quadrature over `M` reaches the tolerance if it is split at `m*` (the kink of `min(P, k)`); the oracle uses two 200-node Gauss-Legendre rules on `[-12, m*]` and `[m*, 12]` as a cross-check.

Checks: `d <= a`, `a < 0` or `d > 1`: `E_INPUT`; `p` outside `(0, 1)`, `rho` outside `(0, 1)`, `R` outside `[0, 1)`: `E_DOMAIN`; an empty `losses`: `E_INPUT`; a loss `x_j` not in `(0, 1 - R)`: `E_DOMAIN`.

## Worked examples

- CDS option (`creditopt_e-0001`): expiry 2027-03-20, CDS to 2032-03-20, `r = 3.5%`, `h = 2%`, `R = 40%`, payer at 1.20%, vol 50%, knock-out. Forward spread 1.18877% (close to `(1 - R) h = 1.2%`, lower because of the accrual and discounting), risky annuity 4.32865, price 59,847.84 on 10m. The reported `front_end_protection` is `1e7 x 0.6 x (1 - e^{-0.02 x 134/365}) x e^{-0.035 x 134/365} = 43,333.06`; a non-knock-out payer would add it to its price. A receiver on the same underlying at 0.96% (`creditopt_e-0003`) is worth 11,581.73.
- Copulas (`creditopt_e-0147`, `-0151`): `p = (2%, 3%)`, `rho = 0.3`. Gaussian joint default 0.2288%, Student t with 4 degrees of freedom 0.5102%: more than twice as likely, from tail dependence alone. At `rho = 0` the Gaussian gives exactly `p1 p2 = 0.06%` (`creditopt_e-0155`); the t with 5 degrees of freedom still gives 2.04% against 1.5% (`creditopt_e-0154`).
- LHP (`creditopt_e-0161` to `-0166`): `p = 5%`, `rho = 0.3`, `R = 40%`, pool loss 3%. Expected loss of the 0-3% tranche is 54.11% of its notional, 3-7% 19.58%, 7-10% 8.78%, 10-15% 4.06%, 15-30% 0.81%, 30-100% 0.0082%. Width-weighted, they add up to 3%.

## Acceptance

Suite `stage_e_b/creditopt_e`. CDS option prices 1e-9 per unit notional (stage D credit); forward spread and annuity class `simple_analytic`; implied vol class `root_finding`. Copula probabilities and LHP values 1e-12 absolute plus 1e-9 relative (1e-5 currency on a 10m tranche).

Outside oracle (QuantLib 1.44, `oracle/outside_register_e_b.json`): every CDS option and implied-vol case through `CdsOption`, `BlackCdsOptionEngine` and `MidPointCdsEngine`, with `front_end_protection` taken as QuantLib's non-knock-out payer value minus its knock-out payer value. Gaussian copula, LHP tranche and loss-CDF cases are re-evaluated with QuantLib's `BivariateCumulativeNormalDistributionWe04DP` and normal functions, but their outputs are the spec's own algebra on those functions, so they are listed as partly outside and not counted (ruling E-B28, as spec A's E-A17). The Student-t copula has no QuantLib object in the Python wheel; its goldens rest on 50-digit quadrature. QuantLib's `GaussianLHPLossModel` and tranche engines are not in the Python wheel.

Wrong-convention checks, each caught: annuity without accrual on default; ACT/365 premium accrual; option time to maturity instead of expiry; front-end protection added to a knock-out; Gaussian in place of t; `sqrt(rho)` used as the pair correlation; tranche points not scaled by `1 - R`; `rho` read as `sqrt(rho)` in the pool.

## Sources

- [S1] O'Kane, D., *Modelling Single-name and Multi-name Credit Derivatives*, Wiley, 2008: CDS option pricing with Black on the forward spread and the front-end protection (chapter on CDS options); the large homogeneous pool (chapter on the LHP model) (not opened)
- [S2] Vasicek, O., "Limiting loan loss probability distribution", KMV Corporation, 1991; "The distribution of loan portfolio value", *Risk* 15(12), 2002, 160-162 (the LHP loss distribution) (not opened)
- [S3] Li, D. X., "On default correlation: a copula function approach", *Journal of Fixed Income* 9(4), 2000, 43-54 (Gaussian copula for default times) (not opened)
- [S4] Demarta, S. and McNeil, A. J., "The t copula and related copulas", *International Statistical Review* 73(1), 2005, 111-129 (Student t copula, tail dependence) (not opened)
- [S5] West, G., "Better approximations to cumulative normal functions", *Wilmott Magazine*, 2005 (the bivariate normal algorithm QuantLib uses) (not opened)
- [S6] QuantLib 1.44 Python wheel: `CdsOption`, `BlackCdsOptionEngine`, `MidPointCdsEngine`, `BivariateCumulativeNormalDistributionWe04DP`, `InverseCumulativeNormal` (used by behaviour)
