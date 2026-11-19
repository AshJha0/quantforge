# H-5 results

Targets: `specifications/10-execution/library-interfaces.md` section 4, committed in 6560d079 before this run and not changed by it.

## Java, local Windows laptop, not the acceptance machine (2026-11-18)

Reference laptop of `README.md` (Intel Core 5 120U, Windows 11), OpenJDK 25.0.5, default JVM flags, not pinned. Harness `java25/src/test/java/org/quantforge/bench/H5Latency.java`, run as `java -cp "target/classes;target/test-classes" org.quantforge.bench.H5Latency ../examples`. Clock overhead (`System.nanoTime`, median of 10,000 pairs): 100 ns, which is also the timer's apparent resolution on this machine, so single-call figures below about 1 us are coarse. Raw: `java_local_windows.json`. In-process analytics on simulated inputs; no trading-system, network or venue latency is claimed.

| # | Target p50 / p99 | Measured p50 / p99 | On this machine |
|---|---:|---:|---|
| E1 twap N=100 | 1 us / 5 us | 0.2 us / 0.6 us | under |
| E2 vwap N=390 | 20 us / 100 us | 48.4 us / 124.5 us | over (both) |
| E3 AC trajectory N=100 | 5 us / 25 us | 8.1 us / 30.2 us | over (both) |
| E4 shortfall, 1,000 fills | 5 us / 25 us | 4.7 us / 15.2 us | under |
| E5 as_quotes (batch 100) | 200 ns / 1 us | 25 ns / 53 ns | under |
| E6 impact_sqrt (batch 100) | 100 ns / 500 ns | 9 ns / 20 ns | under |
| B1* bootstrap | 2 ms / 5 ms | 242 us / 557 us | under |
| B2* swap PV | 50 us / 250 us | 4.2 us / 11.7 us | under |
| B3 implied vol | 5 us / 25 us | 1.8 us / 5.3 us | under |

A laptop figure never counts as met or missed (spec 4.4); the E2 and E3 overs are noted for the acceptance run, not acted on, and the targets are not moved. E2 is dominated by the largest-remainder sort (HR-3); E3 by one `sinh` ratio per step.

\* Deviations from the spec workload, so these rows are indicative only: B1 used the unjittered 13-quote example `examples/ois_bootstrap_sofr.json` rather than T1's jittered set; B2 priced one 5Y PAY trade rather than a T2-book trade. B4 (10,000-swap book) was not run.

Not run: Python (all rows), Rust and C++ (no typed layer yet; WSL queue busy), and the acceptance machine (Actions runner).
