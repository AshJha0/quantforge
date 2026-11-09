# SOFR check: 2026-11-09

Result: **PASS** (25 checks, 0 failed, 0 warnings). Generated 2026-11-09T23:44Z by `tools/workflows/`. Batch command: rust `quantforge --batch`.


## Published averages against the library

NY Fed 30/90/180-day SOFR averages for the last 5 publications. Pass if |library - published| ≤ 1e-07 (published to 5 decimals in percent, so half a unit is 5e-8). Implementation: rust.
| Date | Window (d) | Published (%) | Library (%) | Diff (decimal) | Operation |
|---|---|---|---|---|---|
| 2026-11-03 | 30 | 3.90759 | 3.9075927 | 2.68e-08 | rates.ois.compound |
| 2026-11-03 | 90 | 3.78843 | 3.7884323 | 2.29e-08 | rates.ois.compound_dated |
| 2026-11-03 | 180 | 3.72493 | 3.7249339 | 3.85e-08 | rates.ois.compound_dated |
| 2026-11-04 | 30 | 3.91060 | 3.9106021 | 2.13e-08 | rates.ois.compound_dated |
| 2026-11-04 | 90 | 3.79213 | 3.7921333 | 3.31e-08 | rates.ois.compound_dated |
| 2026-11-04 | 180 | 3.72703 | 3.7270275 | -2.52e-08 | rates.ois.compound_dated |
| 2026-11-05 | 30 | 3.91227 | 3.9122740 | 4.04e-08 | rates.ois.compound_dated |
| 2026-11-05 | 90 | 3.79539 | 3.7953858 | -4.25e-08 | rates.ois.compound_dated |
| 2026-11-05 | 180 | 3.72896 | 3.7289555 | -4.55e-08 | rates.ois.compound |
| 2026-11-06 | 30 | 3.91294 | 3.9129428 | 2.81e-08 | rates.ois.compound_dated |
| 2026-11-06 | 90 | 3.79876 | 3.7987585 | -1.46e-08 | rates.ois.compound |
| 2026-11-06 | 180 | 3.73077 | 3.7307682 | -1.77e-08 | rates.ois.compound |
| 2026-11-09 | 30 | 3.91461 | 3.9146143 | 4.29e-08 | rates.ois.compound |
| 2026-11-09 | 90 | 3.80772 | 3.8077210 | 9.50e-09 | rates.ois.compound_dated |
| 2026-11-09 | 180 | 3.73568 | 3.7356841 | 4.14e-08 | rates.ois.compound_dated |


## SOFR Index

| From | To | Index-implied (%) | Library (%) | Diff |
|---|---|---|---|---|
| 2026-11-03 | 2026-11-04 | 3.97007 | 3.97000 | -7.3e-07 |
| 2026-11-04 | 2026-11-05 | 3.93977 | 3.94000 | 2.3e-06 |
| 2026-11-05 | 2026-11-06 | 3.92000 | 3.92000 | 2.1e-08 |
| 2026-11-06 | 2026-11-09 | 3.89000 | 3.89000 | 4.1e-08 |


## USD-LIBOR-3M fallback

Period 2026-08-07 to 2026-11-06: compounded 3.79084%, spread 0.26161%, fallback 4.05245%.

## Checks

| Check | Level | Result | Detail |
|---|---|---|---|
| SOFR level | fail | ok | 2026-11-06: 0.0389 |
| SOFR day change | fail | ok | 0.0003 vs 0.01 |
| SOFR day change (warn) | warn | ok | 0.0003 vs 0.0025 |
| 30-day average 2026-11-03 | fail | ok | diff 2.68e-08 |
| 90-day average 2026-11-03 | fail | ok | diff 2.29e-08 |
| 180-day average 2026-11-03 | fail | ok | diff 3.85e-08 |
| 30-day average 2026-11-04 | fail | ok | diff 2.13e-08 |
| 90-day average 2026-11-04 | fail | ok | diff 3.31e-08 |
| 180-day average 2026-11-04 | fail | ok | diff -2.52e-08 |
| 30-day average 2026-11-05 | fail | ok | diff 4.04e-08 |
| 90-day average 2026-11-05 | fail | ok | diff -4.25e-08 |
| 180-day average 2026-11-05 | fail | ok | diff -4.55e-08 |
| 30-day average 2026-11-06 | fail | ok | diff 2.81e-08 |
| 90-day average 2026-11-06 | fail | ok | diff -1.46e-08 |
| 180-day average 2026-11-06 | fail | ok | diff -1.77e-08 |
| 30-day average 2026-11-09 | fail | ok | diff 4.29e-08 |
| 90-day average 2026-11-09 | fail | ok | diff 9.50e-09 |
| 180-day average 2026-11-09 | fail | ok | diff 4.14e-08 |
| Index step 2026-11-04 | warn | ok | diff -7.27e-07 |
| Index step 2026-11-05 | warn | ok | diff 2.31e-06 |
| Index step 2026-11-06 | warn | ok | diff 2.09e-08 |
| Index step 2026-11-09 | warn | ok | diff 4.12e-08 |
| fallback computed | fail | ok | ok |
| ISDA 3M spread adjustment | fail | ok | 0.0026161 |
| fallback = compounded + spread | fail | ok | 0.0405245073132062 |

## Data notices

- The SOFR data is subject to the Terms of Use posted at newyorkfed.org. The New York Fed is not responsible for publication of the SOFR data by QuantForge, does not sanction or endorse any particular republication, and has no liability for your use. QuantForge is not affiliated with the New York Fed. The New York Fed does not sanction, endorse, or recommend any products or services offered by QuantForge. The Secured Overnight Financing Rate (SOFR) Data are calculated using data provided under a license granted to the New York Fed by DTCC Solutions LLC ("Solutions"), an affiliate of The Depository Trust & Clearing Corporation. Solutions, its affiliates, and third parties from which they obtained data have no liability for the content of this material.
