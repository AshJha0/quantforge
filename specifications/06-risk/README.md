# Risk analytics

## Purpose
Define the scope and shared contract for the risk analytics domain.

## Capabilities
- Analytic and bump-and-revalue delta, gamma, vega, theta and rho
- DV01, key-rate DV01, duration and convexity
- CS01, spread duration, credit and FX exposure
- Portfolio VaR, expected shortfall and scenario aggregation
- Historical, hypothetical and reverse stress testing
- P&L explain, sensitivity reconciliation and risk attribution

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
- Finite-difference Greeks versus analytic values
- DV01 and key-rate risk on a swap portfolio
- Historical VaR and expected shortfall toy example
- Scenario shocks with correlated risk factors
- P&L explain residual diagnostics

## Acceptance criteria
- [ ] Domain contract reviewed and versioned.
- [ ] Analytical/simple benchmark cases independently checked.
- [ ] Normal, boundary, invalid and stress inputs covered.
- [ ] Python reference and applicable production implementations conform.
- [ ] Numerical diagnostics and failure modes are explicit.
- [ ] Deterministic fixtures and provenance are recorded.
- [ ] Performance baseline exists where relevant.
- [ ] User and developer documentation includes examples and limitations.
