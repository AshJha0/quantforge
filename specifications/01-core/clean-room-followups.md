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
