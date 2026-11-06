# Dataset policy

## Categories
- `synthetic/`: deterministic, generated data for CI and examples.
- `historical/`: licensed or otherwise authorised data; keep out of public Git unless redistribution is explicitly permitted.
- `calibration/`: quote sets with known generating parameters or independent calibration references.
- `marketdata/`: quote, trade, book and event fixtures.
- `instruments/`: instrument definitions, schedules and conventions.
- `execution/`: order, fill, cancellation and market-event replay.
- `edge-cases/`: sparse, stale, crossed, missing, negative-rate and extreme-value cases.
- `golden/`: independently verified expected outputs and provenance.

## Requirements
Every dataset must document schema version, generator/source, timestamp semantics, units, conventions, seed (if generated), licence/redistribution status and expected use. Do not commit secrets or proprietary client/venue data.
