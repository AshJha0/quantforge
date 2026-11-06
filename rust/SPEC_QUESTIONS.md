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

## Closed at `stage-a` 3737bb5

- `core.store.*` order of checks: ruling A2 replaced "before anything else", and the code follows it.
- `core.store.*`, `sequence` below 1 is `E_SCHEMA`: confirmed by A1.
- `core.store.replay`, `head` is the whole log: confirmed by A6.

## Closed at `stage-a` bb663d6

- `E_LIMIT` on `document_text`: B1 and B2 put size and a lexical depth scan before parsing, and the code follows them.
- `dimensions` of 65 with a large `count` is `E_LIMIT`: confirmed by B3.

## Readings chosen where the spec is silent

No golden case shows these to be wrong, but the other languages may read them differently.

- `core.root.newton`: when `f(a)` is exactly 0, the bracket shrinks by the sign of `f(b)`, so the root at `a` stays
  inside it (ruling R3 leaves this step open).

## Stage B readings

No stage B golden case conflicted with a spec. These are points the specs leave open.

- `rates.schedule.generate`: a negative `payment_lag` is `E_INPUT`.
- `rates.projection.*`, `rates.swap.pv`, `rates.basis.spread`: schedules use `end_of_month` false, as the spec names
  no end-of-month rule for them. `spot` is `as_of` plus 2 `USGS` business days, with no `FOLLOWING` step first.
- `rates.curve.*`: an empty `pillars` is `E_INPUT`.
- `fx.forward.pv`, `fx.swap.pv`: no `E_DATE_ORDER` on a value date before spot, as only `outright` names it.
- `fx.curve.implied`: nodes out of order are `E_INPUT`. A tenor may use any unit `add_tenor` accepts.
- `hedge.solve`: a non-positive weight is `E_DOMAIN`. Stage B's limits name quotes and pillars for `rates.*`, `risk.*`
  and `usecase.*`, so `calib.curve_report` follows them too, and `fx.*` curves have only the general array limit.
- `calib.fit`: `lower` above `upper`, a wrong-length `prior`, `weights` or bound, and `max_iter < 1` are `E_INPUT`.
  `x` and `y` may be left out for `ROSENBROCK`.
- `rates.ois.compound`: an empty `rates` is `E_INPUT`, and a `denominator` other than 360 or 365 is `E_SCHEMA` (G5).
