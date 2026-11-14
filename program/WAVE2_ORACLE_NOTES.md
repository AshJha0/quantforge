# Stage J wave 2: outside-library oracle notes (2026-11-14)

Script `oracle/python/outside_j.py` (wave 2 functions `optim`, `estim`, `esbt`, `baumwelch`; run with `--wave 2`, which
keeps the committed wave 1 suites unchanged), output `oracle/OUTSIDE_J.json`, pins
`oracle/python/requirements-outside-j.txt` (separate venv, not `uv.lock`). Goldens and implementation code were not
changed. Each case is compared output by output at the golden's own tolerance class (`root_finding` 1e-10 abs +
1e-10 rel for mean-variance and risk parity; `simple_analytic` for Euler, Ledoit-Wolf, Black-Litterman; the per-case
`tolerance_limit` 1e-12 abs + 1e-9 rel for Baum-Welch parameters and `likelihood_sum` for its log-likelihood, as
`conformance/runner/runner.py` applies them). A case counts only if every compared output passes.
`tools/outside_shares.py` reads the same file through `load_percase_j`, so no change to the share tool was needed.

## Result

| Suite | Value cases | Library-checked | Class | Library |
|---|---|---|---|---|
| `optim_j` mean-variance | 21 | 21 | library-primitive | DAQP 0.11.2 dual active-set QP |
| `optim_j` risk parity | 8 | 6 | library-primitive | cvxpy 1.9.3 with Clarabel 0.11.1, `min 1/2 y'Sy - b'log y` |
| `optim_j` Euler | 6 | 6 | library-primitive | autograd 1.9.1, derivative of `sigma(w)` |
| `estim_j` Ledoit-Wolf | 9 | 9 | library-primitive | scikit-learn 1.9.1 `LedoitWolf` |
| `estim_j` Black-Litterman | 6 | 6 | library-primitive | PyPortfolioOpt 1.6.0 `BlackLittermanModel` |
| `esbt_j` | 7 | 0 | none | no free library |
| `baumwelch_j` | 6 | 6 | library-primitive | hmmlearn 0.3.3 `GaussianHMM.fit` |
| Wave 2 total | 63 (96 with error cases) | 54 | 54 primitive | |

Wave 2 alone: 54 of 63 value-checked cases (85.7 %). Stage J after both waves: 95 of 126 value-checked cases
(75.4 %), up from 41 of 63 (65.1 %); old all-case figure 40.6 %. Every wave 2 case is `library-primitive` because at
least one output is arithmetic on the library result (`via: "arithmetic"` in the JSON): mean-variance expected return,
volatility, objective and `at_bound` (within 1e-9 of a bound); risk-parity volatility and contributions; Euler
contributions and shares; Ledoit-Wolf `mu = trace/N` of the library covariance; Black-Litterman
`posterior_covariance = bl_cov - Sigma`; Baum-Welch `sds = sqrt(covars_)`, `iterations` and `converged` read off the
library's convergence history.

Largest gaps among counted cases: mean-variance weights 1.5e-15 (the 20 J-5 problems plus the hand case); Euler
1.1e-16; Ledoit-Wolf and Black-Litterman 1.6e-15; Baum-Welch 8.5e-14 (a log-likelihood) with every stop iteration
and `converged` flag equal; risk parity 7.1e-12.

## Convention checks

