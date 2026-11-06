# Portfolio analytics

## Purpose
Define the scope and shared contract for the portfolio analytics domain.

## Capabilities
- Position, trade and instrument aggregation
- Multi-asset, multi-currency valuation and FX translation
- Net/gross exposure, concentration and liquidity measures
- Factor, sector, currency and curve exposure
- Portfolio P&L, attribution and performance statistics
- Portfolio constraints, limits and scenario aggregation

## Required specification sections
- Mathematical definitions and assumptions
- Inputs, outputs, units and conventions
- Algorithms and numerical considerations
- Error handling and diagnostics
- Data provenance and model versioning
- Validation strategy and independent references
- Performance expectations and benchmark workload
- Limitations and unsupported cases

## Suggested exercises
- Aggregate multi-currency positions
- Net versus gross exposure reconciliation
- Portfolio P&L attribution
- Concentration and limit breach detection
- Portfolio risk aggregation consistency

## Acceptance criteria
- [ ] Domain contract reviewed and versioned.
- [ ] Analytical/simple benchmark cases independently checked.
- [ ] Normal, boundary, invalid and stress inputs covered.
- [ ] All four implementations conform, and the named oracle passes.
- [ ] Numerical diagnostics and failure modes are explicit.
- [ ] Deterministic fixtures and provenance are recorded.
- [ ] Performance baseline exists where relevant.
- [ ] User and developer documentation includes examples and limitations.
