# P&L explain: 2026-11-13

Result: **PASS** (4 checks, 0 failed, 0 warnings). Generated 2026-11-13T21:20Z by `tools/workflows/`. Batch command: rust `quantforge --batch`.

Real moves of a proxy curve; synthetic product terms. USD proxy curve: Treasury par yields bootstrapped with SOFR OIS conventions. Not a SOFR swap curve. Years [2026], 2 day pairs, implementation rust. Threshold: spec `06-risk/pnl-explain.md`.

## Explained share by product

| Product | Days | Explained | Errors | Share | p50 rel | p95 rel | p99 rel | Spearman (reported) | KS D (reported) |
|---|---|---|---|---|---|---|---|---|---|
| OIS 2Y RECEIVE | 2 | 2 | 0 | 100.0% | 1.70e-03 | 1.70e-03 | 1.70e-03 | nan | 0.5000 |
| OIS 10Y RECEIVE | 2 | 2 | 0 | 100.0% | 6.42e-03 | 6.42e-03 | 6.42e-03 | nan | 0.5000 |
| OIS 30Y PAY | 2 | 2 | 0 | 100.0% | 1.04e-02 | 1.04e-02 | 1.04e-02 | nan | 0.5000 |
| Bond 4.25% 2035 | 2 | 2 | 0 | 100.0% | 5.92e-03 | 5.92e-03 | 5.92e-03 | nan | 0.5000 |


## Worst days

| Product | Start | End | Unexplained | Full P&L | Largest move (bp) |
|---|---|---|---|---|---|
| OIS 2Y RECEIVE | 2026-11-10 | 2026-11-12 | 104.39 | -61435.21 | 16.0 |
| OIS 2Y RECEIVE | 2026-11-12 | 2026-11-13 | 1.83 | -9447.29 | 5.0 |
| OIS 10Y RECEIVE | 2026-11-10 | 2026-11-12 | 600.21 | -93539.73 | 16.0 |
| OIS 10Y RECEIVE | 2026-11-12 | 2026-11-13 | 69.41 | -38906.49 | 5.0 |
| OIS 30Y PAY | 2026-11-10 | 2026-11-12 | -612.73 | 59120.70 | 16.0 |
| OIS 30Y PAY | 2026-11-12 | 2026-11-13 | -134.25 | 29422.01 | 5.0 |
| Bond 4.25% 2035 | 2026-11-10 | 2026-11-12 | 490.30 | -82881.51 | 16.0 |
| Bond 4.25% 2035 | 2026-11-12 | 2026-11-13 | 38.83 | -29242.92 | 5.0 |


## Checks

| Check | Level | Result | Detail |
|---|---|---|---|
| OIS 2Y RECEIVE explained share >= 95% | fail | ok | 100.0% of 2 days, 0 errors |
| OIS 10Y RECEIVE explained share >= 95% | fail | ok | 100.0% of 2 days, 0 errors |
| OIS 30Y PAY explained share >= 95% | fail | ok | 100.0% of 2 days, 0 errors |
| Bond 4.25% 2035 explained share >= 95% | fail | ok | 100.0% of 2 days, 0 errors |

## Data notices

- Source: US Department of the Treasury.
