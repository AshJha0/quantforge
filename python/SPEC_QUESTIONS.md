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
