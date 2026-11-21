# Cross-currency basis swap PV

<p class="note">Hand-written page, listed under "Method pages" on the Curves index. Every number below is from the Python build in this repository, run on 2026-11-21 through <code>uv run --locked quantforge batch</code>: goldens <code>xccy_d-0002</code> to <code>-0004</code> (agreed to 3.0e-9 relative) and one request made for this page, the <code>xccy_d-0002</code> trade with its spread set to 0, which has no golden. Measured, local laptop, not the acceptance machine. Inputs are synthetic. The instrument is a constant-notional basis swap, not the market's mark-to-market resetting swap (ruling R1-1).</p>

Back to [Curves](README.md).

**Plain idea.** A cross-currency basis swap exchanges a floating leg in one currency for a floating leg in another, with notionals exchanged at start and end. If both legs were worth par on their own curves the swap would be fair at zero spread, but in practice one leg needs a spread (the basis) to be fair. Once a foreign discount curve has been bootstrapped from those basis quotes, any such swap can be valued: each leg is projected on its own index curve, the foreign leg is discounted on the basis-adjusted curve, and the foreign value is converted at spot.

**Formal statement** (`specifications/02-curves/cross-currency.md` 1.0.0, read 2026-11-21). Domestic USD (`SOFR`), foreign EUR (`ESTR`).

- Schedule: from `start` (a business day on both calendars, else `E_INPUT`), dates `start + 3k` months adjusted modified following on the joint calendar; `months` a positive multiple of 3; accrual `days/360` on both legs.
- Leg value with notional exchanges: `L = N [ sum ((P(s_i)/P(e_i) - 1) + m alpha_i) D(e_i) + D(T) - D(start) ]`, `P` the leg's projection curve, `D` its discount curve, `m` its spread.
- `fx.xccy.pv`: `foreign_leg` on `N_f` with the spread, projected on `foreign_projection` and discounted on `foreign_discount`; `domestic_leg` on `N_f x spot`, flat, on `domestic` for both; `pv = sign x (spot x foreign_leg - domestic_leg)` in USD, `+1` for `RECEIVE_FOREIGN`.
- `fx.xccy.bootstrap` builds `foreign_discount` from basis quotes so each quoted swap has `L_foreign = 0`; the multi-curve version is the `XCCY` curve type of `rates.curve.joint_solve` ([Joint solve](joint-solve.md)).

**Worked example** (`xccy_d-0002`). Receive EUR ESTR - 12 bp on EUR 10,000,000 for 2 years from 2026-11-10, pay USD SOFR flat on USD 10,850,000; spot 1.085 USD per EUR.

| Output | Value | Reading |
|---|---|---|
| `domestic_leg` | 8.1e-10 (USD) | the USD leg projected and discounted on the same curve is worth par: zero up to rounding |
| `foreign_leg` | -51,449.43 (EUR) | the EUR leg at -12 bp, discounted on the basis-adjusted curve |
| `pv` | -55,822.63 (USD) | `1.085 x -51,449.43` |

Where the value comes from. The same trade at spread 0 gives `foreign_leg` -27,655.85. The leg is linear in the spread, so its spread annuity is `(-51,449.43 + 27,655.85) / (-0.0012 x 10,000,000) = 1.9828` (per unit notional), and the spread that makes the foreign leg worth zero is `27,655.85 / (10,000,000 x 1.9828) = 13.95 bp` (computed from the two measured runs). Receiving at -12 bp against a fair +13.95 bp on these synthetic curves gives up 25.95 bp a year on the annuity: `-0.0025948 x 1.9828 x 10,000,000 = -51,449` EUR.

The other two goldens (same curves): pay EUR - 30 bp on EUR 50,000,000 for 5 years gives `pv` +1,321,243.18 USD; receive EUR - 20 bp on EUR 25,000,000 for 10 years gives -1,093,687.58 USD. In each the USD leg is zero to rounding, so the whole value is the foreign leg times spot.

**Where it goes wrong.**
- Using this curve for market trades: the market swap resets the USD notional each period, so the curve bootstrapped here is not the market's cross-currency-implied curve, and must not be described as one (ruling R1-1).
- Discounting the EUR leg on the EUR OIS curve: for USD-collateralised trades the foreign cash flows discount on the basis-adjusted curve; on the OIS curve the basis would vanish from the price (inferred from the construction).
- A start date that is a holiday on either calendar is refused (`xccy_d-0007`, US Veterans Day).

**Sources and evidence.** Spec `cross-currency.md` (read). Goldens `xccy_d-0002` to `-0004` are `verified_by` an independent replay and QuantLib 1.44 (an outside library); the bootstrap golden `xccy_d-0001` by a known truth and an independent replay. Non-finite-input goldens are in `stage_f/e1_fx_1.json` and `e1_fx_2.json`. The curve page is [Cross-currency](cross-currency.md).
