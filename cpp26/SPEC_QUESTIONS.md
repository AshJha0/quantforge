# Spec questions from the C++ implementation

Written from the specs alone. Nothing here was changed to fit a golden file.

## Settled by the stage-a corrections

- `add_tenor` end of month: `calendars.md` now states QuantLib's rule, and this build follows it.
- `diff_linalg-0006`: the limit now follows the formula in the spec.
- Runner command on Windows: `runner.py` now resolves the path.
- `start == end` is tested first in `daycount.md`, which also settles `BUS_252` outside the calendar range: 0.

## Open

`cli-contract.md` names `conformance/runner/implementations.yaml`. The file is `implementations.json`.

## Gaps in the specs, and the reading used

No golden case covers these. Each is a choice another language could make differently.

| Where | Gap | Reading used |
|---|---|---|
| `root-finders.md`, Newton | Only one of `a`, `b` given: no code named | `E_SCHEMA`, as an input is missing |
| `root-finders.md`, Newton | `f(a)` or `f(b)` exactly 0: do they "differ in sign"? | Not an error; a zero counts as a sign change |
| `root-finders.md`, Newton | `a >= b` with a bracket | `E_INPUT` |
| `integration.md` | `max_depth` or `max_intervals` below 1 | `E_INPUT` |
| `integration.md` | Adaptive rule evaluates to infinity, as `inv_sqrt` at 0 under `adaptive_simpson` | `E_NON_FINITE` at once |
| `differentiation-and-linalg.md` | `order` other than 1 or 2 | `E_INPUT` |
| `differentiation-and-linalg.md` | "Asymmetry above 1e-12 relative": relative to what | The largest absolute entry of `a` |
| `differentiation-and-linalg.md` | All-zero matrix in `solve`: the pivot is not "below" a threshold of 0 | `E_SINGULAR` |
| `interpolation.md`, `tension` | `tension < 0`: the code is not named | `E_DOMAIN` |
| `interpolation.md`, monotone convex | Region (iv) with `g0 = 0` gives `eta = 1`, and at `x = 1` the table's fraction is 0/0 | `g(1) = g1`, the node forward; `G` takes no term from that piece |
| `interpolation.md`, monotone convex | Bad `at` and negative `fd` together | `E_OUT_OF_RANGE` first, as listed first |
| `compounding.md` | `discount_factor` at `t = 0` with `1 + r/n <= 0` | 1, as check 3 comes before check 4 |
| `calendars.md` | `business_days_between`: range and order both broken; is `end` itself range-checked | Both dates checked, range first |
| `timezone-and-cutoff.md` | `to_instant` on a local time in range whose instant falls outside, such as Tokyo 2007-01-01T00:00:00 | Allowed; only the input is checked |
| `statistics-and-time-series.md` | `ols` with constant `y`: `r_squared` is 0/0 | `E_NON_FINITE` through the output rule |
| `statistics-and-time-series.md` | `ar1` with zero variance in the regressor | `E_SINGULAR`, as for `ols` |
| `pde.md` | With `R = 0` the first step's old boundary: formula at `tau = 0`, or the cell average | The formula, as "boundary values ... at `tau`" says |
| `rng.md` | `skip` has no upper limit, and a very large one runs for a very long time | Accepted; negative is `E_SCHEMA` |
| `monte-carlo.md` | `stream` out of range: not listed there | `E_SCHEMA`, as in `rng.md` |
| `cli-contract.md` | Keys in `inputs` that the operation does not use | Ignored |
| `cli-contract.md` | An optional input given as `null` | Treated as absent |
| `cli-contract.md` | An integer written `2.0` or `2e0` | `E_SCHEMA`: "no fraction" is read on the spelling |
| `cli-contract.md` | A blank line in `batch` | A result with `E_PARSE`, so line counts stay in step |
