# Stage B follow-ups

What each language builds, in a separate clean-room session. The list is the same for Java, C++, Python and Rust; none is the reference. No stage B code exists yet, and no build has run these suites.

Read first: `cli-contract.md`, `01-core/rulings.md`, `01-core/limits.md`, `02-curves/stage-b-targets.md`.

| Order | Build | Spec | Golden suite in `datasets/golden/stage_b/` |
|---|---|---|---|
| 1 | Units, money (128-bit or decimal), convention registry, `E_CURRENCY_MISMATCH` | `01-core/units-and-money.md`, `conventions.md` | `units` |
| 2 | Schedules | `02-curves/schedules.md` | `schedule` |
| 3 | Curve object, interpolation, extrapolation | `02-curves/curve-framework.md` | `curve` |
| 4 | OIS legs, bootstrap (both methods), compounding, PV | `02-curves/ois-curves.md` | `ois` |
| 5 | Projection bootstrap, FRA, swap, tenor basis | `02-curves/projection-and-fra.md` | `projection` |
| 6 | FX | `02-curves/fx.md` | `fx` |
| 7 | Gauss-Newton, Levenberg-Marquardt, BFGS, report | `03-calibration/least-squares.md` | `calibration` |
| 8 | DV01, key-rate, duration | `06-risk/rates-sensitivities.md` | `risk` |
| 9 | Hedge solve, cost | `08-hedging/stage-b-hedges.md` | `hedge` |
| 10 | Use cases | `04-pricing/use-cases.md` | `usecases` |

Notes for all four:
- Keep the five parts of `04-pricing/pricing-framework.md` apart in the API.
- Curve solves must stop below 1e-13 in rate, or bumped risk will miss its limits.
- Keep calculations as pure functions of their inputs, so that stage F can add AD (ADR-0010).
- Proven libraries may be used for linear algebra and general solvers. Financial logic stays your own.
- Add the new limits in `01-core/limits.md`.

The stage A follow-ups in `01-core/clean-room-followups.md` still stand where not yet done.

## Second round: deeper cases and rulings

Run the new suites `schedule_deep`, `curve_deep`, `ois_deep`, `projection_deep`, `risk_deep`, `fx_deep`, `hedge_deep` and `rulings_b`. Read `stage-b-rulings.md`. No build has run them.

| Ruling | Java | C++ | Python | Rust |
|---|---|---|---|---|
| B0 spot counts from `as_of`, with no `FOLLOWING` first, in OIS too | **Change** OIS: spec said `FOLLOWING` | **Change** both | **Change** OIS | **Change** OIS |
| B3 empty `pillars` is `E_INPUT` | Not stated | **Change**: `E_SCHEMA` | ok | ok |
| B5 100-pillar limit on every curve | Not stated | Not stated | **Change**: not on `fx.*` | **Change**: not on `fx.*` |
| B7 `D`, `W` tenors in `fx.curve.implied` are `E_SCHEMA` | **Change** | ok | ok | **Change** |
| B8 curve `as_of` must match in `fx.*` | **Change** | **Change** | Not stated | Not stated |
| B9 dates before spot, near after far are `E_DATE_ORDER` | **Change** | **Change** | **Change** | **Change** |
| B10 `snapshot_id` in `fx.*` | **Change**: always `null` | Not stated | Not stated | Not stated |
