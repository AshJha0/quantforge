# Almgren-Chriss optimal execution

Spec version 0.1.0 (stage H wave 1; confirmed 2026-11-18 by the stage H coordinator). Status: implemented in all four builds (Python, Java, C++, Rust; 2026-11-18). Rulings HR-2, HR-5, HR-6, HR-9. Plan items 14.7 H-3 (trajectory and frontier to 1e-12), 15.1.

**Plain idea.** Selling fast costs impact; selling slowly leaves the position exposed to price moves. With linear impact and mean-variance preferences the optimal holdings decay like a hyperbolic sine, and the risk aversion `lambda` slides the schedule along an efficient frontier of (expected cost, variance).

Sources:
- [AC00] R. Almgren, N. Chriss, "Optimal execution of portfolio transactions", *Journal of Risk* 3(2) 5-39 (issue dated winter 2000/01, DOI 10.21314/JOR.2001.041). Read 2026-11-15 in the free December 2000 preprint (copy at smallake.kr/wp-content/uploads/2016/03/optliq.pdf; Almgren's own Toronto and NYU links are dead). Page numbers below are the PREPRINT's own page numbers, not journal pages. Verified against the text:
  - eq. (5), p. 10: `V = sigma^2 tau sum_{k=1..N} x_k^2`;
  - eq. (8), p. 11: `E = 1/2 gamma X^2 + epsilon sum |n_k| + (eta_tilde / tau) sum n_k^2`, with `eta_tilde = eta - gamma tau / 2` (unnumbered, p. 11); `sum |n_k| = |X|` for monotone trajectories (p. 11), which is ruling HR-5's `epsilon X`;
  - eqs. (9)-(11), pp. 11-12: linear trajectory, `E = 1/2 gamma X^2 + epsilon X + eta_tilde X^2 / T`, `V = 1/3 sigma^2 X^2 T (1 - 1/N)(1 - 1/(2N))`;
  - eq. (16) and the unnumbered line after it, p. 14: `(2 / tau^2)(cosh(kappa tau) - 1) = kappa_tilde^2 = lambda sigma^2 / eta_tilde` (the spec's `2 (cosh(kappa tau) - 1) = tau^2 lambda sigma^2 / eta_tilde` is the same relation);
  - eq. (17), p. 14: `x_j = X sinh(kappa (T - t_j)) / sinh(kappa T)`; eq. (18), p. 14: trade list;
  - eq. (19), p. 15: `kappa_tilde -> kappa = sqrt(lambda sigma^2 / eta)` as tau -> 0 (property test below);
  - eq. (20), p. 15: closed forms for E and V of the optimal trajectory (the text extraction garbles the layout; the form used in the scratch check agrees with the direct sums (5), (8) to 15 digits for lambda = 1e-6 and 2e-6).
  Evidence class: paper, read.
- Parameter set P is the paper's test case: section 3.4, pp. 23-24, and Table 1, p. 25 (S0 = 50, X = 1e6, T = 5 days, N = 5, sigma = 0.95, epsilon = 0.0625, gamma = 2.5e-7, eta = 2.5e-6, lambda = 1e-6; also mu = 0.02, not used, and VaR v = 1.645). Verified. The paper prints no trajectory, E or V values for P; Figures 1 and 2 (pp. 17-18) are plots without tabulated numbers, so they cannot serve as goldens. Printed numbers that can: kappa "about 0.6/day" and kappa T "about 3" (p. 24, from eq. (19)); case ac_h-0005.
- Remark, not a golden: p. 24 says the no-trading standard deviation sigma sqrt(T) X = $2.12M is "precisely twice" the standard deviation of the lowest frontier point. For the discrete linear trajectory with N = 5 (ac_h-0001) the ratio is 2.124e6 / 1.0407e6 = 2.04, not 2; the paper's statement is not reproduced exactly and is not used.
- Outside check for the other goldens: no free library implements AC. Per DR-H2 a golden counts as outside-checked only through a printed figure or a blind re-derivation by a second lane that has not seen these numbers. ac_h-0001, 0002, 0004 were then blind re-derived (2026-11-15, second lane, mpmath 40 digits, inputs only; STAGE_H_BLIND_REDERIVATION.md): ac_h-0001 E and V exact, ac_h-0002 within 3.3e-10 relative (print rounding), ac_h-0003 E_DOMAIN, ac_h-0004 E = 562,500. Caveat: the ac_h-0001 standard deviation 1.0407e6 (line above) was visible to the second lane beforehand, so that one figure is not blind; the other outputs were. ac_h-0005 is outside-checked against the printed figure. Wave-1 outside-checked goldens: see the share in STAGE_H_START.md.

## `exec.ac.trajectory`
Inputs `quantity` X, `horizon` T, `n_steps` N, `sigma`, `epsilon`, `eta`, `gamma`, `risk_aversion` lambda (>= 0). Outputs `holdings` x_0..x_N (x_0 = X, x_N = 0), `trades` n_1..n_N, `kappa`, `expected_cost`, `variance`, `objective` = E + lambda V. Errors, in this order (HR-122): N < 1, X <= 0, an empty `risk_aversions`: `E_INPUT`; then T <= 0, sigma < 0, epsilon < 0, gamma < 0, `eta_tilde <= 0`, lambda < 0: `E_DOMAIN`. `x_0 = X` and `x_N = 0` are assigned, not computed. When y = lambda sigma^2 tau^2 / (2 eta_tilde) is 0 (lambda = 0, sigma = 0, or underflow) the output is the linear trajectory with `kappa = 0` (HR-124).

## `exec.ac.frontier`
As above with `risk_aversions` (list); one (lambda, E, V) per entry. Property: E non-decreasing and V non-increasing in lambda.

## Golden cases

P: X = 1e6, T = 5, N = 5 (tau = 1), sigma = 0.95, epsilon = 0.0625, eta = 2.5e-6, gamma = 2.5e-7; so eta_tilde = 2.375e-6.

| Case | lambda | Expected | Derivation |
|---|---|---|---|
| ac_h-0001 | 0 | holdings [1e6, 8e5, 6e5, 4e5, 2e5, 0]; E = 662,500; V = 1.083e12 | Blind re-derived (DR-H2; the std dev was visible beforehand). E = 125,000 (1/2 gamma X^2) + 62,500 (epsilon X) + 475,000 (eta_tilde X^2 / T); V = sigma^2 tau X^2 (N-1)(2N-1)/(6N) = 0.9025e12 x 1.2; both are [AC00] eqs. (10), (11), pp. 11-12 |
| ac_h-0002 | 1e-6 | kappa = 0.6070761632; holdings [1e6, 541955.5544, 289854.2194, 147897.4878, 62141.8016, 0]; E = 911,226.986; V = 3.641285721e11; objective 1,275,355.558 | cosh(kappa) = 1 + 1e-6 x 0.9025 / (2 x 2.375e-6) = 1.19; holdings from the sinh ratio; digits from an mpmath scratch script (40 digits, 2026-11-15); E and V also agree with closed form eq. (20) p. 15 to 15 digits; to be reproduced by the oracle generator. Blind re-derived (DR-H2): outside-checked |
| ac_h-0003 | gamma = 2 eta / tau | `E_DOMAIN` | eta_tilde = 0 |
| ac_h-0004 | P with N = 1 (so tau = T = 5), lambda = 1e-6 | holdings [1e6, 0]; E = 562,500 | E = 1/2 gamma X^2 + epsilon X + eta_tilde X^2 / T = 125,000 + 62,500 + 375,000. Here eta_tilde = eta - gamma tau / 2 depends on tau: with tau = 5, eta_tilde = 2.5e-6 - 2.5e-7 x 5 / 2 = 1.875e-6, not the 2.375e-6 of the P line (which holds for tau = 1); reusing 2.375e-6 would give 662,500. Lambda (1e-6) does not change the single-trade holdings or E; it only enters kappa (about 0.527 here), which is not asserted. Blind re-derived (DR-H2) |
| ac_h-0005 | P, lambda = 1e-6 | kappa = 0.6070761632 (as ac_h-0002); kappa T = 3.0353808 | OUTSIDE-CHECKED against printed figures, [AC00] p. 24: "kappa about 0.6/day, so kappa T about 3". Agreement to the one significant figure printed; the paper's figure comes from approximation (19), sqrt(lambda sigma^2 / eta) = 0.6008, so the test tolerance is 0.05 on kappa and 0.25 on kappa T |
| ac_h-0006 | `exec.ac.frontier`, P, lambdas [0, 5e-7, 1e-6, 2e-6] | E non-decreasing, V non-increasing; points 1 and 3 equal ac_h-0001, ac_h-0002 | added by the oracle lane 2026-11-18; hand calculation and oracle only, not blind re-derived |
| ac_h-0007 | P with N = 0 | `E_INPUT` | N < 1; added by the oracle lane 2026-11-18; hand calculation and oracle only, not blind re-derived |
| ac_h-0008 | P with X = 0 | `E_INPUT` | non-positive quantity (HR-56); added by the integration lane 2026-11-18 for HR-56; hand calculation and oracle only, not blind re-derived |
| ac_h-0009 | P with epsilon = -0.0625 | `E_DOMAIN` | negative epsilon (HR-56); added by the integration lane 2026-11-18 for HR-56; hand calculation and oracle only, not blind re-derived |
| ac_h-0010 | P with gamma = -2.5e-7 | `E_DOMAIN` | negative gamma (HR-56); added by the integration lane 2026-11-18 for HR-56; hand calculation and oracle only, not blind re-derived |

## Property tests
Trades sum to X to 1e-12 relative; for lambda > 0 holdings lie strictly below linear; as tau -> 0, kappa tends to `sqrt(lambda sigma^2 / eta)` ([AC00] eq. (19), p. 15).

## Convergence and limit cases
| Limit | Behaviour | Check |
|---|---|---|
| lambda -> 0 | trajectory tends to the linear one; lambda = 0 returns it exactly, not by cancellation (HR-5) | ac_h-0001; property test at lambda = 1e-15 on P within 2e-9 relative of linear. Derivation: x_k = X sinh(kappa (T - t_k)) / sinh(kappa T) = linear x (1 + kappa^2 ((T - t_k)^2 - T^2) / 6 + O(kappa^4)), so the model's own shift from linear is at most kappa^2 T^2 / 6; on P, y = lambda sigma^2 tau^2 / (2 eta_tilde) = 1.9e-10, kappa^2 about 2y = 3.8e-10, kappa^2 T^2 / 6 about 1.6e-9 (the earlier 1e-9 bound was below the model's own shift; corrected 2026-11-18) |
| tau -> 0 (N large, T fixed) | kappa_tilde -> sqrt(lambda sigma^2 / eta), [AC00] eq. (19) | property test at N = 10, 100, 1000: error falls like tau |
| y small in HR-6 | `log1p` form keeps kappa accurate where `acosh(1 + y)` loses digits | property test at y = 1e-14 against the series sqrt(2y) |
| kappa T > 700 | sinh ratio in exponential form, no overflow (HR-6) | property test at kappa T = 1000: holdings finite, decreasing |
| N = 1 | single trade, E as ac_h-0004 | ac_h-0004 |
| eta_tilde <= 0 | `E_DOMAIN` | ac_h-0003 |

## Limitations
Linear impact, arithmetic Brownian price, no drift, pre-committed schedule. Adaptive re-optimisation is wave 2.
