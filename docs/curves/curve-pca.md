# Principal components of curve moves

<p class="note">Hand-written page, listed under "Method pages" on the Curves index. Every number below is from the Python build in this repository, run on 2026-11-21 through <code>uv run --locked quantforge batch</code> on goldens <code>risk_f3-0010</code> and <code>risk_f3-0012</code>; the outputs agreed with the goldens to 6.2e-15 relative, and the error goldens <code>-0035</code>, <code>-0036</code>, <code>-0038</code> and <code>-0057</code> returned their expected codes (measured, local laptop, not the acceptance machine). The daily changes are synthetic, made to have a level, slope and curvature structure; they are not market data.</p>

Back to [Curves](README.md).

**Plain idea.** A curve has many tenors, but day to day they do not move independently: most of the variance is the whole curve moving up or down together (level), most of the rest is the front and back moving in opposite directions (slope), and a little is the middle moving against both ends (curvature). Principal components find those shapes from the data, ranked by how much variance each explains. A desk uses them to reduce a ladder of tenor risks to a few factors, to build scenarios, and to see which hedges cover most of what actually happens.

**Formal statement** (`specifications/06-risk/book-sensitivities.md`, `risk.curve.pca`; read 2026-11-21).

- Inputs: `changes`, a `T x N` array (rows are days, columns tenors), `T >= 2` and every row of length `N` (else `E_INPUT`); `components` `k` with `1 <= k` (else `E_DOMAIN`) and `k <= N` (else `E_INPUT`); at most 200 tenors (`E_LIMIT`, ruling F-42).
- Method: demean each column, sample covariance with divisor `T - 1`, symmetric eigen decomposition. All `N` eigenvalues in descending order; loadings are the first `k` unit eigenvectors, each signed so that its entry of largest absolute value is positive (ties: lowest index).
- Uniqueness: if two of the first `k + 1` eigenvalues (all of them when `k = N`) differ by less than `1e-6 lambda_1`, the loadings are not unique and the answer is `E_DOMAIN`, not an arbitrary choice.
- Outputs: `eigenvalues`, `loadings` (`k` arrays of `N`), `explained_ratio` (`lambda_i / sum lambda`, first `k`).

**Worked example 1: level and slope** (`risk_f3-0010`, 60 days, 5 tenors, 2 components). Eigenvalues `2.0320e-6`, `2.4872e-7`, `1.1272e-8`, `4.35e-10`, `3.27e-10`. Explained: 88.63% and 10.85%.

| Component | Loadings across the 5 tenors | Shape |
|---|---|---|
| 1 | 0.437, 0.438, 0.441, 0.452, 0.467 | all the same sign, nearly equal: level |
| 2 | 0.656, 0.318, 0.001, -0.314, -0.608 | front against back, crossing zero in the middle: slope |

**Worked example 2: ten tenors, three components** (`risk_f3-0012`, 250 days). Explained 85.25%, 14.00% and 0.70%, 99.95% together. The square roots of the first three eigenvalues are 21.6 bp, 8.7 bp and 2.0 bp: the standard deviation of a day's move along each shape (the data are synthetic, so these are not market volatilities). The third loading runs 0.518, 0.171, -0.095, -0.257, -0.343, -0.343, -0.260, -0.082, 0.184, 0.534: both ends against the middle, curvature.

**Why the sign rule and the uniqueness check matter.** An eigenvector is defined only up to sign, and when two eigenvalues are equal any rotation of their vectors is as good. Four builds that each used their linear algebra library's default would disagree on both. The sign rule fixes the first; the `E_DOMAIN` rule refuses the second. Golden `risk_f3-0038` has changes `[1, 0], [-1, 0], [0, 1], [0, -1]`: both columns have sample variance 2/3 and zero covariance, so the two eigenvalues are equal and the answer is `E_DOMAIN` (computed by hand from the definition).

**Using it.** Project a book's key-rate ladder on the loadings to get its exposure to level, slope and curvature (inferred; no operation does this projection). With [Curve risk](curve-risk.md) key rates on the same tenors, a book whose level exposure is hedged can still carry the 14% of variance that slope explains.

**Sources and evidence.** Spec `book-sensitivities.md` (read); Litterman and Scheinkman, "Common factors affecting bond returns", *Journal of Fixed Income* 1(1), 1991 (level, slope and curvature; recalled, cited by the spec as not opened). Goldens `risk_f3-0010` to `-0033` (24 value cases) from a 40-digit `mpmath.eigsy`, with `scipy.linalg.eigh` as the outside check (spec acceptance, read); errors `risk_f3-0034` to `-0038` and `-0057`.
