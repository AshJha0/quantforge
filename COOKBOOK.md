# Cookbook

Short recipes. Commands run from the repository root, in Git Bash or a Unix shell. `python` means any Python 3.12 or later, because the neutral tools use only the standard library.

New here? [Tutorial 1](docs/getting-started/tutorial-1-swap.md) builds a curve, prices a swap and takes its DV01 in each language; the [tutorial series](docs/getting-started/README.md) goes on to bonds and repo, options, credit, risk, rates models and counterparty risk. `python tools/check_tutorial.py --lang rust` runs the blocks of every tutorial and checks the output.

## Run a tutorial script

Tutorials 2 to 16 each have a script in `examples/tutorials/` that sends its operations to any build: Python in process with no argument, or another build's CLI. Tutorial 1's script, `examples/tutorial_swap.py`, takes a build's CLI command, and so do the hedging tutorials' scripts, `examples/tutorial_hedge_17.py` to `tutorial_hedge_21.py`, which send cases built from the `examples/hedge_*_i.json` inputs.

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


## Stage I recipes

Each file below is one case document copied verbatim from the named golden case, so its expected outputs are that case's `expected.outputs` in `datasets/golden/stage_i/` (`program/STAGE_I_HANDOVER.md`, follow-up note). Send it to a build's CLI, for example:

```bash
rust/target/release/quantforge run < examples/hedge_greeks_i.json
```

All four builds answer every stage I operation: each passed 14,935 of 14,935 golden cases (7,413 value-checked, 5,008 error, 1,257 invariance and 1,257 `any` base cases) on the integration tree (2026-11-11, observed). Each language has a smoke test that runs every file below through its CLI and checks `status: ok` and the golden values.

