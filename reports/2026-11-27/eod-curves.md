# EOD curves: 2026-11-27

Result: **PASS** (39 checks, 0 failed, 0 warnings). Generated 2026-11-27T23:19Z by `tools/workflows/`. Batch command: rust `quantforge --batch`.


## USD

USD proxy curve: Treasury par yields bootstrapped with SOFR OIS conventions. Not a SOFR swap curve. As of 2026-11-27, 13 tenors. Implementation: rust.
| Pillar | t (y) | DF | Zero (cc, %) | Fwd to pillar (%) |
|---|---|---|---|---|
| 2027-01-06 | 0.110 | 0.99527629 | 4.3206 | 4.3206 |
| 2027-02-03 | 0.186 | 0.99194113 | 4.3432 | 4.3756 |
| 2027-03-03 | 0.263 | 0.98853048 | 4.3860 | 4.4899 |
| 2027-04-05 | 0.353 | 0.98454292 | 4.4077 | 4.4707 |
| 2027-06-03 | 0.515 | 0.97723980 | 4.4699 | 4.6061 |
| 2027-12-03 | 1.016 | 0.95465055 | 4.5659 | 4.6646 |
| 2028-12-05 | 2.025 | 0.91022474 | 4.6459 | 4.7265 |
| 2029-12-05 | 3.025 | 0.86812003 | 4.6757 | 4.7362 |
| 2031-12-03 | 5.019 | 0.79001190 | 4.6961 | 4.7270 |
| 2033-12-05 | 7.027 | 0.71452447 | 4.7833 | 5.0010 |
| 2036-12-03 | 10.025 | 0.61074315 | 4.9187 | 5.2361 |
| 2046-12-05 | 20.036 | 0.33523025 | 5.4550 | 5.9920 |
| 2056-12-05 | 30.044 | 0.20072778 | 5.3449 | 5.1245 |


### USD key-rate risk, sample book

50 synthetic SOFR swaps from `tools/workflows/sample_book.py` (seed 20261107, book sha256 `49456317fff9f842`), fixed rates at par ± up to 100 bp. Figures in USD per 1 bp, sign per `risk.ois.dv01`.
| Key rate | DV01 (USD/bp) |
|---|---|
| 1M | -18.90 |
| 2M | -0.00 |
| 3M | 0.00 |
| 4M | -0.03 |
| 6M | 1.11 |
| 1Y | -985.16 |
| 2Y | -28,591.09 |
| 3Y | 6,358.57 |
| 5Y | -11,171.97 |
| 7Y | 45,758.95 |
| 10Y | 62,748.17 |
| 20Y | 62,702.29 |
| 30Y | -57,179.35 |
| Parallel | 79,622.59 |


## GBP

Reference: Bank of England fitted OIS spot curve (50 maturities) and nominal government spot curve (80 maturities) for 2026-11-26, from the latest yield curve data zip, with SONIA fixings to 2026-11-25. Only pass or fail is published: the curves are Bank copyright, licensed here for internal non-commercial use only, and raw SONIA may not be redistributed until the Bank answers (`tools/recorder/sources.json`); the zip is fetched per run and no raw copy is kept. The library does not build its own GBP curve: free data has no SONIA swap quotes to bootstrap from.

## Checks

| Check | Level | Result | Detail |
|---|---|---|---|
| USD par quotes quote levels | fail | ok | outside band: none |
| USD par quotes adjacent tenor gaps | warn | ok | none |
| USD par quotes day change | fail | ok | largest 10Y 0.0009 |
| USD par quotes day change (warn) | warn | ok | largest 10Y 0.0009 |
| SOFR level | fail | ok | 2026-11-25: 0.0395 |
| SOFR day change | fail | ok | 0.0001 vs 0.01 |
| SOFR day change (warn) | warn | ok | 0.0001 vs 0.0025 |
| USD bootstrap | fail | ok | ok |
| USD curve discount factors in band | fail | ok | min 0.200728, max 0.995276 |
| USD curve discount factors non-increasing | warn | ok | rises after none |
| USD curve zero rates in band | fail | ok | min 0.043206, max 0.0545497 |
| USD curve forwards in band | fail | ok | min 0.043206, max 0.0599202 |
| USD fixing vs shortest quote | warn | ok | -0.0032 vs ±0.0075 |
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
| USD sum of key rates vs parallel DV01 | warn | ok | sum 79,622.60 vs DV01 79,622.59 |
| SONIA level | fail | ok | 2026-11-25: value withheld |
| SONIA day change | fail | ok | value withheld vs 0.01 |
| SONIA day change (warn) | warn | ok | value withheld vs 0.0025 |
| GBP BoE curves read | fail | ok | OIS 19 days, nominal 19 days |
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
| GBP BoE curve date vs SONIA | warn | ok | BoE 2026-11-26, SONIA 2026-11-25 |

## Data notices

- Source: US Department of the Treasury.
- The SOFR data is subject to the Terms of Use posted at newyorkfed.org. The New York Fed is not responsible for publication of the SOFR data by QuantForge, does not sanction or endorse any particular republication, and has no liability for your use. QuantForge is not affiliated with the New York Fed. The New York Fed does not sanction, endorse, or recommend any products or services offered by QuantForge. The Secured Overnight Financing Rate (SOFR) Data are calculated using data provided under a license granted to the New York Fed by DTCC Solutions LLC ("Solutions"), an affiliate of The Depository Trust & Clearing Corporation. Solutions, its affiliates, and third parties from which they obtained data have no liability for the content of this material.
- SONIA and/or SONIA Compounded Index data licensed under the Open Government Licence v3.0 and copyright the Governor and Company of the Bank of England. The trade marks "Bank of England" and "SONIA" are registered trade marks of the Bank of England.
- Yield curve data: Bank of England (sources: Bloomberg Finance L.P., Tradeweb and Bank calculations), https://www.bankofengland.co.uk/statistics/yield-curves. Used for internal checks; no values are reproduced.
