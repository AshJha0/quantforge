# QuantForge
## Quantitative analytics and trading infrastructure

QuantForge is a quantitative library written four times, in Java, C++, Python and Rust, from one set of specifications. The plan covers market data, curves, calibration, pricing, volatility, risk, portfolio analytics, hedging, market microstructure, execution analytics and systematic research. Only the first stage, Foundation, is built so far: see Status below.

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
| `datasets/` | Schemas and golden files |
| `conformance/` | Neutral runner, fuzz and mutation harnesses, tolerance policy |
| `tools/` | Public-data recorder and forward log |
| `program/` | Tickets, exercises and traceability |
| `docs/` | Developer guides, getting started and diagrams |
| `.github/` | CI and issue templates |

### Start here
1. `LEARN.md` for a path through the maths, `COOKBOOK.md` for commands.
2. `ARCHITECTURE.md`, then the ADRs in `architecture/decisions/`.
3. `ROADMAP.md` for the stages, `GLOSSARY.md` for terms.

### Status
Each capability moves through `Proposed → Specified → Implemented → Validated → Benchmarked → Operationally tested`. Stage A, domain 01, is at Implemented. Nothing is claimed as Validated, Benchmarked or Operationally tested, and domains 02 to 12 are capability lists only.

What has run (observed, local): on 2026-11-06, at commit `ffa0585`, all four implementations passed all 4,388 golden cases in 21 suites through the neutral runner, on one Windows machine.

What that does not show:
- **Validation is self-assessment** until the human review after the project ends. Many golden cases have only hand or replay sources, which can share a misreading with the spec (`oracle/README.md`).
- **CI has not yet run on GitHub.** The workflows are written, but no result here comes from them.
- **The recorder is built but not scheduled.** There is no daily record yet: the forward log holds one run, from 2026-11-06.
- **No market data is used.** Golden cases are constructed test values, and any synthetic data is labelled as synthetic.
- **Trading is simulated only.** There are no live orders, and stage A contains no trading code. QuantForge makes no HFT or latency claims, and no benchmark has been run.

### Licensing and market data
The project is MIT-licensed, with third-party notices in `THIRD_PARTY_NOTICES.md`. Market-data licensing and redistribution rights are separate: only commit data that you are entitled to redistribute. Prefer deterministic synthetic data for CI.
