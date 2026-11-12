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
| H Microstructure and execution | 8 | Use case 5 | v0.10 |
| I Hedging | 5 | Use case 6 | v0.8 |
| J Research and portfolio | 8 | Published study reports | v0.9 |
| K Platform and release | 12 | Clean-machine run of all examples | v1.0.0 |

Tags follow the build order of the 2026-11-07 plan consolidation: I (v0.8), J (v0.9), H (v0.10), K (v1.0.0). Stage I (hedging) was built before stage H and released as v0.8.0 on 2026-11-12 (`program/STAGE_I_HANDOVER.md`).

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
| E Full volatility and exotics | Done, released as `v0.5.0` (2026-11-09) | E1 arbitrage-free SVI surfaces, Dupire local vol, forward vol; E2 Heston, Bates, Merton, SLV leverage; E3 FX smile conventions; E4 SABR swaption cube, caplet stripping, bond futures options, YoY and ZC inflation caps; E5 exotics and American options; E6 correlation repair, implied correlation, dispersion; E7 GARCH(1,1), variance swaps, VIX-style index; E8 CDS options, copulas, large-pool model. 6,817 of 6,817 goldens in all four languages at `597abf2`; outside oracle 557 of 895 stage E cases (62.2%) | Python T1 and T4 speed and fuzz rate; Rust T1 on native Linux; calendar check until SIFMA's 2027 schedule; licensed citations awaiting a human; paywalled equation numbers unverified; workflow (b) prices by hand | All inputs synthetic. GARCH, VIX, Student-t copula, large pool, SLV and American FD have no outside library; SLV and FD goldens test agreement, not convergence (E-A14, E-A23) |
| F Risk, portfolio, book | Done, tag `v0.6.0` | Pluggable interpolation and a joint multi-curve solve with the IFT Jacobian; book sensitivities with an AAD reference in Rust; VaR, ES, backtests and FRTB-SA GIRR delta; book lifecycle and marks; use case 4; NaN and infinity rejected at every input; API style and name map ([ADR-0011](architecture/decisions/ADR-0011-api-style.md)); [Tutorial 1](docs/getting-started/tutorial-1-swap.md) run in CI; [determinism](docs/determinism.md). 12,462 of 12,462 golden cases in each language (2026-11-10). See the [Curves gallery](docs/curves/interpolation-methods.md) Wave 2b (Inflation01, dividend and borrow and correlation sensitivity, reverse stress, limits, concentration, liquidity, model reserves, the rest of FRTB) and E1 cases for the stage F operations, all delivered in stage G; the outside-oracle floor, still open | Outside oracle 51.4%, below the 60% floor (`oracle/OUTSIDE_GAPS_F.md`); R7 has no outside case. The FRTB `low` scenario formula was confirmed by the owner against MAR21.6 on 2026-11-10 (F-33) |
| G Rates models and xVA | Done, released as `v0.7.0` (2026-11-11) | Vasicek, CIR and Hull-White bond prices and options; Jamshidian and affine swaptions; Hull-White calibration; G2++; Bermudan swaptions and callable bonds; caps and floors; LMM caplet and Rebonato swaption pricing; MC Greeks and the model-reserve report; an AAD ladder; swap EE under Hull-White, portfolio exposure checked against ORE (wave 4c), collateralised exposure, CVA, DVA, FVA, SIMM-style IR delta IM and wrong-way CVA; BGK discrete barriers (R9); E1 for every stage G operation; stage F carry-overs (F3 sensitivities, F4 risk tools, FRTB FX, equity, CSR, commodity, vega and curvature) | G-42b ORE re-test (needs WSL; carried to stage I by G-52); CSR securitisations; a full 50-digit regeneration of the fixed `expsim_g` PFE goldens | Outside-oracle share 57.4% (338 of 589), below the 60% floor; every input synthetic |
| I Hedging | Done, released as `v0.8.0` (2026-11-12; taken before H) | The constrained least-squares hedge solver with costs, impact, liquidity and margin, scaling to 200 instruments in every build (I-48); integer lots; minimum-variance, Greek, beta, credit, correlation and cross-asset hedges; residual risk; instrument selection; the risk-against-cost frontier; a dynamic delta-hedge backtest with costs; hedge effectiveness; slippage. 443 golden cases in 21 suites, rulings I-1 to I-55, CLI contract 1.11.0; 14,935 of 14,935 golden cases in each language on the integration tree (2026-11-11, observed). Sixteen example inputs (`examples/hedge_*_i.json`); the stage G PFE goldens regenerated | Q6, calibration on real noisy quotes: blocked by the data terms of the candidate sources, preregistration only, tutorial 22 not shipped. From stage G: G-42b, the C++ sanitizer run on wave 4c, the formal G-9 AAD timing (`program/STAGE_I_CARRY.md`). FRTB CSR securitisations, with DRC, a candidate for a later FRTB completion item | Outside-oracle share 62.8% (278 of 443), above the 60% floor (I-2); integer lots, beta, residual, slippage and error cases have no free outside reference; every input synthetic; nothing is traded |
| H, J, K | Planned | Nothing yet. Each domain's real specs are written before its own stage | | |

