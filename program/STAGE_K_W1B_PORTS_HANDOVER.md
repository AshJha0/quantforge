# Stage K round 1, wave 1b ports: SA-CCR (K-8d) and FRTB IMA backtesting (K-8e) in Java, Rust and C++

Branch `k-w1b-ports` (off `k-w1b` at 8ec742c4), written 2026-11-19 by the wave 1b port lane. The Python reference, specs, rulings (KR-30 to KR-47) and goldens are those of `program/STAGE_K_W1B_HANDOVER.md`; nothing here changes them. None of the central registration files was edited: `cli/Operations.java`, `ops/mod.rs` and its `DOMAINS` table, `dispatch.cpp`, `cli-contract.md`, `name-map.json` and the generated checklists are untouched. The coordinator applies the lines below at integration.

## Shared tables: one source

The two JSON files under `specifications/06-risk/` stay the only copy of the parameters (evidence: read, the three builds' sources below).

| Build | Mechanism | Staleness check |
|---|---|---|
| Rust | `include_str!` of the JSON, parsed once (`saccr::params()`, `frtb_backtest::tables()`), as `sobol.rs` does | none needed: the file is the source; `tests/stage_k_w1b.rs` also compares the parsed values with the file |
| C++ | `#embed` of the JSON, parsed once, as `sobol.cpp` does; `OBJECT_DEPENDS` on both files so an edit rebuilds | as Rust |
| Java | the repo had no build-time mechanism (Sobol is a hand-kept copy with an equality test). New generator `tools/gen_k_w1b_tables.py` writes `risk/SaCcrTables.java` and `risk/FrtbBacktestTables.java` | `python tools/gen_k_w1b_tables.py --check` exits 1 when a generated file is stale; `SaCcrTest` and `FrtbBacktestTest` also compare the classes with the JSON |

Suggested CI line (coordinator's choice of job): `python tools/gen_k_w1b_tables.py --check` next to `gen_name_map.py --check`.

## Files added

| Build | Core | CLI handler (unregistered) | Tests |
|---|---|---|---|
| Java | `java25/src/main/java/org/quantforge/risk/SaCcr.java`, `FrtbBacktest.java`, generated `SaCcrTables.java`, `FrtbBacktestTables.java` | `java25/src/main/java/org/quantforge/cli/OpsStageKW1b.java` (`register(table)`) | `risk/SaCcrTest.java`, `risk/FrtbBacktestTest.java`, `cli/StageKW1bCliTest.java` |
| Rust | `rust/crates/quantforge-core/src/saccr.rs`, `frtb_backtest.rs` | `rust/crates/quantforge-cli/src/ops/kw1b.rs` (`registry!` block, `NAMES`, `dispatch`) | `quantforge-core/tests/stage_k_w1b.rs`; `ops/kw1b.rs` `mod tests` |
| C++ | `cpp26/include/quantforge/core/saccr.hpp`, `frtb_backtest.hpp`; `cpp26/src/core/saccr.cpp`, `frtb_backtest.cpp` | `cpp26/src/cli/ops_k_w1b.inc` (array `k_w1b_ops`) | `cpp26/tests/test_stage_k_w1b.cpp` |

## Edits outside new files (the smallest that compile the new files)

| File | Edit | Why |
|---|---|---|
| `rust/crates/quantforge-core/src/lib.rs` | `pub mod frtb_backtest;` after `pub mod frtb3;`, `pub mod saccr;` after `pub mod sabr;` | a Rust module is compiled only when declared |
| `rust/crates/quantforge-cli/src/main.rs` | 4 lines after `mod ops_j_tests;`: a comment, `#[cfg(test)]`, `#[path = "ops/kw1b.rs"]`, `mod ops_kw1b;` | compiles the handler file for its tests without touching `ops/mod.rs`; test-only, so release builds and clippy on the binary do not see dead code |
| `cpp26/CMakeLists.txt` | one block before `# H-5 p50/p99 harness`: `target_sources(quantforge_core ...)` for the two `.cpp`, `OBJECT_DEPENDS` on the two JSON files, `target_sources(quantforge_core_tests ...)` for the test | the source lists are central; a separate `target_sources` block merges apart from them |

## Registration lines (apply at integration)

Java, `java25/src/main/java/org/quantforge/cli/Operations.java`, `MODULES`: add after `new Registry.Module("paper", OpsPaper::register)` (put a comma on that line):

```java
            new Registry.Module("stage_k_w1b", OpsStageKW1b::register)
```

Then delete the test `registersFourVerbsAndNoCollision` in `java25/src/test/java/org/quantforge/cli/StageKW1bCliTest.java` (it asserts the verbs are not yet registered). `GoldenSuiteTest` will then replay `saccr_k` and `btk_k` through `Main.handle` as well.

Rust, `rust/crates/quantforge-cli/src/ops/mod.rs`:

```rust
mod kw1b;                                   // in the mod list, after `mod infl;`
    ("risk", kw1b::NAMES, kw1b::dispatch), // in DOMAINS, after ("risk", w3::risk::NAMES, w3::risk::dispatch)
```

and in `rust/crates/quantforge-cli/src/main.rs` delete the four lines that declare `mod ops_kw1b` (comment, `#[cfg(test)]`, `#[path = "ops/kw1b.rs"]`, `mod ops_kw1b;`). Delete the test `verbs_are_not_registered_yet` in `ops/kw1b.rs`. The file uses absolute paths (`crate::ops::registry!`, `crate::ops::{Outcome, plain}`), so it compiles unchanged as `ops::kw1b`. Optional, no result changes: in `limits.rs` `operation_above`, `"risk.frtb.backtest.zone" | "risk.frtb.backtest.desk" => above(i, "observations", 1_000_000),` (the core already returns `E_LIMIT` first, KR-46).

C++, `cpp26/src/cli/dispatch.cpp`:

```cpp
#include "quantforge/core/frtb_backtest.hpp"   // with the core includes at the top
#include "quantforge/core/saccr.hpp"
#include "ops_k_w1b.inc"                       // after #include "ops_paper.inc"
    k_w1b_ops,                                 // in registry[], after paper_ops,
```

Then delete the last loop of the test case "input layer order and the unregistered verbs" in `cpp26/tests/test_stage_k_w1b.cpp` (it checks the verbs are not registered). The test compiles a renamed copy of `dispatch.cpp`; `ops_k_w1b.inc` carries `#pragma once`, so after integration the test's own `#include` of it is a no-op and the test keeps working. Optionally move the two `.cpp` into the `add_library(quantforge_core ...)` list and the test into the `quantforge_core_tests` list, and drop the separate block.

Python stays as `program/STAGE_K_W1B_HANDOVER.md` says (registry, operations import).

## Error order (HR-122) as built

Every handler reads all inputs first (E_SCHEMA, enum values included: a value outside the list is E_SCHEMA in the input layer of each build), then the gate (held E_LIMIT, then the finite rule), then the core: structural E_INPUT over every trade, then E_DOMAIN. The Rust and C++ cores also apply the finite rule themselves before the structural checks (rule E1 for public library entry points); the Java core relies on the CLI layer, as Python does. The observations cap (1,000,000) is E_LIMIT, checked first in each core (KR-46) and also in each handler after the reads.

## Evidence (measured on the local laptop, not the acceptance machine, 2026-11-19)

Targeted runs only, not the full CI chain (no full test suites, no conformance runner, no mutation, no sanitizer build).

| Build | Command | Result | Coverage of the new files |
|---|---|---|---|
| Java | `mvn -Pcoverage test -Dtest=SaCcrTest,FrtbBacktestTest,StageKW1bCliTest` (JDK 25, Windows) | 18 tests pass (7, 6, 5); saccr_k, btk_k, tlk_k replay clean | JaCoCo lines: SaCcr 262/263, FrtbBacktest 63/63, OpsStageKW1b 82/82 (branches 198/205, 48/48, 20/20) |
| Rust | `cargo fmt --check`; `cargo clippy -p quantforge-core -p quantforge-cli --all-targets -D warnings`; `cargo test -p quantforge-core --test stage_k_w1b`; `cargo test -p quantforge-cli ops_kw1b` (WSL) | fmt and clippy clean; 11 + 5 tests pass (3 proptest properties at 150 cases each) | llvm-cov lines: saccr.rs 99.65%, frtb_backtest.rs 95.37%, ops/kw1b.rs 95.04% |
| C++ | gcc 15.2 Release, `-DQF_WERROR=ON` (`-Werror -Wconversion -Wshadow`), targets `quantforge_core_tests` and `quantforge`; `quantforge_core_tests "[k_w1b]"`; clang 21.1.8 `-fsyntax-only -Wshadow -Wconversion -Werror` on the two core files and the test (WSL) | builds clean; 9 test cases, 4,476 assertions pass; clang clean | gcovr lines: ops_k_w1b.inc 100%, saccr.cpp 99%, frtb_backtest.cpp 97% |

All three golden files are replayed in process in each build, every case (value, error, and the two-error cases, read from the files, counts not hard-coded), through each build's own input layer and gate order. Each build asserts the five CRE99 EADs 569, 381, 5,406, 936, 1,879 (KR-30 rounding), the printed intermediates, KR-31's -7,099, MAR99 Table 2 rows 0 to 10, and the KR-36 overflow case (V - C > 0 with a subnormal add-on gives multiplier exactly 1).

Not verified: the full CI chain of any build, the conformance runner against the built CLIs (the verbs are unregistered), the C++ sanitizer and coverage-gate jobs, mutation testing, `tools/quality_gate.py --per-file` itself (the per-file figures above were read from the tools' own reports).

## Open points for the coordinator

- No E1 golden: neither `saccr_k` nor `btk_k` has a case with a "NaN" or "Infinity" input expecting E_DOMAIN, so `tools/check_e1_coverage.py` will flag the four new operations once they are in `name-map.json`. All four builds already return E_DOMAIN for such an input (unit-tested here in each build: a "NaN" notional ahead of a missing hedging set). Adding the cases means regenerating the goldens with `oracle/python/gen_stage_k_w1b.py`, which this lane did not touch.
- Binomial sums: the ports build the terms with a running log binomial coefficient (as each build's existing `traffic_light`) and a Neumaier-compensated sum; Python uses `lgamma` terms and `math.fsum`. All golden probabilities agree within `simple_analytic`; the zone boundaries are exact in every golden.
