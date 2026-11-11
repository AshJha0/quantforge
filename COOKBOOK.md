# Cookbook

Short recipes. Commands run from the repository root, in Git Bash or a Unix shell. `python` means any Python 3.12 or later, because the neutral tools use only the standard library.

New here? [Tutorial 1](docs/getting-started/tutorial-1-swap.md) builds a curve, prices a swap and takes its DV01 in each language; the [tutorial series](docs/getting-started/README.md) goes on to bonds and repo, options, credit, risk, rates models and counterparty risk. `python tools/check_tutorial.py --lang rust` runs the blocks of every tutorial and checks the output.

## Run a tutorial script

Tutorials 2 to 16 each have a script in `examples/tutorials/` that sends its operations to any build: Python in process with no argument, or another build's CLI. Tutorial 1's script, `examples/tutorial_swap.py`, takes a build's CLI command.

```bash
uv run --project python python examples/tutorials/t2_bonds.py                  # Python
python examples/tutorials/t5_risk.py rust/target/release/quantforge            # Rust
python examples/tutorials/t6_hull_white.py java -jar java25/target/quantforge-cli.jar
python examples/tutorials/t7_counterparty.py cpp26/build/quantforge
python tools/check_tutorial.py --lang cpp --page docs/getting-started/tutorial-4-credit.md
```

Each recipe names its spec; the sources behind the spec are in its `## Sources` section and in [References](docs/references.md).

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

`--impl` takes `java`, `cpp`, `python` or `rust`. Add `--suite daycount` for one suite. The last line of a full Python run on the stage E merge, `597abf2`, 2026-11-08 (*observed*, Windows; the other three builds reported the same count):

```
TOTAL {'cases': 6817, 'pass': 6817, 'fail': 0, 'not_implemented': 0}
```

## More on the CLI

