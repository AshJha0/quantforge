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

## Stage B, closed at `stage-b` ddf2b18

`specifications/stage-b-rulings.md` settles the stage B readings listed here earlier, and the code follows it. The
changes of a stated choice were B0 (spot in OIS), B5, B7, B8, B9 and B10. B11 and B12 also reordered `calib.fit`.
`hedge.solve` now gives `E_NO_CONVERGENCE` if its result fails the first-order conditions (B13).

## Stage B, closed at `stage-b` 9615ef5

- `fx.curve.implied` limit on `points`: confirmed by B21.
- `newton` bracket with an exact zero at an end: confirmed by B23.

## Closed on `stage-c-rust`

- B24: every operation that works on an array now stops at the limit after its typed reads, before any work.

## Stage C, readings taken where the spec is silent

None of these is reached by a golden. All 428 stage C cases pass with them.

- `vol.delta.*`, `vol.smile.rr_bf`: `SPOT` with a `null` scale is `E_INPUT`. The spec gives `E_DOMAIN` only for a scale not above 0.
- `vol.delta.*`: the scale checks run after the type reads and before the `forward`, `vol`, `expiry_years` checks, as the table states them first.
- `vol.svi.calibrate`, `vol.sabr.calibrate`: a `weights` of another length is `E_INPUT`, and lengths are checked before order.
- `risk.vol.surface_vega`: a position with `forward`, `strike`, `discount_factor` or `expiry_years` not above 0 is `E_DOMAIN`.
- `vol.sabr.arbfree`: `vols` is `null` only where the price does not exceed intrinsic, as stated. A price at or above `f0` would be `E_DOMAIN` from the implied solve.
- `usecase.vol_surface`: empty or out-of-order `slices` is `E_INPUT`; a slice expiry on or before `as_of`, or a target `strike` or `quantity` not above 0, is `E_DOMAIN`. The target check runs before any fit.
