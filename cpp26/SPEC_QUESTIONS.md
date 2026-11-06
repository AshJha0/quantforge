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

Nothing is open.
