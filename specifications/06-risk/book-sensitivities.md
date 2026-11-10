# Book sensitivities: AAD reference, IFT Jacobian, PCA, cross gamma, jump to default

Spec version 1.0.0. Status: Specified (stage F, slice F3, plan items Q3a and F3). Rulings: `stage-f-rulings.md` F-29 to F-30. Suite `stage_f/risk_f3`, written by `oracle/python/gen_stage_f_w2.py` (slice `F3`).

**Plain idea.** Risk on a book of 500 swaps by bumping each of 12 quotes means 12 x 2 x 500 revaluations, and the answer is only as good as the bump size. Algorithmic differentiation (AAD) gets every sensitivity of the whole book from one forward pass and one backward pass, exactly to rounding. The implicit function theorem (IFT) does the same for the curve itself: how each zero rate moves when one quote moves. This page fixes what those numbers are, so that an AAD tape (the Rust reference) and a chain rule (the other three languages) must agree to 1e-8 relative. It also adds three smaller tools: principal components of curve moves, the second-order (cross gamma) matrix, and the loss if a name defaults now.

Risk before stage F was bump and revalue only (ADR-0010). AAD is added here as a reference method, not a requirement: ruling F-29.

## `risk.book.ois_sensitivity` (Q3a)

### Inputs

- `as_of`, `convention` (`SOFR`, `SONIA`, `ESTR`), `quotes` (`[{tenor, rate}]`), `interpolation` (`LOG_LINEAR_DF` or `LINEAR_ZERO`, the sequential builds; another value is `E_INPUT`, ruling F-41): the curve is `rates.ois.bootstrap` of these quotes (`02-curves/ois-curves.md`).
- `swaps`: at least one, else `E_INPUT`; ids unique, else `E_INPUT`. Each has `id`, `tenor_years` (integer in `[1, 100]`, else `E_DOMAIN`, ruling F-41), `fixed_rate` (decimal), `side` (`PAY` or `RECEIVE`, as `ois-curves.md`, else `E_SCHEMA`; ruling F-36). A swap is an OIS on the curve's convention from spot, with the periods of an OIS of tenor `"<n>Y"` on that convention (`ois-curves.md`), notional 1.

### Values

- `pv` of a swap: `s (L_float - K A)`, with `A` and `L_float` the legs of `ois-curves.md`, `K` the fixed rate, `s = +1` for `PAY` (pay fixed), `-1` for `RECEIVE`. Per unit notional.
- `quote_sensitivity.matrix[i][j] = d pv_i / d q_j`, per unit quote (a quote in decimal; multiply by 1e-4 for money per bp). The curve is rebuilt in the derivative: this is par-quote risk (`par-and-key-rate.md`), not zero-rate risk.
- `zero_jacobian.matrix[i][j] = d z_i / d q_j`, with `z_i = -ln D(p_i) / t_i` the continuous ACT/365 zero rate at pillar `i` (`t_i = (p_i - as_of)/365` days).
- `book_pv` and `book_sensitivity` (column sums).

By the IFT, with unknowns `x_i = ln D(p_i)` and residuals `R_j(x, q) = par_j(x) - q_j`: `dx/dq = -(dR/dx)^{-1} dR/dq = (dR/dx)^{-1}`, and `d pv/dq = (d pv/dx)(dx/dq)`. On a sequential build (log-linear) `dR/dx` is lower triangular: entries of `zero_jacobian` above the diagonal are exactly 0 (ruling F-30) and goldens hold them as 0.

### Methods

- **Rust (reference):** reverse-mode AAD on a tape through the pricer, with the curve's adjoint passed through the IFT (`x_bar` solves `(dR/dx)^T lambda = x_bar`; `q_bar = lambda`), so the tape never records the Newton iterations [S1, S2].
- **C++, Java, Python:** the chain rule above with `d pv/dx` and `dR/dx` in closed form or by forward-mode duals. Central differences on `x` are not enough here (1e-9 relative error against a 1e-8 bound with no margin); any exact method is allowed.

### Golden construction

The oracle solves the bootstrap at 40 digits (mpmath) and forms `dR/dx` and `d pv/dx` by central differences with `h = 1e-18` at 40 digits (error below 1e-21), so the goldens are the exact IFT values rounded once. No bump-and-rebuild enters a golden.

The 500-swap book of the T row is drawn from `core.rng` (`01-core/rng.md`), seed 20261109, stream 0, three uniforms per swap in order: `tenor_years = 1 + floor(30 u1)`, `spread = -0.01 + 0.02 u2` added to the swap's own par rate on the curve, `PAY` if `u3 < 0.5`. The book is written into the case input, so a build does not need to regenerate it.

Classes (policy): `aad_sensitivity` (`1e-10` absolute, `1e-8` relative) for PVs and sensitivities; `ift_jacobian` (`1e-11`, `1e-9`) for the zero Jacobian. Both bounds are the T row's, fixed before the stage.

## `risk.curve.pca`

Inputs: `changes` (a `T x N` array of curve changes, rows are days, `T >= 2`, all rows of length `N`, else `E_INPUT`), `components` `k` (`1 <= k`, else `E_DOMAIN`; `k <= N`, else `E_INPUT`).

