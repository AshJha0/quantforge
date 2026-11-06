# Curves and term structures

## Purpose
Define the scope and shared contract for the curves and term structures domain.

## Capabilities
- Equity spot, dividend, borrow, financing and forward curves
- FX spot, forward points, FX swaps and cross-currency basis
- OIS discount, projection, government zero, par and forward curves
- Credit spread, hazard, survival, recovery and CDS curves
- Repo, securities financing, inflation and volatility term structures
- Bootstrap, interpolation, extrapolation, dependencies, snapshots and versioning

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
- Single-curve bootstrap from synthetic instruments
- Multi-curve dependency and discounting case
- Negative-rate and sparse-tenor cases
- Curve bump and rebuild reproducibility
- Interpolation/extrapolation boundary behaviour

## Acceptance criteria
- [ ] Domain contract reviewed and versioned.
- [ ] Analytical/simple benchmark cases independently checked.
- [ ] Normal, boundary, invalid and stress inputs covered.
- [ ] All four implementations conform, and the named oracle passes.
- [ ] Numerical diagnostics and failure modes are explicit.
- [ ] Deterministic fixtures and provenance are recorded.
- [ ] Performance baseline exists where relevant.
- [ ] User and developer documentation includes examples and limitations.
