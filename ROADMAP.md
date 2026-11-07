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
| D Curves and fixed income | Done, tag `v0.4` | D1 rates core (full SOFR, ESTR, jumps, compounding conventions, IBOR fallbacks, meeting steps, convexity, CSA, basis, joint and robust fits), D2 bonds and repo, D3 cross-currency and NDF, D4 ISDA CDS, D5 equity carry, index and TRS, D6 inflation, D7 caps and swaptions, D8 commodities, D9 MBS. At merge `95cbf11` on 2026-11-07, each of the four implementations passed 5,514 of 5,514 golden cases locally, 331 of them in stage D's 20 suites, and fuzzing with seed 17 found nothing (`conformance/README.md`) | To later stages: monotone-convex and spline curves; term structures of borrow; cap and swaption surfaces (stage E). End of project: the human review | All inputs synthetic; the stage D data survey found no free swap, bond-level, special repo, cross-currency, CDS, borrow, commodity-curve or MBS data. Several suites have no outside oracle (`specifications/stage-d-rulings.md`) |
| E to K | Planned | Nothing yet. Each domain's real specs are written before its own stage | | |

## R1: credibility hardening (v0.4.1, in progress)

Before stage E, R1 works on how far the existing results can be trusted. It adds no new pricing.

| Item | What it adds | State |
|---|---|---|
| Batch mode | Contract 1.6.0: `--batch`, `--timings`, rules BT1 to BT8, 19 stream fixtures | Specified; builds landing |
| Edge cases | A register of edge cases per operation, each pinned by a fixture | In progress |
| Model inventory | One list of every model: spec, oracle, evidence class, known limits | In progress |
| Calendar provenance | The source of every holiday calendar | In progress |
| Recorder | Scheduled daily recording of public data | In progress |
| Conformance matrix | Which suites pass in which language and toolchain, and in CI | In progress |
| Workflows (a) and (c) | Two end-to-end workflows on recorded public data | In progress |
| Targets and mutation | Throughput targets in `benchmarks/targets.md`; a mutation report | In progress |
| Citations | A source and evidence class for every claim in the docs | In progress |

R2, risk-first (par and key-rate risk, P&L explain, calibration stability), follows as v0.4.2, then stage E.

What R1 cannot change: on free public data QuantForge can show correct pricing, curve quality against published curves and honest statistics, never tradable profitability (see the README).

## Not in the repository yet

Planned, and absent today: `infra/`, kernel-level benchmarks, API docs per package, the eight-file spec sets and validation reports per model, per-domain flow diagrams, microstructure folders in the four implementations, and data and solutions for EX-004, EX-007 and EX-010 to EX-012.
