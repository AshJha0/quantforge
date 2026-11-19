# CLI contract

Version 1.17.0 (stage K, owner decision K-QC, ruling KR-1; the blocks below give the minor versions each stage added). `01-core/rulings.md` and `01-core/limits.md` are part of this contract.
From stage K (owner decision K-QC, ruling KR-1: one number for every stage K wave) every build reports `contract_version` `1.17.0` (stage H: `1.16.0`, rulings HR-1 and DR-H8; stage J wave 3 and the curves lane: `1.15.0`, rulings J-W3-1 and J-C-1; stage J wave 2: `1.14.0`, ruling J-W2-1; stage J wave 1: `1.13.0`, ruling J-1; R6: `1.12.0`, ruling R6-0.1; stage I: `1.11.0`, ruling I-51), and the runner stops on any other value. Before stage I every build reported `1.0.0`; nothing in 1.1.0 to 1.17.0 breaks the wire format.
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
| `quantforge version` | Write one JSON object: `{"language":..., "implementation_version":..., "contract_version":"1.17.0", "toolchain":...}`. |
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
| `E_NON_FINITE` | A result would be NaN or infinite, including an intermediate that overflows from finite inputs (ruling R6-8.1: never a crash, never `E_DOMAIN`) |
| `E_CURRENCY_MISMATCH` | Two amounts in different currencies were combined |
| `E_ARBITRAGE` | A model result breaks no-arbitrage and the case asked to reject it (`vol.sabr.density`) |
| `E_LIMIT` | A size-like input is above its limit in `01-core/limits.md`. No work is started |
| `E_INFEASIBLE` | No point satisfies the operation's constraints (bounds and equalities). Added in contract 1.11.0 (stage I, ruling I-1) |

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
- **Finite rule (F-2, plan item E1).** The first rule check of every operation is that every Real input is finite; otherwise `E_DOMAIN`. Order of checks becomes `E_PARSE`, `E_SCHEMA`, `E_LIMIT`, the finite rule, then the operation's own checks. For the stage H operations the own checks are structural `E_INPUT` before `E_DOMAIN`, and a limit that only arises after validation is last (HR-122, which reconciles HR-66 with this order; goldens `rule_h`).
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
| `rates.shortrate.hw_calibrate` | `04-pricing/short-rate-models.md`, section "`rates.shortrate.hw_calibrate`" | G2c (wave 2c) |
| `rates.shortrate.bermudan_swaption` | `04-pricing/short-rate-models.md`, section "`rates.shortrate.bermudan_swaption`" | G2d (wave 2d) |
| `rates.shortrate.capfloor` | `04-pricing/short-rate-models.md`, section "`rates.shortrate.capfloor`" | G2e (wave 2e) |
| `rates.shortrate.swaption`: new optional input `model` (`VASICEK`, `CIR`; default `HULL_WHITE`) | `04-pricing/short-rate-models.md`, "Stage G wave 2f" | G2f (wave 2f) |
| `rates.shortrate.callable_bond` | `04-pricing/short-rate-models.md`, section "`rates.shortrate.callable_bond`" | G3 (wave 2g) |
| `risk.mc.greeks` | `06-risk/mc-greeks.md` | Q9 part 1 (wave 3a) |
| `xva.exposure.swap_ee_hw` | `06-risk/xva-exposure.md` | G5a (wave 4a) |
| `rates.lmm.capfloor`, `rates.lmm.swaption_rebonato` | `04-pricing/lmm.md` | G4a (wave 3b, LMM) |
| `rates.shortrate.bermudan_ladder` | `06-risk/aad-core.md` | Q3b (wave 3d) |
| `risk.model_reserve.dispersion` (`null` legal for `relative_reserve`) | `06-risk/model-reserve.md` | Q9 part 2 (wave 3e) |
| `xva.exposure.collateralised`, `xva.adjustments.value`, `xva.sbim.ir_delta` (named `xva.simm.ir_delta` until v0.10.0; see "Deprecated aliases"), `xva.wwr.cva_hw` | `06-risk/xva-framework.md` | G5b (wave 4b); renamed in contract 1.17.0 (KR-152) |
| `xva.exposure.portfolio_hw` | `06-risk/xva-exposure-portfolio.md` | G5c (wave 4c, ORE-checked) |
| `risk.stress.reverse`, `risk.limits.check`, `risk.concentration.measures`, `risk.var.liquidity_adjusted`, `risk.vol.horizon` | `06-risk/portfolio-risk-tools.md` | F4 carry-over (wave 2b) |
| `risk.sens.inflation01`, `risk.sens.dividend_borrow`, `risk.sens.correlation` | `06-risk/f3-sensitivities.md` | F3 carry-over (wave 2b) |
| `risk.frtb.fx_delta`, `risk.frtb.equity_delta`, `risk.frtb.csr_delta`, `risk.frtb.commodity_delta` | `06-risk/frtb-sa-fx-equity.md` | FRTB carry-over (wave 2b) |
| `risk.frtb.vega`, `risk.frtb.curvature` | `06-risk/frtb-sa-vega-curvature.md` | FRTB carry-over (wave 2b) |

`E_LIMIT` sizes for the stage G operations: ruling G-6 as amended by G-31 (full table and the combined grid-work bound). `rates.shortrate.hw_calibrate` iterates; a failed line returns `E_NO_CONVERGENCE` and the batch goes on.

## Stage I operations (target contract 1.11.0)

Stage I adds operations and one error code, `E_INFEASIBLE` (ruling I-1). `stage-i-rulings.md` is normative. Operations are added to the table as each wave lands.

