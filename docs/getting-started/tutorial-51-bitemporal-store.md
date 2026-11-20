# Tutorial 51: what did we know, and when? A bitemporal store

<!-- tutorial:only python -->

The plain idea: a stored number has two times. One is the period it is meant to describe (the rate for February). The other is the moment we learned it (we heard about February's rate on 2 January, and a correction on 1 April). An as-of store with one time answers "what did we know at 16:00 on Tuesday?". A bitemporal store answers that and also "for which period?", and it never overwrites: a correction is a new record, so a report rerun as of March still shows what March knew.

You will run the query rule by hand on the eight golden cases, see a correction and a withdrawal, and check the property the stage K acceptance test is built on: a record learned later never changes an earlier answer. Budget 10 minutes.

<p class="note">Stage K. The operation <code>core.store.bitemporal_query</code> is merged to <code>main</code> in all four builds (2026-11-19; not in a tag) (spec <code>specifications/01-core/bitemporal-store.md</code> 1.0.0, rulings KR-2 to KR-4 and KR-16). Acceptance evidence files: Python and Java; C++ and Rust run the same properties in their unit tests without writing evidence files (<code>program/STAGE_K_W1_HANDOVER.md</code>). Step 1 restates the rule with the standard library on the golden inputs; Step 2 calls the library, and CI checks that it prints the lines shown under Step 1.</p>

Terms, defined here. **Valid time** `[valid_from, valid_to)` is the period a record describes; `valid_to` null means open-ended. **Knowledge time** is the instant the store learned the record. A query asks at **knowledge as of** `K` for the value **valid at** `V`. **Withdrawn** means the latest record known by `K` that covers `V` is a deletion.

## What you need

- A clone of the repository, with commands run from its root.
- [uv](https://docs.astral.sh/uv/): `uv sync --locked --project python`. Step 1 uses the Python standard library only.

## Step 1: the rule on the shared golden log

The log is the one every `bt_k` value case uses (spec table "Golden value cases"): series `A`, a value of 100 from 1 January, 110 from 1 March, a correction of February to 105 learned on 1 April, and a withdrawal of March onward learned on 2 April.

```python
# The KR-2 query rule on the shared log of goldens bt_k-0001 to 0008, restated with the standard library.
from datetime import datetime, timezone


def t(s):  # "2026-03-15" or a full Z instant
    s = s if "T" in s else s + "T00:00:00Z"
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


LOG = [  # sequence, valid_from, valid_to (None = open), knowledge_time, value, deleted
    (1, "2026-01-01", None, "2026-01-02", 100, False),
    (2, "2026-03-01", None, "2026-03-02", 110, False),
    (3, "2026-02-01", "2026-03-01", "2026-04-01", 105, False),  # a correction for February
    (4, "2026-03-01", None, "2026-04-02", None, True),  # withdraws everything from March on
]


def query(log, k, v):
    known = [r for r in log if t(r[3]) <= t(k) and t(r[1]) <= t(v) and (r[2] is None or t(v) < t(r[2]))]
    if not known:
        return "NONE", None
    w = max(known, key=lambda r: r[0])  # the latest record known by K that covers V
    return ("WITHDRAWN", None) if w[5] else ("FOUND", (w[0], w[4]))


CASES = [  # case, K (knowledge as of), V (valid at), golden status, golden (sequence, value)
    ("bt_k-0001", "2026-03-15", "2026-02-15", "FOUND", (1, 100)),
    ("bt_k-0002", "2026-04-01", "2026-02-15", "FOUND", (3, 105)),
    ("bt_k-0003", "2026-03-15", "2026-03-10", "FOUND", (2, 110)),
    ("bt_k-0004", "2026-04-05", "2026-03-10", "WITHDRAWN", None),
    ("bt_k-0005", "2026-04-05", "2026-01-15", "FOUND", (1, 100)),
    ("bt_k-0006", "2026-01-01T12:00:00Z", "2026-01-15", "NONE", None),
    ("bt_k-0007", "2026-04-01", "2026-03-01", "FOUND", (2, 110)),
    ("bt_k-0008", "2026-04-01", "2026-02-28T23:59:59Z", "FOUND", (3, 105)),
]
for case, k, v, status, row in CASES:
    got = query(LOG, k, v)
    assert got == (status, row), case  # the restatement equals the golden
    print(f"{case} K {k} V {v} -> {got[0]}" + (f" seq {got[1][0]} value {got[1][1]}" if got[1] else ""))

# KR-4: a record learned after K never changes an answer as of K.
early = [r for r in LOG if t(r[3]) <= t("2026-03-15")]
same = all(query(early, "2026-03-15", v) == query(LOG, "2026-03-15", v) for v in ("2026-01-15", "2026-02-15", "2026-03-10"))
print("KR-4: answers as of 2026-03-15 unchanged after appending seq 3 and 4:", same)
```

Output (CI checks that Step 2 prints these lines):

<!-- tutorial:expect -->
```text
bt_k-0001 K 2026-03-15 V 2026-02-15 -> FOUND seq 1 value 100
bt_k-0002 K 2026-04-01 V 2026-02-15 -> FOUND seq 3 value 105
bt_k-0003 K 2026-03-15 V 2026-03-10 -> FOUND seq 2 value 110
bt_k-0004 K 2026-04-05 V 2026-03-10 -> WITHDRAWN
bt_k-0005 K 2026-04-05 V 2026-01-15 -> FOUND seq 1 value 100
bt_k-0006 K 2026-01-01T12:00:00Z V 2026-01-15 -> NONE
bt_k-0007 K 2026-04-01 V 2026-03-01 -> FOUND seq 2 value 110
bt_k-0008 K 2026-04-01 V 2026-02-28T23:59:59Z -> FOUND seq 3 value 105
KR-4: answers as of 2026-03-15 unchanged after appending seq 3 and 4: True
```

### Reading the numbers

- **The correction, before and after it was known.** Asked in mid-March about mid-February, the store returns 100 from record 1: the February correction (record 3) was learned on 1 April, after `K` (`bt_k-0001`). Asked on 1 April about the same day, it returns 105 (`bt_k-0002`). `K` is inclusive: a record learned at exactly `K` counts.
- **The withdrawal.** From 2 April, March onward is withdrawn. Record 4 is the latest record covering 10 March, so it masks records 2 and 1 and the answer is `WITHDRAWN` with no row (`bt_k-0004`). January is untouched: only record 1 covers it (`bt_k-0005`).
- **Nothing known yet.** At noon on 1 January nothing has been learned, so `NONE` (`bt_k-0006`).
- **Edges of valid time.** Record 3 covers `[1 February, 1 March)`, so at 1 March itself it no longer applies and record 2 answers (`bt_k-0007`); one second earlier record 3 still does (`bt_k-0008`).
- **The property.** Removing every record learned after `K` leaves every answer as of `K` the same. That is what makes an old report reproducible from today's log.

### The formal statement, checked against the spec

From `specifications/01-core/bitemporal-store.md` (rulings KR-2 to KR-4, KR-16; read 2026-11-19).

- For a query `(K, V)`, let `C = { r : knowledge_time(r) <= K and valid_from(r) <= V < valid_to(r) }`, with `valid_to` null read as +infinity. If `C` is empty the answer is `NONE`. Otherwise the record with the largest `sequence` in `C` wins; if it is a deletion the answer is `WITHDRAWN`, else `FOUND` with that record.
- The log is checked in the order of the stage A rulings: a missing or mistyped key is `E_SCHEMA`; a non-increasing `sequence`, a `knowledge_time` lower than the previous record's, or `valid_to <= valid_from` is `E_INPUT` (`bt_k-0009`, `bt_k-0010`); more than 1,000,000 records is `E_LIMIT`.
- KR-4, the acceptance property: appending any record with `knowledge_time > K` leaves every `(K, V)` answer unchanged byte for byte. Acceptance evidence (measured by the k-w1 lane, 2026-11-19): 10,000 generated logs and 500,000 query pairs, zero failures, in Python and Java (`program/stage_k_w1/acceptance_python.json` and `acceptance_java.jsonl`, key `kr4_correction_property`). C++ and Rust run the same property in their unit tests (`cpp26/tests/test_stage_k.cpp`, `rust/crates/quantforge-core/src/stage_k_tests.rs`) without writing an evidence file.
- Instants are whole seconds (KR-16). A stage A record is the bitemporal record `[event_time, event_time + 1 s)`.

## Step 2: the same cases through the library

This block calls the library on the goldens in `datasets/golden/stage_k/`. It was turned on at integration (2026-11-19) and printed the same lines as Step 1; CI now checks them.

<!-- tutorial:run python -->
```python
# Goldens bt_k-0001 to 0008 through core.store.bitemporal_query, and the KR-4 property on the same log.
import json

from quantforge_core.cli.main import run_case

cases = {c["case_id"]: c for c in json.load(open("datasets/golden/stage_k/bt_k.json", encoding="utf-8"))["cases"]}


def ask(case_id, inputs):
    r = run_case(json.dumps({"schema_version": "1.0", "case_id": case_id, "operation": "core.store.bitemporal_query", "inputs": inputs}))
    return r["outputs"]


def short(s):
    return s.replace("T00:00:00Z", "")


for n in range(1, 9):
    c = cases[f"bt_k-{n:04d}"]
    out = ask(c["case_id"], c["inputs"])
    assert out == c["expected"]["outputs"], c["case_id"]  # the build equals the golden, key for key
    row = out["row"]
    print(f"{c['case_id']} K {short(c['inputs']['knowledge_as_of'])} V {short(c['inputs']['valid_at'])} -> {out['status']}"
          + (f" seq {row['sequence']} value {row['value']}" if row else ""))

log = cases["bt_k-0001"]["inputs"]["records"]
early = [r for r in log if r["knowledge_time"] <= "2026-03-15T00:00:00Z"]
same = all(ask("kr4", {"records": early, "series_id": "A", "knowledge_as_of": "2026-03-15T00:00:00Z", "valid_at": v})
           == ask("kr4", {"records": log, "series_id": "A", "knowledge_as_of": "2026-03-15T00:00:00Z", "valid_at": v})
           for v in ("2026-01-15T00:00:00Z", "2026-02-15T00:00:00Z", "2026-03-10T00:00:00Z"))
print("KR-4: answers as of 2026-03-15 unchanged after appending seq 3 and 4:", same)
```

## For practitioners

- **Two clocks, two questions.** "What was the February fixing?" has two answers once a correction exists. A risk report must say which one it used; storing `K` with every report makes that answerable later.
- **No persistent store yet.** The operation reads a log passed in the request; there is no database behind it (handover limitation). It fixes the rule that any store must follow.
- **Corrections are not edits.** A store that updates in place cannot answer "as known in March" after April. The cost is a log that only grows.

## Common mistakes

- **Taking the latest record by knowledge time instead of by sequence.** Two records learned in the same second are ordered by `sequence`; the rule uses `sequence` alone.
- **Making `valid_to` inclusive.** It is exclusive, so a record that ends on 1 March does not answer for 1 March (`bt_k-0007`).

## What you just did

You ran the bitemporal query rule on eight golden cases, saw a correction and a withdrawal from both sides of the moment they were learned, and checked that a later record cannot change an earlier answer.

## Try next

- Add a record that corrects January to 101, learned on 10 April, and predict the answer as of 5 April and as of 15 April before you run it.

## References and further reading

- This project: `specifications/01-core/bitemporal-store.md` and `specifications/stage-k-rulings-w1.md`; the stage A store, [`asof-store.md`](../../specifications/01-core/asof-store.md).
- R. T. Snodgrass, *Developing Time-Oriented Database Applications in SQL*, Morgan Kaufmann, 2000, chapters 2 and 10, for valid time and transaction time (cited in the spec; not opened, recalled).
- K. Kulkarni and J.-E. Michels, "Temporal features in SQL:2011", *SIGMOD Record* 41(3), 2012 (cited in the spec; not opened, recalled).
