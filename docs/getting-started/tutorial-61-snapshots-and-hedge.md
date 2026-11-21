# Tutorial 61: snapshots a reader can trust, and the hedge they carry

<!-- tutorial:only python -->

The plain idea: one thread owns the market state; many threads price and hedge from it. If readers looked at the state while the writer changed it, a reader could see a new yield next to an old delta. So the writer never changes anything in place: it builds a complete, read-only copy (a snapshot) and makes it current with one store. A reader takes whichever snapshot is current and can check, from a checksum stored inside it, that it has the whole of one snapshot. Each snapshot also carries a hedge recommendation: how many units of a 10-year zero cancel the book's sensitivity to a parallel move.

You will compute the hedge for version 1 of the shared scenario by hand, check that it cancels a further 1 bp move to first order, compute the checksum and see it catch a one-bit change, and run a small race of one writer and four readers. Budget 10 minutes.

<p class="note">Stage K, item K-5, merged to <code>main</code> 2026-11-20 (not in a tag; spec <code>specifications/12-platform/lock-free-snapshots.md</code> 1.0.0, rulings KR-280 to KR-288 in <code>specifications/stage-k-rulings-k5.md</code>, confirmed 2026-11-20). Label: "latency-aware analytics on simulated data"; the book is simulated (<code>datasets/scenarios/k5_snapshot.json</code>, drawn once from <code>random.Random(20261120)</code>). <strong>The Python build used here is a correctness reference only and is not lock-free</strong>; the race evidence that counts is the C++ and Rust ThreadSanitizer and Java jcstress runs, and on 2026-11-21 the three CI race jobs had not yet run green, no timing run existed (acceptance LF5 not met, no latency claimed), and the hedge is a library function with no goldens and no outside check (<code>docs/known-issues.md</code>, read 2026-11-21). Step 1 uses the standard library; Step 2 calls <code>quantforge_core.live_snapshot</code>, and CI checks that it prints the lines shown under Step 1.</p>

Terms, defined here. A **snapshot** holds a version, a logical event number, the cumulative parallel yield shift `h` of the simulated market, the delta-gamma P&L estimate and its bound, the book's parallel delta, the delta of one unit of the hedge zero, the hedge notional, and a 64-bit checksum of the other fields. A **torn read** is a read that mixes fields of two snapshots. **Delta** here is `dV/dh`, the change in value per unit of parallel yield move.

## What you need

