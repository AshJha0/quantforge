# As-of store and replay

Spec version 1.0.0. Status: Specified. Depends on `snapshot-hash.md`.

The idea: never overwrite a number. A correction is a new record. Then "what did we know at 16:00 on Tuesday?" has one
answer, and an old valuation can be reproduced. This is the minimal store for stage A. The full bitemporal store is
stage K.

The operations are pure functions of a log passed in the case, so all four languages can be compared. How a build
keeps a log on disk is its own affair, and is not part of conformance.

## Record

| Key | Meaning |
|---|---|
| `sequence` | Integer, at least 1. Strictly increasing through the log |
| `series_id` | Non-empty string |
| `event_time` | Instant the value is about |
| `knowledge_time` | Instant the store learned it |
| `value` | Any JSON value. `null` means known to be missing |
| `deleted` | Optional boolean, default false. True withdraws the value |

The key of a value is `(series_id, event_time)`. Several records may share a key: these are versions.

Instants follow the contract, with any offset accepted and compared as instants. Output instants are written in `Z`
form. Unlike `timezone-and-cutoff.md`, the year limit is only that of `Z` form, years 1 to 9999 (`rulings.md` A5).

## Log checks

In this order, within the contract's order of checks (`rulings.md` A2):
1. A record missing a key, or mistyped, including `sequence < 1` or an empty `series_id`: `E_SCHEMA`.
2. `sequence` not strictly increasing: `E_INPUT`.
3. `knowledge_time` lower than the previous record's: `E_INPUT`. A log is written in the order it was learned, so
   nothing can be learned in the past. Equal times are allowed.

## View at `as_of`

1. Keep records with `knowledge_time <= as_of`. The limit is inclusive.
2. For each key, keep the record with the highest `sequence`.
3. Drop those with `deleted` true.
4. Order by `series_id` (UTF-8 bytes, as in `snapshot-hash.md`), then `event_time`.

A row has keys `series_id`, `event_time`, `knowledge_time`, `sequence`, `value`.

## Operations

All take `records`, an array, which may be empty.

| Operation | Further inputs | Outputs |
|---|---|---|
| `core.store.query_as_of` | `as_of`; optional `series_id`; optional `event_from`, `event_to` (both inclusive) | `rows` |
| `core.store.latest` | `as_of`, `series_id` | `row`: the row with the latest `event_time`, or `null` if none |
| `core.store.snapshot` | `as_of` | `canonical`, `snapshot_id` |
| `core.store.replay` | `checkpoints`: array of instants, ascending, not necessarily distinct | `snapshots`: `{as_of, row_count, snapshot_id}` for each; `head` |
| `core.store.chain` | None | `head` and `hashes` |

`event_from` after `event_to`: `E_DATE_ORDER`. `checkpoints` out of order: `E_INPUT`.

**Snapshot.** The document `{"as_of": <instant in Z form>, "rows": [...]}`, hashed as in `snapshot-hash.md`. Instants
inside it are written in `Z` form, so a log's offsets do not change the hash.

**Chain.** Tamper evidence for an append-only log. `h_0` is 64 zeros. For record `i`, from 1,
`h_i` is the hex SHA-256 of the UTF-8 bytes of `h_{i-1}`, then the canonical form of the record as given, with
instants untouched. Every key of the record counts (`rulings.md` A3). `hashes` lists `h_1..h_n`. `head` is `h_n`, or `h_0` for an empty log. The forward log in
`tools/forward-log/` uses the same chain.

**Replay.** Checks that history is stable: it rebuilds each checkpoint from the log. Run twice, or after later records
are appended, the `snapshot_id` at an earlier checkpoint must not change, provided the new knowledge times are after it.
Golden cases test this directly.

## Acceptance

Class `date_and_convention`, exact. Oracle: hand-written expected rows, with hashes from the oracle's canonical form.
It has one source, by nature. Cases cover the inclusive limit, corrections, withdrawals, a value withdrawn and restored,
late data, offsets, and an append that leaves earlier checkpoints unchanged.

## Sources

Added in R1 (v0.4.1) to meet plan 11.2.4 and 11.5. These are references only: they do not change any rule above. "(not opened)" means the reference was checked from memory for this backfill, not re-read; section numbers are given only where known.

- [S1] Snodgrass, R. T., *Developing Time-Oriented Database Applications in SQL*, Morgan Kaufmann, 2000 (valid time and transaction time, the bitemporal model behind `event_time` and `knowledge_time`) (not opened)
- [S2] NIST FIPS PUB 180-4, *Secure Hash Standard (SHS)*, 2015, SHA-256 (not opened)
- [S3] IETF RFC 8259, *The JavaScript Object Notation (JSON) Data Interchange Format*, 2017 (not opened)