| Prefix | Spec | Slice |
|---|---|---|
| `hedge.qp.solve`, `hedge.integer.solve`, `hedge.minvar.ratio`, `hedge.greeks.neutralise`, `hedge.beta.futures`, `hedge.residual.report` | `08-hedging/hedge-solvers.md` | wave 1 |
| `hedge.credit.cds`, `hedge.correlation.neutralise` | `08-hedging/credit-and-correlation-hedges.md` | wave 2 |
| `hedge.crossasset.solve` | `08-hedging/cross-asset-hedge.md` | wave 3 |
| `hedge.qp.solve`: new optional inputs `half_spreads`, `impact`, `cost_weight`, `margin_rates`, `margin_limit` (outputs `risk`, `cost`, `margin` only with them); `hedge.frontier.solve` | `08-hedging/hedge-costs-and-frontier.md` | wave 4a |
| `hedge.backtest.delta`, `hedge.effectiveness` | `08-hedging/dynamic-hedge-and-effectiveness.md` | wave 4b |
| `hedge.select.solve` | `08-hedging/instrument-selection.md` | wave 4c |
| `hedge.slippage.report` (`null` legal for `average_price`) | `08-hedging/hedge-slippage.md` | wave 4d |
| `hedge.backtest.delta`: new optional inputs `half_spread`, `impact` (output `trading_cost` only with them) | `08-hedging/dynamic-hedge-and-effectiveness.md`, section "Costs in the backtest (wave 4e)" | wave 4e |

`null` is legal inside `lower`, `upper`, `lower_lots`, `upper_lots` (ruling I-12). `E_LIMIT` sizes: ruling I-4. Every rank or singularity decision uses the relative threshold `1e-12` (ruling I-3).

## Versioning

Adding an operation or an error code is a minor version. Changing the meaning of a key, a code or an
exit status is a major version, and all four implementations and the runner move together.

## Deprecated aliases

A deprecated alias is an old operation id that every build still accepts for a stated time. It runs the same
handler as its target, so its outputs, error codes and diagnostics are those of the target; nothing in the result
marks it (extra keys in `outputs` are a failure, see "Result document"). The deprecation is stated here and in
`specifications/deprecated-aliases.json`, which `tools/gen_name_map.py` reads. Removing an alias is a major change
(KR-154): it is done with the release named below. Golden suites pin each alias with invariance pairs (the target
with expected `any`, the alias with `same_as`), so a build whose alias drifts from its target fails.

| Alias (deprecated) | Target | Deprecated in | Removal | Ruling |
|---|---|---|---|---|
| `xva.simm.ir_delta` | `xva.sbim.ir_delta` | contract 1.17.0 (release v0.10.1) | v1.0.0 | KR-152; goldens `stage_k/sbim_alias_k.json` |

## R6 changes (contract 1.12.0, rulings `r6-rulings.md`)

| Operation | Change | Spec |
|---|---|---|
| `risk.curve.jacobian` | No entry is set to 0 (R6-1.1); new optional inputs `tension`, `step_end` as `rates.ois.bootstrap` (R6-1.2) | `06-risk/par-and-key-rate.md` |
| `risk.var.historical`, `risk.var.filtered_historical`, `risk.var.monte_carlo` | `es` is the Acerbi-Tasche estimator with a fractional tail weight; `tail_count = ceil(n - n c)` (R6-3.1) | `06-risk/var-es-and-backtests.md` |
| `risk.frtb.sbm_total` (new) | MAR21.7 total across classes and measures, per scenario then the largest (R6-4.1) | `06-risk/frtb-sa-girr.md` |
| every operation | A non-finite result from finite inputs is `E_NON_FINITE`, never a crash and never `E_DOMAIN` (R6-8.1) | this page, error table |
| policy | New tolerance class `per_unit` (absolute 1e-10, relative 1e-8) for rates, spreads, vols and ratios (R6-10.1, R6-10.2) | `conformance/tolerances/policy.yaml` |

Later R6 waves append rows here (see `program/R6_HANDOVER.md`).

## Stage J operations (contract 1.13.0)

Stage J wave 1 adds operations and no error code (ruling J-1). `stage-j-rulings-w1.md` and `stage-j-rulings.md` are normative. Operations are added to the table as each wave lands. Wave 1 is implemented in all four builds. For these operations the page limits of ruling J-20 (bars 1,000,000; observations 1,000,000; Viterbi steps 100,000; statistics cells 10,000,000) replace the general per-array limit of 100,000 elements.

| Prefix | Spec | Slice |
|---|---|---|
| `research.backtest.run` | `11-research/backtester.md` | wave 1 |
| `research.cv.purged_kfold`, `research.cv.cpcv_paths` | `11-research/purged-cv.md` | wave 1 |
| `research.regime.viterbi` | `11-research/regimes.md` | wave 1 |
| `research.stats.psr`, `research.stats.dsr`, `research.stats.pbo`, `research.stats.power` | `11-research/research-statistics.md` | wave 1 |
| `research.portfolio.mean_variance`, `research.portfolio.risk_parity`, `risk.contrib.euler` | `07-portfolio/optimisation.md` | wave 2 (specified) |
| `research.estimate.ledoit_wolf`, `research.estimate.black_litterman` | `07-portfolio/estimation.md` | wave 2 (specified) |
| `risk.backtest.es_z2` | `06-risk/es-backtest.md` | wave 2 (specified) |
| `research.regime.baum_welch` | `11-research/baum-welch.md` | wave 2 (specified) |
| `risk.scenario.historical_shock`, `risk.scenario.replay` | `06-risk/scenario-stress.md` | wave 3 |
| `research.backtest.interp_loo`, `research.backtest.surface_holdout` | `11-research/interp-backtest.md` | wave 3 |
| `research.drift.cusum`, `research.drift.page_hinkley`, `research.drift.psi`, `research.drift.ks` | `11-research/drift-detectors.md` | wave 3 |

Wave 2 (rulings `stage-j-rulings-w2.md` J-W2-1 to J-W2-15) adds no error code and raises the contract to 1.14.0 (J-W2-1); all four builds implement the wave 2 operations and report 1.14.0. The wave 2 page limits (J-W2-14) replace the general per-array limit as J-20 does for wave 1.

