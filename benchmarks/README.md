# Benchmarks

The plain idea: send the same batch of cases to each language's CLI and time it from the outside.

This measures the whole CLI path: process start, JSON parsing, the calculation, JSON writing and the pipe. It says nothing about the latency of a single call, and it is not a measure of any language's numerical speed. The project makes no latency or HFT claims. Nothing here moves a capability to Benchmarked.

## Method

`cli_throughput.py` uses the commands in `conformance/runner/implementations.json`. Build the CLIs first, as in `docs/developer-guides/test-infrastructure.md`.

```bash
python benchmarks/cli_throughput.py --suite daycount --cases 20000 --repeats 5 --out result.json
```

- The workload is the inputs of the chosen golden suite, in file order, repeated up to the case count. Expected values are not sent.
- One unmeasured batch runs first, then the repeats, one language at a time. The figure is the median.
- `cases/s` is the case count over wall time, with start-up included.
- `marginal` is (N - N/5) / (t(N) - t(N/5)), which removes fixed start-up cost. JIT warm-up in Java is only partly removed.
- `start-up` is the median wall time of `quantforge version`. The Python figure includes the `uv run` launcher.
- A run fails if the line count is wrong or if a language's statuses differ from the first language's. Values are checked by conformance, not here.

## Recorded run

Observed, 2026-11-06, commit `c956604`, one run on a laptop in normal use, so treat differences of a few percent as noise. The raw file is `results/2026-11-06-windows-daycount.json`.

Machine: Intel Core 5 120U, 12 logical CPUs, 15.6 GiB, Windows 11 (10.0.26200), mains or battery state not recorded. Workload: 20,000 cases from the `daycount` suite (1,756 distinct), 5 repeats.

| Language | Toolchain and build | cases/s | marginal cases/s | start-up, s |
|---|---|---:|---:|---:|
| Rust | rustc 1.99.1, `cargo build --release` | 115,488 | 141,251 | 0.034 |
| C++ | GCC 16.2.0 (WinLibs), CMake Release | 44,958 | 50,220 | 0.082 |
| Java | JDK 25.0.5, default JVM flags | 21,032 | 28,150 | 0.148 |
| Python | CPython 3.15.2, through `uv run` | 13,700 | 23,949 | 0.685 |

Day counts are cheap, so this mostly compares JSON handling and I/O. A heavier suite would rank differently, and this one workload should not be read as a ranking of the languages. It has not been run on Linux or in CI, and no CI job runs it, to save minutes.
