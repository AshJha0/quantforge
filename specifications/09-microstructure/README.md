# Market microstructure and liquidity

## Purpose
Define the scope and shared contract for the market microstructure and liquidity domain.

## Capabilities
- Market-by-price and market-by-order book reconstruction
- Spread, depth, imbalance, order flow and trade intensity
- Queue position, cancellations and queue dynamics
- Fill probability, adverse selection and market resilience
- Venue liquidity comparison and market-data replay
- Timestamp ordering, sequence gaps and book recovery

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
- Rebuild a book from incremental updates
- Handle sequence gap and snapshot recovery
- Calculate depth and order-book imbalance
- Estimate simple fill probability
- Measure adverse selection after fills

## Acceptance criteria
- [ ] Domain contract reviewed and versioned.
- [ ] Analytical/simple benchmark cases independently checked.
- [ ] Normal, boundary, invalid and stress inputs covered.
- [ ] All four implementations conform, and the named oracle passes.
- [ ] Numerical diagnostics and failure modes are explicit.
- [ ] Deterministic fixtures and provenance are recorded.
- [ ] Performance baseline exists where relevant.
- [ ] User and developer documentation includes examples and limitations.
