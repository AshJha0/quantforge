# Cookbook

Short recipes. Commands run from the repository root, in Git Bash or a Unix shell. `python` means any Python 3.12 or later, because the neutral tools use only the standard library.

New here? [Tutorial 1](docs/getting-started/tutorial-1-swap.md) builds a curve, prices a swap and takes its DV01 in each language; the [tutorial series](docs/getting-started/README.md) goes on to bonds and repo, options, credit, risk, rates models and counterparty risk. `python tools/check_tutorial.py --lang rust` runs the blocks of every tutorial and checks the output.

## Recipes by domain

The sections below follow the order in which stages were built. To find recipes by subject, use the twelve domains of `specifications/` (01 to 12):

| Domain | Recipes |
|---|---|
| 01 Foundation | [Stage A](#stage-a-recipes), [Batch mode](#batch-mode) |
| 02 Curves | [Stage B](#stage-b-recipes), [Stage D](#stage-d-recipes), [Stage F](#stage-f-recipes), [financing term structure](#stage-j-curves-lane-financing-term-structure-and-liquidity-curve) |
| 03 Calibration | [Build a curve](#build-a-curve), [Stage F](#stage-f-recipes) (joint solve), [Stage G](#stage-g-recipes) (Hull-White calibration) |
| 04 Pricing | [Stage B](#stage-b-recipes), [Stage D](#stage-d-recipes), [Stage E](#stage-e-recipes), [Stage G](#stage-g-recipes) |
| 05 Volatility | [Stage C](#stage-c-recipes), [Stage E](#stage-e-recipes) |
| 06 Risk and xVA | [stage K](#stage-k-recipes) (intraday bounds, SA-CCR, backtesting zones, K-8 ladder; [desk recipes](#stage-k-desk-recipes); [wave 2 capital and xVA](#stage-k-wave-2-capital-and-xva-recipes): RRAO, securitisation and CTP DRC, RFET, SA-CVA, large exposures, wrong-way CVA), [R2 risk](#r2-risk-recipes), [Stage F](#stage-f-recipes), [Stage G](#stage-g-recipes), [stress scenarios and drift](#stage-j-wave-3-stress-scenarios-interpolation-backtests-drift-detectors) |
| 07 Portfolio | [Stage F](#stage-f-recipes) (book), [portfolio construction](#stage-j-wave-2-portfolio-construction-estimation-es-backtest-baum-welch) |
| 08 Hedging | [Stage I](#stage-i-recipes) |
| 09 Microstructure | [Stage H](#stage-h-recipes-available-from-v0100) (book rebuild, quotes, estimators), [trading conventions](#stage-h-multi-asset-recipes-equities-fx-rates-and-their-simulated-venues) |
| 10 Execution | [Stage H](#stage-h-recipes-available-from-v0100) (schedules, TCA, simulated venues, paper trading), [simulated auction, FX and futures venues](#stage-h-multi-asset-recipes-equities-fx-rates-and-their-simulated-venues), [liquidity curve](#read-a-liquidity-cost-curve) |
| 11 Research | [Stage J](#stage-j-recipes) |
| 12 Platform | [Stage K](#stage-k-recipes) (bitemporal store, daily paper ledger, scheduled on main since 2026-11-20), [platform recipes](#stage-k-platform-recipes-simulated-feeds-end-of-day-rehearsal-soak-and-snapshots) (simulated feed fixtures, end-of-day rehearsal, soak verdict) |

## Check the recipes

A recipe whose bash block is marked `<!-- cookbook:run -->` carries a hidden `<!-- cookbook:expect -->` list of strings its output must contain. `python tools/check_cookbook.py` runs every marked block from the repository root and fails if a string is missing or a command fails; `--list` names them and `--only TEXT` runs the recipes whose heading contains `TEXT`. It sends `quantforge` lines to `python -m quantforge_core.cli.main`, the same entry point. Its tests: `python tools/test_check_cookbook.py`. Not run by any workflow yet.

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

FX and rates slices. All inputs are synthetic, and nothing is traded. Charts of the same curves are in the [Curves gallery](docs/curves/README.md).

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

Equity vol slice. All inputs are synthetic, and nothing is traded. Outputs below are real, from the Rust build on 2026-11-07. There are no stage C files in `examples/` yet, so these use golden-case inputs.

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
| Collateralised exposure; CVA, DVA, FVA; sensitivity-based IR delta margin (placeholder weights); wrong-way CVA | `xva.exposure.collateralised`, `xva.adjustments.value`, `xva.sbim.ir_delta`, `xva.wwr.cva_hw` | `collexp_g`, `xvaadj_g-0001`, `sbim_g`, `wwr_g` |
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

Stage J wave 1 (released in v0.9.0) adds research tools; wave 2 recipes follow the wave 1 ones. Each file below copies the inputs of the named golden case verbatim, so its expected outputs are that case's `expected.outputs` in `datasets/golden/stage_j/`. All four builds pass every stage J case (15,514 of 15,514 in each language at contract 1.15.0, 2026-11-15). The outputs quoted here are from the Python build on 2026-11-14.

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

Wave 2 adds seven operations (rulings J-W2-1 to J-W2-23 in `specifications/stage-j-rulings-w2.md`). All four builds implement them, at CLI contract 1.14.0 (merged in PR #40, released in v0.9.0). As above, each file copies the inputs of the named golden case verbatim, and the outputs quoted are from the Python build on 2026-11-14. [Tutorial 25](docs/getting-started/tutorial-25-build-and-stress-a-portfolio.md) and [Tutorial 26](docs/getting-started/tutorial-26-test-es-and-fit-regimes.md) work through them on hand-sized data.

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

### Stage J wave 3: stress scenarios, interpolation backtests, drift detectors

Tutorial 33 runs all eight operations together; the recipes below are one call each.

### Replay a curve shock on a book

Plain idea: move each tenor of today's curve by the shock, interpolated onto the book's tenors, and price the move with DV01s. Formally (`specifications/06-risk/scenario-stress.md`, J-W3-4, J-W3-5): `applied_bp = scale x` linear interpolation of the shock in tenor, flat outside the shock's tenors; `shocked = yield + applied_bp / 100`; `pnl = -sum dv01 x applied_bp`.

```bash
uv run --project python quantforge run < examples/risk_scenario_replay_j.json
```

Worked example. Shock 10, 50, 20 bp at 1Y, 5Y, 30Y; the 2Y point is a quarter of the way from 1Y to 5Y, so `10 + 0.25 x 40 = 20` bp; the 10Y point is a fifth of the way from 5Y to 30Y, `50 - 0.2 x 30 = 44` bp. Output `"applied_bp":[20.0,44.0]`, `"shocked_yields":[4.2,4.640000000000001]`, and with DV01s 1,000 and 2,000 per bp `"pnl":-108000.0`. For a real crisis, take `shock_tenors` and `shift_bp` from `datasets/scenarios/us_treasury_shocks.json`, or measure them with `risk.scenario.historical_shock`.

### Leave one knot out

Plain idea: hide each inner knot, rebuild with the same method, and record the miss. Formally (`specifications/11-research/interp-backtest.md`, J-W3-8): `e_i = f_{-i}(x_i) - y_i` for each inner `i`, with the max absolute error and the RMSE.

```bash
uv run --project python quantforge run < examples/research_interp_loo_j.json
```

Worked example. Knots `(1, 3.0), (2, 3.4), (3, 3.6), (5, 4.0)`, `linear`. Hiding 2 rebuilds `3.0 + 0.5 x 0.6 = 3.3`, error -0.1; hiding 3 rebuilds `3.4 + 0.6 / 3 = 3.6`, error 0. Output `"errors":[-0.10000000000000009,0.0]`, `"max_abs_error":0.10000000000000009`, `"rmse":0.07071067811865482`. For an option smile use `research.backtest.surface_holdout`, which interpolates total variance across strike.

### Detect a mean shift with CUSUM

Plain idea: add up how far each value sits above (and below) the in-control mean, less an allowance `k`, and alarm when the running total passes `h`. Formally (`specifications/11-research/drift-detectors.md`, J-W3-10): `S+_t = max(0, S+_{t-1} + z_t - k)` on `z = (x - mu0) / sigma`, the mirror for `S-`, alarm when either is strictly above `h`, then both restart.

```bash
uv run --project python quantforge run < examples/research_drift_cusum_j.json
```

Worked example. `x = 0, 0.2, -0.1, 1.4, 1.6, 1.5, 1.7`, `k = 0.5`, `h = 2`. `S+` stays 0 for three steps, then 0.9, 2.0 (not above 2: the test is strict), 3.0: alarm at index 5, restart, then 1.2. Output `"alarms":[5]`, `"directions":[1]`, `"s_plus":1.2`, `"s_minus":0.0`. `research.drift.page_hinkley` is the same idea measured against the running mean instead of a fixed `mu0`.

### Compare two windows with KS

Plain idea: the largest vertical gap between the two empirical distribution functions, and the chance of a gap that large if both windows came from the same continuous distribution. Formally (J-W3-13): `D = max |F_n - G_m|`; the p-value counts the lattice paths with `|i m - j n| < D n m` exactly.

```bash
uv run --project python quantforge run < examples/research_drift_ks_j.json
```

Worked example. `a = 1, 2, 3, 4`, `b = 3.5, 5, 6, 7`. At `x = 3` three quarters of `a` and none of `b` lie at or below: `D = 0.75`. Of the `C(8, 4) = 70` orderings, 16 give a gap at least that large, so `p = 16 / 70`. Output `"statistic":0.75`, `"p_value":0.22857142857142856`, `"reject":false`: four points each are too few to tell. For binned shares use `research.drift.psi`.

To check a whole suite: `python conformance/runner/runner.py --impl python --suite scen_j` (or `interpbt_j`, `drift_j`).

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

## Stage H recipes (available from v0.10.0)

Stage H is implemented in all four languages from v0.10.0 (released 2026-11-19; spec version 0.1.0, confirmed 2026-11-18), the `paper.*` operations included. Each request copies the inputs of the named golden case, and the expected outputs are that case's values in the spec, which every build reproduces in conformance. Send a request with `quantforge batch`: one case per line on stdin, each line holding exactly the keys `schema_version`, `case_id`, `operation` and `inputs` (a line missing one is `E_SCHEMA`; see [Batch mode](#batch-mode)). From `python/`, with the request lines in a file:

```bash
PYTHONUTF8=1 uv run quantforge batch < requests.jsonl
```

The outputs printed below are from the Python build (observed, local, 2026-11-19); the other three builds return the same values in conformance. [Tutorials 36 to 40](docs/getting-started/README.md) also check the same numbers by hand with a standard-library script.

| Task | Operation | From golden | Expected |
|---|---|---|---|
| Schedule an order at 20 % of volume | `exec.schedule.pov` | `sched_h-0005` | slices `[250, 500, 250]`, residual 0 |
| Almgren-Chriss trajectory for a given risk aversion | `exec.ac.trajectory` | `ac_h-0002` | `kappa` 0.6070761632, `expected_cost` 911,226.986 |
| Shortfall decomposition of a fill list | `exec.tca.shortfall` | `tca_h-0001` | delay 80, execution 100, opportunity 200, total 385 (38.5 bp) |
| Impact estimate for a size | `exec.impact.sqrt` | `imp_h-0001` | 0.002 |
| Inventory-aware quotes | `micro.mm.as_quotes` | `as_h-0001` | reservation 99.2, bid 98.3546147886, ask 100.0453852114 |

### Schedule an order

Plain idea: cut the parent order into child slices. Formally (`specifications/10-execution/schedules.md`, HR-3, HR-4): POV child `i = min(remaining, p v_i / (1 - p))`, floored in whole units.

```json
{"schema_version": "1.0", "case_id": "pov", "operation": "exec.schedule.pov", "inputs": {"quantity": 1000, "participation": 0.2, "market_volume": [1000, 2000, 4000], "mode": "UNITS"}}
```

### Almgren-Chriss trajectory

```json
{"schema_version": "1.0", "case_id": "ac", "operation": "exec.ac.trajectory", "inputs": {"quantity": 1000000, "horizon": 5, "n_steps": 5, "sigma": 0.95, "epsilon": 0.0625, "eta": 2.5e-6, "gamma": 2.5e-7, "risk_aversion": 1e-6}}
```

For the frontier, send `exec.ac.frontier` with `risk_aversions` as a list; `E` must not fall and `V` must not rise along it.

### Shortfall of a fill list

```json
{"schema_version": "1.0", "case_id": "is", "operation": "exec.tca.shortfall", "inputs": {"side": "BUY", "decision_price": 100, "arrival_price": 100.10, "end_price": 101, "order_quantity": 1000, "fills": [{"quantity": 600, "price": 100.20}, {"quantity": 200, "price": 100.30}], "fees": 5}}
```

### Impact for a size

```json
{"schema_version": "1.0", "case_id": "imp", "operation": "exec.impact.sqrt", "inputs": {"quantity": 100000, "daily_volume": 10000000, "daily_vol": 0.02, "coefficient": 1}}
```

`coefficient` is an assumption (HR-10); the default is 1.

### Quotes for an inventory

```json
{"schema_version": "1.0", "case_id": "as", "operation": "micro.mm.as_quotes", "inputs": {"mid": 100, "inventory": 2, "risk_aversion": 0.1, "sigma": 2, "time_left": 1, "k": 1.5}}
```

### Rebuild a book from a recorded file and check it

`micro.book.rebuild` takes the recorded messages as decimal strings, the subscribed depth (100 for days from 2026-11-17 20:15 UTC) and the pair's decimals, and returns the final book with counts of checksum failures, crossed and locked books and gaps (`specifications/09-microstructure/order-book.md`, HR-11 to HR-17). Checksum failures are counted, not errors. Goldens: `ob_h`, 17 cases, starting from the venue's own checksum example (`ob_h-0001`). Results on recorded days are labelled "crypto venue; not equities or rates". Recorded rows may not be published (HR-41), so the request below is the synthetic golden `ob_h-0002`: a depth-10 snapshot with bids 100.0 (1) and 99.0 (2) and asks 101.0 (1) and 102.0 (2), then an update that sets the 99.0 bid to 0, which removes it. Each message also carries a timestamp `t` and `checksum` null. The command reads the inputs straight from the golden file (the message timestamps are left out of this page because the holdout-date guard, `research/test_preregs.py`, scans it):

```bash
python -c "import json; c=next(c for c in json.load(open('datasets/golden/stage_h/ob_h.json'))['cases'] if c['case_id']=='ob_h-0002'); print(json.dumps({'schema_version':'1.0','case_id':c['case_id'],'operation':c['operation'],'inputs':c['inputs']}))" | uv run --project python quantforge batch
```

```json
{"schema_version":"1.0","case_id":"ob_h-0002","status":"ok","outputs":{"book":{"bids":[["100.0","1.00000000"]],"asks":[["101.0","1.00000000"],["102.0","2.00000000"]]},"stats":{"messages":2,"snapshots":1,"updates":1,"level_changes":1,"deletes_of_absent_level":0,"truncated_levels":0,"checksum_checked":0,"checksum_failed":0,"checkpoint_checked":0,"checkpoint_failed":0,"crossed":0,"locked":0,"gaps":0,"resyncs":0},"events":[],"crc32":3791984124},"diagnostics":{}}
```

`crc32` is the venue-style checksum of the final top 10, computed whether or not the input carried one; with `checksum` null on every message, `checksum_checked` stays 0. To see a gap counted, send `ob_h-0008` from `datasets/golden/stage_h/ob_h.json`: its output has `gaps` 1 and the events `GAP` and `UPDATE_BEFORE_SNAPSHOT`.

### Replay an order sequence through the engine

`exec.sim.lit.run` takes `tick_size`, `lot_size`, a list of `NEW`, `CANCEL` and `MODIFY` events and a fee schedule, and returns fills, rejects, the final book and fees (`specifications/10-execution/lit-matching.md`, HR-25 to HR-31). Output is labelled "simulated venue; not a real exchange". Goldens: `lit_h`, 20 cases (one per order type: LIMIT `lit_h-0002`, FOK `0003`, IOC `0004`, POST_ONLY `0005`, ICEBERG `0006`, PEG_MID `0008`, MARKET `0009`, PEG_PRIMARY `0010`; FIFO `0001` and `0007`). A quantity that is not a positive multiple of `lot_size` is `E_DOMAIN`, and a MODIFY of an id that is not open is the reject `UNKNOWN_ID` (HR-128). Price-time priority, `lit_h-0001`: three bids of 10 at 100, then a sell of 15 at 100.

```json
{"schema_version":"1.0","case_id":"lit_h-0001","operation":"exec.sim.lit.run","inputs":{"events":[{"id":"B1","op":"NEW","price":"100","qty":"10","side":"BUY","trader":"T1","type":"LIMIT"},{"id":"B2","op":"NEW","price":"100","qty":"10","side":"BUY","trader":"T1","type":"LIMIT"},{"id":"B3","op":"NEW","price":"100","qty":"10","side":"BUY","trader":"T1","type":"LIMIT"},{"id":"S1","op":"NEW","price":"100","qty":"15","side":"SELL","trader":"T2","type":"LIMIT"}],"fee_schedule":{"maker_rebate":"0","taker_fee":"0"},"lot_size":"1","tick_size":"1"}}
```

```json
{"schema_version":"1.0","case_id":"lit_h-0001","status":"ok","outputs":{"fills":[{"taker_id":"S1","maker_id":"B1","price":"100","qty":"10","seq":1},{"taker_id":"S1","maker_id":"B2","price":"100","qty":"5","seq":2}],"rejects":[],"cancelled":[],"book":{"bids":[{"id":"B2","price":"100","display_qty":"5","hidden_qty":"0","seq":2},{"id":"B3","price":"100","display_qty":"10","hidden_qty":"0","seq":3}],"asks":[]},"mbp":{"bids":[["100","15"]],"asks":[]},"fees":{"T1":"0","T2":"0"},"conservation":{"B1":{"submitted":"10","filled":"10","resting":"0","cancelled":"0","rejected":"0"},"B2":{"submitted":"10","filled":"5","resting":"5","cancelled":"0","rejected":"0"},"B3":{"submitted":"10","filled":"0","resting":"10","cancelled":"0","rejected":"0"},"S1":{"submitted":"15","filled":"15","resting":"0","cancelled":"0","rejected":"0"}},"label":"simulated venue; not a real exchange"},"diagnostics":{}}
```

B1 arrived first and fills in full, B2 fills 5 and keeps its place, B3 is untouched. Each order's `conservation` row adds up: submitted = filled + resting + cancelled + rejected. Simulated venue; not a real exchange.

### Cross orders in the simulated dark pool

Plain idea: hidden orders meet at the lit midpoint, and a minimum quantity can stop a fill that is too small. Formally (`specifications/10-execution/dark-pool.md`, HR-32 to HR-34): cross at the mid of the last `BOOK` event, on the half tick if needed, when the mid is within both limits and the fill `min(open_a, open_b)` meets each order's `min_qty`. `dark_h-0001` and `dark_h-0002` differ only in the buy's `min_qty` of 80:

```json
{"schema_version":"1.0","case_id":"dark_h-0001","operation":"exec.sim.dark.run","inputs":{"config":{"firm_delay":0,"lot_size":"1","p_firm":"1","penalty_events":2,"seed":20261118,"tick_size":"0.01"},"events":[{"ask":"100.10","bid":"100.00","op":"BOOK"},{"id":"B1","kind":"FIRM","op":"NEW","qty":"100","side":"BUY"},{"id":"S1","kind":"FIRM","op":"NEW","qty":"60","side":"SELL"}]}}
{"schema_version":"1.0","case_id":"dark_h-0002","operation":"exec.sim.dark.run","inputs":{"config":{"firm_delay":0,"lot_size":"1","p_firm":"1","penalty_events":2,"seed":20261118,"tick_size":"0.01"},"events":[{"ask":"100.10","bid":"100.00","op":"BOOK"},{"id":"B1","kind":"FIRM","min_qty":"80","op":"NEW","qty":"100","side":"BUY"},{"id":"S1","kind":"FIRM","op":"NEW","qty":"60","side":"SELL"}]}}
```

```json
{"schema_version":"1.0","case_id":"dark_h-0001","status":"ok","outputs":{"fills":[{"buy_id":"B1","sell_id":"S1","price":"100.05","qty":"60","seq":1}],"invitations":[],"suspensions":[],"resting":[{"id":"B1","side":"BUY","open_qty":"40","seq":1}],"label":"simulated venue; not a real dark pool"},"diagnostics":{}}
{"schema_version":"1.0","case_id":"dark_h-0002","status":"ok","outputs":{"fills":[],"invitations":[],"suspensions":[],"resting":[{"id":"B1","side":"BUY","open_qty":"100","seq":1},{"id":"S1","side":"SELL","open_qty":"60","seq":2}],"label":"simulated venue; not a real dark pool"},"diagnostics":{}}
```

The mid of 100.00 and 100.10 is 100.05, so 60 cross there and 40 of the buy rests. With `min_qty` 80 the only possible fill, 60, is too small, and both orders rest. Markouts of dark fills: `exec.sim.dark.markouts` (`dark_h-0007`). Simulated venue; not a real dark pool. No real dark-pool data is used.

### Split an order across venues with the router

`exec.sor.allocate` returns the market order `M` and the limit posts `L` per venue that minimise the sample mean of the Cont-Kukanov cost (`specifications/10-execution/smart-order-router.md`, HR-37 to HR-39). `sor_h-0003`: buy 10 lots on one lit venue with 2 lots queued ahead, half spread 0.5, fee 0.3, rebate 0.2, underfill penalty 4, eight equally likely outflows.

```json
{"schema_version":"1.0","case_id":"sor_h-0003","operation":"exec.sor.allocate","inputs":{"S":"10","f":"0.3","h":"0.5","lambda_o":"1","lambda_u":"4","lit_samples":[["0"],["2"],["4"],["6"],["8"],["10"],["12"],["14"]],"theta":"0","venues":[{"Q":"2","as":"0","kind":"LIT","r":"0.2"}]}}
```

```json
{"schema_version":"1.0","case_id":"sor_h-0003","status":"ok","outputs":{"M":"8","L":["2"],"expected_cost":"7.35","expected_fill":"9.5","p_underfill":"0.25"},"diagnostics":{}}
```

Send 8 at market and post 2. The post fills unless the outflow is 0 or 2, so the order is short 2 lots a quarter of the time; the worked cost is in [LEARN](LEARN.md#dark-pools-and-the-smart-order-router-simulated). This output has no `label` field; with `"report_se": true` the build adds `expected_cost_se` and the label "simulated venues; router scored in simulation only" (`sorx_h-0002`). The fill distributions are inputs, so the split is only as good as they are. The comparison of the router against single-venue routing on 10,000 simulated parent orders (seed 20261117) is fixed in the spec as a simulated result, not a gate (HR-40); no result file for it is in the repository at v0.10.0. See [Simulators](docs/simulators/README.md).

### Record and refresh the crypto feed

`python tools/recorder/crypto_l2.py --symbols BTC/USD ETH/USD` records Kraken's public book at 100 levels and trades to local files, never to git. See [Recorded feeds](docs/data/recorded-feeds.md) for terms, depth by date and what may be published.

### Run a paper trading day

The paper book is a Python application on the library operations, not an operation itself (`specifications/10-execution/paper-trading.md`, HR-42 to HR-55). Book fills, close the day and get the explain; `total` always equals the NAV change exactly, or the call raises:

```python
from decimal import Decimal
from quantforge_core import paper

book = paper.Book(Decimal("10000"))
day = paper.end_of_day(book, fills, prev_marks, marks, days=1, cash_rate="0.0365")
print(day["market"], day["trading"], day["fees"], day["financing"], day["total"])
```

`paper.pretrade_check(order, ref_price, position, cash, orders_today, limits)` returns `{accepted, reasons}` with reasons in the HR-49 order; `mode` other than `"simulated"` raises `E_UNSUPPORTED_OPERATION`. Golden numbers: [Tutorial 44](docs/getting-started/tutorial-44-paper-trading.md). Fills from the simulated venues come from `quantforge_core.paper_fills.Session` (Python).

### Check a paper ledger has not been edited

```python
from quantforge_core import paper
print(paper.verify(open("ledger.jsonl", encoding="utf-8").read()))
```

`ok` false with `first_bad_seq` and a reason (`HASH`, `LINK`, `SEQ`, `LABEL`, `PARSE`); it never repairs. A truncated tail is caught only by comparing the head hash with the published one (HR-46).

### Estimate a book rate with its standard error (available from v0.10.0)

`micro.est.arrival_rate`, `micro.est.cancel_rate`, `micro.est.resilience`, `micro.est.liquidity_decay`, `micro.est.adverse_selection`, `micro.est.regime_impact` and `micro.est.passive_vs_aggressive` each return the estimate and `se` (`specifications/09-microstructure/micro-estimators.md`). For 12 arrivals in 4 seconds:

```json
{"schema_version": "1.0", "case_id": "arr", "operation": "micro.est.arrival_rate", "inputs": {"count": 12, "window": 4}}
```

gives `lambda` 3, `se` 0.8660254037844386 (`mest_h-0001`). See [Tutorial 45](docs/getting-started/tutorial-45-microstructure-estimators.md).

### Compare venues by markout and fill rate (available from v0.10.0)

`exec.venue.analytics` takes `mids`, `fills`, `orders` and `horizons` and returns `fill_rates` and one `{venue, h, markout, markout_bps, toxicity}` row per venue and horizon (`specifications/10-execution/venue-analytics.md`). Report several horizons: in `venue_h-0001` and `0002` the two venues swap places between 5 and 10 seconds. See [Tutorial 46](docs/getting-started/tutorial-46-venue-analytics.md).

### Schedule an adaptive order (available from v0.10.0)

`exec.algo.arrival` (urgency `kappa`), `exec.algo.close` (auction cap and profile), `exec.algo.liquidity_seek` (share of in-limit depth), `exec.algo.pair` and `exec.algo.basket` (`specifications/10-execution/adaptive-algos.md`). For an arrival-price order of 1,000 over two buckets at `kappa = ln 2`:

```json
{"schema_version": "1.0", "case_id": "arrival", "operation": "exec.algo.arrival", "inputs": {"quantity": 1000, "n_buckets": 2, "urgency": 0.69314718055994531, "mode": "CONTINUOUS"}}
```

gives slices 600 and 400 to rounding (the build prints 599.9999999999999 and 399.99999999999994; `alg_h-0002`). See [Tutorial 47](docs/getting-started/tutorial-47-adaptive-algos-and-tca.md).

### Estimate cost before trading and split it afterwards (available from v0.10.0)

`exec.tca.pretrade` returns `expected_cost_bps` and, separately, `timing_risk_bps`; `exec.tca.attribution` returns delay, impact, spread, opportunity and fees summing to `total` (`specifications/10-execution/tca-pretrade.md`). `tcx_h-0006` reproduces the `tca_h-0001` total of 385 with the execution cost split into impact 60 and spread 40.

### Read the low-latency book results (available from v0.10.0)

The H-9 results file `benchmarks/results/h9/README.md` gives p50, p99 and p99.9 per operation against the targets in `specifications/09-microstructure/low-latency-targets.md`. Every run so far is a laptop under WSL, not the acceptance machine; quote it with that label and with "in-process, simulated feed; no network or venue latency". Workload R (the recorded Kraken window 2026-11-18 21:49:17 to 2026-11-19 03:49:17 UTC, median of 5 runs) is a timing MISS at p99 and p99.9 in every language, with 0 correctness mismatches; the per-level figure quoted beside it is descriptive only and has no target. See [Tutorial 48](docs/getting-started/tutorial-48-low-latency-book.md).

### Stage H multi-asset recipes: equities, FX, rates and their simulated venues

Round 4 (H-22 to H-24) adds trading conventions and three simulated venues. Convention operations (`micro.eq.*`, `micro.fx.*`, `micro.rates.*`) are arithmetic and carry no label; venue operations (`exec.sim.*`) carry a "simulated venue" label on every output (HR-111). No venue here is real: the only real data in stage H is one crypto venue's public book. Specs: `specifications/09-microstructure/asset-conventions.md`, `specifications/10-execution/auction.md`, `fx-rfq-venue.md` and `rates-futures-venue.md`; rulings HR-80 to HR-120 in `specifications/stage-h-rulings-multiasset.md`. Decimals go in as strings (HR-12). Each request below is a golden case's inputs unless the recipe says otherwise, and each output is the Python build's real output (observed, local, 2026-11-19). The `message` text of an error is not part of the contract; the `code` is.

### Round an equity price to the tick grid

Plain idea: a limit price must sit on the venue's price grid, and rounding must never make the order more aggressive than asked. Formally (HR-81, HR-120; SEC Rule 612): the tick is 0.0001 below 1.00 and 0.01 at or above it, or 0.005 for a stock on the half-penny tier; a buy rounds down and a sell rounds up. The half-penny tier belongs to the amended rule, whose compliance date is 2027-11-01 (deferred by SEC order 34-105656). With no `as_of` the operation applies the amended text; with an `as_of` it applies the rule in force on that date.

```json
{"schema_version":"1.0","case_id":"eqc_h-0001","operation":"micro.eq.round_price","inputs":{"price":"10.005","side":"BUY"}}
{"schema_version":"1.0","case_id":"eqc_h-0002","operation":"micro.eq.round_price","inputs":{"price":"10.005","side":"SELL"}}
{"schema_version":"1.0","case_id":"eqc_h-0010","operation":"micro.eq.round_price","inputs":{"price":"10.003","side":"SELL","tick_tier":"HALF_PENNY"}}
{"schema_version":"1.0","case_id":"eqc_h-0020","operation":"micro.eq.round_price","inputs":{"price":"10.003","side":"BUY","tick_tier":"HALF_PENNY","as_of":"2026-11-19"}}
{"schema_version":"1.0","case_id":"eqc_h-0022","operation":"micro.eq.round_price","inputs":{"price":"10.003","side":"SELL","tick_tier":"HALF_PENNY","as_of":"2027-11-01"}}
```

```json
{"schema_version":"1.0","case_id":"eqc_h-0001","status":"ok","outputs":{"price":"10.00"},"diagnostics":{}}
{"schema_version":"1.0","case_id":"eqc_h-0002","status":"ok","outputs":{"price":"10.01"},"diagnostics":{}}
{"schema_version":"1.0","case_id":"eqc_h-0010","status":"ok","outputs":{"price":"10.005"},"diagnostics":{}}
{"schema_version":"1.0","case_id":"eqc_h-0020","status":"error","error":{"code":"E_INPUT","message":"tick_tier HALF_PENNY before the compliance date","field":"tick_tier"},"diagnostics":{}}
{"schema_version":"1.0","case_id":"eqc_h-0022","status":"ok","outputs":{"price":"10.005"},"diagnostics":{}}
```

The third line has no `as_of`, so it gets the amended text. That tier is not in force before 2027-11-01: the fourth line asks for it on 2026-11-19 and is refused. Limits: the tier is an input per stock, and the six-monthly spread test that assigns it is not modelled; the SEC has the deferred rules under review, so the date may move, and `compliance_date` overrides the default.

### Check an access fee against the cap

Plain idea: a venue may not charge more than a capped fee to take a displayed quote. Formally (HR-85, HR-120; SEC Rule 610(c)): the cap in force today is 0.003 a share at 1.00 or more and 0.3 % of the price below; the amended cap, 0.001 and 0.1 %, has the same 2027-11-01 compliance date as the tick rule. A fee above the cap is `E_DOMAIN`.

```json
{"schema_version":"1.0","case_id":"eqc_h-0011","operation":"micro.eq.fee_check","inputs":{"price":"20","taker_fee":"0.0015"}}
{"schema_version":"1.0","case_id":"eqc_h-0023","operation":"micro.eq.fee_check","inputs":{"price":"20","taker_fee":"0.0015","as_of":"2026-11-19"}}
{"schema_version":"1.0","case_id":"eqc_h-0024","operation":"micro.eq.fee_check","inputs":{"price":"20","taker_fee":"0.0015","as_of":"2027-11-01"}}
```

```json
{"schema_version":"1.0","case_id":"eqc_h-0011","status":"error","error":{"code":"E_DOMAIN","message":"taker_fee above the Rule 610 cap","field":"taker_fee"},"diagnostics":{}}
{"schema_version":"1.0","case_id":"eqc_h-0023","status":"ok","outputs":{"cap":"0.003","taker_fee":"0.0015"},"diagnostics":{}}
{"schema_version":"1.0","case_id":"eqc_h-0024","status":"error","error":{"code":"E_DOMAIN","message":"taker_fee above the Rule 610 cap","field":"taker_fee"},"diagnostics":{}}
```

The same fee of 0.0015 fails with no `as_of` (amended cap 0.001), passes on 2026-11-19 (cap 0.003) and fails again from 2027-11-01. Limits: this is a cap test, not a fee schedule; `cap_check: false` returns the cap without the error.

### Find the round lot for a price

Plain idea: the standard order size shrinks as the share price rises. Formally (HR-82, HR-120; SEC Rule 600(b)(93)): 100 shares up to 250.00, 40 up to 1,000.00, 10 up to 10,000.00 and 1 above. This rule was not deferred: it has applied since the first business day of November 2025, and before that the lot was 100 at every price.

```json
{"schema_version":"1.0","case_id":"eqc_h-0015","operation":"micro.eq.round_lot","inputs":{"price":"250.01"}}
{"schema_version":"1.0","case_id":"eqc_h-0025","operation":"micro.eq.round_lot","inputs":{"as_of":"2026-11-19","price":"500"}}
{"schema_version":"1.0","case_id":"round-lot-old","operation":"micro.eq.round_lot","inputs":{"as_of":"2012-06-01","price":"500"}}
```

```json
{"schema_version":"1.0","case_id":"eqc_h-0015","status":"ok","outputs":{"round_lot":40},"diagnostics":{}}
{"schema_version":"1.0","case_id":"eqc_h-0025","status":"ok","outputs":{"round_lot":40},"diagnostics":{}}
{"schema_version":"1.0","case_id":"round-lot-old","status":"ok","outputs":{"round_lot":100},"diagnostics":{}}
```

Limits: `price` stands for the rule's Evaluation-Period average closing price; the six-month operative period is not modelled.

### Equity settlement date

Plain idea: cash and shares change hands a fixed number of business days after the trade. Formally (HR-86): `settle_lag` good days, default 1, on the calendar passed in.

```json
{"schema_version":"1.0","case_id":"eqc_h-0008","operation":"micro.eq.settle_date","inputs":{"holidays":[],"settle_lag":1,"trade_date":"2026-11-20"}}
{"schema_version":"1.0","case_id":"settle-holiday","operation":"micro.eq.settle_date","inputs":{"holidays":["2026-11-26"],"settle_lag":1,"trade_date":"2026-11-25"}}
```

```json
{"schema_version":"1.0","case_id":"eqc_h-0008","status":"ok","outputs":{"settle_date":"2026-11-23"},"diagnostics":{}}
{"schema_version":"1.0","case_id":"settle-holiday","status":"ok","outputs":{"settle_date":"2026-11-27"},"diagnostics":{}}
```

Friday settles on Monday; a Wednesday trade before a Thursday holiday settles on Friday. Limits: holidays are inputs; the operation knows no exchange calendar. The second case is not a golden (Python build output only).

### FX pip value and spot date

Plain idea: a pip is the unit a spot price moves in, and the spot date is when the two currencies are delivered. Formally (HR-87 to HR-89): a pip is 0.0001, or 0.01 when JPY is the quote currency, and its value in the quote currency is notional times pip. Spot is T+2 good days, T+1 for USDCAD. The first day after the trade needs only the non-USD currency to be open, but the value date must be a good day in both.

```json
{"schema_version":"1.0","case_id":"fxc_h-0001","operation":"micro.fx.pip_value","inputs":{"notional":"1000000","pair":"EURUSD"}}
{"schema_version":"1.0","case_id":"fxc_h-0002","operation":"micro.fx.pip_value","inputs":{"notional":"1000000","pair":"USDJPY"}}
{"schema_version":"1.0","case_id":"fxc_h-0005","operation":"micro.fx.spot_date","inputs":{"holidays":{},"pair":"EURUSD","trade_date":"2026-11-20"}}
{"schema_version":"1.0","case_id":"fxc_h-0004","operation":"micro.fx.spot_date","inputs":{"holidays":{"USD":["2026-11-26"]},"pair":"EURUSD","trade_date":"2026-11-24"}}
```

```json
{"schema_version":"1.0","case_id":"fxc_h-0001","status":"ok","outputs":{"currency":"USD","pip_value":"100"},"diagnostics":{}}
{"schema_version":"1.0","case_id":"fxc_h-0002","status":"ok","outputs":{"currency":"JPY","pip_value":"10000"},"diagnostics":{}}
{"schema_version":"1.0","case_id":"fxc_h-0005","status":"ok","outputs":{"spot_date":"2026-11-24"},"diagnostics":{}}
{"schema_version":"1.0","case_id":"fxc_h-0004","status":"ok","outputs":{"spot_date":"2026-11-27"},"diagnostics":{}}
```

In the last case T+2 from Tuesday 2026-11-24 is Thursday the 26th, a USD holiday, so spot rolls to Friday the 27th. Limits: eight currencies only (EUR, GBP, AUD, NZD, USD, CAD, CHF, JPY); another currency, or a pair written the wrong way round, is `E_INPUT` (HR-88, HR-123). USDCAD T+1 is market convention with no primary source read (HR-119).

### Send a last-look request to the simulated FX venue

Plain idea: a dealer quotes a bid and an ask, and when a client asks to trade the dealer may look at the market once more and refuse. Formally (`specifications/10-execution/fx-rfq-venue.md`, HR-97): the request is rejected `LL_PRICE` if the mid moved by more than `threshold_pips` against the dealer (either way when `symmetric`); otherwise rejected `LL_RANDOM` if the draw `u` is below `p_random_reject`; otherwise filled at the quoted price. Without `u`, the draw comes from `core.rng` with `seed` and stream `request_index`, and is returned.

```json
{"schema_version":"1.0","case_id":"fxv_h-0004","operation":"exec.sim.fx.request","inputs":{"mid_after":"1.0852","p_random_reject":"0.05","pair":"EURUSD","qty":"1000000","quote":{"ask":"1.0852","bid":"1.0850","quote_mid":"1.0851"},"side":"BUY","symmetric":true,"threshold_pips":"2","u":"0.50"}}
{"schema_version":"1.0","case_id":"fxv_h-0003","operation":"exec.sim.fx.request","inputs":{"mid_after":"1.0855","p_random_reject":"0.05","pair":"EURUSD","qty":"1000000","quote":{"ask":"1.0852","bid":"1.0850","quote_mid":"1.0851"},"side":"BUY","symmetric":true,"threshold_pips":"2","u":"0.50"}}
{"schema_version":"1.0","case_id":"fxv_h-0010","operation":"exec.sim.fx.request","inputs":{"mid_after":"1.0852","p_random_reject":"0.5","pair":"EURUSD","qty":"1000000","quote":{"ask":"1.0852","bid":"1.0850","quote_mid":"1.0851"},"side":"BUY","symmetric":true,"threshold_pips":"2","request_index":0,"seed":20261118}}
```

```json
{"schema_version":"1.0","case_id":"fxv_h-0004","status":"ok","outputs":{"label":"simulated venue; not a real exchange; no real FX data","move_pips":"1","outcome":"FILL","price":"1.0852"},"diagnostics":{}}
{"schema_version":"1.0","case_id":"fxv_h-0003","status":"ok","outputs":{"label":"simulated venue; not a real exchange; no real FX data","move_pips":"4","outcome":"LL_PRICE","price":null},"diagnostics":{}}
{"schema_version":"1.0","case_id":"fxv_h-0010","status":"ok","outputs":{"label":"simulated venue; not a real exchange; no real FX data","move_pips":"1","outcome":"FILL","price":"1.0852","u":0.9911886460034905},"diagnostics":{}}
```

A 1-pip move fills at the ask; a 4-pip move is refused; the seeded request draws 0.9912, above the 0.5 reject rate, and fills. Limits: a simulated dealer, not a real one. The thresholds and the random reject are the spec's own toy model, not taken from the FX Global Code, and `LL_RANDOM` stands in for validity and credit rejects (HR-119). `seed` is within 0..2^53-1 and `request_index` within 0..2^32-1, else `E_LIMIT` (HR-116). `exec.sim.fx.stream` builds the quotes from a mid path.

### Parse and format a price in 32nds

Plain idea: Treasury prices are written in 32nds of a point, not decimals. Formally (HR-90, HR-109, HR-118): `H-FF[q]` is `H + (FF + q) / 32`, with the third digit in quarters of a 32nd: none or `0` is 0, `2` is 1/4, `5` or `+` is 1/2, `7` is 3/4.

```json
{"schema_version":"1.0","case_id":"rtc_h-0003","operation":"micro.rates.parse_32nds","inputs":{"text":"99-162"}}
{"schema_version":"1.0","case_id":"rtc_h-0005","operation":"micro.rates.format_32nds","inputs":{"resolution":64,"value":"101.296875"}}
{"schema_version":"1.0","case_id":"rtc_h-0015","operation":"micro.rates.parse_32nds","inputs":{"text":"99-163"}}
```

```json
{"schema_version":"1.0","case_id":"rtc_h-0003","status":"ok","outputs":{"value":"99.5078125"},"diagnostics":{}}
{"schema_version":"1.0","case_id":"rtc_h-0005","status":"ok","outputs":{"text":"101-09+"},"diagnostics":{}}
{"schema_version":"1.0","case_id":"rtc_h-0015","status":"error","error":{"code":"E_SCHEMA","message":"text: not H-FF[q] with q in 0, 2, 5, 7, + (HR-109)","field":"text"},"diagnostics":{}}
```

99-162 is 99 + 16.25/32. Limits: only the third digits 0, 2, 5 and 7 are read (the CME quarter-tick convention, source read 2026-11-19). Contracts that tick in eighths of a 32nd (2-year and 3-year notes) are not supported, so any other third digit is `E_SCHEMA` (HR-118). A value off the `resolution` grid is `E_DOMAIN`.

### Bond price, bond yield and bill price

Plain idea: discount each coupon and the principal at the yield; a bill is quoted as a discount from par. Formally (HR-92): on a coupon date `P = sum_{i=1..n} (100 c / f) / (1 + y / f)^i + 100 / (1 + y / f)^n`; bill `P = 100 (1 - d days / 360)`; the yield is found by Brent on `(-0.99 f, 10)` to 1e-12.

```json
{"schema_version":"1.0","case_id":"rtc_h-0008","operation":"micro.rates.bond_price","inputs":{"coupon":"0.04","frequency":2,"periods":2,"yield":"0.05"}}
{"schema_version":"1.0","case_id":"rtc_h-0012","operation":"micro.rates.bond_yield","inputs":{"coupon":"0.04","frequency":2,"periods":2,"price":"99.036287923854848305"}}
{"schema_version":"1.0","case_id":"rtc_h-0010","operation":"micro.rates.bill_price","inputs":{"days":91,"discount":"0.05"}}
```

```json
{"schema_version":"1.0","case_id":"rtc_h-0008","status":"ok","outputs":{"price":"99.036287924"},"diagnostics":{}}
{"schema_version":"1.0","case_id":"rtc_h-0012","status":"ok","outputs":{"yield":0.050000000000064035},"diagnostics":{}}
{"schema_version":"1.0","case_id":"rtc_h-0010","status":"ok","outputs":{"price":"98.736111111"},"diagnostics":{}}
```

The yield comes back as 5 % to within the solver tolerance, not byte for byte, so its golden is compared within tolerance. Limits: coupon dates only; off a coupon date use the stage D bond operations ([Price a bond from its yield](#price-a-bond-from-its-yield)).

### Futures price to ticks, and P&L

Plain idea: a futures venue counts prices in whole ticks, and P&L is ticks moved times the tick value. Formally (`specifications/10-execution/rates-futures-venue.md`, HR-91): ticks = price / tick on the contract's grid (ZN tick 1/64 of a point worth 15.625, ZB tick 1/32 worth 31.25); P&L = ticks x tick value x quantity, less `fee_per_contract` on each side.

```json
{"schema_version":"1.0","case_id":"fut_h-0001","operation":"exec.sim.fut.to_ticks","inputs":{"contract":{"symbol":"ZN"},"price":"110-16+"}}
{"schema_version":"1.0","case_id":"fut_h-0005","operation":"exec.sim.fut.pnl","inputs":{"buy_price":"110-16","contract":{"symbol":"ZN"},"fee_per_contract":"1.00","qty":3,"sell_price":"110-17+"}}
{"schema_version":"1.0","case_id":"fut_h-0006","operation":"exec.sim.fut.variation","inputs":{"contract":{"symbol":"ZB"},"price":"120-00","qty":1,"settlements":["119-31"],"side":"BUY"}}
```

```json
{"schema_version":"1.0","case_id":"fut_h-0001","status":"ok","outputs":{"label":"simulated venue; not a real exchange; no real rates data","ticks":7073},"diagnostics":{}}
{"schema_version":"1.0","case_id":"fut_h-0005","status":"ok","outputs":{"fees":"6","label":"simulated venue; not a real exchange; no real rates data","pnl":"134.625"},"diagnostics":{}}
{"schema_version":"1.0","case_id":"fut_h-0006","status":"ok","outputs":{"label":"simulated venue; not a real exchange; no real rates data","variation_margin":["-31.25"]},"diagnostics":{}}
```

110-16+ is 110.515625, or 7,073 ticks of 1/64. Three lots up 3 ticks make 3 x 3 x 15.625 = 140.625, less 6 in fees. Limits: a price off the contract grid is `E_DOMAIN` (a quarter-32nd on ZN, `fut_h-0003`); an integer beyond +-(2^53-1) is `E_LIMIT` (HR-116). Simulated; no real rates data.

### Run the simulated futures venue

Plain idea: the futures venue is the lit matching engine with prices written in 32nds and a P&L per trader at the end. Formally (`specifications/10-execution/rates-futures-venue.md`): `exec.sim.fut.run` converts each event's price to ticks, runs the lit engine in whole contracts, charges `fee_per_contract` to both sides of each fill and reports `fees` and `pnl` per trader.

```json
{"schema_version":"1.0","case_id":"fut_h-0011","operation":"exec.sim.fut.run","inputs":{"contract":{"symbol":"ZN"},"events":[{"id":"S1","op":"NEW","price":"110-16","qty":"3","side":"SELL","trader":"M","type":"LIMIT"},{"id":"B1","op":"NEW","price":"110-16","qty":"3","side":"BUY","trader":"P","type":"LIMIT"},{"id":"S2","op":"NEW","price":"110-17+","qty":"3","side":"SELL","trader":"P","type":"LIMIT"},{"id":"B2","op":"NEW","price":"110-17+","qty":"3","side":"BUY","trader":"N","type":"LIMIT"}],"fee_per_contract":"1.00"}}
```

```json
{"schema_version":"1.0","case_id":"fut_h-0011","status":"ok","outputs":{"fills":[{"taker_id":"B1","maker_id":"S1","price":"110.5","qty":"3","seq":1},{"taker_id":"B2","maker_id":"S2","price":"110.546875","qty":"3","seq":2}],"rejects":[],"cancelled":[],"book":{"bids":[],"asks":[]},"mbp":{"bids":[],"asks":[]},"fees":{"M":"3","N":"3","P":"6"},"conservation":{"B1":{"submitted":"3","filled":"3","resting":"0","cancelled":"0","rejected":"0"},"B2":{"submitted":"3","filled":"3","resting":"0","cancelled":"0","rejected":"0"},"S1":{"submitted":"3","filled":"3","resting":"0","cancelled":"0","rejected":"0"},"S2":{"submitted":"3","filled":"3","resting":"0","cancelled":"0","rejected":"0"}},"label":"simulated venue; not a real exchange; no real rates data","pnl":{"M":"-143.625","N":"-3","P":"134.625"}},"diagnostics":{}}
```

Trader P buys 3 at 110-16 and sells 3 at 110-17+: 140.625 less 6 in fees is 134.625, the `exec.sim.fut.pnl` answer above. P ends flat. M is left short 3 from 110-16 and N long 3 from 110-17+; their `pnl` is marked at the last trade price, 110-17+, so M shows -140.625 less 3 in fees and N shows 0 less 3. The three figures add to -12, the fees paid. Limits: simulated; the mark is the last trade in the run, not a settlement price (use `exec.sim.fut.variation` for a settlement series). Shared goldens `fut_h-0011` to `0016` were added on 2026-11-19; two of the three value cases were re-derived blind.

### Uncross an opening or closing auction

Plain idea: collect orders without trading, then pick the one price at which the most shares trade and fill everyone there. Formally (`specifications/10-execution/auction.md`, HR-84, HR-127): over the candidate ticks keep the price with the largest matched volume; ties go to the smallest imbalance, then to the rules of `tie_break` (default `CBOE`), which end with the price closest to `ref_price`. Buys fill by limit descending then arrival, sells by limit ascending then arrival. `imbalance` is buy minus sell quantity at the price.

```json
{"schema_version":"1.0","case_id":"auc_h-0001","operation":"exec.sim.auction.uncross","inputs":{"orders":[{"id":"s1","limit":"10.02","qty":100,"side":"BUY"},{"id":"s2","limit":"10.01","qty":200,"side":"BUY"},{"id":"s3","limit":"10.00","qty":300,"side":"BUY"},{"id":"s4","limit":"9.99","qty":150,"side":"SELL"},{"id":"s5","limit":"10.01","qty":250,"side":"SELL"},{"id":"s6","limit":"10.03","qty":100,"side":"SELL"}],"phase":"OPEN","ref_price":"10.00","tick_size":"0.01"}}
{"schema_version":"1.0","case_id":"close-example","operation":"exec.sim.auction.uncross","inputs":{"orders":[{"id":"b1","limit":"MARKET","qty":300,"side":"BUY"},{"id":"b2","limit":"20.10","qty":200,"side":"BUY"},{"id":"a1","limit":"20.05","qty":250,"side":"SELL"},{"id":"a2","limit":"20.10","qty":150,"side":"SELL"}],"phase":"CLOSE","ref_price":"20.08","tick_size":"0.01"}}
```

```json
{"schema_version":"1.0","case_id":"auc_h-0001","status":"ok","outputs":{"cancelled":[],"fills":[{"id":"s1","price":"10.01","qty":100,"side":"B"},{"id":"s2","price":"10.01","qty":200,"side":"B"},{"id":"s4","price":"10.01","qty":150,"side":"S"},{"id":"s5","price":"10.01","qty":150,"side":"S"}],"imbalance":-100,"label":"simulated venue; not a real exchange","price":"10.01","residual":[{"id":"s3","limit":"10.00","qty":300,"side":"B"},{"id":"s5","limit":"10.01","qty":100,"side":"S"},{"id":"s6","limit":"10.03","qty":100,"side":"S"}],"volume":300},"diagnostics":{}}
{"schema_version":"1.0","case_id":"close-example","status":"ok","outputs":{"cancelled":[],"fills":[{"id":"b1","price":"20.10","qty":300,"side":"B"},{"id":"b2","price":"20.10","qty":100,"side":"B"},{"id":"a1","price":"20.10","qty":250,"side":"S"},{"id":"a2","price":"20.10","qty":150,"side":"S"}],"imbalance":100,"label":"simulated venue; not a real exchange","price":"20.10","residual":[{"id":"b2","limit":"20.10","qty":100,"side":"B"}],"volume":400},"diagnostics":{}}
```

The open trades 300 at 10.01 with 100 of sell interest left over. The close trades 400 at 20.10: the market buy fills first, and 100 of the limit buy is left. Limits: a simulated auction, not one exchange's rule book; the imbalance-side and final higher-price tie-break steps are the simulator's own (HR-119). If nothing crosses there is no auction: `price` null and `volume` 0 (HR-127). A limit off the tick grid is `E_DOMAIN`. To run a whole session with both auctions, send `PHASE` events to `exec.sim.lit.run` (`ses_h-0001`, HR-112). The second case is not a golden (Python build output only).

### What error do I get when two inputs are wrong?

Plain idea: when a request breaks two rules, every build must report the same one, so the checks run in one fixed order. Formally (HR-122; `specifications/cli-contract.md`, "Finite rule"): (1) `E_SCHEMA`, for shape, type or an unlisted enum spelling; (2) `E_LIMIT`, for a size limit on the input itself; (3) a non-finite Real, `E_DOMAIN`; (4) structural `E_INPUT`, for an empty list, a count below 1, lengths or cross-field consistency; (5) `E_DOMAIN`, for one value outside its domain. A limit that only arises after validation comes last.

```json
{"schema_version":"1.0","case_id":"rule_h-0015","operation":"exec.schedule.pov","inputs":{"quantity":1000,"participation":1.5,"market_volume":[],"mode":"UNITS"}}
{"schema_version":"1.0","case_id":"rule_h-0012","operation":"exec.schedule.twap","inputs":{"quantity":-5,"n_buckets":200000,"mode":"UNITS"}}
```

```json
{"schema_version":"1.0","case_id":"rule_h-0015","status":"error","error":{"code":"E_INPUT","message":"market_volume must not be empty","field":"market_volume"},"diagnostics":{}}
{"schema_version":"1.0","case_id":"rule_h-0012","status":"error","error":{"code":"E_LIMIT","message":"n_buckets is above its limit of 100000","field":"n_buckets"},"diagnostics":{}}
```

In the first case `participation` 1.5 is outside its domain and `market_volume` is empty: the structural error wins, step (4) before step (5). In the second the quantity is negative and `n_buckets` is above its limit of 100,000: the limit wins, step (2) before step (4). Limits: one exception is recorded, `paper.pretrade.check`, which reports an unknown `side` or `type` as `E_INPUT` (`rule_h-0040`). Before 2026-11-19 two builds answered `E_DOMAIN` and two `E_INPUT` for an Almgren-Chriss request with two faults; suite `rule_h` (40 cases) now pins the order.

## Stage K recipes

Stage K round 1, with the round 2 audit fixes, is merged to main by 2026-11-20 (pull requests #58 and #59), not tagged; it is released with v1.0.0. Every operation below is registered in all four builds (CLI contract 1.17.0), and its goldens pass the conformance runner in each. Send each case line to a build's `run` or `batch` command and compare with the golden named. The "Observed" lines were run once by hand (items C1 to C9 of `program/STAGE_K_DOCS_PENDING.md`); no checker runs these blocks. Where an observed value differs from the golden in the last digit or two, the golden is the 50-digit oracle value rounded to binary64 and the build is inside the golden's tolerance class (`simple_analytic`).

### Query a bitemporal log

Plain idea: ask what was known at `K` about the value valid at `V`. Formally (`specifications/01-core/bitemporal-store.md`, KR-2): among records with `knowledge_time <= K` and `valid_from <= V < valid_to`, the largest `sequence` wins.

```json
{"schema_version": "1.0", "case_id": "bt", "operation": "core.store.bitemporal_query", "inputs": {"records": [{"sequence": 1, "series_id": "A", "valid_from": "2027-01-01T00:00:00Z", "valid_to": null, "knowledge_time": "2027-01-02T00:00:00Z", "value": 100}, {"sequence": 2, "series_id": "A", "valid_from": "2027-03-01T00:00:00Z", "valid_to": null, "knowledge_time": "2027-03-02T00:00:00Z", "value": 110}, {"sequence": 3, "series_id": "A", "valid_from": "2027-02-01T00:00:00Z", "valid_to": "2027-03-01T00:00:00Z", "knowledge_time": "2027-04-01T00:00:00Z", "value": 105}], "series_id": "A", "knowledge_as_of": "2027-04-01T00:00:00Z", "valid_at": "2027-02-15T00:00:00Z"}}
```

Expected: `status` `FOUND`, `row.sequence` 3, `row.value` 105. This is the log of golden `bt_k-0002` with every date moved one year later and record 4, learned after this `K`, left out; by KR-4 neither change alters the answer. The dates are moved so that this page carries no date inside a preregistered holdout window (`research/test_preregs.py`). Observed (observed 2026-11-19 on `k-r1`, Python build (`uv run --locked --project python quantforge batch`), local laptop, not the acceptance machine): `status` `FOUND`, `row.sequence` 3, `row.value` 105, as expected. Limits: the log travels in the request; there is no persistent store.

### Update a curve for one moved quote

```json
{"schema_version": "1.0", "case_id": "inc", "operation": "curve.incremental.update", "inputs": {"previous_quotes": [0.02, 0.025, 0.03], "previous_discount_factors": [0.9803921568627451, 0.9516977522716404, 0.9145993230349208], "new_quotes": [0.02, 0.026, 0.03]}}
```

Expected (golden `inc_k-0002`): `first_changed_index` 1, `recomputed` 2, `discount_factors` `[0.9803921568627451, 0.9498146237052326, 0.9146541714397677]`. `previous_discount_factors` must be the output of `curve.bootstrap.par_annual` on `previous_quotes`, bit for bit, or the answer is `E_INPUT`. Observed (observed 2026-11-19 on `k-r1`, Python build (`uv run --locked --project python quantforge batch`), local laptop, not the acceptance machine): `first_changed_index` 1, `recomputed` 2, `discount_factors` `[0.9803921568627451, 0.9498146237052325, 0.9146541714397676]`; the last two differ from the golden by one unit in the last place, inside the tolerance.

### Check whether to recalibrate

```json
{"schema_version": "1.0", "case_id": "trig", "operation": "calib.trigger.check", "inputs": {"changes": [1.0, -1.0, 1.0, -1.0], "x_ref": 100.0, "x_now": 105.0, "days_since": 1.0, "k": 3.0}}
```

Expected (golden `trig_k-0001`): `fire` true, `sigma` 1.1547005383792515, `threshold` 3.4641016151377544, `false_alarm_rate` 0.057668885622437306, `nominal_rate` 0.002699796063260189. A move exactly equal to the threshold does not fire (KR-13). `false_alarm_rate` is the rate of the trigger as used, with `sigma` estimated from four changes: `P(abs(T_3) > 3)` (spec 1.1.0, KR-232, class `tail_probability`, 1e-11 relative); `nominal_rate` is the known-sigma rate `2 (1 - Phi(k))`, computed as `2 Phi(-k)` (far-tail golden `trig_k-0009`). Observed (2026-11-20 on `k-r2-docs`, Python build through Tutorial 53 Step 2, local laptop, not the acceptance machine): these values to the printed six decimals. K-4c outside share: see `oracle/OUTSIDE_SHARES.md` (the blind matches cover `nominal_rate`).

### Intraday P&L with an error bound

```json
{"schema_version": "1.0", "case_id": "idr", "operation": "risk.intraday.delta_gamma_bound", "inputs": {"positions": [{"notional": 1000000.0, "maturity": 5.0, "yield": 0.04}], "shift": 0.01}}
```

Expected (golden `idr_k-0001`, spec 1.1.0): `estimate_pnl` -39913.124212551615, `bound` 17.056890689308766, `label` "latency-aware analytics on simulated data". The bound is the Lagrange term plus a binary64 rounding allowance (KR-234); it is 1.1e-11 relative above the 1.0.0 value 17.05689068912462. Zero-coupon positions only. Outside check: the version 2 blind packet matched all 11 bounds and 9 of 11 cases (`program/STAGE_K_BLIND_K5A_V2.md`). Observed (2026-11-20 on `k-r2-docs`, Python build (`uv run --locked --project python quantforge batch`), local laptop, not the acceptance machine): the three values above, bit for bit.

### Guard a Richardson extrapolation

```json
{"schema_version": "1.0", "case_id": "rich", "operation": "num.richardson.check", "inputs": {"values": [10.5, 10.125, 10.03125], "ratio": 2.0, "assumed_order": 2.0}}
```

Expected (golden `rich_k-0001`): `status` `OK`, `observed_order` 2.0, `extrapolated` 10.0. Values that do not shrink regularly give `NON_MONOTONE` and no extrapolation (`rich_k-0004`). Observed (observed 2026-11-19 on `k-r1`, Python build (`uv run --locked --project python quantforge batch`), local laptop, not the acceptance machine): `status` `OK`, `observed_order` 2.0, `extrapolated` 10.0, as expected.

### Ask for the smoothed Bermudan ladder

Add `"method": "CN_RANNACHER_SMOOTHED"` to the inputs of `rates.shortrate.bermudan_ladder` or `rates.shortrate.bermudan_swaption`; absent or `G18_IMPLICIT` keeps the G-18 scheme bit for bit, and any other value is `E_SCHEMA` (`program/K8_PORT_NOTE.md`). Inputs otherwise as the stage G goldens; `datasets/golden/stage_k/k8_k.json` has seven value cases, run in all four builds. The default stays `G18_IMPLICIT` (KR-8). **The R6 use restriction stays for both methods: not for hedging** (ruling KR-113, 2026-11-19; `docs/model-inventory.md`, MG-6 and MK-5). Acceptance 1 to 3 pass at 201/100 on three in-sample cases; at 101/50 two of them miss 1%. The ladder row of a curve node the price does not depend on (0.4986 years in the judged cases) is exactly zero and is not judged (owner decision 2026-11-19; `program/K8_ROW0_FINDING.md`: no bug). K-8 outside share: 7 of 7 value cases, by blind re-derivation (`program/STAGE_K_BLIND_K8.md`). Observed (observed 2026-11-19 on `k-r1`, Python build (`uv run --locked --project python quantforge batch`), local laptop, not the acceptance machine): the inputs of `k8_k-0001` with `method` `CN_RANNACHER_SMOOTHED` returned the golden's `price` 22737.43110152093 and every ladder entry bit for bit (about 3 s); the same inputs with `method` `CN_RANNACHER` returned `E_SCHEMA` ("method: CN_RANNACHER is not listed").

### SA-CCR EAD for a netting set

```json
{"schema_version": "1.0", "case_id": "saccr", "operation": "risk.saccr.ead", "inputs": {"trades": [{"id": "1", "asset_class": "IR", "notional": 10000, "market_value": 30, "maturity": 10, "position": "LONG", "start": 0, "end": 10, "hedging_set": "USD"}, {"id": "2", "asset_class": "IR", "notional": 10000, "market_value": -20, "maturity": 4, "position": "SHORT", "start": 0, "end": 4, "hedging_set": "USD"}, {"id": "3", "asset_class": "IR", "notional": 5000, "market_value": 50, "maturity": 11, "position": "BOUGHT", "kind": "OPTION", "option_type": "PUT", "underlying_price": 0.06, "strike": 0.05, "exercise": 1, "start": 1, "end": 11, "hedging_set": "EUR"}]}}
```

Expected (golden `saccr_k-0001`, Basel CRE99 Example 1): `ead` 569.4701409373457, `rc` 60, `pfe` 346.76438638381836, `multiplier` 1, hedging-set add-ons EUR 50.4145690652664 and USD 296.34981731855197. Worked step by step in [Tutorial 56](docs/getting-started/tutorial-56-sa-ccr-example-1.md). SA-CCR outside share: 12 of 19 value cases (`oracle/OUTSIDE_SHARES.md`, generated): the 5 published examples through the blind packet that re-derived them (`program/STAGE_K_BLIND_PUB.md`; a printed figure alone does not count, KR-250) and 7 blind re-derivations (`program/STAGE_K_BLIND_W1B.md`). Observed (observed 2026-11-19 on `k-r1`, Python build (`uv run --locked --project python quantforge batch`), local laptop, not the acceptance machine): `ead` 569.4701409373457, `rc` 60.0 and `multiplier` 1.0 as expected; `pfe` 346.7643863838184 and the add-ons EUR 50.414569065266406 and USD 296.349817318552 differ from the golden in the last digit or two, inside the tolerance.

### Backtesting zone and desk eligibility

```json
{"schema_version": "1.0", "case_id": "zone", "operation": "risk.frtb.backtest.zone", "inputs": {"observations": 250, "exceptions_actual": 3, "exceptions_hypothetical": 5}}
{"schema_version": "1.0", "case_id": "desk", "operation": "risk.frtb.backtest.desk", "inputs": {"observations": 250, "exceptions_99_actual": 13, "exceptions_99_hypothetical": 0, "exceptions_975_actual": 0, "exceptions_975_hypothetical": 0}}
```

Expected (spec worked example and golden `btk_k-0020`): the first gives `exceptions` 5, `zone` `AMBER`, `amber_from` 5, `red_from` 10, `multiplier` 1.7; the second `breach_99` true, `eligible` false. To count exceptions from series, send `risk.frtb.backtest.count` with `var`, `actual` and `hypothetical` arrays (a null counts as an exception; a loss equal to VaR does not). K-8e outside share: 23 of 28 value cases (`oracle/OUTSIDE_SHARES.md`, generated): the 12 MAR99 Table 2 cases through the blind packet that re-derived them (`program/STAGE_K_BLIND_PUB.md`; a printed figure alone does not count, KR-250) and 11 by blind re-derivation (`program/STAGE_K_BLIND_BTK.md`). Observed (observed 2026-11-19 on `k-r1`, Python build (`uv run --locked --project python quantforge batch`), local laptop, not the acceptance machine): zone `exceptions` 5, `cumulative_probability` 0.9588168159302313, `zone` `AMBER`, `amber_from` 5, `red_from` 10, `multiplier` 1.7; desk `exceptions_99` 13, `breach_99` true, `breach_975` false, `eligible` false, as expected.

### Verify the daily paper ledger (not yet runnable)

```bash
git fetch origin paper-ledger paper-ledger-anchors
git show origin/paper-ledger:ledger/ledger.jsonl > ledger.jsonl
python tools/paper_daily/verify_ledger.py verify --ledger ledger.jsonl --no-cli         # from the ledger alone
python tools/paper_daily/verify_ledger.py verify --ledger ledger.jsonl --anchors A --forward-log F --bitcoin-headers H --require-days 20
```

`--no-cli` checks the chain, the configuration, the dates and holdout windows, and replays every day in exact decimal from the ledger's own numbers; the full run also rebuilds each day through the CLI. The tool is merged (`tools/paper_daily/verify_ledger.py`, spec `specifications/12-platform/paper-ledger-daily.md`). The workflow is scheduled on main since 2026-11-20 (pull request #59), and its first run creates the `paper-ledger` branch; on 2026-11-20 the branch did not exist yet (`git ls-remote origin`, read by the docs lane), so **0 of 20 recorded trading days.** Every row is labelled "paper marks on a fitted curve; not tradable"; no performance claim is made. Not run: there is no ledger to fetch (2026-11-19, `k-r1`). Checked only that `verify_ledger.py --help` lists the `verify` command and the `--ledger`, `--no-cli` and `--require-days` options used above.

### Stage K desk recipes

Tasks a desk user would do with the stage K operations and the jobs around them, each worked by hand and then run. Commands run from the repository root in Git Bash or a Unix shell and send the lines between `<<'EOF'` and `EOF` to the Python build in one batch. The outputs shown were observed on 2026-11-20 on branch `k-v1-docs2` with the Python build (`uv run --locked --project python quantforge batch`), local laptop, not the acceptance machine; the other three builds return the same values within each golden's tolerance in conformance. Every input below is synthetic or comes from a named golden; dates in requests are moved to 2027 so that this page carries no date inside a preregistered holdout window (`research/test_preregs.py`). They were run once by hand for this page; the blocks marked `cookbook:run` (the incremental update, the SA-CCR netting sets and the two-fault errors) are rerun by `python tools/check_cookbook.py`, which no workflow runs yet.

#### Correct a past value and prove that earlier as-of answers do not change

Plain idea: when a correction arrives, append it with the time you learned it; never overwrite. A report rerun as of an earlier date must then give the number it gave then.

Formal statement (`specifications/01-core/bitemporal-store.md`, KR-2, KR-4): the answer at `(K, V)` depends only on records with `knowledge_time <= K`, so appending a record with a later knowledge time cannot change it. Here record 3 corrects February from 100 to 105 and is learned on 1 April.

```bash
uv run --locked --project python quantforge batch <<'EOF'
{"schema_version":"1.0","case_id":"mar_before","operation":"core.store.bitemporal_query","inputs":{"records":[{"sequence":1,"series_id":"A","valid_from":"2027-01-01T00:00:00Z","valid_to":null,"knowledge_time":"2027-01-02T00:00:00Z","value":100},{"sequence":2,"series_id":"A","valid_from":"2027-03-01T00:00:00Z","valid_to":null,"knowledge_time":"2027-03-02T00:00:00Z","value":110}],"series_id":"A","knowledge_as_of":"2027-03-15T00:00:00Z","valid_at":"2027-02-15T00:00:00Z"}}
{"schema_version":"1.0","case_id":"apr_after","operation":"core.store.bitemporal_query","inputs":{"records":[{"sequence":1,"series_id":"A","valid_from":"2027-01-01T00:00:00Z","valid_to":null,"knowledge_time":"2027-01-02T00:00:00Z","value":100},{"sequence":2,"series_id":"A","valid_from":"2027-03-01T00:00:00Z","valid_to":null,"knowledge_time":"2027-03-02T00:00:00Z","value":110},{"sequence":3,"series_id":"A","valid_from":"2027-02-01T00:00:00Z","valid_to":"2027-03-01T00:00:00Z","knowledge_time":"2027-04-01T00:00:00Z","value":105}],"series_id":"A","knowledge_as_of":"2027-04-01T00:00:00Z","valid_at":"2027-02-15T00:00:00Z"}}
{"schema_version":"1.0","case_id":"mar_after","operation":"core.store.bitemporal_query","inputs":{"records":[{"sequence":1,"series_id":"A","valid_from":"2027-01-01T00:00:00Z","valid_to":null,"knowledge_time":"2027-01-02T00:00:00Z","value":100},{"sequence":2,"series_id":"A","valid_from":"2027-03-01T00:00:00Z","valid_to":null,"knowledge_time":"2027-03-02T00:00:00Z","value":110},{"sequence":3,"series_id":"A","valid_from":"2027-02-01T00:00:00Z","valid_to":"2027-03-01T00:00:00Z","knowledge_time":"2027-04-01T00:00:00Z","value":105}],"series_id":"A","knowledge_as_of":"2027-03-15T00:00:00Z","valid_at":"2027-02-15T00:00:00Z"}}
EOF
```

Output, key fields: `mar_before` `FOUND`, `row.sequence` 1, `row.value` 100; `apr_after` `FOUND`, sequence 3, value 105; `mar_after` `FOUND`, sequence 1, value 100. The third line is the check: the log now holds the correction, and the March answer is still the March answer, row for row. This is the log of golden `bt_k-0002` with every date one year later and its record 4 left out. Limits: one series, one pair of times per request; the acceptance property behind it (10,000 logs, 500,000 query pairs, 0 failures) is in `program/stage_k_w1/acceptance_python.json`, key `kr4_correction_property` (measured).

#### Update one curve node incrementally and compare with a full rebuild

Plain idea: when the 2-year quote ticks, the 1-year pillar cannot move, so copy it and solve only the 2-year and 3-year pillars. The result must be the same bits as rebuilding the whole curve, and a cache from somewhere else must be refused.

Formal statement (`specifications/02-curves/incremental-update.md`, KR-5): `P_k = (1 - S_k sum_{i<k} P_i) / (1 + S_k)`. By hand for quotes 2%, 2.6%, 3%: `P_1 = 1/1.02 = 0.980392`, `P_2 = (1 - 0.026 x 0.980392) / 1.026 = 0.949815`, `P_3 = (1 - 0.03 x (0.980392 + 0.949815)) / 1.03 = 0.914654`.

<!-- cookbook:run -->
```bash
uv run --locked --project python quantforge batch <<'EOF'
{"schema_version":"1.0","case_id":"incremental","operation":"curve.incremental.update","inputs":{"previous_quotes":[0.02,0.025,0.03],"previous_discount_factors":[0.9803921568627451,0.9516977522716404,0.9145993230349208],"new_quotes":[0.02,0.026,0.03]}}
{"schema_version":"1.0","case_id":"full_rebuild","operation":"curve.bootstrap.par_annual","inputs":{"quotes":[0.02,0.026,0.03]}}
{"schema_version":"1.0","case_id":"stale_cache","operation":"curve.incremental.update","inputs":{"previous_quotes":[0.02,0.025,0.03],"previous_discount_factors":[0.9803921568627451,0.9516977522716404,0.9145993230349209],"new_quotes":[0.02,0.026,0.03]}}
EOF
```
<!-- cookbook:expect
"case_id":"full_rebuild","status":"ok","outputs":{"discount_factors":[0.9803921568627451,0.9498146237052325,0.9146541714397676]}
"code":"E_INPUT"
-->

```json
{"schema_version":"1.0","case_id":"incremental","status":"ok","outputs":{"discount_factors":[0.9803921568627451,0.9498146237052325,0.9146541714397676],"first_changed_index":1,"recomputed":2},"diagnostics":{}}
{"schema_version":"1.0","case_id":"full_rebuild","status":"ok","outputs":{"discount_factors":[0.9803921568627451,0.9498146237052325,0.9146541714397676]},"diagnostics":{}}
{"schema_version":"1.0","case_id":"stale_cache","status":"error","error":{"code":"E_INPUT","message":"previous_discount_factors is not the bootstrap of previous_quotes","field":"previous_discount_factors"},"diagnostics":{}}
```

The incremental and full answers are the same three binary64 numbers. The golden `inc_k-0002` states the last two as `...2326` and `...7677` (the 30-digit value rounded once); the build's `...2325` and `...7676` are one unit in the last place away, inside the 1e-15 absolute tolerance. The third line moves the cached last pillar by one unit in the last place (as golden `inc_k-0006` does) and is refused. Limits: the operation re-runs the previous bootstrap to check the cache, so it is never faster than one rebuild; the saving is in the library entry points without the check (`ois.bootstrap_incremental` in Python), measured bit-identical on 10,000 of 10,000 moves in each build (`program/STAGE_K_W1_HANDOVER.md`, key `incremental_property_stage_b_patched`).

#### SA-CCR EAD for a small netting set, by hand and by CLI

Plain idea: SA-CCR exposure is 1.4 times (what the netting set is worth to us now, floored at zero, plus a supervisory add-on for how much it could grow). Trades in the same currency and maturity bucket offset in full.

Formal statement (`specifications/06-risk/sa-ccr.md`, CRE52 read 2026-11-19 by the SA-CCR lane). For an interest-rate trade from `S` to `E` years: supervisory duration `SD = (exp(-0.05 S) - exp(-0.05 E)) / 0.05`, adjusted notional `d = N x SD`, maturity factor `MF = sqrt(min(M, 1))` unmargined, delta +1 long and -1 short, effective notional `D = delta x d x MF`. Inside a currency the bucket sums `D_1` (under 1 year), `D_2` (1 to 5), `D_3` (over 5) combine as `sqrt(D_1^2 + D_2^2 + D_3^2 + 1.4 D_1 D_2 + 1.4 D_2 D_3 + 0.6 D_1 D_3)`; the add-on is 0.5% of that. `RC = max(V - C, 0)`, multiplier `m = min(1, 0.05 + 0.95 exp((V - C) / (2 x 0.95 x AddOn)))`, `PFE = m x AddOn`, `EAD = 1.4 (RC + PFE)`.

By hand, a 10-year USD swap received on 10,000 (market value +30) and a 10-year USD swap paid on 5,000 (market value -10), no collateral: `SD = (1 - exp(-0.5)) / 0.05 = 7.869387`; `D_A = 78,693.87`, `D_B = -39,346.93`, both in bucket 3, so `D_3 = 39,346.93` and the effective notional is 39,346.93; add-on `0.005 x 39,346.93 = 196.73`; `V = 20`, `RC = 20`, `m = 1`; `EAD = 1.4 x (20 + 196.73) = 303.43`. If the set were worth -310 to us instead (the long swap at -300), `RC = 0` and `m = 0.05 + 0.95 exp(-310 / 373.80) = 0.4645`, so `EAD = 1.4 x 0.4645 x 196.73 = 127.94`.

<!-- cookbook:run -->
```bash
uv run --locked --project python quantforge batch <<'EOF'
{"schema_version":"1.0","case_id":"set_plus","operation":"risk.saccr.ead","inputs":{"trades":[{"id":"A","asset_class":"IR","notional":10000,"market_value":30,"maturity":10,"position":"LONG","start":0,"end":10,"hedging_set":"USD"},{"id":"B","asset_class":"IR","notional":5000,"market_value":-10,"maturity":10,"position":"SHORT","start":0,"end":10,"hedging_set":"USD"}]}}
{"schema_version":"1.0","case_id":"set_minus","operation":"risk.saccr.ead","inputs":{"trades":[{"id":"A","asset_class":"IR","notional":10000,"market_value":-300,"maturity":10,"position":"LONG","start":0,"end":10,"hedging_set":"USD"},{"id":"B","asset_class":"IR","notional":5000,"market_value":-10,"maturity":10,"position":"SHORT","start":0,"end":10,"hedging_set":"USD"}]}}
EOF
```
<!-- cookbook:expect
"ead":303.4285382011566
"ead":127.94333326981402
"multiplier":0.4645246062932369
-->

Output, key fields: `set_plus` `ead` 303.4285382011566, `rc` 20.0, `pfe` 196.7346701436833, `multiplier` 1.0, trade A `supervisory_duration` 7.8693868057473315 and `effective_notional` 78693.86805747332, trade B `effective_notional` -39346.93402873666; `set_minus` `ead` 127.94333326981402, `rc` 0.0, `multiplier` 0.4645246062932369. Both agree with the hand figures. These two netting sets are not goldens; for a published check, run golden `saccr_k-0001` (Basel CRE99 Example 1, EAD 569.47, worked in [Tutorial 56](docs/getting-started/tutorial-56-sa-ccr-example-1.md)). Limits: no margin agreement here; scope limits KR-39.

#### Count exceptions and read the traffic-light zone

Plain idea: an exception is a day the loss beat the VaR. FRTB counts them on actual and on hypothetical P&L and takes the larger count; the binomial distribution of exceptions for a correct 99% model says when that count is too many.

Formal statement (`specifications/06-risk/frtb-ima-backtest.md`, KR-40 to KR-47; MAR32 and MAR99 read 2026-11-19): day `t` is an exception when the loss `-pnl_t` is strictly greater than `VaR_t`, or when either value is missing; a loss equal to VaR is not one. With `X ~ Binomial(n, 0.01)`, amber starts at the first count with `P(X <= x) >= 0.95` and red at `0.9999`.

Step 1, count. Golden `btk_k-0024`: VaR `[1, 1, null, 2, 0.5]`, actual P&L `[-1, -1.25, 0.3, null, 0]`, hypothetical `[-1.5, 0, 0.1, -2.5, -0.5]`. By hand, actual: day 0 loses exactly the VaR (not an exception), day 1 loses 1.25 (exception), day 2 has no VaR and day 3 no P&L (both exceptions); hypothetical: days 0, 2 and 3. Step 2, the zone for 0 to 11 exceptions in 250 days.

```bash
{ echo '{"schema_version":"1.0","case_id":"count","operation":"risk.frtb.backtest.count","inputs":{"var":[1.0,1.0,null,2.0,0.5],"actual":[-1.0,-1.25,0.3,null,0.0],"hypothetical":[-1.5,0.0,0.1,-2.5,-0.5]}}'
  for x in 0 1 2 3 4 5 6 7 8 9 10 11; do echo "{\"schema_version\":\"1.0\",\"case_id\":\"zone$x\",\"operation\":\"risk.frtb.backtest.zone\",\"inputs\":{\"observations\":250,\"exceptions_actual\":$x,\"exceptions_hypothetical\":0}}"; done
} | uv run --locked --project python quantforge batch
```

`count` returns `days_actual` `[1, 2, 3]`, `days_hypothetical` `[0, 2, 3]`, `exceptions` 3, as worked. The zone lines, read from the output:

| Exceptions | `cumulative_probability` | `zone` | `multiplier` |
|---|---|---|---|
| 0 | 0.08105851616218145 | GREEN | 1.5 |
| 4 | 0.8921876269036252 | GREEN | 1.5 |
| 5 | 0.9588168159301516 | AMBER | 1.7 |
| 6 | 0.9862985521447962 | AMBER | 1.76 |
| 9 | 0.9997498099312594 | AMBER | 1.92 |
| 10 | 0.9999461013709529 | RED | 2.0 |

Every line also says `amber_from` 5 and `red_from` 10. How to read it: with 4 exceptions a correct model is still well inside its own distribution (89.2% of correct models would show 4 or fewer); at 5 the chance of 5 or fewer first reaches 95%. A correct model still shows 5 or more about 1 time in 9 (`1 - 0.8922 = 10.8%`), which is why amber means "look", not "wrong"; red starts at 10, the first count with `P(X <= x)` at or above 99.99% (0.99995 at 10, 0.99975 at 9), so 10 or more happens to a correct model 2.5 times in 10,000 (`1 - 0.99975`). The multipliers are MAR32 Table 1's for 250 days. Golden for the 5-exception line: `btk_k-0006`, expected `cumulative_probability` 0.9588168159301517, one unit in the last place from the Python output, inside the tolerance (the probabilities follow ruling KR-237's arithmetic-only recurrence). An earlier recipe observed 0.9588168159302313 on 2026-11-19, before that ruling's code was merged (inferred from the dates). Limits: the zone is a statement about a 99% VaR model under independence of exceptions; clustering of exceptions is not tested here (that is the Christoffersen test of stage F).

#### Check the intraday bound against full revaluation

Plain idea: the delta-gamma estimate is fast; the bound says how far it can be from revaluing the position. Check it yourself by revaluing.

Formal statement (`specifications/06-risk/intraday-risk-bounds.md` 1.1.0, KR-7, KR-15, KR-234): for `V(y) = N exp(-y T)` the estimate is `V (-T h + T^2 h^2 / 2)` and the Lagrange part of the bound is `|h|^3 T^3 |N| exp(-T min(y, y + h)) / 6`, plus a binary64 rounding allowance.

```bash
uv run --locked --project python quantforge batch <<'EOF'
{"schema_version":"1.0","case_id":"move_1pct","operation":"risk.intraday.delta_gamma_bound","inputs":{"positions":[{"notional":1000000.0,"maturity":5.0,"yield":0.04}],"shift":0.01}}
{"schema_version":"1.0","case_id":"move_1bp","operation":"risk.intraday.delta_gamma_bound","inputs":{"positions":[{"notional":1000000.0,"maturity":5.0,"yield":0.04}],"shift":0.0001}}
EOF
python -c "import math; [print(h, 1e6*(math.exp(-(0.04+h)*5)-math.exp(-0.2))) for h in (0.01, 0.0001)]"
```

Output: `move_1pct` `estimate_pnl` -39913.124212551615, `bound` 17.056890689308766 (golden `idr_k-0001`); `move_1bp` `estimate_pnl` -409.2630351948562, `bound` 1.7056892435299685e-05. Full revaluation, from the last line: -39929.97000657694 and -409.2630522495311. Errors: 16.85, which is 98.8% of the bound, and 1.7055e-05, 99.99% of the bound. The bound is close to the error because one zero-coupon position's third derivative barely changes over the move; on a book, bounds are added without netting, so the ratio falls. Limits: zero-coupon positions and parallel moves only; label "latency-aware analytics on simulated data".

#### Catch an edited ledger row and recompute its hash

Plain idea: each ledger row stores the SHA-256 of its own canonical bytes and the hash of the row before it. Change one character and the stored hash no longer fits.

Formal statement (`specifications/10-execution/paper-trading.md`, HR-45, HR-46): `hash = SHA-256(canonical(row without "hash"))`, canonical meaning keys sorted, separators `,` and `:` with no spaces, ASCII escapes; `prev` of row 0 is 64 zeros. The daily paper ledger uses the same rule (`specifications/12-platform/paper-ledger-daily.md`). Golden `pt_h-0021` is a one-row ledger whose `limit_price` was changed from "101" to "102" after hashing.

```bash
python -c "
import json
c = next(c for c in json.load(open('datasets/golden/stage_h/pt_h.json'))['cases'] if c['case_id'] == 'pt_h-0021')
t = c['inputs']['text']
for cid, text in (('as_edited', t), ('restored', t.replace('\"limit_price\":\"102\"', '\"limit_price\":\"101\"', 1))):
    print(json.dumps({'schema_version': '1.0', 'case_id': cid, 'operation': 'paper.ledger.verify', 'inputs': {'text': text}}))
" | uv run --locked --project python quantforge batch
python -c "
import hashlib, json
row = {'body': {'limit_price': '101', 'order_id': 'O1', 'quantity': '3', 'side': 'BUY', 'symbol': 'BTC-USD', 'type': 'LIMIT'}, 'kind': 'ORDER', 'label': 'crypto venue; simulated', 'prev': '0' * 64, 'seq': 0, 'ts': '2026-11-18T00:00:01Z'}
for price in ('101', '102'):
    row['body']['limit_price'] = price
    print(price, hashlib.sha256(json.dumps(row, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest())
"
```

```json
{"schema_version":"1.0","case_id":"as_edited","status":"ok","outputs":{"ok":false,"records":0,"first_bad_seq":0,"reason":"HASH","head":null,"label":"crypto venue; simulated"},"diagnostics":{}}
{"schema_version":"1.0","case_id":"restored","status":"ok","outputs":{"ok":true,"records":1,"first_bad_seq":null,"reason":null,"head":"72c85984abb1b7c4072c65dbba0567b3de51279645b0ad63cfd242137aed7e81","label":"crypto venue; simulated"},"diagnostics":{}}
```

The standard-library lines print `101 72c85984...7e81` (the stored hash) and `102 937f6a4d3baa1a1870e38e7ffb2e7152385de5fcf0b097ebc789238943764e90`. So the verifier is not trusting anything it cannot recompute. Limits: a chain alone does not catch someone who edits a row and recomputes every later hash; that is what the anchors on a separate branch are for (HR-46; for the daily ledger, OpenTimestamps on `paper-ledger-anchors`). The daily ledger has no rows yet: 0 of 20 recorded trading days as of 2026-11-20 13:00 UTC.

#### Explain a day's P&L into carry, roll-down, curve move and costs

Plain idea: a day's change in NAV splits into what the positions earn by the passing of time (carry and roll-down), what the curve's move did to them, and what trading cost. In the daily paper ledger the split must close exactly, with nothing left unexplained.

Formal statement (`specifications/12-platform/paper-ledger-daily.md`, "Daily P&L explain", KR-79), with `n` the opening units and positions struck at par: carry = `sum n x accrued` + cash interest; roll-down = `sum n x (clean_roll - 100)`, where `clean_roll` is the clean price on yesterday's curve one day older; curve move = `sum n x (clean_close - clean_roll)`; fills and costs = `sum s q (100 - p)` minus fees (`s` +1 for a buy). Every term is an exact decimal from recorded 6-decimal marks and whole lots, so `unexplained = total - (carry + roll_down + curve_move + fills_costs)` is exactly 0, a bookkeeping identity rather than a model test.

The command builds the first three days of the synthetic 30-day ledger of `python/tests/test_paper_daily.py` (invented yields from 2027-01-04; not market data) through the job's own code, `tools/paper_daily/paper_core.py`, and prints day 2:

```bash
uv run --locked --project python python -c "
import sys; sys.path.insert(0, 'python/tests')
import test_paper_daily as t
days = t.business_days(3)
row = t.rows_of(t.run_days(days, t.forward_log(t.synthetic_yields(days))))[2]
b = row['body']
print(b['date'], b['nav_open'], b['nav_close'], b['pnl'])
print({k: b['explain'][k] for k in ('carry', 'coupon_accrual', 'cash_interest', 'roll_down', 'curve_move', 'fills_costs', 'total', 'unexplained')})
print(row['hash'])
"
```

Output: `2027-01-05 9999714.0625 9998826.61425 -887.44825`; carry 1213.9355 (coupon accrual 352.1055 plus cash interest 861.83), roll-down 16.5625, curve move -1993.7275, fills and costs -124.21875, total -887.44825, unexplained 0; row hash `06897fde4a8a5a7a787777ec9769827e136257b53007282ae1415732e3eba468`. Check by hand: 1,213.9355 + 16.5625 - 1,993.7275 - 124.21875 = -887.44825 = 9,998,826.61425 - 9,999,714.0625. The cash interest is one day at the previous day's 3-month yield: 7,349,714.0625 x 4.28% / 365 = 861.83 to the cent. The row hash is the one `test_goldens_pl_k` pins, so the day above is the spec's worked day; `uv run --locked --project python pytest python/tests/test_paper_daily.py::test_goldens_pl_k -q` checks it (1 passed, 2026-11-20). Limits: the order rule ignores the market and fills are simulated; label "paper marks on a fitted curve; not tradable"; no performance claim. Replayed by hand in exact decimal in [Tutorial 58](docs/getting-started/tutorial-58-daily-paper-ledger.md).

#### Confirm that the deprecated margin alias gives the same answer

Plain idea: the stage G margin operation was renamed; the old id still works in v1.0.0 and must return exactly what the new id returns.

Formal statement (`specifications/cli-contract.md`, section "Deprecated aliases"; KR-152, KR-256): `xva.simm.ir_delta` runs the handler of `xva.sbim.ir_delta`; it stays in v1.0.0 and is removed in the first release after v1.0.0. The inputs below are those of golden `sbim_alias_k-0001` (placeholder weights `RW = 10 x k`, `rho = 1 - 0.1 abs(k - l)`).

```bash
python -c "
import json
c = json.load(open('datasets/golden/stage_k/sbim_alias_k.json'))['cases'][0]
for op in ('xva.sbim.ir_delta', 'xva.simm.ir_delta'):
    print(json.dumps({'schema_version': '1.0', 'case_id': op, 'operation': op, 'inputs': c['inputs']}))
" | uv run --locked --project python quantforge batch
```

Both lines return `weighted_sensitivities` `[10000.0, -10000.0, 75000.0, 160000.0, -60000.0, 18000.0]`, `concentration_factor` 1.0 and `margin` 190937.1624383268. By hand, the weighted sensitivities are `RW_k x s_k`: 10 x 1,000, 20 x -500, 30 x 2,500, 40 x 4,000, 50 x -1,200, 60 x 300. Limits: placeholder weights; not a margin anyone could post; no ISDA material is used (owner decision 2026-11-19).

#### Which error does a request with two faults get?

Plain idea: every build checks in one fixed order, so two faults give one code everywhere (see [ARCHITECTURE](ARCHITECTURE.md#the-four-build-conformance-model-and-why-two-wrong-inputs-give-one-error)).

<!-- cookbook:run -->
```bash
uv run --locked --project python quantforge batch <<'EOF'
{"schema_version":"1.0","case_id":"e2_k-0008","operation":"calib.trigger.check","inputs":{"changes":[1.0],"x_ref":100.0,"x_now":105.0,"days_since":1.0,"k":0.0}}
{"schema_version":"1.0","case_id":"e2_k-0011","operation":"risk.intraday.delta_gamma_bound","inputs":{"positions":[],"shift":"NaN"}}
EOF
```
<!-- cookbook:expect
"case_id":"e2_k-0008","status":"error","error":{"code":"E_INPUT"
"case_id":"e2_k-0011","status":"error","error":{"code":"E_DOMAIN"
-->

```json
{"schema_version":"1.0","case_id":"e2_k-0008","status":"error","error":{"code":"E_INPUT","message":"changes must hold at least two one-day changes","field":"changes"},"diagnostics":{}}
{"schema_version":"1.0","case_id":"e2_k-0011","status":"error","error":{"code":"E_DOMAIN","message":"shift is not finite","field":"shift"},"diagnostics":{}}
```

The first breaks a structural rule and a domain rule: structural comes first, `E_INPUT`. The second breaks a structural rule and the finite rule: the finite rule comes first, `E_DOMAIN` (KR-230). The goldens compare the code only; the messages are the Python build's.

#### Default risk charge: a short bond does not offset a long stock (wave 2, golden drc_k-0007)

Plain idea: the default risk charge asks what the desk loses if an issuer defaults tomorrow. Longs and shorts of the same issuer offset only when the short is at least as senior as the long, because a defaulted senior bond recovers more than a defaulted share. Here the short is a senior bond and the long is the stock: the bond cannot hedge the stock, so both stay in the bucket, and only the hedge benefit ratio gives some credit.

Formal statement (`specifications/06-risk/frtb-drc-rrao.md`, MAR22 read 2026-11-19 by the spec lane; ruling KR-53, PROPOSED). Gross jump-to-default `JTD = LGD x notional + PnL` with `PnL = market value - notional` (0 here), LGD 100% for equity and 75% for senior debt; net per obligor; `HBR = sum net_long / (sum net_long + sum |net_short|)`; `DRC_b = max(sum RW net_long - HBR sum RW |net_short|, 0)`, risk weight 15% for BB.

By hand: stock `JTD = 1.00 x 50 = 50`, bond `JTD = 0.75 x (-40) = -30`; `HBR = 50 / 80 = 0.625`; weighted long `0.15 x 50 = 7.5`, weighted short `0.15 x 30 = 4.5`; `DRC = 7.5 - 0.625 x 4.5 = 4.6875`.

<!-- cookbook:run -->
```bash
uv run --locked --project python quantforge batch <<'EOF'
{"schema_version":"1.0","case_id":"drc_k-0007","operation":"risk.frtb.drc_nonsec","inputs":{"positions":[{"id":"stock","obligor":"Z","bucket":"CORPORATE","seniority":"EQUITY","notional":50,"market_value":50,"maturity_years":2,"cash_equity":true},{"id":"bond","obligor":"Z","bucket":"CORPORATE","seniority":"SENIOR","notional":-40,"market_value":-40,"maturity_years":2}],"ratings":{"Z":"BB"}}}
EOF
```
<!-- cookbook:expect
"drc":4.6875
"hbr":0.625
-->

Output, key fields (Python build, read 2026-11-20): bond `gross_jtd` -30.0, stock `gross_jtd` 50.0, bucket `hbr` 0.625, `wtd_long` 7.5, `wtd_short` 4.5, `drc` 4.6875, with the label "regulatory formula on caller inputs; not a regulatory return". The golden records the same values, a fractions-and-mpmath oracle and a blind MATCH (`program/STAGE_K_BLIND_W2.md`). Limits: one bucket, and a maturity of at least one year, so no maturity scaling (the spec's Limits section).

#### BA-CVA capital for one counterparty (wave 2, golden cva_k-0001)

Plain idea: CVA capital covers the risk that the market value of a counterparty's default risk moves against the bank. The reduced basic approach multiplies a supervisory risk weight by the exposure, its effective maturity and a discount factor, then scales by a fixed 0.65.

Formal statement (`specifications/06-risk/cva-capital.md`, MAR50 read 2026-11-19 by the spec lane): `DF = (1 - exp(-0.05 M)) / (0.05 M)`, `SCVA = (1 / 1.4) RW M EAD DF` (MAR50.15, RW from MAR50.16 Table 1), `K_reduced = sqrt((0.5 sum SCVA)^2 + 0.75 sum SCVA^2)`, capital `0.65 K_reduced` (MAR50.14), `rwa = 12.5 x capital`.

By hand: financials, investment grade, RW 5%; EAD 1,000,000, M 5. `DF = (1 - e^-0.25) / 0.25 = 0.884797`; `SCVA = 0.05 x 5 x 1,000,000 x 0.884797 / 1.4 = 157,999.44`; with one counterparty `K_reduced = SCVA`; capital `0.65 x 157,999.44 = 102,699.64`.

<!-- cookbook:run -->
```bash
uv run --locked --project python quantforge batch <<'EOF'
{"schema_version":"1.0","case_id":"cva_k-0001","operation":"risk.cva.ba","inputs":{"version":"REDUCED","counterparties":[{"id":"C1","sector":"financials","quality":"IG","netting_sets":[{"ead":1000000,"m":5,"imm":false}]}]}}
EOF
```
<!-- cookbook:expect
"df":0.8847968677143805
"rwa":1283745.4553891683
-->

Output, key fields (Python build, read 2026-11-20): `df` 0.8847968677143805, `scva` and `k_reduced` 157999.44066328224, `capital` 102699.63643113346, `rwa` 1283745.4553891683. The golden's `capital` is 102699.63643113345: the last digit differs, and the case passes inside its stated tolerance. Limits: no hedges (`REDUCED`); the `FULL` version and SA-CVA are in the same spec.

#### Leverage ratio from one derivative netting set (wave 2, golden lev_k-0001)

Plain idea: the leverage ratio is Tier 1 capital over an exposure measure that ignores risk weights, so a bank cannot hold very little capital just because its models call its assets safe. A derivative netting set counts at 1.4 times its replacement cost plus potential future exposure.

Formal statement (`specifications/06-risk/leverage-large-exposures.md`, LEV20 and LEV30 read 2026-11-19 by the spec lane): `RC = max(v - cvm_received + cvm_provided, 0)`, exposure `1.4 (RC + pfe)` per netting set (LEV30.14 to 30.16), `ratio = tier1 / exposure` (LEV20.3), `meets_minimum` when `tier1 >= 0.03 x exposure` (LEV20.7).

By hand, with the netting set of Basel CRE99 Example 1 (V 60, PFE 347): `1.4 x (60 + 347) = 569.8`; `ratio = 100 / 569.8 = 17.55%`, above 3%.

<!-- cookbook:run -->
```bash
uv run --locked --project python quantforge batch <<'EOF'
{"schema_version":"1.0","case_id":"lev_k-0001","operation":"risk.capital.leverage","inputs":{"tier1":100,"on_balance":[],"derivatives":[{"v":60,"cvm_received":0,"cvm_provided":0,"pfe":347}],"written_credit_derivatives":[],"sfts":[],"off_balance":[]}}
EOF
```
<!-- cookbook:expect
"exposure":569.8
"ratio":0.17550017550017552
"meets_minimum":true
-->

Output, key fields (Python build, read 2026-11-20): `derivatives` 569.8, `exposure` 569.8, `ratio` 0.17550017550017552, `meets_minimum` true, label "simplified leverage ratio (LEV30 subset); not a regulatory return". The golden records the Basel printed EAD 569 (CRE99.40) within its stated tolerance of 1.0 and a blind MATCH (`program/STAGE_K_BLIND_K8I.md`). Limits: a simplified subset of LEV30, not a regulatory return.

### Stage K wave 2 capital and xVA recipes

The wave 2 operations (merged to main 2026-11-20, merge 37292e4f; not in a tag) not covered by a recipe above, and the wrong-way-risk CVA of stage G with its KR-257 root fix. The IMA pieces (PLA, ES with liquidity horizons, stress calibration, SES, capital) are worked in [Tutorial 59](docs/getting-started/tutorial-59-frtb-ima-pla-to-capital.md). Every output shown was observed on 2026-11-21 on branch `k-v1-docs-a` with the Python build, local laptop, not the acceptance machine. On that laptop Windows Smart App Control blocks the `quantforge` launcher that `uv` installs, so the lines were sent to `uv run --locked --project python python -m quantforge_core.cli.main batch`, the same entry point; on Linux or macOS use `uv run --locked --project python quantforge batch` as below. Every capital output carries a label such as "regulatory formula on caller inputs; not a regulatory return". Every block in this section and the next is marked `cookbook:run` and rerun by `python tools/check_cookbook.py`, which checks the numbers named in the output lines below (no workflow runs it yet).

#### Residual risk add-on: what counts and what is excluded (golden rrao_k-0002)

Plain idea: the RRAO is a blunt charge on gross notional for risks the sensitivities do not see: 1% for exotic underlyings (weather, longevity, realised volatility), 0.1% for other residual risks (barriers, baskets, Bermudans). Back-to-back hedged trades, and "other" instruments that are listed or clearable, are excluded.

Formal statement (`specifications/06-risk/frtb-drc-rrao.md`, MAR23.7 and MAR23.8(2) read 2026-11-19 by the spec lane): `RRAO = sum gross_notional x (0.01 for EXOTIC, 0.001 for OTHER)` over the instruments not excluded. Classifying an instrument is the caller's job.

By hand: the listed OTHER of 5,000,000 is excluded; the listed EXOTIC of 1,000,000 is not (listing excludes only OTHER), so it adds 10,000; the back-to-back EXOTIC of 3,000,000 is excluded. RRAO 10,000.

<!-- cookbook:run -->
```bash
uv run --locked --project python quantforge batch <<'EOF'
{"schema_version":"1.0","case_id":"rrao","operation":"risk.frtb.rrao","inputs":{"instruments":[{"id":"o","gross_notional":5000000,"kind":"OTHER","listed_or_clearable":true,"back_to_back":false},{"id":"e1","gross_notional":1000000,"kind":"EXOTIC","listed_or_clearable":true,"back_to_back":false},{"id":"e2","gross_notional":3000000,"kind":"EXOTIC","listed_or_clearable":false,"back_to_back":true}]}}
EOF
```
<!-- cookbook:expect
"rrao":10000.0
"id":"e2","weight":0.01,"excluded":true
-->

Output, key fields: instruments `o` weight 0.001 `excluded` true, `e1` weight 0.01 `excluded` false `addon` 10000.0, `e2` `excluded` true; `rrao` 10000.0, as worked and as the golden.

#### Securitisation DRC: two tranches of one pool do not offset (golden sec_k-0001)

Plain idea: for securitisations the jump-to-default is the market value (no recovery assumption), and a long and a short offset only when they are the same tranche of the same pool. Different tranches of one pool lose differently in a default, so they only hedge each other through the hedge benefit ratio.

Formal statement (`specifications/06-risk/frtb-drc-rrao.md`, MAR22.27 to 22.35, KR-55): `JTD = market value`; net within identical `pool` and `tranche`; `HBR = sum net_long / (sum net_long + sum |net_short|)`; `DRC_b = max(sum RW net_long - HBR sum RW |net_short|, 0)`. The risk weight is the caller's (`rw_source` says "securitisation risk weights supplied by the caller (CRE40-CRE44 not implemented)").

By hand, long 50 of tranche T1 and short 20 of tranche T2, RW 20%: `HBR = 50 / 70 = 0.7143`; weighted long 10, weighted short 4; `DRC = 10 - 0.7143 x 4 = 7.1429`. If the short were the same tranche T1, the two would net to a long of 30 and `DRC = 0.2 x 30 = 6`.

<!-- cookbook:run -->
```bash
uv run --locked --project python quantforge batch <<'EOF'
{"schema_version":"1.0","case_id":"sec","operation":"risk.frtb.drc_sec_nonctp","inputs":{"positions":[{"id":"l","bucket":"RMBS-EU","pool":"P1","tranche":"T1","market_value":50,"maturity_years":5,"rw":0.2},{"id":"s","bucket":"RMBS-EU","pool":"P1","tranche":"T2","market_value":-20,"maturity_years":5,"rw":0.2}]}}
{"schema_version":"1.0","case_id":"sec_same","operation":"risk.frtb.drc_sec_nonctp","inputs":{"positions":[{"id":"l","bucket":"RMBS-EU","pool":"P1","tranche":"T1","market_value":50,"maturity_years":5,"rw":0.2},{"id":"s","bucket":"RMBS-EU","pool":"P1","tranche":"T1","market_value":-20,"maturity_years":5,"rw":0.2}]}}
EOF
```
<!-- cookbook:expect
"case_id":"sec","status":"ok"
"drc":7.142857142857142
"hbr":1.0,"wtd_long":6.0,"wtd_short":0.0,"drc":6.0
-->

Output, key fields: `sec` bucket `hbr` 0.7142857142857143, `wtd_long` 10.0, `wtd_short` 4.0, `drc` 7.142857142857142; `sec_same` `hbr` 1.0, `wtd_long` 6.0, `drc` 6.0. The golden `sec_k-0001` states `drc` 7.142857142857143, one unit in the last place from the output, inside its tolerance. The second line is not a golden; it is the same input with one tranche label changed.

#### Correlation trading DRC: a negative bucket gives half credit (golden ctp_k-0002)

Plain idea: in the correlation trading portfolio a short in one index can partly offset a long in another. Each index bucket's DRC may go negative, and a negative bucket reduces the total at half weight.

Formal statement (`specifications/06-risk/frtb-drc-rrao.md`, MAR22.39 to 22.45): net within identical `index`, `series` and `tranche`; `HBR_ctp` over all CTP net positions together; `DRC_b = sum RW net_long - HBR_ctp sum RW |net_short|` with no floor; `DRC_CTP = max(sum_b (max(DRC_b, 0) + 0.5 min(DRC_b, 0)), 0)`.

By hand, long 1,000 of index A and short 1,000 of index B, RW 10%: `HBR_ctp = 1000 / 2000 = 0.5`; `DRC_A = 100`, `DRC_B = -0.5 x 100 = -50`; total `100 + 0.5 x (-50) = 75`.

<!-- cookbook:run -->
```bash
uv run --locked --project python quantforge batch <<'EOF'
{"schema_version":"1.0","case_id":"ctp","operation":"risk.frtb.drc_ctp","inputs":{"positions":[{"id":"a","index":"A","series":"S1","tranche":"T1","market_value":1000,"maturity_years":5,"rw":0.1},{"id":"b","index":"B","series":"S1","tranche":"T1","market_value":-1000,"maturity_years":5,"rw":0.1}]}}
EOF
```
<!-- cookbook:expect
"hbr_ctp":0.5
"bucket":"B","wtd_long":0.0,"wtd_short":100.0,"drc":-50.0
"drc":75.0
-->

Output, key fields: `hbr_ctp` 0.5, bucket A `drc` 100.0, bucket B `drc` -50.0, `drc` 75.0, as worked and as the golden. To check the aggregation alone, send `{"bucket_drc": [100, -100]}` (golden `ctp_k-0001`, the MAR22.45 printed example): 50.

#### SA-CVA interest-rate delta, with and without a hedge (goldens sacva_k-0001 and sacva_k-0002)

Plain idea: SA-CVA charges how the bank's CVA moves with market factors. Hedges net against the CVA sensitivities, but the formula keeps 1% of the squared hedge sensitivities as a floor term, so even a perfect hedge leaves a charge.

Formal statement (`specifications/06-risk/cva-capital.md`, MAR50.51 to 50.53, KR-62): `WS_k = RW_k s_cva_k - RW_k s_hdg_k`, `WSH_k = RW_k s_hdg_k`, `K_b = sqrt(max(0, sum WS_k^2 + sum_{k != l} rho_kl WS_k WS_l + 0.01 sum WSH_k^2))`. USD is a specified currency: RW 1.11% at 1Y and 0.74% at 5Y, `rho(1Y, 5Y) = 72%` (spec worked example).

By hand without a hedge: `WS_1Y = 11,100`, `WS_5Y = -14,800`; `K_b^2 = 11,100^2 + 14,800^2 - 2 x 0.72 x 11,100 x 14,800 = 105,686,800`, `K_b = 10,280.41`. With a 5Y hedge sensitivity of -1,500,000: `WS_5Y = -3,700`, hedge term `0.01 x 11,100^2`, `K_b = 8,887.70`. With hedges equal to both CVA sensitivities, every `WS_k` is 0 and `K_b = 0.1 sqrt(11,100^2 + 14,800^2) = 1,850`.

<!-- cookbook:run -->
```bash
uv run --locked --project python quantforge batch <<'EOF'
{"schema_version":"1.0","case_id":"sacva_nohedge","operation":"risk.cva.sa","inputs":{"m_cva":1,"reporting_currency":"USD","classes":{"IR.DELTA":[{"bucket":"USD","factor":"1Y","s_cva":1000000,"s_hdg":0},{"bucket":"USD","factor":"5Y","s_cva":-2000000,"s_hdg":0}]}}}
{"schema_version":"1.0","case_id":"sacva_hedge","operation":"risk.cva.sa","inputs":{"m_cva":1,"reporting_currency":"USD","classes":{"IR.DELTA":[{"bucket":"USD","factor":"1Y","s_cva":1000000,"s_hdg":0},{"bucket":"USD","factor":"5Y","s_cva":-2000000,"s_hdg":-1500000}]}}}
{"schema_version":"1.0","case_id":"sacva_perfect","operation":"risk.cva.sa","inputs":{"m_cva":1,"reporting_currency":"USD","classes":{"IR.DELTA":[{"bucket":"USD","factor":"1Y","s_cva":1000000,"s_hdg":1000000},{"bucket":"USD","factor":"5Y","s_cva":-2000000,"s_hdg":-2000000}]}}}
EOF
```
<!-- cookbook:expect
"k_b":10280.408552192855
"k_b":8887.704990603592
"k_b":1850.0
"rwa":23125.0
-->

Output, key fields: `sacva_nohedge` `k_b` 10280.408552192855, `total` 10280.408552192855, `rwa` 128505.1069024107; `sacva_hedge` `k_b` 8887.704990603592, `rwa` 111096.3123825449; `sacva_perfect` `k_b` 1850.0, `rwa` 23125.0. The first two equal their goldens; the third is not a golden and shows the floor term. Limits: every sensitivity is an input; there is no CVA model behind it (spec, Limits).

#### Large exposures: a trading book short of a junior claim offsets a senior bond (golden lex_k-0004)

Plain idea: the large exposures rule caps what a bank can lose if one counterparty, or one connected group, fails, at 25% of Tier 1; 10% or more must be reported. In the trading book it assumes nothing is recovered, and a short position offsets a long only if the short is not more senior.

Formal statement (`specifications/06-risk/leverage-large-exposures.md`, LEX10, LEX20 and LEX30 read 2026-11-19 by the spec lane): trading book JTD with LGD 1 (LEX30.17); offsets per counterparty by the seniority rule; a net short counts 0; exposure = banking book + converted off balance sheet + trading book net long - protected + received as provider; `large` when exposure >= 0.10 Tier 1, `breach` when exposure > 0.25 Tier 1 (0.15 between G-SIBs).

By hand, Tier 1 1,000: a loan of 200 to issuer G; a long senior bond of G, face 100, market value 90: JTD `100 + (90 - 100) = 90`; a short of G stock, -30. The stock is junior to the bond, so it offsets: net long 60. Exposure `200 + 60 = 260`, 26% of Tier 1: large and in breach.

<!-- cookbook:run -->
```bash
uv run --locked --project python quantforge batch <<'EOF'
{"schema_version":"1.0","case_id":"lex","operation":"risk.capital.large_exposures","inputs":{"tier1":1000,"bank_gsib":false,"counterparties":[{"id":"G"}],"banking_book":[{"counterparty":"G","value":200}],"off_balance":[],"crm":[],"trading_book":[{"id":"bond","counterparty":"G","seniority":"SENIOR","notional":100,"market_value":90,"maturity_years":5},{"id":"stock","counterparty":"G","seniority":"EQUITY","notional":-30,"market_value":-30,"maturity_years":1,"cash_equity":true}]}}
EOF
```
<!-- cookbook:expect
"trading_book_net_long":60.0
"exposure":260.0,"share":0.26,"large":true,"limit":250.0,"breach":true
-->

Output, key fields: counterparty G `banking_book` 200.0, `trading_book_net_long` 60.0, `exposure` 260.0; group G `share` 0.26, `large` true, `limit` 250.0, `breach` true; `report` `["G"]`; label "simplified large exposures (LEX subset); not a regulatory return". Under MAR22 the same bond would have LGD 75% and JTD 65 (spec worked example); the large exposures rule assumes no recovery.

#### Wrong-way-risk CVA: how the CVA moves with the dependence parameter (goldens wwr_g-0001 to wwr_g-0004, wwr_g-0007)

Plain idea: ordinary CVA assumes the counterparty's default is independent of the exposure. Wrong-way risk is when the counterparty is more likely to default exactly when the bank is owed most. The Hull-White model makes the hazard rate on each simulated path grow with the exposure on that path, `exp(a(t) + b V(t))`, and recalibrates `a(t)` so the average survival still matches the counterparty's credit curve. `b > 0` is wrong way, `b < 0` right way, `b = 0` independent.

Formal statement (`specifications/06-risk/xva-framework.md`, ruling G-44; J. Hull and A. White, "CVA and wrong-way risk", 2012, recalled through the spec): on path `p` the hazard in bucket `i` is `exp(a_i + b V_p(t_i))`; `a_i` solves `mean_p S_p(t_i) = e^(-h t_i)`; `CVA = (1 - R) sum_i D_i mean_p[max(V_p(t_i), 0) (S_p(t_(i-1)) - S_p(t_i))]`. Ruling KR-257 (confirmed 2026-11-20) fixed the root: before it, large `|b V|` returned an unconverged `a` and CVA 0 without an error in Python and Rust.

By hand at `b = 0`: every path has hazard `h = 0.03`, so `a_i = ln 0.03 = -3.506558` and the CVA is the independent one on the path-mean positive exposure `EE = (1.125, 2.75, 3.375, 2.75)`: `0.6 x sum D_i EE_i (e^(-0.03 t_(i-1)) - e^(-0.03 t_i)) = 0.0436277` (standard-library line, 0.043627733225243444). For identical exposure on every path (KR-257 closed form) `a_i = ln h - b V`: with `h = 0.01`, `b = 1`, `V = 10`, `a = ln 0.01 - 10 = -14.605170` and `CVA = 0.6 x 10 x (0.97 (1 - e^-0.01) + 0.94 (e^-0.01 - e^-0.02)) = 0.113471`.

<!-- cookbook:run -->
```bash
{ for b in 0.0 0.1 0.3 -0.2; do echo "{\"schema_version\":\"1.0\",\"case_id\":\"b=$b\",\"operation\":\"xva.wwr.cva_hw\",\"inputs\":{\"times\":[0.25,0.5,0.75,1.0],\"values\":[[3.0,5.0,2.0,-1.0],[-2.0,-4.0,-6.0,-3.0],[1.0,6.0,9.0,4.0],[0.5,-1.0,2.5,7.0]],\"discount_factors\":[0.995,0.99,0.985,0.98],\"hazard_rate\":0.03,\"recovery\":0.4,\"wwr_b\":$b}}"; done
  echo '{"schema_version":"1.0","case_id":"flat","operation":"xva.wwr.cva_hw","inputs":{"times":[1.0,2.0],"values":[[10.0,10.0],[10.0,10.0]],"discount_factors":[0.97,0.94],"hazard_rate":0.01,"recovery":0.4,"wwr_b":1.0}}'
  echo '{"schema_version":"1.0","case_id":"too_big","operation":"xva.wwr.cva_hw","inputs":{"times":[1.0,2.0],"values":[[10.0,10.0],[800.0,10.0]],"discount_factors":[0.97,0.94],"hazard_rate":0.01,"recovery":0.4,"wwr_b":1.0}}'
} | uv run --locked --project python quantforge batch
```
<!-- cookbook:expect
"cva":0.043627733225243
"cva":0.061148353888627
"cva":0.086487304714250
"cva":0.015569211034720
"cva":0.11347051247504
"a":[-14.605170185988
"code":"E_DOMAIN"
-->

The table shows the Windows output (local laptop, 2026-11-21). On the Linux GitHub runner (Docs run 44895037149) two values differ in the 16th and 17th significant digits: `b = 0.1` gives 0.061148353888627785 and `b = -0.2` gives 0.015569211034720722 (the root finder and `exp` round differently across platforms). The recipe check asserts the first 14 significant digits, which both platforms print. Why this is allowed: [docs/determinism.md](docs/determinism.md) claims bit-for-bit equality only for integer, date, enum and error outputs; a real output such as `cva` is compared within its golden tolerance (class `root_finding` in `wwr_g`, 1e-9 absolute plus 1e-12 relative), and the cross-platform gap here, about 4e-17 at `b = 0.1` (measured from the two printed values), is far inside it.

| Case | `wwr_b` | `cva` | `a` first bucket | Golden |
|---|---|---|---|---|
| independent | 0.0 | 0.04362773322524349 | -3.50655789731998 | `wwr_g-0001` |
| wrong way | 0.1 | 0.06114835388862783 | -3.584568660698148 | `wwr_g-0002` |
| wrong way | 0.3 | 0.08648730471425058 | -3.8277224868236654 | `wwr_g-0003` |
| right way | -0.2 | 0.015569211034720719 | -3.4452987689759205 | `wwr_g-0004` |
| identical paths | 1.0 | 0.11347051247504979 | -14.605170185988092 | `wwr_g-0007` |

The last line, `too_big`, returns `E_DOMAIN` on `wwr_b` ("|wwr_b * value| must be at most 700 (KR-257)"): `b V = 800` would overflow the hazard, and the operation now says so instead of returning a wrong number. How to read it: at `b = 0.3` the CVA is about twice the independent figure on the same paths, because the recalibrated hazard is highest on the paths with the largest exposure; at `b = -0.2` it falls to about a third. The outputs differ from the goldens in the last digit or two, inside the `root_finding` tolerance (1e-9 absolute plus 1e-12 relative). Limits: the paths are inputs (four hand-written paths here, not a simulation); the choice of `b` is a model judgement the operation does not make.

#### Is a risk factor modellable? The RFET on three observation patterns (risk.frtb.rfet)

Plain idea: under the internal models approach a risk factor may stay in the ES model only if it has enough real prices. Either it was observed on at least 24 days in the last 12 months with no 90-day stretch holding fewer than 4 of them, or it was observed on at least 100 days. A factor that fails goes to the stress scenario charge instead ([Tutorial 59](docs/getting-started/tutorial-59-frtb-ima-pla-to-capital.md)).

Formal statement (`specifications/06-risk/frtb-ima.md`, MAR31.12 to 31.16 read 2026-11-19 by the spec lane; ruling KR-59): count distinct calendar days in the 12 months ending at `as_of`; criterion 1 is at least 24 days and at least 4 in every 90-day window lying wholly inside the 12 months; criterion 2 is at least 100 days; pass is either. The goldens use dates in 2025 and 2026, so this recipe builds its own lists for the 12 months to 2028-06-30 (synthetic dates; none is a golden). By hand: every 14 days gives 26 days and at least `floor(90 / 14) = 6` in any 90-day window, so criterion 1 holds; 30 consecutive days give 30 days but leave most windows empty; 100 consecutive days fail criterion 1 for the same reason and pass criterion 2.

<!-- cookbook:run -->
```bash
python -c "
import datetime as dt, json
start = dt.date(2027, 7, 5)
for name, days in (('every_14_days', [start + dt.timedelta(14 * i) for i in range(26)]),
                   ('one_quarter_daily', [start + dt.timedelta(i) for i in range(30)]),
                   ('busy_quarter_100', [start + dt.timedelta(i) for i in range(100)])):
    print(json.dumps({'schema_version': '1.0', 'case_id': name, 'operation': 'risk.frtb.rfet',
                      'inputs': {'as_of': '2028-06-30', 'observations': [d.isoformat() for d in days]}}))
for t in (0.75, 0.7499):
    print(json.dumps({'schema_version': '1.0', 'case_id': f'bucket_{t}', 'operation': 'risk.frtb.rfet.bucket', 'inputs': {'row': 'A', 't': t}}))
" | uv run --locked --project python quantforge batch
```
<!-- cookbook:expect
"distinct_days":26,"min_window_count":6
"first_failing_window_start":"2027-08-01","first_failing_window_count":3,"crit1":false,"crit2":false,"pass":false
"distinct_days":100
"crit1":false,"crit2":true,"pass":true
"bucket":2,"lower":0.75
"bucket":1,"lower":0.0
-->

| Case | `distinct_days` | `min_window_count` | First failing window | `crit1` | `crit2` | `pass` |
|---|---|---|---|---|---|---|
| every 14 days | 26 | 6 | none | true | false | true |
| 30 consecutive days | 30 | 0 | starts 2027-08-01, 3 days | false | false | false |
| 100 consecutive days | 100 | 0 | starts 2027-10-10, 3 days | false | true | true |

Every line has `window_start` 2027-07-01. The first failing window of the second case runs from 1 August, and holds only 1, 2 and 3 August before the observations stop. The bucket lines give `bucket` 2 for `t` 0.75 (lower bound inclusive, `[0.75, 1.5)`) and `bucket` 1 for 0.7499 (MAR31.16 Table 1 row A). Limits: no vendor audit, no representativeness test and no lag between the RFET and calibration periods (spec, Limits).

### Stage K platform recipes: simulated feeds, end-of-day rehearsal, soak and snapshots

Operating tasks around the K-3, K-5 and K-6 items merged to main on 2026-11-20 (not in a tag). Outputs observed on 2026-11-21 on branch `k-v1-docs-a`, Windows, local laptop, not the acceptance machine. Two of these tasks have tutorials that CI runs: reading a soak verdict ([Tutorial 60](docs/getting-started/tutorial-60-read-a-soak-run.md)) and the K-5 snapshot, its checksum and its hedge ([Tutorial 61](docs/getting-started/tutorial-61-snapshots-and-hedge.md)).

#### Round-trip every simulated feed fixture and check the malformed ones (K-3)

Plain idea: the five feed formats (QF-FIX-S, QF-ITCH-S, QF-OUCH-S, QF-MOLD-S, QF-FAST-S) are simulated, not any venue's or standard's. Each hand-built fixture records the fields the spec derives and the SHA-256 of its bytes. Decoding must give those fields, and re-encoding must give the same bytes; every malformed input must raise `FeedError` with its listed code.

Formal statement (`specifications/12-platform/adapters.md` 0.2.0 section 3, rulings KR-270 to KR-283 confirmed 2026-11-20; KR-276: every encoding is canonical, so anything that decodes re-encodes to the same bytes). The adapter package lives outside the library trees (`platform/python`), so it is put on `PYTHONPATH`.

<!-- cookbook:run -->
```bash
export PYTHONUTF8=1 PYTHONPATH=platform/python
uv run --locked --project python python - <<'EOF'
import hashlib, json, pathlib
from quantforge_adapters.feeds import FeedError, fast, fix, itch, mold, ouch

CODEC = {"QF-FIX-S": (fix.decode, fix.encode), "QF-ITCH-S": (itch.decode, itch.encode),
         "QF-OUCH-S": (ouch.decode, ouch.encode), "QF-MOLD-S": (mold.decode, mold.encode),
         "QF-FAST-S": (lambda b: {"messages": fast.decode_packet(b)}, lambda m: fast.encode_packet(m["messages"]))}
STREAM = (lambda b: {"messages": ouch.decode_stream(b)}), (lambda m: ouch.encode_stream(m["messages"]))
good = 0
for meta in sorted(pathlib.Path("datasets/feeds").glob("*/*.json")):
    spec, raw = json.loads(meta.read_text(encoding="utf-8")), meta.with_suffix(".bin").read_bytes()
    dec, enc = STREAM if meta.stem.startswith("stream") else CODEC[spec["format"]]
    msg = dec(raw)
    good += (json.loads(json.dumps(msg, default=bytes.hex)) == spec["fields"]  # the fields the spec derived
             and enc(msg) == raw                                              # canonical: same bytes back
             and hashlib.sha256(raw).hexdigest() == spec["sha256"])           # the file is the one recorded
right = 0
cases = json.loads(pathlib.Path("datasets/feeds/malformed.json").read_text(encoding="utf-8"))["cases"]
for case in cases:
    dec = STREAM[0] if case["name"].startswith("stream") else CODEC[case["format"]][0]
    try:
        dec(bytes.fromhex(case["hex"]))
    except FeedError as e:
        right += e.code == case["code"]
print(f"{good} of {len(list(pathlib.Path('datasets/feeds').glob('*/*.json')))} fixtures round-trip; "
      f"{right} of {len(cases)} malformed inputs give their expected code")
EOF
```
<!-- cookbook:expect
17 of 17 fixtures round-trip; 39 of 39 malformed inputs give their expected code
-->

Output: `17 of 17 fixtures round-trip; 39 of 39 malformed inputs give their expected code`. The OUCH fixture `stream_two` and the malformed cases whose names start with "stream" are length-prefixed streams, so they go to `ouch.decode_stream`. A byte-level worked example (the 36-byte ITCH Add Order, offset by offset) is in the [adapters developer guide](docs/developer-guides/adapters.md#decoding-a-fixture-a-worked-example). Label: "simulated; not a certified implementation; not connected to any venue". Limits: the container round trips (Kafka, PostgreSQL and the others) run only in the `adapters` workflow and need Docker; this recipe does not start any service.

#### Rehearse an end of day, then plant a fault and watch the step that catches it (K-6)

Plain idea: before trusting the daily jobs with a date, run the whole chain for that date as a dry run: read and verify the recorder's log, check the date against the preregistered holdout windows, fit the curve, run the paper ledger, compute intraday risk, render and check the pages, archive. A failed step stops the run, and the steps after it are recorded as "not run". A planted fault must be caught at the step named for it.

Formal statement (`specifications/12-platform/soak-eod-capacity.md` 0.2.0 section 3, rulings KR-217 to KR-221 confirmed 2026-11-20; `tools/eod/rehearse.py`, read): eight steps E1 to E8; `--plant` injects exactly one fault: `GAP` (E1), `HOLDOUT` (E2), `HASH` (E3), `EXPLAIN` (E4), `DOMAIN` (E5), `LABEL` (E6), `WIDTH` (E7). It writes only to a temporary folder and to the `--out` file; it never writes to `forward-log`, `curve-daily` or `paper-ledger` and starts no workflow.

<!-- cookbook:run -->
```bash
export PYTHONUTF8=1
uv run --locked --project python python tools/eod/rehearse.py --date 2026-11-19 --source synthetic --out "${TMPDIR:-/tmp}/eod.json"
uv run --locked --project python python tools/eod/rehearse.py --date 2026-11-19 --source synthetic --plant EXPLAIN --out "${TMPDIR:-/tmp}/eod-explain.json" || echo "exit $?"
uv run --locked --project python python tools/eod/rehearse.py --date 2026-11-19 --source synthetic --plant HOLDOUT --out "${TMPDIR:-/tmp}/eod-holdout.json" || echo "exit $?"
```
<!-- cookbook:expect
result: pass
result: fail (failed at E4)
result: fail (failed at E2)
exit 1
-->

Output: the clean run prints `pass` for E1 to E8 and `result: pass` (about 1 s in all). With `EXPLAIN`, E1 to E3 pass, E4 prints `fail    EXPLAIN`, E5 to E8 print `not run`, and the result is `fail (failed at E4)`; the E4 evidence in the JSON reads `"planted": "roll_down of the date's row plus one cent, chain rebuilt"`, `"verify_ok": false`, `"verify_reason": "EXPLAIN"`: one cent in one explain term, with the hash chain recomputed as a forger would, and the verifier's exact replay still refuses it. With `HOLDOUT` the run stops at E2. A failed run exits 1, which the `|| echo` lines print so the block runs on; the JSON files go to the temporary folder. The JSON holds hashes, counts and aggregates only, never a recorded row. On 2026-11-20 the same date from the forward log (`--source forward-log`) passed all eight steps (`benchmarks/results/k6/eod-2026-11-19-forward-log.json`, measured by the K-6 lane); not rerun here. Limits: a dry run has no anchors to check; E3 fits the five recorded Treasury tenors, not the thirteen of the scheduled run (`rehearse.py`, deviation 3). How to act on a failed step: [runbook](docs/runbooks/soak-and-eod.md#rehearse-an-end-of-day).

#### Reread a soak verdict from the committed files (K-6)

<!-- cookbook:run -->
```bash
export PYTHONUTF8=1
python benchmarks/soak/analyse.py benchmarks/results/k6/soak-python-2026-11-20.csv benchmarks/results/k6/soak-python-2026-11-20.summary.json --out "${TMPDIR:-/tmp}/soak-verdict.json" || echo "exit $?"
```
<!-- cookbook:expect
python: MISS slope 2.3243 MiB/h (95% CI [1.696, 3.7996])
reasons ['SLOPE']
exit 1
-->

Output: `python: MISS slope 2.3243 MiB/h (95% CI [1.696, 3.7996]), range 13.035 MiB of median 432.59 MiB, reasons ['SLOPE']`. **This is the recorded MISS of the Python soak**: the memory climbs 2.32 MiB an hour against a bound of 1 MiB an hour fixed before the run, and the cause has not been found (`docs/known-issues.md`). `--out` writes the full verdict JSON; without it the analyser prints the line only, and it exits 1 on a MISS (`analyse.py`, read). Worked by hand in [Tutorial 60](docs/getting-started/tutorial-60-read-a-soak-run.md). Running a new soak takes 130 minutes and must be detached on a shared machine ([runbook](docs/runbooks/soak-and-eod.md#run-a-soak)).
