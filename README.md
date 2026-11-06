# QuantForge
## Institutional Quantitative Analytics & Trading Infrastructure

**Engineering the foundations of quantitative finance.**

QuantForge is a multi-language quantitative engineering platform for financial mathematics, market data, curves, calibration, pricing, volatility, risk, portfolio analytics, hedging, market microstructure, execution analytics and systematic research.

### Technology targets
- **Python:** latest stable Python 3.x; research, reference models and validation.
- **C++26:** low-latency and high-throughput quantitative components; compiler feature support is detected.
- **Java 25:** enterprise and high-throughput services.
- **Rust:** latest stable compiler, Rust 2024 edition.

### Design principles
1. Mathematical specifications precede implementations.
2. Python is a readable reference implementation, not a runtime dependency of other languages.
3. C++, Java and Rust implement domain logic independently.
4. Specifications, schemas, fixtures and conformance contracts are shared.
5. Golden results are independently verified; agreement between implementations alone is insufficient.
6. Correctness, numerical stability and reproducibility precede optimisation.
7. Performance claims require documented hardware, workload and methodology.

### Repository map
| Path | Purpose |
|---|---|
| `architecture/` | System architecture and ADRs |
| `specifications/` | Domain mathematics, contracts and acceptance criteria |
| `python/` | Python reference and research packages |
| `cpp26/` | C++26 implementation |
| `java25/` | Java 25 implementation |
| `rust/` | Rust 2024 workspace |
| `datasets/` | Synthetic fixtures, schemas and golden-result contracts |
| `conformance/` | Cross-language test vectors and tolerance policy |
| `program/` | 36-week roadmap, epics, weekly tickets and exercises |
| `docs/` | User, developer and operational guides |
| `.github/` | CI and issue templates |

### Start here
1. Read `architecture/system-overview.md`.
2. Read the ADRs in `architecture/decisions/`.
3. Review `program/36-week-roadmap.md`.
4. Start Sprint 0 using `program/epics/EPIC-00-foundation.md`.
5. Implement the first vertical slice in `program/weekly-tickets/W01.md`.

### Scope and status
This archive is a project scaffold and implementation programme, not a claim that the models are already implemented, validated or production-ready. Each domain advances through `Proposed → Specified → Implemented → Validated → Benchmarked → Production Ready`.

### Licensing and market data
The project scaffold is MIT-licensed. Market-data licensing and redistribution rights are separate: only commit data that you are entitled to redistribute. Prefer deterministic synthetic data for CI.
