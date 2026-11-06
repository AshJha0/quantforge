# Cookbook

Short recipes. Commands run from the repository root, in Git Bash or a Unix shell. `python` means any Python 3.12 or later, because the neutral tools use only the standard library.

## Build each CLI

```bash
(cd java25 && mvn -B -DskipTests package)
cmake -S cpp26 -B cpp26/build -G Ninja -DBUILD_TESTING=OFF && cmake --build cpp26/build
uv sync --locked --project python
(cd rust && cargo build --release -p quantforge-cli)
```

## Run the conformance suite for one language

```bash
python conformance/runner/runner.py --impl rust
```

`--impl` takes `java`, `cpp`, `python` or `rust`. Add `--suite daycount` for one suite. The last line of a full run, from 2026-11-06:

```
TOTAL {'cases': 4388, 'pass': 4388, 'fail': 0, 'not_implemented': 0}
```

## Send one case by hand

```bash
echo '{"schema_version":"1.0","case_id":"ex-3","operation":"core.root.brent","inputs":{"function":"cubic_wallis","a":2,"b":3}}' | rust/target/release/quantforge run
```

Real output, Rust build:

```json
{"schema_version":"1.0","case_id":"ex-3","status":"ok","outputs":{"root":2.094551481542327},"diagnostics":{"iterations":6,"residual":3.552713678800501e-15,"termination":"X_TOL"}}
```

`quantforge operations` lists every operation. `specifications/cli-contract.md` has the full contract. `batch` takes one case per line.

## Regenerate golden files

See `oracle/README.md`. Never edit a golden file by hand, and never produce one from an implementation.

## Record public data

```bash
python tools/recorder/record.py
```

This downloads from three public sources and appends to `tools/forward-log/log.jsonl`, so run it only when you mean to add to the record. Nothing schedules it yet.

## Check the forward log

```bash
python tools/forward-log/forward_log.py verify
```

## Fuzz a CLI

```bash
python conformance/fuzz/fuzz_cli.py --impl rust --seconds 20 --seed 1
```

## Add a test case

Add it to a generator in `oracle/python/`, naming what verified it in `verified_by`, then regenerate. If it settles a silent point, add a line to `specifications/01-core/rulings.md`.
