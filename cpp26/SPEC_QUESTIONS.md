# Spec questions from the C++ implementation

Written from the specs alone. Nothing here was changed to fit a golden file.

## Settled by the stage-a corrections

- `add_tenor` end of month: `calendars.md` now states QuantLib's rule, and this build follows it.
- `diff_linalg-0006`: the limit now follows the formula in the spec.
- Runner command on Windows: `runner.py` now resolves the path.
- `start == end` is tested first in `daycount.md`, which also settles `BUS_252` outside the calendar range: 0.

## Open

`asof-store.md` says the log checks come "before anything else", while `cli-contract.md` puts all `E_SCHEMA` before
rule checks. With an unordered log and a bad `as_of`, this build gives `E_INPUT`, as the store spec is the more exact.

`asof-store.md` does not name a code for `sequence < 1` or an empty `series_id`. This build gives `E_SCHEMA`, reading
both as a mistyped record.

Every earlier gap in this file is settled by `specifications/01-core/rulings.md`.
