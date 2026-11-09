# QuantForge

[![Python](https://github.com/AshJha0/quantforge/actions/workflows/python.yml/badge.svg)](https://github.com/AshJha0/quantforge/actions/workflows/python.yml) [![Rust](https://github.com/AshJha0/quantforge/actions/workflows/rust.yml/badge.svg)](https://github.com/AshJha0/quantforge/actions/workflows/rust.yml) [![Java 25](https://github.com/AshJha0/quantforge/actions/workflows/java25.yml/badge.svg)](https://github.com/AshJha0/quantforge/actions/workflows/java25.yml) [![C++26](https://github.com/AshJha0/quantforge/actions/workflows/cpp26.yml/badge.svg)](https://github.com/AshJha0/quantforge/actions/workflows/cpp26.yml) [![Docs](https://github.com/AshJha0/quantforge/actions/workflows/docs.yml/badge.svg)](https://ashjha0.github.io/quantforge/) [![Licence: MIT](https://img.shields.io/badge/licence-MIT-blue.svg)](LICENSE)

Quick start: with [uv](https://docs.astral.sh/uv/) installed, from the repository root (uv fetches Python 3.15 on the first run):

<!-- quickstart:begin -->
```bash
uv run --project python quantforge batch < examples/batch.jsonl
```

```json
{"schema_version":"1.0","case_id":"example-daycount","status":"ok","outputs":{"year_fraction":0.5055555555555555},"diagnostics":{}}
{"schema_version":"1.0","case_id":"example-discount","status":"ok","outputs":{"discount_factor":0.9048374180359595},"diagnostics":{}}
{"schema_version":"1.0","case_id":"example-root","status":"ok","outputs":{"root":2.094551481542327},"diagnostics":{"iterations":7,"residual":3.552713678800501e-15,"termination":"X_TOL"}}
{"schema_version":"1.0","case_id":"example-error","status":"error","error":{"code":"E_DATE_ORDER","message":"end is before start","field":"end"},"diagnostics":{}}
```
<!-- quickstart:end -->

That is an ACT/360 year fraction, a discount factor, a root find and a refused input, printed by the Python build on Windows (*observed*, 2026-11-09). `docs.yml` runs the block on every PR (`tools/check_quickstart.py`). Docs site: <https://ashjha0.github.io/quantforge/>
## Quantitative analytics and trading infrastructure

QuantForge is a quantitative library written four times, in Java, C++, Python and Rust, from one set of specifications. The plan covers market data, curves, calibration, pricing, volatility, risk, portfolio analytics, hedging, market microstructure, execution analytics and systematic research. Five stages are built so far: Foundation (released as v0.1), the FX and rates slices (v0.2), the equity vol slice (v0.3), curves and fixed income (stage D, v0.4) and full volatility and exotics (stage E, v0.5.0). Phases R1, credibility hardening (v0.4.1), and R2, risk first (v0.4.2), sit between stages D and E. See Status below.

### What it can and cannot show
On free public data, QuantForge can show correct pricing and risk, curve quality against published curves, and signals on fitted curves tested against preregistered pass rules (research/preregs, amended 2026-11-09: one-sided deflated test, 24-trial family, Holm correction; the studies are underpowered and say so).

It cannot show tradable profitability. That needs instrument-level prices, bid and ask, financing and execution data, which cost money. This is a deliberate limit of a zero-spend project. Today every golden case uses synthetic inputs, and risk is bump-and-revalue sensitivities with P&L explain (R2), not a portfolio risk engine.

### Toolchains
- **Java 25:** JDK 25.0.5.
- **C++26:** GCC 16.2, and Clang.
- **Python:** 3.15.2, pinned per release. The oracle runs separately on 3.12.
- **Rust:** 1.99.1, pinned per release, 2024 edition.

### Design principles
1. Mathematical specifications precede implementations.
2. Java, C++, Python and Rust are four equal implementations; none is the reference.
3. Each is written from the specification alone, with no shared code, FFI or generated maths.
4. Specifications, schemas, fixtures and conformance contracts are shared.
5. Expected results come from `oracle/`, never from an implementation. Agreement between implementations proves nothing on its own.
6. Correctness, numerical stability and reproducibility precede optimisation.
7. Performance claims require documented hardware, workload and methodology.

### Repository map
| Path | Purpose |
|---|---|
| `architecture/` | System architecture and ADRs |
| `specifications/` | Domain mathematics, contracts and acceptance criteria |
| `python/` | Python implementation |
| `cpp26/` | C++26 implementation |
| `java25/` | Java 25 implementation |
| `rust/` | Rust 2024 workspace |
| `oracle/` | Source of the golden results; tests only |
| `datasets/` | Schemas, golden files and the data-availability table |
| `conformance/` | Neutral runner, fuzz and mutation harnesses, tolerance policy |
| `tools/` | Public-data recorder, forward log and docs site build |
| `examples/` | Small cases to send to the CLI |
| `benchmarks/` | CLI batch throughput harness |
| `program/` | Tickets, exercises and traceability |
| `docs/` | Developer guides, getting started and diagrams |
| `.github/` | CI and issue templates |

### Start here
1. `LEARN.md` for a path through the maths, `COOKBOOK.md` for commands.
2. `ARCHITECTURE.md`, then the ADRs in `architecture/decisions/`.
3. `ROADMAP.md` for the stages, `GLOSSARY.md` for terms.
4. [Curves gallery](docs/curves/README.md): every implemented curve, with charts from real CLI runs on synthetic inputs.

### Status
Each capability moves through `Proposed → Specified → Implemented → Validated → Benchmarked → Operationally tested`. Stage A (domain 01), the stage B slices of domains 02, 03, 04, 06 and 08, the stage C slices of domains 02, 04, 05 and 06, the stage D slices of domains 02, 03, 04 and 05, and the stage E slices of domains 04, 05 and 06 are at Implemented. Nothing is claimed as Validated, Benchmarked or Operationally tested. The rest of those domains, and domains 07 and 09 to 12, are capability lists only.

Stage B covers SONIA and minimal SOFR OIS curves, projection curves, FRAs, swaps, FX forwards and swaps, quote-driven basis, Gauss-Newton, Levenberg-Marquardt and BFGS fits, DV01 and key-rate risk, and hedges with a spread-based cost. It was released as v0.2, tag on `fe33b40`. v0.1 was released on 2026-11-06.

Stage C covers equity forwards with borrow and discrete dividends, Black-Scholes, Black-76 and Bachelier prices and implied vols, Greeks, delta conventions, SVI and SSVI, vol surface checks, Hagan and arbitrage-free SABR, and use case 3. It was released as tag `v0.3` on 2026-11-07, after pull request #13 and main CI passed. On 2026-11-07 all four implementations passed all 5,183 golden cases locally, including 446 stage C cases in 11 suites, and the fuzz driver found nothing after a Java fix. All stage C inputs are synthetic.

Stage D was released as tag `v0.4` on 2026-11-07. It covers OIS curves (full SOFR and ESTR) with turn-of-year jumps, overnight compounding conventions and IBOR fallbacks, meeting-date steps, futures convexity, CSA discounting, index basis and joint and robust curve fits; bonds, repo and bond futures; cross-currency basis on a synthetic constant-notional basis swap, not a market-implied curve (ruling R1-1 in `specifications/r1-rulings.md`), and NDFs; ISDA CDS, which needs `LOG_LINEAR_DF` discount curves; equity dividend, borrow and index work; inflation and linkers; caps and swaptions on stylised conventions; commodity curves; and MBS. At merge `95cbf11` on 2026-11-07, each of the four implementations passed 5,514 of 5,514 golden cases locally, 331 of them in stage D's 20 suites, and fuzzing with seed 17 found nothing (`conformance/README.md`). All stage D inputs are synthetic. The ESTR payment lag of 2 is a library choice taken from Strata, not a market standard (TP ICAP uses 1), and bond-future conversion factors take a `contract` input with CME rounding from R1 (rulings R1-2, R1-3).

R1 (tag `v0.4.1`) added no new pricing. It added:
- batch mode, CLI contract 1.6.0 (`quantforge --batch`, `--timings`, rules BT1 to BT8), with 19 stream fixtures in `datasets/batch/streams.json`;
- rulings R1-1 to R1-6 (`specifications/r1-rulings.md`) and an [edge-case register](specifications/edge-case-register.md) of 14 rows;
- a [model inventory and limitations register](docs/model-inventory.md);
- calendar provenance (`datasets/calendar_provenance.json`) and tolerances restated as money on 10 million notional (`conformance/tolerances/money.md`);
- scheduled jobs on GitHub Actions: the recorder with a gap monitor, a 12-cell cross-platform conformance matrix, daily workflows (a) and (c) through `--batch`, sanity bands that include Bank of England GBP curves, a per-stage mutation report, an outside-oracle floor and a calendar expiry check ([R1 infrastructure](docs/developer-guides/r1-infra.md));
- batch performance targets, written before measuring ([benchmarks/targets.md](benchmarks/targets.md));
- three R3 preregistrations, signed by Claude under the owner's delegation, with the holdout unread (`research/preregs/`).

R2 (tag `v0.4.2`) added risk: par and key-rate risk, the Jacobian and P&L explain, with 85 new goldens re-priced in QuantLib. There are now 5,922 golden cases in 76 suite files. Unit-test line coverage is C++ 94.2%, Java 97.3%, Rust 96.5% (reported by the language lanes) and Python 97.2% (5,806 of 5,976 lines of `quantforge_core`, coverage.py over 365 tests, measured on `r1` at `3f5d97d`).

Stage E (v0.5.0, untagged until the release) adds the full volatility and exotics layer in eight slices: arbitrage-free SVI surfaces with Dupire local vol and forward vol, the Heston family (Heston, Bates, Merton) and SLV leverage, FX smile conventions, a SABR swaption cube with caplet stripping, bond futures options and inflation caps, exotics and American options, correlation repair, implied correlation and dispersion, GARCH(1,1), variance swaps and a VIX-style index, CDS options, Gaussian and Student-t copulas and the large-pool model. Specs are in `specifications/04-pricing/`, `05-volatility/` and `06-risk/`, with rulings E-A1 to E-A40 and E-B1 to E-B40. There are now 6,817 golden cases in 91 suite files (counted from `datasets/golden/`).

What has run for stage E: at merge `597abf2` (2026-11-08), C++, Java and Rust each reported 6,817 of 6,817 golden cases passing in their final stage E commits (`5af077d`, `a9cd195`, `141245d`; reported), and Python passed 6,817 of 6,817 through the neutral runner on the merged tree (observed, local, Windows, 2026-11-08). Outside oracle: 557 of the 895 stage E cases (62.2%) are re-priced in QuantLib 1.44 with every output a QuantLib value (rule 11.2.5, rulings E-A17 and E-B28), above the 60% floor by 20 cases.

What had run for R2 (observed, local): on the merged `r2` tree on 2026-11-08, from clean builds on one Windows machine, Java, C++, Python and Rust each passed 5,922 of 5,922 golden cases through the neutral runner, every batch check and their unit tests. Fuzzing 60 seconds per language with seed 53 found nothing, and `run_all.py` regenerated every golden byte-identical.

What that does not show:
- **Validation is self-assessment** until the human review after the project ends. Many golden cases have only hand or replay sources, which can share a misreading with the spec. For stage B, `specifications/stage-b-rulings.md` lists which suites have an outside oracle: `usecases` and `rulings_b` have none, and `risk` is hand and self-consistency only, as are tenor basis, FX outright points, FX swap PV and basis. FX forward PV and delta have QuantLib `FxForward` checks in `fx_deep`.
- **CI.** Stages A to D passed every workflow they triggered on GitHub, on their pull requests and on `main`. Fuzz and mutation workflows run on a schedule or by hand.
- **R2 risk is checked on goldens and one real-move run.** It adds par and key-rate risk, the Jacobian and P&L explain (`specifications/06-risk/`), with 85 new goldens re-priced in QuantLib. On real 2025 Treasury moves, P&L explain explained 100% of days on every product in Java and Python, against a 95% target. The calibration stability report passed 28 of 28 across the four languages, including C3 under ruling R2-A9.
- **Citations are only partly opened.** The citations lane reports 10 sources opened and confirmed, 2 partly confirmed and 16 unreachable; licensed sources (books such as Hull, Clark and O'Kane) are still not opened and need a human. Equation numbers in paywalled papers (Heston 1993, Bates 1996, Merton 1976, Dupire 1994, Carr and Madan 1999) are given from memory and unverified (`specifications/stage-e-sources.md`). Stage E's VIX rules were read against Cboe's methodology v5.0 (ruling E-B15).
- **Outside-oracle coverage is partial.** Stage E: 62.2% (557 of 895) under rule 11.2.5 and rulings E-A17 and E-B28; GARCH, the VIX method, the Student-t copula, the large-pool model, SLV and the American FD scheme have no QuantLib object in the Python wheel and rest on hand cases and high-precision replicas. Stage D: 64.1% of cases are outside-oracle checked under rule 11.2.5; most counted cases are fixed-rate bonds. Every suite still at 0% has a reason why not in the [coverage table](oracle/REPORT.md#stage-d-outside-oracle-coverage-rule-1125).
- **Some scheduled jobs have no result yet.** The recorder is live and pushes to `forward-log` with no gaps, and the daily workflows run. The cross-platform matrix runs on `main` after the R2 merge and has no published result yet, so there is no macOS or Linux result for Java, Python or Rust. Stage D mutation score: Rust 93.4%, Java 86.2% (credit now 83.3%, from 73.8%), Python 74.2% on unit tests plus the stage D goldens (65.0% on unit tests alone, 89.0% leaving out mutants that change only error-message text, which the contract does not compare), C++ 82.5% with unit tests. C++ has passed all 5,514 v0.4 goldens on Linux, with GCC 15.2 under WSL (`docs/developer-guides/r1-infra.md`).
- **No market data is used.** Golden cases are constructed test values. Stage B curve data is labelled synthetic for almost everything, because no free history of OIS, swap, FRA, basis or bid/ask quotes was found (`datasets/data-availability.md`). A passing curve case shows the method agrees with its oracle on those quotes. It says nothing about fit to a market.
- **Trading is simulated only.** There are no live orders, and nothing here connects to a market: the hedges in stage B are calculations. QuantForge makes no HFT or latency claims. The only benchmark result is one laptop run of CLI batch throughput on a stage A suite, in `benchmarks/`; the R1 targets in `benchmarks/targets.md` are now measured; see the misses below.

### Known issues
- **Clang on Windows** is blocked at times by Windows Application Control, which stops freshly built binaries. Clang conformance therefore relies on CI; GCC runs locally under WSL.
- **Licence questions are open** on SONIA redistribution and on the Bank of England's forward and curve data. Raw data stays local (`oracle/LICENCES.md`).
- **Python fuzz is slow.** About 12,800 inputs a minute in the R2 check (seed 53, 60 s per language; up from about 9,500 at R1), against the target of 50,000; Rust and C++ ran 126,600 and 92,600 in the same check (*observed* at R2, not re-measured for stage E).
- **Performance targets missed.** Benchmarks against `benchmarks/targets.md`: C++ meets every target. Python meets T3 (10,000-trade key-rate risk in 214 s against 900 s, down from about 20,900 s once curve rebuilds were cached) and misses T1 (bootstrap p99 129 ms against 5 ms; p50 14.6 ms) and T4 (start-up 1.84 s against 1.0 s, of which `uv run` is about 1.1 s and QuantForge 0.1 s; `uv run` stays for reproducibility). Java misses T1 (p99 10.7 ms against 5 ms), put down to CPU contention on the test machine rather than code cost. Rust's T1 was measured under WSL and needs a rerun on native Linux.
- **Workflow (b), rich/cheap, still needs prices by hand** (ruling R2-A11). The recorder's new Fiscal Data auction feed (`fiscaldata-treasury-auctions` in `tools/recorder/sources.json`, open licence) was checked on 2026-11-08 and does not qualify: it gives each note or bond a price only on its own auction day (`price_per100`), and from 2026-08-01 to 2026-11-08 at most two notes or bonds were auctioned on any one day (23 auctions on 21 days, observed through the public API). The screen needs the whole coupon universe priced on one date, so a curve fit is impossible from auctions; the feed stays in use only to mark on-the-run issues. Daily security prices (TreasuryDirect FedInvest) are refused to automated clients by its robots.txt and terms, and the DMO's gilt prices sit behind an anti-bot page. The manual `--data DIR` path stays.
- **The calendar check stays red** until SIFMA publishes its 2027 US holiday schedule (usually in December); the USGS calendar is confirmed only through 2027-01-01.

### Licensing and market data
The project is MIT-licensed, with third-party notices in `THIRD_PARTY_NOTICES.md`. Market-data licensing and redistribution rights are separate: only commit data that you are entitled to redistribute. Prefer deterministic synthetic data for CI. Notices for each public source are in `THIRD_PARTY_NOTICES.md`.