## R1: credibility hardening (tag `v0.4.1`)

Before stage E, R1 works on how far the existing results can be trusted. It adds no new pricing.

| Item | What it adds | State |
|---|---|---|
| Batch mode | Contract 1.6.0: `--batch`, `--timings`, rules BT1 to BT8, 19 stream fixtures | Built in all four languages |
| Rulings | R1-1 to R1-6 in `specifications/r1-rulings.md` | Done |
| Edge cases | [Register](specifications/edge-case-register.md) of 14 rows: 7 pinned, 3 pinned in part, 4 out of scope with the stage that brings them in | Done |
| Model inventory | [One page per model](docs/model-inventory.md): spec, oracle, outside-checked share, limits, use restriction | Done |
| Calendar provenance | Source and confirmed-through date for each calendar, `datasets/calendar_provenance.json`, checked weekly | Done; check red until SIFMA's 2027 schedule |
| Money tolerances | Every tolerance restated as money on 10 million, `conformance/tolerances/money.md` | Done |
| Recorder | Scheduled on GitHub Actions with a gap monitor | Built; first run after push |
| Conformance matrix | 3 OS by 4 languages on Actions; local Linux C++ under WSL | Built; first run after push. WSL C++ passed 5,514 v0.4 goldens |
| Workflows (a) and (c) | EOD curves with sanity bands (USD proxy curve, BoE GBP pass or fail) and a SOFR averages check, through `--batch` | Built; first local runs passed 2026-11-07 |
| Targets and mutation | [Targets](benchmarks/targets.md) written before measuring; per-stage mutation report | Measured (C++ stage D mutation 82.5%, measured in R2); Python T1 and T4 and Java T1 missed |
| Coverage | Unit-test line coverage: C++ 94.2%, Java 97.3%, Python 97.2%, Rust 96.5% | Measured |
| Citations | A `## Sources` section in 50 specs (`program/R1_CITATION_FINDINGS.md`) | Done. The citations lane reports 10 sources opened and confirmed, 2 partly confirmed and 16 unreachable; licensed sources are still not opened |
| R3 preregistrations | Three studies in `research/preregs/` | Signed by Claude under the owner's delegation; holdout unread |

Open at the end of R1: Python fuzz runs at about 2,760 cases a minute against the 50,000 target.

## R2: risk first (tag `v0.4.2`, released 2026-11-08)

Risk before more products: par and key-rate risk, P&L explain, calibration stability and workflow (b). Contract 1.7.0 adds operations and no error code.

| Item | What it adds | State |
|---|---|---|
| Par and key-rate risk | `risk.curve.par`, `risk.curve.key_rate` (`TRIANGULAR`, `PILLAR`), `risk.curve.jacobian`; spec `06-risk/par-and-key-rate.md`; 41 goldens in `risk_r2`, re-priced in QuantLib | Done: all four languages pass 5,922 of 5,922 |
| P&L explain | `risk.pnl.explain` with a threshold of 5% of the larger of full and gross first-order P&L, a project choice (rulings R2-A3, R2-A4); spec `06-risk/pnl-explain.md`; 44 goldens in `pnl_r2`; real-move run `tools/workflows/pnl_explain.py` | Run: 100% of 2025 days explained on every product, Java and Python |
| Calibration stability | Seven calibrations, C1 to C7, judged on metrics S1 to S7, `03-calibration/stability.md` | Run: 28 of 28 pass, languages within 2e-8; C3 rerun under R2-A9 passes |
| Workflow (b) | Treasury and gilt rich/cheap screen, `1/D_mod^2` weights, on-the-run issues reported but not fitted, `04-pricing/workflow-b-rich-cheap.md` | BLOCKED on price data (R2-A11); Fiscal Data auction prices checked at stage E and not usable (one auction day per bond, at most two a day); manual `--data DIR` path |
| Carried from R1 | Recorder and daily workflows | Live: the recorder pushes to `forward-log` with no gaps, and the daily workflows run |
| Carried from R1 | Python fuzz rate, C++ stage D mutation, Rust T1 on native Linux, cross-platform matrix | Python fuzz 12,800 a minute (target 50,000, still short); C++ mutation 82.5%; Rust T1 native Linux still owed; cross-platform matrix checked on main after merge |

Stage E followed R2; its row is in the stage status table above. Stage F (risk, portfolio, book) followed it.

What R1 cannot change: on free public data QuantForge can show correct pricing, curve quality against published curves and honest statistics, never tradable profitability (see the README).

## Not in the repository yet

Planned, and absent today: `infra/`, kernel-level benchmarks, API docs per package, the eight-file spec sets and validation reports per model, per-domain flow diagrams, microstructure folders in the four implementations, and data and solutions for EX-004, EX-007 and EX-010 to EX-012.
