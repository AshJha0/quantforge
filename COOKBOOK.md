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

## Stage C recipes

Equity vol slice, at Implemented, not Validated. All inputs are synthetic, and nothing is traded. Outputs below are real, from the Rust build on 2026-11-07. There are no stage C files in `examples/` yet, so these use golden-case inputs.

### Run the stage C suites

```bash
python conformance/runner/runner.py --impl rust --suite sabr_deep
```

Real last line, 2026-11-07:

```
TOTAL {'cases': 13, 'pass': 13, 'fail': 0, 'not_implemented': 0}
```

The 11 suites are `equity_forward`, `equity_forward_deep`, `black`, `black_deep`, `greeks`, `smile`, `surface`, `sabr`, `sabr_deep`, `strata_vol` and `usecases_c`: 446 cases.

### Equity forward, and the wrong form

```bash
echo '{"schema_version":"1.0","case_id":"f","operation":"eq.forward.flat",
 "inputs":{"spot":100,"rate":0.04,"borrow":0.05,"expiry_years":1,
 "dividends":[{"time_years":0.5,"amount":2}]}}' | tr -d '\n' |
 rust/target/release/quantforge run
```

Output: `"forward":97.01495841653144`. The wrong form, `(S - PV_r(D)) e^{(r-b)T}`, would give 97.0640923.

### Price, then solve the vol back

```bash
echo '{"schema_version":"1.0","case_id":"b","operation":"vol.option.price",
 "inputs":{"model":"BLACK_76","option_type":"CALL","strike":100,
 "expiry_years":1,"forward":100,"discount_factor":0.9704455335485082,
 "vol":0.2}}' | tr -d '\n' | rust/target/release/quantforge run
```

Output: `"price":7.730149359277918`. Send the same inputs to `vol.option.implied` with `"price":7.730149359277918` in place of `vol`, and it returns `"vol":0.20000000000000007`. Set `model` to `BACHELIER` and `vol` to 20 for 7.743035083184538.

### Greeks

```bash
echo '{"schema_version":"1.0","case_id":"g","operation":"risk.vol.greeks",
 "inputs":{"model":"BLACK_SCHOLES","option_type":"CALL","strike":100,
 "expiry_years":1,"spot":100,"rate":0.03,"yield":0.01,"vol":0.2}}' |
 tr -d '\n' | rust/target/release/quantforge run
```

Output: delta 0.5734959790277754, gamma 0.01935758770796135, vega 38.715175415922694, theta -4.753689862887256, rho 48.5222766774254.

### See Hagan SABR go negative

```bash
echo '{"schema_version":"1.0","case_id":"s","operation":"vol.sabr.density",
 "inputs":{"forward":0.02,"strikes":[0.0005,0.002,0.008,0.02,0.05],
 "expiry_years":20,"alpha":0.03,"beta":0.5,"rho":-0.3,"nu":0.5,
 "h_strike":0.0002,"on_negative":"REPORT"}}' | tr -d '\n' |
 rust/target/release/quantforge run
```

On the nine strikes of case `sabr-0013` the density at 0.0005 is -174.57449723243258, and `negative_density` is true. Change `on_negative` to `REJECT` to get `E_ARBITRAGE`. Use `vol.sabr.arbfree` for prices with a density that cannot go negative: see `specifications/05-volatility/sabr.md` for its grid inputs.

### Any stage C case by hand

The inputs of every case are in `datasets/golden/stage_c/*.json`. Wrap a case's `operation` and `inputs` in `{"schema_version":"1.0","case_id":"x",...}` and pipe it to the CLI. That is how the [Learn](LEARN.md#stage-c-equity-vol-slice) worked examples were made, including use case 3 (`usecases_c-0001`).

## Stage D recipes

Outputs below are the golden values of the named case; all four builds match them within tolerance. Recipes that need curves point to a case to copy the inputs from.

### Compound SOFR with a lookback

```bash
echo '{"schema_version":"1.0","case_id":"x","operation":"rates.ois.compound_dated",
 "inputs":{"convention":"SOFR","start":"2026-11-10","end":"2027-02-10",
 "method":"LOOKBACK","shift_days":2,"fixings":[...]}}' | tr -d '\n' | rust/target/release/quantforge run
```

Copy `fixings` from case `compound_d-0002`. Output: `compounded_rate` 0.04333939898551821. Methods: `NONE`, `LOOKBACK`, `OBSERVATION_SHIFT`, `LOCKOUT` (`specifications/02-curves/overnight-compounding.md`).

### Futures convexity

```bash
echo '{"schema_version":"1.0","case_id":"x","operation":"rates.futures.convexity",
 "inputs":{"price":96.0,"start_years":0.25,"end_years":0.5,
 "sigma":0.01,"mean_reversion":0.03}}' | tr -d '\n' | rust/target/release/quantforge run
```

Output (case `futures_d-0001`): `futures_rate` 0.04, `convexity` 9.33955888783533e-06, `forward_rate` 0.039990660441112165.

### Price a bond from its yield

```bash
echo '{"schema_version":"1.0","case_id":"x","operation":"bond.price.from_yield",
 "inputs":{"bond":{"maturity":"2029-11-15","coupon":0.0425,"frequency":2},
 "settlement":"2026-11-09","yield":0.041}}' | tr -d '\n' | rust/target/release/quantforge run
```

Output (case `bonds_d-0001`): clean 100.42085974293727, accrued 2.0557065217391304, modified duration 2.74949144731416. `bond.yield.from_price` goes back.

### Price a pass-through MBS

```bash
echo '{"schema_version":"1.0","case_id":"x","operation":"mbs.price",
 "inputs":{"pool":{"balance":1000000,"wac":0.065,"net_coupon":0.06,"wam":60,"age":0,
 "prepayment":{"model":"PSA","speed":150}},"yield":0.055,"delay_days":24}}' | tr -d '\n' | rust/target/release/quantforge run
```

Output (case `mbs_d-0004`): price 100.76748931062598, modified duration 2.3323199804373487, WAL 2.4872786417395525.

### Recipes that need curves

Copy the inputs of the named case from `datasets/golden/stage_d/`:

| Task | Operation | Case |
|---|---|---|
| ESTR OIS curve; with a year-end jump | `rates.ois.bootstrap` | `ois_d-0001`; `ois_d` cases tagged `turn-of-year` |
| Meeting-date step curve and fit | `rates.ois.step_curve`, `rates.ois.fit_steps` | `steps_d-0001`, `steps_d-0007` |
| IBOR fallback rate | `rates.fallback.rate` | `compound_d` cases tagged `fallback` |
| CSA discounting, OIS basis, joint bootstrap | `rates.csa.discount`, `rates.basis.ois_spread`, `rates.curve.joint_bootstrap` | `csa_d-0001`, `csa_d-0008`, `csa_d-0011` |
| Z-spread, asset swap, FRN, repo, CTD | `bond.*`, `repo.*` | `bonds_d`, `repo_d` |
| Cross-currency curve and NDF | `fx.xccy.*`, `fx.ndf.pv` | `xccy_d-0001`, `xccy_d-0002` |
| CDS price and hazard curve | `credit.*` | `credit_d-0004`, `credit_d-0001` |
| Implied dividends, TRS | `eq.*` | `equity_d-0001`, `trs_d-0001` |
| CPI curve, ZCIS, linkers | `infl.*` | `inflation_d-0001`, `inflation_d-0007` |
| Caps and swaptions | `rates.cap.price`, `rates.swaption.price` | `capswaption_d-0001`, `capswaption_d-0010` |
| Commodity curve and storage | `cmdty.*` | `commodity_d-0001`, `commodity_d-0007` |
