# Examples

The plain idea: each file here is one case for the `quantforge` command. Send it on stdin and read the JSON that comes back. Nothing else about a language matters to a caller.

The contract is `specifications/cli-contract.md`. These inputs are small illustrations, not test evidence; the golden cases in `datasets/golden/` are what the project is judged on.

Build a CLI first (`docs/developer-guides/test-infrastructure.md` has all four). From the repository root, with Rust:

```bash
(cd rust && cargo build --release -p quantforge-cli)
rust/target/release/quantforge run < examples/daycount.json
```

For the other languages, replace the command:

| Language | Command |
|---|---|
| Java | `java -jar java25/target/quantforge-cli.jar` |
| C++ | `cpp26/build/quantforge` |
| Python | `uv run --project python quantforge` |
| Rust | `rust/target/release/quantforge` |

## Real output

Rust build on Windows, 2026-11-06, rerun at commit `13d9871`. The status and the outputs were also the same from the Java, C++ and Python builds, apart from the differences listed below.

`daycount.json`: ACT/360 from 2024-01-01 to 2024-07-01 is 182/360. Exit code 0.

```json
{"schema_version":"1.0","case_id":"example-daycount","status":"ok","outputs":{"year_fraction":0.5055555555555555},"diagnostics":{}}
```

`discount_factor.json`: continuous compounding at 5% for two years, so exp(-0.1). Exit code 0.

```json
{"schema_version":"1.0","case_id":"example-discount","status":"ok","outputs":{"discount_factor":0.9048374180359595},"diagnostics":{}}
```

`root_brent.json`: Brent's method on the registered function `cubic_wallis`, bracketed by 2 and 3. Exit code 0.

```json
{"schema_version":"1.0","case_id":"example-root","status":"ok","outputs":{"root":2.094551481542327},"diagnostics":{"iterations":6,"residual":3.552713678800501e-15,"termination":"X_TOL"}}
```

`error_date_order.json`: the end date is before the start date. A calculation error is still a result on stdout, and `run` exits with code 2.

```json
{"schema_version":"1.0","case_id":"example-error","status":"error","error":{"code":"E_DATE_ORDER","message":"end is before start"}}
```

`batch.jsonl` holds the four stage A cases above, one per line. `quantforge batch < examples/batch.jsonl` writes four lines in the same order and exits 0, whatever the status of each case.

## Stage B: curve and use cases

All three inputs are synthetic and copied from golden cases. The outputs are calculations, and nothing is traded. Exit code 0 from all four builds, 2026-11-06, commit `13d9871`. Output below is from the Rust build.

`ois_bootstrap.json`: 13 SONIA quotes to discount factors, sequentially, with log-linear interpolation. Pillars shortened here to the first and last.

```json
{"schema_version":"1.0","case_id":"example-ois","status":"ok","outputs":{"pillars":[{"date":"2026-11-13","discount_factor":0.9992870839543515}, ... ,{"date":"2056-11-06","discount_factor":0.337281701011728}]},"diagnostics":{"max_repricing_error":1.817990202823694e-15}}
```

`usecase_fx_hedge.json`: use case 1. Two GBPUSD forwards, hedged with spot.

```json
{"schema_version":"1.0","case_id":"example-usecase-1","status":"ok","outputs":{"pv":59903.64653464559,"fx_delta":2054546.4912482663,"hedge_spot_base":-2054546.4912482663,"residual_delta":0.0,"hedge_cost":102.72732456241332},"diagnostics":{}}
```

`usecase_rates_hedge.json`: use case 2. A 6Y SONIA payer, hedged with 5Y and 7Y par swaps.

```json
{"schema_version":"1.0","case_id":"example-usecase-2","status":"ok","outputs":{"pv":4688.463457886704,"dv01":5359.884273971188,"key_rate":[0.0,0.0,0.0,0.0,0.0032343783204851206,0.006512847761314333,0.015018871840766224,2210.203389321763,3149.655767292203,0.0,0.0,0.0,0.0],"hedge_units":[-4.871268420002989,-5.123922256644436],"residual_key_rate":[0.0,0.0,0.0,0.0,0.0032343784231503134,0.006512848038736604,0.015018871147210547,0.0,0.0,0.0,0.0,0.0,0.0],"hedge_cost":1339.9647891535699},"diagnostics":{}}
```

## Where the languages differed

Except where stated, none of these is compared by the runner, and each is allowed by the contract.

- `iterations` in the Brent case was 6 from Rust and 7 from Java, C++ and Python. Diagnostics are not compared.
- `error.field` is optional. Java, C++ and Python wrote `"field":"end"`; Rust left it out.
- Stage B solves differ in the last digits. In use case 2 the PV runs from 4688.463457883096 (C++) to 4688.463457886704 (Rust), and bootstrapped discount factors differ in the last one or two digits. Each is inside its golden case's tolerance, and the runner does compare these.
- `residual_delta` in use case 1 is `0` from C++ and `0.0` from the others. It is the same number.
- Java writes the residual as `3.552713678800501E-15`, with a capital E. It is the same number in valid JSON.