### Stage J curves lane (contract 1.15.0)

Rulings `stage-j-rulings-curves.md` J-C-1 to J-C-9. No new error code; the general per-array limit applies. Implemented in all four builds. These rows take precedence over the `repo.*` and `eq.forward.*` rows above for the names they list.

| Prefix | Spec | Slice |
|---|---|---|
| `repo.term.curve`, `eq.forward.term_financed` | `02-curves/financing-term-structure.md` | curves lane |
| `liq.curve.cost` | `10-execution/liquidity-curve.md` | curves lane |

### Stage J wave 3 (contract 1.15.0)

Rulings `stage-j-rulings-w3.md` J-W3-1 to J-W3-17. No new error code; page limits J-W3-14. Implemented in all four builds; the contract number 1.15.0 is shared with the curves lane (J-C-1, J-W3-1).

### Stage H wave 1 (contract 1.16.0 per HR-1 and DR-H8; DR-H7's 1.15.0 was taken by stage J)

Rulings `stage-h-rulings-w1.md` HR-1 to HR-10 (confirmed 2026-11-18). No new error code; `E_LIMIT` sizes HR-9. Goldens in `datasets/golden/stage_h/` (`oracle/python/gen_stage_h_w1.py`). Not implemented yet. Names below are fixed by the oracle lane (2026-11-18) where the spec left them open; they bind all four builds.

| Operation | Spec | Inputs | Outputs |
|---|---|---|---|
| `exec.schedule.twap` | `10-execution/schedules.md` | `quantity`, `n_buckets` (Integer), `mode` (`UNITS`, `CONTINUOUS`) | `slices` (Integers in `UNITS`) |
| `exec.schedule.vwap` | same | `quantity`, `profile`, `mode` | `slices` |
| `exec.schedule.pov` | same | `quantity`, `participation`, `market_volume`, `mode` | `slices`, `filled`, `residual` |
| `exec.ac.trajectory` | `10-execution/almgren-chriss.md` | `quantity`, `horizon`, `n_steps` (Integer), `sigma`, `epsilon`, `eta`, `gamma`, `risk_aversion` | `holdings`, `trades`, `kappa` (0 when linear), `expected_cost`, `variance`, `objective` |
| `exec.ac.frontier` | same | as `exec.ac.trajectory` with `risk_aversions` (array) in place of `risk_aversion` | parallel arrays `risk_aversions`, `expected_costs`, `variances` |
| `exec.impact.sqrt` | `10-execution/impact.md` | `quantity`, `daily_volume`, `daily_vol`, `coefficient` | `impact`, `model` (the HR-10 label string, always) |
| `exec.impact.ow_optimal` | same | `quantity`, `horizon`, `resilience` (rho <= 0 or T <= 0: `E_DOMAIN`) | `initial_block`, `rate`, `final_block` |
| `exec.tca.shortfall` | `10-execution/tca.md` | `side` (`BUY`, `SELL`), `decision_price`, `arrival_price`, `end_price`, `order_quantity`, `fills` (array of `{quantity, price}`), `fees`, optional `benchmark_vwap` | `delay`, `execution`, `opportunity`, `total`, `total_bps`; `vwap_slippage` only when `benchmark_vwap` is given |
| `micro.mm.as_quotes` | `09-microstructure/avellaneda-stoikov.md` | `mid`, `inventory`, `risk_aversion`, `sigma`, `time_left`, `k` | `reservation`, `spread`, `bid`, `ask` |
| `usecase.execution_tca` | `04-pricing/use-cases.md` (use case 5) | see the spec | `lots`, `expected_cost`, `variance`, `filled`, `fees`, `delay`, `execution`, `opportunity`, `total`, `total_bps` |

## Stage H wave 2 operations

No new error code. Prices, quantities and fees are decimal strings (HR-12); outputs are canonical JSON (HR-29). The specs' Errors lines give the page limits (`micro.book.rebuild` 50,000,000 messages, HR-17; `exec.sim.lit.run` 10,000,000 events), which replace the general per-array limit for those arrays. Goldens `datasets/golden/stage_h/ob_h.json`, `lit_h.json`, `dark_h.json` and `sor_h.json` (`oracle/python/gen_stage_h_w2.py`). All five wave 2 operations (`micro.book.rebuild`, `exec.sim.lit.run`, `exec.sim.dark.run`, `exec.sim.dark.markouts`, `exec.sor.allocate`) are implemented in all four builds.

| Prefix | Spec | Slice |
|---|---|---|
| `micro.book.rebuild` | `09-microstructure/order-book.md` | wave 2 (H-2) |
| `exec.sim.lit.run` | `10-execution/lit-matching.md` | wave 2 (H-11); every output carries `label` "simulated venue; not a real exchange" |
| `exec.sim.dark.run` | `10-execution/dark-pool.md` | wave 2 (H-12); one run (`config`, `events`) or `scenarios`; every run carries `label` "simulated venue; not a real dark pool"; `events` up to 10,000,000 |
| `exec.sim.dark.markouts` | `10-execution/dark-pool.md` (Adverse selection; name set by the H-12 lane, the spec names no verb) | wave 2 (H-12); each markout element carries `label` |
| `exec.sor.allocate` | `10-execution/smart-order-router.md` | wave 2 (H-13); `method` default `SAMPLE_AVERAGE`; optional `ranking` (true adds the full ranking, grid at most 10^6 points) and `report_se` (adds `expected_cost_se` and `label` "simulated venues; router scored in simulation only"); `lit_samples` up to 1,000,000 |

## Stage H multi-asset operations (H-22, H-23, H-24)

