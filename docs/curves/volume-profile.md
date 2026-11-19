# Intraday volume profile (VWAP input)

<p class="note">Stage H, v0.10.0. The operation is built in all four languages (spec version 0.1.0, confirmed 2026-11-18), but this page is still written by hand from the spec's golden cases, not generated from CLI runs. The profiles here are synthetic.</p>

## What it is

The plain idea: trading volume is not spread evenly through the day. A VWAP schedule tries to trade in step with the market, so it needs a curve that says what share of the day's volume to expect in each interval. That curve is the volume profile.

Formally (spec [`10-execution/schedules.md`](../../specifications/10-execution/schedules.md), ruling HR-3): `exec.schedule.vwap` takes `profile`, a list of `N` non-negative weights `w_i`, normalises it internally, and returns slices `X w_i / sum w`. In UNITS mode the slices are whole units by the largest-remainder rule, ties to the earliest bucket, so they sum to `X` exactly. An all-zero profile is `E_DOMAIN`.

The profile is an **input**. QuantForge does not forecast it in wave 1 (spec limitation); a desk would estimate it from past days of the same instrument, and the schedule is only as good as that estimate.

## Schedules from the goldens

| Order `X` | Profile | Mode | Slices | Case |
|---|---|---|---|---|
| 1,000 | `[1, 2, 3, 4]` | CONTINUOUS | `[100, 200, 300, 400]` | `sched_h-0003` |
| 10 | `[1, 1, 1]` | UNITS | `[4, 3, 3]` | `sched_h-0004` |
| any | `[0, 0]` | any | `E_DOMAIN` | `sched_h-0008` |

A flat profile reduces VWAP to TWAP (`exec.schedule.twap`). Evidence: hand calculation, then a blind re-derivation from the inputs only (DR-H2, 2026-11-15), all match. The textbook source ([Kis13]) was not read.

## What it does not show

No real intraday profile is published here. The recorded crypto feed ([recorded feeds](../data/recorded-feeds.md)) holds trades from which a profile for one crypto venue could be built; any such profile would be labelled "crypto venue; not equities or rates", and a crypto market trades around the clock, so its shape is not an equity day's.

## Related

[Tutorial 36](../getting-started/tutorial-36-slice-an-order.md) works these cases by hand.
