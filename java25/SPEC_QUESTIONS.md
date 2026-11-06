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

## Golden case that depends on rounding (1 failing case)

### 13. limits-0011: `adaptive_simpson`, `oscillatory` on `[0, 2]`, `tol = 1e-300`, `max_depth = 60`

Expected `E_NO_CONVERGENCE`. This build returns `ok`, value -0.0010168568739964898. The recipe in `integration.md` is
followed: `|S1 + S2 - S| <= 15 tol_here` accepts an interval when the difference rounds to exactly 0.

Measured with the same recipe in a throwaway trace, changing only the maths library:

| Library | Result | Calls | Accepted with difference exactly 0 |
|---|---|---|---|
| Java `Math` (this build) | Converges, greatest depth 60 | 5,242,365 | 1,310,591 |
| Java `StrictMath` | Depth exceeded near `x = 0.0041854742709` | 10,273 | 2,548 |
| Python `math` | Depth exceeded | 10,373 | 2,573 |

So the outcome turns on the last bits of `exp` and `cos`, which the contract says may differ. None of the three reaches
the 10,000,000 call limit, so this case does not test what `limits.md` says it does. Moving to `StrictMath` would make
it pass, and was not done, as that fits a golden case without any spec reason.

Question: can a case be chosen that reaches the limit whatever the rounding? One option is an accept test that does
not pass on an exact 0 at a tiny `tol`, but that changes the recipe.

## Open points

| # | Place | Choice |
|---|---|---|
| 10 | `limits.md`, nesting beyond about 2000 levels | The parser stops there with `E_LIMIT` to protect its stack, so a syntax error later in such text is not seen. Below that, `E_PARSE` wins over `E_LIMIT` as the contract orders. The same applies to the case document itself |
| 11 | `limits.md`, "no work is started", general array limit | Operations with a limit on work stop before starting. Others, such as `quantile`, may make one pass over an oversized array before `E_LIMIT` is returned. The result is the same, and the cost is bounded by the input read |
| 12 | `document_text` over 1,048,576 bytes | Parsed first, so that `E_PARSE` and `E_SCHEMA` keep their rank. "No work is started" is read as applying after those checks |

## Small document points

- `Normal.java` does not use `erfc` (ruling S5 allows this). It works directly in `x`, because
  `x/sqrt(2)` and a rounded `x^2` alone cost about 1e-13 relative at `x = -37`, over the 1e-14 target.
