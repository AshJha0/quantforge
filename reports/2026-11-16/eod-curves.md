# EOD curves: 2026-11-16

Result: **PASS** (39 checks, 0 failed, 0 warnings). Generated 2026-11-16T23:42Z by `tools/workflows/`. Batch command: rust `quantforge --batch`.


## USD

USD proxy curve: Treasury par yields bootstrapped with SOFR OIS conventions. Not a SOFR swap curve. As of 2026-11-16, 13 tenors. Implementation: rust.
| Pillar | t (y) | DF | Zero (cc, %) | Fwd to pillar (%) |
|---|---|---|---|---|
| 2026-12-22 | 0.099 | 0.99591535 | 4.1499 | 4.1499 |
| 2027-01-21 | 0.181 | 0.99222874 | 4.3145 | 4.5121 |
| 2027-02-22 | 0.268 | 0.98831764 | 4.3767 | 4.5049 |
| 2027-03-22 | 0.345 | 0.98508703 | 4.3526 | 4.2681 |
| 2027-05-20 | 0.507 | 0.97779150 | 4.4311 | 4.5987 |
| 2027-11-22 | 1.016 | 0.95454300 | 4.5770 | 4.7222 |
| 2028-11-22 | 2.019 | 0.90791654 | 4.7843 | 4.9943 |
| 2029-11-21 | 3.016 | 0.86458937 | 4.8236 | 4.9032 |
| 2031-11-20 | 5.014 | 0.78278540 | 4.8846 | 4.9766 |
| 2033-11-22 | 7.022 | 0.70536766 | 4.9707 | 5.1857 |
| 2036-11-20 | 10.019 | 0.60026602 | 5.0941 | 5.3831 |
| 2046-11-21 | 20.027 | 0.32616860 | 5.5940 | 6.0946 |
| 2056-11-22 | 30.038 | 0.19469621 | 5.4474 | 5.1541 |


### USD key-rate risk, sample book

50 synthetic SOFR swaps from `tools/workflows/sample_book.py` (seed 20261107, book sha256 `49456317fff9f842`), fixed rates at par ± up to 100 bp. Figures in USD per 1 bp, sign per `risk.ois.dv01`.
| Key rate | DV01 (USD/bp) |
|---|---|
| 1M | -9.33 |
| 2M | -0.00 |
| 3M | 0.01 |
| 4M | -0.06 |
| 6M | 2.18 |
| 1Y | -987.46 |
| 2Y | -28,625.94 |
| 3Y | 6,347.51 |
| 5Y | -11,112.17 |
| 7Y | 45,487.85 |
| 10Y | 62,272.78 |
| 20Y | 61,886.62 |
| 30Y | -56,240.32 |
| Parallel | 79,021.67 |


## GBP

Reference: Bank of England fitted OIS spot curve (50 maturities) and nominal government spot curve (80 maturities) for 2026-11-13, from the latest yield curve data zip, with SONIA fixings to 2026-11-12. Only pass or fail is published: the curves are Bank copyright, licensed here for internal non-commercial use only, and raw SONIA may not be redistributed until the Bank answers (`tools/recorder/sources.json`); the zip is fetched per run and no raw copy is kept. The library does not build its own GBP curve: free data has no SONIA swap quotes to bootstrap from.

## Checks

| Check | Level | Result | Detail |
|---|---|---|---|
| USD par quotes quote levels | fail | ok | outside band: none |
| USD par quotes adjacent tenor gaps | warn | ok | none |
| USD par quotes day change | fail | ok | largest 5Y 0.0005 |
| USD par quotes day change (warn) | warn | ok | largest 5Y 0.0005 |
| SOFR level | fail | ok | 2026-11-13: 0.039 |
| SOFR day change | fail | ok | 0 vs 0.01 |
| SOFR day change (warn) | warn | ok | 0 vs 0.0025 |
| USD bootstrap | fail | ok | ok |
| USD curve discount factors in band | fail | ok | min 0.194696, max 0.995915 |
| USD curve discount factors non-increasing | warn | ok | rises after none |
| USD curve zero rates in band | fail | ok | min 0.0414986, max 0.0559404 |
| USD curve forwards in band | fail | ok | min 0.0414986, max 0.0609458 |
| USD fixing vs shortest quote | warn | ok | -0.002 vs ±0.0075 |
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
| USD sum of key rates vs parallel DV01 | warn | ok | sum 79,021.68 vs DV01 79,021.67 |
| SONIA level | fail | ok | 2026-11-12: value withheld |
| SONIA day change | fail | ok | value withheld vs 0.01 |
| SONIA day change (warn) | warn | ok | value withheld vs 0.0025 |
| GBP BoE curves read | fail | ok | OIS 10 days, nominal 10 days |
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
| GBP BoE curve date vs SONIA | warn | ok | BoE 2026-11-13, SONIA 2026-11-12 |

## Data notices

- Source: US Department of the Treasury.
- The SOFR data is subject to the Terms of Use posted at newyorkfed.org. The New York Fed is not responsible for publication of the SOFR data by QuantForge, does not sanction or endorse any particular republication, and has no liability for your use. QuantForge is not affiliated with the New York Fed. The New York Fed does not sanction, endorse, or recommend any products or services offered by QuantForge. The Secured Overnight Financing Rate (SOFR) Data are calculated using data provided under a license granted to the New York Fed by DTCC Solutions LLC ("Solutions"), an affiliate of The Depository Trust & Clearing Corporation. Solutions, its affiliates, and third parties from which they obtained data have no liability for the content of this material.
- SONIA and/or SONIA Compounded Index data licensed under the Open Government Licence v3.0 and copyright the Governor and Company of the Bank of England. The trade marks "Bank of England" and "SONIA" are registered trade marks of the Bank of England.
- Yield curve data: Bank of England (sources: Bloomberg Finance L.P., Tradeweb and Bank calculations), https://www.bankofengland.co.uk/statistics/yield-curves. Used for internal checks; no values are reproduced.
