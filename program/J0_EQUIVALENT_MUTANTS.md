# J-0 equivalent mutants

Mutants that no test can kill because the mutated program behaves identically. One line each.

## var.rs
- `var.rs:34:19 replace - with + in order_statistic`: the `w <= 0` branch is dead, since `c < 1` and `n c` never rounds up to `n` for f64 (checked for c = 1 - 2^-53).
- `var.rs:34:19 replace - with / in order_statistic`: same dead branch.
- `var.rs:38:14 replace < with <= in order_statistic`: `m = floor(n - n c) < n` because `c >= 0.5`, so `m == n` never happens.
