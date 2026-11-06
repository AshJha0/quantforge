# Finite differences and linear algebra

Spec version 1.0.0. Status: Specified.

## `core.diff.central`

Inputs: `function` (from `test-functions.md`), `x`, `h` (> 0, else `E_INPUT`), `order` (1 or 2).
Output: `value`.

- Order 1: `(f(x+h) - f(x-h)) / (2h)`
- Order 2: `(f(x+h) - 2 f(x) + f(x-h)) / h^2`

Rounding error grows as `h` shrinks, about `eps/h` and `eps/h^2`. Cases use `h` near `1e-5` and `1e-4`.

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

Class `quadrature` for differences, with oracle replay at 50 digits of the true derivative and a per-case
limit. Class `interpolation` for linear algebra, against mpmath at 50 digits.
