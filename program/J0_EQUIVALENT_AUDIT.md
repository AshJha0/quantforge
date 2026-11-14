# Independent audit of the "equivalent" mutant claims (stage J, J-0 and J-0c)

The auditor did not write the code or the claims. Sources were read at `stage-j` (acdd07e).

Method. Rust: a throwaway copy of `hedge.rs` with a runtime switch per mutant, run on a seeded
random search (300 cases, n = 1..5 instruments, columns up to 1e-6 near-collinear, lambda 0 or
positive) plus hand-built cases. Python: each mutation applied to a copy of `variance.py`, run on
seven workloads (garch_fit x2, garch_estimate NORMAL x3, STUDENT_T x1, one in basis-point scale) and
hand-built varswap/VIX inputs. Nothing in the repository was edited. AGREE = no output difference
above 1e-9 relative and no change of error status found, plus a reason none can exist. DISAGREE = a
concrete input where the mutant differs.

## Summary

| Module | Claims checked | AGREE | DISAGREE |
|---|---|---|---|
| hedge.rs (18 entries) | 18 | 7 | 11 |
| var.rs (order_statistic x3, floor_lr) | 4 | 4 | 0 |
| variance.py (48 mutant groups sampled of 91) | 48 | 42 | 6 |

## hedge.rs

`polish` is not only an accelerator. On case A the original returns Ok because `polish` is tried at
sweep 63; every mutant that breaks or removes that call returns E_NO_CONVERGENCE.

Case A (5 rows, 4 instruments):
`a = [[0.06452333649029651, 0.42367816317235063, 0.4236560454811379, 0.42364098535829753],
[0.2152159902079146, 0.21521075185620386, 0.14812324400176635, 0.1480935238690613],
[0.11760969739417759, 0.11760514338479665, -0.3067217067624666, -0.306761385865427],
[0.24936890745714102, -0.34829343966111903, -0.42467215863102337, -0.4247066591314843],
[0.39511830312956386, 0.3115634021783298, 0.3115422984456242, 0.3115354464695181]]`,
`b = [0.47846487040675223, -0.17730671622319183, 0.2750276985583118, -0.30931612482738524, 0.12307859374017927]`,
`weights = [0.5066255997901173, 0.929824446642092, 0.2847009500015133, 0.274103313367548, 0.11666851217794064]`,
`costs = [0.16754907601671443, 0, 0, 0]`, `lambda = 0.007895753744258438`. Original Ok; mutants
marked A return E_NO_CONVERGENCE.

Case B (lambda 0, costs [0,0], weights [1,1], a = identity 2x2, b = [-1, 5]): original x = [1, -5].
With `polish -> Some(vec![1.0])` the length-1 candidate passes `conditions_hold` (it reads only
`q[0][0]`), becomes x, and `residual` indexes x[1]: panic. Case B' (b = [1, 5], x = [-1, -5]) does the
same for `Some(vec![-1.0])`.

| Line | Mutant | Verdict | Evidence |
|---|---|---|---|
| 56:5 | polish -> None | DISAGREE | A |
| 56:5 | polish -> Some(vec![1.0]) | DISAGREE | A; B panics |
| 56:5 | polish -> Some(vec![-1.0]) | DISAGREE | A; B' panics |
| 56:61 | `!=` -> `==` | DISAGREE | A; another random case is Ok in both but x differs by 2.2e-6 relative |
| 66:25 | `-` -> `+` | DISAGREE | A |
| 66:25 | `-` -> `/` | DISAGREE | A |
| 66:19 | delete `-` | DISAGREE | A |
| 66:34 | `*` -> `+` | DISAGREE | A |
| 66:34 | `*` -> `/` | AGREE | `signum` is +-1 (1 for 0.0), so `pen / sg == pen * sg` bit for bit |
| 71:23 | `!=` -> `==` | DISAGREE | A |
| 128:29 | `>` -> `>=` | AGREE | at `rest == pen` the branch gives -(0)/q = 0, same as the else |
| 130:28 | `<` -> `<=` | AGREE | same at `rest == -pen` |
| 135:34 | `-` -> `+` | AGREE | stopping measure only; 300 cases identical (a case that would stop early waits for the next polish: slower, same output) |
| 138:29 | `\|\|` -> `&&` | DISAGREE | A (polish at sweep 63 is the only success) |
| 138:23 | `==` -> `!=` | AGREE | polish tried at nearly every sweep; an accepted candidate satisfies the conditions; 300 cases identical |
| 138:18 | `%` -> `/` | AGREE | polish at sweeps 4032-4095 and at `moved == 0`; 300 cases identical; slower, and equal only if descent survives that long |
| 138:18 | `%` -> `+` | DISAGREE | `sweep + 64 == 63` never holds, polish only at `moved == 0`: A |
| 138:38 | `==` -> `!=` | AGREE | polish at every moving sweep; 300 cases identical; the `moved == 0` break becomes unreachable, so a failure takes 2e6 sweeps instead of one |

