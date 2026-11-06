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

## Open

| # | Question | Choice made |
|---|---|---|
| Q25 | `limits.md` puts `E_LIMIT` after `E_PARSE`, but a text too deep for the JSON reader cannot be shown valid | `E_LIMIT`, including for a deep text that is also malformed, in the case and in `document_text` |
| Q26 | Is `document_text` over the byte limit `E_LIMIT` even if malformed? | Yes: `E_LIMIT` is checked on its size, without parsing, so no work is started. `snapshot-hash.md` nesting and `E_SCHEMA` inside the text keep their order |
| Q27 | A conditional daycount input missing, or `frequency` unlisted (`E_SCHEMA`), together with an unused over-long array | `E_LIMIT`, because those two checks sit in the core. Other enums are read before the limit stage |
| Q28 | Nesting limit on a record's keys other than `value` | The limit is applied to every key of a record, since the chain hashes them all |
| Q29 | Does A5 apply to `chain`, which leaves instants untouched? | Yes: the ruling names no exception |
