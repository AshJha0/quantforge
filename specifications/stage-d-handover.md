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

## Wave 2

### D2 bonds and repo (ready)

New operations: `bond.price.from_yield`, `bond.yield.from_price`, `bond.price.from_curve`, `bond.spread.z`, `bond.spread.asset_swap`, `bond.frn.price`, `repo.forward`, `repo.implied_rate`, `bond.futures.conversion_factor`, `bond.futures.basis`, `bond.fit.nelson_siegel`.

Goldens: `datasets/golden/stage_d/{bonds_d,repo_d,bondfit_d}.json`, 72 cases.

Read, beyond wave 1: `specifications/04-pricing/bonds.md`; the wave 2 table in `02-curves/stage-d-targets.md`; rulings D13 to D16.

### D3 cross-currency and NDF (ready)

New operations: `fx.xccy.bootstrap`, `fx.xccy.pv`, `fx.ndf.pv`. Goldens: `datasets/golden/stage_d/xccy_d.json`, 13 cases. Read: `specifications/02-curves/cross-currency.md`; the D3 table in `stage-d-targets.md`; rulings D17, D18.

### D4 credit (ready)

New operations: `credit.cds.price`, `credit.cds.bootstrap`, `credit.index.intrinsic`, `credit.curve.composite`. Goldens: `datasets/golden/stage_d/credit_d.json`, 19 cases. Read: `specifications/04-pricing/credit.md`; the D4 table in `stage-d-targets.md`; rulings D19 to D21.

### D5 equity (ready)

New operations: `eq.dividend.implied`, `eq.borrow.implied`, `eq.futures.basis`, `eq.index.dividends`, `eq.index.rebalance`, `eq.corporate_action.adjust`, `eq.trs.pv`. Goldens: `datasets/golden/stage_d/{equity_d,index_d,trs_d}.json`, 25 cases. Read: `specifications/02-curves/equity-curves.md`, `specifications/04-pricing/equity-index.md`; the D5 table in `stage-d-targets.md`; rulings D22 to D24.

## Wave 3

Not yet specified.

Not for language sessions: anything under `oracle/`.
