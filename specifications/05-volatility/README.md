# Volatility and quantitative models

## Purpose
Define the scope and shared contract for the volatility and quantitative models domain.

## Capabilities
- Black-Scholes and Black-76 pricing and implied-volatility inversion
- ATM, delta smile, risk reversal, butterfly and smile conventions
- Volatility surfaces across expiry and strike/delta
- SABR and Heston model implementation and calibration
- Local volatility and Dupire framework
- Realised volatility, EWMA/GARCH, Greeks and arbitrage diagnostics

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
- Implied volatility inversion with price bounds
- Construct a smile from delta quotes
- Surface interpolation and extrapolation
- SABR calibration with diagnostics
- Calendar and butterfly arbitrage checks

## Acceptance criteria
- [ ] Domain contract reviewed and versioned.
- [ ] Analytical/simple benchmark cases independently checked.
- [ ] Normal, boundary, invalid and stress inputs covered.
- [ ] Python reference and applicable production implementations conform.
- [ ] Numerical diagnostics and failure modes are explicit.
- [ ] Deterministic fixtures and provenance are recorded.
- [ ] Performance baseline exists where relevant.
- [ ] User and developer documentation includes examples and limitations.
