# Spec questions from the Java stage A build

Written from the specs alone. Where a spec and a golden case disagree, this build follows the spec text.

## Resolved by the spec corrections on `stage-a` (363e5a8)

1. `add_tenor` end-of-month on a non-business date: `calendars.md` now gives the rule, and the code follows it.
2. `THIRTY_E_360_ISDA` with `start == end`: `daycount.md` confirms 0. The build already returned 0.
3. diff_linalg-0006 limit at the rounding noise: `differentiation-and-linalg.md` now sets limits that accept any
   correct form of `f`. `poly5` stays as `Math.pow`, which was changed after seeing the old failure.

The choices once listed here for silent points are now settled by `specifications/01-core/rulings.md`, and the
code follows those rulings.

## Open points

| # | Place | Choice |
|---|---|---|
| 4 | `asof-store.md`, `sequence < 1` or empty `series_id` | `E_SCHEMA`, as a mistyped record under log check 1. The spec does not name a code |
| 5 | `asof-store.md`, "before anything else" | Log checks run before all other inputs, so a log `E_INPUT` beats a malformed `as_of`, which differs from the contract's schema-first order |
| 6 | `asof-store.md`, chain | "Canonical form of the record as given" keeps every key, including unknown ones. A top-level `snapshot_id` in a record is kept, as the exclusion belongs to the snapshot hash |
| 7 | `asof-store.md`, lone surrogate inside `value` | Not rejected. `snapshot-hash.md` would make it `E_SCHEMA` on document text, and UTF-8 cannot carry it |
| 8 | `core.store.replay` | `head` is the chain head of the whole log |
| 9 | Ruling N1, `skip` | `rng` steps one draw at a time, so a skip near 2^53 is correct in principle but will not finish. `sobol` keeps its limit of indices below 2^32 |

## Small document points

- `Normal.java` does not use `erfc` (ruling S5 allows this). It works directly in `x`, because
  `x/sqrt(2)` and a rounded `x^2` alone cost about 1e-13 relative at `x = -37`, over the 1e-14 target.
