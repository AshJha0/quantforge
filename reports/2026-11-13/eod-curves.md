# EOD curves: 2026-11-13

Result: **PASS** (39 checks, 0 failed, 0 warnings). Generated 2026-11-13T21:20Z by `tools/workflows/`. Batch command: rust `quantforge --batch`.


## USD

USD proxy curve: Treasury par yields bootstrapped with SOFR OIS conventions. Not a SOFR swap curve. As of 2026-11-13, 13 tenors. Implementation: rust.
| Pillar | t (y) | DF | Zero (cc, %) | Fwd to pillar (%) |
|---|---|---|---|---|
| 2026-12-21 | 0.104 | 0.99568892 | 4.1499 | 4.1499 |
| 2027-01-21 | 0.189 | 0.99190518 | 4.2995 | 4.4829 |
| 2027-02-19 | 0.268 | 0.98838873 | 4.3499 | 4.4699 |
| 2027-03-19 | 0.345 | 0.98505359 | 4.3624 | 4.4061 |
| 2027-05-19 | 0.512 | 0.97757112 | 4.4277 | 4.5625 |
| 2027-11-19 | 1.016 | 0.95429259 | 4.6028 | 4.7809 |
| 2028-11-21 | 2.025 | 0.90679844 | 4.8322 | 5.0634 |
| 2029-11-21 | 3.025 | 0.86301406 | 4.8708 | 4.9489 |
| 2031-11-19 | 5.019 | 0.78070625 | 4.9322 | 5.0254 |
| 2033-11-21 | 7.027 | 0.70335524 | 5.0074 | 5.1955 |
| 2036-11-19 | 10.025 | 0.59855494 | 5.1197 | 5.3830 |
| 2046-11-21 | 20.036 | 0.32598664 | 5.5945 | 6.0700 |
| 2056-11-21 | 30.044 | 0.19442422 | 5.4511 | 5.1639 |


### USD key-rate risk, sample book

50 synthetic SOFR swaps from `tools/workflows/sample_book.py` (seed 20261107, book sha256 `49456317fff9f842`), fixed rates at par ± up to 100 bp. Figures in USD per 1 bp, sign per `risk.ois.dv01`.
| Key rate | DV01 (USD/bp) |
|---|---|
| 1M | -18.64 |
| 2M | -0.00 |
| 3M | 0.00 |
| 4M | -0.03 |
| 6M | 1.08 |
| 1Y | -982.93 |
| 2Y | -28,529.60 |
| 3Y | 6,344.97 |
| 5Y | -11,093.61 |
| 7Y | 45,410.04 |
| 10Y | 62,122.00 |
| 20Y | 61,797.11 |
| 30Y | -56,133.07 |
| Parallel | 78,917.32 |


## GBP

Reference: Bank of England fitted OIS spot curve (50 maturities) and nominal government spot curve (80 maturities) for 2026-11-12, from the latest yield curve data zip, with SONIA fixings to 2026-11-11. Only pass or fail is published: the curves are Bank copyright, licensed here for internal non-commercial use only, and raw SONIA may not be redistributed until the Bank answers (`tools/recorder/sources.json`); the zip is fetched per run and no raw copy is kept. The library does not build its own GBP curve: free data has no SONIA swap quotes to bootstrap from.

## Checks

| Check | Level | Result | Detail |
|---|---|---|---|
| USD par quotes quote levels | fail | ok | outside band: none |
| USD par quotes adjacent tenor gaps | warn | ok | none |
| USD par quotes day change | fail | ok | largest 10Y 0.0005 |
| USD par quotes day change (warn) | warn | ok | largest 10Y 0.0005 |
| SOFR level | fail | ok | 2026-11-12: 0.039 |
| SOFR day change | fail | ok | 0.0001 vs 0.01 |
| SOFR day change (warn) | warn | ok | 0.0001 vs 0.0025 |
| USD bootstrap | fail | ok | ok |
| USD curve discount factors in band | fail | ok | min 0.194424, max 0.995689 |
| USD curve discount factors non-increasing | warn | ok | rises after none |
| USD curve zero rates in band | fail | ok | min 0.0414986, max 0.0559453 |
| USD curve forwards in band | fail | ok | min 0.0414986, max 0.0606997 |
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
| USD sum of key rates vs parallel DV01 | warn | ok | sum 78,917.33 vs DV01 78,917.32 |
| SONIA level | fail | ok | 2026-11-11: value withheld |
| SONIA day change | fail | ok | value withheld vs 0.01 |
| SONIA day change (warn) | warn | ok | value withheld vs 0.0025 |
| GBP BoE curves read | fail | ok | OIS 9 days, nominal 9 days |
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
| GBP BoE curve date vs SONIA | warn | ok | BoE 2026-11-12, SONIA 2026-11-11 |

## Data notices

- Source: US Department of the Treasury.
- The SOFR data is subject to the Terms of Use posted at newyorkfed.org. The New York Fed is not responsible for publication of the SOFR data by QuantForge, does not sanction or endorse any particular republication, and has no liability for your use. QuantForge is not affiliated with the New York Fed. The New York Fed does not sanction, endorse, or recommend any products or services offered by QuantForge. The Secured Overnight Financing Rate (SOFR) Data are calculated using data provided under a license granted to the New York Fed by DTCC Solutions LLC ("Solutions"), an affiliate of The Depository Trust & Clearing Corporation. Solutions, its affiliates, and third parties from which they obtained data have no liability for the content of this material.
- SONIA and/or SONIA Compounded Index data licensed under the Open Government Licence v3.0 and copyright the Governor and Company of the Bank of England. The trade marks "Bank of England" and "SONIA" are registered trade marks of the Bank of England.
- Yield curve data: Bank of England (sources: Bloomberg Finance L.P., Tradeweb and Bank calculations), https://www.bankofengland.co.uk/statistics/yield-curves. Used for internal checks; no values are reproduced.
