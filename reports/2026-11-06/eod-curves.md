# EOD curves: 2026-11-06

Result: **PASS** (39 checks, 0 failed, 0 warnings). Generated 2026-11-07T18:24Z by `tools/workflows/`. Batch command: rust `quantforge --batch`.


## USD

USD proxy curve: Treasury par yields bootstrapped with SOFR OIS conventions. Not a SOFR swap curve. As of 2026-11-06, 13 tenors. Implementation: rust.
| Pillar | t (y) | DF | Zero (cc, %) | Fwd to pillar (%) |
|---|---|---|---|---|
| 2026-12-14 | 0.104 | 0.99577272 | 4.0690 | 4.0690 |
| 2027-01-13 | 0.186 | 0.99222470 | 4.1898 | 4.3428 |
| 2027-02-12 | 0.268 | 0.98873211 | 4.2205 | 4.2902 |
| 2027-03-12 | 0.345 | 0.98555978 | 4.2136 | 4.1892 |
| 2027-05-12 | 0.512 | 0.97850846 | 4.2406 | 4.2964 |
| 2027-11-15 | 1.025 | 0.95694755 | 4.2948 | 4.3489 |
| 2028-11-14 | 2.025 | 0.91340181 | 4.4738 | 4.6573 |
| 2029-11-15 | 3.027 | 0.87123470 | 4.5532 | 4.7135 |
| 2031-11-13 | 5.022 | 0.79359463 | 4.6035 | 4.6798 |
| 2033-11-15 | 7.030 | 0.71804960 | 4.7114 | 4.9812 |
| 2036-11-13 | 10.027 | 0.61519263 | 4.8449 | 5.1582 |
| 2046-11-15 | 20.038 | 0.33950352 | 5.3910 | 5.9380 |
| 2056-11-14 | 30.044 | 0.20466555 | 5.2802 | 5.0583 |


### USD key-rate risk, sample book

50 synthetic SOFR swaps from `tools/workflows/sample_book.py` (seed 20261107, book sha256 `49456317fff9f842`), fixed rates at par ± up to 100 bp. Figures in USD per 1 bp, sign per `risk.ois.dv01`.
| Key rate | DV01 (USD/bp) |
|---|---|
| 1M | -19.04 |
| 2M | -0.00 |
| 3M | 0.00 |
| 4M | -0.06 |
| 6M | 2.71 |
| 1Y | -992.28 |
| 2Y | -28,676.83 |
| 3Y | 6,381.37 |
| 5Y | -11,214.51 |
| 7Y | 45,932.76 |
| 10Y | 62,989.31 |
| 20Y | 63,102.36 |
| 30Y | -57,657.90 |
| Parallel | 79,847.87 |


## GBP

Reference: Bank of England fitted OIS spot curve (50 maturities) and nominal government spot curve (80 maturities) for 2026-11-05, from the latest yield curve data zip, with SONIA fixings to 2026-11-04. Only pass or fail is published: the curves are Bank copyright, licensed here for internal non-commercial use only, and raw SONIA may not be redistributed until the Bank answers (`tools/recorder/sources.json`); the zip is fetched per run and no raw copy is kept. The library does not build its own GBP curve: free data has no SONIA swap quotes to bootstrap from.

## Checks

| Check | Level | Result | Detail |
|---|---|---|---|
| USD par quotes quote levels | fail | ok | outside band: none |
| USD par quotes adjacent tenor gaps | warn | ok | none |
| USD par quotes day change | fail | ok | largest 3Y 0.0006 |
| USD par quotes day change (warn) | warn | ok | largest 3Y 0.0006 |
| SOFR level | fail | ok | 2026-11-05: 0.0392 |
| SOFR day change | fail | ok | 0.0002 vs 0.01 |
| SOFR day change (warn) | warn | ok | 0.0002 vs 0.0025 |
| USD bootstrap | fail | ok | ok |
| USD curve discount factors in band | fail | ok | min 0.204666, max 0.995773 |
| USD curve discount factors non-increasing | warn | ok | rises after none |
| USD curve zero rates in band | fail | ok | min 0.0406902, max 0.0539102 |
| USD curve forwards in band | fail | ok | min 0.0406902, max 0.05938 |
| USD fixing vs shortest quote | warn | ok | -0.001 vs ±0.0075 |
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
| USD sum of key rates vs parallel DV01 | warn | ok | sum 79,847.88 vs DV01 79,847.87 |
| SONIA level | fail | ok | 2026-11-04: value withheld |
| SONIA day change | fail | ok | value withheld vs 0.01 |
| SONIA day change (warn) | warn | ok | value withheld vs 0.0025 |
| GBP BoE curves read | fail | ok | OIS 4 days, nominal 4 days |
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
| GBP BoE curve date vs SONIA | warn | ok | BoE 2026-11-05, SONIA 2026-11-04 |

## Data notices

- Source: US Department of the Treasury.
- The SOFR data is subject to the Terms of Use posted at newyorkfed.org. The New York Fed is not responsible for publication of the SOFR data by QuantForge, does not sanction or endorse any particular republication, and has no liability for your use. QuantForge is not affiliated with the New York Fed. The New York Fed does not sanction, endorse, or recommend any products or services offered by QuantForge. The Secured Overnight Financing Rate (SOFR) Data are calculated using data provided under a license granted to the New York Fed by DTCC Solutions LLC ("Solutions"), an affiliate of The Depository Trust & Clearing Corporation. Solutions, its affiliates, and third parties from which they obtained data have no liability for the content of this material.
- SONIA and/or SONIA Compounded Index data licensed under the Open Government Licence v3.0 and copyright the Governor and Company of the Bank of England. The trade marks "Bank of England" and "SONIA" are registered trade marks of the Bank of England.
- Yield curve data: Bank of England (sources: Bloomberg Finance L.P., Tradeweb and Bank calculations), https://www.bankofengland.co.uk/statistics/yield-curves. Used for internal checks; no values are reproduced.
