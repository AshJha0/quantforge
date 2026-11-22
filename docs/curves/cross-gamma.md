# Cross gamma on a curve

<p class="note">Hand-written page, listed under "Method pages" on the Curves index. Every number below is from the Python build in this repository, run on 2026-11-21 through <code>uv run --locked quantforge batch</code> on golden <code>risk_f3-0039</code>; the output agreed with the golden to 2.5e-15 relative (measured, local laptop, not the acceptance machine). Inputs are synthetic.</p>

Back to [Curves](README.md).

**Plain idea.** Key-rate DV01 says how value moves when one pillar's zero rate moves by 1 bp. It changes as rates move: that change is gamma. Cross gamma also asks how the DV01 at one pillar changes when another pillar moves. A book that is DV01-flat bucket by bucket can still lose on a large curve move if its gammas are not small, and a hedge that matches DV01 but not gamma has to be re-struck as the market moves.

**Formal statement** (`specifications/06-risk/book-sensitivities.md`, `risk.curve.cross_gamma`, ruling F-36; read 2026-11-21). Inputs: a curve object, an OIS product (as `par-and-key-rate.md`), `bump_bp` with `0 < bump_bp <= 100` (else `E_DOMAIN`, `risk_f3-0045`). With the `PILLAR` bump (pillar `i`'s discount factor times `exp(-h_i t_i)`, curve re-interpolated) and `h = bump_bp` bp:

- `Gamma_ii = (V(+h e_i) - 2 V(0) + V(-h e_i)) / bump_bp^2`
- `Gamma_ij = (V(+h e_i + h e_j) - V(+h e_i - h e_j) - V(-h e_i + h e_j) + V(-h e_i - h e_j)) / (4 bump_bp^2)` for `i != j`

Output: `value` and an `N x N` symmetric matrix in money per bp squared. The four-point formula at 1 bp on a 1,000,000 notional loses about 1.5e-10 to binary64 cancellation, so the case limit is 1e-9 absolute (F-36); a build may use a closed form per exponential term instead, and Rust does on log-linear curves.

**Worked example** (`risk_f3-0039`). A 5-year SOFR OIS, pay 3.60% fixed on 1,000,000, on a 12-pillar log-linear curve as of 2026-11-10. Value -3,649.51.

| Entry | Value (money per bp squared) |
|---|---|
| `Gamma` at the 5-year pillar (2031-11-17) | -0.22064 |
| `Gamma` at the 3-year pillar (2029-11-15) | -0.0052660 |
| `Gamma` between the 3-year and 5-year pillars | -0.00083758 |
| `Gamma` at the 2-year pillar (2028-11-15) | -0.0021980 |
| Every entry at pillars after 5 years, and at the 3-month pillar | 0 |

Why the 5-year entry dominates, by hand (inferred, an approximation). A payer is short a fixed-rate bond: the last fixed coupon plus, through the floating leg's final discount factor, the notional, about `1,000,000 x 1.036` paid at the last pillar. A zero-coupon amount `A D(t)` with `D = exp(-z t)` has `d^2 V / dz^2 = A t^2 D`; per bp squared that is `1.036e6 x 0.83871 x 5.0219^2 x 1e-8 = 0.2191`, with a minus sign for a short position. The golden's -0.22064 differs by under 1% because the earlier coupons and the interpolated discount factors around the last payment add small terms. Pillars after the swap's last payment carry no cash flow, so their rows are exactly 0.

How a desk uses it. The largest gamma here is under a quarter of a currency unit per bp squared; for a 25 bp move at the 5-year pillar the second-order P&L is about `0.5 x -0.22064 x 25^2 = -68.95` beyond what the bucket's DV01 predicts (inferred, second-order Taylor term). The off-diagonal entries say a hedge in the 3-year bucket also changes the 5-year DV01.

**Not shown here.** Cross gamma for bonds or options (the product kind is OIS only in this operation), and parallel gamma of a zero-coupon book, which is `risk.intraday.delta_gamma_bound` (stage K) with an error bound ([LEARN](../../LEARN.md#a-fast-risk-number-with-an-error-bound)).

**Sources and evidence.** Spec `book-sensitivities.md` (read); goldens `risk_f3-0039` to `-0045` (6 value cases, 1 error), each `verified_by` "mpmath 40-digit revaluation" (our own oracle at higher precision, not an outside library); all four builds pass `risk_f3` (spec acceptance, read). The bump rules are those of [Curve risk](curve-risk.md).
