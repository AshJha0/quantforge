# EOD curves: 2026-11-17

Result: **PASS** (39 checks, 0 failed, 0 warnings). Generated 2026-11-17T22:49Z by `tools/workflows/`. Batch command: rust `quantforge --batch`.


## USD

USD proxy curve: Treasury par yields bootstrapped with SOFR OIS conventions. Not a SOFR swap curve. As of 2026-11-17, 13 tenors. Implementation: rust.
| Pillar | t (y) | DF | Zero (cc, %) | Fwd to pillar (%) |
|---|---|---|---|---|
| 2026-12-23 | 0.099 | 0.99592574 | 4.1393 | 4.1393 |
| 2027-01-21 | 0.178 | 0.99236294 | 4.3050 | 4.5106 |
| 2027-02-23 | 0.268 | 0.98834511 | 4.3663 | 4.4873 |
| 2027-03-23 | 0.345 | 0.98512089 | 4.3426 | 4.2595 |
| 2027-05-21 | 0.507 | 0.97784069 | 4.4211 | 4.5889 |
| 2027-11-23 | 1.016 | 0.95473151 | 4.5576 | 4.6933 |
| 2028-11-22 | 2.016 | 0.90856807 | 4.7552 | 4.9560 |
| 2029-11-21 | 3.014 | 0.86546074 | 4.7945 | 4.8741 |
| 2031-11-21 | 5.014 | 0.78392849 | 4.8554 | 4.9472 |
| 2033-11-23 | 7.022 | 0.70627778 | 4.9523 | 5.1941 |
| 2036-11-21 | 10.019 | 0.60137848 | 5.0756 | 5.3644 |
| 2046-11-21 | 20.025 | 0.32659104 | 5.5883 | 6.1018 |
| 2056-11-22 | 30.036 | 0.19404770 | 5.4590 | 5.2003 |


### USD key-rate risk, sample book

50 synthetic SOFR swaps from `tools/workflows/sample_book.py` (seed 20261107, book sha256 `49456317fff9f842`), fixed rates at par ± up to 100 bp. Figures in USD per 1 bp, sign per `risk.ois.dv01`.
| Key rate | DV01 (USD/bp) |
|---|---|
| 1M | -9.34 |
| 2M | -0.00 |
| 3M | 0.01 |
| 4M | -0.06 |
| 6M | 2.18 |
| 1Y | -987.87 |
| 2Y | -28,600.52 |
| 3Y | 6,344.91 |
| 5Y | -11,125.28 |
| 7Y | 45,561.82 |
| 10Y | 62,355.39 |
| 20Y | 61,946.77 |
| 30Y | -56,291.08 |
| Parallel | 79,196.92 |


## GBP

Reference: Bank of England fitted OIS spot curve (50 maturities) and nominal government spot curve (80 maturities) for 2026-11-16, from the latest yield curve data zip, with SONIA fixings to 2026-11-13. Only pass or fail is published: the curves are Bank copyright, licensed here for internal non-commercial use only, and raw SONIA may not be redistributed until the Bank answers (`tools/recorder/sources.json`); the zip is fetched per run and no raw copy is kept. The library does not build its own GBP curve: free data has no SONIA swap quotes to bootstrap from.

## Checks

| Check | Level | Result | Detail |
|---|---|---|---|
| USD par quotes quote levels | fail | ok | outside band: none |
| USD par quotes adjacent tenor gaps | warn | ok | none |
| USD par quotes day change | fail | ok | largest 2Y 0.0003 |
| USD par quotes day change (warn) | warn | ok | largest 2Y 0.0003 |
| SOFR level | fail | ok | 2026-11-16: 0.0393 |
| SOFR day change | fail | ok | 0.0003 vs 0.01 |
| SOFR day change (warn) | warn | ok | 0.0003 vs 0.0025 |
| USD bootstrap | fail | ok | ok |
| USD curve discount factors in band | fail | ok | min 0.194048, max 0.995926 |
| USD curve discount factors non-increasing | warn | ok | rises after none |
| USD curve zero rates in band | fail | ok | min 0.0413929, max 0.0558834 |
| USD curve forwards in band | fail | ok | min 0.0413929, max 0.0610181 |
| USD fixing vs shortest quote | warn | ok | -0.0016 vs ±0.0075 |
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
| USD sum of key rates vs parallel DV01 | warn | ok | sum 79,196.93 vs DV01 79,196.92 |
| SONIA level | fail | ok | 2026-11-13: value withheld |
| SONIA day change | fail | ok | value withheld vs 0.01 |
| SONIA day change (warn) | warn | ok | value withheld vs 0.0025 |
| GBP BoE curves read | fail | ok | OIS 11 days, nominal 11 days |
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
| GBP BoE curve date vs SONIA | warn | ok | BoE 2026-11-16, SONIA 2026-11-13 |

## Data notices

- Source: US Department of the Treasury.
- The SOFR data is subject to the Terms of Use posted at newyorkfed.org. The New York Fed is not responsible for publication of the SOFR data by QuantForge, does not sanction or endorse any particular republication, and has no liability for your use. QuantForge is not affiliated with the New York Fed. The New York Fed does not sanction, endorse, or recommend any products or services offered by QuantForge. The Secured Overnight Financing Rate (SOFR) Data are calculated using data provided under a license granted to the New York Fed by DTCC Solutions LLC ("Solutions"), an affiliate of The Depository Trust & Clearing Corporation. Solutions, its affiliates, and third parties from which they obtained data have no liability for the content of this material.
- SONIA and/or SONIA Compounded Index data licensed under the Open Government Licence v3.0 and copyright the Governor and Company of the Bank of England. The trade marks "Bank of England" and "SONIA" are registered trade marks of the Bank of England.
- Yield curve data: Bank of England (sources: Bloomberg Finance L.P., Tradeweb and Bank calculations), https://www.bankofengland.co.uk/statistics/yield-curves. Used for internal checks; no values are reproduced.
