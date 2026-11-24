# EOD curves: 2026-11-24

Result: **PASS** (39 checks, 0 failed, 0 warnings). Generated 2026-11-24T23:49Z by `tools/workflows/`. Batch command: rust `quantforge --batch`.


## USD

USD proxy curve: Treasury par yields bootstrapped with SOFR OIS conventions. Not a SOFR swap curve. As of 2026-11-24, 13 tenors. Implementation: rust.
| Pillar | t (y) | DF | Zero (cc, %) | Fwd to pillar (%) |
|---|---|---|---|---|
| 2026-12-30 | 0.099 | 0.99580643 | 4.2608 | 4.2608 |
| 2027-01-29 | 0.181 | 0.99221323 | 4.3232 | 4.3981 |
| 2027-03-02 | 0.268 | 0.98825933 | 4.3987 | 4.5544 |
| 2027-03-31 | 0.348 | 0.98486052 | 4.3844 | 4.3361 |
| 2027-06-01 | 0.518 | 0.97710204 | 4.4735 | 4.6561 |
| 2027-12-01 | 1.019 | 0.95472289 | 4.5462 | 4.6213 |
| 2028-11-29 | 2.016 | 0.91165459 | 4.5870 | 4.6287 |
| 2029-11-29 | 3.016 | 0.86971281 | 4.6277 | 4.7098 |
| 2031-12-02 | 5.025 | 0.79172918 | 4.6478 | 4.6780 |
| 2033-11-30 | 7.022 | 0.71604950 | 4.7566 | 5.0304 |
| 2036-12-02 | 10.030 | 0.61223990 | 4.8916 | 5.2066 |
| 2046-11-29 | 20.027 | 0.33730530 | 5.4264 | 5.9630 |
| 2056-11-29 | 30.036 | 0.20254246 | 5.3164 | 5.0962 |


### USD key-rate risk, sample book

50 synthetic SOFR swaps from `tools/workflows/sample_book.py` (seed 20261107, book sha256 `49456317fff9f842`), fixed rates at par ± up to 100 bp. Figures in USD per 1 bp, sign per `risk.ois.dv01`.
| Key rate | DV01 (USD/bp) |
|---|---|
| 1M | -14.22 |
| 2M | -0.00 |
| 3M | 0.00 |
| 4M | -0.07 |
| 6M | 1.17 |
| 1Y | -993.15 |
| 2Y | -28,614.44 |
| 3Y | 6,358.94 |
| 5Y | -11,205.48 |
| 7Y | 45,865.02 |
| 10Y | 62,825.59 |
| 20Y | 62,896.71 |
| 30Y | -57,389.98 |
| Parallel | 79,730.08 |


## GBP

Reference: Bank of England fitted OIS spot curve (50 maturities) and nominal government spot curve (80 maturities) for 2026-11-23, from the latest yield curve data zip, with SONIA fixings to 2026-11-20. Only pass or fail is published: the curves are Bank copyright, licensed here for internal non-commercial use only, and raw SONIA may not be redistributed until the Bank answers (`tools/recorder/sources.json`); the zip is fetched per run and no raw copy is kept. The library does not build its own GBP curve: free data has no SONIA swap quotes to bootstrap from.

## Checks

| Check | Level | Result | Detail |
|---|---|---|---|
| USD par quotes quote levels | fail | ok | outside band: none |
| USD par quotes adjacent tenor gaps | warn | ok | none |
| USD par quotes day change | fail | ok | largest 5Y 0.0005 |
| USD par quotes day change (warn) | warn | ok | largest 5Y 0.0005 |
| SOFR level | fail | ok | 2026-11-23: 0.0392 |
| SOFR day change | fail | ok | 0 vs 0.01 |
| SOFR day change (warn) | warn | ok | 0 vs 0.0025 |
| USD bootstrap | fail | ok | ok |
| USD curve discount factors in band | fail | ok | min 0.202542, max 0.995806 |
| USD curve discount factors non-increasing | warn | ok | rises after none |
| USD curve zero rates in band | fail | ok | min 0.0426075, max 0.054264 |
| USD curve forwards in band | fail | ok | min 0.0426075, max 0.0596299 |
| USD fixing vs shortest quote | warn | ok | -0.0029 vs ±0.0075 |
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
| USD sum of key rates vs parallel DV01 | warn | ok | sum 79,730.09 vs DV01 79,730.08 |
| SONIA level | fail | ok | 2026-11-20: value withheld |
| SONIA day change | fail | ok | value withheld vs 0.01 |
| SONIA day change (warn) | warn | ok | value withheld vs 0.0025 |
| GBP BoE curves read | fail | ok | OIS 16 days, nominal 16 days |
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
| GBP BoE curve date vs SONIA | warn | ok | BoE 2026-11-23, SONIA 2026-11-20 |

## Data notices

- Source: US Department of the Treasury.
- The SOFR data is subject to the Terms of Use posted at newyorkfed.org. The New York Fed is not responsible for publication of the SOFR data by QuantForge, does not sanction or endorse any particular republication, and has no liability for your use. QuantForge is not affiliated with the New York Fed. The New York Fed does not sanction, endorse, or recommend any products or services offered by QuantForge. The Secured Overnight Financing Rate (SOFR) Data are calculated using data provided under a license granted to the New York Fed by DTCC Solutions LLC ("Solutions"), an affiliate of The Depository Trust & Clearing Corporation. Solutions, its affiliates, and third parties from which they obtained data have no liability for the content of this material.
- SONIA and/or SONIA Compounded Index data licensed under the Open Government Licence v3.0 and copyright the Governor and Company of the Bank of England. The trade marks "Bank of England" and "SONIA" are registered trade marks of the Bank of England.
- Yield curve data: Bank of England (sources: Bloomberg Finance L.P., Tradeweb and Bank calculations), https://www.bankofengland.co.uk/statistics/yield-curves. Used for internal checks; no values are reproduced.
