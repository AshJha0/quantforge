# R4 library interfaces and p50/p99 benchmarks (H-5)

Spec version 0.1.0 (stage H, item H-5). Plan 14.7 H-5; ADR-0011 (`architecture/decisions/ADR-0011-api-style.md`); [PERF] `architecture/performance-standards.md`; [TGT] `benchmarks/targets.md`.

**Targets in section 4 are fixed as of 2026-11-18, in their own commit, before any H-5 timing run** (the R1 rule, as H-9 did in `09-microstructure/low-latency-targets.md`). A miss is published as a miss and is not retuned in the change that measures. A target changes only in its own later commit with a reason, before the next measurement.

## 1. Scope

H-5 asks for an in-process API in each language that meets ADR-0011, plus p50 and p99 latency with targets written first and a 20% regression threshold. This spec covers:

- **(I) the execution and microstructure layer** (operations `exec.schedule.*`, `exec.ac.*`, `exec.impact.*`, `exec.tca.shortfall`, `micro.mm.as_quotes`), whose kernels already exist in all four languages but, in Python, take closed choices as strings and return dicts, which ADR-0011 rules out at a public boundary;
- **(B) the benchmark set**: the four R4 workloads the plan names (bootstrap, swap PV, implied vol, 10,000-swap book) and six execution-layer kernels.

The maths is unchanged. Every typed call delegates to the existing kernel and returns the same numbers; the goldens of `schedules.md`, `almgren-chriss.md`, `impact.md`, `tca.md` and `avellaneda-stoikov.md` stay the acceptance test of the numbers.

## 2. Interfaces (I)

### 2.1 Names

Operation names and input keys follow the name map (ADR-0011 rule 1); the typed layer adds types, not new operation names. Location per language:

| Language | Typed layer | Existing kernels |
|---|---|---|
| Python | module `quantforge_core.exec_api` | `quantforge_core.execution` (dict in, dict out; kept for the CLI) |
| Java | class `org.quantforge.execution.Execution` (already typed) | same class |
| Rust | module `quantforge::execution` types (later lane) | existing |
| C++ | namespace `qf::execution` types (later lane) | existing |

### 2.2 Closed choices (ADR-0011 rule 3)

| Enum | Values | JSON spelling |
|---|---|---|
| `Side` | `BUY`, `SELL` | upper-case string |
| `FillMode` (Java `Mode`) | `UNITS`, `CONTINUOUS` | upper-case string |

Each enum has one parse function at the edge (Python `Side.parse(text)`, Java `Side.valueOf`); an unknown spelling, or a value that is not the enum where the enum is required, is `E_SCHEMA` and never reaches the maths.

### 2.3 Value types (ADR-0011 rules 4 and 5)

All are immutable value types: Python frozen dataclasses with tuple fields, Java records. Each is validated when built, with the spec's error code; none can exist in an invalid state.

| Type | Fields | Invariants checked at construction (code) |
|---|---|---|
| `AcParams` | quantity, horizon, n_steps, sigma, epsilon, eta, gamma | as `almgren-chriss.md` (HR-2, HR-5): eta_tilde > 0, sigma >= 0, horizon > 0 (`E_DOMAIN`); n_steps >= 1, quantity > 0 (`E_INPUT`); epsilon, gamma >= 0 (`E_DOMAIN`); all finite (F-2) |
| `Fill` | quantity, price | quantity > 0 (`E_INPUT`), price > 0 (`E_DOMAIN`), finite |
| `Schedule` | slices, filled, residual | output; slices sum to filled; residual >= 0 |
| `AcTrajectory` | holdings, trades, kappa, expected_cost, variance, objective | output |
| `AcFrontier` | risk_aversions, expected_costs, variances | output; equal lengths |
| `OwOptimal` | initial_block, rate, final_block | output |
| `Shortfall` | delay, execution, opportunity, total, total_bps, vwap_slippage (optional) | output |
| `Quotes` | reservation, spread, bid, ask | bid <= ask (`E_DOMAIN`) |

Thread-safety line (rule 5) on every type above: "Thread safety: immutable; safe to share between threads." Java records holding `double[]` do not copy the arrays on the hot path; their line reads "Thread safety: safe to share once built; the arrays are not copied, so callers must not write to them."

### 2.4 Functions

| Operation | Python typed call | Java |
|---|---|---|
| `exec.schedule.twap` | `twap(quantity, n_buckets, mode: FillMode) -> Schedule` | `Execution.twap(double, long, Mode) -> double[]` |
| `exec.schedule.vwap` | `vwap(quantity, profile, mode) -> Schedule` | `Execution.vwap` |
| `exec.schedule.pov` | `pov(quantity, participation, market_volume, mode) -> Schedule` | `Execution.pov -> Pov` |
| `exec.ac.trajectory` | `ac_trajectory(params: AcParams, risk_aversion) -> AcTrajectory` | `Execution.acTrajectory` |
| `exec.ac.frontier` | `ac_frontier(params, risk_aversions) -> AcFrontier` | `Execution.acFrontier` |
| `exec.impact.sqrt` | `impact_sqrt(quantity, daily_volume, daily_vol, coefficient) -> float` | `Execution.impactSqrt` |
| `exec.impact.ow_optimal` | `ow_optimal(quantity, horizon, resilience) -> OwOptimal` | `Execution.owOptimal` |
| `exec.tca.shortfall` | `shortfall(side: Side, decision_price, arrival_price, end_price, order_quantity, fills: Sequence[Fill], fees, benchmark_vwap=None) -> Shortfall` | `Execution.shortfall`, plus an overload taking `List<Fill>` |
| `micro.mm.as_quotes` | `as_quotes(mid, inventory, risk_aversion, sigma, time_left, k) -> Quotes` | `Execution.asQuotes` |

