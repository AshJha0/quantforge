# Portfolio optimisation: mean-variance, risk parity, Euler risk contributions

Spec version 1.0.0. Status: Implemented (stage J, wave 2) in Python, Rust, Java and C++; every build passes all its cases (15,315 of 15,315, 2026-11-14). CLI contract 1.14.0 (ruling J-W2-1). Rulings: `stage-j-rulings-w2.md` J-W2-2 to J-W2-6, J-W2-14. Suite: `datasets/golden/stage_j/optim_j`, written by `oracle/python/gen_stage_j_w2.py`. Plan row J ("mean-variance, risk parity, factor optimisation"), 14.5 (Euler contributions), 14.6 J-5 and J-8.

**Plain idea.** Mean-variance picks the weights that trade expected return against variance, with a budget and per-asset bounds. Risk parity ignores expected returns and picks weights so that each asset adds a chosen share of the total risk. Euler contributions split a portfolio's volatility into one piece per asset that adds up exactly to the total, which is what both of the others are judged by.

Sources:
- [Mar52] H. Markowitz, "Portfolio selection", *Journal of Finance* 7(1), 1952, 77-91 (not opened in this session). Evidence class: paper, recalled.
- [NW06] J. Nocedal, S. J. Wright, *Numerical Optimization*, 2nd ed., Springer, 2006, chapter 16 (KKT conditions and active-set methods for convex QP) (not opened). Evidence class: textbook, recalled; the generator verifies the KKT conditions of every golden in exact arithmetic.
- [Spinu13] F. Spinu, "An algorithm for computing risk parity weights", SSRN 2297383, 2013 (the system `Sigma y = b / y`, Newton's method, existence and uniqueness) (not opened). Evidence class: paper, recalled.
- [MRT10] S. Maillard, T. Roncalli, J. Teiletche, "The properties of equally weighted risk contribution portfolios", *Journal of Portfolio Management* 36(4), 2010, 60-70 (equal risk contributions; the portfolio's volatility lies between the minimum-variance and the equally weighted portfolio's) (not opened in this session). Evidence class: paper, recalled.
- [Roncalli13] T. Roncalli, *Introduction to Risk Parity and Budgeting*, CRC Press, 2013, chapter 2 (risk budgeting; two-asset result `w_i` proportional to `1/sigma_i`) (not opened). Evidence class: textbook, recalled; the two-asset result is re-derived below by hand.
- [Tas99] D. Tasche, "Risk contributions and performance measurement", working paper, TU Munich, 1999 (Euler allocation) (not opened). Evidence class: paper, recalled; the identity `sum w_i d sigma / d w_i = sigma` is Euler's theorem for a function homogeneous of degree 1.

## Common rules

Check order: `E_PARSE`, `E_SCHEMA`, `E_LIMIT` (J-W2-14), F-2, shapes (`E_INPUT`), then the domain checks of each operation. Symmetry and positive definiteness as ruling J-W2-3.

## `research.portfolio.mean_variance`

### Inputs

`expected_returns` (`mu`, length `N >= 1`), `covariance` (`Sigma`, `N x N`), `risk_aversion` (`gamma > 0`), optional `lower`, `upper` (length `N`; defaults all 0 and all 1).

### Problem

Maximise `mu'w - (gamma/2) w' Sigma w` subject to `sum_i w_i = 1` and `lower_i <= w_i <= upper_i` (J-W2-2). Errors: `gamma <= 0`, `lower_i > upper_i`, `sum lower > 1`, `sum upper < 1`, `Sigma` not symmetric or not positive definite: `E_DOMAIN`.

### Optimality conditions (what every build must satisfy)

With multiplier `nu` for the budget and gradient `g_i = mu_i - gamma (Sigma w)_i - nu`: a free asset (`lower_i < w_i < upper_i`) has `g_i = 0`; an asset at its lower bound has `g_i <= 0`; at its upper bound `g_i >= 0`. Because `Sigma` is positive definite the point satisfying these is unique. Any method that reaches it is acceptable; a primal active-set method [NW06, 16.5] started from a feasible point, with the equality-constrained step solved on the free set, reaches it exactly in finitely many steps. A bound weight is set to the bound exactly (J-W2-4).

### Outputs

`weights`; `expected_return = mu'w`; `volatility = sqrt(w' Sigma w)`; `objective`; `at_bound` (Integers `-1`, `0`, `+1`, exact). Tolerance class `root_finding`.

### Worked example (`optim_j-0001`)

`mu = (0.08, 0.10)`, `Sigma = diag(0.04, 0.09)`, `gamma = 4`, bounds `[-10, 10]` (none binding). Both assets free: `0.16 w_1 + nu = 0.08`, `0.36 w_2 + nu = 0.10`, `w_1 + w_2 = 1`. Subtracting, `0.16 w_1 - 0.36 (1 - w_1) = -0.02`, so `w_1 = 0.34/0.52 = 17/26 = 0.6538...` and `w_2 = 9/26`.

## `research.portfolio.risk_parity`

### Inputs

`covariance` (`N x N`), optional `budgets` (`b`, length `N`, each `> 0`, summing to 1 within `1e-12`; default `1/N` each). Errors as J-W2-5.

### Definition and method

Find `w > 0`, `sum w = 1`, with `w_i (Sigma w)_i / (w' Sigma w) = b_i / sum b` for every `i`. Solve `Sigma y = b / y` (element-wise division) for `y > 0` and set `w = y / sum y` [Spinu13]. Newton's method on `F(y) = Sigma y - b/y` with Jacobian `Sigma + diag(b / y^2)` (positive definite) from `y_0 = sqrt(b_i / Sigma_ii)`, halving the step while any `y_i` would become non-positive, converges; stop when `||F||` is below `1e-14 ||b||` or the step is below `1e-15`. Any other convergent method (for example cyclical coordinate descent) is acceptable.

### Outputs

`weights`, `volatility`, `contributions` (`w_i (Sigma w)_i / sigma`, summing to `sigma`). Tolerance class `root_finding`.

### Worked example (`optim_j-0029`)

Two assets, `sigma = (0.2, 0.3)`, correlation 0.3, equal budgets. Equal contributions `w_1 (Sigma w)_1 = w_2 (Sigma w)_2` reduce to `w_1^2 sigma_1^2 = w_2^2 sigma_2^2` because the cross terms `w_1 w_2 rho sigma_1 sigma_2` are equal on both sides, so `w` is proportional to `(1/0.2, 1/0.3)`: `w = (0.6, 0.4)`, for any correlation.

## `risk.contrib.euler`

Inputs `weights` (length `N`, any sign) and `covariance` (symmetric, J-W2-6). Outputs `volatility`, `marginal` (`(Sigma w)/sigma`), `contributions` (`w_i` times marginal), `shares` (contributions over `sigma`). `w' Sigma w <= 0` is `E_DOMAIN`. Tolerance `simple_analytic`. Example (`optim_j-0041`): `w = (0.5, 0.5)`, `Sigma = diag(0.04, 0)`: `sigma = 0.1`, contributions `(0.1, 0)`.

## Property tests (each language, own data)

- Mean-variance: the KKT conditions above hold to `1e-9` at the returned point; raising an upper bound that binds never lowers the objective; with all bounds wide the result equals the closed form `w = Sigma^-1 (mu - nu 1)/gamma`.
- Risk parity: contribution shares equal `b / sum b` to `1e-10` (J-5); invariant to scaling `Sigma` by a positive constant.
- Euler: contributions sum to `sigma` to `1e-10` relative (J-8); scaling `w` by `c > 0` scales contributions by `c`.

## Convergence and limit cases

| Case | Behaviour | Check |
|---|---|---|
| Active-set iteration count | Finite: each step adds or drops one bound and the objective rises strictly under strict complementarity | Goldens keep a `1e-6` complementarity margin (J-W2-4); the generator verifies the KKT point exactly |
| Risk-parity Newton | Quadratic near the root; the step halving keeps `y > 0` | Oracle solves to `1e-45` at 50 digits and checks shares to `1e-40` |
| Near-singular `Sigma` | Weights become ill-conditioned; definiteness check by Cholesky pivot sign only | Covariance singular in exact arithmetic is an `E_DOMAIN` golden |
| `N = 1` | Mean-variance gives `w = 1` if `lower <= 1 <= upper`; risk parity gives `w = 1` | Property test |

## Limitations

Long-only risk parity only; no transaction costs, turnover limits or cardinality constraints; inputs `mu` and `Sigma` are taken as given (estimation error is the job of `estimation.md` and of the study design). Factor optimisation is a use of mean-variance with `Sigma = B F B' + D` built by the caller (gap G15). Results on Ken French portfolios are labelled "academic portfolio returns, not tradable" (J-5).
