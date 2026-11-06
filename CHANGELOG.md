# Changelog

## Unreleased: stage B, FX and rates slices (target v0.2)

Not released. Stage B is at Implemented, not Validated: validation is self-assessment until the human review after the project. The figures below are one local run on Windows, 2026-11-06, at commit `13d9871`. The branch has not been pushed, so CI has not run it.

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
