# Regime estimation: Baum-Welch for a Gaussian hidden Markov model

Spec version 1.0.0. Status: Specified (stage J, wave 2); not yet implemented in any build. Target CLI contract 1.14.0 (ruling J-W2-1). Rulings: `stage-j-rulings-w2.md` J-W2-9, J-W2-11 to J-W2-14. Suite: `datasets/golden/stage_j/baumwelch_j`, written by `oracle/python/gen_stage_j_w2.py`. Plan 12.5 A4 and 12.10 A4 (recovery, bit-reproducibility, parameters within 1e-9 relative across languages). Companion of `regimes.md` (Viterbi labels with fixed parameters).

**Plain idea.** Viterbi labels days with a model whose parameters are known. Baum-Welch estimates those parameters (how sticky each regime is, and the mean and spread of returns in each) from the returns alone. It is the EM algorithm: guess the parameters, work out how likely each day is to be in each regime, re-estimate the parameters from those weights, and repeat until the likelihood stops improving. Results are descriptive; nothing here is a forecast.

Sources:
- [Rab89] L. R. Rabiner, "A tutorial on hidden Markov models and selected applications in speech recognition", *Proceedings of the IEEE* 77(2), 1989, 257-286, sections III.A (scaled forward-backward), III.C (re-estimation, eqs. 40a-40c) and V.A (scaling) (not opened in this session). Evidence class: paper, recalled.
- [DLR77] A. P. Dempster, N. M. Laird, D. B. Rubin, "Maximum likelihood from incomplete data via the EM algorithm", *JRSS B* 39(1), 1977, 1-38 (monotone likelihood) (not opened). Evidence class: paper, recalled.
- Hand check: with one state the first M-step gives the sample mean and the population standard deviation, and the second leaves them unchanged, so the run stops at iteration 2 (`baumwelch_j-0001`). Evidence class: hand calculation.

## `research.regime.baum_welch`

### Inputs

`observations` (`y`, length `T >= 2`); start values `initial` (`K`), `transition` (`K x K`), `means`, `sds` (`K`, `sds > 0`); optional `tolerance` (default `1e-10`, `> 0`) and `max_iterations` (Integer, default 1,000, `1 <= max_iterations <= 10,000`).

### Checks, in order

`E_LIMIT` (J-W2-14: `K > 16`, `max_iterations > 10,000`, `T > 1,000,000`, `T K > 10,000,000`); F-2; shapes, `T < 2`, `K < 1`, `max_iterations < 1`: `E_INPUT`; negative probability, a row of `initial` or `transition` summing to other than 1 within `1e-9`, `sd <= 0`, `tolerance <= 0`: `E_DOMAIN`; degeneracies during the run (J-W2-13): `E_DOMAIN`.

### E-step (scaled forward-backward, at parameters `theta`)

`b_t(j)` = normal density of `y_t` with mean `mu_j`, sd `sigma_j`. Forward: `ahat_0(j) = pi_j b_0(j)`; for `t >= 1`, `ahat_t(j) = (sum_i a_{t-1}(i) A_ij) b_t(j)`; `c_t = sum_j ahat_t(j)` (`c_t = 0` is `E_DOMAIN`); `a_t = ahat_t / c_t`. Backward: `beta_{T-1}(i) = 1`; `beta_t(i) = sum_j A_ij b_{t+1}(j) beta_{t+1}(j) / c_{t+1}`. Then `gamma_t(i) = a_t(i) beta_t(i)`, `xi_t(i, j) = a_t(i) A_ij b_{t+1}(j) beta_{t+1}(j) / c_{t+1}`, and `loglik(theta) = sum_t log c_t`. Sums run over ascending indices.

### M-step

`pi_i = gamma_0(i)`; `A_ij = sum_{t<T-1} xi_t(i, j) / sum_{t<T-1} gamma_t(i)` (zero denominator `E_DOMAIN`); `mu_i = sum_t gamma_t(i) y_t / sum_t gamma_t(i)`; `sigma_i^2 = sum_t gamma_t(i) (y_t - mu_i)^2 / sum_t gamma_t(i)` with the new `mu_i` (`<= 0` is `E_DOMAIN`).

### Iteration (J-W2-11)

E-step at the start values gives `L_0`. Iteration `k`: M-step, then E-step at the new parameters giving `L_k`; gain `L_k - L_{k-1}`. Stop at the first `k` with gain `< tolerance` (`converged = true`) or at `k = max_iterations` (`converged = false`). No variance floor, no relabelling.

### Outputs

`initial`, `transition`, `means`, `sds` (the parameters of the last E-step), `log_likelihood` (its `L_k`), `iterations` (`k`, exact), `converged` (exact). Tolerances J-W2-9: parameters absolute `1e-12` plus relative `1e-9` (each case's `tolerance_limit`), `log_likelihood` class `likelihood_sum`.

## Property tests (each language, own data)

- The log-likelihood never falls by more than `1e-9 |L|` from one iteration to the next ([DLR77]).
- `K = 1` stops at iteration 2 with the sample mean and population sd.
- Two runs of the same binary on the same input give identical IEEE-754 bytes of every output (12.10 A4, bit-reproducible).
- Permuting the states of the start values permutes the fitted states the same way.

## Convergence and limit cases

| Case | Behaviour | Check |
|---|---|---|
| Stop iteration across builds | Same in every build because each golden's stop tests are decided by at least `1e-11` (J-W2-12) | Generator asserts the margin for every gain it evaluates |
| Slow EM near a flat optimum | Gains shrink geometrically; parameters at the stop sit at a distance of order `sqrt(tolerance)` from the maximum, identical across builds because the iteration is the same | `baumwelch_j` cases stop with gains near `1e-7` to `1e-9` |
| Collapse onto one point | Variance update goes to 0 | Constant-series golden is `E_DOMAIN` |
| Underflow | Densities far in a tail underflow in binary64 but not in the 50-digit oracle | Goldens keep every observation within 6 sd of some state; a build may compute `b_t` in logs and rescale, as long as the iteration is the one above |
| `max_iterations` reached | `converged = false`, parameters of the last E-step | `baumwelch_j-0003` (5 iterations) |

## Limitations

Gaussian emissions, one series, maximum likelihood from given start values (a local maximum; no restarts). The A4 recovery run (T = 5,000, plan 12.10) and the Markov-switching AR(1) are research-lane items (gap G8, G12). Labels and parameters are in-sample and descriptive; they never feed a trading signal at time `t`.
