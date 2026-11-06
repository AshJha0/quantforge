# QuantForge 36-week delivery programme

Assumption: one engineer working approximately 20–25 focused hours per week, with review/validation support. Four full implementations across all domains may take materially longer; treat weeks as sequencing guidance, not an unconditional delivery promise.

| Phase | Weeks | Focus | Release gate |
|---|---:|---|---|
| 1 | 1–5 | Core, data, numerical methods, CI and conformance | v0.1 foundation |
| 2 | 6–12 | Curves, calibration and pricing | v0.2 pricing |
| 3 | 13–18 | Volatility and quantitative models | v0.3 volatility |
| 4 | 19–24 | Risk and portfolio analytics | v0.4 risk |
| 5 | 25–30 | Hedging, microstructure and execution | v0.5 trading analytics |
| 6 | 31–36 | Research, integration, hardening and release | v1.0 platform |

## Weekly cadence
- Day 1: read spec, refine scope, identify assumptions and test cases.
- Day 2: implement/reference model and tests.
- Day 3: independent implementation or port and conformance.
- Day 4: edge cases, numerical review and benchmarks.
- Day 5: documentation, review, issue closure and demo.

## Release gates
A milestone cannot be tagged while critical mathematical, data-provenance, reproducibility or security defects remain open. Performance claims must include reproducible evidence.
