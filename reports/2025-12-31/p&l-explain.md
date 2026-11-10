# P&L explain: 2025-12-31

Result: **PASS** (4 checks, 0 failed, 0 warnings). Generated 2026-11-10T21:15Z by `tools/workflows/`. Batch command: rust `quantforge --batch`.

Real moves of a proxy curve; synthetic product terms. USD proxy curve: Treasury par yields bootstrapped with SOFR OIS conventions. Not a SOFR swap curve. Years [2025], 248 day pairs, implementation rust. Threshold: spec `06-risk/pnl-explain.md`.

## Explained share by product

| Product | Days | Explained | Errors | Share | p50 rel | p95 rel | p99 rel | Spearman (reported) | KS D (reported) |
|---|---|---|---|---|---|---|---|---|---|
| OIS 2Y RECEIVE | 248 | 248 | 0 | 100.0% | 3.92e-04 | 1.33e-03 | 2.54e-03 | 0.9961 | 0.0403 |
| OIS 10Y RECEIVE | 248 | 248 | 0 | 100.0% | 1.71e-03 | 5.03e-03 | 6.82e-03 | 0.9997 | 0.0242 |
| OIS 30Y PAY | 248 | 248 | 0 | 100.0% | 3.80e-03 | 1.11e-02 | 1.36e-02 | 0.9999 | 0.0242 |
| Bond 4.25% 2035 | 248 | 248 | 0 | 100.0% | 1.72e-03 | 5.22e-03 | 6.78e-03 | 1.0000 | 0.0121 |


## Worst days

| Product | Start | End | Unexplained | Full P&L | Largest move (bp) |
|---|---|---|---|---|---|
| OIS 2Y RECEIVE | 2025-07-31 | 2025-08-01 | 424.97 | 119776.69 | 25.0 |
| OIS 2Y RECEIVE | 2025-04-08 | 2025-04-09 | 281.92 | -95802.81 | 20.0 |
| OIS 2Y RECEIVE | 2025-04-02 | 2025-04-03 | 243.33 | 95927.34 | 21.0 |
| OIS 2Y RECEIVE | 2025-01-09 | 2025-01-10 | 104.89 | -61740.30 | 15.0 |
| OIS 2Y RECEIVE | 2025-05-01 | 2025-05-02 | 103.27 | -62160.38 | 13.0 |
| OIS 10Y RECEIVE | 2025-04-02 | 2025-04-03 | 1007.30 | 115352.78 | 21.0 |
| OIS 10Y RECEIVE | 2025-07-31 | 2025-08-01 | 978.47 | 114817.43 | 25.0 |
| OIS 10Y RECEIVE | 2025-04-04 | 2025-04-07 | 692.26 | -114892.52 | 17.0 |
| OIS 10Y RECEIVE | 2025-01-14 | 2025-01-15 | 622.64 | 95747.07 | 15.0 |
| OIS 10Y RECEIVE | 2025-06-05 | 2025-06-06 | 545.93 | -88769.60 | 14.0 |
| OIS 30Y PAY | 2025-04-04 | 2025-04-07 | -2756.63 | 139148.83 | 17.0 |
| OIS 30Y PAY | 2025-04-07 | 2025-04-08 | -1663.63 | 104763.62 | 15.0 |
| OIS 30Y PAY | 2025-04-09 | 2025-04-10 | -1512.15 | 110919.09 | 14.0 |
| OIS 30Y PAY | 2025-02-04 | 2025-02-05 | -1149.04 | -88890.67 | 12.0 |
| OIS 30Y PAY | 2025-05-20 | 2025-05-21 | -1125.76 | 92927.91 | 12.0 |
| Bond 4.25% 2035 | 2025-04-02 | 2025-04-03 | 987.84 | 113122.45 | 21.0 |
| Bond 4.25% 2035 | 2025-07-31 | 2025-08-01 | 961.44 | 112670.49 | 25.0 |
| Bond 4.25% 2035 | 2025-04-04 | 2025-04-07 | 743.59 | -119739.90 | 17.0 |
| Bond 4.25% 2035 | 2025-01-14 | 2025-01-15 | 643.31 | 94862.55 | 15.0 |
| Bond 4.25% 2035 | 2025-06-05 | 2025-06-06 | 544.46 | -87546.47 | 14.0 |


## Checks

| Check | Level | Result | Detail |
|---|---|---|---|
| OIS 2Y RECEIVE explained share >= 95% | fail | ok | 100.0% of 248 days, 0 errors |
| OIS 10Y RECEIVE explained share >= 95% | fail | ok | 100.0% of 248 days, 0 errors |
| OIS 30Y PAY explained share >= 95% | fail | ok | 100.0% of 248 days, 0 errors |
| Bond 4.25% 2035 explained share >= 95% | fail | ok | 100.0% of 248 days, 0 errors |

## Data notices

- Source: US Department of the Treasury.
