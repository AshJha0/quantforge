# EOD curves: 2026-11-12

Result: **PASS** (39 checks, 0 failed, 0 warnings). Generated 2026-11-12T21:47Z by `tools/workflows/`. Batch command: rust `quantforge --batch`.


## USD

USD proxy curve: Treasury par yields bootstrapped with SOFR OIS conventions. Not a SOFR swap curve. As of 2026-11-12, 13 tenors. Implementation: rust.
| Pillar | t (y) | DF | Zero (cc, %) | Fwd to pillar (%) |
|---|---|---|---|---|
| 2026-12-18 | 0.099 | 0.99589550 | 4.1701 | 4.1701 |
| 2027-01-21 | 0.192 | 0.99178905 | 4.2991 | 4.4357 |
| 2027-02-18 | 0.268 | 0.98838596 | 4.3510 | 4.4806 |
| 2027-03-18 | 0.345 | 0.98501660 | 4.3733 | 4.4514 |
| 2027-05-19 | 0.515 | 0.97745287 | 4.4276 | 4.5380 |
| 2027-11-18 | 1.016 | 0.95429035 | 4.6031 | 4.7833 |
| 2028-11-20 | 2.025 | 0.90716050 | 4.8125 | 5.0236 |
| 2029-11-20 | 3.025 | 0.86351393 | 4.8516 | 4.9309 |
| 2031-11-19 | 5.022 | 0.78177583 | 4.9023 | 4.9789 |
| 2033-11-18 | 7.022 | 0.70502226 | 4.9776 | 5.1669 |
| 2036-11-19 | 10.027 | 0.60165942 | 5.0668 | 5.2750 |
| 2046-11-20 | 20.036 | 0.32850690 | 5.5561 | 6.0464 |
| 2056-11-20 | 30.044 | 0.19666659 | 5.4129 | 5.1263 |


### USD key-rate risk, sample book

50 synthetic SOFR swaps from `tools/workflows/sample_book.py` (seed 20261107, book sha256 `49456317fff9f842`), fixed rates at par ± up to 100 bp. Figures in USD per 1 bp, sign per `risk.ois.dv01`.
| Key rate | DV01 (USD/bp) |
|---|---|
| 1M | -18.70 |
| 2M | -0.00 |
| 3M | 0.00 |
| 4M | -0.03 |
| 6M | 1.10 |
| 1Y | -983.28 |
| 2Y | -28,533.05 |
| 3Y | 6,331.47 |
| 5Y | -11,111.87 |
| 7Y | 45,453.77 |
| 10Y | 62,237.38 |
| 20Y | 61,976.11 |
| 30Y | -56,392.67 |
| Parallel | 78,960.23 |


## GBP

Reference: Bank of England fitted OIS spot curve (50 maturities) and nominal government spot curve (80 maturities) for 2026-11-11, from the latest yield curve data zip, with SONIA fixings to 2026-11-10. Only pass or fail is published: the curves are Bank copyright, licensed here for internal non-commercial use only, and raw SONIA may not be redistributed until the Bank answers (`tools/recorder/sources.json`); the zip is fetched per run and no raw copy is kept. The library does not build its own GBP curve: free data has no SONIA swap quotes to bootstrap from.

## Checks

| Check | Level | Result | Detail |
|---|---|---|---|
| USD par quotes quote levels | fail | ok | outside band: none |
| USD par quotes adjacent tenor gaps | warn | ok | none |
| USD par quotes day change | fail | ok | largest 3Y 0.0016 |
| USD par quotes day change (warn) | warn | ok | largest 3Y 0.0016 |
| SOFR level | fail | ok | 2026-11-10: 0.0389 |
| SOFR day change | fail | ok | 0.0001 vs 0.01 |
| SOFR day change (warn) | warn | ok | 0.0001 vs 0.0025 |
| USD bootstrap | fail | ok | ok |
| USD curve discount factors in band | fail | ok | min 0.196667, max 0.995896 |
| USD curve discount factors non-increasing | warn | ok | rises after none |
| USD curve zero rates in band | fail | ok | min 0.0417007, max 0.0555609 |
| USD curve forwards in band | fail | ok | min 0.0417007, max 0.0604637 |
| USD fixing vs shortest quote | warn | ok | -0.0023 vs ±0.0075 |
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
| USD sum of key rates vs parallel DV01 | warn | ok | sum 78,960.24 vs DV01 78,960.23 |
| SONIA level | fail | ok | 2026-11-10: value withheld |
| SONIA day change | fail | ok | value withheld vs 0.01 |
| SONIA day change (warn) | warn | ok | value withheld vs 0.0025 |
| GBP BoE curves read | fail | ok | OIS 8 days, nominal 8 days |
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
| GBP BoE curve date vs SONIA | warn | ok | BoE 2026-11-11, SONIA 2026-11-10 |

## Data notices

- Source: US Department of the Treasury.
- The SOFR data is subject to the Terms of Use posted at newyorkfed.org. The New York Fed is not responsible for publication of the SOFR data by QuantForge, does not sanction or endorse any particular republication, and has no liability for your use. QuantForge is not affiliated with the New York Fed. The New York Fed does not sanction, endorse, or recommend any products or services offered by QuantForge. The Secured Overnight Financing Rate (SOFR) Data are calculated using data provided under a license granted to the New York Fed by DTCC Solutions LLC ("Solutions"), an affiliate of The Depository Trust & Clearing Corporation. Solutions, its affiliates, and third parties from which they obtained data have no liability for the content of this material.
- SONIA and/or SONIA Compounded Index data licensed under the Open Government Licence v3.0 and copyright the Governor and Company of the Bank of England. The trade marks "Bank of England" and "SONIA" are registered trade marks of the Bank of England.
- Yield curve data: Bank of England (sources: Bloomberg Finance L.P., Tradeweb and Bank calculations), https://www.bankofengland.co.uk/statistics/yield-curves. Used for internal checks; no values are reproduced.
