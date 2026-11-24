# EOD curves: 2026-11-23

Result: **PASS** (39 checks, 0 failed, 0 warnings). Generated 2026-11-24T02:05Z by `tools/workflows/`. Batch command: rust `quantforge --batch`.


## USD

USD proxy curve: Treasury par yields bootstrapped with SOFR OIS conventions. Not a SOFR swap curve. As of 2026-11-23, 13 tenors. Implementation: rust.
| Pillar | t (y) | DF | Zero (cc, %) | Fwd to pillar (%) |
|---|---|---|---|---|
| 2026-12-30 | 0.101 | 0.99570089 | 4.2502 | 4.2502 |
| 2027-01-27 | 0.178 | 0.99229234 | 4.3449 | 4.4701 |
| 2027-03-01 | 0.268 | 0.98823428 | 4.4081 | 4.5326 |
| 2027-03-30 | 0.348 | 0.98486530 | 4.3830 | 4.2981 |
| 2027-05-27 | 0.507 | 0.97763999 | 4.4616 | 4.6339 |
| 2027-11-30 | 1.019 | 0.95489777 | 4.5283 | 4.5942 |
| 2028-11-29 | 2.019 | 0.91152848 | 4.5876 | 4.6481 |
| 2029-11-28 | 3.016 | 0.86916546 | 4.6486 | 4.7720 |
| 2031-11-28 | 5.016 | 0.78998346 | 4.6994 | 4.7761 |
| 2033-11-29 | 7.022 | 0.71514433 | 4.7746 | 4.9628 |
| 2036-11-28 | 10.022 | 0.61207772 | 4.8982 | 5.1875 |
| 2046-11-28 | 20.027 | 0.33766614 | 5.4211 | 5.9448 |
| 2056-11-29 | 30.038 | 0.20384325 | 5.2946 | 5.0415 |


### USD key-rate risk, sample book

50 synthetic SOFR swaps from `tools/workflows/sample_book.py` (seed 20261107, book sha256 `49456317fff9f842`), fixed rates at par ± up to 100 bp. Figures in USD per 1 bp, sign per `risk.ois.dv01`.
| Key rate | DV01 (USD/bp) |
|---|---|
| 1M | -9.48 |
| 2M | -0.00 |
| 3M | 0.01 |
| 4M | -0.06 |
| 6M | 2.20 |
| 1Y | -992.60 |
| 2Y | -28,691.56 |
| 3Y | 6,361.98 |
| 5Y | -11,181.85 |
| 7Y | 45,793.80 |
| 10Y | 62,761.24 |
| 20Y | 62,869.66 |
| 30Y | -57,408.44 |
| Parallel | 79,504.89 |


## GBP

Reference: Bank of England fitted OIS spot curve (50 maturities) and nominal government spot curve (80 maturities) for 2026-11-20, from the latest yield curve data zip, with SONIA fixings to 2026-11-19. Only pass or fail is published: the curves are Bank copyright, licensed here for internal non-commercial use only, and raw SONIA may not be redistributed until the Bank answers (`tools/recorder/sources.json`); the zip is fetched per run and no raw copy is kept. The library does not build its own GBP curve: free data has no SONIA swap quotes to bootstrap from.

## Checks

| Check | Level | Result | Detail |
|---|---|---|---|
| USD par quotes quote levels | fail | ok | outside band: none |
| USD par quotes adjacent tenor gaps | warn | ok | none |
| USD par quotes day change | fail | ok | largest 6M 0.0007 |
| USD par quotes day change (warn) | warn | ok | largest 6M 0.0007 |
| SOFR level | fail | ok | 2026-11-20: 0.0392 |
| SOFR day change | fail | ok | 0.0001 vs 0.01 |
| SOFR day change (warn) | warn | ok | 0.0001 vs 0.0025 |
| USD bootstrap | fail | ok | ok |
| USD curve discount factors in band | fail | ok | min 0.203843, max 0.995701 |
| USD curve discount factors non-increasing | warn | ok | rises after none |
| USD curve zero rates in band | fail | ok | min 0.0425016, max 0.0542106 |
| USD curve forwards in band | fail | ok | min 0.0425016, max 0.0594476 |
| USD fixing vs shortest quote | warn | ok | -0.0028 vs ±0.0075 |
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
| USD sum of key rates vs parallel DV01 | warn | ok | sum 79,504.90 vs DV01 79,504.89 |
| SONIA level | fail | ok | 2026-11-19: value withheld |
| SONIA day change | fail | ok | value withheld vs 0.01 |
| SONIA day change (warn) | warn | ok | value withheld vs 0.0025 |
| GBP BoE curves read | fail | ok | OIS 15 days, nominal 15 days |
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
| GBP BoE curve date vs SONIA | warn | ok | BoE 2026-11-20, SONIA 2026-11-19 |

## Data notices

- Source: US Department of the Treasury.
- The SOFR data is subject to the Terms of Use posted at newyorkfed.org. The New York Fed is not responsible for publication of the SOFR data by QuantForge, does not sanction or endorse any particular republication, and has no liability for your use. QuantForge is not affiliated with the New York Fed. The New York Fed does not sanction, endorse, or recommend any products or services offered by QuantForge. The Secured Overnight Financing Rate (SOFR) Data are calculated using data provided under a license granted to the New York Fed by DTCC Solutions LLC ("Solutions"), an affiliate of The Depository Trust & Clearing Corporation. Solutions, its affiliates, and third parties from which they obtained data have no liability for the content of this material.
- SONIA and/or SONIA Compounded Index data licensed under the Open Government Licence v3.0 and copyright the Governor and Company of the Bank of England. The trade marks "Bank of England" and "SONIA" are registered trade marks of the Bank of England.
- Yield curve data: Bank of England (sources: Bloomberg Finance L.P., Tradeweb and Bank calculations), https://www.bankofengland.co.uk/statistics/yield-curves. Used for internal checks; no values are reproduced.
