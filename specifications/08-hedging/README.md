# Hedging and optimisation

## Purpose
Define the scope and shared contract for the hedging and optimisation domain.

## Capabilities
- Delta, DV01, key-rate, FX and vega hedge construction
- Minimum-variance and constrained least-squares hedging
- Multi-instrument hedge selection and residual risk
- Transaction-cost, liquidity and lot-size-aware optimisation
- Dynamic hedge rebalancing and hedge effectiveness
- Optimisation diagnostics, infeasibility and sensitivity

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
- Single-instrument delta hedge
- Key-rate DV01 hedge with multiple bonds
- Constrained least-squares hedge
- Cost-aware hedge versus risk-only hedge
- Discrete lot-size and infeasible constraints

## Acceptance criteria
- [ ] Domain contract reviewed and versioned.
- [ ] Analytical/simple benchmark cases independently checked.
- [ ] Normal, boundary, invalid and stress inputs covered.
- [ ] Python reference and applicable production implementations conform.
- [ ] Numerical diagnostics and failure modes are explicit.
- [ ] Deterministic fixtures and provenance are recorded.
- [ ] Performance baseline exists where relevant.
- [ ] User and developer documentation includes examples and limitations.
