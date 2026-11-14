# Covariance and return estimation: Ledoit-Wolf shrinkage, Black-Litterman

Spec version 1.0.0. Status: Specified (stage J, wave 2); not yet implemented in any build. Target CLI contract 1.14.0 (ruling J-W2-1). Rulings: `stage-j-rulings-w2.md` J-W2-3, J-W2-7, J-W2-8, J-W2-14. Suite: `datasets/golden/stage_j/estim_j`, written by `oracle/python/gen_stage_j_w2.py`. Plan row J ("Bayesian estimation"), 14.6 J-6.

**Plain idea.** A sample covariance matrix from a short history is noisy, and an optimiser leans on exactly the noisiest entries. Ledoit-Wolf pulls it towards a multiple of the identity by an amount estimated from the data. Black-Litterman starts from a prior for expected returns (usually the returns that make the market portfolio optimal) and moves it towards an investor's views by as much as their stated confidence allows. Both are closed forms; neither is iterative.

Sources:
- [LW04] O. Ledoit, M. Wolf, "A well-conditioned estimator for large-dimensional covariance matrices", *Journal of Multivariate Analysis* 88(2), 2004, 365-411 (scaled-identity target, `m`, `d^2`, `b^2`, `delta = b^2/d^2`) (not opened in this session). Evidence class: paper, recalled. The generator computes the estimator in two algebraic forms, the paper's and the one in scikit-learn's `ledoit_wolf_shrinkage` source, and asserts they are equal in exact arithmetic. scikit-learn itself was not run (not installed in the oracle environment on 2026-11-14): the J-6 library check is open (J-W2-15).
- [BL92] F. Black, R. Litterman, "Global portfolio optimization", *Financial Analysts Journal* 48(5), 1992, 28-43 (not opened). Evidence class: paper, recalled.
- [HL99] G. He, R. Litterman, "The intuition behind Black-Litterman model portfolios", Goldman Sachs working paper, 1999 (posterior mean and covariance formulas) (not opened). Evidence class: paper, recalled. The generator checks the update form against the precision form `[(tau Sigma)^-1 + P' Omega^-1 P]^-1 [(tau Sigma)^-1 pi + P' Omega^-1 q]` exactly.

## `research.estimate.ledoit_wolf`

Inputs `returns` (`T x N`, one row per period, `T >= 2`, `N >= 1`, rows of equal length; else `E_INPUT`). Definition (J-W2-7), with `x_t` the demeaned row and `||A||^2 = sum_ij A_ij^2`:

- `S = (1/T) sum_t x_t x_t'`; `m = tr S / N`;
- `d^2 = ||S - m I||^2 / N`; `bbar^2 = (1/T^2) sum_t ||x_t x_t' - S||^2 / N`; `b^2 = min(bbar^2, d^2)`;
- `delta = b^2 / d^2`, and `delta = 0` when `b^2 = 0` (this covers `d^2 = 0`, for example `N = 1`);
- `covariance = delta m I + (1 - delta) S`.

Outputs `covariance`, `shrinkage` (`delta`), `mu` (`m`). Tolerance `simple_analytic`. A build should form `sum_t ||x_t x_t' - S||^2` as `sum_t (sum_i x_ti^2)^2 - T ||S||^2` only if it accepts the cancellation; the direct sum is the safer form.

Worked example (`estim_j-0001`): rows `(1, 0), (-1, 0), (0, 1), (0, -1)`; means 0; `S = diag(0.5, 0.5)`; `m = 0.5`; `d^2 = 0`, so `b^2 = 0` and `delta = 0`.

## `research.estimate.black_litterman`

Inputs `covariance` (`Sigma`, `N x N`, symmetric positive definite), `prior_returns` (`pi`, length `N`), `pick` (`P`, `K x N`, `K >= 1`), `views` (`q`, length `K`), `view_covariance` (`Omega`, `K x K`, symmetric positive definite), `tau > 0`. Errors: shapes `E_INPUT`; `tau <= 0`, `Sigma` or `Omega` not symmetric positive definite `E_DOMAIN`.

Outputs (J-W2-8): `posterior_returns = pi + tau Sigma P' (P tau Sigma P' + Omega)^-1 (q - P pi)`; `posterior_covariance = tau Sigma - tau Sigma P' (P tau Sigma P' + Omega)^-1 P tau Sigma`; `predictive_covariance = Sigma + posterior_covariance`. Solve with the `K x K` matrix by Cholesky; never invert `Sigma`. Tolerance `simple_analytic`.

Worked example (`estim_j-0012`): one asset, `Sigma = 0.04`, `tau = 0.05` (prior variance of the mean 0.002), `pi = 0.05`, a view `q = 0.10` with `Omega = 0.002`. Equal precisions give the average, `0.075`; posterior variance of the mean `0.001`.

## Property tests (each language, own data)

- Ledoit-Wolf: `0 <= delta <= 1`; the output is symmetric positive definite whenever `delta > 0`; invariant to adding a constant to a column.
- Black-Litterman: as `Omega` grows (all entries times `c`, `c` large) the posterior tends to the prior; with `Omega -> 0` and `P = I` it tends to `q`; the update and precision forms agree to `1e-10` (J-6).

## Limitations

Only the scaled-identity Ledoit-Wolf target (no constant-correlation or single-factor target, no nonlinear shrinkage). Black-Litterman takes the prior as an input; the reverse optimisation `pi = delta Sigma w_mkt` and the choice of `tau` and `Omega` are the caller's, and the J-6 acceptance treats the closed form only.
