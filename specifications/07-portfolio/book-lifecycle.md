# Book: trade and position lifecycle, end-of-day marks

Spec version 1.0.0. Status: Specified (stage F, slice F5). Ruling: `stage-f-rulings.md` F-34. Suite `stage_f/book_f`, written by `oracle/python/gen_stage_f_w3.py`.

**Plain idea.** Before any risk number means anything, the book has to be right: which positions are held, at what cost, and what has already been made or lost. Trades come in; options expire; a bond issuer defaults; a futures position is rolled to the next contract; index fixings are recorded for later coupons. At the end of the day every position needs a price, from the preferred source if it has one, from a backup or a recent price if not, and an independent price check flags marks that look wrong. This page fixes those rules so four languages keep the same book.

## `book.lifecycle.apply`

### Inputs

- `positions`: the opening book, `[{instrument, quantity, average_cost}]` (quantity signed: negative is short). An instrument twice is `E_INPUT`; a zero quantity is ignored (ruling F-39).
- `events`: in non-decreasing `date` order, else `E_INPUT`. Each has `date` and `type`; another type is `E_SCHEMA`:

| `type` | Keys | Effect |
|---|---|---|
| `TRADE` | `instrument`, `quantity` (signed, not 0, else `E_DOMAIN`), `price` | as the cost rule below |
| `FIXING` | `index`, `value` | recorded; the same `index` and `date` twice is `E_INPUT` |
| `EXPIRY` | `instrument`, `settlement_price` | a trade of minus the position at the settlement price; the instrument is closed |
| `DEFAULT` | `instrument`, `recovery_price` | the same, at the recovery price |
| `ROLL` | `from`, `to`, `from_price`, `to_price` | close `from` at `from_price`, then trade the same signed quantity of `to` at `to_price`; `from` is closed |

`EXPIRY`, `DEFAULT` and `ROLL` on an instrument not held, or a `TRADE` or `ROLL` into a closed instrument, are `E_INPUT`.

### Cost rule (ruling F-34): weighted average cost

For a position `q` at average cost `a` and a trade `dq` at price `p`:

- **Same direction or flat** (`q = 0` or `q` and `dq` of the same sign): `q' = q + dq`, `a' = (q a + dq p) / q'`.
- **Reducing:** the closed quantity is `c = min(|dq|, |q|)`; realised P&L grows by `sign(q) c (p - a)`. If the position reaches 0 it is removed. If it keeps its sign, `a` is unchanged. If it crosses zero, the remainder `q + dq` opens at `a' = p`.

Average cost, not first-in-first-out, is the rule: it needs no lot history and is what most position-keeping systems report as "average cost" [S1]. An instrument appears in `realized_pnl` once any reducing trade has touched it, even when the amount is 0.

### Outputs

- `positions`: open positions in instrument order (`quantity`, `average_cost`).
- `realized_pnl`: `[{instrument, pnl}]` in instrument order; `total_realized`.
- `fixings`: `[{index, date, value}]` sorted by index, then date.

Goldens replay in exact rational arithmetic; class `simple_analytic` (`fixings` exact).

## `book.marks.resolve`

### Inputs

- `as_of`, `instruments`, `sources` (in priority order, names unique, else `E_INPUT`; each `{name, quotes: [{instrument, date, price}]}`), `max_age_days` (`>= 0`, else `E_DOMAIN`).
- `ipv` (optional, `[{instrument, price}]`, independent prices, each `> 0`, else `E_DOMAIN`) and `ipv_threshold` (relative). A quote dated after `as_of` is never a mark (ruling F-39).

### Rule (data fallback)

For each instrument, in order:

1. The first source, in priority order, with a quote dated `as_of`: status `PRIMARY` if it is the first source, else `FALLBACK`; `age_days` 0.
2. Otherwise the most recent quote dated within `max_age_days` calendar days before `as_of`, from any source (the earlier source wins a tie on date): status `STALE`, `age_days` the gap.
3. Otherwise `MISSING`: `price`, `source` and `age_days` are `null`.

Price verification: when the instrument has an `ipv` price and a mark, `ipv_diff = (mark - ipv) / ipv` and `ipv_breach = |ipv_diff| > ipv_threshold`; otherwise `ipv_diff` is `null` and `ipv_breach` is `false`.

### Outputs

`marks`: one row per instrument in input order, `{instrument, price, source, status, age_days, ipv_diff, ipv_breach}`. Class `simple_analytic`.

## Convergence and limit cases

No numerical method: exact rules. Limit cases (goldens): a position closed exactly to 0 is removed; a reversal through 0 opens the remainder at the trade price; a widened stale limit turns `MISSING` into `STALE`.

## Acceptance

- Every case of `book_f` passes in all four languages.
- No outside oracle exists for these rules (they are this platform's own conventions); the suite does not count toward the 60% floor.
- Deferred: corporate actions, settlement-date accounting and multi-currency cash.

## Sources

- [S1] CFA Institute, *CFA Program Curriculum*, Level I, "Inventories" (weighted average cost against FIFO), 2024 edition (not opened)
