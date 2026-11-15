# J-0 equivalent mutants

Mutants that no test can kill because the mutated program behaves identically. One line each.

## var.rs
- `var.rs:34:19 replace - with + in order_statistic`: the `w <= 0` branch is dead, since `c < 1` and `n c` never rounds up to `n` for f64 (checked for c = 1 - 2^-53).
- `var.rs:34:19 replace - with / in order_statistic`: same dead branch.
- `var.rs:38:14 replace < with <= in order_statistic`: `m = floor(n - n c) < n` because `c >= 0.5`, so `m == n` never happens.

## hedge.rs
The objective is strictly convex (full-rank Q checked first), and `solve_hedge` only returns after
`conditions_hold` verifies the first-order conditions of the unique minimiser to 1e-9. The sweep
schedule details below change the path or the stopping sweep but
not the returned hedge (verified against the brute-force reference in tests/hedge_mutants.rs).
- `hedge.rs:66:34 replace * with / in polish`: `signum` is +-1, so `pen / sg == pen * sg` bit for bit (audit AGREE).
- `hedge.rs:128:29 replace > with >= in solve_hedge`: at `rest == pen` both branches give 0.
- `hedge.rs:130:28 replace < with <= in solve_hedge`: at `rest == -pen` both branches give 0.
- `hedge.rs:135:34 replace - with + in solve_hedge`: changes only the stopping measure; final check unchanged.
- `hedge.rs:138:23 replace == with != in solve_hedge`: polish runs at other sweeps; same minimiser.
- `hedge.rs:138:18 replace % with / in solve_hedge`: polish still runs at sweeps 4032-4095 and at `moved == 0`; same output, slower (audit AGREE).
- `hedge.rs:138:38 replace == with != in solve_hedge`: polish at every moving sweep; same output (audit AGREE).

