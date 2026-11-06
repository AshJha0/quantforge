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

## Open

`document_text` that breaks a limit and a parse rule together. `limits.md` puts `E_LIMIT` before rule checks, while
`snapshot-hash.md` lists invalid JSON first, and the contract's `E_PARSE` may mean the envelope only. This build:
over 1,048,576 bytes is `E_LIMIT` without parsing; over 64 levels is `E_LIMIT` only once the text has passed every
`snapshot-hash.md` check, as nesting has no meaning in text that is not JSON. A duplicate key below 1000 levels of
nesting is not seen, so such a text gives `E_LIMIT` and not `E_PARSE`.

The general array limit needs each operation's `E_SCHEMA` checks to run first. Here the handler runs once and its
result is dropped, so "no work is started" holds only in that no result is produced. Other limits stop before any work.
