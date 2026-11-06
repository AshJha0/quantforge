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

## Stage B: open choices

No golden case conflicted with a spec. These points are silent, and no case decides them.

| # | Where | Question | Choice made |
|---|---|---|---|
| Q30 | `schedules.md` | Every date adjusts onto or before `start`, so no period is left | Returns an empty `periods` |
| Q31 | `schedules.md` | `payment_lag < 0` has no code | `E_INPUT` |
| Q32 | `projection-and-fra.md` | Does `end_of_month` apply to the term index schedules and month steps? | No: false throughout, as the spec names no rule |
| Q33 | `fx.md` | `value_date` before the spot date is an error for `outright`. For `forward.pv` and `swap.pv`? | Not checked there: only `outright` lists it |
| Q34 | `fx.md` | `fx.curve.implied` with a `D` or `W` tenor | `E_SCHEMA`, as the spec says months. Tenors out of order: `E_INPUT` |
| Q35 | `limits.md` | Does the 100 quote or pillar limit reach `calib.curve_report` and `fx.*`? | `calib.curve_report` yes, as it bootstraps. `fx.*` no, as the row names `rates.*`, `risk.*`, `usecase.*` |
| Q36 | `least-squares.md` | `ROSENBROCK` with another method, or `NELSON_SIEGEL` with `GAUSS_NEWTON` | Allowed and run, as no code is named |
| Q37 | `least-squares.md` | `max_iter < 1`, and the order of length against domain checks | `E_INPUT`. All length checks come before domain checks |
| Q38 | `least-squares.md` | Do `weights` apply to `ROSENBROCK`? | No: it has no data |
| Q39 | `curve-framework.md` | A curve with no pillars | `E_INPUT` |
| Q40 | `curve-framework.md` | `rates.curve.forward` with a `day_count` needing conditional inputs | `E_SCHEMA`, as there is no way to give them |
| Q41 | `least-squares.md` | Timestamps in the `curve_report` diagnostic `inputs` | Tenors only: quotes carry no timestamps here |
