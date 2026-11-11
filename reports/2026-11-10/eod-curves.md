# EOD curves: 2026-11-10

Result: **PASS** (39 checks, 0 failed, 0 warnings). Generated 2026-11-11T21:49Z by `tools/workflows/`. Batch command: rust `quantforge --batch`.


## USD

USD proxy curve: Treasury par yields bootstrapped with SOFR OIS conventions. Not a SOFR swap curve. As of 2026-11-10, 13 tenors. Implementation: rust.
| Pillar | t (y) | DF | Zero (cc, %) | Fwd to pillar (%) |
|---|---|---|---|---|
| 2026-12-16 | 0.099 | 0.99596521 | 4.0991 | 4.0991 |
| 2027-01-15 | 0.181 | 0.99234126 | 4.2518 | 4.4351 |
| 2027-02-18 | 0.274 | 0.98820413 | 4.3311 | 4.4850 |
| 2027-03-17 | 0.348 | 0.98514458 | 4.3015 | 4.1919 |
| 2027-05-17 | 0.515 | 0.97763240 | 4.3920 | 4.5803 |
| 2027-11-17 | 1.019 | 0.95501343 | 4.5164 | 4.6435 |
| 2028-11-15 | 2.016 | 0.90983373 | 4.6862 | 4.8597 |
| 2029-11-15 | 3.016 | 0.86793989 | 4.6954 | 4.7139 |
| 2031-11-17 | 5.022 | 0.78707276 | 4.7678 | 4.8767 |
| 2033-11-16 | 7.022 | 0.71119016 | 4.8536 | 5.0690 |
| 2036-11-17 | 10.027 | 0.60851059 | 4.9538 | 5.1880 |
| 2046-11-15 | 20.027 | 0.33375228 | 5.4793 | 6.0062 |
| 2056-11-15 | 30.036 | 0.20037947 | 5.3521 | 5.0977 |


### USD key-rate risk, sample book

50 synthetic SOFR swaps from `tools/workflows/sample_book.py` (seed 20261107, book sha256 `49456317fff9f842`), fixed rates at par ± up to 100 bp. Figures in USD per 1 bp, sign per `risk.ois.dv01`.
| Key rate | DV01 (USD/bp) |
|---|---|
| 1M | -14.15 |
| 2M | -0.00 |
| 3M | 0.00 |
| 4M | -0.05 |
| 6M | 1.14 |
| 1Y | -992.75 |
| 2Y | -28,589.81 |
| 3Y | 6,351.90 |
| 5Y | -11,163.03 |
| 7Y | 45,708.41 |
| 10Y | 62,575.22 |
| 20Y | 62,532.98 |
| 30Y | -57,000.22 |
| Parallel | 79,409.64 |


## GBP

Reference: Bank of England fitted OIS spot curve (50 maturities) and nominal government spot curve (80 maturities) for 2026-11-10, from the latest yield curve data zip, with SONIA fixings to 2026-11-09. Only pass or fail is published: the curves are Bank copyright, licensed here for internal non-commercial use only, and raw SONIA may not be redistributed until the Bank answers (`tools/recorder/sources.json`); the zip is fetched per run and no raw copy is kept. The library does not build its own GBP curve: free data has no SONIA swap quotes to bootstrap from.

## Checks

| Check | Level | Result | Detail |
|---|---|---|---|
| USD par quotes quote levels | fail | ok | outside band: none |
| USD par quotes adjacent tenor gaps | warn | ok | none |
| USD par quotes day change | fail | ok | largest 1Y 0.0018 |
| USD par quotes day change (warn) | warn | ok | largest 1Y 0.0018 |
| SOFR level | fail | ok | 2026-11-09: 0.0388 |
| SOFR day change | fail | ok | 0.0001 vs 0.01 |
| SOFR day change (warn) | warn | ok | 0.0001 vs 0.0025 |
| USD bootstrap | fail | ok | ok |
| USD curve discount factors in band | fail | ok | min 0.200379, max 0.995965 |
| USD curve discount factors non-increasing | warn | ok | rises after none |
| USD curve zero rates in band | fail | ok | min 0.0409911, max 0.0547928 |
| USD curve forwards in band | fail | ok | min 0.0409911, max 0.0600615 |
| USD fixing vs shortest quote | warn | ok | -0.0017 vs ±0.0075 |
| USD par probe 10Y | fail | ok | ok |
| USD par probe 15Y | fail | ok | ok |
| USD par probe 1Y | fail | ok | ok |
| USD par probe 20Y | fail | ok | ok |
| USD par probe 2Y | fail | ok | ok |
| USD par probe 30Y | fail | ok | ok |
| USD par probe 3Y | fail | ok | ok |
| USD par probe 5Y | fail | ok | ok |
| USD par probe 7Y | fail | ok | ok |
| USD key-rate risk | fail | ok | 50/50 trades ok; failed none |
| USD sum of key rates vs parallel DV01 | warn | ok | sum 79,409.65 vs DV01 79,409.64 |
| SONIA level | fail | ok | 2026-11-09: value withheld |
| SONIA day change | fail | ok | value withheld vs 0.01 |
| SONIA day change (warn) | warn | ok | value withheld vs 0.0025 |
| GBP BoE curves read | fail | ok | OIS 7 days, nominal 7 days |
| GBP BoE OIS spot zero rates in band | fail | ok | value withheld; 50 maturities |
| GBP BoE OIS spot forwards in band | fail | ok | value withheld |
| GBP BoE OIS spot day change | fail | ok | value withheld vs 0.01 |
| GBP BoE OIS spot day change (warn) | warn | ok | value withheld vs 0.003 |
| GBP BoE nominal spot zero rates in band | fail | ok | value withheld; 80 maturities |
| GBP BoE nominal spot forwards in band | fail | ok | value withheld |
| GBP BoE nominal spot day change | fail | ok | value withheld vs 0.01 |
| GBP BoE nominal spot day change (warn) | warn | ok | value withheld vs 0.003 |
| GBP OIS vs nominal gap | warn | ok | value withheld vs 0.015; 50 shared maturities |
| GBP SONIA vs shortest OIS spot | warn | ok | value withheld vs 0.0075; OIS shortest maturity 0.5y |
| GBP BoE curve date vs SONIA | warn | ok | BoE 2026-11-10, SONIA 2026-11-09 |

## Data notices

- Source: US Department of the Treasury.
- The SOFR data is subject to the Terms of Use posted at newyorkfed.org. The New York Fed is not responsible for publication of the SOFR data by QuantForge, does not sanction or endorse any particular republication, and has no liability for your use. QuantForge is not affiliated with the New York Fed. The New York Fed does not sanction, endorse, or recommend any products or services offered by QuantForge. The Secured Overnight Financing Rate (SOFR) Data are calculated using data provided under a license granted to the New York Fed by DTCC Solutions LLC ("Solutions"), an affiliate of The Depository Trust & Clearing Corporation. Solutions, its affiliates, and third parties from which they obtained data have no liability for the content of this material.
- SONIA and/or SONIA Compounded Index data licensed under the Open Government Licence v3.0 and copyright the Governor and Company of the Bank of England. The trade marks "Bank of England" and "SONIA" are registered trade marks of the Bank of England.
- Yield curve data: Bank of England (sources: Bloomberg Finance L.P., Tradeweb and Bank calculations), https://www.bankofengland.co.uk/statistics/yield-curves. Used for internal checks; no values are reproduced.
