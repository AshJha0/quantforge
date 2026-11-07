# Changelog

## 0.4.1: R1, credibility hardening (unreleased)

Work in progress on branch `r1`. Nothing here changes a golden value.

### Added
- Batch mode, CLI contract 1.6.0: `quantforge --batch` as a synonym of `quantforge batch`, framing rules BT1 to BT8 in `specifications/cli-contract.md`, the optional `--timings` flag, and 19 stream fixtures in `datasets/batch/streams.json`, checked by `conformance/runner/batch_check.py`. The wire `contract_version` stays 1.0.0. On 2026-11-07 each v0.4 build passed 14 of the 19 streams; the five failures are the new items.
- The honest-ceiling statement in `README.md`: what free public data can and cannot show.
- Batch mode sections in `COOKBOOK.md` and `LEARN.md`, and an R1 section in `ROADMAP.md`.

### Changed
- `README.md` no longer says stage D is untagged; it was released as `v0.4`.

## 0.4.0: stage D, curves and fixed income (2026-11-07)

Tagged `v0.4` on `e4047a1` after pull request #15. Stage D is at Implemented, not Validated. Figures are local runs on Windows, 2026-11-07, on branch `stage-d` at merge `95cbf11`.

### Added
- Stage D in all four implementations, from the specs alone: D1 rates core (SOFR and ESTR OIS, curve jumps, lookback, observation shift and lockout, IBOR fallbacks, meeting-date steps, Hull-White futures convexity, CSA discounting, OIS index basis, joint bootstrap, smoothness-regularised and Huber curve fits), D2 bonds, Z-spread, asset swap, FRN, repo and special repo, conversion factors and CTD, sovereign fits, D3 cross-currency basis and NDFs, D4 ISDA CDS, index CDS and composite curves, D5 implied dividends and borrow, futures basis, index dividends and dividend futures, rebalancing, corporate actions and TRS, D6 CPI curves with seasonality, zero-coupon inflation swaps and linkers, D7 caps, floors and swaptions on flat or quoted vol, D8 commodity curves with seasonality and storage carry, D9 MBS prepayment and pass-through pricing.
- Specifications, numeric targets set before the code, and rulings D1 to D64. CLI contract 1.5.0 adds operations and no error code; the wire `contract_version` stays 1.0.0.
- 331 golden cases in 20 suites in `datasets/golden/stage_d/`, from QuantLib (including its ISDA CDS engine), SciPy, analytic, exact-rational and hand sources. Each of the four builds passed all 5,514 cases. Wrong-convention checks are listed in `oracle/REPORT.md`, each shown to fail.
- Stage D sections in `LEARN.md`, `COOKBOOK.md`, `ARCHITECTURE.md`, `GLOSSARY.md` and `ROADMAP.md`.

### Changed
- Stage C goldens regenerated: the committed values could not be reproduced on this machine by any generator version or venv, while reruns are byte-identical to each other. 31 output lines in 6 files moved, each by at most 1.4e-4 of its own tolerance (largest: `greeks-0014` volga, 2.7e-8 absolute), and quote inputs of `usecases_c-0001` and `-0002` moved in the last bits. The cause is the platform's numerics, not seeding, threads, order or solver starts.
- Stage B case `ois-0023` now sends `TONA`, not `ESTR`, as its unlisted convention (ruling D27).

### Known issues
- Free data is thin. The stage D data survey (2026-11-07) found free overnight fixings, fitted Bank of England curves, US Treasury par and real curves and UK CPI, but no free swap quotes, bond-level prices, special repo, cross-currency basis, CDS spreads, borrow, commodity curves or MBS factors. Those studies stay method tests on synthetic data.
- Python fuzz volume is low compared with the other languages.
- Python has 40 mypy errors in older modules. mypy is not a CI check.
- Several stage D suites have no outside oracle (`specifications/stage-d-rulings.md`).

## 0.3.0: stage C, equity vol slice (2026-11-07)

Tagged v0.3 on `20d4d07` after main CI passed. Stage C is at Implemented, not Validated. Figures are local runs on Windows, 2026-11-07, on branch `stage-c`; pull request #13 and main CI then passed.

### Added
- Stage C in all four implementations, from the specs alone: equity forwards on funding and borrow curves with discrete dividends, Black-Scholes, Black-76 and Bachelier prices and implied vols, analytic and bump Greeks, spot and forward delta conventions, risk-reversal and butterfly quotes, SVI and SSVI evaluation and fits with no-arbitrage checks, vol surface query, check and vega, Hagan SABR with a density check, arbitrage-free SABR (Hagan, Kumar, Lesniewski and Woodward, 2014), and use case 3.
- Specifications, numeric targets set before the code, and rulings C1 to C17. CLI contract 1.4.0 adds `E_ARBITRAGE`; the wire `contract_version` stays 1.0.0.
- 446 golden cases in 11 suites in `datasets/golden/stage_c/`, from QuantLib, Strata, analytic and hand sources. All four builds passed all 5,183 cases. 30 wrong-convention checks, each shown to fail.
- Stage C sections in `LEARN.md`, `COOKBOOK.md`, `ARCHITECTURE.md`, `GLOSSARY.md` and `ROADMAP.md`.

### Fixed
- Java crashed in `vol.sabr.calibrate` on extreme input; found by fuzzing and fixed. Fuzz is now clean on all four.
- Rulings C15 to C17 settled three edge cases where the languages had diverged: `scale` against delta convention, `vol.sabr.arbfree` prices with no finite vol, and empty arrays.

