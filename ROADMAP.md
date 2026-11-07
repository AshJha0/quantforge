# Roadmap

Eleven stages, one pull request and one tag each. Estimates are plan-weeks, 106 in all, not calendar weeks.

| Stage | Plan-weeks | Demo | Tag |
|---|---|---|---|
| A Foundation | 9 | Same hash, results within tolerance | v0.1 |
| B FX and rates slices | 10 | Use cases 1, 2 | v0.2 |
| C Equity vol slice | 7 | Use case 3 | v0.3 |
| D Remaining curves and pricing | 18 | All instruments reprice | v0.4 |
| E Full volatility and exotics | 11 | Arbitrage-free surfaces | v0.5 |
| F Risk, portfolio, book | 10 | Use case 4 | v0.6 |
| G Rates models and xVA | 8 | Exposure checked against ORE | v0.7 |
| H Microstructure and execution | 8 | Use case 5 | v0.8 |
| I Hedging | 5 | Use case 6 | v0.9 |
| J Research and portfolio | 8 | Published study reports | v0.10 |
| K Platform and release | 12 | Clean-machine run of all examples | v1.0.0 |

A stage exits when all four languages conform, the oracle named for its scope passes, its minimum test set runs and its docs are reviewed.

Use cases 1 and 2 are defined in `specifications/04-pricing/use-cases.md`; use cases 3 to 6 are defined in the project plan, which is kept outside this repository.

## Stage status

Done means built and passing locally through the neutral runner, at status Implemented, not Validated. Validation is self-assessment until the human review at the end of the project. Carried means left open by that stage and still owed.

| Stage | Status | Done | Carried | Known limits |
|---|---|---|---|---|
| A Foundation | Done, tag `v0.1` | Domain 01 in four languages; oracle; CLI; neutral runner; fuzz and mutation harnesses; recorder and forward log | Scheduling the recorder; the end-of-project human review | Many golden cases have hand or replay sources only. The only benchmark is one laptop run of CLI batch throughput. Clang on Windows is blocked at times, so it relies on CI |
| B FX and rates slices | Done, tag `v0.2` | SONIA and minimal SOFR OIS, projection curves, FRAs, swaps, FX forwards and swaps, quote-driven basis, calibration, DV01, key-rate risk, hedges, use cases 1 and 2. See the [Curves gallery](docs/curves/README.md) | To stage D: monotone-convex and spline curves on the curve object, full SOFR, ESTR, curves built from basis swaps. To stage F: AD, as risk is bump and rebuild (ADR-0010). No stage set: running Strata's calibrator; the licence questions in `oracle/LICENCES.md`. End of project: the human review | Almost all curve inputs are synthetic, so results show the method, not a market. `usecases` and `rulings_b` have no outside oracle, and `risk` is hand and self-consistency only (`specifications/stage-b-rulings.md`). Hedges are calculations: nothing is traded |
| C Equity vol slice | Done, tag `v0.3` | Equity forward with borrow and dividends, Black-Scholes, Black-76 and Bachelier with implied vol, analytic and bump Greeks, delta conventions, SVI and SSVI, surface checks, Hagan SABR with density check, arbitrage-free SABR, use case 3. 446 goldens in 11 suites; all four languages pass all 5,183 cases; fuzz clean | To stage E: full surfaces and exotics. No stage set: a tight outside source for `vol.sabr.arbfree` at `nu > 0`; a free source of option, borrow or dividend history. End of project: the human review | All inputs synthetic. European options only (ruling C1). Arbitrage checks on given points only. Rulings C15 to C17 settled edge cases where builds had diverged (`specifications/stage-c-rulings.md`) |
| D to K | Planned | Nothing yet. Each domain's real specs are written before its own stage | | |

## Not in the repository yet

Planned, and absent today: `infra/`, kernel-level benchmarks, API docs per package, the eight-file spec sets and validation reports per model, per-domain flow diagrams, microstructure folders in the four implementations, and data and solutions for EX-004, EX-007 and EX-010 to EX-012.
