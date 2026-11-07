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

### D6 inflation and linkers (ready)

New operations: `infl.curve.cpi`, `infl.zcis.pv`, `infl.linker.price`, `infl.linker.price_curve`. Goldens: `datasets/golden/stage_d/inflation_d.json`, 13 cases. Read: `specifications/02-curves/inflation.md`; the D6 table in `stage-d-targets.md`; rulings D25, D26.

### D7 caps and swaptions (ready)

New operations: `rates.cap.price`, `rates.swaption.price`. Goldens: `datasets/golden/stage_d/capswaption_d.json`, 14 cases. Read: `specifications/05-volatility/caps-and-swaptions.md`, `specifications/05-volatility/black-models.md`; the D7 table in `stage-d-targets.md`; ruling D28. Stage B case `ois-0023` changed (ruling D27).

### D8 commodities (ready)

New operations: `cmdty.curve.forward`, `cmdty.storage.carry`. Goldens: `datasets/golden/stage_d/commodity_d.json`, 10 cases. Read: `specifications/02-curves/commodity.md`; the D8 table in `stage-d-targets.md`; ruling D29.

### D9 MBS (ready)

New operations: `mbs.cashflows`, `mbs.price`. Goldens: `datasets/golden/stage_d/mbs_d.json`, 12 cases. Read: `specifications/04-pricing/mbs.md`; the D9 table in `stage-d-targets.md`; ruling D30.

All of stage D is now specified.

## Rulings on the builds' spec questions

Rulings D31 to D46, with goldens in `datasets/golden/stage_d/rulings_d.json` (18 cases). `bonds.md`, `mbs.md` and `meeting-steps.md` were corrected to match goldens already in place.

Not for language sessions: anything under `oracle/`.
