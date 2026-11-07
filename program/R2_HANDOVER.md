# R2 handover

From the spec and oracle session to the four clean-room language sessions. Kept current as R2 items land. Date 2026-11-07.

## R2.1 Par and key-rate risk (ready)

Contract 1.7.0; the wire `contract_version` stays `1.0.0`. New operations, no new error code:
- `risk.curve.par`: par-quote risk by bump and rebuild of the OIS curve, with a parallel DV01 and one bucket per quote;
- `risk.curve.key_rate`: zero-rate key-rate risk on a given curve, in mode `TRIANGULAR` (key dates, triangular weights) or `PILLAR` (one bucket per curve pillar);
- `risk.curve.jacobian`: d(pillar zero)/d(par quote), central difference.

Products are `OIS` (as `rates.ois.pv`) and `BOND` (as `bond.price.from_curve`, scaled by `notional`). Results are money per bp. Each reuses your existing pricers; no new pricing rule.

Read only these:
- `specifications/06-risk/par-and-key-rate.md`
- `specifications/cli-contract.md` (the R2 table)
- the pricer specs you already have (`02-curves/ois-curves.md`, `04-pricing/bonds.md`, `02-curves/curve-framework.md`)
- `datasets/golden/r2/risk_r2.json`, through the runner

Do not read `oracle/`.

Golden suite: `r2/risk_r2`, 41 cases, each checked against QuantLib. Par risk and the Jacobian difference curve solves, so your solve must stop below 1e-13 in rate, as in stage B.

Check:

```bash
python conformance/runner/runner.py --impl <lang> --suite risk_r2
```

Questions go in `SPEC_QUESTIONS` as before.

## R2.2 P&L explain (ready)

New operation `risk.pnl.explain`: full revaluation between two quote sets on one `as_of`, against par buckets times the quote moves, with the fixed threshold `max(5% |full|, 5% |par_dv01|)` and a boolean `explained`. Read `specifications/06-risk/pnl-explain.md`. Golden suite `r2/pnl_r2`, 44 cases.

Once it passes, the real-data run is `python tools/workflows/pnl_explain.py --impl <lang> --years 2025`, which calls your CLI in batch mode. That is infra's job to schedule; you only need the goldens.
