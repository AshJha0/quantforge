# CLI contract

Version 1.1.0. `01-core/rulings.md` is part of this contract, and settles points it leaves silent.
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
| `quantforge version` | Write one JSON object: `{"language":..., "implementation_version":..., "contract_version":"1.0.0", "toolchain":...}`. |
| `quantforge operations` | Write a JSON array of the operation names this build supports, sorted. |

`batch` exists because a JVM start per case would dominate run time. `run` and `batch` must give
the same result for the same case. No state may carry from one case to the next.

Output on stdout is UTF-8 JSON with no byte order mark. Anything for humans goes to stderr; the
runner ignores stderr. No command reads the clock, the environment, or any file for its numbers.

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
stream. Any other exit code, or a timeout, is a crash.

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

Order of checks: `E_PARSE`, then `E_SCHEMA`, then the rule checks in the order the operation's spec
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
errors. Stage A:

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

A test function cannot be sent as JSON, so operations that need one name it from the registry in
`01-core/test-functions.md`.

## Versioning

Adding an operation or an error code is a minor version. Changing the meaning of a key, a code or an
exit status is a major version, and all four implementations and the runner move together.
