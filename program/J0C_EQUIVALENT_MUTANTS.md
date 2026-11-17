# J-0c: surviving Python mutants of `quantforge_core/variance.py`

Lane J-0c, 2026-11-14. The `garch_varswap_vix` and `garch_vix` cells both map to
`quantforge_core.variance*` in `conformance/mutation/stages.json`. On PR #39 the 12-mutant CI sample
killed 5 of 12 and 8 of 12.

## Full local run

Runner: `conformance/mutation/python_sampled_mutants.py --profile variance --sample 100000`, which
covers all 794 sites. Kill tests are in `python/tests/test_variance_kills.py`. The run went in passes
to save time. First the `variance_fast` profile ran on all 794 sites. Then `--retry` reran only the
survivors: once with the full `variance` profile, which adds the slow `vol.garch.estimate` goldens
and property tests, and once more after the last fast tests were added. The test set only grew
between passes, so a mutant killed in an earlier pass stays killed.

| Region | Killed | Sites | Score | Wilson 95 % lower |
|---|---|---|---|---|
| GARCH (lines 30-358) | 460 | 530 | 86.8 % | 83.6 % |
| Variance swap + VIX (lines 360-564) | 260 | 264 | 98.5 % | 96.2 % |
| Whole file | 720 | 794 | 90.7 % | 88.5 % |

Corrected 2026-11-14 after the independent audit (`program/J0_EQUIVALENT_AUDIT.md`) disagreed with six
claims. The first pass scored 445, 258 and 703 killed. A rerun of the runner (`variance_fast`,
`--retry` on all 192 sites of the survivor lines) with the new tests killed 17 of the 91: lines 161,
176 (`+` form), 185 (code and message), 288 (two nu-map changes), 327/328 (eight interior-guard
mutants), 339, 422 and 559. The 176 `+` kill comes from a test added after that rerun started; it
was checked by running the mutant (fit -161.07000 against the reference -161.06350).

## The 74 survivors

Each line gives the source line, then the mutant, then the reason it is left. "Equivalent" means no
allowed input changes the output. "Tolerance-equivalent" means the output moves by less than the
golden tolerance, because an optimiser converges to the same optimum. "Not killed" means the
mutant is reachable in principle and is left alive on purpose; the reason is given.

### Nelder-Mead (lines 110-133)
- 110 `<=` -> `<` in the stop test; 110 `values[0]` -> `values[1]` in the stop scale: tolerance-equivalent (the stop threshold is 1e-14 relative, so the end point is the same).
- 116, 133 `strict=True` -> `False`: equivalent (the zipped lists always have the same length).
- 120 `fr < values[0]` -> `<=`; 123 `fe < fr` -> `<=`; 124 `fr < values[-2]` -> `<=`; 127 `fr >= values[-1]` -> `>`; 129 `fc < min` -> `<=`: equivalent except on exact float ties, which none of the objectives produce.

### Sigmoid and garch_fit (lines 141-185)
- 141 `x >= 0` -> `> 0` and -> `>= 1`: equivalent (both branches are the same function; they differ by at most 1 ulp).
- 156 `sample` built with `*` or `r / r`: tolerance-equivalent (`sample` only seeds the starting omega; the multi-start search reaches the same optimum).
- 161 `persistence - alpha` -> `+`: NOT equivalent, now killed by `test_fit_reaches_the_reference_optimum` (heavy-tailed series; the mutant stops short of the scipy reference optimum by about 2e-3 relative).
- 166 `and` -> `or`, `> 0` -> `>= 0`: equivalent (`exp` is always positive, and the overflow case is caught as `inf`).
- 176 start omega `*` -> `+`: NOT equivalent, now killed by `test_fit_reaches_the_reference_optimum` (150 Student-t returns: -161.07000 against -161.06350). 176 the two other start-omega changes; 177 step 0.5 -> 1.5, iterations 2000 -> 2001; 178 `<` -> `<=`; 182 four polish-step changes; 183 iterations 4000 -> 4001: tolerance-equivalent (only the starts and polish settings change; the optimum is the same).
- 185 code and message of the `E_NO_CONVERGENCE` raise: NOT equivalent (reachable: `garch_fit([1e200] * 30)` overflows every start); now killed by `test_fit_overflowing_squares_has_no_finite_likelihood`.

