# J-0 equivalent mutants

Mutants that no test can kill because the mutated program behaves identically. One line each.

## var.rs
- `var.rs:34:19 replace - with + in order_statistic`: the `w <= 0` branch is dead, since `c < 1` and `n c` never rounds up to `n` for f64 (checked for c = 1 - 2^-53).
- `var.rs:34:19 replace - with / in order_statistic`: same dead branch.
- `var.rs:38:14 replace < with <= in order_statistic`: `m = floor(n - n c) < n` because `c >= 0.5`, so `m == n` never happens.

## hedge.rs
The objective is strictly convex (full-rank Q checked first), and `solve_hedge` only returns after
`conditions_hold` verifies the first-order conditions of the unique minimiser to 1e-9. `polish` and
the sweep schedule are accelerators: the mutants below change the path or the stopping sweep but
not the returned hedge (verified against the brute-force reference in tests/hedge_mutants.rs).
- `hedge.rs:56:5 replace polish with None`: descent alone reaches `moved == 0` at the same minimiser.
- `hedge.rs:56:5 replace polish with Some(vec![1.0])`: candidate fails `conditions_hold`, descent continues.
- `hedge.rs:56:5 replace polish with Some(vec![-1.0])`: same as above.
- `hedge.rs:56:61 replace != with == in polish`: wrong support gives a rejected candidate; descent continues.
- `hedge.rs:66:25 replace - with + in polish`: wrong right-hand side gives a rejected candidate.
- `hedge.rs:66:25 replace - with / in polish`: same.
- `hedge.rs:66:19 delete - in polish`: same.
- `hedge.rs:66:34 replace * with + in polish`: same.
- `hedge.rs:66:34 replace * with / in polish`: same.
- `hedge.rs:71:23 replace != with == in polish`: returns None for good candidates; descent finishes.
- `hedge.rs:128:29 replace > with >= in solve_hedge`: at `rest == pen` both branches give 0.
- `hedge.rs:130:28 replace < with <= in solve_hedge`: at `rest == -pen` both branches give 0.
- `hedge.rs:135:34 replace - with + in solve_hedge`: changes only the stopping measure; final check unchanged.
- `hedge.rs:138:29 replace || with && in solve_hedge`: polish runs less often; descent still converges.
- `hedge.rs:138:23 replace == with != in solve_hedge`: polish runs at other sweeps; same minimiser.
- `hedge.rs:138:18 replace % with / in solve_hedge`: same.
- `hedge.rs:138:18 replace % with + in solve_hedge`: same.
- `hedge.rs:138:38 replace == with != in solve_hedge`: same.
- `var.rs:167:11 replace < with <= in floor_lr`: differs only at `lr == 1e-12` exactly, which no input produces.
- `var.rs:34:19 replace - with + in order_statistic`: dead branch; `w = n - n c <= 0` needs `c >= 1`, which `check_confidence` rejects (`c in [0.5, 1)`), and no `n < 5000` rounds `n - n c` to 0 even at the largest `c < 1`.
- `var.rs:34:19 replace - with / in order_statistic`: same dead branch.
- `var.rs:38:14 replace < with <= in order_statistic`: `m == n` needs `w >= n`, i.e. `c <= 0`; rejected by `check_confidence`.

## hedge_solvers.rs targeted in J-0 var lane (check against final h3)
- Killed by `tests/hedge_solvers.rs::costs_any_is_true_when_any_single_input_is_given`:
  `hedge_solvers.rs:91:13` and `:92:13 replace || with && in Costs<'_>::any`.
- Not yet targeted (partial h3 missed list): 163:15 check_system, 189:36/189:44/193:16 householder_qr,
  273:23/280:20/281:30 general_inverse, 340:39 dual_active_set.
