# Timezones and cut-off

Spec version 1.0.0. Status: Specified.

All stored instants are UTC. A market's date comes from its local clock and its cut-off: a London close at
16:00 belongs to one business date, a quote one second later to the next.

## Zones

To keep behaviour identical without relying on a language's timezone database, the rules are written here.
The valid range is instants in years 2007 to 2037 (UTC) and local times in the same years. Outside: `E_DATE_RANGE`.
Unknown zone: `E_SCHEMA`.

| Zone | Standard offset | Summer time |
|---|---|---|
| `UTC` | 0 | None |
| `Europe/London` | 0 | +1 h from last Sunday of March 01:00 UTC to last Sunday of October 01:00 UTC |
| `Europe/Berlin` | +1 h | +1 h more, same instants as London |
| `America/New_York` | -5 h | +1 h from second Sunday of March 02:00 local to first Sunday of November 02:00 local (07:00 UTC and 06:00 UTC) |
| `Asia/Tokyo` | +9 h | None |

Summer time starts at the given instant, inclusive, and ends at the given instant, exclusive.

## Operations

`core.time.utc_offset`. Inputs: `zone`, `instant`. Output: `offset_seconds`.

`core.time.to_local`. Inputs: `zone`, `instant`. Output: `local` (local-time string).

`core.time.to_instant`. Inputs: `zone`, `local`, optional `overlap` (`EARLIER` or `LATER`). Output: `instant`, in `Z` form.
- A local time in a spring gap: `E_NONEXISTENT_LOCAL_TIME`.
- A local time in an autumn overlap, with no `overlap`: `E_AMBIGUOUS_LOCAL_TIME`. `EARLIER` picks the first
  occurrence (summer offset), `LATER` the second.
- `overlap` given on an ordinary time: ignored.

`core.time.business_date`. Inputs: `instant`, `zone`, `cutoff` (`HH:MM`, local), `calendar`. Output: `date`.

Take the local date. If the local time of day is at or after `cutoff`, add one calendar day. Then apply `FOLLOWING`
on `calendar`. So a cut-off of 16:00 puts 15:59:59 on today and 16:00:00 on the next business day, and a Saturday
quote lands on Monday. A malformed `cutoff` is `E_SCHEMA`.

## Acceptance

Class `date_and_convention`, exact. Oracle: Python `zoneinfo` with `tzdata` pinned in `oracle/python/uv.lock`, checked
against these rules at every transition from 2007 to 2037, with hand cases one second each side of a change.

## Limits

Governments change these rules. A change needs a spec version and fresh golden files. Earlier history
is out of scope; a calculation on dates before 2007 needs dates, not instants.

## Sources

Added in R1 (v0.4.1) to meet plan 11.2.4 and 11.5. These are references only: they do not change any rule above. "(not opened)" means the reference was checked from memory for this backfill, not re-read; section numbers are given only where known.

- [S1] IANA Time Zone Database (tzdb), zones `Europe/London`, `America/New_York`, `Europe/Berlin` and their summer-time rules (not opened)
- [S2] ISO 8601, date and time representation (instants with offset) (not opened)