Method: demean each column; sample covariance with divisor `T - 1`; symmetric eigen decomposition. Eigenvalues are reported in descending order, all `N` of them. Loadings are the first `k` unit eigenvectors; sign rule: the entry of largest absolute value is positive (ties: lowest index). If two of the first `k + 1` eigenvalues (or, when `k = N`, of all) differ by less than `1e-6 lambda_1`, the loadings are not unique and the result is `E_DOMAIN`.

Outputs: `eigenvalues`, `loadings` (`k` arrays of `N`), `explained_ratio` (`lambda_i / sum lambda`, first `k`). Class `interpolation`. Goldens: 40-digit `mpmath.eigsy`; outside check `scipy.linalg.eigh` (rule 11.2.5).

## `risk.curve.cross_gamma`

Inputs: `curve` (a curve object), `product` (`{kind: "OIS", trade}` as `par-and-key-rate.md`), `bump_bp` (`0 < bump_bp <= 100`, else `E_DOMAIN`).

With the `PILLAR` bump of `par-and-key-rate.md` (pillar `i` zero rate moved by `h_i`, `D(p_i) exp(-h_i t_i)`, re-interpolated) and `h = bump_bp` bp:

```
Gamma_ii = (V(+h e_i) - 2 V(0) + V(-h e_i)) / bump_bp^2
Gamma_ij = (V(+h e_i + h e_j) - V(+h e_i - h e_j) - V(-h e_i + h e_j) + V(-h e_i - h e_j)) / (4 bump_bp^2)     (i != j)
```

Outputs: `value` (`V(0)`), `cross_gamma` (`N x N`, symmetric, money per bp squared). Class `interpolation`, with a case limit of 1e-9 absolute (ruling F-36): the four-point formula at 1 bp on a 1e6 notional loses about 1.5e-10 to binary64 cancellation, which a direct evaluation cannot avoid. A build may evaluate it in closed form per exponential term instead (Rust does on log-linear curves).

## `risk.credit.jtd`

The value change if the name defaults now, before any recovery delay: `jtd = value_after_default - market_value`.

| `kind` | `value_after_default` |
|---|---|
| `BOND` (holder) | `recovery x notional` |
| `CDS_PROTECTION_BUYER` | `(1 - recovery) x notional` |
| `CDS_PROTECTION_SELLER` | `-(1 - recovery) x notional` |

Inputs: `positions` (`[{id, kind, notional, recovery, market_value}]`, at least one, else `E_INPUT`); `notional >= 0` and `0 <= recovery <= 1`, else `E_DOMAIN`; another kind is `E_SCHEMA`. Outputs: `jtd` per position, `total`. Accrued premium is left out (a stated simplification: the CDS `market_value` input is taken clean). The FRTB default risk charge (MAR22) nets and weights these; that is not in stage F.

## Convergence and limit cases

| Method | Asserted order | Measured on | Limit case | Reference |
|---|---|---|---|---|
| AAD / IFT sensitivity | exact to rounding; a bump reference converges as `h^4` (Richardson, T row) | `h` = 1e-4, 5e-5 on each quote of the 500-swap book | a payer at par: `pv = 0` and `d pv / d q_own = A` (its own annuity) | golden case "limit" |
| IFT zero Jacobian | exact; structural zeros exact | as above | one pillar: `dz/dq` from the closed-form one-period OIS | hand |
| PCA | direct (symmetric eigen solver) | none | one factor plus noise: `lambda_1` near the factor variance | golden cases |
| Cross gamma | `h^2` against the analytic second derivative | `bump_bp` = 10, 5, 1 | a linear product in `D` (a single discount bond) has `Gamma_ij = 0` for `i != j` outside its two pillars | golden family |

## Acceptance (plan Q3a, F3)

- Q3a (T row): for every swap and quote, `|AAD - ref| <= 1e-10 + 1e-8 |ref|`, and for the zero Jacobian `|J - ref| <= 1e-11 + 1e-9 |ref|`, in all four languages, on the goldens. The Rust AAD is additionally checked against its own bump-and-rebuild in its unit tests (Richardson, `h = 1e-4` and `5e-5`).
- Every case of `risk_f3` passes in all four languages. PCA cases are verified outside by SciPy.
- Deferred to wave 2b, each with a stated reason in the handover: Inflation01 (needs the inflation curve's jacobian), dividend and borrow sensitivity (reuse of `risk.vol.bump_greeks` with new bump targets), correlation sensitivity (copula pricer, R7).

## Sources

- [S1] Giles, M. and Glasserman, P., "Smoking adjoints: fast Monte Carlo Greeks", *Risk*, January 2006 (adjoint method for many sensitivities at once) (not opened)
- [S2] Henrard, M., *Algorithmic Differentiation in Finance Explained*, Palgrave Macmillan, 2017 (AAD through a calibrated curve with the implicit function theorem) (not opened)
- [S3] Litterman, R. and Scheinkman, J., "Common factors affecting bond returns", *Journal of Fixed Income* 1(1), 1991, 54-61 (level, slope and curvature as principal components) (not opened)
- [S4] Virtanen, P. et al., "SciPy 1.0", *Nature Methods* 17, 2020 (`scipy.linalg.eigh`, used as the outside check)
