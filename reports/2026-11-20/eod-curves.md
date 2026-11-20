# EOD curves: 2026-11-20

Result: **PASS** (39 checks, 0 failed, 0 warnings). Generated 2026-11-20T22:12Z by `tools/workflows/`. Batch command: rust `quantforge --batch`.


## USD

USD proxy curve: Treasury par yields bootstrapped with SOFR OIS conventions. Not a SOFR swap curve. As of 2026-11-20, 13 tenors. Implementation: rust.
| Pillar | t (y) | DF | Zero (cc, %) | Fwd to pillar (%) |
|---|---|---|---|---|
| 2026-12-29 | 0.107 | 0.99547899 | 4.2408 | 4.2408 |
| 2027-01-27 | 0.186 | 0.99198072 | 4.3218 | 4.4308 |
| 2027-02-26 | 0.268 | 0.98838144 | 4.3527 | 4.4226 |
| 2027-03-29 | 0.353 | 0.98476378 | 4.3442 | 4.3175 |
| 2027-05-26 | 0.512 | 0.97775745 | 4.3905 | 4.4934 |
| 2027-11-29 | 1.025 | 0.95523332 | 4.4698 | 4.5490 |
| 2028-11-28 | 2.025 | 0.91127788 | 4.5888 | 4.7108 |
| 2029-11-28 | 3.025 | 0.86990042 | 4.6080 | 4.6469 |
| 2031-11-26 | 5.019 | 0.79104807 | 4.6700 | 4.7641 |
| 2033-11-29 | 7.030 | 0.71523642 | 4.7672 | 5.0098 |
| 2036-11-26 | 10.025 | 0.61178497 | 4.9017 | 5.2173 |
| 2046-11-28 | 20.036 | 0.33647546 | 5.4365 | 5.9720 |
| 2056-11-28 | 30.044 | 0.20185455 | 5.3262 | 5.1056 |


### USD key-rate risk, sample book

50 synthetic SOFR swaps from `tools/workflows/sample_book.py` (seed 20261107, book sha256 `49456317fff9f842`), fixed rates at par ± up to 100 bp. Figures in USD per 1 bp, sign per `risk.ois.dv01`.
| Key rate | DV01 (USD/bp) |
|---|---|
| 1M | -18.95 |
| 2M | -0.00 |
| 3M | 0.01 |
| 4M | -0.08 |
| 6M | 2.74 |
| 1Y | -989.78 |
| 2Y | -28,616.81 |
| 3Y | 6,365.73 |
| 5Y | -11,185.76 |
| 7Y | 45,824.91 |
| 10Y | 62,819.06 |
| 20Y | 62,815.40 |
| 30Y | -57,312.99 |
| Parallel | 79,703.48 |


## GBP

Reference: Bank of England fitted OIS spot curve (50 maturities) and nominal government spot curve (80 maturities) for 2026-11-19, from the latest yield curve data zip, with SONIA fixings to 2026-11-18. Only pass or fail is published: the curves are Bank copyright, licensed here for internal non-commercial use only, and raw SONIA may not be redistributed until the Bank answers (`tools/recorder/sources.json`); the zip is fetched per run and no raw copy is kept. The library does not build its own GBP curve: free data has no SONIA swap quotes to bootstrap from.

## Checks

| Check | Level | Result | Detail |
|---|---|---|---|
| USD par quotes quote levels | fail | ok | outside band: none |
| USD par quotes adjacent tenor gaps | warn | ok | none |
| USD par quotes day change | fail | ok | largest 3Y 0.0016 |
| USD par quotes day change (warn) | warn | ok | largest 3Y 0.0016 |
| SOFR level | fail | ok | 2026-11-19: 0.0391 |
| SOFR day change | fail | ok | 0.0001 vs 0.01 |
| SOFR day change (warn) | warn | ok | 0.0001 vs 0.0025 |
| USD bootstrap | fail | ok | ok |
| USD curve discount factors in band | fail | ok | min 0.201855, max 0.995479 |
| USD curve discount factors non-increasing | warn | ok | rises after none |
| USD curve zero rates in band | fail | ok | min 0.042408, max 0.0543647 |
| USD curve forwards in band | fail | ok | min 0.042408, max 0.0597201 |
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
| USD sum of key rates vs parallel DV01 | warn | ok | sum 79,703.49 vs DV01 79,703.48 |
| SONIA level | fail | ok | 2026-11-18: value withheld |
| SONIA day change | fail | ok | value withheld vs 0.01 |
| SONIA day change (warn) | warn | ok | value withheld vs 0.0025 |
| GBP BoE curves read | fail | ok | OIS 14 days, nominal 14 days |
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
| GBP BoE curve date vs SONIA | warn | ok | BoE 2026-11-19, SONIA 2026-11-18 |

## Data notices

- Source: US Department of the Treasury.
- The SOFR data is subject to the Terms of Use posted at newyorkfed.org. The New York Fed is not responsible for publication of the SOFR data by QuantForge, does not sanction or endorse any particular republication, and has no liability for your use. QuantForge is not affiliated with the New York Fed. The New York Fed does not sanction, endorse, or recommend any products or services offered by QuantForge. The Secured Overnight Financing Rate (SOFR) Data are calculated using data provided under a license granted to the New York Fed by DTCC Solutions LLC ("Solutions"), an affiliate of The Depository Trust & Clearing Corporation. Solutions, its affiliates, and third parties from which they obtained data have no liability for the content of this material.
- SONIA and/or SONIA Compounded Index data licensed under the Open Government Licence v3.0 and copyright the Governor and Company of the Bank of England. The trade marks "Bank of England" and "SONIA" are registered trade marks of the Bank of England.
- Yield curve data: Bank of England (sources: Bloomberg Finance L.P., Tradeweb and Bank calculations), https://www.bankofengland.co.uk/statistics/yield-curves. Used for internal checks; no values are reproduced.