### Student-t helpers (lines 192-217)
- 192 `NU_MAX` 500 -> 501: tolerance-equivalent (only the upper map bound for nu; the fitted nu is about 6).
- 198 `x < 10` -> `<= 10` and -> `< 11`: equivalent within 1e-15 (the asymptotic series is accurate at both cut points).
- 202 `/ 132` -> `/ 133`: equivalent within 1e-15 (the x^-10 term is below 1e-14 for x >= 10).
- 214, 215, 217 the normal-branch placeholders 0.0 -> 1.0: equivalent (nu, c and dc are not read when `student` is false).

### garch_estimate (lines 271-349)
- 286 `persistence - alpha` -> `+`; 288 one change to the nu map (two more are now killed by `test_estimate_pinned_workloads`); 301 three start-omega changes; 303 five start-nu changes; 304 step and iteration changes; 305 `<` -> `<=`; 309 three polish-step changes; 310 iterations 4000 -> 4001: tolerance-equivalent (Newton polishing takes any nearby start to the same interior optimum, and `test_estimate_properties` checks that optimum).
- 312 the three unit `scale` entries 1.0 -> 2.0: tolerance-equivalent (they only scale the 1e-12 Newton stop test).
- 323, 340, 341 `strict=True` -> `False`: equivalent (equal lengths).
- 327 and 328 the interior guard: eight of the 13 mutants (bound constants, the index of `t[0]`, `1e-6 * sample`) are now killed by `test_estimate_pinned_workloads` (pinned current output on four series, one at scale 1e-3). The other five (comparison and sum changes): not killed. Each one moves the guard by 1e-6 or loosens it, and the golden estimates sit far inside the region. The `garch_f-0017` no-convergence case fails on the Hessian sign, not on this guard. A kill would need a hand-made series whose optimum lies within 1e-6 of a bound.
- 334 `range(60)` -> `range(61)`: equivalent in practice (Newton converges in under 10 steps).
- 339 `/` -> `*` in `rel`: NOT equivalent; on returns in basis points the mutant returns E_NO_CONVERGENCE. Now killed by `test_estimate_is_scale_equivariant`.
- 342 `rel < 1e-12` -> `<=`, and -> `< 1.000000000001`: tolerance-equivalent. The start is already at the optimum to about 1e-10, so the Newton step that is skipped changes nothing at golden tolerance.
- 349 `eigvalsh(h) < 0` -> `<= 0`: equivalent except at an exactly zero eigenvalue.

### Variance swap and VIX (lines 412-559)
- 412 `strict=True` -> `False`: equivalent (equal lengths).
- 418 `"PUT"` -> `"XXPUTXX"`: equivalent (`black` treats any type other than `"CALL"` as a put).
- 422 `fair < 0` -> `<= 0`; 559 `bracket < 0` -> `<= 0`: NOT equivalent; an exactly zero variance is reachable (options pricing to 0.0; an ulp-scanned VIX strip). Now killed by `test_zero_fair_variance_is_allowed` and `test_zero_bracket_variance_is_allowed`.
- 536 `len(ks) == 1` -> `== 2`; 537 `gap = 0.0` -> `1.0`: equivalent. The branch is unreachable: E-B15 requires at least one put and one call, so `ks` always has at least 3 strikes.

Note (2026-11-15): the whole `python/` tree was reformatted with `ruff format` in the v0.9.0 PR. Python line numbers in this file, `program/J0_EQUIVALENT_AUDIT.md` and the R6 handovers refer to the code before that commit (`main` at `a148d0e`); the formatting commit is listed in `.git-blame-ignore-revs`.
