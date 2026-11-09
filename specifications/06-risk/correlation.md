# Correlation: validation, nearest correlation, implied correlation, dispersion

Spec version 1.0.0. Status: Specified (stage E, E6, spec B). Rulings: `stage-e-rulings-b.md` E-B18 to E-B21.

## `risk.corr.validate`

**Plain idea.** A correlation matrix must be symmetric, have ones on the diagonal, entries in [-1, 1], and be positive semidefinite (no portfolio can have negative variance). Estimated matrices, especially ones assembled pair by pair, often fail the last test.

Input: `matrix` (square array of arrays). Outputs: `symmetric` (exact equality `m_ij == m_ji`), `unit_diagonal` (exact `m_ii == 1`), `in_range` (every entry in `[-1, 1]`), `min_eigenvalue` (smallest eigenvalue of `(M + M^T)/2`, so an asymmetric input still gets one), `psd` (`min_eigenvalue >= -1e-10`), `valid` (all four). Checks: empty or not square: `E_INPUT`. Goldens keep `min_eigenvalue` at least 1e-4 away from 0, so the boolean never depends on rounding.

## `risk.corr.nearest`

**Plain idea.** Replace an invalid matrix by the closest valid correlation matrix. "Closest" is in the Frobenius norm (sum of squared entry changes). The answer is unique, because the valid set is convex.

Input: `matrix`, symmetric (exact equality, else `E_INPUT`), any size from 1. Output: `matrix` `X` minimising `||X - M||_F` over symmetric PSD matrices with unit diagonal, and `frobenius_distance` `||X - M||_F`. Unweighted (ruling E-B18). Any method that converges to the minimiser may be used. The reference is Higham's alternating projections with Dykstra's correction [S1]:

```
Y = M, dS = 0
repeat:  R = Y - dS;  X = P_S(R);  dS = X - R;  Y = P_U(X)
P_S: set negative eigenvalues to 0 (V max(w, 0) V^T);  P_U: set the diagonal to 1
```

stopping as Higham does when the largest of `||X_k - X_{k-1}||_F/||X_k||_F`, `||Y_k - Y_{k-1}||_F/||Y_k||_F` and `||Y_k - X_k||_F/||Y_k||_F` is below `tol`, with `tol <= 1e-12` (ruling E-B31). Returned is `Y` (unit diagonal exactly); it must have smallest eigenvalue `>= -1e-10`, which that stopping rule gives. A valid input comes back unchanged. Matrices that converge slowly (rank-deficient answers) are in the goldens: a 20 by 20 whose answer has 8 zero eigenvalues, and the four cases where QuantLib's own Higham stops early.

Acceptance is a convergence tolerance, not an iteration path: every entry within 2e-5 of the golden, and the distance within 2e-5 (ruling E-B18). The goldens are the minimiser refined to 1e-30 by semismooth Newton on the dual in 40-digit arithmetic, so they do not depend on a BLAS build (ruling E-B41); two independent float solvers (Higham with Dykstra to 1e-15 in the iterate, and a dual quasi-Newton solve after Qi and Sun [S2]) agree to 1e-7 or better. Two common wrong repairs miss by far more than 2e-5 and are wrong-convention checks: clipping eigenvalues and rescaling to a unit diagonal, and alternating projections without Dykstra's correction.

## `risk.corr.implied`

**Plain idea.** If an index's variance is known from its options, and each member's variance too, one average correlation makes the two consistent.

Inputs: `weights` `w_i`, `vols` `sigma_i` (at least two names), `index_vol` `sigma_I`. Output:

```
correlation = (sigma_I^2 - sum_i w_i^2 sigma_i^2) / (sum_{i != j} w_i w_j sigma_i sigma_j)
```

The sum over `i != j` counts each pair twice. The result is not clipped to [-1, 1] (ruling E-B20). Weights must be `>= 0` with at least two positive; a zero weight drops its name (ruling E-B33). Checks: fewer than two names, or lists of different length: `E_INPUT`; then, all `E_DOMAIN`, in this order: a negative weight, a member vol `<= 0`, `index_vol <= 0`, fewer than two positive weights (zero denominator) (rulings E-B33, E-B39).