Rulings `stage-h-rulings-multiasset.md` HR-80 to HR-103 and the 2026-11-18 rule-version rulings, with HR-118 to HR-120 of 2026-11-19 (compliance dates per rule). No new error code; error order HR-122 (which reconciles HR-66 with "Error precedence" above). Decimals are HR-12 decimal strings; venue and simulator outputs (`exec.*`) carry `label` (HR-94), convention outputs (`micro.*`) none (HR-111). `exec.sim.lit.run` gains optional `session` and `PHASE` events (HR-112, goldens `ses_h`); `exec.sim.dark.run` `config.asset_class` and `exec.sor.allocate` `asset_class` on the order and venues (HR-93; other classes on a dark venue are `E_INPUT`, HR-113; goldens `acls_h`). Goldens `datasets/golden/stage_h/auc_h.json`, `eqc_h.json`, `fxc_h.json`, `fxv_h.json`, `rtc_h.json`, `fut_h.json`, E1 cases `e1_h4.json` (`oracle/python/gen_stage_h_ma.py`). Implemented in all four builds (the Rust build reuses its lit engine for `exec.sim.fut.run`). Integer inputs within +-(2^53-1), `request_index` within 0..2^32-1, else `E_LIMIT` (HR-116).

| Operation | Spec | Inputs | Outputs |
|---|---|---|---|
| `micro.eq.round_price` | `09-microstructure/asset-conventions.md` 1.1 | `price`, `side`, optional `tick_table`, `tick_tier` (`PENNY`, `HALF_PENNY`), `as_of`, `compliance_date` | `price` at the tick decimals |
| `micro.eq.fee_check` | same 1.5 | `price`, `taker_fee`, `cap_check` (default true), `as_of`, `compliance_date` | `cap`, `taker_fee` |
| `micro.eq.round_lot` | same 1.2 | `price`, `as_of`, `compliance_date` | `round_lot` |
| `micro.eq.settle_date` | same 1.6 | `trade_date`, `settle_lag` (default 1), `holidays` | `settle_date` |
| `exec.sim.auction.uncross` | `10-execution/auction.md` | `orders` (`id`, `side`, `limit` or `MARKET`, `qty` Integer, `seq`, `on_close`), `tick_size`, `ref_price`, `phase`, `tie_break` (`CBOE` default, `IEX`); orders up to 10,000,000, candidates up to 1,000,000 | `price`, `volume`, `imbalance`, `fills`, `residual`, `cancelled` |
| `micro.fx.pip_value` | `asset-conventions.md` 2.1 | `pair`, `notional` | `pip_value`, `currency` |
| `micro.fx.spot_date` | same 2.3 | `pair`, `trade_date`, `holidays` (currency to dates), `t1_pairs` | `spot_date` |
| `exec.sim.fx.stream` | `10-execution/fx-rfq-venue.md` | `mid_path` (`time` Integer, `mid`), `half_spread_pips`, `pair`, `tick` | `quotes` |
| `exec.sim.fx.request` | same | `quote` (`bid`, `ask`, `quote_mid`), `side`, `qty`, `mid_after`, `threshold_pips`, `symmetric`, `p_random_reject`, `u` or (`seed`, `request_index`), `pair` | `outcome`, `price`, `move_pips`; `u` when drawn |
| `micro.rates.parse_32nds` / `micro.rates.format_32nds` | `asset-conventions.md` 3.1 | `text` / `value`, `resolution` | `value` / `text` |
| `micro.rates.tick_value` | same 3.2 | `face`, `tick` | `tick_value` |
| `micro.rates.bond_price` / `micro.rates.bill_price` | same 3.3 | `coupon`, `frequency`, `periods`, `yield` / `discount`, `days` | `price` (9 decimals, half-even) |
| `micro.rates.bond_yield` | same 3.3 | `coupon`, `frequency`, `periods`, `price` | `yield` (Real, Brent 1e-12) |
| `exec.sim.fut.to_ticks` / `exec.sim.fut.to_text` | `10-execution/rates-futures-venue.md` | `price` or `ticks`, `contract` | `ticks` / `text` |
| `exec.sim.fut.pnl` | same (HR-102) | `buy_price`, `sell_price`, `qty`, `fee_per_contract`, `contract` | `pnl`, `fees` |
| `exec.sim.fut.variation` | same (HR-103) | `side`, `qty`, `price`, `settlements`, `contract` | `variation_margin` (one per settlement) |
| `exec.sim.fut.run` | same | `events` (lit events, prices as 32nds or decimals), `fee_per_contract`, `contract` | the `exec.sim.lit.run` output with `fees` and `pnl` per trader |

### Stage H wave 2: microstructure estimators (H-4b) and venue analytics (H-16)

Rulings `stage-h-rulings-micro.md` HR-70 to HR-75 as amended (HR-66). No new error code. Unlike the other wave 2 operations, every number here is a JSON Real (the F-2 finite rule applies: a non-finite input is `E_DOMAIN`); `count` is an Integer. Outputs are binary64, compared to 1e-12 relative (1e-15 absolute at 0). Error order HR-75 as amended (HR-66): structural `E_INPUT`, then `E_DOMAIN`, then value-dependent `E_INPUT`. Goldens `datasets/golden/stage_h/mest_h.json` and `venue_h.json` (`oracle/python/gen_stage_h_micro.py`). Implemented in all four builds (Java sums the venue decimals with `BigDecimal`, C++ with its own arbitrary-precision integers, Rust with a small unbounded integer as the bounded `Dec` of HR-57 cannot hold every product; each makes one correctly rounded division per output). The planted-truth simulations (HR-71) are tests, not operations: the Python tests draw with `numpy.random.default_rng`, and the Java, C++ and Rust tests use ports of that generator (SeedSequence, PCG64 and the numpy draws used), checked draw by draw against numpy, so all four run the same seeds on the same streams and miss the same coverage seeds.

