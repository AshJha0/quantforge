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

Rust build on Windows, 2026-11-06. The status and the outputs were also the same from the Java, C++ and Python builds, apart from the differences listed below.

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

`batch.jsonl` holds the same four cases, one per line. `quantforge batch < examples/batch.jsonl` writes four lines in the same order and exits 0, whatever the status of each case.

## Where the languages differed

None of these is compared by the runner, and each is allowed by the contract.

- `iterations` in the Brent case was 6 from Rust and 7 from Java, C++ and Python. Diagnostics are not compared.
- `error.field` is optional. Java, C++ and Python wrote `"field":"end"`; Rust left it out.
- Java writes the residual as `3.552713678800501E-15`, with a capital E. It is the same number in valid JSON.
