# Spec questions from the Rust implementation

Each entry is a place where the specs and the golden cases disagreed, or where the spec leaves a choice open.
Nothing here was tuned to fit: the code follows the spec text.

## Resolved at `stage-a` 363e5a8

- `add_tenor` with `end_of_month`: `calendars.md` now says "on or after the last business day", with a separate
  `UNADJUSTED` rule. The code follows the new text.
- `THIRTY_E_360_ISDA` with `start == end`: the spec keeps 0, and the golden case was corrected.
- `implementations.json` on Windows: the runner now resolves the path, and no config copy is needed.
- Shift by the first value: now required for `summary`, `covariance`, `ols`, `autocorrelation` and `ar1`.

- The `implementations.yaml` name in `cli-contract.md` is corrected to `.json`.
- The silent points listed here earlier are settled by `specifications/01-core/rulings.md`, and the code follows it.
  The one change of a stated choice was S2: `ols` on constant `y` now gives a `null` `r_squared`.

## Readings chosen where the spec is silent

No golden case shows these to be wrong, but the other languages may read them differently.

- `core.store.*`: "before anything else" is read literally, so all log checks run before the other inputs are
  read. A bad `as_of` on a log that also breaks `sequence` order gives `E_INPUT`, not `E_SCHEMA`. This sits against
  the contract's order of `E_SCHEMA` before rule checks.
- `core.store.*`: a `sequence` below 1 counts as mistyped, so it is `E_SCHEMA`.
- `core.store.replay`: `head` is the chain head of the whole log.
- `core.root.newton`: when `f(a)` is exactly 0, the bracket shrinks by the sign of `f(b)`, so the root at `a` stays
  inside it (ruling R3 leaves this step open).
