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
TOTAL {'cases': 4731, 'pass': 4731, 'fail': 0, 'not_implemented': 0}
```

## More on the CLI

`quantforge operations` lists every operation. `specifications/cli-contract.md` has the full contract. `batch` takes one case per line.

## Regenerate golden files

See `oracle/README.md`. Never edit a golden file by hand, and never produce one from an implementation.

## Add a test case

Add it to a generator in `oracle/python/`, naming what verified it in `verified_by`, then regenerate. If it settles a silent point, add a line to `specifications/01-core/rulings.md`, or `specifications/stage-b-rulings.md` for stage B. Stage B generators are `gen_stage_b.py` and `gen_stage_b_deep.py`.

## Stage A recipes

Foundation. Passing here is self-assessment, on constructed inputs. Limits are in the [Roadmap](ROADMAP.md#stage-status).

### Run a stage A suite

```bash
python conformance/runner/runner.py --impl rust --suite daycount
```

Last line from 2026-11-06:

```
TOTAL {'cases': 1756, 'pass': 1756, 'fail': 0, 'not_implemented': 0}
```

### Send one case by hand

```bash
echo '{"schema_version":"1.0","case_id":"ex-3","operation":"core.root.brent","inputs":{"function":"cubic_wallis","a":2,"b":3}}' | rust/target/release/quantforge run
```

Real output, Rust build:

```json
{"schema_version":"1.0","case_id":"ex-3","status":"ok","outputs":{"root":2.094551481542327},"diagnostics":{"iterations":6,"residual":3.552713678800501e-15,"termination":"X_TOL"}}
```

### Record public data

```bash
python tools/recorder/record.py
```

This downloads from three public sources and appends to `tools/forward-log/log.jsonl`, so run it only when you mean to add to the record. Nothing schedules it yet.

### Check the forward log

```bash
python tools/forward-log/forward_log.py verify
```

### Fuzz a CLI

```bash
python conformance/fuzz/fuzz_cli.py --impl rust --seconds 20 --seed 1
```

## Stage B recipes

FX and rates slices, at Implemented, not Validated. All inputs are synthetic, and nothing is traded. Charts of the same curves are in the [Curves gallery](docs/curves/README.md).

### Run a stage B use case

```bash
rust/target/release/quantforge run < examples/usecase_fx_hedge.json
rust/target/release/quantforge run < examples/usecase_rates_hedge.json
python conformance/runner/runner.py --impl rust --suite usecases
```

The inputs are synthetic, and nothing is traded. `examples/README.md` has the real output.

### Build a curve

```bash
rust/target/release/quantforge run < examples/ois_bootstrap.json
```

Change `method` to `GLOBAL`, or `interpolation`, in a copy of the file. Check `max_repricing_error` in `diagnostics`.

### Build a SOFR curve

```bash
rust/target/release/quantforge run < examples/ois_bootstrap_sofr.json
```

Real output, Rust build, 2026-11-06, first pillar only:

```json
{"schema_version":"1.0","case_id":"example-ois-sofr","status":"ok","outputs":{"pillars":[{"date":"2026-11-19","discount_factor":0.9986040008603396}, ...
```

### Price an FX forward

```bash
rust/target/release/quantforge run < examples/fx_forward_outright.json
```

Real output, Rust build, 2026-11-06, on synthetic curves and spot:

```json
{"schema_version":"1.0","case_id":"example-fx-forward","status":"ok","outputs":{"forward":1.2825461006120924,"points":25.461006120923724},"diagnostics":{}}
```

### Run the stage B curve suites

```bash
python conformance/runner/runner.py --impl rust --suite ois
python conformance/runner/runner.py --impl rust --suite projection
python conformance/runner/runner.py --impl rust --suite fx
```

These gave 32, 6 and 14 cases on 2026-11-06, all passing. The first ended:

```
TOTAL {'cases': 32, 'pass': 32, 'fail': 0, 'not_implemented': 0}
```

### Rebuild the Curves gallery

```bash
python tools/build_gallery.py --check
```

This reruns the Python CLI against the committed [gallery](docs/curves/README.md). Real last line, 2026-11-06: `4 curves checked against the Python CLI; 0 differences`. Without `--check` it needs all four CLIs: see the [guide](docs/developer-guides/curves-gallery.md).
