# Pricing and valuation

Stage B specs: `pricing-framework.md`, `use-cases.md`. Instruments beyond these are specified before their stages.

## Purpose
Define the scope and shared contract for the pricing and valuation domain.

## Capabilities
- Instrument definitions, cashflows, schedules and payoff interfaces
- Equity cash, futures, forwards and vanilla options
- FX spot, forwards, swaps, NDFs and vanilla options
- Rates futures, FRAs, OIS, swaps, caps/floors and swaptions
- Bonds, repo, CDS and selected credit derivatives
- PV, accrued interest, conventions, model metadata and valuation explain

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
- Equity forward carry and dividend valuation
- FX forward and NDF settlement examples
- Fixed/floating swap cashflow valuation
- Bond clean/dirty price and accrued interest
- Independent price benchmark reconciliation

## Acceptance criteria
- [ ] Domain contract reviewed and versioned.
- [ ] Analytical/simple benchmark cases independently checked.
- [ ] Normal, boundary, invalid and stress inputs covered.
- [ ] All four implementations conform, and the named oracle passes.
- [ ] Numerical diagnostics and failure modes are explicit.
- [ ] Deterministic fixtures and provenance are recorded.
- [ ] Performance baseline exists where relevant.
- [ ] User and developer documentation includes examples and limitations.
