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
| GARCH (lines 30-358) | 445 | 530 | 84.0 % | 80.6 % |
| Variance swap + VIX (lines 360-564) | 258 | 264 | 97.7 % | 95.1 % |
| Whole file | 703 | 794 | 88.5 % | 86.1 % |

## The 91 survivors

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
- 161 `persistence - alpha` -> `+`: tolerance-equivalent on the goldens (a different map to beta; the optimum it reaches is the same).
- 166 `and` -> `or`, `> 0` -> `>= 0`: equivalent (`exp` is always positive, and the overflow case is caught as `inf`).
- 176 three start-omega changes; 177 step 0.5 -> 1.5, iterations 2000 -> 2001; 178 `<` -> `<=`; 182 four polish-step changes; 183 iterations 4000 -> 4001: tolerance-equivalent (only the starts and polish settings change; the optimum is the same).
- 185 code and message of the `E_NO_CONVERGENCE` raise: equivalent (unreachable: `objective` returns `inf` rather than failing, and some start always gives a finite value).

### Student-t helpers (lines 192-217)
- 192 `NU_MAX` 500 -> 501: tolerance-equivalent (only the upper map bound for nu; the fitted nu is about 6).
- 198 `x < 10` -> `<= 10` and -> `< 11`: equivalent within 1e-15 (the asymptotic series is accurate at both cut points).
- 202 `/ 132` -> `/ 133`: equivalent within 1e-15 (the x^-10 term is below 1e-14 for x >= 10).
- 214, 215, 217 the normal-branch placeholders 0.0 -> 1.0: equivalent (nu, c and dc are not read when `student` is false).

### garch_estimate (lines 271-349)
- 286 `persistence - alpha` -> `+`; 288 three changes to the nu map; 301 three start-omega changes; 303 five start-nu changes; 304 step and iteration changes; 305 `<` -> `<=`; 309 three polish-step changes; 310 iterations 4000 -> 4001: tolerance-equivalent (Newton polishing takes any nearby start to the same interior optimum, and `test_estimate_properties` checks that optimum).
- 312 the three unit `scale` entries 1.0 -> 2.0: tolerance-equivalent (they only scale the 1e-12 Newton stop test).
- 323, 340, 341 `strict=True` -> `False`: equivalent (equal lengths).
- 327 and 328 the interior guard (13 mutants: comparison, and/or, bound and index changes): not killed. Each one moves the guard by 1e-6 or loosens it, and the golden estimates sit far inside the region. The `garch_f-0017` no-convergence case fails on the Hessian sign, not on this guard. A kill would need a hand-made series whose optimum lies within 1e-6 of a bound.
- 334 `range(60)` -> `range(61)`: equivalent in practice (Newton converges in under 10 steps).
- 339 `/` -> `*` in `rel`: not killed. With scale >= 1e-4 the product is still below 1e-12 once Newton has converged, so the loop stops one step early at the same point.
- 342 `rel < 1e-12` -> `<=`, and -> `< 1.000000000001`: tolerance-equivalent. The start is already at the optimum to about 1e-10, so the Newton step that is skipped changes nothing at golden tolerance.
- 349 `eigvalsh(h) < 0` -> `<= 0`: equivalent except at an exactly zero eigenvalue.

### Variance swap and VIX (lines 412-559)
- 412 `strict=True` -> `False`: equivalent (equal lengths).
- 418 `"PUT"` -> `"XXPUTXX"`: equivalent (`black` treats any type other than `"CALL"` as a put).
- 422 `fair < 0` -> `<= 0`; 559 `bracket < 0` -> `<= 0`: equivalent except at an exactly zero variance, which no float input reaches through the strip sums.
- 536 `len(ks) == 1` -> `== 2`; 537 `gap = 0.0` -> `1.0`: equivalent. The branch is unreachable: E-B15 requires at least one put and one call, so `ks` always has at least 3 strikes.
