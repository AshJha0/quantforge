# CLI contract

Version 1.7.0. `01-core/rulings.md` and `01-core/limits.md` are part of this contract.
The `contract_version` a build reports stays `1.0.0`: nothing here breaks the wire format.
 Applies identically to the Java, C++, Python and Rust implementations.

The idea: every implementation is a black box that reads a case and writes a result. The neutral
runner in `conformance/` only ever sees that JSON. Nothing else about an implementation is part of
the contract.

## Invocation

Each implementation builds one executable (or launcher) called `quantforge`. The runner learns how
to start it from `conformance/runner/implementations.json`.

| Command | Behaviour |
|---|---|
| `quantforge run` | Read one case JSON document from stdin to end of file. Write one result JSON document to stdout. |
| `quantforge batch` | Read JSON Lines from stdin, one case per line. Write one result per line to stdout, in the same order, flushing after each line. |
| `quantforge --batch` | Exactly the same as `quantforge batch` (1.6.0). Both spellings must work. |
| `quantforge version` | Write one JSON object: `{"language":..., "implementation_version":..., "contract_version":"1.0.0", "toolchain":...}`. |
| `quantforge operations` | Write a JSON array of the operation names this build supports, sorted. |

`batch` exists because a JVM start per case would dominate run time. `run` and `batch` must give
the same result for the same case. No state may carry from one case to the next.

Output on stdout is UTF-8 JSON with no byte order mark. Anything for humans goes to stderr; the
runner ignores stderr. No command reads the clock, the environment, or any file for its numbers.

## Batch mode (1.6.0, R1)

`quantforge batch` and `quantforge --batch` are the same command. This section is normative for both.
Fixtures: `datasets/batch/streams.json`, checked by `conformance/runner/batch_check.py`. They are
not in `datasets/golden/`, because they test the stream, not an operation.

**Framing.**

| # | Rule |
|---|---|
| BT1 | Input is a byte stream split on LF (`0x0A`). One line is one case document. A CR (`0x0D`) directly before the LF is removed first, so CRLF input works |
| BT2 | The last line may end without LF; it is still a case. An empty stream (zero bytes) gives zero results and exit 0 |
| BT3 | Every line gives exactly one result line, in input order, even a line that is empty, all whitespace, not UTF-8, not JSON, or starts with a byte order mark. Those are `E_PARSE` with `case_id: "unknown"`. No line is skipped |
| BT4 | A line is parsed with the same checks, in the same order, as `run` gives the same bytes: `E_PARSE`, `E_SCHEMA`, `E_LIMIT`, rule checks. The result for a line equals the `run` result for that line, key for key and bit for bit |
| BT5 | A line longer than 16,777,216 bytes (after BT1) is `E_LIMIT` with `case_id: "unknown"`, decided on its length without parsing. The stream continues with the next line. A build may read and drop the rest of the line, but holds no more than the limit in memory |
| BT6 | Output is one result document per line, UTF-8, no byte order mark, no blank lines, each ending in a single LF (never CRLF, also on Windows). Each line is flushed before the next input line is read beyond its end, so a caller that writes one line and waits gets its result without closing stdin |
| BT7 | No state carries from one line to the next: not caches that change a number, not error state, not the random state. Reordering the lines reorders the results and changes nothing else |
| BT8 | Exit 0 when stdin ends, whatever the status of each case. Exit 70 only for an internal fault; results already written stay valid. The runner treats a short stream as a crash |

**Timings (optional flag).** `quantforge batch --timings` (and `quantforge --batch --timings`, and
`quantforge run --timings`) adds one key to each result: `diagnostics.elapsed_ns`, a non-negative
integer, the monotonic wall time in nanoseconds from the end of reading the line to the end of
building the result, before writing it. It is present on `error` results too. Nothing else in the
result changes, and `outputs` must be bit for bit the same as without the flag. An empty
`diagnostics` object and an absent one mean the same. Without the flag, a
build must not write `elapsed_ns`. The runner never compares `diagnostics`; the benchmark harness
reads `elapsed_ns` to publish per-operation timings. Any other argument, or an argument in another
position, is exit 64 with empty stdout.

**Throughput target (informative, not checked by conformance).** Start-up is paid once per stream.
`benchmarks/targets.md` holds the numbers. The R1 acceptance line is Python fuzz at 50,000 inputs a
minute or more through batch mode.

## Case document (input)

Schema: `datasets/schemas/case.schema.json`.

