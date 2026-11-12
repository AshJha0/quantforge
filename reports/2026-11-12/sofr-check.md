# SOFR check: 2026-11-12

Result: **PASS** (25 checks, 0 failed, 0 warnings). Generated 2026-11-12T21:47Z by `tools/workflows/`. Batch command: rust `quantforge --batch`.


## Published averages against the library

NY Fed 30/90/180-day SOFR averages for the last 5 publications. Pass if |library - published| ≤ 1e-07 (published to 5 decimals in percent, so half a unit is 5e-8). Implementation: rust.
| Date | Window (d) | Published (%) | Library (%) | Diff (decimal) | Operation |
|---|---|---|---|---|---|
| 2026-11-05 | 30 | 3.91227 | 3.9122740 | 4.04e-08 | rates.ois.compound_dated |
| 2026-11-05 | 90 | 3.79539 | 3.7953858 | -4.25e-08 | rates.ois.compound_dated |
| 2026-11-05 | 180 | 3.72896 | 3.7289555 | -4.55e-08 | rates.ois.compound |
| 2026-11-06 | 30 | 3.91294 | 3.9129428 | 2.81e-08 | rates.ois.compound_dated |
| 2026-11-06 | 90 | 3.79876 | 3.7987585 | -1.46e-08 | rates.ois.compound |
| 2026-11-06 | 180 | 3.73077 | 3.7307682 | -1.77e-08 | rates.ois.compound |
| 2026-11-09 | 30 | 3.91461 | 3.9146143 | 4.29e-08 | rates.ois.compound |
| 2026-11-09 | 90 | 3.80772 | 3.8077210 | 9.50e-09 | rates.ois.compound_dated |
| 2026-11-09 | 180 | 3.73568 | 3.7356841 | 4.14e-08 | rates.ois.compound_dated |
| 2026-11-10 | 30 | 3.91498 | 3.9149765 | -3.50e-08 | rates.ois.compound |
| 2026-11-10 | 90 | 3.81041 | 3.8104127 | 2.73e-08 | rates.ois.compound_dated |
| 2026-11-10 | 180 | 3.73733 | 3.7373252 | -4.82e-08 | rates.ois.compound_dated |
| 2026-11-12 | 30 | 3.91631 | 3.9163139 | 3.89e-08 | rates.ois.compound_dated |
| 2026-11-12 | 90 | 3.81646 | 3.8164646 | 4.59e-08 | rates.ois.compound_dated |
| 2026-11-12 | 180 | 3.74112 | 3.7411182 | -1.82e-08 | rates.ois.compound |


## SOFR Index

| From | To | Index-implied (%) | Library (%) | Diff |
|---|---|---|---|---|
| 2026-11-05 | 2026-11-06 | 3.92000 | 3.92000 | 2.1e-08 |
| 2026-11-06 | 2026-11-09 | 3.89000 | 3.89000 | 4.1e-08 |
| 2026-11-09 | 2026-11-10 | 3.88021 | 3.88000 | -2.1e-06 |
| 2026-11-10 | 2026-11-12 | 3.89002 | 3.89000 | -2.2e-07 |


## USD-LIBOR-3M fallback

Period 2026-08-11 to 2026-11-10: compounded 3.79716%, spread 0.26161%, fallback 4.05877%.

## Checks

| Check | Level | Result | Detail |
|---|---|---|---|
| SOFR level | fail | ok | 2026-11-10: 0.0389 |
| SOFR day change | fail | ok | 0.0001 vs 0.01 |
| SOFR day change (warn) | warn | ok | 0.0001 vs 0.0025 |
| 30-day average 2026-11-05 | fail | ok | diff 4.04e-08 |
| 90-day average 2026-11-05 | fail | ok | diff -4.25e-08 |
| 180-day average 2026-11-05 | fail | ok | diff -4.55e-08 |
| 30-day average 2026-11-06 | fail | ok | diff 2.81e-08 |
| 90-day average 2026-11-06 | fail | ok | diff -1.46e-08 |
| 180-day average 2026-11-06 | fail | ok | diff -1.77e-08 |
| 30-day average 2026-11-09 | fail | ok | diff 4.29e-08 |
| 90-day average 2026-11-09 | fail | ok | diff 9.50e-09 |
| 180-day average 2026-11-09 | fail | ok | diff 4.14e-08 |
| 30-day average 2026-11-10 | fail | ok | diff -3.50e-08 |
| 90-day average 2026-11-10 | fail | ok | diff 2.73e-08 |
| 180-day average 2026-11-10 | fail | ok | diff -4.82e-08 |
| 30-day average 2026-11-12 | fail | ok | diff 3.89e-08 |
| 90-day average 2026-11-12 | fail | ok | diff 4.59e-08 |
| 180-day average 2026-11-12 | fail | ok | diff -1.82e-08 |
| Index step 2026-11-06 | warn | ok | diff 2.09e-08 |
| Index step 2026-11-09 | warn | ok | diff 4.12e-08 |
| Index step 2026-11-10 | warn | ok | diff -2.07e-06 |
| Index step 2026-11-12 | warn | ok | diff -2.17e-07 |
| fallback computed | fail | ok | ok |
| ISDA 3M spread adjustment | fail | ok | 0.0026161 |
| fallback = compounded + spread | fail | ok | 0.04058773874017708 |

## Data notices

- The SOFR data is subject to the Terms of Use posted at newyorkfed.org. The New York Fed is not responsible for publication of the SOFR data by QuantForge, does not sanction or endorse any particular republication, and has no liability for your use. QuantForge is not affiliated with the New York Fed. The New York Fed does not sanction, endorse, or recommend any products or services offered by QuantForge. The Secured Overnight Financing Rate (SOFR) Data are calculated using data provided under a license granted to the New York Fed by DTCC Solutions LLC ("Solutions"), an affiliate of The Depository Trust & Clearing Corporation. Solutions, its affiliates, and third parties from which they obtained data have no liability for the content of this material.
