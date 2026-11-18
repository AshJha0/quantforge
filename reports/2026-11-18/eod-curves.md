# EOD curves: 2026-11-18

Result: **PASS** (39 checks, 0 failed, 0 warnings). Generated 2026-11-18T22:31Z by `tools/workflows/`. Batch command: rust `quantforge --batch`.


## USD

USD proxy curve: Treasury par yields bootstrapped with SOFR OIS conventions. Not a SOFR swap curve. As of 2026-11-18, 13 tenors. Implementation: rust.
| Pillar | t (y) | DF | Zero (cc, %) | Fwd to pillar (%) |
|---|---|---|---|---|
| 2026-12-23 | 0.096 | 0.99602882 | 4.1496 | 4.1496 |
| 2027-01-22 | 0.178 | 0.99234587 | 4.3146 | 4.5071 |
| 2027-02-24 | 0.268 | 0.98832684 | 4.3732 | 4.4887 |
| 2027-03-24 | 0.345 | 0.98501204 | 4.3746 | 4.3795 |
| 2027-05-24 | 0.512 | 0.97749892 | 4.4421 | 4.5815 |
| 2027-11-24 | 1.016 | 0.95455656 | 4.5756 | 4.7113 |
| 2028-11-22 | 2.014 | 0.90869130 | 4.7549 | 4.9377 |
| 2029-11-23 | 3.016 | 0.86535167 | 4.7944 | 4.8736 |
| 2031-11-24 | 5.019 | 0.78413284 | 4.8450 | 4.9211 |
| 2033-11-23 | 7.019 | 0.70797851 | 4.9200 | 5.1082 |
| 2036-11-24 | 10.025 | 0.60310360 | 5.0442 | 5.3344 |
| 2046-11-23 | 20.027 | 0.33127675 | 5.5164 | 5.9897 |
| 2056-11-22 | 30.033 | 0.19688936 | 5.4111 | 5.2003 |


### USD key-rate risk, sample book

50 synthetic SOFR swaps from `tools/workflows/sample_book.py` (seed 20261107, book sha256 `49456317fff9f842`), fixed rates at par ± up to 100 bp. Figures in USD per 1 bp, sign per `risk.ois.dv01`.
| Key rate | DV01 (USD/bp) |
|---|---|
| 1M | -9.38 |
| 2M | -0.00 |
| 3M | 0.00 |
| 4M | -0.05 |
| 6M | 1.14 |
| 1Y | -991.48 |
| 2Y | -28,562.52 |
| 3Y | 6,343.01 |
| 5Y | -11,131.97 |
| 7Y | 45,591.33 |
| 10Y | 62,311.64 |
| 20Y | 62,263.31 |
| 30Y | -56,618.02 |
| Parallel | 79,197.01 |


## GBP

Reference: Bank of England fitted OIS spot curve (50 maturities) and nominal government spot curve (80 maturities) for 2026-11-17, from the latest yield curve data zip, with SONIA fixings to 2026-11-16. Only pass or fail is published: the curves are Bank copyright, licensed here for internal non-commercial use only, and raw SONIA may not be redistributed until the Bank answers (`tools/recorder/sources.json`); the zip is fetched per run and no raw copy is kept. The library does not build its own GBP curve: free data has no SONIA swap quotes to bootstrap from.

## Checks

| Check | Level | Result | Detail |
|---|---|---|---|
| USD par quotes quote levels | fail | ok | outside band: none |
| USD par quotes adjacent tenor gaps | warn | ok | none |
| USD par quotes day change | fail | ok | largest 20Y 0.0006 |
| USD par quotes day change (warn) | warn | ok | largest 20Y 0.0006 |
| SOFR level | fail | ok | 2026-11-17: 0.0392 |
| SOFR day change | fail | ok | 0.0001 vs 0.01 |
| SOFR day change (warn) | warn | ok | 0.0001 vs 0.0025 |
| USD bootstrap | fail | ok | ok |
| USD curve discount factors in band | fail | ok | min 0.196889, max 0.996029 |
| USD curve discount factors non-increasing | warn | ok | rises after none |
| USD curve zero rates in band | fail | ok | min 0.0414962, max 0.0551645 |
| USD curve forwards in band | fail | ok | min 0.0414962, max 0.0598971 |
| USD fixing vs shortest quote | warn | ok | -0.0018 vs ±0.0075 |
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
| USD sum of key rates vs parallel DV01 | warn | ok | sum 79,197.01 vs DV01 79,197.01 |
| SONIA level | fail | ok | 2026-11-16: value withheld |
| SONIA day change | fail | ok | value withheld vs 0.01 |
| SONIA day change (warn) | warn | ok | value withheld vs 0.0025 |
| GBP BoE curves read | fail | ok | OIS 12 days, nominal 12 days |
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
| GBP BoE curve date vs SONIA | warn | ok | BoE 2026-11-17, SONIA 2026-11-16 |

## Data notices

- Source: US Department of the Treasury.
- The SOFR data is subject to the Terms of Use posted at newyorkfed.org. The New York Fed is not responsible for publication of the SOFR data by QuantForge, does not sanction or endorse any particular republication, and has no liability for your use. QuantForge is not affiliated with the New York Fed. The New York Fed does not sanction, endorse, or recommend any products or services offered by QuantForge. The Secured Overnight Financing Rate (SOFR) Data are calculated using data provided under a license granted to the New York Fed by DTCC Solutions LLC ("Solutions"), an affiliate of The Depository Trust & Clearing Corporation. Solutions, its affiliates, and third parties from which they obtained data have no liability for the content of this material.
- SONIA and/or SONIA Compounded Index data licensed under the Open Government Licence v3.0 and copyright the Governor and Company of the Bank of England. The trade marks "Bank of England" and "SONIA" are registered trade marks of the Bank of England.
- Yield curve data: Bank of England (sources: Bloomberg Finance L.P., Tradeweb and Bank calculations), https://www.bankofengland.co.uk/statistics/yield-curves. Used for internal checks; no values are reproduced.
