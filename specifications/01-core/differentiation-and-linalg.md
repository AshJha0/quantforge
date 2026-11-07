# Finite differences and linear algebra

Spec version 1.0.0. Status: Specified.

## `core.diff.central`

Inputs: `function` (from `test-functions.md`), `x`, `h` (> 0, else `E_INPUT`), `order` (1 or 2).
Output: `value`.

- Order 1: `(f(x+h) - f(x-h)) / (2h)`
- Order 2: `(f(x+h) - 2 f(x) + f(x-h)) / h^2`

Rounding error grows as `h` shrinks. Any correct way of writing `f` is accepted, such as `x*x*x*x*x` or `pow(x, 5)`, and
these differ by a few ulps of the largest term. With `eps = 2^-52` and `M` the size of the largest terms in `f`, plus
`|x f'(x)|` for the rounding of `x + h`, each case's limit is `8 eps M / h` for order 1 and `32 eps M / h^2` for
order 2. For `poly5` at `x = 1.3`, `h = 1e-4`, that is about 1e-5. A wrong stencil misses by far more.

## Linear algebra

Proven libraries are allowed here (plan rule 4). Matrices are arrays of rows. A ragged or
non-square matrix, or a wrong vector length, is `E_INPUT`.

| Operation | Inputs | Outputs | Errors |
|---|---|---|---|
| `core.linalg.solve` | `a`, `b` | `x`, solving `a x = b` by LU with partial pivoting | `E_SINGULAR` when a pivot is below `1e-14` times the largest absolute entry of `a` |
| `core.linalg.cholesky` | `a`, symmetric | `l`, lower triangular, `l l^T = a`, positive diagonal | `E_NOT_POSITIVE_DEFINITE` on a pivot `<= 0`. Asymmetry above `1e-12` relative: `E_INPUT` |
| `core.linalg.eigen_symmetric` | `a`, symmetric | `values`, ascending | Asymmetry as above: `E_INPUT` |

Eigenvectors are not compared, because their signs are arbitrary.

## Acceptance

Class `quadrature` for differences, with oracle replay of the stencil at 50 digits and the per-case limit
above. Class `interpolation` for linear algebra, against mpmath at 50 digits.

## Sources

Added in R1 (v0.4.1) to meet plan 11.2.4 and 11.5. These are references only: they do not change any rule above. "(not opened)" means the reference was checked from memory for this backfill, not re-read; section numbers are given only where known.

- [S1] Press, W. H., Teukolsky, S. A., Vetterling, W. T. and Flannery, B. P., *Numerical Recipes: The Art of Scientific Computing*, 3rd ed., Cambridge University Press, 2007, chapter 2 (LU decomposition, Cholesky), chapter 11 (symmetric eigensystems), section 5.7 (numerical derivatives) (not opened)
- [S2] Golub, G. H. and Van Loan, C. F., *Matrix Computations*, 4th ed., Johns Hopkins University Press, 2013 (not opened)
