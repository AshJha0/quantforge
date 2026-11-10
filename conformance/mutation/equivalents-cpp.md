# C++ mutation survivors: equivalent and accepted

Survivors from the PR #29 mutation report (Actions run 42888111129, 12 sampled mutants per module, seed 1, `--unit`).
Line numbers are those of commit 324aeae. One row per mutant, as rule M (`program/STAGE_F_HANDOVER.md`) asks.
Under rule M a row with an empty second-reviewer cell still counts as surviving.

Classes:
- **Equivalent**: no input changes any output.
- **Equivalent (UB)**: the mutant only adds undefined behaviour that no value test can see (an out-of-range write
  that lands in allocator slack). AddressSanitizer would catch it; the mutation job does not run under ASan.
- **Accepted**: not equivalent, but the only inputs that tell it apart need an exact floating-point tie or a
  maximum-likelihood point inside a band of width 1e-6 at a parameter boundary; no test can build one on purpose.

| File:line | Operator | Mutant | Class | Author reason | Second reviewer, date |
|---|---|---|---|---|---|
| credit_options.cpp:109 | `<` to `<=` | `fabs(d) <= tiny` in the Lentz continued fraction | Accepted | At `fabs(d) == tiny` the mutant writes `tiny` over `d`: no change for `d == +tiny`, a sign flip only for `d == -tiny` exactly (an exact tie). Every other `d` takes the same branch. Judged equivalent in stage F; classed here as an exact-tie acceptance. | |
| credit_options.cpp:285 | `-` to `+` | `hi = 2 * strike / (1 + recovery)` | Equivalent | Only the first upper bound of the bracket changes. The doubling loop grows `hi` until `gap(hi) > 0`, and bisection then runs to `mid <= lo or mid >= hi`, that is to adjacent doubles around the one root of the monotone `gap`; the chosen end is the one with the smaller `abs(gap)`. Both bounds give the same root. Judged equivalent in stage F. | |
| multicurve.cpp:385 | `>` to `>=` | `r[j] >= 0.0 ? 1 : -1` | Equivalent | The branch is reached only when `fabs(r[j]) > delta`, and `delta > 0` is checked at entry, so `r[j] != 0` there. | |
| multicurve.cpp:390 | `<` to `<=` | `for (j = 0; j <= n; ++j)` in `solve_split` | Equivalent (UB) | One extra write to `w[n]` and `c[n]`, past the end; the solve reads only `0..n-1`. Undefined behaviour with no effect on any value. | |
| multicurve.cpp:415 | `<` to `<=` | `for (it = 0; it <= 20000; ++it)` | Equivalent | One more IRLS step only when 20,000 steps have not met `change < 1e-17`; the exact split solve that follows replaces `b` whenever its split reproduces itself, and the IRLS fallback is reached only after the split iteration failed. No test case reaches 20,000 steps. | |
| multicurve.cpp:418 | `<=` to `<` | `fabs(r[j]) < delta ? 1.0 : delta / fabs(r[j])` | Equivalent | At `fabs(r[j]) == delta` both branches give weight 1.0. | |
| vol_stats.cpp:458 | `-` to `+` | `1.0 + alpha - beta >= tol` | Accepted | The stationarity part of the interior check (ruling F-11). The Newton polish keeps `alpha + beta < 1` (`feasible`), so the mutant differs only when the polish converges (`done`) to a stationary point with `1 - 1e-6 <= alpha + beta < 1`. A series whose likelihood peaks on the boundary stops the polish (`feasible` fails) and is rejected by `done` in both. | |
| vol_stats.cpp:459 | `>=` to `>` | `nu - 2.0 >= tol * 2.0` | Accepted | Differs only when the fitted `nu` is exactly `2 + 2e-6` in floating point. | |

Killed by `cpp26/tests/test_mut_kill_g.cpp` (stage G), each checked by applying the mutant by hand in a scratch copy
(2026-11-10): vol_stats.cpp:272 (`digamma(nu * 2)` in the score in nu) and vol_stats.cpp:287 (sign of the last term
of the second derivative in nu), both by the Student-t estimate test; vol_stats.cpp:209 (`gain = fbest + fx`) by the
garch_fit test on returns of variance near 1, where the objective is positive and the stop rule is never met.

Scores on the PR #29 sample, counting only killed mutants (rule M: the unsigned rows above still count as surviving):

| Module | Before | After (hand-applied) | Left |
|---|---|---|---|
| garch_varswap_vix (vol_stats.cpp) | 7/12, 58.3% | 10/12, 83.3% | 458, 459 accepted, unsigned |
| rates_d (multicurve.cpp) | 8/12, 66.7% | 8/12, 66.7%; 12/12 once the four equivalent rows are signed | 385, 390, 415, 418 |
| credit_options (credit_options.cpp) | 10/12, 83.3% | unchanged | 109, 285, unsigned |

This is a hand-applied check of the sampled survivors, not a fresh mutation run.
