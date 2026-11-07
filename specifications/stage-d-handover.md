# Stage D handover

From the spec and oracle session, to the four language sessions. Kept current per wave. Date 2026-11-07.

## Wave 1: D1 rates core (ready)

New operations: `rates.ois.compound_dated`, `rates.fallback.rate`, `rates.ois.step_curve`, `rates.ois.fit_steps`, `rates.futures.convexity`, `rates.csa.discount`, `rates.basis.ois_spread`, `rates.curve.joint_bootstrap`, `calib.curve.smooth`, `calib.curve.robust`.

Changed: `rates.ois.bootstrap` and `rates.ois.pv` accept `ESTR`; `rates.ois.bootstrap` takes optional `jumps`; the curve object takes optional `jumps`, so every operation that reads a curve honours them.

Goldens: `datasets/golden/stage_d/{ois_d,compound_d,steps_d,futures_d,csa_d,fits_d}.json`, 109 cases.

Read:
- `specifications/cli-contract.md`
- `specifications/stage-d-rulings.md`
- `specifications/01-core/conventions.md` (ESTR row)
- `specifications/02-curves/curve-framework.md` (jumps)
- `specifications/02-curves/ois-curves.md`
- `specifications/02-curves/overnight-compounding.md`
- `specifications/02-curves/meeting-steps.md`
- `specifications/02-curves/futures-convexity.md`
- `specifications/02-curves/csa-and-basis.md`
- `specifications/03-calibration/curve-fits.md`
- `specifications/02-curves/stage-d-targets.md`
- `datasets/golden/stage_d/*.json`, through the runner

## Waves 2 and 3

Not yet specified. Do not start them.

Not for language sessions: anything under `oracle/`.
