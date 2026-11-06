# QuantForge
## Quantitative analytics and trading infrastructure

**Engineering the foundations of quantitative finance.**

QuantForge is a multi-language quantitative engineering platform for financial mathematics, market data, curves, calibration, pricing, volatility, risk, portfolio analytics, hedging, market microstructure, execution analytics and systematic research.

### Technology targets
- **Python:** 3.15.2, pinned per release.
- **C++26:** low-latency and high-throughput quantitative components; compiler feature support is detected.
- **Java 25:** enterprise and high-throughput services.
- **Rust:** 1.99.1, pinned per release, 2024 edition.

### Design principles
1. Mathematical specifications precede implementations.
2. Java, C++, Python and Rust are four equal implementations; none is the reference.
3. Each is written from the specification alone, with no shared code, FFI or generated maths.
4. Specifications, schemas, fixtures and conformance contracts are shared.
5. Golden results are independently verified; agreement between implementations alone is insufficient.
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
| `datasets/` | Synthetic fixtures, schemas and golden-result contracts |
| `conformance/` | Cross-language test vectors and tolerance policy |
| `program/` | Tickets and exercises |
| `docs/` | User, developer and operational guides |
| `.github/` | CI and issue templates |

### Start here
1. Read `architecture/system-overview.md`.
2. Read the ADRs in `architecture/decisions/`.
3. Review `ROADMAP.md`.

### Scope and status
This is an early scaffold and nothing here is validated yet. Each capability advances through `Proposed → Specified → Implemented → Validated → Benchmarked → Operationally tested`. Trading is simulated only; there are no live orders.

### Licensing and market data
The project scaffold is MIT-licensed. Market-data licensing and redistribution rights are separate: only commit data that you are entitled to redistribute. Prefer deterministic synthetic data for CI.
