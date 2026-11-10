# Changelog

## 0.6.0: stage F, curve layer, portfolio risk and book (unreleased)

Stage F lands in two pull requests. Part 1 (PR #25, merged at `5c8fa9d`) holds wave 0 and the parallel lanes. Part 2 holds waves 1 to 3, listed first below. No golden value of an earlier stage changed. Language results for part 2 are recorded here at its merge; until then the stage F operations are *Specified*.

### Added (part 2)
- F1 curve layer: monotone convex (Hagan and West), monotonic log cubic, tension spline and hybrid interpolation, and `rates.curve.inspect` (`02-curves/curve-framework.md`, rulings F-18 to F-22, F-35). `rates.curve.joint_solve` adds a joint multi-curve solve with solved turns, meeting-date steps fitted to SR3 futures after convexity, and the IFT Jacobian. `rates.funding.curve` adds a funding curve over OIS (`02-curves/joint-solve-and-funding.md`, F-24 to F-28).
- F3 sensitivities: `risk.book.ois_sensitivity` (Q3a: exact par-quote risk and zero Jacobian of an OIS book, with an AAD reference in Rust), `risk.curve.pca`, `risk.curve.cross_gamma`, `risk.credit.jtd` (`06-risk/book-sensitivities.md`, F-29, F-30, F-36).
- F4 portfolio risk: historical, filtered historical, parametric and Monte Carlo VaR and ES; Kupiec, Christoffersen and the Basel traffic light (`06-risk/var-es-and-backtests.md`, F-31, F-32, F-39); FRTB-SA GIRR delta under MAR21 (`06-risk/frtb-sa-girr.md`, F-33).
- F5 book and use case 4: `book.lifecycle.apply`, `book.marks.resolve` (`07-portfolio/book-lifecycle.md`, F-34); `usecase.factor_attribution` (`04-pricing/use-cases.md`).
- F6 model fixes: R7 CDS index option on Pedersen's adjusted forward, R8 GARCH estimates with standard errors and Student-t innovations (the coverage study puts every parameter inside its preregistered band), R10 VIX null quotes and local-vol continuity at slice expiries.
- 438 stage F value goldens in 11 suites, besides the 5,207 E1 goldens: 12,462 golden cases in 125 suite files (counted from `datasets/golden/`). New tolerance classes `jacobian`, `standard_error`, `aad_sensitivity`, `ift_jacobian`. Model inventory entries MF-1 to MF-11.
- Outside oracle for stage F (`oracle/outside_f.py`): QuantLib 1.44, SciPy, NumPy and `arch` 7.2.0. `arch` runs under WSL, because Windows Application Control blocks pandas on the host.

### Added (part 1)
- T: tightened acceptance rows for A3, A4, A5, A7, Q1, Q3a and the equivalent-mutant sign-off, with parameters fixed before the items are built (`program/STAGE_F_HANDOVER.md`).
- E1: every public numeric input must be finite, else `E_DOMAIN`; a token in an Integer field is `E_SCHEMA` (ruling F-1). 5,207 shared goldens with NaN, +inf, -inf and -0.0 per input of every verb, passed by all four languages.
- E4: cross-language name map generated from the specs, and the API style ADR. Q5b: convergence order and limit-case field in the spec template, checked by `tools/quality_gate.py --check-specs`.
- A2: model-register fields (tier, challenger, monitoring thresholds, data-lineage hash, retirement trigger, validation report), checked by `--check-register`; earlier entries are on a baseline list.
- G2: microbenchmarks (criterion, JMH, Google Benchmark, pytest-benchmark) for bootstrap, swap PV and implied vol, with a regression gate against a stored baseline. G3: build-provenance attestation and a CycloneDX SBOM in `release.yml`. G6: coverage floors per language, a mutation gate, and property tests (proptest, jqwik, hypothesis). G8: weekly Dependabot security updates.
- E2: "Tutorial 1: price your first swap" in Python, Rust, Java and C++, run in CI by `tutorial.yml`; LEARN reordered by topic. E9: `docs/determinism.md`.
- E6: site accessibility (WCAG AA colours, skip link, focus styles, labelled charts) checked by pa11y-ci. E7: client-side site search and a home status table generated from the facts file. E10: `concurrency` on every workflow and PR mutation on changed files only. E11: a hygiene gate for tracked files over 1 MB and empty packages.
- R4: the forward-log head hash is anchored to OpenTimestamps by the recorder, with a verifier that detects a rewritten history.

### Changed
- Versions are 0.6.0 in all four builds (`cpp26/CMakeLists.txt`, `java25/pom.xml`, `python/pyproject.toml`, `rust/Cargo.toml` and their lock files), the oracle (`oracle/python/pyproject.toml`, `uv.lock`) and `oracle/strata/pom.xml`; the site facts name stage F as the pending release.
- G4: modules are named by domain, not by stage letter, in all four languages, and CLI dispatch uses a registry. Conformance is unchanged. Mutation and quality configs follow the new paths.
- G9: Rust denies `clippy::unwrap_used` outside tests.

### Known issues (0.6.0)
- **Outside-oracle share is 51.4% (225 of 438): the 60% floor is not met.** Error cases stay in the denominator (coordinator ruling). `oracle/OUTSIDE_GAPS_F.md` lists every case without a free outside source, with its reason; 79 of the 213 are error cases. The R5 second review of the outside register is still owed.
- **R7 has no outside case.** Pedersen (2003), the CDS index option's reference example, is not freely available.
- **FRTB-SA GIRR `low` scenario formula is unconfirmed:** it is an image in MAR21.6 (ruling F-33). The equity FRTB parameters were read only in summary.
- **Deferred to wave 2b:**
  - F3: Inflation01, dividend and borrow sensitivity, correlation sensitivity;
  - F4: reverse stress, limits, concentration, liquidity-adjusted risk, portfolio vol by horizon, model-risk reserves;
  - FRTB: vega, curvature and the other risk classes.
- **E1 cases for the stage F operations are not yet generated** (`gen_stage_f_e1.py` skips `stage_f`).

## 0.5.0: stage E, full volatility and exotics (2026-11-09)

Tagged `v0.5.0` on `1b2bc7e` (PR #22). Two spec sessions wrote slices E1 to E8 in parallel; each language was built from the specs alone. No golden value of an earlier stage changed.

### Added
- Stage E closeout infrastructure (plan 13.1 R3, R12, E3, E5, E8): recorder sources for Treasury bill and real yield curves and BLS CPI (API v1, no key), with parsed values, `state_sha256`, revision rows, daily study rows for R3-01 to R3-03 and the `sources.json` hash in every row; `gap_monitor.py --studies` and `recheck`. FRED T5YIE and T10YIE are listed but disabled, because FRED's terms forbid storing its data; the breakevens are rebuilt from the Treasury curves. `release.yml` for vMAJOR.MINOR.PATCH tags, `tools/doctor.py`, a devcontainer, a rewritten CONTRIBUTING and a README quick start checked in CI.
- Stage E mutation scores and closeout tests (`test_mutants_e` in C++, Python and Rust): pooled CI score 84.3% before the new tests; every module and language at or above 80% after them by hand-applied survivor checks, not a fresh full run (table in `docs/model-inventory.md`).
- E1 arbitrage-free SVI surfaces (butterfly, calendar and wing checks, SSVI to SVI, surface fit), Dupire local vol on SVI slices, forward vol, smile dynamics and vol of vol (`05-volatility/arb-free-surfaces.md`, `local-and-forward-vol.md`).
- E2 Heston, Bates and Merton prices by the Lewis integral, and SLV leverage by a reference PDE scheme (`05-volatility/heston-family.md`).
- E3 FX smile: four delta types, three ATM types, risk-reversal and butterfly strikes, Garman-Kohlhagen (`05-volatility/fx-smile.md`).
- E4 SABR swaption cube on the D7 swaption, caplet stripping, bond futures options with yield vol, YoY and ZC inflation caps (`05-volatility/rates-vol-cube.md`).
- E5 digitals, barriers, geometric Asians, lookbacks, quanto, chooser, Kirk spread, moment-matched baskets; American options by CRR, BAW and FD (`04-pricing/exotics.md`).
- E6 correlation validation, Higham nearest correlation, implied correlation and dispersion (`06-risk/correlation.md`).
- E7 GARCH(1,1) likelihood, forecast and fit; variance swap replication and realised variance; a VIX-style index from caller strips, following Cboe's methodology v5.0 (`05-volatility/garch.md`, `variance-swaps.md`, `vix-index.md`).
- E8 CDS options with front-end protection, Gaussian and Student-t copulas, large-pool Vasicek tranches (`04-pricing/credit-options-and-copulas.md`).
- 895 stage E goldens in `datasets/golden/stage_e/` (446) and `stage_e_b/` (449); 6,817 goldens in all. Rulings E-A1 to E-A40 (`specifications/stage-e-rulings.md`) and E-B1 to E-B40 (`specifications/stage-e-rulings-b.md`), including two independent audits and the cross-language spec questions. Stage E rows in the model inventory and the edge-case register; stage E sections in `LEARN.md`, `COOKBOOK.md`, `ARCHITECTURE.md`, `GLOSSARY.md` and `ROADMAP.md`.
- Outside-oracle verifiers with their own convention maps: `oracle/OUTSIDE_E_A.md` and `oracle/CONVENTION_MAP_E_B.md`; registers `oracle/outside_register_e_a.json` and `oracle/outside_register_e_b.json`.

### Changed
- Versions are 0.5.0 in all four builds, the oracle (`oracle/python/pyproject.toml`, `uv.lock`) and `oracle/strata/pom.xml`.
- New tolerance class `likelihood_sum` in `conformance/tolerances/policy.yaml`; stage E goldens give non-money outputs their own class through `output_classes` (ruling E-B14).
- The outside-oracle count is stricter from stage E: a case counts only if every output is a QuantLib value or plain arithmetic on QuantLib values (rulings E-A17, E-B28). Under it, 557 of 895 stage E cases count (62.2%).

### Verified on the merged tree (`597abf2`, 2026-11-08)
- C++, Java and Rust each reported 6,817 of 6,817 golden cases passing in their final stage E commits (`5af077d`, `a9cd195`, `141245d`; reported). Java's commit also reports unit tests, batch checks and fuzz passing.
- Python passed 6,817 of 6,817 through the neutral runner (observed, local, Windows).
- Outside oracle: spec A 280 of 446, spec B 277 of 449, stage E 557 of 895 (62.2%), every counted row on QuantLib 1.44.

### Known issues (carried)
- Python misses performance targets T1 (bootstrap p99 129 ms against 5 ms) and T4 (start-up 1.84 s against 1.0 s, mostly `uv run`), and its fuzz rate (about 12,800 inputs a minute at R2) is short of the 50,000 target (`benchmarks/targets.md`; R2 figures, not re-measured for stage E).
- Rust T1 was measured under WSL; a native Linux rerun is still owed.
- The calendar provenance check stays red until SIFMA publishes its 2027 US holiday schedule (usually in December).
- Licensed citations (books such as Hull, Clark, O'Kane) are not opened and need a human to confirm them; equation numbers in paywalled papers are given from memory and unverified (`specifications/stage-e-sources.md`).
- Workflow (b) still takes prices by hand (`--data DIR`): the recorder's Fiscal Data auction feed gives a price per note or bond only on its auction day, at most two a day, so it cannot price the universe for a curve fit (checked 2026-11-08).
- GARCH, the VIX method, the Student-t copula, the large-pool model, SLV and the American FD scheme have no outside library; SLV and FD goldens test agreement between builds, not convergence.


## 0.4.2: R2, risk first (2026-11-08)

Released as tag `v0.4.2` (PR #19). No golden value of an earlier stage changed.

### Added
- CLI contract 1.7.0, with no new error code; the wire `contract_version` stays 1.0.0. New operations: `risk.curve.par` (bump and rebuild, one bucket per quote), `risk.curve.key_rate` (`TRIANGULAR` or `PILLAR` zero shifts on a given curve), `risk.curve.jacobian` (zero rates against par quotes) and `risk.pnl.explain` (full revaluation against par risk times the move, with threshold `0.05 max(|full_pnl|, gross_risk_pnl) + 1e-8 x notional`, a project choice and not the FRTB P&L attribution test; the real-move run reports Spearman and Kolmogorov-Smirnov statistics without judging them). Products are `OIS` and `BOND`. Specs in `specifications/06-risk/`.
- Goldens `datasets/golden/r2/risk_r2.json` (41 cases) and `pnl_r2.json` (44 cases), each re-priced in QuantLib 1.44. The oracle checks the pillar chain rule, par buckets against pillar key rates times the Jacobian, on every product.
- Specs for the calibration stability report (`03-calibration/stability.md`) and workflow (b), the rich/cheap screen (`04-pricing/workflow-b-rich-cheap.md`), and the real-move P&L explain tool `tools/workflows/pnl_explain.py`.
- Rulings R2-A1 to R2-A8 (`specifications/r2-rulings.md`), including a move-scaled P&L explain threshold (`pnl_r2` regenerated, no flag changed), `1/D_mod^2` rich/cheap weights with Treasury on-the-run and first off-the-run issues reported but not fitted, and the Jacobian basis (continuous zeros on ACT/365F).
- R2 sections in `LEARN.md`, `COOKBOOK.md`, `ARCHITECTURE.md`, `GLOSSARY.md` and `ROADMAP.md`.

### Changed
- Stage D outside-oracle coverage is 64.1% (419 of 654 cases) under rule 11.2.5, up from 63.4%: CSA (no FX) and cross-currency PV and bootstrap are now counted through QuantLib.
- P&L explain on real 2025 Treasury moves: 100% of days explained on every product, against a 95% target, in Java and Python. Spearman and KS are reported, not judged (2Y OIS 0.997 and 0.044; 10Y OIS 0.9998 and 0.028).
- Calibration stability: 28 of 28 pass, languages within 2e-8; C3 was rerun under R2-A9 and passes (all four languages, 2026-11-08).
- The Actions recorder is live and pushes to `forward-log` with no gaps; the daily workflows run.
- Stage D mutation score: Rust 93.4%, Java 86.2% (credit now 83.3%, from 73.8%), Python 74.2% on unit tests plus the stage D goldens (65.0% on unit tests alone, 89.0% leaving out mutants that change only error-message text, which the contract does not compare), C++ 82.5% with unit tests.
- Benchmarks against `benchmarks/targets.md`: C++ meets every target. Python meets T3 (10,000-trade key-rate risk in 214 s against 900 s, down from about 20,900 s once curve rebuilds were cached) and misses T1 (bootstrap p99 129 ms against 5 ms; p50 14.6 ms) and T4 (start-up 1.84 s against 1.0 s, of which `uv run` is about 1.1 s and QuantForge 0.1 s; `uv run` stays for reproducibility). Java misses T1 (p99 10.7 ms against 5 ms), put down to CPU contention on the test machine rather than code cost. Rust's T1 was measured under WSL and needs a rerun on native Linux.
- Citations: the citations lane reports 10 sources opened and confirmed, 2 partly confirmed and 16 unreachable; licensed sources are still not opened.

### Known issues
- The calendar provenance check still fails: SIFMA has not published its 2027 US holiday schedule, usually out in December, so the check stays red until then.
- Workflow (b), rich/cheap, is blocked on price data (R2-A11): TreasuryDirect's robots.txt and terms, and the DMO's anti-bot page. Manual path: `--data DIR`.
- Performance targets missed: Python T1 (bootstrap p99 129 ms against 5 ms) and T4 (start-up 1.84 s against 1.0 s, mostly `uv run`); Java T1 (p99 10.7 ms against 5 ms, CPU contention). Rust T1 needs a rerun on native Linux.
- Rust T1 was measured under WSL; a native Linux rerun is still owed.
- The licensed citations have not been opened and need a human to confirm them.
- The cross-platform matrix runs on main after the merge; its result is checked then, not before the PR.

### Verified on the merged tree (observed, local, Windows, 2026-11-08, `r2`)
- Java, C++, Python and Rust each pass 5,922 of 5,922 golden cases and every batch check; unit tests pass in all four.
- Fuzzing 60 seconds per language with seed 53 found nothing. Inputs a minute: Rust 126,600, C++ 92,600, Python 12,800 (up from about 9,500 at R1, still short of the 50,000 target), Java 8,600.
- Calibration stability 28 of 28; P&L explain on 2025 Treasury moves PASS; stage D outside-oracle coverage 64.1%; `run_all.py` regenerated every golden byte-identical.

## 0.4.1: R1, credibility hardening (2026-11-07)

*Note: the v0.4.1 tag (3194067) still carries 0.4.0 in the package manifests; the bump to 0.4.1 landed just after, in the follow-up PR.*

Merged as PR #17 (`3194067`). No new pricing. No golden value changed except where a ruling below says so.

### Added
- Batch mode, CLI contract 1.6.0: `quantforge --batch` as a synonym of `quantforge batch`, framing rules BT1 to BT8, the optional `--timings` flag (`diagnostics.elapsed_ns`), and 19 stream fixtures in `datasets/batch/streams.json`, checked by `conformance/runner/batch_check.py`. The wire `contract_version` stays 1.0.0.
- Rulings R1-1 to R1-6 (`specifications/r1-rulings.md`): cross-currency is a synthetic constant-notional basis swap; the ESTR payment lag of 2 is a Strata library choice, while TP ICAP terms use 1; bond-future conversion factors take an optional `contract` input with CME rounding; every credit operation needs a `LOG_LINEAR_DF` discount curve; cap and swaption conventions are stylised; USGS Good Fridays with a SIFMA early close are business days, and SOFR compounding skips every Good Friday.
- The edge-case register (`specifications/edge-case-register.md`, 14 rows), the model inventory (`docs/model-inventory.md`), calendar provenance (`datasets/calendar_provenance.json`) and tolerances in money (`conformance/tolerances/money.md`). 5,837 golden cases in 74 suite files.
- GitHub Actions jobs: recorder and gap monitor, cross-platform conformance (3 OS by 4 languages), daily workflows (a) and (c) through `--batch`, sanity bands including Bank of England GBP curves, per-stage mutation report, outside-oracle floor, calendar expiry. A local Linux C++ path under WSL. See `docs/developer-guides/r1-infra.md`.
- Batch performance targets, written before measuring (`benchmarks/targets.md`), and a real-data gallery page (`docs/curves/real-usd-treasury.md`).
- Three R3 preregistrations, signed by Claude under the owner's delegation; the holdout is unread.
- The honest-ceiling statement in `README.md` and on the site home page. Batch mode sections in `COOKBOOK.md` and `LEARN.md`, an R1 section in `ROADMAP.md`.

### Changed
- Unit-test line coverage: C++ 94.2%, Java 97.3%, Rust 96.5% (language lanes), Python 97.2% (measured on `3f5d97d`).
- Stage D outside-oracle coverage is 63.4% under rule 11.2.5, mostly fixed-rate bonds; every suite at 0% has a reason in `oracle/REPORT.md`.
- `README.md` no longer says stage D is untagged.

### Known issues
- Python fuzz runs about 9,500 inputs a minute (coordinator check, seed 41, 90 s) against a 50,000 target.
- The calendar provenance check fails until SIFMA publishes its 2027 US holiday schedule (usually in December); the USGS calendar is confirmed only through 2027-01-01.
- The mutation report and cross-platform matrix first run after the push, so neither has a result yet.

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
