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
Killed by `empty_rows_are_rejected_even_with_rows_present`: 163:15 (check_system `||` -> `&&`).
Killed by `integer_sized_bound_violation_is_still_enforced`: 340:39 `/` -> `%` (an integer violation
mod scale 1 becomes -0 and the bound is skipped).

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
