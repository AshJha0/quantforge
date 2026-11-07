# Spec questions from the Python implementation

Each item is a place where the spec is unclear, or where a golden case disagrees with it. Nothing here
was tuned to fit. The code follows the spec text, and the choice made is stated.

## Resolved by the spec corrections on `stage-a` (363e5a8)

- Q1, `add_tenor` end of month: `calendars.md` now says on or after the last business day, with a calendar
  month-end rule for `UNADJUSTED`. The code changed to match.
- Q2, `start == end` on `THIRTY_E_360_ISDA`: `daycount.md` keeps 0 and the golden case changed. No code change.
- Q3, moments at a large offset: `statistics-and-time-series.md` now specifies the shift by the first value,
  which the code already did.

No golden case is known to disagree with the spec now.

All of the earlier open choices, Q4 to Q21, are now settled by `specifications/01-core/rulings.md`, or by the corrected
contract and `root-finders.md`. The code follows those rulings.

## Closed by `limits.md` and rulings A1 to A6

- Q22, `sequence < 1` or an empty `series_id`: closed by A1, `E_SCHEMA`.
- Q23, lone surrogate in a record: closed by A4, `E_SCHEMA`.
- Q24, an instant outside years 1 to 9999: closed by A5, now `E_DATE_RANGE`.

## Closed by `limits.md` B1 to B5

- Q25, text too deep: closed by B2. A lexical scan runs before parsing, limit 64 on `document_text` and 80 on a case.
- Q26, `document_text` over the byte limit: closed by B1, `E_LIMIT` without parsing.
- Q27, `E_SCHEMA` with an over-long array: closed by B3. Every `E_SCHEMA` check now runs before the limit stage.
- Q28, nesting of record keys: closed by B4, every key.
- Q29, A5 and `chain`: closed by B5, it applies.

No question is open.

## Stage B: closed by `stage-b-rulings.md`

Q30 by B1, Q31 by B2, Q32 by the corrected `projection-and-fra.md`, Q33 by B9 (now checked in every `fx.*`), Q34 by B7,
Q35 by B5 (now on `fx.*` too), Q36 by B12, Q37 by B11, Q38 by B12, Q39 by B3, Q40 by B4, Q41 by B17.

Q42 is closed by B19: `start_months` runs from 0 to 1200, else `E_INPUT`.

No question is open.

## Stage C: choices made where the spec is silent

No golden turns on these, so none blocked work. Each is this build's reading, not a ruling.

- Q43, `SPOT` with `scale: null`: closed by C15, `E_INPUT`.
- Q44, order of the scale, positivity and delta checks in `vol.delta.*`, unlisted: scale, then `forward`/`vol`/`expiry_years`, then strike or delta.
- Q45, `vol.sabr.arbfree` where a call price reaches `f0`: closed by C16, `null`.
- Q46, `vol.svi.evaluate` with empty `log_moneyness`: closed by C17, `E_INPUT`.
- Q47, `usecase.vol_surface` checks not listed: `as_of` differing from the curve's, empty `slices`, or expiries out of order `E_INPUT`; target `strike`, `quantity` not above 0 `E_DOMAIN`, after the expiry check.
- Q48, `vol.ssvi.calibrate` has no listed check of `thetas`: it applies those of `vol.ssvi.evaluate`.
- Q49, `gamma` at exactly 1 in `vol.ssvi.calibrate`: the fit keeps `gamma` below 1, so a true 1 is only approached.

## Stage D wave 1 (open)

- QD1, `stage_b/ois.json` case `ois-0023` sends `ESTR` to `rates.ois.bootstrap` and expects `E_SCHEMA`. Stage D
  (`ois-curves.md` 1.1.0, contract 1.5.0) makes `ESTR` valid, so the code returns `ok` and this one old golden fails.
  The golden needs retiring or changing; the code follows the stage D spec.
- QD2, curve object check order: pillar checks run before jump checks (`curve-framework.md` lists no order).
- QD3, `rates.csa.discount`: two forwards on one date is not covered; the code gives `E_INPUT`. Curve checks run
  before the `fx` checks.
- QD4, `rates.basis.ois_spread`: the three curves are checked as curves before the shared `as_of` check.
- QD5, `rates.curve.joint_bootstrap`: the empty-list check runs first, then all OIS checks, then all term checks.
  `GLOBAL` applies to the OIS block; the term block is always solved after it, which ruling D9 says is the same answer.
- QD6, limits: `ois_quotes` and `term_quotes` are taken as quote lists, capped at 100 like `quotes`.
- QD7, `rates.ois.fit_steps`: quotes out of tenor order are caught by the pillar rule as `E_INPUT`.

## Stage D waves 2 and 3 (open)

- QD8, `bond.yield.from_price`: golden `bonds_d-0048` gives `clean_price` -1 (dirty +1.06) and expects `E_DOMAIN`,
  but the spec's check is `clean_price + accrued <= 0`. The code gives `E_DOMAIN` for `clean_price <= 0` as well.
- QD9, `bond.spread.asset_swap`: the quarterly floating dates are stepped back from `maturity` with the day clipped
  to the month. The bond object's month-end rule is not applied to them (golden `bonds_d-0041` needs that reading).
- QD10, `bond.fit.nelson_siegel`: a negative weight gives `E_DOMAIN`, and a `weights` list of the wrong length
  gives `E_INPUT`. Neither is listed.
- QD11, `bond.futures.conversion_factor`: a maturity on or before the first day of the delivery month gives
  `E_DATE_ORDER`, which is not listed.
- QD12, `fx.xccy.pv` does not check that `start` is on or after the curves' `as_of`. Bootstrap curve checks run
  before the quote checks.
- QD13, credit: a hazard curve with no pillars, dates not increasing after `as_of` (`E_INPUT`) or a survival
  `<= 0` (`E_DOMAIN`) is not specified. Hazard time counts from `trade_date`, and the hazard `as_of` is only used
  to check pillar order. `credit.cds.price` and `credit.index.intrinsic` apply the bootstrap's recovery check.
  The trade date is rejected when it equals any adjusted accrual start or any payment date.
- QD14, `eq.futures.basis`: the implied financing spread is searched in `[-0.5, 0.5]` ("as for borrow"), and
  gives `E_NOT_BRACKETED` outside it.
- QD15, `eq.trs.pv`: `end <= start` gives `E_DATE_ORDER`, which is not listed.
- QD16, `infl.*`: `seasonality` is taken as a required key that may be `null` (ruling C9 style).

## Stage D wave 3 (open)

- QD17, `mbs.cashflows`: golden `mbs_d-0011` has `wac` 0 and `net_coupon` 0.06 and expects `E_DOMAIN`, but the
  listed order puts `net_coupon > wac` (`E_INPUT`) first. The code checks `wac <= 0` before `net_coupon > wac`.
- QD18, `cmdty.storage.carry`: a forward price `<= 0` gives `E_DOMAIN` (it is not listed, and the log needs it).
- QD19, `rates.swaption.price`: the vol check runs after the expiry check and before the curve-derived forward check.

QD1 is closed by ruling D27: stage B `ois-0023` now sends `TONA`, and the code needs no change.
