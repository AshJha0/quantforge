# EOD curves: 2026-11-25

Result: **PASS** (39 checks, 0 failed, 0 warnings). Generated 2026-11-25T23:32Z by `tools/workflows/`. Batch command: rust `quantforge --batch`.


## USD

USD proxy curve: Treasury par yields bootstrapped with SOFR OIS conventions. Not a SOFR swap curve. As of 2026-11-25, 13 tenors. Implementation: rust.
| Pillar | t (y) | DF | Zero (cc, %) | Fwd to pillar (%) |
|---|---|---|---|---|
| 2027-01-05 | 0.112 | 0.99515763 | 4.3214 | 4.3214 |
| 2027-02-02 | 0.189 | 0.99182073 | 4.3445 | 4.3784 |
| 2027-03-02 | 0.266 | 0.98843375 | 4.3776 | 4.4592 |
| 2027-04-02 | 0.351 | 0.98470093 | 4.3963 | 4.4549 |
| 2027-06-02 | 0.518 | 0.97720925 | 4.4523 | 4.5698 |
| 2027-12-02 | 1.019 | 0.95500416 | 4.5173 | 4.5845 |
| 2028-12-04 | 2.027 | 0.91155359 | 4.5677 | 4.6186 |
| 2029-12-04 | 3.027 | 0.87004993 | 4.5982 | 4.6600 |
| 2031-12-02 | 5.022 | 0.79340867 | 4.6081 | 4.6233 |
| 2033-12-02 | 7.025 | 0.71850649 | 4.7060 | 4.9514 |
| 2036-12-02 | 10.027 | 0.61612925 | 4.8298 | 5.1193 |
| 2046-12-04 | 20.038 | 0.34040990 | 5.3777 | 5.9266 |
| 2056-12-04 | 30.047 | 0.20651214 | 5.2498 | 4.9938 |


### USD key-rate risk, sample book

50 synthetic SOFR swaps from `tools/workflows/sample_book.py` (seed 20261107, book sha256 `49456317fff9f842`), fixed rates at par ± up to 100 bp. Figures in USD per 1 bp, sign per `risk.ois.dv01`.
| Key rate | DV01 (USD/bp) |
|---|---|
| 1M | -23.80 |
| 2M | -0.00 |
| 3M | 0.00 |
| 4M | -0.07 |
| 6M | 1.15 |
| 1Y | -986.36 |
| 2Y | -28,615.75 |
| 3Y | 6,353.25 |
| 5Y | -11,196.71 |
| 7Y | 45,902.24 |
| 10Y | 62,897.31 |
| 20Y | 63,122.84 |
| 30Y | -57,733.49 |
| Parallel | 79,720.60 |


## GBP

Reference: Bank of England fitted OIS spot curve (50 maturities) and nominal government spot curve (80 maturities) for 2026-11-24, from the latest yield curve data zip, with SONIA fixings to 2026-11-23. Only pass or fail is published: the curves are Bank copyright, licensed here for internal non-commercial use only, and raw SONIA may not be redistributed until the Bank answers (`tools/recorder/sources.json`); the zip is fetched per run and no raw copy is kept. The library does not build its own GBP curve: free data has no SONIA swap quotes to bootstrap from.

## Checks

| Check | Level | Result | Detail |
|---|---|---|---|
| USD par quotes quote levels | fail | ok | outside band: none |
| USD par quotes adjacent tenor gaps | warn | ok | none |
| USD par quotes day change | fail | ok | largest 10Y 0.0006 |
| USD par quotes day change (warn) | warn | ok | largest 10Y 0.0006 |
| SOFR level | fail | ok | 2026-11-24: 0.0394 |
| SOFR day change | fail | ok | 0.0002 vs 0.01 |
| SOFR day change (warn) | warn | ok | 0.0002 vs 0.0025 |
| USD bootstrap | fail | ok | ok |
| USD curve discount factors in band | fail | ok | min 0.206512, max 0.995158 |
| USD curve discount factors non-increasing | warn | ok | rises after none |
| USD curve zero rates in band | fail | ok | min 0.0432137, max 0.0537771 |
| USD curve forwards in band | fail | ok | min 0.0432137, max 0.0592657 |
| USD fixing vs shortest quote | warn | ok | -0.0033 vs ±0.0075 |
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
| USD sum of key rates vs parallel DV01 | warn | ok | sum 79,720.61 vs DV01 79,720.60 |
| SONIA level | fail | ok | 2026-11-23: value withheld |
| SONIA day change | fail | ok | value withheld vs 0.01 |
| SONIA day change (warn) | warn | ok | value withheld vs 0.0025 |
| GBP BoE curves read | fail | ok | OIS 17 days, nominal 17 days |
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
| GBP BoE curve date vs SONIA | warn | ok | BoE 2026-11-24, SONIA 2026-11-23 |

## Data notices

- Source: US Department of the Treasury.
- The SOFR data is subject to the Terms of Use posted at newyorkfed.org. The New York Fed is not responsible for publication of the SOFR data by QuantForge, does not sanction or endorse any particular republication, and has no liability for your use. QuantForge is not affiliated with the New York Fed. The New York Fed does not sanction, endorse, or recommend any products or services offered by QuantForge. The Secured Overnight Financing Rate (SOFR) Data are calculated using data provided under a license granted to the New York Fed by DTCC Solutions LLC ("Solutions"), an affiliate of The Depository Trust & Clearing Corporation. Solutions, its affiliates, and third parties from which they obtained data have no liability for the content of this material.
- SONIA and/or SONIA Compounded Index data licensed under the Open Government Licence v3.0 and copyright the Governor and Company of the Bank of England. The trade marks "Bank of England" and "SONIA" are registered trade marks of the Bank of England.
- Yield curve data: Bank of England (sources: Bloomberg Finance L.P., Tradeweb and Bank calculations), https://www.bankofengland.co.uk/statistics/yield-curves. Used for internal checks; no values are reproduced.
