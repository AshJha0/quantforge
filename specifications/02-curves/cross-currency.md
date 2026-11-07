# Cross-currency basis and NDFs

Spec version 1.0.0. Status: Specified (stage D, D3).

Cash flows in a foreign currency, collateralised in the domestic one, discount on a basis-adjusted curve, not on the foreign OIS curve. The cross-currency basis swap quotes pin that curve down. In this stage the domestic currency is USD (`SOFR`) and the foreign EUR (`ESTR`).

## Schedule

From `start` (a business day on both calendars of the two conventions, else `E_INPUT`): dates `start + 3k` months, `k = 1 .. months/3`, each adjusted `MODIFIED_FOLLOWING` on the joint calendar (a business day on both). `months` is a positive multiple of 3, else `E_INPUT`. Accrual `alpha = days/360` on both legs.

## Legs

A leg on notional `N`, projection `P`, discount `D`, spread `m`, with notional exchanges:

`L = N [ sum ((P(s_i)/P(e_i) - 1) + m alpha_i) D(e_i) + D(T) - D(start) ]`

The coupon is the compounded overnight rate over the period with a simple spread; on a curve, `P(s)/P(e) - 1`.

## `fx.xccy.bootstrap`

Inputs: `domestic` (USD OIS curve), `foreign_projection` (EUR OIS curve), `domestic_convention`, `foreign_convention`, `start`, `quotes` `[{months, spread}]`, `interpolation`. Output: `pillars` of the foreign discount curve, one per quote, at its last date.

Each quote is the spread on the foreign leg (EUR `ESTR` + spread, notional 1) that makes the swap par against the USD leg (`SOFR` flat). The USD leg is projected and discounted on `domestic`, so it is worth 0: the condition is `L_foreign = 0`, with `D` the curve being solved. Solve so every quote reprices below 1e-13 (in leg value per unit). `months` strictly increasing, else `E_INPUT`.

## `fx.xccy.pv`

Inputs: `domestic`, `foreign_projection`, `foreign_discount`, `spot` (USD per EUR), `trade` `{start, months, foreign_notional, spread, side}`, `side` `RECEIVE_FOREIGN` or `PAY_FOREIGN`. Outputs: `foreign_leg` (EUR, `N_f`, spread on it, `foreign_discount`), `domestic_leg` (USD, `N_f spot`, flat, `domestic` for both), `pv = sign (spot foreign_leg - domestic_leg)` in USD, sign +1 for `RECEIVE_FOREIGN`. Constant notional: no resets. **Synthetic instrument (R5, ruling R1-1):** this is a constant-notional basis swap. The market EUR/USD cross-currency basis swap resets the USD notional each period (mark-to-market), so the curve solved here is not the market xccy-implied curve and must never be described as one. The MTM-reset variant is row E13 of `../edge-case-register.md`.

## `fx.ndf.pv`

A non-deliverable forward, settled in USD on `payment_date`, on a currency quoted per USD. Inputs: `usd_curve`, `offshore_curve` (the NDF-implied curve of the other currency), `spot`, `trade` `{fixing_date, payment_date, strike, usd_notional, side}`, `fixing` (number or `null`; key required).

`F = fixing` if given, else `spot D_usd(p) / D_off(p)`. `pv = sign N (1 - K/F) D_usd(p)`, +1 for `BUY` (buy USD forward). The USD payoff `N (1 - K/X)` has forward value `N (1 - K/F)` exactly, as `1/X` is a USD-priced asset.

Checks, in order: `payment_date < fixing_date`: `E_DATE_ORDER`. `fixing_date <= as_of` with `fixing` `null`: `E_INPUT`. `spot`, `fixing` or `strike <= 0`: `E_DOMAIN`.

## Acceptance

Bootstrap pillars within 1e-9 of known truth; replay recovers it within 1e-13. PV: 1e-9 per unit notional; QuantLib `OvernightLeg` NPV of the foreign coupons agrees within 1e-6 on 1e7. NDF: class `interpolation`, analytic. Suite `stage_d/xccy_d`.

## Sources

Added in R1 (v0.4.1) to meet plan 11.2.4 and 11.5. These are references only: they do not change any rule above. "(not opened)" means the reference was checked from memory for this backfill, not re-read; section numbers are given only where known.

- [S1] Fujii, M., Shimada, Y. and Takahashi, A., "A note on construction of multiple swap curves with and without collateral", *FSA Research Review* 6, 2010 (collateralised cross-currency discounting) (not opened)
- [S2] Andersen, L. B. G. and Piterbarg, V. V., *Interest Rate Modeling*, Atlantic Financial Press, 2010, vol. 1, chapter on multi-curve and cross-currency (not opened)
- [S3] Hull, J. C., *Options, Futures, and Other Derivatives*, 10th ed., Pearson, 2018, chapter "Swaps" (currency swaps) (not opened)
- [S4] Federal Reserve Bank of New York, SOFR and reference-rate production methodology (statement on the Secured Overnight Financing Rate) (not opened)
- [S5] European Central Bank, *Euro short-term rate (€STR) methodology and policies* (not opened)
