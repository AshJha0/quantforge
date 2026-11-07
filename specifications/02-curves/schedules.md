# Schedules

Spec version 1.0.0. Status: Implemented, not Validated. Stage B covers regular schedules with one short first stub. Long stubs and ex-dividend periods are stage D.

## `rates.schedule.generate`

Inputs: `start`, `end` (dates), `frequency_months` (1, 2, 3, 4, 6 or 12; else `E_SCHEMA`), `calendar`, `end_of_month` (boolean), `payment_lag` (business days, at least 0). Output: `periods`, an array of `{start, end, payment}`. `end <= start`: `E_DATE_ORDER`.

Rules, all with `MODIFIED_FOLLOWING`:
1. Unadjusted dates step back from `end` by `k * frequency_months`, from the original `end` each time, with the day clipped to the month, while the date stays after `start`.
2. Any short stub is therefore first. `start` is kept as given.
3. Each date except `start` is adjusted. If `end_of_month`, it is instead the last business day of its month.
4. A date equal to or before `start` after adjustment is dropped. For example `start` 2027-02-26 with 2027-02-28 adjusting back onto it.
5. `payment` is `end` plus `payment_lag` business days.

## Acceptance

Exact, against QuantLib `Schedule` with `Backward` generation.

## Sources

Added in R1 (v0.4.1) to meet plan 11.2.4 and 11.5. These are references only: they do not change any rule above. "(not opened)" means the reference was checked from memory for this backfill, not re-read; section numbers are given only where known.

- [S1] ISDA, *2006 ISDA Definitions*, Section 4.12 (business day conventions) and the Period End Date / roll provisions (not opened)