## `risk.corr.dispersion`

**Plain idea.** A dispersion trade buys variance on the members and sells variance on the index. It profits when members move more than the index, which is when realised correlation is below the correlation implied at the strikes.

Inputs: `weights`, `vol_strikes` `K_i`, `index_vol_strike` `K_I`, `realized_vols` `s_i`, `index_realized_vol` `s_I`, `vega_notional` `N`. Variance notionals (ruling E-B21): `N_i = N w_i / (2 K_i)` long, `N_I = N / (2 K_I)` short (each leg about `N w_i` of vega at its strike).

```
pnl = sum_i N_i (s_i^2 - K_i^2) - N_I (s_I^2 - K_I^2)
```

Outputs: `pnl`, `implied_correlation` (the formula above at the strikes), `realized_correlation` (the same at the realised vols), `constituent_variance_notionals`, `index_variance_notional`. Checks: lists of different lengths or fewer than two names: `E_INPUT`; a strike or realised vol `<= 0`: `E_DOMAIN`.

## Worked examples

- Higham's 3 by 3 [S1]: `M = [[1,1,0],[1,1,1],[0,1,1]]` has eigenvalues `1 + sqrt 2`, 1, `1 - sqrt 2`, so `min_eigenvalue = -0.414214` (`corr_e-0001`). Its nearest correlation matrix has off-diagonals `0.760690` (pairs 1-2 and 2-3) and `0.157298` (pair 1-3) (`corr_e-0002`), the values in [S1].
- Implied (`corr_e-0036`): `w = (0.5, 0.5)`, `sigma = (20%, 30%)`, `sigma_I = 22%`. Numerator `0.0484 - 0.25 (0.04 + 0.09) = 0.0159`; denominator `2 x 0.25 x 0.2 x 0.3 = 0.03`; correlation 0.53.
- Dispersion (`corr_e-0046`): `N = 100,000`, strikes 25% and 30%, index strike 24%, realised 28%, 35% and 22%. `N_1 = 100,000`, `N_2 = 83,333.33`, `N_I = 208,333.33`. P&L `1,590 + 2,708.33 + 1,916.67 = 6,215`. Implied correlation 0.519, realised -0.037: the trade made money because correlation fell.

## Acceptance

Suite `stage_e_b/corr_e`. Validation: `min_eigenvalue` class `interpolation` (1e-10), booleans exact. Nearest: 2e-5 on entries and distance. Implied correlation 1e-12 absolute plus 1e-10 relative; dispersion P&L 1e-12 per unit of vega notional plus 1e-10 relative.

Outside oracle: QuantLib 1.44 `SymmetricSchurDecomposition` on `(M + M^T)/2` (every validation case) and `pseudoSqrt` with `SalvagingAlgorithm.Higham` (repaired matrix `S S^T`) on every nearest case where QuantLib converges. On four harder matrices QuantLib's Higham stops at its own iteration cap with a diagonal up to 2e-2 away from 1; those cases are not counted, and their goldens rest on the two internal solvers. Implied correlation and dispersion have no QuantLib object.

## Sources

- [S1] Higham, N. J., "Computing the nearest correlation matrix: a problem from finance", *IMA Journal of Numerical Analysis* 22(3), 2002, 329-343 (alternating projections with Dykstra's correction; the 3 by 3 example) (not opened)
- [S2] Qi, H. and Sun, D., "A quadratically convergent Newton method for computing the nearest correlation matrix", *SIAM Journal on Matrix Analysis and Applications* 28(2), 2006, 360-385 (the dual problem used for the cross-check) (not opened)
- [S3] Bossu, S., "Introduction to variance swaps" and related dispersion notes, JPMorgan, 2005-2007; Hull, J. C., *Options, Futures, and Other Derivatives*, 10th ed., chapter "Estimating Volatilities and Correlations" (implied correlation from index and member vols) (not opened)
