# Systematic research and backtesting

## Purpose
Define the scope and shared contract for the systematic research and backtesting domain.

## Capabilities
- Historical market replay and event-driven simulation
- Signal generation, feature engineering and portfolio construction
- Vectorised and event-driven backtesting
- Transaction-cost and market-impact integration
- Walk-forward, out-of-sample and robustness validation
- Look-ahead, survivorship, selection and leakage controls

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
- Build a deterministic event replay
- Implement a signal with explicit timestamp rules
- Add realistic transaction costs
- Walk-forward split and out-of-sample report
- Detect look-ahead bias in a deliberately flawed strategy

## Acceptance criteria
- [ ] Domain contract reviewed and versioned.
- [ ] Analytical/simple benchmark cases independently checked.
- [ ] Normal, boundary, invalid and stress inputs covered.
- [ ] Python reference and applicable production implementations conform.
- [ ] Numerical diagnostics and failure modes are explicit.
- [ ] Deterministic fixtures and provenance are recorded.
- [ ] Performance baseline exists where relevant.
- [ ] User and developer documentation includes examples and limitations.
