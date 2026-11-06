# System overview

## Mission
Provide reusable, testable quantitative capabilities from raw market observations through valuation, portfolio risk, hedging and execution analysis. Stages A and B have built the data, conventions and numerical layers, and FX and rates slices of the domain engines; the rest of this page describes the target.

## Logical layers
1. **Data and conventions:** market-data contracts, instrument definitions, calendars, timestamps, currencies and units.
2. **Financial mathematics:** numerical methods, statistics, interpolation, optimisation and linear algebra.
3. **Domain engines:** curves, calibration, pricing, volatility, risk, portfolio, hedging, microstructure and execution.
4. **Research and replay:** historical replay, simulation, backtesting and attribution.
5. **Integration and operations:** APIs, orchestration, observability, audit and reproducibility.

## Dependency rules
- Domain packages depend on core contracts and explicitly declared domain interfaces.
- Core must not depend on product-specific or execution-specific packages.
- Pricing may consume curves and calibrated models through stable interfaces.
- Risk may consume valuation and sensitivity interfaces; it must not depend on private pricing implementation details.
- Execution analytics may consume orders, trades and market data without depending on pricing.
- Backtesting orchestrates domain interfaces; it does not own duplicate pricing or risk mathematics.
- No language implementation calls another language implementation to perform its core calculations.

## Data flow
`Source → Normalised Observation → Immutable Snapshot → Model Inputs → Calculation → Result + Diagnostics + Provenance`

Every material result should identify:
- valuation/calculation timestamp and timezone;
- input snapshot ID and source lineage;
- instrument and convention identifiers;
- model and configuration version;
- units, currency and numerical method;
- warnings, validation status and diagnostics.

## Runtime topology
Begin with libraries and command-line examples. Add services only when a concrete integration use case requires them. Do not prematurely split the platform into microservices.

## Quality gates
Mathematical correctness, numerical stability, deterministic reproducibility, cross-language conformance, performance evidence and operational behaviour.