## var.rs

| Line | Mutant | Verdict | Reason |
|---|---|---|---|
| 34:19 | `-` -> `+` (`losses[n - 1]`) | AGREE | branch needs `w = n - n*c <= 0`. For c <= 1 - 2^-53 and n >= 1 the product rounds below n (power of two: exact; otherwise the error exceeds half a spacing), so w > 0. Empty input is rejected before |
| 34:19 | `-` -> `/` | AGREE | same dead branch |
| 38:14 | `<` -> `<=` | AGREE | `m = floor(w) <= n/2 < n` because c >= 0.5 and n >= 1 |
| 167:11 | `<` -> `<=` (floor_lr) | AGREE | differs only at lr exactly 1e-12. lr is a difference of terms of size >= 2^-39, so a multiple of 2^-91, while 1e-12 has an odd mantissa at 2^-92; the all-zero-term corner gives n*k*2^-52, also not 1e-12. Not proven for every input; no counter-example |

hedge_solvers.rs: the J-0 file makes no equivalence claim there, so nothing to audit.

## variance.py (J0C sample)

"Tol" means the outputs moved by at most 4.2e-10 relative on the workloads.

| Line | Mutant | Verdict | Evidence |
|---|---|---|---|
| 110 | `<=` -> `<` | AGREE | equal values give 0 < positive RHS, so both break |
| 110 | `values[0]` -> `values[1]` | AGREE | identical. Theoretical gap: if values[1] is inf the mutant stops at once; needs three or more infinite start vertices, not found |
| 116, 133, 323, 340, 341, 412 | `strict=True` -> `False` | AGREE | zipped lists have equal length by construction |
| 120, 123, 124, 127, 129 | `<`->`<=`, `>=`->`>` | AGREE | identical on all workloads; exact float ties only |
| 141 | `x >= 0` -> `> 0` / `>= 1` | AGREE | identical; branches differ by an ulp |
| 156 | `r / r`, `* len` | AGREE | tol (<= 3e-15) |
| 161 | `persistence - alpha` -> `+` | DISAGREE | `garch_fit` on 120 heavy-tailed returns (seed 7 of the audit generator): log-likelihood differs by 2.9e-5 relative |
| 166 | `and`->`or`, `> 0`->`>= 0` | AGREE | identical; exp is positive, inf handled |
| 176 | start omega `*` -> `/` | AGREE | tol (1.2e-15) |
| 176 | start omega `*` -> `+` | DISAGREE | `garch_fit` on 300 returns (seed 1 generator): log-likelihood differs by 9.5e-4 relative, so the multi-start search does not always reach the same optimum |
| 177 | 0.5 -> 1.5; 2000 -> 2001 | AGREE | tol / identical |
| 178 | `<` -> `<=` | AGREE | identical |
| 182, 183 | polish steps; 4000 -> 4001 | AGREE | identical |
| 185 | code or message of the E_NO_CONVERGENCE raise | DISAGREE | reachable: `garch_fit([1e200]*30, "SAMPLE")` raises E_NO_CONVERGENCE (squares overflow, sample is inf, every start is inf). A mutant with another code raises that code. `garch_estimate` has a finite guard; `garch_fit` has none |
| 192 | NU_MAX 500 -> 501 | AGREE | tol (7.6e-10) |
| 198 | `x < 10` -> `<= 10` | AGREE | identical |
| 198 | `x < 11` | AGREE | tol (2.7e-10) |
| 202 | `/ 132` -> `/ 133` | AGREE | tol (3.2e-10) |
| 214, 215, 217 | placeholders 0.0 -> 1.0 | AGREE | nu, c, dc are read only under `if student` |
| 286 | `persistence - alpha` -> `+` | AGREE | tol (3.2e-10) after Newton polish |
| 288 | nu map `NU_MAX - 2` -> `+ 2` | AGREE | tol (4.2e-10) |
| 301, 303, 304, 305 | start omega, start nu, step/iterations, `<=` | AGREE | tol / identical |
| 309, 310 | polish step, 4000 -> 4001 | AGREE | identical |
| 312 | unit scales 1.0 -> 2.0 | AGREE | identical; only moves the stop threshold 2x |
| 334 | `range(60)` -> `61` | AGREE | identical |
| 339 | `/` -> `*` in `rel` | DISAGREE | `garch_estimate(r, "SAMPLE", "NORMAL", True)` on 400 returns with standard deviation about 100 (basis points; seed 3 generator times 1e4). Original Ok (omega 127.32, alpha 0.1167, beta 0.8566). Mutant E_NO_CONVERGENCE: `rel` multiplies the omega step by `sample` (about 1e4) and the step noise stays above 1e-12 |
| 342 | `<` -> `<=` | AGREE | identical |
| 342 | `< 1.000000000001` | AGREE (weak) | tol (4.2e-10) on three converging workloads; a flat-nu STUDENT_T case could not be tested (baseline E_NO_CONVERGENCE) |
| 349 | `< 0` -> `<= 0` | AGREE | identical; an exactly zero eigenvalue is a singular Hessian |
| 327/328 | interior guard | not claimed equivalent | marked "not killed"; bounds loosened to 1e-5 gave identical output |
| 418 | `"PUT"` -> `"XXPUTXX"` | AGREE | identical fair strike; `black` tests only `== "CALL"` |
| 422 | `fair < 0` -> `<= 0` | DISAGREE | `varswap_fair_strike(2026-01-01, 2027-01-01, spot 100, rate 0, div 0, puts [1.0], calls [1e6], vols [(1.0, 0.01), (1e6, 0.01)], step 0.5, strike 0, notional 1)`: both options price exactly 0, so fair = 0.0. Original returns (0.0, 0.0, 0.0); mutant raises E_DOMAIN |
| 536, 537 | `len(ks) == 1` -> `2`; `gap = 0.0` -> `1.0` | AGREE | ks always has at least 3 strikes |
| 559 | `bracket < 0` -> `<= 0` | DISAGREE | `vix_index((43200, 0.0, S), (86400, 0.0, S))`, S = strikes 99, 100, 102 with quotes bid = ask: 99 put 1e-5 call 10.00001; 100 put 0.001 call 1.601; 102 put 5.0 call 0.04083039237832999 (found by an ulp scan). v1 is exactly 0.0 and the second weight is 0 (n1 = 30 days), so bracket = 0.0. Original returns (0.0, 0.0, 0.0); mutant raises E_DOMAIN |

Not sampled: 43 of the 91 survivors, mostly the 13 interior-guard mutants (327/328, claimed "not
killed", not "equivalent") and the remaining parameter variations in the families above.

## Consequences

Keep only the 7 AGREE rows in the hedge.rs list. Case A kills nine of the eleven DISAGREE mutants
(polish -> None, 56:61, the 66 and 71 mutants, 138:29, 138:18 `+`); cases B and B' kill the two
`Some(vec![+-1.0])` mutants. In J0C, entries 161, 176 (`+` form), 185, 339, 422 and 559 are
killable by the inputs above; 185, 422 and 559 are plain error-status tests.
