# Tutorial 48: how fast is the book? Reading a latency table honestly

<!-- tutorial:only python -->

The plain idea: a trading system's order book must apply each market-data message and answer "what is the best bid?" in well under a microsecond. Whether it does is a measurement, and a measurement is only useful if the targets were fixed before it, the machine is stated, and misses are reported as misses.

You will compare the first recorded H-9 run against its targets. Budget 10 minutes. There is nothing to build: the figures are the run's recorded results.

<p class="note">Available from v0.10.0 (unreleased). The low-latency books (<code>cpp26/include/quantforge/core/fast_book.hpp</code>, <code>rust/crates/quantforge-core/src/fast_book.rs</code>) and the benchmark are in the repository. The figures below are copied from <code>benchmarks/results/h9/README.md</code> (2026-11-18): <strong>a laptop under WSL, not the acceptance machine</strong>; in-process, simulated feed; no network or venue latency. The targets are from <code>specifications/09-microstructure/low-latency-targets.md</code>, fixed before any timing run (HR-23).</p>

Terms, defined here. **p99** is the 99th percentile: 1 % of samples were slower. **Workload S** is the synthetic stress stream: 10,000,000 messages from `core.rng` seed 20261117, 1,000,000 of warm-up and 9,000,000 timed. `qty_at` returns the depth at one price; `top(n)` copies the best `n` levels into a caller's buffer.

## What you need

- A clone of the repository, with commands run from its root.
- [uv](https://docs.astral.sh/uv/): `uv sync --locked --project python`. The script uses the Python standard library only.

## Step 1: check the numbers

<!-- tutorial:run python -->
```python
# H-9 workload S: recorded laptop medians (ns, benchmarks/results/h9/README.md on branch h-lowlat) against the
# targets fixed before any run (specifications/09-microstructure/low-latency-targets.md).
rows = [  # (metric, target, C++, Rust)
    ("update p50", 150, 39, 47),
    ("update p99", 1000, 80, 94),
    ("update p99.9", 5000, 264, 242),
    ("best_bid p99", 50, 26, 105),
    ("best_ask p99", 50, 22, 53),
    ("qty_at present p99", 100, 120, 99),
    ("qty_at absent p99", 100, 28, 52),
    ("top(10) p99", 200, 69, 56),
    ("top(100) p99", 1000, 73, 76),
]
for metric, target, cpp, rust in rows:
    verdict = " ".join(f"{lang} {'met' if v <= target else 'MISSED'}" for lang, v in (("C++", cpp), ("Rust", rust)))
    print(f"{metric:<19} target <= {target:>5}  C++ {cpp:>4}  Rust {rust:>4}  {verdict}")
print("laptop, WSL, one pinned thread; in-process, simulated feed; no network or venue latency")
```

Output (CI checks these lines):

<!-- tutorial:expect -->
```text
update p50          target <=   150  C++   39  Rust   47  C++ met Rust met
update p99          target <=  1000  C++   80  Rust   94  C++ met Rust met
update p99.9        target <=  5000  C++  264  Rust  242  C++ met Rust met
best_bid p99        target <=    50  C++   26  Rust  105  C++ met Rust MISSED
best_ask p99        target <=    50  C++   22  Rust   53  C++ met Rust MISSED
qty_at present p99  target <=   100  C++  120  Rust   99  C++ MISSED Rust met
qty_at absent p99   target <=   100  C++   28  Rust   52  C++ met Rust met
top(10) p99         target <=   200  C++   69  Rust   56  C++ met Rust met
top(100) p99        target <=  1000  C++   73  Rust   76  C++ met Rust met
laptop, WSL, one pinned thread; in-process, simulated feed; no network or venue latency
```

### Reading the numbers

- **Updates meet every target in both languages**, with room: a median of 39 ns (C++) and 47 ns (Rust) against 150. Figures are the median of five runs; the results file gives the min-max range, for example Rust p99 94 (88 to 117).
- **Three query rows miss.** Rust `best_bid` and `best_ask` p99, and C++ `qty_at` for a present price. They are published as misses; the targets were not moved (HR-23).
- **Why the misses need care.** Each query was timed singly, and one clock read costs about 15 ns (C++) or 17 ns (Rust) at p50, so a 50 ns target is close to the clock's own cost. Batch timing for queries (HR-21) was not run, so the misses include the clock read and are stated as single-sample figures.
- **Zero allocations** in the measured region in both languages, every run (row L4), and 0 mismatches against a plain transcription of the order-book spec at 10,000 checkpoints: speed did not trade against correctness.

### The formal statement, checked against the spec

From [`09-microstructure/low-latency-book.md`](../../specifications/09-microstructure/low-latency-book.md) and [`low-latency-targets.md`](../../specifications/09-microstructure/low-latency-targets.md) (rulings HR-18 to HR-24).

- Same answer, faster: every result must equal `micro.book.rebuild` on the same stream ([Tutorial 41](tutorial-41-rebuild-a-book.md)).
- Harness: one process, one thread pinned to one core, a monotonic clock around each `apply`, clock cost published and not subtracted, HdrHistogram-style buckets; unpaced replay, so no coordinated-omission correction is claimed.
- Not yet measured: workload R (a full recorded day at 100 levels) and Java (row L3). Those rows stay open rather than being filled from S.

## For practitioners

- **A laptop number is a laptop number.** Frequency scaling is not visible under WSL and other jobs may have run at the same time; the acceptance run is a pinned Linux machine.
- **Pre-decoded input.** Parsing is not timed ("no I/O", H-9(a)), so these figures say nothing about network or decoding cost.

## Common mistakes

- **Quoting the median alone.** The tail (p99.9) is where a slow book hurts; it is reported for every row.
- **Subtracting the clock cost.** The spec forbids it: the overhead is published beside the figures so a reader can judge.

## What you just did

You read a latency table against targets fixed in advance, found three misses, and saw why a single-sample query time near the clock cost needs a batch measurement before it means much.

## Try next

- Open `benchmarks/results/h9/cpp_S.json` and find the p99 for delete messages alone.

## References and further reading

- G. Tene, "How NOT to measure latency" (2015), via the spec's secondary source; HdrHistogram README.
- This project: the two specs above; all sources in [References](../references.md).