`quantforge operations` lists every operation. `specifications/cli-contract.md` has the full contract. `batch` takes one case per line; see [Batch mode](#batch-mode).

## Batch mode

`quantforge batch` reads one case document per line on stdin and writes one result line per input line, in order. Start-up is paid once for the whole stream, which matters on the JVM. The rules, BT1 to BT8, are in `specifications/cli-contract.md` (contract 1.6.0).

```bash
rust/target/release/quantforge batch < examples/batch.jsonl
```

Real output, Rust build:

```json
{"schema_version":"1.0","case_id":"example-daycount","status":"ok","outputs":{"year_fraction":0.5055555555555555},"diagnostics":{}}
{"schema_version":"1.0","case_id":"example-discount","status":"ok","outputs":{"discount_factor":0.9048374180359595},"diagnostics":{}}
{"schema_version":"1.0","case_id":"example-root","status":"ok","outputs":{"root":2.094551481542327},"diagnostics":{"iterations":6,"residual":3.552713678800501e-15,"termination":"X_TOL"}}
{"schema_version":"1.0","case_id":"example-error","status":"error","error":{"code":"E_DATE_ORDER","message":"end is before start"}}
```

The fourth case is an error, and the exit code is still 0: batch exits 0 when stdin ends, whatever each case returned (BT8). A bad line is never skipped. It gets its own `E_PARSE` result with `case_id: "unknown"` (BT3):

```bash
printf 'not json
' | rust/target/release/quantforge batch
```

```json
{"schema_version":"1.0","case_id":"unknown","status":"error","error":{"code":"E_PARSE","message":"bad literal"}}
```

The message text is not part of the contract and differs by language; the code is.

New in 1.6.0 (R1): `quantforge --batch` is the same command, and `--timings` on `batch`, `--batch` or `run` adds `diagnostics.elapsed_ns` to each result and changes nothing else. Check a build against the stream fixtures:

```bash
python conformance/runner/batch_check.py --impl rust
```

`--skip-run` leaves out the slow per-case `run` comparison. With `--impl python` the full check runs past five minutes on a Windows laptop, because each `run` call starts a fresh `uv` process; `--skip-run` passes in about a minute (*observed*, 2026-11-09).

## R2 risk recipes

All four builds pass these goldens (5,922 of 5,922 at the R2 merge). Each recipe sends golden cases through batch mode; the expected values are the oracle's, from `datasets/golden/r2/`. This shell function turns golden cases into batch input lines:

```bash
pick() { python -c "import json,sys; f,ids=sys.argv[1],sys.argv[2:]; [print(json.dumps({'schema_version':'1.0','case_id':c['case_id'],'operation':c['operation'],'inputs':c['inputs']})) for c in json.load(open(f))['cases'] if c['case_id'] in ids]" "$@"; }
```

### Par risk, `risk.curve.par`

```bash
pick datasets/golden/r2/risk_r2.json risk_r2-0001 | rust/target/release/quantforge --batch
```

Expected: `value` -24052.571714570924, `par_dv01` -4806.9447178779665, 2Y bucket -4808.126944588765. Rust CLI output (2026-11-08, `r2`): status `ok`, `value` -24052.571714571273, `par_dv01` -4806.94471788022, 2Y bucket -4808.126944588765, within the case's tolerance class.

### Key-rate risk, `risk.curve.key_rate`

```bash
pick datasets/golden/r2/risk_r2.json risk_r2-0002 risk_r2-0004 | rust/target/release/quantforge --batch
```

`risk_r2-0002` is `TRIANGULAR` with key dates on the pillars; `-0004` is `PILLAR` (`key_dates: null`). Both give `zero_dv01` -4913.216280838518; the 2Y bucket is -4802.5944942185415 and -4828.703749426391. Rust CLI output (2026-11-08): both `ok`, `zero_dv01` -4913.216280838518, 2Y buckets -4802.5944942185415 and -4828.703749426391.

### Jacobian, `risk.curve.jacobian`

```bash
pick datasets/golden/r2/risk_r2.json risk_r2-0031 | rust/target/release/quantforge --batch
```

Expected: 13 pillar dates, their zero rates, and a lower-triangular 13 by 13 matrix whose first entry is 1.0131265112373748. Rust CLI output (2026-11-08): `ok`, 13 pillars from 2026-11-19, first entry 1.0131265111749248 (6e-11 away, inside the Jacobian tolerance).

### P&L explain, `risk.pnl.explain`

```bash
pick datasets/golden/r2/pnl_r2.json pnl_r2-0001 pnl_r2-0011 | rust/target/release/quantforge --batch
```

Expected: `pnl_r2-0001` explained (unexplained 0.7134295024516177, threshold 240.71713873755908); `pnl_r2-0011` not (unexplained -91509.0298994584, threshold 63158.45945421277). Rust CLI output (2026-11-08): `pnl_r2-0001` explained, unexplained 0.713429492531759, threshold 240.71713873782616; `pnl_r2-0011` not explained, unexplained -91509.0299005867, threshold 63158.4594542317.

Over real daily moves, once a build passes the goldens:

```bash
python tools/workflows/pnl_explain.py --impl rust --years 2025
```

Check a build with `python conformance/runner/runner.py --impl rust --suite risk_r2`, and `--suite pnl_r2`.

## Run the daily workflows

Workflow (a) builds end-of-day curves and checks them against wide sanity bands; workflow (c) recomputes the NY Fed SOFR averages and checks the LIBOR fallback. Both send every case to one `quantforge --batch` process. Both fetch public data, so they need a network connection, or `--data DIR` to read saved files.

```bash
python tools/workflows/eod_curves.py --help
python tools/workflows/sofr_check.py --help
```

Each run writes `reports/workflows/<as-of>/`. The USD curve in (a) is a proxy: Treasury par yields are not SOFR swap rates. GBP results are pass or fail only, because the Bank of England curves may not be redistributed. Details and the first runs are in [r1-infra.md](docs/developer-guides/r1-infra.md#daily-workflows-a-and-c).

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

This downloads from the 15 public sources in `tools/recorder/sources.json` and appends to `tools/forward-log/log.jsonl`, so run it only when you mean to add to the record. From R1 the scheduled copy runs on GitHub Actions twice each weekday and writes to branch `forward-log` ([recorder-actions.md](docs/developer-guides/recorder-actions.md)). Its first run happens after the R1 push.

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

Output (case `bonds_d-0001`): clean 100.42085974293727, accrued 2.0557065217391304, modified duration 2.7494914473141594. `bond.yield.from_price` goes back.

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

## Stage E recipes

Slices E1, E2, E3 and E5. Copy the inputs of the named case from `datasets/golden/stage_e/`:

| Task | Operation | Case |
|---|---|---|
| Check an SVI surface for arbitrage; reject it | `vol.svi.surface_check` | `surf_e-0001` (clean), `surf_e-0007`, `surf_e-0008` (reject) |
| SSVI slice to raw SVI | `vol.ssvi.to_svi` | `surf_e-0018` |
| Fit SVI slices to a surface of quotes | `vol.svi.fit_surface` | `surf_e-0024` |
| Local vol from SVI slices | `vol.local.dupire` | `lv_e-0001` |
| Forward vol between expiries | `vol.forward.vol` | `lv_e-0007` |
| Reprice a smile after a spot move, sticky strike or sticky delta | `vol.smile.dynamics` | `lv_e-0018`, `lv_e-0020` |
| Vol of vol from a vol history | `vol.volofvol.measure` | `lv_e-0033` |
| FX vanilla price and Greeks | `fx.option.price` | `fxs_e-0001` |
| FX strike from a delta quote; ATM strike; RR/BF to strikes | `fx.delta.to_strike`, `fx.atm.strike`, `fx.smile.from_quotes` | `fxs_e` cases tagged `forward_pa`; tagged `atm`; `fxs_e-0120` |
| Heston, Bates, Merton prices | `vol.heston.price`, `vol.bates.price`, `vol.merton.price` | `heston_e-0001`; `heston_e` cases tagged `bates`, `merton` |
| SLV leverage function | `vol.slv.leverage` | `slv_e-0001` |
| Barrier, digital, Asian, lookback, quanto, chooser, spread, basket | `exotic.*` | `exotic_e` cases by tag |
| American put: tree, BAW, FD | `exotic.american.crr`, `.baw`, `.fd` | `american_e-0002`; `american_e` cases tagged `baw`, `fd` |


Slices E4, E6, E7 and E8. The outputs quoted are the golden values (`datasets/golden/stage_e_b/`), which all four builds reproduce. Replace the binary with any build's CLI. On Windows without a Rust build, `python/.venv/Scripts/quantforge.exe run` (after `uv sync`) gives the same values to within the last two or three digits, inside each case's tolerance (*observed*, 2026-11-09, all eight recipes below).

#### GARCH likelihood by hand

```bash
echo '{"schema_version":"1.0","case_id":"x","operation":"vol.garch.loglik",
 "inputs":{"returns":[0.01,-0.02],"omega":1e-5,"alpha":0.1,"beta":0.8,"initial_variance":"SAMPLE"}}' | tr -d '\n' | rust/target/release/quantforge run
```

Expected (case `garch_e-0009`): `loglik` 5.410998350356715, `variances` [0.00025, 0.00022], `next_variance` 0.000226. Worked in `specifications/05-volatility/garch.md`.

#### A VIX term from five strikes

```bash
echo '{"schema_version":"1.0","case_id":"x","operation":"vol.vix.term_variance",
 "inputs":{"minutes_to_expiry":43200,"rate":0.0,"strip":[
 {"strike":90,"call_bid":10.5,"call_ask":11.5,"put_bid":0.5,"put_ask":0.7},
 {"strike":95,"call_bid":6.0,"call_ask":6.6,"put_bid":1.4,"put_ask":1.6},
 {"strike":100,"call_bid":2.9,"call_ask":3.1,"put_bid":2.9,"put_ask":3.3},
 {"strike":105,"call_bid":1.0,"call_ask":1.2,"put_bid":5.8,"put_ask":6.6},
 {"strike":110,"call_bid":0.3,"call_ask":0.5,"put_bid":10.0,"put_ask":11.0}]}}' | tr -d '\n' | rust/target/release/quantforge run
```

Expected (case `vix_e-0001`): `forward` 99.9, `k0` 95, `variance` 0.08188158767696967. Set `call_bid` at 100 to 0 and the forward moves to 98.45 (case `vix_e-0018`): a zero bid still counts when choosing the forward, but that call drops out of the sum.

#### Implied correlation

```bash
echo '{"schema_version":"1.0","case_id":"x","operation":"risk.corr.implied",
 "inputs":{"weights":[0.5,0.5],"vols":[0.2,0.3],"index_vol":0.22}}' | tr -d '\n' | rust/target/release/quantforge run
```

Expected (case `corr_e-0036`): `correlation` 0.53.

#### Repair Higham's matrix

```bash
echo '{"schema_version":"1.0","case_id":"x","operation":"risk.corr.nearest",
 "inputs":{"matrix":[[1,1,0],[1,1,1],[0,1,1]]}}' | tr -d '\n' | rust/target/release/quantforge run
```

Expected (case `corr_e-0002`): off-diagonals 0.76069 and 0.15730, unit diagonal, within 2e-5 per entry.

#### Joint default under two copulas

```bash
echo '{"schema_version":"1.0","case_id":"x","operation":"credit.copula.joint_default",
 "inputs":{"copula":"STUDENT_T","default_probabilities":[0.02,0.03],"correlation":0.3,"degrees_of_freedom":4}}' | tr -d '\n' | rust/target/release/quantforge run
```

Expected (case `creditopt_e-0151`): `joint_default_probability` 0.005101673899339225. With `"copula":"GAUSSIAN"` and no `degrees_of_freedom` (case `creditopt_e-0147`): 0.0022875610978654965.

#### An equity tranche in the large pool

```bash
echo '{"schema_version":"1.0","case_id":"x","operation":"credit.lhp.tranche_loss",
 "inputs":{"default_probability":0.05,"correlation":0.3,"recovery":0.4,"attachment":0,"detachment":0.03}}' | tr -d '\n' | rust/target/release/quantforge run
```

Expected (case `creditopt_e-0161`): `expected_loss_fraction` 0.5410575024827762.

#### A CDS option

```bash
echo '{"schema_version":"1.0","case_id":"x","operation":"credit.cdsoption.price",
 "inputs":{"as_of":"2026-11-06","expiry":"2027-03-20","maturity":"2032-03-20","rate":0.035,"hazard_rate":0.02,
 "recovery":0.4,"type":"PAYER","strike":0.012,"notional":1e7,"vol":0.5,"knock_out":true}}' | tr -d '\n' | rust/target/release/quantforge run
```

Expected (case `creditopt_e-0001`): `price` 59847.84260792966, `forward_spread` 0.011887730437307897, `risky_annuity` 4.328652217279409, `front_end_protection` 43333.06144966937.

#### A zero-coupon inflation floor at 0%

```bash
echo '{"schema_version":"1.0","case_id":"x","operation":"infl.cap.zc_price",
 "inputs":{"model":"BLACK_76","type":"FLOOR","forward_index_ratio":1.1268,"years":5.0,"strike":0.0,
 "discount_factor":0.8305,"vol":0.028,"notional":1e7}}' | tr -d '\n' | rust/target/release/quantforge run
```

Expected (case `ratesvol_e-0081`): `price` 5993.010165883334, `strike_ratio` 1.0: deflation protection over five years.

#### Recipes that need curves or long arrays

The swaption cube, caplet strip, variance swap and GARCH fit take stage D curves or hundreds of numbers. Copy the `inputs` of `ratesvol_e-0001`, `ratesvol_e-0049`, `varswap_e-0001` or `garch_e-0027` from the golden file into a case document and run it the same way.

## Stage F recipes

Copy the inputs of the named case from `datasets/golden/stage_f/` and send them to any build that has the operation. Its `expected.outputs` are the oracle's answer. All four builds reproduce them: each passed every stage F golden case on the merged part 2 tree (2026-11-10, observed). For one curve under five interpolation methods, drawn from real runs of the four CLIs, see the [gallery page](docs/curves/interpolation-methods.md).

| Task | Operation | Case |
|---|---|---|
| Fill a curve with monotone convex, monotonic log cubic, tension spline or hybrid | `rates.curve.inspect`, `rates.ois.bootstrap` | `curve_f` cases by `interpolation` |
| Solve SOFR, term, ESTR and EUR xccy curves together, with a year-end turn and the full Jacobian | `rates.curve.joint_solve` | `joint_f-0001` |
| Meeting-date steps fitted to SR3 futures after convexity | `rates.curve.joint_solve` | `joint_f-0002` |
| Funding curve as a spread over OIS | `rates.funding.curve` | `joint_f` cases tagged `funding` |
| Par-quote risk and zero Jacobian of a 500-swap book (AAD in Rust) | `risk.book.ois_sensitivity` | `risk_f3-0001` |
| Principal components of curve moves | `risk.curve.pca` | `risk_f3` cases tagged `pca` |
| Cross gamma on pillar zero rates | `risk.curve.cross_gamma` | `risk_f3` cases tagged `cross-gamma` |
| Jump to default | `risk.credit.jtd` | `risk_f3` cases tagged `jtd` |
| Historical, filtered historical, parametric and Monte Carlo VaR and ES | `risk.var.*` | `risk_f4-0001` (historical, 250 days at 99%), `risk_f4-0026` (parametric) |
| Kupiec, Christoffersen, Basel traffic light | `risk.backtest.*` | `risk_f4-0047`, `risk_f4` cases tagged `backtest` |
| FRTB-SA GIRR delta capital | `risk.frtb.girr_delta` | `frtb_f-0002` |
| Book lifecycle: trades, expiry, default, roll; end-of-day marks | `book.lifecycle.apply`, `book.marks.resolve` | `book_f-0001`, `book_f` cases tagged `marks` |
| Factor attribution (use case 4) | `usecase.factor_attribution` | `uc4_f-0002` |
| A CDS index option on the adjusted forward; GARCH with standard errors | `credit.cdsindex.option_price`, `vol.garch.estimate` | `cdsidx_f-0001`, `garch_f` |

To check a whole suite against a build: `python conformance/runner/runner.py --impl python --suite risk_f4` (any language name from `conformance/runner/implementations.json`).

## Stage G recipes

Copy the inputs of the named case from `datasets/golden/stage_g/` and send them to any build. Its `expected.outputs` are the oracle's answer; all four builds reproduce every stage G case on the integration tree (2026-11-11, observed).

| Task | Operation | Case |
|---|---|---|
| Vasicek, CIR or Hull-White bond price and bond option | `rates.shortrate.zcb`, `rates.shortrate.zcb_option` | `shortrate_g-0001` |
| European swaption on Hull-White (Jamshidian) | `rates.shortrate.swaption` | `swaption_g-0001` |
| G2++ bond and bond option | `rates.g2pp.zcb`, `rates.g2pp.zcb_option` | `g2pp_g` |
| Calibrate Hull-White sigma to a swaption strip | `rates.shortrate.hw_calibrate` | `hwcal_g` |
| Bermudan swaption, callable bond, cap or floor | `rates.shortrate.bermudan_swaption`, `rates.shortrate.callable_bond`, `rates.shortrate.capfloor` | `bermudan_g`, `callable_g`, `capfloor_g` |
| LMM caplets and Rebonato swaptions | `rates.lmm.capfloor`, `rates.lmm.swaption_rebonato` | `lmmcap_g`, `lmmswn_g` |
| Monte Carlo Greeks; model-reserve dispersion | `risk.mc.greeks`, `risk.model_reserve.dispersion` | `mcgreeks_g`, `reserve_g` |
| Expected exposure of a swap under Hull-White | `xva.exposure.swap_ee_hw` | `exposure_g-0001` |
| Collateralised exposure; CVA, DVA, FVA; SIMM-style IR delta; wrong-way CVA | `xva.exposure.collateralised`, `xva.adjustments.value`, `xva.simm.ir_delta`, `xva.wwr.cva_hw` | `collexp_g`, `xvaadj_g-0001`, `simm_g`, `wwr_g` |
| EE, ENE, PFE, EPE and CVA of a swap portfolio under Hull-White (checked against ORE) | `xva.exposure.portfolio_hw` | `expsim_g-0001` |
| Discretely monitored barrier (BGK shift) | `exotic.barrier.price` with `monitoring: DISCRETE` | `barrier_g` |

To check a whole suite: `python conformance/runner/runner.py --impl rust --suite xvaadj_g`.