Withdrawn after the independent audit (program/J0_EQUIVALENT_AUDIT.md): 56:5 (None, Some(vec![1.0]),
Some(vec![-1.0])), 56:61, 66:25 (x2), 66:19, 66:34 `+`, 71:23, 138:29, 138:18 `+`. `polish` is not only
an accelerator; these are now targeted by `polish_is_needed_on_near_collinear_columns` (audit case A)
and `identity_hedges_return_full_length_answers` (cases B, B') in tests/hedge_mutants.rs.
- `var.rs:167:11 replace < with <= in floor_lr`: differs only at `lr == 1e-12` exactly, which no input produces.
- `var.rs:34:19 replace - with + in order_statistic`: dead branch; `w = n - n c <= 0` needs `c >= 1`, which `check_confidence` rejects (`c in [0.5, 1)`), and no `n < 5000` rounds `n - n c` to 0 even at the largest `c < 1`.
- `var.rs:34:19 replace - with / in order_statistic`: same dead branch.
- `var.rs:38:14 replace < with <= in order_statistic`: `m == n` needs `w >= n`, i.e. `c <= 0`; rejected by `check_confidence`.

## hedge_solvers.rs targeted in J-0 var lane (check against final h3)
- Killed by `tests/hedge_solvers.rs::costs_any_is_true_when_any_single_input_is_given`:
  `hedge_solvers.rs:91:13` and `:92:13 replace || with && in Costs<'_>::any`.
- Not yet targeted (partial h3 missed list): 163:15 check_system, 189:36/189:44/193:16 householder_qr,
  273:23/280:20/281:30 general_inverse, 340:39 dual_active_set.

## hedge_solvers.rs (J-0 var lane, round 2)
Scoped re-run ~/j0-v5-hs (and a manual mutant check) showed both new tests pass under their target
mutants, so neither is killed:
- 163:15 (check_system `||` -> `&&`): with one row and no columns a later check still returns
  E_INPUT, so the error status is unchanged. Equivalent on observed behaviour for `qp_solve`; not
  proven for `integer_solve` or `select_solve`.
- 340:39 `/` -> `%`: the bound in the test is not handled through `dual_active_set` (a 1-variable
  bound does not reach the scaled-slack path). Still open; needs a general inequality (margin limit).

Equivalent (reason):
- `hedge_solvers.rs:189:36 replace > with ==/</>= in householder_qr` and `189:44 delete -`: the sign
  of `alpha` only picks which of the two valid reflectors `x +- |x| e1` is used; Q and R change sign
  per column, and the null-space basis consumer (line 456) gives the same projector. Differences are
  rounding only, inside test tolerances.
- `193:16 replace -= with +=`: same, `v = x + alpha e1` is the other valid reflector.
- `280:20 replace + with * in general_inverse`: the pivot search then also compares row `k` with
  itself; `>` is false, so `p` is unchanged.
- `281:30 replace > with >= / == in general_inverse`: the input is the active-set Gram matrix
  `B^T G^-1 B`, symmetric positive definite, so every diagonal pivot is positive and the pivot
  choice changes rounding only; `==` cannot hit a zero pivot.
- `307:24 replace + with * in general_inverse`: adds `a[i][i] * inv[i][c]` while `inv[i][c]` is
  still 0.
- `340:39 replace / with * in dual_active_set`: the scaled slack only orders violated constraints
  (and both forms flag the same sign); the method ends at the unique KKT point whatever the order,
  except at `|slack| ~ 1e-12`, below test tolerance.
- `341:33 replace < with <=`: differs only at slack exactly `-1e-12`.
- `380:24 replace > with >=`: `ri == 0` gives `u/0 = +inf` (or NaN), never `< t1`.
- `380:43 replace < with <=`: tie in the dual step ratio; a different index is dropped at an exact
  tie, and the final active set is re-solved, giving the same KKT point.
- `386:28 replace > with >=`: differs only at `zn == dependence * gn` exactly.

Not killed, not shown equivalent (needs a crafted near-singular active set; left open):
- `273:23 replace * with / in general_inverse` (singularity limit `1e-14 * largest`).
- `380:38 replace / with % and * in dual_active_set` (dual step length t1).

hedge.rs scoped re-runs (~/j0-v6-hedge, ~/j0-v7-hedge, ~/j0-v8-hedge, -j 1): all 13 polish/schedule mutants
at 56:5, 56:61, 66:25, 66:19, 66:34 `+`, 71:23, 138:29, 138:18 `+` caught. hedge.rs now 97/104 viable
killed (93.3%); the 7 remaining are the audit-AGREE equivalents above.

## hedge_solvers.rs independent audit (branch stage-j-hs-audit, 2026-11-14)
Each kill confirmed by hand-applying the mutant and running `cargo test --test hedge_solvers` (Windows).
Several "equivalent" claims above were wrong: the scaled qp path (Jacobi scaling plus the final
bound clamp) hid them; a nonzero ridge keeps the solve unscaled.
- KILLED 163:15 `check_system_names_the_shape_error_for_one_row_without_columns` (message asserted).
- KILLED 340:39 `%` `bound_violated_by_an_exact_multiple_of_its_scale_is_enforced_on_the_unscaled_path`.
- KILLED 340:39 `*` (claimed equivalent: FALSE) `bound_almost_parallel_to_an_equality_is_enforced` (scale 1e-7).
- KILLED 341:33 `<=` (claimed equivalent: FALSE, exact tie is reachable) `violation_exactly_at_the_threshold_is_not_enforced`.
- KILLED 273:23 `/` `active_set_on_a_stiff_unscaled_problem_is_not_singular` (Gram ~1e-16).
- KILLED 189:36 `<` and `==`, 189:44, 193:16 (claimed equivalent: FALSE, cancellation in v) `equality_almost_along_an_axis_keeps_its_null_space`.
- KILLED 380:38 `*` and `%` `dual_step_drops_the_constraint_with_the_smallest_ratio` (seeded search case).
- AGREE equivalent: 189:36 `>=` (only m == 0: v = +-norm, no cancellation; confirmed surviving), 280:20, 307:24.
- AGREE up to rounding, not proven: 281:30 `>=`/`==` (pivot choice on an SPD Gram matrix; extreme conditioning could move E_SINGULAR).
- PLAUSIBLE, not proven: 380:24 `>=` (needs r_i == 0 exactly with u_i < 0 from rounding), 380:43 `<=`
  (exact ratio tie; y unique, multipliers may differ in degenerate sets), 386:28 `>=` (exact zn == 1e-12 gn).

## hedge_solvers.rs targeted re-score, branch j2-rustkill (2026-11-15)
Survivors after 377834e (22) audited by hand. Killed by new tests in `tests/hedge_solvers.rs`:
- 880:17 delete `margin_rates` (scaled path) `binding_margin_on_the_scaled_path_uses_the_caller_units`.
- 1930:17, 1931:17 delete `lower` / `upper` in select_solve `selection_passes_each_subset_its_own_bounds`.
- 702:27 `*` -> `+` (split margin row has `2 + n` entries) `margin_spent_by_an_equality_alone_is_infeasible_with_three_instruments`.
- 684:20 `+` -> `-` (split bound row on `p_{n-j}`) `upper_bound_of_a_later_instrument_holds_in_the_split_stage`.

Equivalent, with reasoning:
- 1518:31 `+` -> `*` in minvar_ratio: the back-substitution sum then starts at `q = i`, adding
  `l[i][i] * hedge[i]` while `hedge[i]` is still its initial 0. TRUE equivalent.
- 557:51 `>` -> `>=` in scaled_reduced_rank: `D H D` has unit diagonal, so its largest eigenvalue
  is at least 1 and the limit `1e-12 * scale` is positive; the mutant differs only when a reduced
  eigenvalue equals the limit bit for bit. Equivalent up to an exact float tie (not constructible
  through the Jacobi eigen solver). The R6-6.2 rank-cut fix on stage-j2 may move this line.
- 1932:17 delete `costs` in select_solve: by contract (doc comment, I-33, instrument-selection.md)
  `p` carries no costs, so `p.costs` is `Costs::default()` and the field is the same. Equivalent
  under the precondition. Note: select_solve does not itself reject costs; a caller passing
  them would get them silently ignored (correct code) or a shape error (mutant).
- Split-stage mutants of nonsmooth_minimiser that change only the split objective, not its
  constraints: 661:29 `+` and `/` (delta), 666:69 delete `-`, 667:26 `*`->`+`, 673:48 `-`->`/`,
  673:55 `+`->`-` and `*`, 673:66 `%`->`/`, 673:71 `/`->`%` and `*`, and the sign rule 717:57
  `||`->`&&`, 717:81 `*`->`/`. Reasoning: the split only seeds the sign state. Its constraints are
  intact, so its point x0 is feasible and lies in the orthant of the seeded signs; every later
  sign change either releases a zero (the orthant grows) or fixes at 0 a coordinate already 0, so
  every orthant solve stays feasible and the `return Ok(Some(last))` fallback is never taken. The
  loop stops only when the subgradient test holds at every zero, i.e. at a KKT point, and the
  reduced Hessian is definite (rank check), so that point is the unique minimiser. A wrong seed
  costs only extra iterations against the cap `10 (n + p) + 100`. Equivalent in output except
  (a) at the iteration cap, (b) an extreme `delta` (661 `/` with a huge spectral scale) where the
  split's dependence test may misfire, and (c) for 717:57/81, coordinates with
  `0 < |x0_j| <= 1e-11 max|x0|` forced nonzero by an equality: correct code fixes them at 0, the
  orthant can then be infeasible and the inexact split point is returned. (c) is a possible
  accuracy issue in the correct code, not a test gap; noted, not fixed (tests + docs only).
  Only a planted-cap unit test inside src (iteration count as the observable) could separate them.
- 380:43 `<` -> `<=`: unchanged from the audit above (exact ratio tie, plausible equivalent).

Full n2 run (main a148d0e) survivors 460:45, 461:24, 507:23, 508:21 are caught on this branch by
377834e (targeted run r2); its other survivors are the audit entries above.
