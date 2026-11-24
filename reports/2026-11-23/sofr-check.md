# SOFR check: 2026-11-23

Result: **PASS** (7 checks, 0 failed, 0 warnings). Generated 2026-11-24T02:05Z by `tools/workflows/`. Batch command: rust `quantforge --batch`.


## Published averages against the library

NY Fed 30/90/180-day SOFR averages for the last 5 publications. Pass if |library - published| ≤ 1e-07 (published to 5 decimals in percent, so half a unit is 5e-8). Implementation: rust.
15 average(s) skipped: the window starts before the forward start 2026-11-10, inside an R3 holdout (research/preregs/DEVIATION-2026-11-12.md).
| Date | Window (d) | Published (%) | Library (%) | Diff (decimal) | Operation |
|---|---|---|---|---|---|


## SOFR Index

| From | To | Index-implied (%) | Library (%) | Diff |
|---|---|---|---|---|
| 2026-11-17 | 2026-11-18 | 3.92002 | 3.92000 | -2.1e-07 |
| 2026-11-18 | 2026-11-19 | 3.90000 | 3.90000 | 2.7e-08 |
| 2026-11-19 | 2026-11-20 | 3.91008 | 3.91000 | -8.2e-07 |
| 2026-11-20 | 2026-11-23 | 3.91997 | 3.92000 | 2.6e-07 |


## USD-LIBOR-3M fallback

Skipped: a 3M period ending 2026-11-20 starts before the forward start 2026-11-10 (R6-19).

## Checks

| Check | Level | Result | Detail |
|---|---|---|---|
| SOFR level | fail | ok | 2026-11-20: 0.0392 |
| SOFR day change | fail | ok | 0.0001 vs 0.01 |
| SOFR day change (warn) | warn | ok | 0.0001 vs 0.0025 |
| Index step 2026-11-18 | warn | ok | diff -2.07e-07 |
| Index step 2026-11-19 | warn | ok | diff 2.67e-08 |
| Index step 2026-11-20 | warn | ok | diff -8.20e-07 |
| Index step 2026-11-23 | warn | ok | diff 2.59e-07 |

## Data notices

- The SOFR data is subject to the Terms of Use posted at newyorkfed.org. The New York Fed is not responsible for publication of the SOFR data by QuantForge, does not sanction or endorse any particular republication, and has no liability for your use. QuantForge is not affiliated with the New York Fed. The New York Fed does not sanction, endorse, or recommend any products or services offered by QuantForge. The Secured Overnight Financing Rate (SOFR) Data are calculated using data provided under a license granted to the New York Fed by DTCC Solutions LLC ("Solutions"), an affiliate of The Depository Trust & Clearing Corporation. Solutions, its affiliates, and third parties from which they obtained data have no liability for the content of this material.