### Known issues
- All stage C inputs are synthetic. The stage C data survey found no free history of equity or index option quotes, implied vol surfaces, stock borrow cost or dividends. Cboe publishes free daily VIX-family closes, but reuse needs Cboe's approval, and they are not a surface. Stage C results show the methods, not a market.
- `vol.sabr.arbfree` at `nu > 0` has no tight outside source; the `nu = 0` cases are checked against CEV.
- Python has 40 mypy errors in older modules. mypy is not a CI check.
- European options only (ruling C1). Arbitrage checks run on the given points only.

## Unreleased: evidence cleanup after v0.2

### Added
- Curves gallery in `docs/curves/`: SONIA OIS, minimal SOFR OIS, `USD-TERM-3M` projection and GBPUSD FX forward pages, with charts and numbers from real runs of all four CLIs on synthetic inputs, and a status table of every curve in the plan. `tools/build_gallery.py` generates it; `--check` runs in `docs.yml` against the Python CLI. Stage B stays Implemented, not Validated.
- Examples `ois_bootstrap_sofr.json`, `projection_bootstrap.json`, `fx_forward_outright.json` and `fx_curve_implied.json`, with synthetic inputs.
- Per-stage structure in `LEARN.md`, `COOKBOOK.md`, `ARCHITECTURE.md`, `GLOSSARY.md` and `ROADMAP.md`, with done, carried and planned status for each stage.

### Changed
- Swap and FRA checks against QuantLib now assert 1e-5 on a notional of 1,000,000. Use case 1 has an outside QuantLib check. The invariant checker covers stage B. Constructed inputs carry the `synthetic` tag. 4,737 golden cases; no golden value changed.
- Rust checks array limits before work, closing its gap against ruling B24.
- The recorder has six sources, each with its notice, and stores identical bytes once while still logging them.
- All four CLIs report version 0.2.0.

## v0.2: stage B, FX and rates slices

Released as v0.2 (tag on `fe33b40`). Stage B is at Implemented, not Validated: validation is self-assessment until the human review after the project. The figures below are one local run on Windows, 2026-11-06, at commit `13d9871`. The branch has not been pushed, so CI has not run it.

### Added
- Stage B in all four implementations, from the specs alone: units and money, convention registry, schedules, curve object, SONIA and minimal SOFR OIS bootstrap (sequential and global), bid/ask by mid, projection curves, FRAs, swaps, tenor basis, FX forwards, FX swaps, implied curves and quote-driven basis, FX delta, Gauss-Newton, Levenberg-Marquardt, BFGS, regularisation, a calibration sensitivity report, DV01, key-rate risk, duration, hedge solve with a simple spread-based cost, and use cases 1 and 2.
- Specifications for all of that, numeric targets set before the code, and rulings B0 to B24. CLI contract 1.3.0; the wire `contract_version` stays 1.0.0.
- 343 golden cases in 18 suites in `datasets/golden/stage_b/`. All four builds passed all 4,731 cases in 39 suites. `specifications/stage-b-rulings.md` lists which suites have an outside oracle; `usecases` and `rulings_b` have none.
- 23 deliberate convention errors in `oracle/MUTANTS.md`, each caught by the deep suites.
- Tickets W06 to W12, W20 and W25, data and solutions for EX-005, EX-006, EX-008 and EX-009, stage B examples and worked examples.
- Data survey results in `datasets/data-availability.md`: FRED dropped, Bank of England forwards added as conditional, and most curve inputs labelled synthetic.

### Known issues
- Rust does not fully meet ruling B24: cheap array operations make a few linear passes before `E_LIMIT`.
- Clang on Windows is blocked at times by Application Control, so Clang conformance relies on CI.
- `tools/recorder/sources.json` still lags the data survey on SONIA and ECB terms. The recorder remains unscheduled.
- The oracle's invariant check covers `datasets/golden/core/` only, so its count is 4,388.

## v0.1: stage A, Foundation

Released 2026-11-06, tag `v0.1` on `a60d814`. Validation is self-assessment until the human review after the project. The conformance figures below are one local run on Windows, 2026-11-06; the workflows triggered by pull request #1 then passed on GitHub, including conformance in all four languages, GCC, Clang and sanitizers.

### Added
- Four equal implementations of domain 01, in Java 25, C++26, Python 3.15.2 and Rust 1.99.1, each behind the `quantforge` CLI.
- Specifications for day counts, calendars, compounding, timezones and cut-off, data checks, snapshot hash, as-of store and replay, RNG, Sobol, root finders, integration, interpolation, differentiation and linear algebra, statistics and time series, PDE, Monte Carlo and COS, with rulings and input limits. CLI contract 1.2.0.
- `oracle/`, using exact rationals, mpmath, QuantLib, Strata, NumPy and SciPy, hand cases and replay. 4,388 golden cases in 21 suites. All four builds passed all of them.
- Neutral runner, CLI fuzz driver, mutation harnesses, and CI workflows.
- Public-data recorder with a licence manifest, and a hash-chained forward log. The recorder is built but not scheduled.
- Schemas, tolerance policy with no global default, data-availability table, oracle map and licences, ADR-0009 and ADR-0010, numeric targets for stage B.
- Golden-case mutation scoring for Rust and Python, `examples/`, a CLI throughput harness in `benchmarks/`, and a static docs site build.
- Root documents, diagrams, tickets W01 to W05, exercises 1 to 3 with data and solutions, traceability table.

### Changed
- Reworked the starter scaffold: four equal implementations, full MIT text, pinned toolchains and actions, date-based Rust day counts, Catch2 tests for C++.

### Removed
- 36-week roadmap, epics and generated manifest.
