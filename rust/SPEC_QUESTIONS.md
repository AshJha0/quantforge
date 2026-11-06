# Spec questions from the Rust implementation

Each entry is a place where the specs and the golden cases disagreed, or where the spec leaves a choice open.
Nothing here was tuned to fit: the code follows the spec text.

## Resolved at `stage-a` 363e5a8

- `add_tenor` with `end_of_month`: `calendars.md` now says "on or after the last business day", with a separate
  `UNADJUSTED` rule. The code follows the new text.
- `THIRTY_E_360_ISDA` with `start == end`: the spec keeps 0, and the golden case was corrected.
- `implementations.json` on Windows: the runner now resolves the path, and no config copy is needed.
- Shift by the first value: now required for `summary`, `covariance`, `ols`, `autocorrelation` and `ar1`.

## Still open

`cli-contract.md` calls the runner config `implementations.yaml`, while the file on disk is `.json`.

## Readings chosen where the spec is silent

No golden case shows these to be wrong, but the other languages may read them differently.

- `core.calendar.business_days_between`: a date outside 2000 to 2099 is checked before `E_DATE_ORDER`.
- `core.compounding.*`: `frequency` is validated only with `PERIODIC`. Check 4 still applies at `t = 0`, so
  `discount_factor` at `t = 0` with `1 + r/n <= 0` is `E_DOMAIN`, not 1.
- `core.diff.central`: an `order` other than 1 or 2 is `E_SCHEMA`.
- An integer input written as `5.0` is `E_SCHEMA`, from "no fraction" in the value encoding table.
- `core.data.check_quotes`: `outlier_min_history` below 3 is `E_INPUT`. The limit checks run before the
  `event_time` check.
- `core.interp.evaluate`: negative `tension` is `E_DOMAIN`.
- `core.interp.monotone_convex`, region (iv) with `g0 = 0` and `g1 != 0`: `eta = 1`, so the formula is 0/0 at
  `x = 1`. The code takes the node value `g1` there, by continuity.
- `core.pde.bs_european`: at `tau = 0` the right side of a step uses the boundary formulas, not the cell-averaged
  end values. This matters only when `rannacher_steps` is 0.
- `core.stats.ols`: `r_squared` with constant `y` is 0/0, so the result is `E_NON_FINITE`.
- Zero variance is tested as "all values equal", so rounding in a mean cannot hide it.
