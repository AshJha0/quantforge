# Review request: Cross-currency (QuantForge curve)

You are reviewing one curve of an open-source quantitative finance library. You have no access to its code or repository: everything you may use is below.

Rules for your answer:
- Answer only from the material given here and from standard, citable finance knowledge. Where the material is not enough, write "cannot check" rather than guess.
- Quote the spec line or the exact number you question.
- Return findings as one table with columns: curve, claim, issue, severity (high / medium / low / note), evidence (quote or your working).
- After the table, list the questions you answered "cannot check", and why.
- Your review is a second opinion. It is filed under a labelled "AI review" section and never counts as the human sign-off.

Status: Implemented, not Validated (stage D). Evidence line from the project's status table: 1 golden case.

## Questions

1. Conventions: do the formulas, day counts, calendars, spot and payment lags in the spec match the cited market standard or source? Quote the line.
2. Interpolation and extrapolation: is the stated rule applied consistently, and what happens beyond the last pillar?
3. Tolerances: is each tolerance class justified for the quantity it guards (rate, factor, money)?
4. Edge cases: zero or negative rates, dates on as_of or on expiry, empty inputs, boundaries the cases do not cover.
5. Golden cases: recompute any case you can from its inputs with the spec's formulas. Report any number you get differently, with your working.
6. Outside-library and real-data evidence: does the check really test the same quantity? Is anything claimed beyond what it shows?
7. Anything that looks wrong, inconsistent or missing.

## Spec

### `specifications/02-curves/cross-currency.md`

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
- [S4] Federal Reserve Bank of New York, *Additional Information about Reference Rates Administered by the New York Fed*, section "Calculation Methodology for the TGCR, BGCR, and SOFR" (opened 2026-11-07)
- [S5] European Central Bank, *The euro short-term rate (€STR) methodology and policies* (opened 2026-11-07, title from the PDF; body not read)


## Golden cases (1 of 1 value cases of this curve's operations shown, chosen in file order and skipping cases too large to fit; one JSON object per line; `verified_by` lists the sources that agreed)

```json
{"case_id":"xccy_d-0001","operation":"fx.xccy.bootstrap","inputs":{"domestic":{"as_of":"2026-11-06","interpolation":"LOG_LINEAR_DF","pillars":[{"date":"2026-11-19","discount_factor":0.9986040008603395},{"date":"2026-12-14","discount_factor":0.9959394252774483},{"date":"2027-02-12","discount_factor":0.989673278797288},{"date":"2027-05-12","discount_factor":0.9807770908259003},{"date":"2027-11-15","discount_factor":0.9634397330592425},{"date":"2028-11-14","discount_factor":0.9318539967570951},{"date":"2029-11-15","discount_factor":0.9012037662703272},{"date":"2031-11-13","discount_factor":0.839287128565213},{"date":"2033-11-15","discount_factor":0.7766268603223262},{"date":"2036-11-13","discount_factor":0.6858387444275659},{"date":"2041-11-14","discount_factor":0.5536981725589005},{"date":"2046-11-15","discount_factor":0.449831073617216},{"date":"2056-11-14","discount_factor":0.31789224697028523}]},"foreign_projection":{"as_of":"2026-11-06","interpolation":"LOG_LINEAR_DF","pillars":[{"date":"2026-11-19","discount_factor":0.9991807943650066},{"date":"2026-12-14","discount_factor":0.9976187895421391},{"date":"2027-02-12","discount_factor":0.9939609880010525},{"date":"2027-05-12","discount_factor":0.9888433447909688},{"date":"2027-11-12","discount_factor":0.979288122109086},{"date":"2028-11-14","discount_factor":0.9621077025177938},{"date":"2029-11-14","discount_factor":0.9453565613174705},{"date":"2031-11-12","discount_factor":0.9086167288534558},{"date":"2033-11-14","discount_factor":0.8680406595029002},{"date":"2036-11-12","discount_factor":0.8042612131003805},{"date":"2041-11-13","discount_factor":0.7039030892201986},{"date":"2046-11-14","discount_factor":0.6196603907598699},{"date":"2056-11-14","discount_factor":0.5087217489424134}]},"domestic_convention":"SOFR","foreign_convention":"ESTR","start":"2026-11-10","quotes":[{"months":12,"spread":0.0010096188836398502},{"months":24,"spread":0.0013947896204213187},{"months":36,"spread":0.001684807530495905},{"months":60,"spread":0.002070064712703492},{"months":84,"spread":0.0022613526114204406},{"months":120,"spread":0.002449281536013717}],"interpolation":"LOG_LINEAR_DF"},"expected":{"status":"ok","outputs":{"pillars":[{"date":"2027-11-10","discount_factor":0.9784018610254287},{"date":"2028-11-10","discount_factor":0.9595837618865133},{"date":"2029-11-13","discount_factor":0.9405577315984667},{"date":"2031-11-10","discount_factor":0.8991982163399188},{"date":"2033-11-10","discount_factor":0.8543577792163143},{"date":"2036-11-10","discount_factor":0.7844757636238187}]}},"tolerance_class":"interpolation","tolerance_limit":{"absolute":1e-09,"relative":0.0,"reason":"stage-b-targets: discount factors within 1e-9; curve solves stop at 1e-13 in rate"},"verified_by":["known-truth","independent-replay"]}
```

## Outside-library evidence and limits (from the project's own page)

1 golden cases with status ok in `datasets/golden/stage_d` for `fx.xccy.bootstrap`, by `verified_by`:

| Operation: sources | Cases |
|---|---|
| fx.xccy.bootstrap: known-truth, independent-replay | 1 |

Limits: one input per operation, synthetic unless labelled real; charts plot output index, not calendar time; the specs are in `specifications/`.

## Real-data reconciliation

- No free data: the stage C/D data surveys (LEARN.md) found no free cross-currency basis quotes. No reconciliation is possible without paid data, which the project does not buy.

## Rulings that name this curve's operations

- (stage-d-rulings.md) | D39 | `fx.xccy.bootstrap`, `fx.xccy.pv` with `start` before `as_of` | `E_OUT_OF_RANGE`. Case `rulings_d-0014` |
