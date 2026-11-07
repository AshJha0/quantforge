# Spec questions from the C++ implementation

Written from the specs alone. Nothing here was changed to fit a golden file.

## Settled by the stage-a corrections

- `add_tenor` end of month: `calendars.md` now states QuantLib's rule, and this build follows it.
- `diff_linalg-0006`: the limit now follows the formula in the spec.
- Runner command on Windows: `runner.py` now resolves the path.
- `start == end` is tested first in `daycount.md`, which also settles `BUS_252` outside the calendar range: 0.

## Closed by rulings and limits

- Log checks against `E_SCHEMA`: ruling A2, the contract's order holds.
- `sequence < 1` and empty `series_id`: ruling A1, `E_SCHEMA`.
- `skip` with no upper limit: `limits.md`.
- `implementations.yaml` in the contract: corrected.
- Every other gap this file listed: settled by `specifications/01-core/rulings.md`.
- `document_text` breaking a limit and a parse rule together: rulings B1 and B2.

Array limit before work: closed by ruling B24. Each handler now reads its inputs, then calls `In::ready()`, then works.

## Stage B

Closed by `specifications/stage-b-rulings.md` and the corrected specs: `end_of_month` on swap schedules, `spot` from a
non-business `as_of` (my reading was wrong, B0), `months` ranges, `FRA` end, empty `pillars` (my reading was wrong, B3),
`day_count` in `forward`, `payment_lag`, empty `periods`, `compound`, `fx.*` tenors, curve `as_of` in `fx.*` and date
order of swap legs (I had no check, B8, B9), `calib.fit` checks, `hedge.solve` order, `hedge_tenors`, solve method,
19-digit sums, and shared bumped curves.

`start_months`: ruling B19, 0 to 1200, as built.


## Stage C

No golden depends on these. Each is how the build reads a point the spec leaves open; none is sent as a question yet.

- `vol.delta.*` with `SPOT` and `scale: null`: built as `E_DOMAIN`, the "must be above 0" rule. `E_SCHEMA` is also a fair reading.
- `vol.delta.*`, `vol.smile.rr_bf`: the spec lists no order among the scale, forward, vol and delta checks. Built scale first.
- `BACHELIER` with `shift: 0`: `E_SCHEMA`, by C8. C9 says `shift` at 0 may be absent, which does not settle whether it may be present.
- `eq.forward.parity` with no `discount_factor` key: `E_SCHEMA`, treated like `borrow_curve` under C9, though C9 does not name it.
- `vol.svi.evaluate` with empty `log_moneyness`, `vol.sabr.density` with empty `strikes`: `E_INPUT`, as `min_g` and `min_density` have no value.
- `vol.svi.calibrate`, `vol.sabr.calibrate`: the length rule is checked before the increasing rule, though the spec names increasing first.
- `vol.ssvi.calibrate`: no rule for `total_variance <= 0`. None added.
- `vol.sabr.arbfree`: a price at or above `f0` gives a `null` vol, like one at intrinsic. The spec only names intrinsic.
- `usecase.vol_surface`: no check order given, and no rule for `target.strike` or `quantity`. Built as `vol.equity.price`, `E_DOMAIN`.
