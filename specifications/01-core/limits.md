# Input limits

Spec version 1.0.0. Normative: this page is part of every stage A spec.

The contract treats no result as a crash, so an input must never be able to ask for more work than a case can finish.
Each limit below keeps a single case to about 10^8 simple operations or less, and so to seconds in the slowest build. They are far above what any calculation here needs. Above a limit the result is `E_LIMIT`, and no work is started.

Order of checks: `E_PARSE`, `E_SCHEMA`, `E_LIMIT`, then the operation's rule checks. So `simpson` with an odd `n` above the limit is `E_LIMIT`. An integer above 2^53 is already `E_SCHEMA` under the contract. Values below a minimum keep the code their spec gives.

Bounds that come from a table or a definition, not from work, keep their own code: Gauss-Legendre `n` up to 64, Sobol `dimensions` up to 64, `stream` up to 1023, `SOBOL` steps up to 64.

## General

| Input | Maximum | Why |
|---|---|---|
| Any array, at any depth, in `inputs` | 100,000 elements | Bounds memory and sorting. Longer series are a job for a library call, not a case |
| Matrix for `core.linalg.*` | 200 rows | Cubic cost: 8 x 10^6 operations |
| Nesting depth of a JSON value in `document_text` or a record's `value` | 64 | Keeps recursive parsers off the stack limit. An object or array is one level; scalars add none |
| `document_text` | 1,048,576 UTF-8 bytes | Keeps canonical output a sensible size |

## By operation

| Operation | Input | Maximum | Why |
|---|---|---|---|
| `core.integrate.trapezoid`, `simpson` | `n` | 10,000,000 | Function calls. Rounding also grows beyond this, so more points buy nothing |
| `core.integrate.adaptive_simpson` | `max_depth` | 60 | Interval width nears `eps` |
| `core.integrate.adaptive_simpson`, `gauss_kronrod` | Function calls in one run | 10,000,000, fixed. Reaching it is `E_NO_CONVERGENCE`, as the input was legal | A tiny `tol` otherwise needs exponential work |
| `core.integrate.gauss_kronrod` | `max_intervals` | 10,000 | The search for the largest error |
| `core.root.*` | `max_iter` | 100,000 | Far above any convergent run |
| `core.rng.*` | `count` | 100,000 | Output size |
| `core.rng.*` | `skip` | 10,000,000 | Each draw is stepped through |
| `core.sobol.points` | `count` x `dimensions` | 100,000 | Output size |
| `core.sobol.points` | `skip` | 10,000,000 | Each point is stepped through. With these limits an index can never reach 2^32 |
| `core.mc.gbm_european` | `paths` x `steps` | 1,000,000 | Normals drawn. At this size `stderr` is already about 0.014 on the spec's example |
| `core.pde.bs_european` | `space_steps` x `time_steps` | 10,000,000 | Grid updates. `J = 2000`, `M = 5000` is far past the accuracy needed |
| `core.cos.european` | `terms` | 100,000 | Complex evaluations. The series converges far sooner |
| `core.calendar.add_business_days` | `|days|` | 30,000 | More than the business days in 2000 to 2099 |
| `core.ts.rolling` | `window` | 1,000 | Each window is computed afresh |
| `core.ts.autocorrelation`, `ljung_box` | `max_lag` | 1,000 | Cost is `n` x `max_lag` |
| `core.store.replay` | `checkpoints` | 1,000, and `records` x `checkpoints` at most 10,000,000 | Each checkpoint rebuilds a view |

A result date beyond a calendar's years, from `add_tenor` or `add_business_days`, is `E_DATE_RANGE`. Stop as soon as the walk leaves the range.

## Acceptance

Suite `limits`: at the limit and one above, for each row except the `records` x `checkpoints` product, which needs a very large case. The internal call limit is met through a legal `tol`.
