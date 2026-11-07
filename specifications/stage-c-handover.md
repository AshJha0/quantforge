# Stage C handover

From the spec and oracle session, to the four language sessions. Date 2026-11-07.

## Finished

- Specs for every stage C item, at Specified.
- CLI contract 1.4.0: new operations and `E_ARBITRAGE`. `contract_version` stays `1.0.0`.
- Numeric targets, written before any code.
- Goldens in `datasets/golden/stage_c/`: 11 suites, with QuantLib, Strata, analytic and hand sources.
- 30 wrong-convention checks, each shown to fail.

## Not finished

- Full `run_all.py` rerun on 2026-11-07: stage C goldens unchanged; `REPORT.md` carries the stage C lines.
- `check_invariants.py` covers `stage_c`: 446 cases, none breaks a rule.
- `vol.sabr.arbfree` at `nu > 0` has no tight outside source. See `stage-c-rulings.md`.
- No implementation has run a case, so spec gaps may surface. Use each language's `SPEC_QUESTIONS.md`.
- Runner, schemas: no change needed, as cases use the existing format. The runner must be pointed at `datasets/golden/stage_c/`; infrastructure work is with another session.

## What language sessions can start on

All of it, in this order, as later items lean on earlier ones: equity forward, Black models, Greeks, delta and smile, SVI and SSVI, surface, SABR, arbitrage-free SABR, use case 3.

## Files a language session reads

- `specifications/cli-contract.md`
- `specifications/stage-c-rulings.md`
- `specifications/02-curves/curve-framework.md`
- `specifications/02-curves/equity-forward.md`
- `specifications/05-volatility/black-models.md`
- `specifications/05-volatility/smile-and-surface.md`
- `specifications/05-volatility/sabr.md`
- `specifications/05-volatility/stage-c-targets.md`
- `specifications/06-risk/vol-greeks.md`
- `specifications/04-pricing/use-cases.md`, `pricing-framework.md`
- `datasets/golden/stage_c/*.json`, through the runner

Not for language sessions: anything under `oracle/`.
