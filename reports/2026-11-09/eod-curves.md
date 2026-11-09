# EOD curves: 2026-11-09

Result: **PASS** (39 checks, 0 failed, 0 warnings). Generated 2026-11-09T23:44Z by `tools/workflows/`. Batch command: rust `quantforge --batch`.


## USD

USD proxy curve: Treasury par yields bootstrapped with SOFR OIS conventions. Not a SOFR swap curve. As of 2026-11-09, 13 tenors. Implementation: rust.
| Pillar | t (y) | DF | Zero (cc, %) | Fwd to pillar (%) |
|---|---|---|---|---|
| 2026-12-16 | 0.101 | 0.99586379 | 4.0888 | 4.0888 |
| 2027-01-14 | 0.181 | 0.99237659 | 4.2321 | 4.4150 |
| 2027-02-17 | 0.274 | 0.98835829 | 4.2742 | 4.3557 |
| 2027-03-16 | 0.348 | 0.98542842 | 4.2187 | 4.0133 |
| 2027-05-14 | 0.510 | 0.97846665 | 4.2718 | 4.3861 |
| 2027-11-16 | 1.019 | 0.95669512 | 4.3437 | 4.4157 |
| 2028-11-15 | 2.019 | 0.91273552 | 4.5221 | 4.7039 |
| 2029-11-15 | 3.019 | 0.87187513 | 4.5413 | 4.5800 |
| 2031-11-14 | 5.016 | 0.79257764 | 4.6341 | 4.7743 |
| 2033-11-16 | 7.025 | 0.71728546 | 4.7302 | 4.9704 |
| 2036-11-14 | 10.022 | 0.61416464 | 4.8643 | 5.1784 |
| 2046-11-15 | 20.030 | 0.34013074 | 5.3840 | 5.9045 |
| 2056-11-15 | 30.038 | 0.20500808 | 5.2756 | 5.0586 |


### USD key-rate risk, sample book

50 synthetic SOFR swaps from `tools/workflows/sample_book.py` (seed 20261107, book sha256 `49456317fff9f842`), fixed rates at par ± up to 100 bp. Figures in USD per 1 bp, sign per `risk.ois.dv01`.
| Key rate | DV01 (USD/bp) |
|---|---|
| 1M | -14.28 |
| 2M | -0.00 |
| 3M | 0.01 |
| 4M | -0.06 |
| 6M | 2.19 |
| 1Y | -992.05 |
| 2Y | -28,698.63 |
| 3Y | 6,371.69 |
| 5Y | -11,212.80 |
| 7Y | 45,932.92 |
| 10Y | 62,922.35 |
| 20Y | 63,107.99 |
| 30Y | -57,654.13 |
| Parallel | 79,765.19 |


## GBP

Reference: Bank of England fitted OIS spot curve (50 maturities) and nominal government spot curve (80 maturities) for 2026-11-06, from the latest yield curve data zip, with SONIA fixings to 2026-11-05. Only pass or fail is published: the curves are Bank copyright, licensed here for internal non-commercial use only, and raw SONIA may not be redistributed until the Bank answers (`tools/recorder/sources.json`); the zip is fetched per run and no raw copy is kept. The library does not build its own GBP curve: free data has no SONIA swap quotes to bootstrap from.

## Checks

| Check | Level | Result | Detail |
|---|---|---|---|
| USD par quotes quote levels | fail | ok | outside band: none |
| USD par quotes adjacent tenor gaps | warn | ok | none |
| USD par quotes day change | fail | ok | largest 1Y 0.0005 |
| USD par quotes day change (warn) | warn | ok | largest 1Y 0.0005 |
| SOFR level | fail | ok | 2026-11-06: 0.0389 |
| SOFR day change | fail | ok | 0.0003 vs 0.01 |
| SOFR day change (warn) | warn | ok | 0.0003 vs 0.0025 |
| USD bootstrap | fail | ok | ok |
| USD curve discount factors in band | fail | ok | min 0.205008, max 0.995864 |
| USD curve discount factors non-increasing | warn | ok | rises after none |
| USD curve zero rates in band | fail | ok | min 0.0408877, max 0.0538401 |
| USD curve forwards in band | fail | ok | min 0.0401335, max 0.0590448 |
| USD fixing vs shortest quote | warn | ok | -0.0015 vs ±0.0075 |
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
| USD sum of key rates vs parallel DV01 | warn | ok | sum 79,765.20 vs DV01 79,765.19 |
| SONIA level | fail | ok | 2026-11-05: value withheld |
| SONIA day change | fail | ok | value withheld vs 0.01 |
| SONIA day change (warn) | warn | ok | value withheld vs 0.0025 |
| GBP BoE curves read | fail | ok | OIS 5 days, nominal 5 days |
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
| GBP BoE curve date vs SONIA | warn | ok | BoE 2026-11-06, SONIA 2026-11-05 |

## Data notices

- Source: US Department of the Treasury.
- The SOFR data is subject to the Terms of Use posted at newyorkfed.org. The New York Fed is not responsible for publication of the SOFR data by QuantForge, does not sanction or endorse any particular republication, and has no liability for your use. QuantForge is not affiliated with the New York Fed. The New York Fed does not sanction, endorse, or recommend any products or services offered by QuantForge. The Secured Overnight Financing Rate (SOFR) Data are calculated using data provided under a license granted to the New York Fed by DTCC Solutions LLC ("Solutions"), an affiliate of The Depository Trust & Clearing Corporation. Solutions, its affiliates, and third parties from which they obtained data have no liability for the content of this material.
- SONIA and/or SONIA Compounded Index data licensed under the Open Government Licence v3.0 and copyright the Governor and Company of the Bank of England. The trade marks "Bank of England" and "SONIA" are registered trade marks of the Bank of England.
- Yield curve data: Bank of England (sources: Bloomberg Finance L.P., Tradeweb and Bank calculations), https://www.bankofengland.co.uk/statistics/yield-curves. Used for internal checks; no values are reproduced.
