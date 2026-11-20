# Bitemporal store (stage K)

Spec version 1.1.0 (audit A response, 2026-11-19: the size limit, the order of checks, the series condition, `Z` output and required keys; rulings KR-230, KR-231, KR-235(b); findings KA-A1, KA-A2, KA-A12 of `institutional-quant-engine-plan/STAGE_K_R1_AUDIT_A.md`). Version 1.0.0 status: **CONFIRMED** 2026-11-19, confirmed by the stage K coordinator lane (branch k-w1; was PROPOSED, version 0.1.0, stage K wave 1, plan 14.8 K-4). Rulings: `stage-k-rulings-w1.md` KR-2, KR-3 (as corrected by KR-16: a stage A record is `[event_time, event_time + 1 s)`), KR-4. Depends on `asof-store.md` (unchanged) and `snapshot-hash.md`.

**Plain idea.** The stage A store answers "what did we know at 16:00 on Tuesday?". A bitemporal store also answers "for which period was that value meant to hold?". A rate fixed for February, corrected in April, must still read as the old value to anyone asking "as known in March", and as the corrected one to anyone asking "as known in April". Nothing is ever overwritten.

**Formal statement.** A record carries a valid-time interval `[valid_from, valid_to)` and a knowledge instant `knowledge_time`. For a query `(K, V)`, let `C = { r : series_id(r) = S and knowledge_time(r) <= K and valid_from(r) <= V < valid_to(r) }` for the queried series `S` (1.1.0, KR-235(b): the series condition was missing from the 1.0.0 formula, though every build applied it) (with `valid_to` null read as +infinity). If `C` is empty the answer is `null`. Otherwise take `w = argmax_{r in C} sequence(r)`. If `w.deleted`, the answer is withdrawn; otherwise it is `w.value` [Snodgrass, *Developing Time-Oriented Database Applications in SQL*, Morgan Kaufmann 2000, chapters 2 and 10, free PDF from the author's site (UNVERIFIED page numbers); SQL:2011 system-versioned and application-time period tables, Kulkarni and Michels, "Temporal features in SQL:2011", *SIGMOD Record* 41(3) 2012 (free, UNVERIFIED)].

## Record

| Key | Meaning |
|---|---|
| `sequence` | Integer >= 1, strictly increasing through the log |
| `series_id` | Non-empty string |
| `valid_from` | Instant, inclusive |
| `valid_to` | Instant, exclusive, or `null` (open). The key is required (1.1.0, KR-235(b)): a record without it is `E_SCHEMA` |
| `knowledge_time` | Instant the store learned the record |
| `value` | Any JSON value; `null` means known to be missing. The key is required, also on a deleted record (1.1.0, KR-235(b)) |
| `deleted` | Optional boolean, default false |

## Log checks (order as `rulings.md` A2; 1.1.0, KR-230 and KR-231)

1. Missing or mistyped key, `sequence < 1`, empty `series_id`: `E_SCHEMA`.
2. More than 100,000 records: `E_LIMIT`. This is the generic array limit of `01-core/limits.md`; the operation has no limit of its own (KR-231). 1.0.0 listed 1,000,000 here, last; A2 puts the limit straight after `E_SCHEMA`.
3. A non-finite number at the top level of a `value` (ruling F-38): `E_DOMAIN` (the F-2 finite rule).
4. `sequence` not strictly increasing: `E_INPUT`.
5. `knowledge_time` lower than the previous record's: `E_INPUT` (as stage A).
6. `valid_to` not null and `valid_to <= valid_from`: `E_INPUT`.

1.0.0 text, superseded: "1. Missing or mistyped key, `sequence < 1`, empty `series_id`: `E_SCHEMA`. 2. `sequence` not strictly increasing: `E_INPUT`. 3. `knowledge_time` lower than the previous record's: `E_INPUT` (as stage A). 4. `valid_to` not null and `valid_to <= valid_from`: `E_INPUT`. 5. More than 1,000,000 records: `E_LIMIT`."

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

Output fields compared (every case): `status` (string, one of `FOUND`, `WITHDRAWN`, `NONE`); `row` (object with keys `sequence` integer, `valid_from` string, `valid_to` string or null, `knowledge_time` string, `value` JSON value; or `null`). Instants in `Z` form, e.g. `2026-01-01T00:00:00Z`. Error cases compare `error.code` (string) only. Query `series_id` is `A` in every case.

| Case | K | V | Expected status | Expected row.sequence | Expected row.value | Why |
|---|---|---|---|---|---|---|
| bt_k-0001 | 2026-03-15 | 2026-02-15 | FOUND | 1 | 100 | seq 3 not yet known |
| bt_k-0002 | 2026-04-01 | 2026-02-15 | FOUND | 3 | 105 | K inclusive; correction known |
| bt_k-0003 | 2026-03-15 | 2026-03-10 | FOUND | 2 | 110 | |
| bt_k-0004 | 2026-04-05 | 2026-03-10 | WITHDRAWN | row null | row null | seq 4 wins and masks seq 2 and seq 1 (KR-2) |
| bt_k-0005 | 2026-04-05 | 2026-01-15 | FOUND | 1 | 100 | only seq 1 covers January |
| bt_k-0006 | 2026-01-01T12:00:00Z | 2026-01-15 | NONE | row null | row null | nothing known yet |
| bt_k-0007 | 2026-04-01 | 2026-03-01 | FOUND | 2 | 110 | seq 3 ends at 03-01 exclusive; seq 4 not yet known |
| bt_k-0008 | 2026-04-01 | 2026-02-28T23:59:59Z | FOUND | 3 | 105 | last second inside seq 3 |

When `status` is `FOUND`, the other `row` keys (`valid_from`, `valid_to`, `knowledge_time`) are those of the winning record in the shared log, copied as written. (1.1.0, KR-235(b): "copied as written" is withdrawn; the instants of the winning record are written in `Z` form, as the Outputs line above says and every build does. bt_k-0012 has a record written with `+01:00` and `+05:30` offsets.)

| Case | Input | Expected error.code |
|---|---|---|
| bt_k-0009 | shared log with seq 3's `valid_to` set equal to its `valid_from` (2026-02-01); query K 2026-04-01, V 2026-02-15 | E_INPUT |
| bt_k-0010 | shared log with seq 3's `knowledge_time` set to 2026-03-01 (earlier than seq 2's); query K 2026-04-01, V 2026-02-15 | E_INPUT |

