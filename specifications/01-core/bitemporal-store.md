# Bitemporal store (stage K)

Spec version 0.1.0. Status: **PROPOSED** (stage K wave 1, plan 14.8 K-4). Rulings: `stage-k-rulings-w1.md` KR-2, KR-3, KR-4. Depends on `asof-store.md` (unchanged) and `snapshot-hash.md`.

**Plain idea.** The stage A store answers "what did we know at 16:00 on Tuesday?". A bitemporal store also answers "for which period was that value meant to hold?". A rate fixed for February, corrected in April, must still read as the old value to anyone asking "as known in March", and as the corrected one to anyone asking "as known in April". Nothing is ever overwritten.

**Formal statement.** A record carries a valid-time interval `[valid_from, valid_to)` and a knowledge instant `knowledge_time`. For a query `(K, V)`, let `C = { r : knowledge_time(r) <= K and valid_from(r) <= V < valid_to(r) }` (with `valid_to` null read as +infinity). If `C` is empty the answer is `null`. Otherwise take `w = argmax_{r in C} sequence(r)`. If `w.deleted`, the answer is withdrawn; otherwise it is `w.value` [Snodgrass, *Developing Time-Oriented Database Applications in SQL*, Morgan Kaufmann 2000, chapters 2 and 10, free PDF from the author's site (UNVERIFIED page numbers); SQL:2011 system-versioned and application-time period tables, Kulkarni and Michels, "Temporal features in SQL:2011", *SIGMOD Record* 41(3) 2012 (free, UNVERIFIED)].

## Record

| Key | Meaning |
|---|---|
| `sequence` | Integer >= 1, strictly increasing through the log |
| `series_id` | Non-empty string |
| `valid_from` | Instant, inclusive |
| `valid_to` | Instant, exclusive, or `null` (open) |
| `knowledge_time` | Instant the store learned the record |
| `value` | Any JSON value; `null` means known to be missing |
| `deleted` | Optional boolean, default false |

## Log checks (order as `rulings.md` A2)

1. Missing or mistyped key, `sequence < 1`, empty `series_id`: `E_SCHEMA`.
2. `sequence` not strictly increasing: `E_INPUT`.
3. `knowledge_time` lower than the previous record's: `E_INPUT` (as stage A).
4. `valid_to` not null and `valid_to <= valid_from`: `E_INPUT`.
5. More than 1,000,000 records: `E_LIMIT`.

## `core.store.bitemporal_query`

Inputs: `records`, `series_id`, `knowledge_as_of` (K), `valid_at` (V).
Outputs: `status` (`FOUND`, `WITHDRAWN`, `NONE`), `row` (`sequence`, `valid_from`, `valid_to`, `knowledge_time`, `value`) or `null`. Instants written in `Z` form.

## Golden value cases (hand-derived; blind-lane candidates)

Shared log, series `A`, all times `T00:00:00Z` unless shown:

| seq | valid_from | valid_to | knowledge_time | value | deleted |
|---|---|---|---|---|---|
| 1 | 2026-01-01 | null | 2026-01-02 | 100 | |
| 2 | 2026-03-01 | null | 2026-03-02 | 110 | |
| 3 | 2026-02-01 | 2026-03-01 | 2026-04-01 | 105 | |
| 4 | 2026-03-01 | null | 2026-04-02 | | true |

| Case | K | V | Expected | Why |
|---|---|---|---|---|
| bt_k-0001 | 2026-03-15 | 2026-02-15 | FOUND, seq 1, 100 | seq 3 not yet known |
| bt_k-0002 | 2026-04-01 | 2026-02-15 | FOUND, seq 3, 105 | K inclusive; correction known |
| bt_k-0003 | 2026-03-15 | 2026-03-10 | FOUND, seq 2, 110 | |
| bt_k-0004 | 2026-04-05 | 2026-03-10 | WITHDRAWN, row null | seq 4 wins and masks seq 2 and seq 1 (KR-2) |
| bt_k-0005 | 2026-04-05 | 2026-01-15 | FOUND, seq 1, 100 | only seq 1 covers January |
| bt_k-0006 | 2026-01-01T12:00:00Z | 2026-01-15 | NONE, row null | nothing known yet |
| bt_k-0007 | 2026-04-01 | 2026-03-01 | FOUND, seq 2, 110 | seq 3 ends at 03-01 exclusive; seq 4 not yet known |
| bt_k-0008 | 2026-04-01 | 2026-02-28T23:59:59Z | FOUND, seq 3, 105 | last second inside seq 3 |

Error cases: bt_k-0009 a record with `valid_to = valid_from` → `E_INPUT`; bt_k-0010 seq 3 with `knowledge_time` 2026-03-01 (earlier than seq 2's) → `E_INPUT`.

Property (KR-4, the K-4 acceptance test): appending any record with `knowledge_time > K` leaves every `(K, V)` answer unchanged byte for byte. Example: bt_k-0001 is unchanged after appending seq 3 and seq 4, because both have `knowledge_time > 2026-03-15`.

## Acceptance (fixed before any run)

- bt_k-0001..0010 in four languages, exact.
- KR-4 property on at least 10,000 generated logs per language (seeded generator in the oracle), zero failures.
- Stage A goldens unchanged.

## Sources

Snodgrass 2000 and Kulkarni-Michels 2012 for the vocabulary (valid time, transaction time) only; the rule above is our own and is fixed by KR-2. Both UNVERIFIED this session (not opened).