1. **Ledoit-Wolf.** scikit-learn's `ledoit_wolf_shrinkage` uses the same scaled-identity target, demeans
   (`assume_centered=False`), divides by `T` (not `T - 1`), and forms `b^2` by the cancellation form
   `(1/(N T^2)) [sum_t ||x_t||^4 - T ||S||^2]`, which equals the spec's direct sum `(1/T^2) sum_t ||x_t x_t' - S||^2 / N`
   in exact arithmetic. It clips `b^2` at `d^2` and returns shrinkage 0 for `N = 1`, as J-W2-7. Conventions match, so
   all nine cases are counted. This closes the scikit-learn item left open in J-W2-15.
2. **Black-Litterman.** PyPortfolioOpt's `bl_returns` is the spec's update form `pi + tau S P' (P tau S P' + Omega)^-1
   (q - P pi)` and `bl_cov` returns `Sigma + M` with `M` the posterior covariance of the mean, which is the spec's
   `predictive_covariance`. `posterior_covariance` is `bl_cov - Sigma` (arithmetic). Licence MIT.
3. **Mean-variance.** PyPortfolioOpt's `max_quadratic_utility` maximises `mu'w - (gamma/2) w'Sw` with
   `sum w = 1` and per-asset bounds, the J-W2-2 problem. It runs on Clarabel (interior point) and is reported per case
   as `second_solver` but not counted: its largest weight gap is 2.1e-12, inside `root_finding` everywhere, against
   the 1.8e-8 that scipy SLSQP reached in the generator. The counted solver is DAQP, a dual active-set method whose
   final working set is solved by factorisation, so it reaches the exact KKT point to rounding, as the J-W2-4 rule
   expects. The J-5 1e-8 target is met by both outside solvers on all 20 problems.
4. **Baum-Welch.** hmmlearn's `GaussianHMM` defaults are not plain maximum likelihood: `min_covar = 1e-3`,
   `covars_prior = 1e-2` and the mean prior would bias the M-step. The check sets `min_covar = 0`, `covars_prior = 0`,
   `covars_weight = 1`, `means_weight = 0` and flat Dirichlet priors (`startprob_prior = transmat_prior = 1`), and
   `init_params = ""` so the given start values are used. EM finds a local maximum that depends on the start, so a
   case can only be compared when the start and the stop rule match; both do here. hmmlearn's `ConvergenceMonitor`
   stops at the first `j` with `L_j - L_{j-1} < tol` (absolute gain, the J-W2-11 test), but hmmlearn applies one more
   M-step after its last E-step, so its returned parameters are `theta_{k+1}`. The check therefore takes `k` from the
   library's history and re-runs `fit` with `n_iter = k` and the stop test off to get `theta_k`, and takes `L_k` from
   the library's `score`. All six cases agree (stop iterations 2, 28, 5 not converged, 15, 39, 5).

## Not counted

- **`esbt_j` (7 value cases).** No pip-installable free library computes the Acerbi-Szekely Z2 statistic. The
  MATLAB Risk Toolbox has it and is commercial. The `AS14_test` class of the Realized_Risk_Measures project is on
  GitHub only, with a bootstrap p-value interface and a licence that was not read. [AS14] prints critical values,
  not a worked example on data, so there is no published example to count either. The suite stays hand-checked:
  `esbt_j-0001` and `-0002` are hand cases in the spec. scipy or numpy around the spec's one-line formula would be a
  reimplementation (D6).
- **`optim_j-0029`, `optim_j-0030` (risk parity, two assets).** Clarabel misses `root_finding` on weights by
  2.9e-10 and 2.8e-8. See the investigation below. **The goldens are right; the gap is the interior-point solver.**

## Investigation: risk parity, two-asset cases

Settings were fixed once for all eight cases (`tol_gap_abs = tol_gap_rel = tol_feas = 1e-14`, `max_iter = 500`) and
not tuned per case. Clarabel cannot certify 1e-14 and reports `optimal_inaccurate` on four of the eight (status
recorded per case as `solver_status`). Its accuracy at stop varies from case to case: a scan of tolerances 1e-10,
1e-12, 1e-13, with equilibration on and off, gave weight errors from 9e-14 to 2e-6, and no single setting put all
eight within 1e-10. That is how an interior-point method behaves near its accuracy floor, not a sign of a different
answer.

Independent check of the two goldens (arithmetic, not counted): with `r = w_2 / w_1`, equal-share risk budgeting for
two assets reduces to `b_1 s_2^2 r^2 + (b_1 - b_2) s_12 r - b_2 s_1^2 = 0`. Solved at 50 digits:
`optim_j-0029` gives `w_1 = 0.6` to 1e-50 (the spec's hand result); `optim_j-0030` gives
`w_1 = 0.723056437901844224...`, within 7.5e-17 of the golden. Both goldens stand.

A library that reaches these to 1e-10 would need an exact Newton or active-set method on this problem.
`riskparityportfolio` (Spinu's Newton) was not tried: it pulls in jax, which is a heavy install on a machine at
full load. It is the obvious next candidate if the two cases are to be counted.

## Precision notes (no golden disagreement)

1. Risk-parity cases that do count agree to 1e-11 or better (7.1e-12 worst, `optim_j-0032`).
2. `check()` now honours a per-case `tolerance_limit` exactly as the runner does; only `baumwelch_j` uses one in
   stage J, so wave 1 results are unchanged (the wave 1 suites in `OUTSIDE_J.json` are byte-for-byte the committed ones).

## Draft ruling row (for `specifications/stage-j-rulings-w2.md`)

| J-W2-16 | Outside check, wave 2 (amends J-W2-15) | Outside libraries now check 54 of the 63 value-checked wave 2 goldens (54 of 96 with error cases), all `library-primitive`: `optim_j` 33/35 (mean-variance 21/21 DAQP 0.11.2 dual active-set QP, worst weight gap 1.5e-15, PyPortfolioOpt 1.6.0 on Clarabel 0.11.1 reported as a second solver at 2.1e-12; risk parity 6/8 cvxpy 1.9.3 with Clarabel 0.11.1 on `min 1/2 y'Sy - b'log y`; Euler 6/6 autograd 1.9.1); `estim_j` 15/15 (Ledoit-Wolf 9/9 scikit-learn 1.9.1 `LedoitWolf`, same estimator and `1/T` convention; Black-Litterman 6/6 PyPortfolioOpt 1.6.0); `baumwelch_j` 6/6 hmmlearn 0.3.3 `GaussianHMM.fit` with ML settings, same start values and stop rule, `theta_k` by a re-run with `n_iter = k`; `esbt_j` 0/7 (no free Z2 library, no published worked example). `optim_j-0029`, `-0030` miss `root_finding` by Clarabel's accuracy floor (2.9e-10, 2.8e-8); a 50-digit two-asset closed form confirms both goldens. Per case in `oracle/OUTSIDE_J.json`; notes in `program/WAVE2_ORACLE_NOTES.md`. Stage J value share 95 of 126 = 75.4 % (`tools/outside_shares.py`) |
