# Spec questions from the C++ implementation

Written from the specs alone. Nothing here was changed to fit a golden file.

## Settled by the stage-a corrections

- `add_tenor` end of month: `calendars.md` now states QuantLib's rule, and this build follows it.
- `diff_linalg-0006`: the limit now follows the formula in the spec.
- Runner command on Windows: `runner.py` now resolves the path.
- `start == end` is tested first in `daycount.md`, which also settles `BUS_252` outside the calendar range: 0.

## Closed by rulings and limits

- Log checks against `E_SCHEMA`: ruling A2, the contract's order holds.
- `sequence < 1` and empty `series_id`: ruling A1, `E_SCHEMA`.
- `skip` with no upper limit: `limits.md`.
- `implementations.yaml` in the contract: corrected.
- Every other gap this file listed: settled by `specifications/01-core/rulings.md`.
- `document_text` breaking a limit and a parse rule together: rulings B1 and B2.

## Open

The general array limit needs each operation's `E_SCHEMA` checks to run first. Here the handler runs once and its
result is dropped. `limits.md` now allows one linear pass and no work that grows with the limit, and this goes
further than that on an oversized array: a sort in `quantile`, or `n` x `window` in `rolling`. The cost is bounded by the
input already read. Other limits stop before any work. A schema-only pass per operation would close the gap.

## Stage B gaps, and the reading used

No golden case covers these. Nothing conflicts with a golden case.

| Where | Gap | Reading used |
|---|---|---|
| `projection-and-fra.md` | `end_of_month` for the swap schedules is not stated | False |
| `projection-and-fra.md` | "`spot` is `as_of` plus 2 `USGS` business days" when `as_of` is not a business day | `as_of` adjusted `FOLLOWING` first, as in `ois-curves.md` |
| `projection-and-fra.md` | No quotes; zero or very large `months`, `tenor_months` | `E_INPUT`; the range allowed is 1 to 1200 |
| `projection-and-fra.md` | `FRA` end: from the adjusted or unadjusted start | The adjusted start |
| `curve-framework.md` | Empty `pillars`: the schema has `minItems` 1, the spec is silent | `E_SCHEMA` |
| `curve-framework.md` | `forward` with a `day_count` that needs conditional inputs | `E_SCHEMA`: those are not offered here |
| `curve-framework.md`, `limits.md` | Extrapolation with one pillar has no previous pillar | The implied node at `as_of` is the previous one |
| `schedules.md` | `payment_lag < 0` | `E_INPUT` |
| `schedules.md` | Every date dropped by rule 4 | An empty `periods`, not an error |
| `ois-curves.md` | Order of "no quotes", "pillars" and `bid > ask`, and `bid > ask` against a pillar error | `bid > ask` first, as it needs no dates; the spec lists it last |
| `ois-curves.md` | `compound` with empty arrays | `E_INPUT` |
| `fx.md` | `fx.curve.implied` tenors in `D` or `W` | `E_SCHEMA`: the rule is in months |
| `fx.md` | `as_of` differing from a curve's `as_of` | Not checked |
| `fx.md` | `fx.swap.pv` with `near_date` after `far_date` | Not checked; each leg checks against spot only |
| `least-squares.md` | `max_iter < 1`; `lower` above `upper`; wrong length of `prior`, `weights`, bounds | `E_INPUT` |
| `least-squares.md` | `start` outside the bounds | Projected on the box |
| `least-squares.md` | Order of `E_INPUT` on bounds against `E_DOMAIN` on `weights` | The table's row order |
| `least-squares.md` | `curve_report` tolerance breach format | An array `tolerance_breaches`, empty, as a solve that misses 1e-13 is `E_NO_CONVERGENCE` |
| `stage-b-hedges.md` | Ragged or empty `a` | `E_INPUT` |
| `stage-b-hedges.md` | The rank test's method | LU with partial pivoting on `A^T W A` |
| `use-cases.md` | Hedge tenors whose key-rate columns are dependent | `E_SINGULAR`, from `hedge.solve` |
| `use-cases.md`, `limits.md` | Number of `hedge_tenors` | Limit 20, from `hedge.solve` |
| `rates-sensitivities.md`, `use-cases.md` | Which solve method: no `method` input | `SEQUENTIAL` |
| `units-and-money.md` | `add_money` with a sum of 19 whole digits | Written in full |
| `limits.md` | "Curve solves are `2 n + 2` per trade" in `usecase.rates_hedge` | The bumped curves are built once and shared by all its trades, as they are the same curves |

`hedge.solve` uses coordinate descent to find the support, then an exact linear solve on it, accepted only when all
first-order conditions hold. If that never happens within 200,000 sweeps the result is `E_NO_CONVERGENCE`, a code the
spec does not list here.
