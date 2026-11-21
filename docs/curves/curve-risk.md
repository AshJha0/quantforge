# Curve risk: par buckets, key rates and the Jacobian

<p class="note">Hand-written page, listed under "Method pages" on the Curves index. Every number below is from the Python build in this repository, run on 2026-11-21 through <code>uv run --locked quantforge batch</code> on goldens <code>risk_r2-0001</code>, <code>-0003</code>, <code>-0004</code> and <code>-0031</code>; each agreed with its golden (largest relative difference 2.9e-9; measured, local laptop, not the acceptance machine). Inputs are synthetic.</p>

Back to [Curves](README.md).

**Plain idea.** "What is my DV01?" has several honest answers, depending on what you move. Move the market quotes and rebuild the curve: par risk, which is what a desk can hedge with the same instruments. Move zero rates on a fixed curve: key-rate risk, which is cheaper and easier to aggregate across books. The Jacobian of zero rates against quotes converts one into the other. All three are bump and revalue (ADR-0010), in money per basis point, with the sign of the value change for rates up 1 bp, so a receiver of fixed has negative risk.

**Formal statement** (`specifications/06-risk/par-and-key-rate.md` 1.0.0, rulings R2-A1, R2-A8, R6-1.1 to R6-1.3; read 2026-11-21).

- `risk.curve.par`: bump quote `j` by `h` bp, rebuild with `rates.ois.bootstrap`, revalue; central scheme `(V(+h) - V(-h)) / (2 bump_bp)`. Outputs `par_dv01` (all quotes together) and `par_buckets` (one per quote). Buckets sum to `par_dv01` to first order only.
- `risk.curve.key_rate`, no rebuild. `TRIANGULAR`: bucket `i` shifts the continuously compounded zero rate by `h w_i(t)` with tent weights on key times that sum to 1 at every `t`; `PILLAR`: bucket `i` bumps pillar `i`'s zero rate and re-interpolates. Either way the buckets sum to `zero_dv01`, the parallel zero shift `D(t) exp(-h t)`, to first order.
- `risk.curve.jacobian`: `J[i][j] = dz_i / dq_j` by central differences, `z_i = -ln D(p_i) / t_i` on ACT/365F, quotes on their own day counts. With a local interpolation it is lower triangular; with a global one (monotone convex, monotonic log cubic, tension spline, hybrid) every entry can be non-zero.
- Chain rule: `par_buckets[j] ~ sum_i key_rates_PILLAR[i] J[i][j]`. It holds for `PILLAR` key rates, not for `TRIANGULAR` ones, which move the curve between pillars differently.

**Worked example.** A 25,000,000 two-year SOFR OIS, receive 3.45% fixed, on a 13-quote SOFR curve as of 2026-11-06, log-linear in `D`. Value -24,052.57.

| Measure | Result | Where the risk sits |
|---|---|---|
| `par_dv01` | -4,806.94 | 2Y bucket -4,808.13; 1Y +1.17; 1W +0.027; all buckets beyond 2Y exactly 0 |
| `zero_dv01` | -4,913.22 | a parallel 1 bp zero shift |
| Key rates, `PILLAR` | sum -4,913.22 | 2Y pillar -4,828.70; 1Y -110.67; first pillar (2026-11-19) +27.37 |
| Key rates, `TRIANGULAR` on 1Y, 2Y, 5Y, 10Y, 30Y | sum -4,913.22 | 1Y -56.60; 2Y -4,834.42; 5Y -22.19; 10Y and 30Y 0 |

Three things to read from it.
1. Par and zero DV01 differ by about 2%: a 1 bp move in the par quotes is not a 1 bp move in continuously compounded zeros. The Jacobian's diagonal near two years is 0.9804 (1Y) and 0.9957 (2Y), not 1, and it grows to 1.497 at 30 years on this curve.
2. The chain rule closes. Multiplying the `PILLAR` key rates by the Jacobian column of the 2Y quote gives -4,808.1269 against the par bucket -4,808.1269 (difference 3e-6), and the 1Y column gives 1.17215 against 1.17215. The oracle checks this on every product to 1e-3 of `par_dv01`.
3. Where a bucket lands depends on the bucket scheme. With triangular keys at 1Y, 2Y and 5Y, the swap's 2-year cash flows sit between key dates and part of their risk is shared with the 5Y key (-22.19), although no 5-year instrument is involved. Pillar keys put it on the 2Y pillar and its neighbours. Neither is wrong; a hedge report must say which it used.

**Book-level curve risk.** Cross gamma (`risk.curve.cross_gamma`, second derivatives across tenor pairs) and principal components of curve moves (`risk.curve.pca`) are specified in `specifications/06-risk/book-sensitivities.md`; the GIRR regulatory buckets are on the Curves index under "Risk and capital term structures". The stage K intraday operation `risk.intraday.delta_gamma_bound` is the parallel delta-gamma of a zero-coupon book with an error bound ([LEARN](../../LEARN.md#a-fast-risk-number-with-an-error-bound)).

**Evidence.** Suite `r2/risk_r2` (41 cases), each checked against QuantLib rebuilding its curve from its own `OISRateHelper` quotes after each bump; `TRIANGULAR` against QuantLib `PiecewiseZeroSpreadedTermStructure`; the R6 Jacobian goldens also against a Richardson extrapolation of central differences (spec, Acceptance).