| Operation | Spec | Inputs | Outputs |
|---|---|---|---|
| `micro.est.arrival_rate` | `09-microstructure/micro-estimators.md` | `count` (Integer), `window` | `lambda`, `se` |
| `micro.est.cancel_rate` | same | `orders` (array of `{lifetime, outcome}`, outcome `CANCEL` or `FILL`) | `theta`, `se` |
| `micro.est.resilience` | same | `s_inf`, `points` (array of `{t, s}`) | `kappa`, `se` |
| `micro.est.liquidity_decay` | same | `levels` (array of `{k, depth}`) | `alpha`, `se` |
| `micro.est.adverse_selection` | same | `x`, `y` (equal-length arrays) | `lambda_as`, `se` |
| `micro.est.regime_impact` | same | `regimes` (object, label to `{x, y}`; `calm` and `stressed` required) | `regimes` (label to `{lambda_as, se}`), `ratio` |
| `micro.est.passive_vs_aggressive` | same | `passive`, `aggressive` (costs in bp) | `delta`, `se` |
| `exec.venue.analytics` | `10-execution/venue-analytics.md` | `mids` (array of `{t, mid}`), `fills` (array of `{venue, side, quantity, price, t}`), `orders` (array of `{venue, sent, filled}`), `horizons` | `fill_rates` (venue to rate), `markouts` (array of `{venue, h, markout, markout_bps, toxicity}`, venues in code-point order, horizons in input order) |

### Stage H wave 2 execution (H-14, H-17; rulings HR-59 to HR-66)