```json
{
  "schema_version": "1.0",
  "case_id": "daycount-0001",
  "operation": "core.daycount.year_fraction",
  "inputs": {"convention": "ACT_360", "start": "2024-01-01", "end": "2024-07-01"}
}
```

Expected values are never sent to the implementation. The runner strips them from the golden file.

## Result document (output)

Schema: `datasets/schemas/result.schema.json`.

Success:

```json
{
  "schema_version": "1.0",
  "case_id": "daycount-0001",
  "status": "ok",
  "outputs": {"year_fraction": 0.5055555555555555},
  "diagnostics": {}
}
```

Failure of the calculation:

```json
{
  "schema_version": "1.0",
  "case_id": "daycount-0002",
  "status": "error",
  "error": {"code": "E_DATE_ORDER", "message": "end is before start", "field": "end"}
}
```

`outputs` and `error` are mutually exclusive. `diagnostics` is an object and may always be present.
`error.code` is compared by the runner. `error.message` is free text and is not compared.
`error.field` is the input name when one input is at fault; it is optional and is not compared.
Extra keys in `outputs` are a failure; missing keys are a failure.

## Exit codes

| Code | Meaning | stdout |
|---|---|---|
| 0 | `run`: result with status `ok`. `batch`, `version`, `operations`: the stream ended normally, whatever the status of each case | result |
| 2 | `run`: result with status `error` | result |
| 64 | Unknown command or bad arguments | empty |
| 70 | Internal fault: an unhandled exception, or a bug | anything; the runner reports a crash |

A malformed case is still a result: `run` writes status `error` with `E_PARSE` or `E_SCHEMA` and
exits 2, using `case_id: "unknown"` if none can be read. In `batch`, one bad line must not stop the
stream (BT3). Any other exit code, or a timeout, is a crash.

## Error codes

These are the same in all four languages. A case that expects an error passes only on the exact code.

| Code | When |
|---|---|
| `E_PARSE` | Input is not valid JSON, or has a duplicate key |
| `E_SCHEMA` | JSON is valid but the envelope or an input is missing, mistyped or malformed. This includes a bad date string, and an enum value that is not listed |
| `E_UNSUPPORTED_OPERATION` | The operation name is not in this build. The runner counts this as "not implemented", not as a pass |
| `E_INPUT` | Inputs are well formed but break a rule of the operation, such as knots not strictly increasing, or an array that is too short |
| `E_DATE_ORDER` | A date range runs backwards |
| `E_DATE_RANGE` | A date or instant is outside the range the operation supports |
| `E_DOMAIN` | A value is outside the mathematical domain, such as the log of a negative number |
| `E_NOT_BRACKETED` | A root finder was given an interval without a sign change |
| `E_NO_CONVERGENCE` | An iteration reached its limit |
| `E_ZERO_DERIVATIVE` | Newton met a zero derivative |
| `E_SINGULAR` | A matrix is singular to working precision |
| `E_NOT_POSITIVE_DEFINITE` | Cholesky met a non-positive pivot |
| `E_OUT_OF_RANGE` | An interpolation point lies outside the knots |
| `E_NONEXISTENT_LOCAL_TIME` | A local time falls in a daylight-saving gap |
| `E_AMBIGUOUS_LOCAL_TIME` | A local time falls in a daylight-saving overlap and no choice was given |
| `E_NON_FINITE` | A result would be NaN or infinite |
| `E_CURRENCY_MISMATCH` | Two amounts in different currencies were combined |
| `E_ARBITRAGE` | A model result breaks no-arbitrage and the case asked to reject it (`vol.sabr.density`) |
| `E_LIMIT` | A size-like input is above its limit in `01-core/limits.md`. No work is started |

Order of checks: `E_PARSE`, then `E_SCHEMA`, then `E_LIMIT` (with the text-size and depth exceptions in `01-core/limits.md` B1 and B2), then the rule checks in the order the operation's spec
lists them. When one case breaks two rules, the first listed wins.

## Value encoding

| Type | JSON form |
|---|---|
| Real number | JSON number. Parsed to the nearest binary64. Written so that it reads back to the same binary64 (shortest round-trip form preferred, never a fixed number of decimals) |
| Integer | JSON number with no fraction, magnitude at most 2^53 |
| 64-bit unsigned | Decimal string, such as `"16172922978634559625"`, because JSON readers lose bits above 2^53 |
| Date | `YYYY-MM-DD`, proleptic Gregorian |
| Instant | RFC 3339 with `Z` or a numeric offset, whole seconds, such as `2024-03-31T00:59:59Z` |
| Local time | `YYYY-MM-DDTHH:MM:SS`, no offset |
| Enum | Upper-case string as listed in the operation's spec |
| Missing | JSON `null`, never zero and never omitted when the schema lists the key |

