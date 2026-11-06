# Roadmap

Eleven stages, one pull request and one tag each. Estimates are plan-weeks, 106 in all, not calendar weeks, and are re-estimated after stage A.

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

Stage A is built on the `stage-a` branch and awaits its pull request; no tag exists yet. Stages B to K have not started, and each domain's real specs are written before its own stage. The use cases are defined in the project plan, which is kept outside this repository.

## Not in the repository yet

Planned, and absent today: `infra/`, `examples/`, benchmarks and any benchmark result, the docs site and its CI build, API docs per package, the eight-file spec sets and validation reports per model, per-domain flow diagrams, microstructure folders in the four implementations, and data and solutions for EX-004 to EX-012.
