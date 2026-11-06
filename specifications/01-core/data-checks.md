# Market-data checks

Spec version 1.0.0. Status: Specified.

Checks turn raw quotes into quotes with a status and flags. They never change a price and never drop a
quote. What to do with a bad quote is the caller's decision; fallback rules are a stage F item.

## `quote_status`

One value per quote, in `datasets/schemas/quote.schema.json`. The source sends `FIRM` or `INDICATIVE`.
The check may replace it. Highest first:

| Status | Meaning |
|---|---|
| `MISSING` | `bid` or `ask` is `null` |
| `CROSSED` | `bid > ask` |
| `STALE` | Older than the limit |
| `INDICATIVE` | Source said so |
| `FIRM` | Tradable, as far as is known |

`LOCKED` and outliers are not statuses: a locked or outlying quote may be real, so they are flags.

## `quality_flags`

Several may apply, listed in this order: `MISSING_BID`, `MISSING_ASK`, `CROSSED`, `LOCKED`, `STALE`, `WIDE_SPREAD`,
`NON_POSITIVE`, `OUTLIER`.

## Operation `core.data.check_quotes`

Inputs:

| Key | Meaning |
|---|---|
| `as_of` | Instant of the check |
| `quotes` | Array of `{instrument_id, event_time, bid, ask, quote_status}`, with `bid`, `ask` real or `null` |
| `stale_after_seconds` | Positive integer |
| `max_relative_spread` | Optional, positive |
| `positive_only` | Boolean, default false. Rates may be negative, prices may not |
| `outlier_threshold` | Positive, default 5 |
| `outlier_min_history` | Integer at least 3, default 5 |
| `history` | Optional object from `instrument_id` to an array of past mids, oldest first |

Output: `results`, one per quote in input order: `{instrument_id, quote_status, quality_flags}`.

Rules, with `mid = (bid + ask)/2`:

- `MISSING_BID`, `MISSING_ASK`: the side is `null`. If either applies, only `NON_POSITIVE` on the other side may join them.
- `CROSSED`: `bid > ask`. `LOCKED`: `bid = ask`.
- `STALE`: `as_of - event_time > stale_after_seconds`. Exactly at the limit is not stale. `event_time` after `as_of` is `E_INPUT`, as the check cannot see the future.
- `WIDE_SPREAD`: `max_relative_spread` given, not crossed, `mid != 0`, and `(ask - bid)/|mid| > max_relative_spread`.
- `NON_POSITIVE`: `positive_only`, and a non-null side is `<= 0`.
- `OUTLIER`: history for the instrument has at least `outlier_min_history` values, and `|mid - med| / (1.4826 MAD) > outlier_threshold`, with `med` the median and `MAD` the median of `|h - med|`. Median of an even count is the mean of the two middle values. If `MAD = 0`, the test is skipped, as the score would be meaningless. Not applied to crossed or missing quotes.

An input `quote_status` other than `FIRM` or `INDICATIVE` is `E_SCHEMA`. Non-positive `stale_after_seconds`, `max_relative_spread`, or `outlier_threshold`: `E_INPUT`.

## Acceptance

Class `date_and_convention`, exact. Oracle: hand cases, one per rule and boundary.