NaN and infinity never appear. As an input they cannot be written in JSON, and a number that
overflows binary64, such as `1e400`, is `E_SCHEMA`. As an output they become `E_NON_FINITE`. Negative
zero may be written as `-0.0` or `0.0`; the runner treats them as equal.

## Numeric rules

Binary64 throughout. No `-ffast-math`. C++ conformance builds disable FMA contraction
(`-ffp-contract=off`). Sums run in array order unless a spec says otherwise, including any
parallel sum. Exact equality between languages is not expected, because `exp`, `log` and friends
differ in the last bits. Tolerance classes are in `conformance/tolerances/policy.yaml`.

## Operations

Operation names are `<domain>.<area>.<verb>`. Each spec file defines its inputs, outputs, and
errors. Stages A, B and C:

| Prefix | Spec |
|---|---|
| `core.daycount.*` | `01-core/daycount.md` |
| `core.calendar.*` | `01-core/calendars.md` |
| `core.compounding.*` | `01-core/compounding.md` |
| `core.snapshot.*` | `01-core/snapshot-hash.md` |
| `core.rng.*` | `01-core/rng.md` |
| `core.sobol.*` | `01-core/sobol.md` |
| `core.root.*` | `01-core/root-finders.md` |
| `core.integrate.*` | `01-core/integration.md` |
| `core.interp.*` | `01-core/interpolation.md` |
| `core.diff.*`, `core.linalg.*` | `01-core/differentiation-and-linalg.md` |
| `core.stats.*`, `core.ts.*` | `01-core/statistics-and-time-series.md` |
| `core.pde.*` | `01-core/pde.md` |
| `core.mc.*` | `01-core/monte-carlo.md` |
| `core.cos.*` | `01-core/cos.md` |
| `core.data.*` | `01-core/data-checks.md` |
| `core.time.*` | `01-core/timezone-and-cutoff.md` |
| `core.store.*` | `01-core/asof-store.md` |
| `core.units.*` | `01-core/units-and-money.md` |
| `core.conventions.*` | `01-core/conventions.md` |
| `rates.schedule.*` | `02-curves/schedules.md` |
| `rates.curve.*` | `02-curves/curve-framework.md` |
| `rates.ois.*` | `02-curves/ois-curves.md` |
| `rates.projection.*`, `rates.fra.*`, `rates.swap.*`, `rates.basis.*` | `02-curves/projection-and-fra.md` |
| `fx.*` | `02-curves/fx.md` |
| `calib.*` | `03-calibration/least-squares.md` |
| `risk.*` | `06-risk/rates-sensitivities.md` |
| `hedge.*` | `08-hedging/stage-b-hedges.md` |
| `usecase.*` | `04-pricing/use-cases.md` |
| `eq.forward.*` | `02-curves/equity-forward.md` |
| `vol.option.*` | `05-volatility/black-models.md` |
| `vol.delta.*`, `vol.smile.*`, `vol.svi.*`, `vol.ssvi.*`, `vol.surface.*` | `05-volatility/smile-and-surface.md` |
| `vol.sabr.*` | `05-volatility/sabr.md` |
| `vol.equity.price`, `risk.vol.*` | `06-risk/vol-greeks.md` |

Stage C adds `E_ARBITRAGE` and these operations, and breaks nothing in the wire format. `stage-c-rulings.md` is normative for them.

Stage D (contract 1.5.0, wave 1) adds these, with no new error code. `stage-d-rulings.md` is normative for them.

| Prefix | Spec |
|---|---|
| `rates.ois.compound_dated`, `rates.fallback.rate` | `02-curves/overnight-compounding.md` |
| `rates.ois.step_curve`, `rates.ois.fit_steps` | `02-curves/meeting-steps.md` |
| `rates.futures.convexity` | `02-curves/futures-convexity.md` |
| `rates.csa.discount`, `rates.basis.ois_spread`, `rates.curve.joint_bootstrap` | `02-curves/csa-and-basis.md` |
| `calib.curve.smooth`, `calib.curve.robust` | `03-calibration/curve-fits.md` |

Wave 2 adds:

| Prefix | Spec |
|---|---|
| `bond.*`, `repo.*` | `04-pricing/bonds.md` |
| `fx.xccy.*`, `fx.ndf.*` | `02-curves/cross-currency.md` |
| `credit.*` | `04-pricing/credit.md` |
| `eq.dividend.*`, `eq.borrow.*`, `eq.futures.*` | `02-curves/equity-curves.md` |
| `eq.index.*`, `eq.corporate_action.*`, `eq.trs.*` | `04-pricing/equity-index.md` |
| `infl.*` | `02-curves/inflation.md` |
| `rates.cap.*`, `rates.swaption.*` | `05-volatility/caps-and-swaptions.md` |
| `cmdty.*` | `02-curves/commodity.md` |
| `mbs.*` | `04-pricing/mbs.md` |

`ESTR` joins `rates.ois.*`, and curve objects take optional `jumps` (`02-curves/curve-framework.md`).

Phase R2 (contract 1.7.0) adds these, with no new error code:

| Prefix | Spec |
|---|---|
| `risk.curve.par`, `risk.curve.key_rate`, `risk.curve.jacobian` | `06-risk/par-and-key-rate.md` |
| `risk.pnl.explain` | `06-risk/pnl-explain.md` |

### Stage E, spec A (E1, E2, E3, E5)

Stage E (target contract 1.8.0, set by the coordinator at merge) adds these, with no new error code; `E_ARBITRAGE` now also covers surface checks with `reject: true`, local vol and forward vol. `stage-e-rulings.md` is normative for them. All are batch operations under the 1.6.0 batch rules, with no change to the stream format.

| Prefix | Spec | Slice |
|---|---|---|
| `vol.svi.surface_check`, `vol.ssvi.to_svi`, `vol.svi.fit_surface` | `05-volatility/arb-free-surfaces.md` | E1 |
| `vol.local.dupire`, `vol.forward.vol`, `vol.smile.dynamics`, `vol.volofvol.measure` | `05-volatility/local-and-forward-vol.md` | E1 |
| `fx.option.price`, `fx.delta.from_strike`, `fx.delta.to_strike`, `fx.atm.strike`, `fx.smile.from_quotes` | `05-volatility/fx-smile.md` | E3 |
| `vol.heston.price`, `vol.heston.cf`, `vol.bates.price`, `vol.merton.price`, `vol.slv.leverage` | `05-volatility/heston-family.md` | E2 |
| `exotic.*` | `04-pricing/exotics.md` | E5 |

A test function cannot be sent as JSON, so operations that need one name it from the registry in
`01-core/test-functions.md`.

## Stage E operations, spec B (contract 1.8.0)

Stage E spec B adds these, with no new error code and no change to the wire format or to `--batch` (each new operation is one line in, one line out, as BT1 to BT4). `stage-e-rulings-b.md` is normative for them. Spec A's stage E operations are in their own section. Rows are added as each slice lands.

| Prefix | Spec | Slice |
|---|---|---|
| `vol.garch.loglik`, `vol.garch.forecast`, `vol.garch.fit` | `05-volatility/garch.md` | E7 |
| `vol.varswap.fair_strike`, `vol.varswap.realized` | `05-volatility/variance-swaps.md` | E7 |
| `vol.vix.term_variance`, `vol.vix.index` | `05-volatility/vix-index.md` | E7 |
| `risk.corr.validate`, `risk.corr.nearest`, `risk.corr.implied`, `risk.corr.dispersion` | `06-risk/correlation.md` | E6 |
| `credit.cdsoption.price`, `credit.cdsoption.implied_vol`, `credit.copula.joint_default`, `credit.lhp.tranche_loss`, `credit.lhp.loss_cdf` | `04-pricing/credit-options-and-copulas.md` | E8 |
| `rates.swaption.price_cube`, `rates.cap.strip`, `rates.bondfut.option_price`, `rates.bondfut.implied_vol`, `infl.cap.yoy_price`, `infl.cap.zc_price` | `05-volatility/rates-vol-cube.md` | E4 |

Batch notes for these operations: `vol.garch.fit`, `rates.cap.strip`, `rates.bondfut.implied_vol` `risk.corr.nearest` and `credit.cdsoption.implied_vol` iterate; a line that fails to converge returns `E_NO_CONVERGENCE` for that line and the batch goes on. Array inputs (`returns`, `prices`, `strip`) count towards `01-core/limits.md` like any array. `initial_variance` is a string or a number: any other JSON type is `E_SCHEMA`. `knock_out` must be a JSON boolean; `copula` must be `GAUSSIAN` or `STUDENT_T` (`E_SCHEMA` otherwise).

## Stage F operations (target contract 1.9.0)

Stage F changes one rule for every operation and adds no error code. `stage-f-rulings.md` is normative.