Specs `10-execution/adaptive-algos.md` and `10-execution/tca-pretrade.md`. No new error code; error precedence HR-122 (`E_SCHEMA`, `E_LIMIT` for a size limit on the input, the finite rule, structural `E_INPUT`, `E_DOMAIN`; it narrows HR-66's "`E_LIMIT` last" to limits that arise after validation). `n_buckets` at most 100,000 and attribution `fills` at most 1,000,000 (as HR-9). Goldens `datasets/golden/stage_h/alg_h.json` and `tcx_h.json` (`oracle/python/gen_stage_h_w2_exec.py`); E1 goldens (F-2: a NaN at one Real input is `E_DOMAIN`) in `e1_h3.json`. Implemented in all four builds; an unlisted `side`, `pair_mode` or `mode` is `E_SCHEMA` (`enum_h.json`). `mode` is `UNITS` or `CONTINUOUS` (absent: `CONTINUOUS`); `side` is `BUY` or `SELL`.

| Operation | Spec | Inputs | Outputs |
|---|---|---|---|
| `exec.algo.arrival` | `10-execution/adaptive-algos.md` | `quantity`, `n_buckets` (Integer), `urgency`, `mode` | `slices` |
| `exec.algo.close` | same | `quantity`, `close_volume`, `auction_participation`, `profile`, `mode` | `auction_quantity`, `slices` |
| `exec.algo.liquidity_seek` | same | `side`, `quantity`, `limit_price`, `take_fraction`, `books` (array of buckets, each an array of `[price, size]` best first) | `slices`, `avg_prices` (null for an empty bucket), `filled`, `residual`, `notional`, `avg_fill_price` (null when nothing filled) |
| `exec.algo.pair` | same | `leg_a` `{side, quantity, price}`, `leg_b` `{side, price}`, `pair_mode` (`CASH_BALANCED`, `HEDGED`), `hedge_ratio` (HEDGED only), `n_buckets`, `mode` | `slices_a`, `slices_b`, `quantity_b`, `cash_imbalance` |
| `exec.algo.basket` | same | `legs` (array of `{side, quantity, price}`), `n_buckets`, `mode` | `slices` (one array per leg), `cash_imbalance`, `gross_notional` |
| `exec.tca.pretrade` | `10-execution/tca-pretrade.md` | `quantity`, `adv`, `daily_vol`, `participation`, `half_spread_bps`, `params` `{a1, a2, a3, a4, b1}`, optional `price` | `istar_bps`, `impact_bps`, `spread_bps`, `expected_cost_bps`, `duration_days`, `timing_risk_bps`; with `price` also `expected_cost`, `timing_risk` |
| `exec.tca.attribution` | same | `side`, `decision_price`, `arrival_mid`, `end_price`, `order_quantity`, `fills` (array of `{quantity, price, mid}`), `fees` | `delay`, `impact`, `spread`, `execution`, `opportunity`, `fees`, `total`, `total_bps` |

## Stage H paper trading operations (H-21, owner decision 2026-11-18: all four builds)

Spec `10-execution/paper-trading.md`, rulings HR-42 to HR-55. Goldens `datasets/golden/stage_h/pt_h.json` and `e1_hpt.json` (`oracle/python/gen_stage_h_pt.py`). Implemented in all four builds (Java: `org.quantforge.paper.Paper`; C++ with the TCA built with `-ffp-contract=off`; Rust: `quantforge_core::paper`, decimals as the Python reference in `paper_dec.rs`); each reproduces the Python ledger hashes byte for byte. Dark pool and SOR are in all four builds (stage-h2/stage-h3), so DARK and SOR sessions are portable too. No new error code.

**Simulated only.** No operation opens a socket, reads a credential or names an order-entry endpoint. An order with `mode` other than `"simulated"` (absent means simulated) is `E_UNSUPPORTED_OPERATION` (HR-42). The runner reads that code as "not implemented", so the live-mode case (spec pt_h-0018) is not a golden: every build pins it in its own unit tests (acceptance test A5).

**Numbers.** Every price, quantity, cash amount, fee and rate, in and out, is an HR-12 decimal string: no exponent, no trailing zeros after the point, `"0"` for zero (so `"-0.00"` is written `"0"`), arithmetic exact; inputs at most 36 digits and 18 decimals, computed values at most 36 digits and 36 decimals, else `E_LIMIT`; average cost rounded half-even to 18 decimals, financing to 0.01 (HR-77, `paper-trading.md`). A JSON number where a decimal string is expected is `E_SCHEMA`. A non-finite token (`"NaN"`, `"Infinity"`, `"-Infinity"`) in a decimal-string input, including any string leaf of a ledger `body`, is a malformed decimal, `E_SCHEMA` (HR-12, ruling F-2a), as for the wave 2 venue verbs. Only `seq`, `days`, `orders_today` and `max_orders_per_day` are JSON integers; `kill_switch` and `allow_short` are booleans. Every output carries `label` `"crypto venue; simulated"` (HR-43).

| Operation | Inputs | Outputs |
|---|---|---|
| `paper.book.apply_fill` | `fills` (array of `{side, quantity, price, fee}`, fee default `"0"`), optional `cash`, `position` (default `"0"`), `avg_cost` (default `"0"`); one symbol | `position`, `avg_cost`, `realised`, `fees`, and `cash`, or `cash_delta` when no `cash` is given |
| `paper.book.end_of_day` | `cash_open`, optional `fills` (applied during the day), `position_open` (default `"0"`), `avg_cost_open` (default `prev_close`), `prev_close` (required when `position_open` is not 0), `close` (required when there is a position or a fill), `days` (Integer, default 1), `cash_rate`, `debit_rate`, `borrow_rate` (default `"0"`) | `market`, `trading`, `fees`, `financing`, `cash_interest`, `short_borrow`, `total`, `position`, `cash_close`; `nav_open` and `nav_close` only when `close` is given |
| `paper.pretrade.check` | `order` (`side`, `type`, `quantity`, `limit_price` unless MARKET, optional `mode`), `ref_price`, `position` (default `"0"`), `cash`, `orders_today` (Integer, default 0), `limits` (`max_order_qty`, `max_notional`, `max_abs_position`, `price_band`, `max_orders_per_day`, optional `kill_switch` false, `allow_short` true) | `accepted`, `reasons` (HR-49 order) |
| `paper.ledger.append` | `seq` (Integer), `ts`, `kind`, `body` (object of strings, arrays and objects), optional `prev` (default 64 zeros) | `canonical_bytes` (string), `hash`, `record` (with `label` and `hash`) |
| `paper.ledger.verify` | `text` (the JSON Lines file as one string) | `ok`, `records`, `first_bad_seq`, `reason`, `head` |
| `paper.session.run` | `cash`, `limits` (as above), `lit` (`tick_size`, `lot_size`, `fee_schedule` of `exec.sim.lit.run`), optional `dark` (config of `exec.sim.dark.run`), `script` (array of steps, below) | `results` (one per step), `records` (every ledger record in order, with `hash`), `head`, `positions` (symbol to signed position, intraday fills included), `cash` (intraday fills included), `label`, `ceiling` |

Order of checks for `paper.pretrade.check`: schema (`side`, `type`, `quantity` present; decimal strings; limits present), then `mode` (`E_UNSUPPORTED_OPERATION`), then unknown side or type (`E_INPUT`), then `E_DOMAIN` (quantity or reference price not positive), then a missing `limit_price` on a non-MARKET order (`E_SCHEMA`) or a non-positive one (`E_DOMAIN`), then the eight checks, all evaluated.

**`paper.ledger.verify`.** Lines are split as Python `str.splitlines` does (a valid record never holds a raw line-break character, so for a valid file this is splitting on `
`; a final newline adds no record). For each line in order, the first failing test gives the reason: `PARSE` (not a JSON object, a key repeated at any level (HR-78), no `hash`, or a JSON number other than `seq` anywhere in the record), `SEQ` (`seq` differs from the line index), `HASH`, `LINK`, `LABEL`. `records` is the number of records that verified before the first bad one (all of them when ok); `first_bad_seq` is that line's index, null when ok; `head` is the last hash when ok (64 zeros for an empty text, which is ok with 0 records), otherwise null.

**`paper.session.run` script.** Each step has `op` and `ts` (string). `SUBMIT`: `order` (`order_id`, `symbol`, `side`, `type`, `quantity`, `limit_price` unless MARKET, `venue` `LIT` (default), `DARK` or `SOR`, optional `mode`), `snapshot` (`{bids, asks}`, each `[[price, qty], ...]` best first), optional `contra` (dark contra events), optional `router` (the `exec.sor.allocate` inputs without `S`). Result `{status: "DONE" or "OPEN", filled}` or `{status: "REJECTED", reasons}`. `CLOSE`: `prev_marks`, `marks` (symbol to price), optional `days`, `cash_rate`, `debit_rate`, `borrow_rate`; result `{status: "CLOSED", eod}` with `eod` the EOD record body (`market`, `trading`, `fees`, `financing`, `interest`, `borrow`, `total`, `nav`, `label`, `ceiling`).

Step semantics are those of the Python `Session` (`paper_fills.py`), which the ports follow exactly:
- Pre-trade on the snapshot mid (best bid + best ask) / 2, with intraday position and cash (fills of the day included) and the count of orders already submitted today (rejected ones count).
- A rejection writes one `REJECT` record (the order without `mode`, plus `reasons`) and nothing else.
- Accepted: one `ORDER` record (the order without `mode`, plus `decision_price` = mid). The order is replayed into the venue seeded with the snapshot: for `LIT`, `exec.sim.lit.run` with events asks first then bids, each level a `NEW` `LIMIT` order with id `BOOK-asks-i` or `BOOK-bids-i` and trader `BOOK`, then our order (id = `order_id`, trader `PAPER`, `price` omitted for MARKET).
- One `FILL` record per venue fill of our order, in venue order: `order_id`, `child_id`, `venue`, `symbol`, `side`, `quantity`, `price`, `fee` (taker fee x qty x price when we take, minus maker rebate x qty x price when we make).
- When nothing rests and the order is not fully filled (IOC or MARKET remainder, venue reject), one `CANCEL` record (`order_id`, `quantity` = unfilled).
- At `CLOSE`: for each accepted order of the day, in submit order, a `CANCEL` if it has a resting remainder (HR-48), then its `TCA` record (`order_id`, `delay`, `execution`, `opportunity`, `total`, `total_bps`; decision and arrival = the submit mid, end = the close mark); then one `EOD`. The day's fills are applied to the book only here; `positions` and `cash` in the output include them either way. All records of a step carry the step's `ts`.
- A duplicate `order_id` within a day or an unknown venue: `E_INPUT`. `DARK` and `SOR` replay through that build's `exec.sim.dark.run` and `exec.sor.allocate`.

### Canonical bytes and hash (HR-45), byte-exact in every build

The hash input is the record without its `hash` key, serialised as:
1. Object keys sorted by Unicode code point at every level (keys here are ASCII, so byte order); array order kept.
2. No whitespace: `,` between members and elements, `:` between key and value.
3. Strings in double quotes. Escapes: `\"`, `\\`, `\b`, `\f`, `\n`, `\r`, `\t`; every other code point below U+0020 and every code point above U+007E as `\uXXXX` with lowercase hex (`é`, `\u007f`), a code point above U+FFFF as its UTF-16 surrogate pair (`😀`). `/` is not escaped. This is Python `json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)`.
4. `seq` is a JSON integer in plain decimal (`0`, `17`); `true`, `false`, `null` as literals; every other number is a decimal string. A JSON number anywhere else is `E_INPUT` on append and `PARSE` on verify.
5. The bytes are ASCII; `hash` is the lowercase hex SHA-256 of them (FIPS 180-4).

The stored line is the full record (with `hash`) in the same form, followed by `\n`. Check value: pt_h-0020 hashes to `72c85984abb1b7c4072c65dbba0567b3de51279645b0ad63cfd242137aed7e81`.

**TCA record values.** `exec.tca.shortfall` runs in binary64 in this order: delay = s x filled x (arrival - decision); execution = s x (the array-order sum, from 0.0, of q x (p - arrival)); opportunity = s x (Q - filled) x (end - decision) + 0.0; total = delay + execution + opportunity + fees; total_bps = total / (Q x decision) x 1e4. Each input is the binary64 nearest its decimal; `fees` is the exact decimal sum of the order's fill fees, converted once; `filled` is the binary64 sum of the fill quantities in order. Each output is written as the shortest round-trip decimal of the binary64 (Python `repr`, Java 19+ `Double.toString`, Rust `{}`, C++ `std::to_chars` without precision), then as an HR-12 decimal string (no exponent: `1e-05` becomes `"0.00001"`, `-0.0` becomes `"0"`). These bytes enter the hash, so a last-bit difference breaks the chain: keep this operation order and no FMA contraction.
## Stage K wave 1 operations (contract 1.17.0; rulings `stage-k-rulings-w1.md` KR-1 to KR-17, confirmed 2026-11-19 except KR-8)

Contract number 1.17.0 for all stage K waves (owner decision K-QC, 2026-11-18). The stage K coordinator lane confirmed the wave-1 rulings on 2026-11-19 with all four builds carrying wave 1, so every build and the runner report 1.17.0 from that change. No new error code. Error order HR-66: `E_SCHEMA`, structural `E_INPUT` (lengths, empty lists, log order), `E_DOMAIN` (the F-2 finite rule first, then single values), value-dependent `E_INPUT` (the stale-cache check), `E_LIMIT` (the spec sizes below, checked last). Goldens `datasets/golden/stage_k/` (`oracle/python/gen_stage_k_w1.py`): `bt_k`, `inc_k`, `trig_k`, `idr_k`, `rich_k`, `e1_k` (F-2) and `e2_k` (two errors at once, HR-66 order). Implemented in all four builds (Python `quantforge_core.stage_k`, Java `org.quantforge.risk.StageK`, C++ `core/stage_k.cpp`, Rust `quantforge_core::stage_k`). `bound` of `risk.intraday.delta_gamma_bound` uses `abs(notional)` (KR-15) and is the exact-arithmetic Lagrange bound evaluated in binary64 (KR-17). Names below are fixed by the oracle lane where the spec left them open; they bind all four builds.

| Operation | Spec | Inputs | Outputs |
|---|---|---|---|
| `core.store.bitemporal_query` | `01-core/bitemporal-store.md` | `records` (each `sequence`, `series_id`, `valid_from`, `valid_to` (instant or null, key required), `knowledge_time`, `value` (any JSON, key required), optional `deleted`; at most 1,000,000), `series_id`, `knowledge_as_of`, `valid_at` | `status` (`FOUND`, `WITHDRAWN`, `NONE`), `row` (`sequence`, `valid_from`, `valid_to`, `knowledge_time`, `value`; instants in `Z` form) or null (KR-14) |
| `curve.bootstrap.par_annual` | `02-curves/incremental-update.md` | `quotes` (1 to 200, each > -1) | `discount_factors` |
| `curve.incremental.update` | same | `previous_quotes`, `previous_discount_factors` (bit-equal to the bootstrap, else `E_INPUT`), `new_quotes` (equal lengths) | `discount_factors`, `first_changed_index` (Integer or null), `recomputed` (Integer) |
| `calib.trigger.check` | `03-calibration/recalibration-triggers.md` | `changes` (2 to 100,000), `x_ref`, `x_now`, `days_since` (Real >= 1), `k` (> 0) | `fire`, `sigma`, `threshold`, `false_alarm_rate` |
| `risk.intraday.delta_gamma_bound` | `06-risk/intraday-risk-bounds.md` | `positions` (1 to 100,000 of `{notional, maturity > 0, yield}`), `shift` | `estimate_pnl`, `bound` (per-position `M3` uses `|notional|`), `label` "latency-aware analytics on simulated data" (KR-10) |
| `num.richardson.check` | `06-risk/bermudan-ladder-k8.md` | `values` (exactly 3), `ratio` (> 1), `assumed_order` (> 0) | `status` (`OK`, `ORDER_MISMATCH`, `NON_MONOTONE`), `observed_order` (or null), `extrapolated` (or null) |

New optional input `method` on `rates.shortrate.bermudan_swaption` and `rates.shortrate.bermudan_ladder` (KR-8 as revised by KR-18; spec `06-risk/bermudan-ladder-k8.md` 0.2.0): absent or `G18_IMPLICIT` is the pinned G-18 scheme, unchanged; `CN_RANNACHER_SMOOTHED` is the K-8 scheme; another value, or a value that is not a string, `E_SCHEMA`, before every other check. Outputs are the G-18 fields. Error order for both methods: `E_SCHEMA`; the grid size limits `nx` at most 10,001 and `steps_per_year` at most 100,000 (`E_LIMIT`, G-31: after `E_SCHEMA`, before F-2 and the domain checks); curve and model; `start_years`; payments; `swaption_type`; `exercise_times` (structural `E_INPUT`); then the grid (`nx` odd and at least 5, `steps_per_year` at least 1: `E_INPUT`; `width` above 0: `E_DOMAIN`). Implemented in all four builds (Python `quantforge_core.bermudan_k8`, Java `org.quantforge.pricing.BermudanK8`, C++ `core/bermudan_k8.cpp`, Rust `quantforge_core::bermudan_k8`). Goldens `k8_k` (14 cases: 7 values, 7 errors, 3 of them with two errors; `oracle/python/gen_stage_k_k8.py`, values from the Python build, not an independent oracle) and four G-18 two-error cases in `e2_k`. The default stays `G18_IMPLICIT` (KR-8). The R6 use restriction is lifted for `CN_RANNACHER_SMOOTHED` only (2026-11-19, KR-110): acceptance 1 to 3 pass in Python and acceptance 3 in Java (`oracle/K8_ACCEPTANCE_W2.json`), and acceptance 3 in C++ and Rust is recorded in `oracle/K8_ACCEPTANCE_PORTS.json`. The first definition failed acceptance 3 in Python and Java (`oracle/K8_ACCEPTANCE_W1.json`, kept as a recorded miss).

### Stage K wave 1b (contract 1.17.0; K-8d SA-CCR, K-8e FRTB IMA backtesting)

Rulings `stage-k-rulings-w1b.md` KR-30 to KR-47. No new error code; the contract number stays 1.17.0 (owner decision K-QC: one number for all stage K waves). Error order HR-122: `E_SCHEMA` (enum values included), `E_LIMIT`, the finite rule, structural `E_INPUT`, `E_DOMAIN`. Reals binary64, class `simple_analytic`; counts, zones, flags, `mpor_days` and the tabulated multiplier exact. Shared tables `06-risk/sa-ccr-parameters.json` and `06-risk/frtb-ima-backtest-tables.json` (one copy: Rust `include_str!`, C++ `#embed`, Java classes generated by `tools/gen_k_w1b_tables.py`). Goldens `datasets/golden/stage_k/saccr_k.json`, `btk_k.json`, `tlk_k.json` (`oracle/python/gen_stage_k_w1b.py`). Implemented in all four builds (registered at integration on `k-r1`, 2026-11-19).

| Operation | Spec | Inputs | Outputs |
|---|---|---|---|
| `risk.saccr.ead` | `06-risk/sa-ccr.md` (K-8d) | `trades` (class, notional, market value, maturity, position, kind, treatment, start and end, hedging set, entity, subclass, option or CDO fields), optional `collateral`, `margin`, `ir_offset` | `ead`, `rc`, `pfe`, `multiplier`, `addon_aggregate`, `addon` (by class), `v`, `c`, `margined`, `mpor_days`, `ead_unmargined`, `capped`, `hedging_sets`, `trades` (per trade `id`, `supervisory_duration`, `adjusted_notional`, `maturity_factor`, `delta`, `effective_notional`, `supervisory_factor`) |
| `risk.frtb.backtest.zone` | `06-risk/frtb-ima-backtest.md` (K-8e) | `observations` (Integer 1 to 1,000,000), `exceptions_actual`, `exceptions_hypothetical` (Integers 0 to n) | `exceptions`, `cumulative_probability`, `zone` (`GREEN`, `AMBER`, `RED`), `amber_from`, `red_from`, `multiplier` (n = 250 only, else null) |
| `risk.frtb.backtest.desk` | same | `observations`, four Integer counts (99% and 97.5%, actual and hypothetical) | the two maximum counts, two cumulative probabilities, `breach_99`, `breach_975`, `eligible` |
| `risk.frtb.backtest.count` | same | `var`, `actual`, `hypothetical` (equal-length arrays of Real or null) | `observations`, `exceptions_actual`, `exceptions_hypothetical`, `exceptions`, `days_actual`, `days_hypothetical` |

### Stage K margin rename (contract 1.17.0; rulings `stage-k-rulings-margin.md` KR-150 to KR-155)

`xva.sbim.ir_delta` is the stage G operation formerly named `xva.simm.ir_delta`, with the same inputs, outputs, error codes and error order (`06-risk/xva-framework.md`, G-43). The old id is a deprecated alias until v1.0.0 (section "Deprecated aliases"). Adding the new id is a minor change under "Versioning", and KR-1 gives every stage K change the one number 1.17.0, so the contract number does not move (KR-154). The goldens' weights and correlations are now placeholder weights from a stated rule (KR-150, `specifications/tables/stage_k/sbim-ir-delta-g.json`); the formula is unchanged. Goldens `datasets/golden/stage_g/sbim_g.json` and `datasets/golden/stage_k/sbim_alias_k.json` (`oracle/python/gen_stage_g_w4b.py`).
