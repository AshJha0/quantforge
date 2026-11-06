# Financial mathematics and shared foundations

## Stage A specifications

Read `../cli-contract.md` first, then `rulings.md` and `limits.md`, which apply to every spec below. Golden cases are in `datasets/golden/core/`.

| Spec | Golden suite | Clean-room status |
|---|---|---|
| `daycount.md` | `daycount` | Ready |
| `calendars.md` | `calendar` | Ready |
| `compounding.md` | `compounding` | Ready |
| `snapshot-hash.md` | `snapshot` | Ready |
| `rng.md` | `rng` | Ready |
| `sobol.md` | `sobol` | Ready |
| `root-finders.md`, `test-functions.md` | `root` | Ready |
| `integration.md` | `integrate` | Ready |
| `interpolation.md` | `interp` | Ready. Tension and monotone-convex have one source each |
| `differentiation-and-linalg.md` | `diff_linalg` | Ready |
| `statistics-and-time-series.md` | `stats` | Ready |
| `pde.md` | `pde` | Ready |
| `monte-carlo.md` | `monte_carlo` | Ready |
| `cos.md` | `cos` | Ready |
| `data-checks.md` | `data_checks` | Ready |
| `timezone-and-cutoff.md` | `time` | Ready |
| `rulings.md` | `rulings`, `store_rulings` | Ready |
| `limits.md` | `limits` | Ready |
| `asof-store.md` | `store` | Ready. Hashes have one source |

Not yet specified from this domain's list: typed units and money, and the convention registry.

## Purpose
Define the scope and shared contract for the financial mathematics and shared foundations domain.

## Capabilities
- Date/time, calendars, business-day adjustment and settlement conventions
- Day counts: ACT/360, ACT/365F, 30/360 variants; compounding and accrual
- Strongly typed money, currency, rates, basis points, prices and quantities
- Numerical root finding, interpolation, integration, differentiation and linear algebra
- Statistics, covariance, correlation, time series and deterministic random generation
- Market-data schemas, validation, quality flags and immutable snapshots

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
- Calendar holiday boundaries and leap years
- Day-count convention reference cases
- Compounding and discount-factor identities
- Root-finder convergence and failure modes
- Unit conversion and invalid currency/rate handling

## Acceptance criteria
- [ ] Domain contract reviewed and versioned.
- [ ] Analytical/simple benchmark cases independently checked.
- [ ] Normal, boundary, invalid and stress inputs covered.
- [ ] All four implementations conform, and the named oracle passes.
- [ ] Numerical diagnostics and failure modes are explicit.
- [ ] Deterministic fixtures and provenance are recorded.
- [ ] Performance baseline exists where relevant.
- [ ] User and developer documentation includes examples and limitations.