<!-- blind:strip -->
Property (KR-4, the K-4 acceptance test): appending any record with `knowledge_time > K` leaves every `(K, V)` answer unchanged byte for byte. Example: bt_k-0001 is unchanged after appending seq 3 and seq 4, because both have `knowledge_time > 2026-03-15`.
<!-- /blind:strip -->

## Acceptance (fixed before any run)

- bt_k-0001..0010 in four languages, exact.
- KR-4 property on at least 10,000 generated logs per language (seeded generator in the oracle), zero failures.
- Stage A goldens unchanged.

## Acceptance evidence (2026-11-19)

- bt_k-0001..0010 and the two-error cases of `e2_k`: pass in Python, Java, C++ and Rust (`conformance/runner/runner.py --impl <lang> --suite 'stage_k/*'`).
- KR-4: 10,000 logs, 500,000 query pairs, zero failures in Python (`program/stage_k_w1/acceptance_python.json`, key `kr4_correction_property`) and Java (`program/stage_k_w1/acceptance_java.jsonl`, same key); also in the C++ and Rust unit tests (`cpp26/tests/test_stage_k.cpp`, `rust/crates/quantforge-core/src/stage_k_tests.rs`).
- Stage A goldens unchanged: the full conformance run passes them in all four builds.

## Sources

Snodgrass 2000 and Kulkarni-Michels 2012 for the vocabulary (valid time, transaction time) only; the rule above is our own and is fixed by KR-2. Both UNVERIFIED this session (not opened).

## Limits and open issues

- **Open audit findings (2026-11-19): KA-A1, KA-A2.** The error order stated for the wave 1 operations (`E_LIMIT` last) contradicts the contract's general rule (`E_LIMIT` straight after `E_SCHEMA`), and the 1,000,000-record limit contradicts the general array cap of 100,000 in `limits.md`. Register: `docs/known-issues.md`.