| Task | File | Operation | From golden |
|---|---|---|---|
| Neutralise delta, gamma and vega with the underlying and two options | `hedge_greeks_i.json` | `hedge.greeks.neutralise` | `hedgegreeks_i-0003` |
| Minimum-variance hedge ratio from two return series | `hedge_minvar_i.json` | `hedge.minvar.ratio` | `hedgemv_i-0006` |
| Equity-beta hedge with index futures (Hull's 30 contracts) | `hedge_beta_i.json` | `hedge.beta.futures` | `hedgebeta_i-0001` |
| Key-rate hedge with long-only bounds that bind | `hedge_qp_keyrate_i.json` | `hedge.qp.solve` | `hedgeqp_i-0009` |
| Duplicate instruments: `MIN_NORM` splits the position evenly | `hedge_qp_minnorm_i.json` | `hedge.qp.solve` | `hedgeqp_i-0018` |
| Whole lots where rounding the continuous answer is wrong | `hedge_integer_i.json` | `hedge.integer.solve` | `hedgeint_i-0010` |
| Residual risk and per-factor contributions of a partial hedge | `hedge_residual_i.json` | `hedge.residual.report` | `hedgeres_i-0002` |
| CS01 and jump-to-default hedge with a 3Y and a 10Y CDS | `hedge_credit_i.json` | `hedge.credit.cds` | `hedgecredit_i-0004` |
| Correlation and vega hedge of exchange options with vanillas | `hedge_correlation_i.json` | `hedge.correlation.neutralise` | `hedgecorr_i-0003` |
| Equity with the underlying, rates with two bonds, in one solve | `hedge_crossasset_i.json` | `hedge.crossasset.solve` | `hedgexa_i-0002` |
| A costly instrument is left out (`x = 0` exactly) | `hedge_cost_i.json` | `hedge.qp.solve` with costs | `hedgecost_i-0002` |
| Risk against cost, seven points of a spread-cost frontier | `hedge_frontier_i.json` | `hedge.frontier.solve` | `hedgefrontier_i-0001` |
| Short call, delta-hedged daily to expiry | `hedge_backtest_i.json` | `hedge.backtest.delta` | `hedgebt_i-0001` |
| Dollar offset, regression and variance reduction of a hedge | `hedge_effectiveness_i.json` | `hedge.effectiveness` | `hedgeeff_i-0001` |
| Best pair of instruments where greedy selection fails | `hedge_select_i.json` | `hedge.select.solve` | `hedgeselect_i-0009` |
| Implementation shortfall and slippage of a buy and a sell | `hedge_slippage_i.json` | `hedge.slippage.report` | `hedgeslip_i-0003` |

The frontier of `hedge_frontier_i.json`, and a sweep through the switch point of golden `hedgecost_i-0023`, are drawn from all four CLIs on the gallery page [Hedging against trading costs](docs/curves/hedging-costs.md).

The same backtest with costs: add `"half_spread"` to the inputs of `hedge_backtest_i.json` as in golden `hedgebtcost_i-0001`. To check a whole suite: `python conformance/runner/runner.py --impl python --suite hedgeqp_i`.

## Stage J recipes

Stage J wave 1 (target v0.9.0, not yet released) adds research tools; wave 2 recipes follow the wave 1 ones. Each file below copies the inputs of the named golden case verbatim, so its expected outputs are that case's `expected.outputs` in `datasets/golden/stage_j/`. All four builds pass every stage J case (15,315 of 15,315 in each language at contract 1.14.0, 2026-11-14). The outputs quoted here are from the Python build on 2026-11-14.

| Task | File | Operation | From golden |
|---|---|---|---|
| Backtest a position path with a two-bar lag and three kinds of cost | `research_backtest_j.json` | `research.backtest.run` | `backtest_j-0004` |
| Purged 3-fold split of ten overlapping labels | `research_purged_kfold_j.json` | `research.cv.purged_kfold` | `purgedcv_j-0002` |
| Label hidden regimes with a Viterbi path | `research_viterbi_j.json` | `research.regime.viterbi` | `regime_j-0001` |
| Deflated Sharpe ratio for a set of trials | `research_dsr_j.json` | `research.stats.dsr` | `rstats_j-0001` |
| Minimum detectable Sharpe for a sample length | `research_power_j.json` | `research.stats.power` | `rstats_j-0017` |
| Probability of backtest overfitting from a strategy matrix | `research_pbo_j.json` | `research.stats.pbo` | `rstats_j-0025` |
| Count CPCV splits and backtest paths | `research_cpcv_paths_j.json` | `research.cv.cpcv_paths` | `purgedcv_j-0017` |
| Probabilistic Sharpe ratio against a benchmark | `research_psr_j.json` | `research.stats.psr` | `rstats_j-0013` |

### Backtest with costs

Plain idea: you say what position you want at each bar; the backtester holds it `lag` bars later, charges for each change and adds up the P&L. Formally (`specifications/11-research/backtester.md`, rulings J-2 to J-6): the held position is `q_t = target_{t-lag}`, the trade is `q_t - q_{t-1}`, gross P&L is `q_{t-1} (p_t - p_{t-1})`, and the cost of a trade of size `d` at price `p` is `|d| p half_spread_bps / 10^4 + |d| commission_per_unit + fixed_per_trade`.

```bash
uv run --project python quantforge run < examples/research_backtest_j.json
```

Worked example. Prices start 100, 101, 99.5; the lag is 2, so the first target (1 unit) is held from bar 2 and bought at 99.5. Its cost is 99.5 x 5 / 10,000 + 0.01 + 1 = 1.05975, the third entry of `cost`. Over the 12 bars there are 9 trades, gross P&L 30.5, spread 1.03425, commission 0.2 and fixed cost 9.0, so `total_net` is 20.26575; `max_drawdown` is 1.18 and `turnover` 2,068.5.

### Purged k-fold split

Plain idea: when each label covers a span of time, a training row whose span overlaps the test fold leaks the answer, so it is dropped (purged), and an embargo can drop a few rows after the fold as well. Formally (`specifications/11-research/purged-cv.md`, rulings J-7 to J-9; López de Prado 2018, ch. 7): row `i` covers `[t0_i, t1_i]`; for a test fold with times from `min t0` to `max t1`, a training row is kept only if its span does not overlap that window and it is not in the embargo.

```bash
uv run --project python quantforge run < examples/research_purged_kfold_j.json
```

Worked example. Ten rows, row `i` covering `[i, i + 2]`, three folds, no embargo. The first test fold is rows 0 to 3, covering times 0 to 5. Rows 4 (`[4, 6]`) and 5 (`[5, 7]`) overlap it and are purged, so the training set is rows 6 to 9:

```json
{"folds":[{"test":[0,1,2,3],"train":[6,7,8,9]},{"test":[4,5,6],"train":[0,1,9]},{"test":[7,8,9],"train":[0,1,2,3,4]}],"embargo_count":0}
```

### Regime labels

Plain idea: given a model of how a market moves between a few hidden states and what each state looks like, find the single most likely sequence of states. Formally (`specifications/11-research/regimes.md`, rulings J-10 to J-12; Rabiner 1989): `delta_t(j) = max_i (delta_{t-1}(i) + log A_ij) + log e_t(j)` in logs, with back-pointers, ties to the lowest state. Give either an `emission` matrix (`T x K`) or `observations` with Gaussian `means` and `sds`.

```bash
uv run --project python quantforge run < examples/research_viterbi_j.json
```

Worked example. The textbook two-state model: Healthy (0) or Fever (1), observations normal, cold, dizzy. Output `"states":[0,0,1]` and `"log_probability":-4.19173690823075`, and `exp(-4.19174) = 0.01512 = 0.6 x 0.5 x 0.7 x 0.4 x 0.3 x 0.6`. The path is smoothed over the whole sample: never feed it to a signal at time `t`.

### Deflated Sharpe ratio for a trial set

Plain idea: the best of many strategies looks good by luck. The DSR is the probability that the true Sharpe beats what the best of `N` useless trials would show. Formally (`research-statistics.md`, J-13; Bailey and López de Prado 2014): `SR0 = sqrt(V) ((1 - gamma) Phi^{-1}(1 - 1/N) + gamma Phi^{-1}(1 - 1/(N e)))`, then the PSR against `SR0`. Sharpe ratios are per period; `sr_variance` is the variance of the trials' per-period Sharpe ratios; `kurtosis` is not excess.

```bash
uv run --project python quantforge run < examples/research_dsr_j.json
```

Worked example, the paper's: annual Sharpe 2.5 over 1,250 days (`sr` 2.5 / sqrt(250) = 0.15811), skew -3, kurtosis 10, 100 trials with `sr_variance` 0.5 / 250 = 0.002. Output `"sr0":0.11317200186513214`, `"dsr":0.9003968344493904`: the printed 0.1132 and 0.9004, not significant at 5 %. With `"n_trials":1000` the same run gives `sr0` 0.14557 and `dsr` 0.63991. Pass the trial count from `research/trials.csv`, never a smaller one.

### Minimum detectable Sharpe

Plain idea: a short sample cannot tell a modest Sharpe from zero. Formally (`research-statistics.md`; Lo 2002): `z_sum = Phi^{-1}(1 - alpha) + Phi^{-1}(power)`, `mds = z_sum / sqrt(years)` for an annual Sharpe, one-sided, iid. Add `sr_target` to get `years_required = (z_sum / sr_target)^2`.

```bash
uv run --project python quantforge run < examples/research_power_j.json
```

Worked example. 13.83 years at 5 % and 80 % power: `"z_sum":2.486474860524386` (1.6449 + 0.8416), `"mds":0.6686101767665223`, the 0.67 of the R3-01 preregistration. Serial correlation makes the true figure larger; the preregistrations report a simulated power beside it.

### PBO from a strategy matrix

Plain idea: split the history into blocks, pick the best strategy on half of them and see where it ranks on the other half; PBO is how often it lands in the bottom half. Formally (`research-statistics.md`, J-15 to J-17; Bailey, Borwein, López de Prado and Zhu 2017): `performance` is `T x N` (rows periods, columns strategies), `n_partitions` `S` is even and divides `T`; for each of `C(S, S/2)` splits the logit of the winner's relative test rank `r / (N + 1)`; PBO is the share of logits at or below zero.

```bash
uv run --project python quantforge run < examples/research_pbo_j.json
```

Worked example. Rows `[1, 0], [1, 0], [0, 2], [0, 2]`, two blocks, metric `MEAN`. Whichever block trains, its winner is last on the other: rank 1 of 2, `omega = 1/3`, logit `log(1/2)`. Output `"pbo":1.0`, `"logits":[-0.6931471805599454,-0.6931471805599454]`, `"n_combinations":2`. [Tutorial 24](docs/getting-started/tutorial-24-is-the-sharpe-real.md) works a three-strategy example by hand, and the gallery page [Research workflow](docs/curves/research-workflow.md) runs all of these on twelve rules.

### Count CPCV splits and paths

Plain idea: combinatorial purged cross-validation cuts the history into `N` groups and tests on every choice of `k` of them; the test groups recombine into several complete backtest paths, which gives a distribution of out-of-sample results instead of one. Formally (`specifications/11-research/purged-cv.md`; López de Prado 2018, section 12.4): `n_splits = C(N, k)`, and each group is tested in `C(N - 1, k - 1)` splits, so `n_paths = k/N C(N, k)`.

```bash
uv run --project python quantforge run < examples/research_cpcv_paths_j.json
```

Worked example. `N = 6`, `k = 2`: `C(6, 2) = 15` splits and `2/6 x 15 = 5` paths. Output `"n_splits":15,"n_paths":5`. [Tutorial 31](docs/getting-started/tutorial-31-leakage-and-purging.md) tabulates `N` = 6, 8, 10 against `k` = 1, 2, 3.

### Probabilistic Sharpe ratio

Plain idea: the probability that the true Sharpe ratio is above a benchmark, given how long the sample is and how skewed and fat-tailed the returns are. Formally (`research-statistics.md`, J-14; Bailey and López de Prado 2012): with `v = 1 - skew sr + (kurtosis - 1)/4 sr^2`, `z = (sr - sr_benchmark) sqrt(T - 1) / sqrt(v)` and `psr = Phi(z)`; `sr` per period, `kurtosis` not excess; `v <= 0` is `E_DOMAIN`.

```bash
uv run --project python quantforge run < examples/research_psr_j.json
```

Worked example. Daily Sharpe 0.1 over 500 days, skew -0.5, kurtosis 5, benchmark 0: `v = 1 + 0.05 + 0.01 = 1.06`, `z = 0.1 x sqrt(499) / sqrt(1.06) = 2.1697`. Output `"z":2.169688265583635,"psr":0.9849847651995092`. With skew 0 and kurtosis 3 the same Sharpe gives `z = 2.2283`: negative skew costs evidence. [Tutorial 30](docs/getting-started/tutorial-30-trials-and-power.md) shows PSR rising with sample length.

To check a whole suite: `python conformance/runner/runner.py --impl python --suite backtest_j` (or `purgedcv_j`, `regime_j`, `rstats_j`).

### Stage J wave 2: portfolio construction, estimation, ES backtest, Baum-Welch

Wave 2 adds seven operations (rulings J-W2-1 to J-W2-23 in `specifications/stage-j-rulings-w2.md`). All four builds implement them, at CLI contract 1.14.0 (merged to `main` in PR #40, unreleased, target v0.9.0). As above, each file copies the inputs of the named golden case verbatim, and the outputs quoted are from the Python build on 2026-11-14. [Tutorial 25](docs/getting-started/tutorial-25-build-and-stress-a-portfolio.md) and [Tutorial 26](docs/getting-started/tutorial-26-test-es-and-fit-regimes.md) work through them on hand-sized data.

| Task | File | Operation | From golden |
|---|---|---|---|
| Shrink a sample covariance matrix | `estimate_ledoit_wolf_j.json` | `research.estimate.ledoit_wolf` | `estim_j-0005` |
| Move prior returns towards a view | `estimate_black_litterman_j.json` | `research.estimate.black_litterman` | `estim_j-0013` |
| Mean-variance weights with bounds | `portfolio_mean_variance_j.json` | `research.portfolio.mean_variance` | `optim_j-0018` |
| Risk-parity weights with budgets | `portfolio_risk_parity_j.json` | `research.portfolio.risk_parity` | `optim_j-0030` |
| Split a portfolio's volatility by asset | `risk_contrib_euler_j.json` | `risk.contrib.euler` | `optim_j-0042` |
| Backtest an ES forecast | `risk_es_z2_j.json` | `risk.backtest.es_z2` | `esbt_j-0001` |
| Fit a Gaussian hidden Markov model | `research_baum_welch_j.json` | `research.regime.baum_welch` | `baumwelch_j-0002` |

### Shrink a covariance matrix

Plain idea: a sample covariance from a short history is noisy, so pull it towards a multiple of the identity, by an amount estimated from the same data. Formally (`specifications/07-portfolio/estimation.md`, ruling J-W2-7; Ledoit and Wolf 2004): with demeaned rows `x_t` and `S = (1/T) sum x_t x_t'`, `m = tr S / N`, `d^2 = ||S - m I||^2 / N`, `b^2 = min((1/T^2) sum_t ||x_t x_t' - S||^2 / N, d^2)`, `delta = b^2 / d^2`, and the output is `delta m I + (1 - delta) S`.

```bash
uv run --project python quantforge run < examples/estimate_ledoit_wolf_j.json
```

Worked example. 55 rows of 5 assets. Output `"shrinkage":0.8218538203751234` and `"mu":0.00030956198250274385`. The sample covariance of assets 1 and 2 (divisor 55) is 9.0666e-6; times `1 - delta = 0.17815` it is the output's 1.6152e-6. With 55 rows for 15 distinct entries the estimator keeps only 18 % of the sample.

### Black-Litterman posterior returns

Plain idea: start from prior expected returns and move them towards your views, by as much as the views' stated uncertainty allows against the prior's. Formally (`estimation.md`, J-W2-8; Black and Litterman 1992, He and Litterman 1999): `posterior = pi + tau Sigma P' (P tau Sigma P' + Omega)^-1 (q - P pi)`; `posterior_covariance` is the uncertainty of the mean, and `predictive_covariance = Sigma + posterior_covariance`.

```bash
uv run --project python quantforge run < examples/estimate_black_litterman_j.json
```

Worked example. Three assets, one view: minus asset 2 minus asset 3 (`P = [0, -1, -1]`) returns 0.037219, with `Omega = 0.001` and `tau = 0.025`. The prior says `P pi = -0.13245`, and the prior's variance of that combination is `tau P Sigma P' = 0.0033059`. The posterior is the precision-weighted average, `(0.001 x (-0.13245) + 0.0033059 x 0.037219) / 0.0043059 = -0.0021851`, and the output `"posterior_returns":[0.01704927512990971,0.013861721897407628,-0.011676651876796222]` gives `-(0.0138617 - 0.0116767) = -0.0021851`.

### Mean-variance with bounds

Plain idea: the weights that best trade expected return against variance, fully invested, each between a lower and an upper bound. Formally (`specifications/07-portfolio/optimisation.md`, J-W2-2 to J-W2-4; Markowitz 1952): maximise `mu'w - (gamma/2) w' Sigma w` with `sum w = 1` and `lower <= w <= upper`; `at_bound` is `-1`, `0` or `+1` per asset.

```bash
uv run --project python quantforge run < examples/portfolio_mean_variance_j.json
```

Worked example. Three assets, `gamma = 1`, each weight between 0 and 0.55. Output `"weights":[0.55,0.0,0.44999999999999996]`, `"at_bound":[1,-1,0]`, `"expected_return":0.05931675`, `"volatility":0.11535876646358524`. Asset 1 (expected return 0.0719) is capped, asset 2 (0.0051) is at zero, and asset 3 takes the remaining 0.45. Check: `0.55 x 0.07191 + 0.45 x 0.043925 = 0.05931675`.

### Risk parity with budgets

Plain idea: long-only weights such that each asset's share of the portfolio's risk equals its budget. Formally (`optimisation.md`, J-W2-5; Maillard, Roncalli and Teiletche 2010, Spinu 2013): `w_i (Sigma w)_i / (w' Sigma w) = b_i`, solved through `Sigma y = b / y`, `w = y / sum y`.

```bash
uv run --project python quantforge run < examples/portfolio_risk_parity_j.json
```

Worked example. Volatilities 20 % and 30 %, covariance 0.018 (correlation 0.3), budgets 70/30. Output `"weights":[0.7230564379018464,0.27694356209815363]`, `"volatility":0.18714718941762643`, `"contributions":[0.13100303259233914,0.05614415682528729]`. Shares: `0.131003 / 0.187147 = 0.7000` and `0.056144 / 0.187147 = 0.3000`. With equal budgets the weights would be `(0.6, 0.4)` for any correlation (`optim_j-0029`).

### Euler risk contributions

Plain idea: split a portfolio's volatility into one piece per asset so that the pieces add up exactly to the total. Formally (`optimisation.md`, J-W2-6; Tasche 1999): `sigma = sqrt(w' Sigma w)`, marginal `(Sigma w) / sigma`, contribution `w_i` times marginal, share contribution over `sigma`. Weights may be negative.

```bash
uv run --project python quantforge run < examples/risk_contrib_euler_j.json
```

Worked example. Long 1 of asset 1, short 0.5 of asset 2, the covariance of the previous recipe. `Sigma w = (0.04 - 0.009, 0.018 - 0.045) = (0.031, -0.027)`, `w' Sigma w = 0.031 + 0.0135 = 0.0445`, `sigma = 0.21095`. Output `"contributions":[0.14695409357339295,0.06399613752389692]`, adding up to 0.21095, and `"shares":[0.6966292134831461,0.3033707865168539]`. The short leg adds risk: its weight and its marginal are both negative, so its contribution is positive. It would reduce risk only if `(Sigma w)_2 = cov_12 - 0.045` were positive, which needs a correlation above `0.045 / (0.2 x 0.3) = 0.75`.

### Backtest an ES forecast with Z2

Plain idea: compare the size of the losses beyond VaR with the expected shortfall the model forecast for those days; 0 means right on average, negative means ES was too small. Formally (`specifications/06-risk/es-backtest.md`, J-W2-10; Acerbi and Szekely 2014): losses are positive, an exception is `L_t > VaR_t` (strict), and `Z2 = 1 - sum_t L_t 1{L_t > VaR_t} / (T alpha ES_t)`.

```bash
uv run --project python quantforge run < examples/risk_es_z2_j.json
```

Worked example. Losses 1, 3, 0.5, 4, VaR 2, ES 2.5, `alpha = 0.25`, so `T alpha = 1`. Exceptions at 3 and 4: `Z2 = 1 - (3 + 4) / 2.5 = -1.8`. Output `"z2":-1.7999999999999998`, `"exceptions":2`, `"expected_exceptions":1.0`: twice the expected count, and larger losses than the ES said.

### Fit a two-state regime model

Plain idea: estimate the parameters of a hidden Markov model (how sticky each state is, and the mean and spread of returns in each) from the returns alone, by EM. Formally (`specifications/11-research/baum-welch.md`, J-W2-9, J-W2-11 to J-W2-13; Rabiner 1989): a scaled forward-backward E-step, the M-step of the re-estimation formulas, and a stop after the first iteration whose log-likelihood gain is below `tolerance`, or after `max_iterations` with `converged` false.

```bash
uv run --project python quantforge run < examples/research_baum_welch_j.json
```

Worked example. 60 observations in blocks of 25, start means -0.5 and 1.5, standard deviations 1, tolerance 1.29e-7. Output: `"iterations":28`, `"converged":true`, `"log_likelihood":-97.04826936250689`, `"means":[-0.4071983679316511,2.7272604649142966]`, `"sds":[0.7495715574047682,1.3624331205819107]`, and staying probabilities 0.9329 and 0.8543 on the diagonal of `"transition"`. The first state's initial probability, `7.9e-28`, is its posterior given the whole series at the first observation, 1.498, which the model places in the second state. Pass the fitted parameters to `research.regime.viterbi` for labels, as Tutorial 26 does.

To check a whole suite: `python conformance/runner/runner.py --impl python --suite optim_j` (or `estim_j`, `esbt_j`, `baumwelch_j`).

### Stage J research questions, one recipe each

These recipes answer a question with several calls rather than one, so each points at the tutorial script that does it; every script runs on any build (`python examples/tutorials/<script> rust/target/release/quantforge`, or the Java or C++ command line) and prints the same lines. The numbers are those scripts' printed output (2026-11-15, all four builds).

| Question | Script | Operations | Tutorial |
|---|---|---|---|
| At what spread does my backtest earn nothing? | `t27_costs.py` | `research.backtest.run` | [27](docs/getting-started/tutorial-27-what-costs-do-to-a-backtest.md) |
| What does a long-only rule cost me? | `t28_frontier.py` | `research.portfolio.mean_variance`, `risk.contrib.euler` | [28](docs/getting-started/tutorial-28-efficient-frontier.md) |
| How strong should my view be? | `t29_view_confidence.py` | `research.estimate.black_litterman` | [29](docs/getting-started/tutorial-29-view-confidence.md) |
| How many trials can my Sharpe survive, and how long must I wait? | `t30_trials_and_power.py` | `research.stats.dsr`, `.psr`, `.power` | [30](docs/getting-started/tutorial-30-trials-and-power.md) |
| How much training data does purging cost? | `t31_purging.py` | `research.cv.purged_kfold`, `research.cv.cpcv_paths` | [31](docs/getting-started/tutorial-31-leakage-and-purging.md) |
| Does shrinkage help at my sample length? | `t32_shrinkage_and_length.py` | `research.estimate.ledoit_wolf`, `research.portfolio.risk_parity` | [32](docs/getting-started/tutorial-32-shrinkage-and-sample-length.md) |

#### Break-even half spread

Plain idea: spread cost grows in a straight line with the half spread, so the half spread at which net P&L is zero follows from one costless run. Formally (`backtester.md`): `total_spread_cost = turnover x half_spread_bps / 10^4`, so `b* = (total_gross - total_commission - total_fixed_cost) / (turnover x 10^-4)`, read from a run with `half_spread_bps` 0. Worked example (Tutorial 27): gross 461.73, commission 9.30, turnover 93,055.8 give `b* = 48.62` bp, and a run at that half spread prints net 0.000000.

#### Price a constraint in return

Plain idea: run mean-variance with and without the constraint at the same risk aversion and compare certainty-equivalent returns `mu'w - (gamma/2) sigma^2`. Worked example (Tutorial 28): at `gamma = 1`, free 0.0823 and long-only 0.0627, so the rule costs 195.5 bp a year; at `gamma = 5` neither portfolio holds a short and the cost is zero.

#### Choose a view's variance from a confidence

Plain idea: for one view, the posterior moves a fraction `c = tau P Sigma P' / (tau P Sigma P' + Omega)` of the way from the prior to the view, so choose `c` and set `Omega = tau P Sigma P' (1 - c) / c`. Worked example (Tutorial 29): `tau P Sigma P' = 0.0019`; `Omega = 0.0019` gives `c = 1/2` and a posterior spread of 0.0590, half-way from 0.038 to 0.08. Only `Omega / tau` affects the posterior mean.

#### Years needed to detect a Sharpe ratio

Plain idea: `years_required = (z_sum / SR)^2`, with `z_sum = 2.4865` at 5 % and 80 % power. Send `{"years": 1, "sr_target": 1.0}` to `research.stats.power`: 6.18 years for an annual Sharpe of 1, 24.73 for 0.5 (Tutorial 30).

<!-- TODO(stage J wave 3): wave 3 recipes (shock library, held-out-strike and leave-one-out backtests, A3 drift) go here; the wave 3 lane writes them. -->

### Stage J curves lane: financing term structure and liquidity curve

Three operations (rulings J-C-1 to J-C-9 in `specifications/stage-j-rulings-curves.md`, contract 1.15.0), in all four builds. Outputs quoted are from the Python build on 2026-11-15. [Tutorial 34](docs/getting-started/tutorial-34-financing-term-structure.md) and [Tutorial 35](docs/getting-started/tutorial-35-liquidity-curve.md) work through them.

### Build a term repo and borrow curve

Plain idea: each term repo quote fixes one point of the financing spread over the funding curve; borrow quotes do the same for the stock-loan fee. Formally (`specifications/02-curves/financing-term-structure.md`, J-C-2 to J-C-4): `S(T_i) = ln(1 + R_i T_i) - Z(T_i) T_i`, linear between pillars, no extrapolation.

```bash
uv run --project python quantforge run < examples/repo_term_curve_j.json
```

Worked example. Four repo quotes 4.25 % to 4.40 % at 1, 3, 6 and 12 months over a funding curve of 4.0 % to 4.2 %: `"pillar_spreads"` 24.25, 27.71, 20.34 and 15.59 bp; at 0.5 years `"financing_rate"` 0.0435, the quote. With one flat quote and one flat fee the curve reproduces ruling D22.

### Price an equity forward on term financing

Plain idea: the forward is spot carried on secured financing, less the borrow fee, less dividends carried the same way. Formally (J-C-5): `F = (S_0 - sum_{0 < t_i <= T} A_i C(t_i)) / C(T)`, `C(t) = exp(-Z(t) t - S(t) + B(t))`.

```bash
uv run --project python quantforge run < examples/eq_forward_term_financed_j.json
```

Worked example. Spot 50, nine months, dividends 0.3 and 0.35 inside the horizon (0.4 at 0.9 years is not): `"forward"` 50.793899, `"pv_dividends"` 0.643404.

### Read a liquidity cost curve

Plain idea: half spread plus square-root impact plus timing risk, by size and horizon, and the cheapest horizon per size. Formally (`specifications/10-execution/liquidity-curve.md`, J-C-6 to J-C-8): `c(Q, h) = s + Y sigma (Q/(V h))^delta + z sigma sqrt(h/3)`.

```bash
uv run --project python quantforge run < examples/liq_curve_cost_j.json
```

Worked example. 5 bp half spread, `sigma` 2 %, `V` 10 million, `z = 1.645`: for 1,000,000 shares `"optimal_horizon"` 0.3330 days and `"min_cost"` 0.0224 (224 bp). Parameters are assumed, not calibrated.

To check the suites: `python conformance/runner/runner.py --impl python --suite termfin_j` (or `liqcurve_j`).