Functions are pure and hold no state: safe to call from any number of threads.

### 2.5 Acceptance for (I)

1. Every typed call returns exactly (bit for bit) what the kernel returns on the same inputs: a test per operation, plus a property test over random valid inputs (Python, Hypothesis).
2. Every invariant in 2.3 has a test that building an invalid value raises the stated code.
3. A string where an enum is required raises `E_SCHEMA` (Python); `Side.parse`/`FillMode.parse` round-trip the JSON spelling and reject anything else with `E_SCHEMA`.
4. Every public type carries the thread-safety line (checked by a test that reads the docstrings in Python; by review in Java).
5. C++ and Rust: typed layer is a later lane; this spec is its contract.

## 3. Measurement method (B)

- **In process, no I/O.** Inputs are built before the timed region; the timer brackets the library call only. (Unlike T1 to T5, which time the whole CLI path.)
- **Clock.** Java `System.nanoTime`, Python `time.perf_counter_ns`. The clock's own overhead (median of 10,000 back-to-back reads) is measured and published beside every table.
- **Batching.** Where a kernel's p50 is expected below 20 times the clock overhead (E5, E6), each sample times a block of 100 calls and is divided by 100; the table says so. All others time one call per sample.
- **Warm-up.** Java: 20,000 untimed calls (JIT); Python: 1,000.
- **Samples.** Java 100,000 per repeat (10,000 for B1, B4: 100 per repeat), Python 10,000 (B4: 3 per repeat). 5 repeats; the figure reported is the median over repeats of each repeat's p50 and p99 (nearest-rank).
- **Inputs.** Fixed, seed `20261118` where random; B1 and B2 use the T1 quote set and the T2 sample book of `benchmarks/targets.md`.
- **Result sink.** Each result feeds a checksum that is printed, so the JIT cannot drop the call.
- **Machine.** Acceptance machine: GitHub `ubuntu-24.04` standard runner (plan H-5). Any other run is labelled with its machine, and a laptop run is labelled "local Windows laptop, not the acceptance machine".

## 4. Targets (fixed 2026-11-18, before any H-5 timing)

Per call, p50 / p99. Reasoning: the execution kernels are O(N) loops over N <= 1,000 doubles with a transcendental per element at most; at ~1 to 5 ns per element in a JIT-compiled loop, N = 100 is well under a microsecond, so targets are set at roughly 5 to 10 times that for p50 and 5 times p50 for p99 (GC, JIT and interrupts land in the tail). Python pays ~50 to 100 ns per bytecode-level operation, so it gets about 50 times Java. These are recalled orders of magnitude, used only to set ceilings with margin; no outside citation is claimed. B1 and B4 reuse T1 and T2 so the in-process figure can be compared with the CLI figure.

### 4.1 Execution layer

| # | Workload | Java p50 / p99 | Python p50 / p99 |
|---|---|---:|---:|
| E1 | `twap`, X = 1,000,003, N = 100, UNITS | 1 us / 5 us | 50 us / 250 us |
| E2 | `vwap`, X = 1,000,003, N = 390 seeded profile, UNITS (largest remainder) | 20 us / 100 us | 1 ms / 5 ms |
| E3 | `ac_trajectory`, the AC00 golden parameters, N = 100, lambda = 1e-6 | 5 us / 25 us | 250 us / 1.25 ms |
| E4 | `shortfall`, BUY, 1,000 seeded fills, with benchmark VWAP | 5 us / 25 us | 500 us / 2.5 ms |
| E5 | `as_quotes`, one call (batched, section 3) | 200 ns / 1 us | 10 us / 50 us |
| E6 | `impact_sqrt`, one call (batched) | 100 ns / 500 ns | 5 us / 25 us |

Rust and C++: half the Java figures, once their lane measures.

### 4.2 R4 set (plan H-5)

| # | Workload | Java p50 / p99 | Python p50 / p99 | Rust, C++ p50 / p99 |
|---|---|---:|---:|---:|
| B1 | `rates.ois.bootstrap`, T1's 13 SOFR quotes, jittered | 2 ms / 5 ms | 50 ms / 150 ms | 0.5 ms / 1 ms |
| B2 | `rates.swap.pv`, one T2-book trade on a built curve | 50 us / 250 us | 1 ms / 5 ms | 25 us / 100 us |
| B3 | Black implied vol, one option | 5 us / 25 us | 100 us / 500 us | 2 us / 10 us |
| B4 | T2 book, 10,000 swaps, whole book per sample | 5 s / 6 s | 15 s / 18 s | 1 s / 1.2 s |

### 4.3 Regression gate

As H-9 (e) and plan H-5: after the first baseline on the acceptance machine (10 runs on `main`), threshold = max(20%, 3 x coefficient of variation of p99 across the 10 runs); a PR whose median p99 over 3 runs exceeds the baseline by more than the threshold fails. The baseline is refreshed only in its own commit with the reason.

### 4.4 What counts as met

Median over 5 repeats of p50 and of p99 at or under the target on the acceptance machine, with no failed repeat. A laptop figure is published for information and never counts as met or missed.

## 5. Limitations

- Latency of analytics calls on simulated inputs; nothing here is a trading-system, network or venue latency.
- Python is the reference implementation; its targets exist so that a regression is visible, not as a claim of speed.
