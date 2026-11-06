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

## Open choices in `asof-store.md`

| # | Question | Choice made |
|---|---|---|
| Q22 | `sequence < 1` and an empty `series_id` have no stated code | `E_SCHEMA`, as log check 1 |
| Q23 | A lone surrogate in a record cannot be put in canonical form | `E_SCHEMA`, as in `snapshot-hash.md` |
| Q24 | With no year limit, an offset can move an instant outside years 1 to 9999, which `Z` form cannot show | Reported as `E_NON_FINITE`. No case covers it |
