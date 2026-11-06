# Dataset policy

## What exists now

| Folder | Holds |
|---|---|
| `golden/core/` | 21 golden suites, 4,388 cases, written only by `oracle/` |
| `schemas/` | JSON schemas for cases, results and market data |
| `synthetic/` | Rules only, so far: no synthetic dataset is committed yet |

No market data is committed. `data-availability.md` says what free data is expected to exist for each planned backtest.

## Planned folders

These are created when a stage first needs them.

- `historical/`: licensed or otherwise authorised data; kept out of Git unless redistribution is explicitly permitted.
- `calibration/`: quote sets with known generating parameters or independent calibration references.
- `marketdata/`: quote, trade, book and event fixtures.
- `instruments/`: instrument definitions, schedules and conventions.
- `execution/`: order, fill, cancellation and market-event replay.
- `edge-cases/`: sparse, stale, crossed, missing, negative-rate and extreme-value cases.

## Requirements
Every dataset must document schema version, generator or source, timestamp semantics, units, conventions, seed if generated, licence and redistribution status, and expected use. Synthetic data is labelled as synthetic wherever it is used. Do not commit secrets or proprietary client or venue data.