- **Non-finite tokens (F-1).** A Real input may be the string `"NaN"`, `"Infinity"` or `"-Infinity"`. This is the only change to the wire format; the value-encoding table above still holds for every other value. Outputs never carry these strings: a non-finite output is `E_NON_FINITE` as before.
- **Finite rule (F-2, plan item E1).** The first rule check of every operation is that every Real input is finite; otherwise `E_DOMAIN`. Order of checks becomes `E_PARSE`, `E_SCHEMA`, `E_LIMIT`, the finite rule, then the operation's own checks.
- **Negative zero (F-3).** `-0.0` gives the same result as `0.0`.

Stage F operations are added to the table below as each wave lands.

| Prefix | Spec | Slice |
|---|---|---|
| `credit.cdsindex.option_price` | `04-pricing/credit-options-and-copulas.md` | F6 (R7) |
| `vol.garch.estimate`; new optional inputs `distribution`, `degrees_of_freedom`, `mean` on `vol.garch.loglik` | `05-volatility/garch.md` | F6 (R8) |
| `vol.vix.term_variance`, `vol.vix.index`: quotes may be `null` | `05-volatility/vix-index.md` | F6 (R10) |
| `rates.curve.inspect`; `interpolation` values `MONOTONE_CONVEX`, `MONOTONIC_LOG_CUBIC`, `TENSION_SPLINE`, `HYBRID` (curve keys `tension`, `step_end`) wherever a curve object or a bootstrap takes `interpolation` | `02-curves/curve-framework.md` | F1 (Q1) |
| `rates.curve.joint_solve`, `rates.funding.curve` | `02-curves/joint-solve-and-funding.md` | F1 (Q4) |
| `risk.book.ois_sensitivity`, `risk.curve.pca`, `risk.curve.cross_gamma`, `risk.credit.jtd` | `06-risk/book-sensitivities.md` | F3 (Q3a) |
| `risk.var.historical`, `risk.var.filtered_historical`, `risk.var.parametric`, `risk.var.monte_carlo`, `risk.backtest.kupiec`, `risk.backtest.christoffersen`, `risk.backtest.traffic_light` | `06-risk/var-es-and-backtests.md` | F4 (Q2) |
| `risk.frtb.girr_delta` | `06-risk/frtb-sa-girr.md` | F4 (Q2) |
| `book.lifecycle.apply`, `book.marks.resolve` | `07-portfolio/book-lifecycle.md` | F5 |
| `usecase.factor_attribution` | `04-pricing/use-cases.md` | F5 (use case 4) |

Batch notes: `rates.curve.joint_solve` and `vol.garch.estimate` iterate; a line that fails returns `E_NO_CONVERGENCE` and the batch goes on. `null` is a legal value only where a spec says so (VIX quotes, `zero_rates` outputs); elsewhere it stays `E_SCHEMA`. New policy classes: `jacobian`, `jacobian_piecewise`, `standard_error`, `aad_sensitivity`, `ift_jacobian`. New runner check `exact_zero` for structural zeros (ruling F-44). `E_LIMIT` sizes for the stage F operations: ruling F-42 (`conformance/tolerances/policy.yaml`).

## Stage G operations (target contract 1.10.0)

Stage G adds operations and no error code. `stage-g-rulings.md` is normative. Operations are added to the table as each wave lands.

| Prefix | Spec | Slice |
|---|---|---|
| `rates.shortrate.zcb`, `rates.shortrate.zcb_option` | `04-pricing/short-rate-models.md` | G1 (wave 1) |
| `exotic.barrier.price`: new optional inputs `monitoring`, `monitoring_per_year` | `04-pricing/exotics.md`, section "Stage G addition" | R9 (wave 1) |
| `rates.shortrate.swaption` | `04-pricing/short-rate-models.md`, section "`rates.shortrate.swaption`" | G2a (wave 2a) |
| `rates.g2pp.zcb`, `rates.g2pp.zcb_option` | `04-pricing/short-rate-models.md`, section "G2++" | G2b (wave 2b) |
| `risk.mc.greeks` | `06-risk/mc-greeks.md` | Q9 part 1 (wave 3a) |
| `xva.exposure.swap_ee_hw` | `06-risk/xva-exposure.md` | G5a (wave 4a) |

`E_LIMIT` sizes for the stage G operations: ruling G-6.

## Versioning

Adding an operation or an error code is a minor version. Changing the meaning of a key, a code or an
exit status is a major version, and all four implementations and the runner move together.
