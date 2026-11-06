# Clean-room follow-ups

For the four language sessions. Rulings are in `rulings.md`; golden cases are in the `rulings` and `store` suites.

## All four

- Add `core.store.query_as_of`, `latest`, `snapshot`, `replay`, `chain` from `asof-store.md`.
- Check `brent` against the corrected signed acceptance test in `root-finders.md`.
- Run the new `rulings` suite. Each language's file did not state every point, so a suite failure may show a conflict not listed here.

## Conflicts with a stated choice

Taken from each `SPEC_QUESTIONS.md`. No build was run against the new cases.

| Ruling | Java | C++ | Python | Rust |
|---|---|---|---|---|
| D1 `BUS_252` range before zero rule | ok | **Change**: gave 0 | ok | Not stated |
| G4 absent `bid` is `E_SCHEMA` | **Change**: treated as `null` | Not stated | Not stated | Not stated |
| G5 `order` not listed is `E_SCHEMA` | **Change**: `E_INPUT` | **Change**: `E_INPUT` | ok | ok |
| G6 unused `frequency` ignored | ok | Not stated | **Change**: `E_SCHEMA` | ok |
| C1 check 4 applies at `t = 0` | Not stated | **Change**: gave 1 | ok | ok |
| R1 one of `a`, `b` is `E_SCHEMA` | ok | ok | **Change**: `E_INPUT` | Not stated |
| I1 `max_depth < 1` is `E_INPUT` | Not stated | ok | **Change**: allowed 0 | Not stated |
| S2 `r_squared` is `null` on constant `y` | ok | **Change**: `E_NON_FINITE` | **Change**: `E_NON_FINITE` | **Change**: `E_NON_FINITE` |
| T1 only the input is range-checked | ok | ok | **Change**: `E_DATE_RANGE` | Not stated |
| R4 signed Brent test | Check | Check | **Change**: stated absolute value | Check |

## Input limits and store rulings

All four add these. They come from `limits.md` and rulings A1 to A6, and no build has been run against them.

- Add `E_LIMIT`, checked after `E_SCHEMA` and before rule checks, for every row of `limits.md`. Run the `limits` suite.
- Stop adaptive quadrature at 10,000,000 function calls, with `E_NO_CONVERGENCE`.
- Stop date walks on leaving 2000 to 2099, with `E_DATE_RANGE`.
- Replace any earlier size checks: `paths` above 1,000,000 was `E_INPUT` at 10,000,000, and `count` in `rng` was `E_SCHEMA`.
- Run the `store_rulings` suite.

| Ruling | Java | C++ | Python | Rust |
|---|---|---|---|---|
| A1 `sequence < 1` is `E_SCHEMA` | ok | ok | ok | ok |
| A2 `E_SCHEMA` before log rule checks | **Change**: log first | **Change**: log first | Not stated | **Change**: log first |
| A3 every record key in the chain | ok | Not stated | Not stated | Not stated |
| A4 lone surrogate is `E_SCHEMA` | **Change**: not rejected | Not stated | ok | Not stated |
| A5 instant outside years 1 to 9999 is `E_DATE_RANGE` | Not stated | Not stated | **Change**: `E_NON_FINITE` | Not stated |
| A6 `head` is the whole log | ok | Not stated | Not stated | ok |

## For the conformance stream

`runner.py` sends cases with `ensure_ascii=False`, then encodes strictly, so a golden case holding a lone surrogate would crash it. Sending with `ensure_ascii=True` would allow one. Ruling A4 has no case until then.
