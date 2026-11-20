# P&L explain: 2026-11-20

Result: **PASS** (4 checks, 0 failed, 0 warnings). Generated 2026-11-20T22:12Z by `tools/workflows/`. Batch command: rust `quantforge --batch`.

Real moves of a proxy curve; synthetic product terms. USD proxy curve: Treasury par yields bootstrapped with SOFR OIS conventions. Not a SOFR swap curve. Years [2026], 7 day pairs, implementation rust. Threshold: spec `06-risk/pnl-explain.md`.

## Explained share by product

| Product | Days | Explained | Errors | Share | p50 rel | p95 rel | p99 rel | Spearman (reported) | KS D (reported) |
|---|---|---|---|---|---|---|---|---|---|
| OIS 2Y RECEIVE | 7 | 7 | 0 | 100.0% | 3.90e-04 | 1.80e-03 | 1.80e-03 | 1.0000 | 0.1429 |
| OIS 10Y RECEIVE | 7 | 7 | 0 | 100.0% | 1.78e-03 | 6.65e-03 | 6.65e-03 | 1.0000 | 0.2857 |
| OIS 30Y PAY | 7 | 7 | 0 | 100.0% | 4.56e-03 | 1.08e-02 | 1.08e-02 | 1.0000 | 0.1429 |
| Bond 4.25% 2035 | 7 | 7 | 0 | 100.0% | 1.33e-03 | 6.17e-03 | 6.17e-03 | 1.0000 | 0.1429 |


## Worst days

| Product | Start | End | Unexplained | Full P&L | Largest move (bp) |
|---|---|---|---|---|---|
| OIS 2Y RECEIVE | 2026-11-19 | 2026-11-20 | 110.94 | 61672.80 | 16.0 |
| OIS 2Y RECEIVE | 2026-11-10 | 2026-11-12 | 104.39 | -61435.21 | 16.0 |
| OIS 2Y RECEIVE | 2026-11-13 | 2026-11-16 | 14.92 | 23633.15 | 5.0 |
| OIS 2Y RECEIVE | 2026-11-18 | 2026-11-19 | 7.23 | 18926.28 | 10.0 |
| OIS 2Y RECEIVE | 2026-11-16 | 2026-11-17 | 5.54 | 14224.74 | 3.0 |
| OIS 10Y RECEIVE | 2026-11-19 | 2026-11-20 | 628.22 | 94508.24 | 16.0 |
| OIS 10Y RECEIVE | 2026-11-10 | 2026-11-12 | 600.21 | -93539.73 | 16.0 |
| OIS 10Y RECEIVE | 2026-11-12 | 2026-11-13 | 69.41 | -38906.49 | 5.0 |
| OIS 10Y RECEIVE | 2026-11-13 | 2026-11-16 | 44.62 | 23384.43 | 5.0 |
| OIS 10Y RECEIVE | 2026-11-18 | 2026-11-19 | 30.73 | 23473.08 | 10.0 |
| OIS 30Y PAY | 2026-11-19 | 2026-11-20 | -731.28 | -67561.21 | 16.0 |
| OIS 30Y PAY | 2026-11-10 | 2026-11-12 | -612.73 | 59120.70 | 16.0 |
| OIS 30Y PAY | 2026-11-17 | 2026-11-18 | -210.88 | -37086.36 | 6.0 |
| OIS 30Y PAY | 2026-11-12 | 2026-11-13 | -134.25 | 29422.01 | 5.0 |
| OIS 30Y PAY | 2026-11-13 | 2026-11-16 | -11.39 | -7366.97 | 5.0 |
| Bond 4.25% 2035 | 2026-11-19 | 2026-11-20 | 527.64 | 85475.34 | 16.0 |
| Bond 4.25% 2035 | 2026-11-10 | 2026-11-12 | 490.30 | -82881.51 | 16.0 |
| Bond 4.25% 2035 | 2026-11-13 | 2026-11-16 | 40.29 | 22021.06 | 5.0 |
| Bond 4.25% 2035 | 2026-11-12 | 2026-11-13 | 38.83 | -29242.92 | 5.0 |
| Bond 4.25% 2035 | 2026-11-18 | 2026-11-19 | 19.47 | 17888.12 | 10.0 |


## Checks

| Check | Level | Result | Detail |
|---|---|---|---|
| OIS 2Y RECEIVE explained share >= 95% | fail | ok | 100.0% of 7 days, 0 errors |
| OIS 10Y RECEIVE explained share >= 95% | fail | ok | 100.0% of 7 days, 0 errors |
| OIS 30Y PAY explained share >= 95% | fail | ok | 100.0% of 7 days, 0 errors |
| Bond 4.25% 2035 explained share >= 95% | fail | ok | 100.0% of 7 days, 0 errors |

## Data notices

- Source: US Department of the Treasury.
