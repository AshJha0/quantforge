# Spec questions from the Java stage A build

Written from the specs alone. Where a spec and a golden case disagree, this build follows the spec text.

## Resolved by the spec corrections on `stage-a` (363e5a8)

1. `add_tenor` end-of-month on a non-business date: `calendars.md` now gives the rule, and the code follows it.
2. `THIRTY_E_360_ISDA` with `start == end`: `daycount.md` confirms 0. The build already returned 0.
3. diff_linalg-0006 limit at the rounding noise: `differentiation-and-linalg.md` now sets limits that accept any
   correct form of `f`. `poly5` stays as `Math.pow`, which was changed after seeing the old failure.

The choices once listed here for silent points are now settled by `specifications/01-core/rulings.md`, and the
code follows those rulings.

## Closed by rulings A1 to A6 and `limits.md` (3737bb5)

| # | Point | Outcome |
|---|---|---|
| 4 | `sequence < 1` or empty `series_id` | Closed: `E_SCHEMA` (A1) |
| 5 | "Before anything else" in the store's log checks | Closed: the contract's order holds (A2), and the code changed |
| 6 | Chain keeps every record key | Closed: confirmed (A3) |
| 7 | Lone surrogate in a record | Closed: `E_SCHEMA` (A4), and the code changed. No golden case yet, so this is untested by the runner |
| 8 | `replay` `head` | Closed: confirmed (A6) |
| 9 | `skip` near 2^53 | Closed: `E_LIMIT` above 10,000,000 in `rng` and `sobol` |

## Closed by rulings B1 to B5 (bb663d6)

| # | Point | Outcome |
|---|---|---|
| 10 | Nesting beyond the parser's threshold | Closed: a lexical scan runs before parsing (B2), and the parser's own limit is gone |
| 11 | "No work is started" and the array limit | Closed: `limits.md` now allows one linear pass over input already read |
| 12 | `document_text` over the byte limit | Closed: tested first, without parsing (B1), and the code changed |
| 13 | limits-0011 depended on rounding | Closed: the case was replaced. The 10,000,000-call limit stays in the code as a backstop with no golden case |

## Open points

None.

## Small document points

- `Normal.java` does not use `erfc` (ruling S5 allows this). It works directly in `x`, because
  `x/sqrt(2)` and a rounded `x^2` alone cost about 1e-13 relative at `x = -37`, over the 1e-14 target.
