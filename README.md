# QuantForge
## Quantitative analytics and trading infrastructure

QuantForge is a quantitative library written four times, in Java, C++, Python and Rust, from one set of specifications. The plan covers market data, curves, calibration, pricing, volatility, risk, portfolio analytics, hedging, market microstructure, execution analytics and systematic research. Two stages are built so far: Foundation (released as v0.1) and the FX and rates slices (stage B, target v0.2). See Status below.

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

### Status
Each capability moves through `Proposed → Specified → Implemented → Validated → Benchmarked → Operationally tested`. Stage A (domain 01) and the stage B slices of domains 02, 03, 04, 06 and 08 are at Implemented. Nothing is claimed as Validated, Benchmarked or Operationally tested. The rest of those domains, and domains 05, 07 and 09 to 12, are capability lists only.

Stage B covers SONIA and minimal SOFR OIS curves, projection curves, FRAs, swaps, FX forwards and swaps, quote-driven basis, Gauss-Newton, Levenberg-Marquardt and BFGS fits, DV01 and key-rate risk, and hedges with a spread-based cost. It targets v0.2, which is not tagged. v0.1 was released on 2026-11-06.

What has run (observed, local): on 2026-11-06, after the evidence cleanup, all four implementations passed all 4,737 golden cases in 40 suites through the neutral runner, on one Windows machine. That is 4,388 cases in 21 stage A suites, and 343 cases in 18 stage B suites.

What that does not show:
- **Validation is self-assessment** until the human review after the project ends. Many golden cases have only hand or replay sources, which can share a misreading with the spec. For stage B, `specifications/stage-b-rulings.md` lists which suites have an outside oracle: `usecases` and `rulings_b` have none, and `risk` is hand and self-consistency only, as are tenor basis and the FX forward, PV and delta formulas.
- **Stage B has not run in CI.** Stage A's pull request passed every workflow it triggered on GitHub. The `stage-b` branch has not been pushed, so every stage B result is local.
- **The recorder is built but not scheduled.** There is no daily record yet.
- **No market data is used.** Golden cases are constructed test values. Stage B curve data is labelled synthetic for almost everything, because no free history of OIS, swap, FRA, basis or bid/ask quotes was found (`datasets/data-availability.md`). A passing curve case shows the method agrees with its oracle on those quotes. It says nothing about fit to a market.
- **Trading is simulated only.** There are no live orders, and nothing here connects to a market: the hedges in stage B are calculations. QuantForge makes no HFT or latency claims. The only benchmark is one laptop run of CLI batch throughput on a stage A suite, in `benchmarks/`.

### Known issues
- **Clang on Windows** is blocked at times by Windows Application Control, which stops freshly built binaries. Clang conformance therefore relies on CI, which has not yet run stage B.
- **Licence questions are open** on SONIA redistribution and on the Bank of England's forward and curve data. Raw data stays local (`oracle/LICENCES.md`).

### Licensing and market data
The project is MIT-licensed, with third-party notices in `THIRD_PARTY_NOTICES.md`. Market-data licensing and redistribution rights are separate: only commit data that you are entitled to redistribute. Prefer deterministic synthetic data for CI. Notices for each public source are in `THIRD_PARTY_NOTICES.md`.
