# First vertical slice

The plain idea: one case goes in as JSON, each language answers, and the answer must match the golden file. Follow it once by hand and the rest of the project is the same thing repeated.

Formally, the contract is `specifications/cli-contract.md`: `quantforge run` reads one case on stdin and writes one result on stdout.

Build a CLI, here Rust, from the repository root:

```bash
(cd rust && cargo build --release)
```

Send one case:

```bash
echo '{"schema_version":"1.0","case_id":"ex-1","operation":"core.daycount.year_fraction","inputs":{"convention":"ACT_360","start":"2024-01-01","end":"2024-07-01"}}' | rust/target/release/quantforge run
```

Real output, 2026-11-06:

```json
{"schema_version":"1.0","case_id":"ex-1","status":"ok","outputs":{"year_fraction":0.5055555555555555},"diagnostics":{}}
```

That is 182/360. The Java, C++ and Python builds printed the same value.

Run the whole suite against its golden file:

```bash
python conformance/runner/runner.py --impl rust --suite daycount
```

Then read each case's `verified_by` in `datasets/golden/core/daycount.json` to see what stands behind the expected values.
