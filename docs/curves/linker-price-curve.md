# Inflation-linked bond priced on a CPI curve

<p class="note">Hand-written page, listed under "Method pages" on the Curves index. Every number below is from the Python build in this repository, run on 2026-11-21 through <code>uv run --locked quantforge batch</code>: golden <code>inflation_d-0013</code> (agreed exactly), plus two requests made for this page on the same inputs (CPI at chosen months, and the same bond with seasonality removed), which have no golden. Measured, local laptop, not the acceptance machine. Inputs are synthetic; the bond is TIPS-like, not a real issue.</p>

Back to [Curves](README.md).

**Plain idea.** An inflation-linked bond pays fixed real coupons scaled by how much a price index has risen since issue. To price it from market curves rather than from a quoted real yield, project the index for each payment date from an inflation curve built on zero-coupon inflation swaps, scale each real cash flow by the projected index ratio, and discount the result on the nominal curve.

**Formal statement** (`specifications/02-curves/inflation.md` 1.0.0, read 2026-11-21).

- CPI curve: `base_month` (already lagged: the last published month the swaps reference), `base_cpi`, zero-coupon swap quotes `{years, rate}` with pillar `I(b + 12n) = I_0 (1 + K)^n`, `ln I` linear in the month index between pillars, the last slope carried on; optional 12 seasonality factors with `I(k) = I_smooth(k) s(k) / s(b)`, which cancel at pillar months so every swap still reprices.
- Reference CPI for a date `d` in month `m` (US TIPS rule, three-month lag, daily interpolation): `ref(d) = I(m-3) + (day(d) - 1) / days_in_month(m) x (I(m-2) - I(m-3))`.
- `infl.linker.price_curve`: `nominal_dirty = sum_k CF_k x ref(d_k) / base_ref_cpi x D(d_k) / D(settlement)`, real cash flows from the bond object. A reference month before `base_month` is `E_OUT_OF_RANGE`. No deflation floor in this stage.
- The companion `infl.linker.price` prices from a quoted real yield and published fixings, with Treasury's rounding of the index ratio (ruling R6-7.5); this page's operation does not round, because its CPI values are projections.

**Worked example** (`inflation_d-0013`). A 4.5% semi-annual linker maturing 2036-08-15, settlement 2026-11-09, `base_ref_cpi` 287.65. CPI curve: base month 2026-08 at 322.15; swaps 1Y 2.65%, 2Y 2.55%, 3Y 2.50%, 5Y 2.45%, 7Y 2.45%, 10Y 2.50%, 20Y 2.55%; seasonality factors from 0.9978 (January) to 1.0018 (April). Discounting on a log-linear SOFR curve.

| Step | Value | By hand |
|---|---|---|
| CPI at 2027-08 (1-year pillar) | 330.686975 | `322.15 x 1.0265`; seasonality cancels at a pillar month |
| CPI at 2026-12 (between pillars) | 325.0684 | log-linear in months, times `s(Dec) / s(Aug) = 0.9997 / 0.9994` |
| Reference CPI on 2036-08-15 | 410.7323 | `I(2036-05) = 410.4627`, `I(2036-06) = 411.0596`, weight `14/31` |
| Index ratio of the final payment | 1.42789 | `410.7323 / 287.65` |
| `nominal_dirty` | 146.61373502120364 | the sum over all coupons and the principal |

Today's index ratio is already `322.15 / 287.65 = 1.11994`: the bond has accrued about 12% of inflation since its base, and that is in every cash flow. Removing the seasonality factors (same request otherwise) gives 146.42706802341064, 0.187 lower: the coupons are paid in February and August, so their reference CPIs are interpolated between November and December, and between May and June; those factors (0.9995, 0.9997, 1.0012, 1.0005) are all above the August base factor 0.9994, so seasonality raises every projected ratio slightly (inferred from the formula).

**Where it goes wrong.**
- The lag. `base_month` must already carry the index lag; a curve whose base is the current calendar month shifts every projection by three months (inferred from the definitions).
- A cash flow whose reference month falls before `base_month` cannot be projected and is refused (`E_OUT_OF_RANGE`) rather than extrapolated backwards.
- Comparing with a market library: QuantLib's inflation curves use other lag and interpolation conventions, so no outside library is run (spec acceptance).

**Sources and evidence.** Spec `inflation.md` (read); US Treasury 31 CFR Part 356 Appendix B for the reference CPI rule (read 2026-11-12 for ruling R6-7.5, per the spec). Golden `inflation_d-0013` is `verified_by` "analytic" (a hand formula; no outside library), tolerance class `interpolation`; the non-finite-input goldens for this operation are in `stage_f/e1_infl.json`. The CPI curve itself is on [Inflation, with seasonality](inflation.md).
