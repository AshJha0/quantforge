# Root finders

Spec version 1.0.0. Status: Specified.

All three find `x` with `f(x) = 0`, with `f` from `test-functions.md`. Every result carries the
diagnostics that `architecture/numerical-standards.md` asks for.

## Common inputs and outputs

Inputs: `function`, `x_tol` (default 1e-12), `f_tol` (default 0), `max_iter` (default 200).
Output: `root`. Diagnostics, always present on success: `iterations`, `residual` (`f(root)`),
`termination` (`X_TOL`, `F_TOL` or `EXACT`). Only `root` is compared; diagnostics are checked for
presence, because iteration paths may differ by a step.

Checks, in order: `x_tol <= 0`, `f_tol < 0` or `max_iter < 1`: `E_INPUT`. Then the method's own.
`max_iter` reached without meeting a test: `E_NO_CONVERGENCE`. An evaluation of `f` that is not finite:
`E_NON_FINITE`.

## `core.root.bisection`

Inputs add `a`, `b` with `a < b` (else `E_INPUT`). If `f(a)` or `f(b)` is exactly 0, return that end
point, with `EXACT`. If `f(a) f(b) > 0` (compare signs, do not multiply): `E_NOT_BRACKETED`.

Repeat: `m = a + (b - a)/2`. If `f(m) = 0` stop with `EXACT`. Keep the half with the sign change.
Stop with `X_TOL` when `(b - a)/2 <= x_tol`, or `F_TOL` when `|f(m)| <= f_tol`. Return `m`. Each
midpoint is one iteration.

## `core.root.brent`

Same inputs and checks. Brent's 1973 method (`zeroin`): inverse quadratic interpolation, secant, and
bisection fallback, keeping the best point in `b` and a bracket `[b, c]`. Per iteration, with
`tol1 = 2 eps |b| + x_tol/2` and `xm = (c - b)/2`:

1. If `|f(c)| < |f(b)|`, swap `b` and `c`, and set `a` to the old `b`, so that `b` is the best point.
2. Stop with `X_TOL` if `|xm| <= tol1`, with `EXACT` if `f(b) = 0`, with `F_TOL` if `|f(b)| <= f_tol`.
3. If the last step was at least `tol1` and `|f(a)| > |f(b)|`, try a secant step (when `a = c`) or
   inverse quadratic, giving `p/q`. Make `p >= 0` by flipping the sign of `q` if needed, as Brent does. Accept the step only
   if `2 p < min(3 xm q - |tol1 q|, |e q|)`, signed, so that a step the wrong way is rejected. Otherwise bisect.
4. Move `b` by the step, or by `tol1` at least, in the direction of `xm`. Keep the sign change in `[b, c]`.

`eps` is 2^-52. Return `b`.

## `core.root.newton`

Safeguarded Newton. Inputs add `x0`, and optional `a`, `b`, which must both be given or both absent.

Repeat: if `f(x) = 0`, stop with `EXACT`. If `df(x) = 0`: `E_ZERO_DERIVATIVE`. Step `d = f(x)/df(x)`,
`x' = x - d`.

With a bracket: `f(a)`, `f(b)` must differ in sign (else `E_NOT_BRACKETED`), `x0` must lie in `[a, b]`
(else `E_INPUT`), and the bracket shrinks to keep the sign change after each evaluation. If `x'` leaves
the bracket, use the midpoint instead.

Stop with `X_TOL` when `|x' - x| <= x_tol (1 + |x'|)`, or `F_TOL` when `|f(x')| <= f_tol`. Return `x'`.

## Acceptance

Class `root_finding`, on `root` only. Oracle: 50-digit mpmath roots. For `triple_root`, `f` underflows
near the root, so the case asks for 1e-4 and says so. Error cases: no bracket, zero derivative, iteration limit.

Numeric target: for simple roots and `x_tol = 1e-12`, the error is at most 1e-10, in at most 60 bisection
steps on a unit-sized bracket, 20 Brent steps or 20 Newton steps.