- A clone of the repository, with commands run from its root.
- [uv](https://docs.astral.sh/uv/): `uv sync --locked --project python`. Step 1 uses the Python standard library only.

## Step 1: the hedge, the checksum and a race, by hand

```python
# K-5 snapshots restated with the standard library: the hedge, the checksum, a torn read, a small race.
import json
import math
import struct
import threading

sc = json.load(open("datasets/scenarios/k5_snapshot.json", encoding="utf-8"))  # simulated book, 20 zeros
book = [(p["notional"], p["maturity"], p["yield"]) for p in sc["book"]]
TH, YH = sc["hedge"]["maturity"], sc["hedge"]["yield"]
MASK, SEED, MUL = (1 << 64) - 1, 0x9E3779B97F4A7C15, 0x94D049BB133111EB


def checksum(words):  # KR-287: c = rotl64(c xor w, 27) * MUL mod 2^64
    c = SEED
    for w in words:
        x = (c ^ w) & MASK
        c = ((((x << 27) | (x >> 37)) & MASK) * MUL) & MASK
    return c


def bits(x):
    return int.from_bytes(struct.pack("<d", x), "little")


def snapshot(k, h):  # version, as_of, shift, estimate, book delta, hedge unit delta, hedge notional (no bound here)
    est = math.fsum(n * math.exp(-y * t) * (-t * h + t * t * h * h / 2) for n, t, y in book)
    d = math.fsum(-t * (n * math.exp(-(y + h) * t)) for n, t, y in book)
    u = -TH * math.exp(-(YH + h) * TH)
    return k, k, h, est, d, u, -d / u


def words(s):
    return [s[0], s[1]] + [bits(x) for x in s[2:]]


print("checksum of no words, [0], [1, 2, 3]:", hex(checksum([])), hex(checksum([0])), hex(checksum([1, 2, 3])))
k, _, h, est, d, u, q = snapshot(1, 0.005)
print(f"version 1, shift {h}: estimate {est:.2f}, book delta {d:.3f}, hedge unit delta {u:.6f}, hedge notional {q:.2f}")


def value(h, units):  # full revaluation of the book plus `units` of the hedge zero
    return math.fsum(n * math.exp(-(y + h) * t) for n, t, y in book) + units * math.exp(-(YH + h) * TH)


move = 0.0001
for units, name in ((0.0, "unhedged"), (q, "hedged")):
    print(f"{name}: value change for a further 1 bp move {value(h + move, units) - value(h, units):.2f}")

good = words(snapshot(1, 0.005))
stored = checksum(good)
torn = good[:6] + [bits(math.nextafter(q, math.inf))] + good[7:]  # hedge notional moved by one unit in the last place
print("intact snapshot passes:", checksum(good) == stored, "; torn snapshot passes:", checksum(torn) == stored)


def shift_of(k):  # KR-287 scenario rule
    return 0.0 if k == 0 else ((k * 7919) % 401 - 200) * 5e-5


current = (snapshot(0, 0.0), checksum(words(snapshot(0, 0.0))))  # one reference, replaced whole
P, R = 2000, 4
seen = [[0, 0, -1, 0, 0] for _ in range(R)]  # torn, non-monotone, last version, reads, mismatched


def reader(r):
    while True:
        s, c = current
        if checksum(words(s)) != c:
            r[0] += 1
        if s[0] < r[2]:
            r[1] += 1
        r[2] = max(r[2], s[0])
        r[3] += 1
        if r[3] % 64 == 0 and s != snapshot(s[0], s[2]):  # exactness: the stored numbers equal a fresh computation
            r[4] += 1
        if s[0] >= P:
            return


threads = [threading.Thread(target=reader, args=(r,)) for r in seen]
for t in threads:
    t.start()
for k in range(1, P + 1):
    s = snapshot(k, shift_of(k))
    current = (s, checksum(words(s)))
for t in threads:
    t.join()
print(f"race, {P} publishes, {R} readers: torn {sum(r[0] for r in seen)}, non-monotone {sum(r[1] for r in seen)}, "
      f"mismatched {sum(r[4] for r in seen)}, last versions {[r[2] for r in seen]}")
```

Output (CI checks that Step 2 prints these lines; measured 2026-11-21 on branch `k-v1-docs-a`, Python 3.15.2 through `uv`, local laptop, not the acceptance machine):

<!-- tutorial:expect -->
```text
checksum of no words, [0], [1, 2, 3]: 0x9e3779b97f4a7c15 0xf6e599aef89d022f 0x8517cc75de438e52
version 1, shift 0.005: estimate 67545.44, book delta 12740024.149, hedge unit delta -6.376282, hedge notional 1998033.51
unhedged: value change for a further 1 bp move 1272.46
hedged: value change for a further 1 bp move -0.90
intact snapshot passes: True ; torn snapshot passes: False
race, 2000 publishes, 4 readers: torn 0, non-monotone 0, mismatched 0, last versions [2000, 2000, 2000, 2000]
```

### Reading the numbers

- **The checksum.** The three pinned values are the ones the spec fixes for every build (section 4): no words gives the seed `0x9e3779b97f4a7c15`, `[0]` gives `0xf6e599aef89d022f`, `[1, 2, 3]` gives `0x8517cc75de438e52`. If your port prints these, its rotate and multiply are right.
- **The hedge.** Version 1 has `h = ((1 x 7919) mod 401 - 200) x 5e-5 = (300 - 200) x 5e-5 = 0.005`. The book's delta at the shifted yields is 12,740,024.149: its value rises about 1,274 for each 1 bp rise in yields, so on balance it is short duration. One unit of the 10-year zero at 4% has delta `-10 exp(-(0.04 + 0.005) x 10) = -10 exp(-0.45) = -6.376282`. Units that cancel the book's delta: `q = -12,740,024.149 / -6.376282 = 1,998,033.51`. The spec's worked example gives the same figures (section 3).
- **Does it hedge?** Revalue in full for a further 1 bp move: the book alone changes by 1,272.46, the book plus the hedge by -0.90. What is left is second order: the book's convexity differs from the hedge zero's, and a parallel-delta hedge does nothing about that or about non-parallel moves.
- **A torn snapshot is caught.** Moving the hedge notional by one unit in the last place, without recomputing the checksum, makes the check fail. That is how a reader in the C++ and Rust race tests detects a torn read: every read recomputes the checksum.
- **The race.** One writer publishes versions 1 to 2,000 while four readers read until they see version 2,000. No read was torn, no reader saw a version go backwards, and every 64th read equalled a fresh computation for its version (exactness, KR-284). In CPython this is what you would expect: replacing one reference is atomic. It shows the semantics, not lock-freedom or speed.

### The formal statement, checked against the spec

From `specifications/12-platform/lock-free-snapshots.md` 1.0.0, sections 1 to 4 (read 2026-11-21).

- Guarantees: no torn read; monotone versions per reader; every reader eventually sees the final version; staleness bounded by the publishes during a read, stated and not timed; exactness, every number bit-identical to calling the same functions directly.
- Fields (KR-283): `estimate_pnl` and `bound` from `risk.intraday.delta_gamma_bound(book, h)`; `book_delta = fsum_i(-T_i N_i exp(-(y_i + h) T_i))`; `hedge_unit_delta = -T_H exp(-(y_H + h) T_H)`; `hedge_notional = -book_delta / hedge_unit_delta`.
- Checksum (KR-287): `c = 0x9E3779B97F4A7C15`; for each 64-bit word, `c = rotl64(c xor w, 27) x 0x94D049BB133111EB mod 2^64`, over version, as-of, then the IEEE 754 bit patterns of the six numbers.
- Algorithm (KR-280 to KR-282): Java publishes a record with a release store and reads it with an acquire load. C++ and Rust use single-writer hazard pointers over a fixed pool of `R + 2` slots: a reader announces the slot it will read and re-checks `current`; the writer reuses only a slot no reader has announced, which always exists by pigeonhole. Writer wait-free, readers lock-free but not wait-free; no heap allocation after construction.
- Acceptance (confirmed 2026-11-20): LF1 race tests clean under ThreadSanitizer and jcstress; LF2 each planted fault shown failing; LF3 exactness on 1,000 publishes per build; LF5 timing targets S1 to S5, not met because no timing run exists.

## Step 2: the same through the library

<!-- tutorial:run python -->
```python
# The same through quantforge_core.live_snapshot (K-5; the Python build is a correctness reference, not lock-free).
import dataclasses
import json
import math

from quantforge_core import live_snapshot as ls
from quantforge_core import stage_k as sk

sc = json.load(open("datasets/scenarios/k5_snapshot.json", encoding="utf-8"))
book = [sk.ZeroPosition(p["notional"], p["maturity"], p["yield"]) for p in sc["book"]]
hedge = ls.HedgeInstrument(sc["hedge"]["maturity"], sc["hedge"]["yield"])

print("checksum of no words, [0], [1, 2, 3]:", hex(ls.checksum([])), hex(ls.checksum([0])), hex(ls.checksum([1, 2, 3])))
s = ls.build(1, 1, book, hedge, ls.scenario_shift(1))
print(f"version 1, shift {s.shift}: estimate {s.estimate_pnl:.2f}, book delta {s.book_delta:.3f}, "
      f"hedge unit delta {s.hedge_unit_delta:.6f}, hedge notional {s.hedge_notional:.2f}")


def value(h, units):  # full revaluation of the book plus `units` of the hedge zero
    return (math.fsum(p.notional * math.exp(-(p.yield_ + h) * p.maturity) for p in book)
            + units * math.exp(-(hedge.yield_ + h) * hedge.maturity))


for units, name in ((0.0, "unhedged"), (s.hedge_notional, "hedged")):
    print(f"{name}: value change for a further 1 bp move {value(s.shift + 0.0001, units) - value(s.shift, units):.2f}")

torn = dataclasses.replace(s, hedge_notional=math.nextafter(s.hedge_notional, math.inf))  # checksum kept
print("intact snapshot passes:", s.intact(), "; torn snapshot passes:", torn.intact())

reports = ls.run_race(book, hedge, publishes=2000, readers=4)
print(f"race, 2000 publishes, 4 readers: torn {sum(r.torn for r in reports)}, "
      f"non-monotone {sum(r.non_monotone for r in reports)}, mismatched {sum(r.mismatched for r in reports)}, "
      f"last versions {[r.last_version for r in reports]}")
```

## For practitioners

- **Publish whole objects.** The pattern needs no lock on the read side because nothing a reader can reach is ever written again. The cost moves to reclamation: knowing when an old snapshot's memory can be reused. Java leaves it to the garbage collector; C++ and Rust need hazard pointers or an equivalent.
- **Why not a seqlock.** A seqlock reader reads memory the writer may be writing at that moment, which the C++ and Rust memory models count as a data race unless every field is atomic, and a writer stalled mid-write blocks every reader (spec, KR-281).
- **The hedge is a number, not an order.** It neutralises parallel delta only; check the residual by full revaluation, as Step 1 does, before trusting it for larger or non-parallel moves.

## Common mistakes

- **Taking the Python race as evidence of lock-freedom.** It is a semantics check; the counted race tests are the ThreadSanitizer and jcstress runs.
- **Computing the checksum over decimal text.** It is over the IEEE 754 bit patterns, so `0.1 + 0.2` and `0.3` give different checksums, as they should.

## What you just did

You computed a parallel-delta hedge from the snapshot scenario and checked by full revaluation that it cancels a further move to first order, reproduced the pinned checksum values, saw a one-bit change caught, and ran a single-writer, four-reader race with no torn or backward reads.

## Try next

- Compute the hedge for version 2 (`h = ((2 x 7919) mod 401 - 200) x 5e-5`) and compare with the `expected` list in `datasets/scenarios/k5_snapshot.json`.
- Read `program/stage_k_k5/K5_RACE_EVIDENCE.md` for the local ThreadSanitizer and jcstress runs and the planted faults.

## References and further reading

- This project: `specifications/12-platform/lock-free-snapshots.md`, `specifications/stage-k-rulings-k5.md`, `python/quantforge_core/live_snapshot.py`, `datasets/scenarios/k5_snapshot.json`, [Tutorial 54](tutorial-54-intraday-risk-bounds.md) for the delta-gamma bound.
- M. M. Michael, "Hazard pointers: safe memory reclamation for lock-free objects", *IEEE Transactions on Parallel and Distributed Systems* 15(6), 2004 (recalled through the spec).
