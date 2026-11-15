# Almgren-Chriss optimal execution (DRAFT)

Spec version 0.1.0 (DRAFT, stage H wave 1). Status: Specified, not implemented. Rulings H-2, H-5, H-6, H-9. Plan items 14.7 H-3 (trajectory and frontier to 1e-12), 15.1.

**Plain idea.** Selling fast costs impact; selling slowly leaves the position exposed to price moves. With linear impact and mean-variance preferences the optimal holdings decay like a hyperbolic sine, and the risk aversion `lambda` slides the schedule along an efficient frontier of (expected cost, variance).

Sources:
- [AC00] R. Almgren, N. Chriss, "Optimal execution of portfolio transactions", *Journal of Risk* 3(2) (2000) 5-39; free preprint on Almgren's site (URL not re-checked). Formulas used: `E = 1/2 gamma X^2 + epsilon sum |n_k| + (eta_tilde / tau) sum n_k^2`; `V = sigma^2 tau sum_{k=1..N} x_k^2`; `eta_tilde = eta - gamma tau / 2`; `2 (cosh(kappa tau) - 1) = tau^2 lambda sigma^2 / eta_tilde`; `x_j = X sinh(kappa (T - t_j)) / sinh(kappa T)`. Recalled; equation and page numbers NOT verified. Evidence class: paper, recalled.
- The parameter set P below is recalled as the paper's worked example; UNVERIFIED against the paper, so the goldens rest on the hand and script derivation, not on printed figures (open question O-1).
- Outside check: no free library implements AC; independent blind re-derivation (Sonnet) per the plan's process. Evidence class: hand calculation plus independent re-derivation.

## `exec.ac.trajectory`
Inputs `quantity` X, `horizon` T, `n_steps` N, `sigma`, `epsilon`, `eta`, `gamma`, `risk_aversion` lambda (>= 0). Outputs `holdings` x_0..x_N (x_0 = X, x_N = 0), `trades` n_1..n_N, `kappa`, `expected_cost`, `variance`, `objective` = E + lambda V. Errors: `eta_tilde <= 0`, sigma < 0, T <= 0: `E_DOMAIN`; N < 1: `E_INPUT`.

## `exec.ac.frontier`
As above with `risk_aversions` (list); one (lambda, E, V) per entry. Property: E non-decreasing and V non-increasing in lambda.

## Golden cases

P: X = 1e6, T = 5, N = 5 (tau = 1), sigma = 0.95, epsilon = 0.0625, eta = 2.5e-6, gamma = 2.5e-7; so eta_tilde = 2.375e-6.

| Case | lambda | Expected | Derivation |
|---|---|---|---|
| ac_h-0001 | 0 | holdings [1e6, 8e5, 6e5, 4e5, 2e5, 0]; E = 662,500; V = 1.083e12 | E = 125,000 (1/2 gamma X^2) + 62,500 (epsilon X) + 475,000 (eta_tilde X^2 / T); V = sigma^2 tau X^2 (N-1)(2N-1)/(6N) = 0.9025e12 x 1.2 |
| ac_h-0002 | 1e-6 | kappa = 0.6070761632; holdings [1e6, 541955.5544, 289854.2194, 147897.4878, 62141.8016, 0]; E = 911,226.986; V = 3.641285721e11; objective 1,275,355.558 | cosh(kappa) = 1 + 1e-6 x 0.9025 / (2 x 2.375e-6) = 1.19; holdings from the sinh ratio; digits from a double-precision scratch script (2026-11-15), to be reproduced by the oracle generator |
| ac_h-0003 | gamma = 2 eta / tau | `E_DOMAIN` | eta_tilde = 0 |
| ac_h-0004 | N = 1 | holdings [X, 0]; E = 1/2 gamma X^2 + epsilon X + eta_tilde X^2 / T | single trade; lambda has no effect |

## Property tests
Trades sum to X to 1e-12 relative; for lambda > 0 holdings lie strictly below linear; as tau -> 0, kappa tends to `sqrt(lambda sigma^2 / eta)`.

## Limitations
Linear impact, arithmetic Brownian price, no drift, pre-committed schedule. Adaptive re-optimisation is wave 2.
