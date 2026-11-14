# Wave 2, Java lane notes (2026-11-14)

Spec doubts met while building `java25` (`research/Allocation.java`, `cli/OpsResearchW2.java`). None changed a golden outcome.

1. J-W2-14 names "assets 500" but not how a ragged matrix wider than 500 counts. Java raises `E_LIMIT` when a matrix has more than 500 rows or any row wider than 500 (before the shape check), for `covariance`, `pick` and `view_covariance`; Ledoit-Wolf `returns` rows wider than 500 are also `E_LIMIT`. No golden tests this; a ruling would align the builds.
2. Baum-Welch `E_LIMIT` on `K > 16` is read from the length of `initial`, `transition`, `means` or `sds`, whichever is longest; the page names only `K`.
3. Risk parity: the `1e-12` budget-sum test applies only to supplied budgets; the default `1/N` is not tested (for `N = 3` the sum of three `1/3` is exactly 1 anyway, but not for every `N`).
4. Mean-variance with every weight at a bound in the feasible start: Java keeps one index in the free set so the budget multiplier is defined (standard active-set practice); the page is silent.
