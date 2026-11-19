## Basel Framework PDF, READ 2026-11-19

Written 2026-11-19 by the stage K wave 2 spec lane (reading and writing only). Same text in `institutional-quant-engine-plan/STAGE_K_SOURCES.md` (appended) and in the repo as `program/STAGE_K_SOURCES_W2.md`. Only short quotations (formulas, parameters, paragraph numbers); everything else is in our words. The PDF and the extracted text are not committed.

### What the file is (evidence class: read)

- File: `institutional-quant-engine-plan/basel-framework-full.pdf`, 8,221,890 bytes, file date 2026-11-11.
- Title page: "The Basel Framework", Basel Committee on Banking Supervision. Page 2: generated on 11/11/2026 from the Basel Framework data on the BIS website, copyright BIS 2026. Every page header reads "11/11/2026 n / 1429".
- 1429 pages. The whole consolidated framework: SCO, CAP, RBC, CRE, MAR, OPE, LEV, LCR, NSF, LEX, MGN, SRP, DIS, BCP (table of contents on PDF pages 3 to 5).
- Version: each chapter carries its own "version effective as of" line. Those read here: MAR22, MAR23, MAR31, MAR32, MAR33, MAR50, MAR99, LEV30, LEX30 effective 1 January 2023; LEX10 and LEX20 effective 15 December 2019; MAR30 carries an FAQ added 5 July 2024. So the PDF is the framework as in force on 11 November 2026, not a frozen 2019 or 2020 text.
- How read: text extracted per page with `pypdf` 6.21.3 into a scratch folder outside the repo. Formulas are embedded images, not text; each formula used below was read by opening the image drawn on that page (PDF page numbers given). Where a formula image and the paragraph text disagree, both are recorded.
- PDF page = the "n / 1429" page number; the framework has no other printed page numbers.

Chapter locations (PDF pages): MAR21 567-618, MAR22 619-633, MAR23 634-637, MAR31 646-657, MAR32 658-668, MAR33 669-686, MAR50 722-750, MAR99 753-761, CRE53 463-482, CRE99 515-547, LEV20 787-789, LEV30 790-810, LEV40 811-813, LEX10 937-941, LEX20 942-943, LEX30 944-956.

### Status per chapter

| Chapter | Status | Worked examples with printed numbers |
|---|---|---|
| MAR22 default risk capital | read in full | MAR22.16 FAQ (index future against stock, net JTD 0); MAR22.45 (CTP +100 and -100 give 50); text illustrations of maturity weights (one-half, one quarter) |
| MAR23 residual risk add-on | read in full | none |
| MAR21 | read only MAR21.4 (SBM aggregation), as SA-CVA reuses it | none used |
| MAR31 RFET | read MAR31.1-31.26 | none (bucketing table only; footnote 306 dated example, no capital number) |
| MAR32 backtesting and PLA | read in full | Table 1 zones and multipliers; KS p-values printed next to the thresholds; MAR32.6 FAQ (EUR -1.5m P&L, 1m VaR, 0.8m NMRF charge not enough) |
| MAR33 ES, LH, stressed, SES, capital | read in full | MAR33.12 FAQ4 (IR volatility, 30-day instrument gets LH 40); MAR33.12 FAQ5 (weighted average LH 12 gives 20) |
| MAR50 BA-CVA, SA-CVA | read in full | none |
| MAR99 | read in full | Table 1 (exact and type 1/type 2 binomial probabilities, k = 0..15, coverage 99/98/97/96/95%); Table 2 (zones, multipliers, cumulative probabilities). No SBM, DRC, ES or CVA examples |
| CRE53 | read MAR-relevant parts: CRE53.7, 53.11-53.26, 53.51 | none |
| CRE99 | read the contents list and the SA-CCR examples (CRE99.20-99.97) | SA-CCR EADs of Examples 1 to 5 (see below) |
| LEV (LEV20, LEV30, LEV40.1-40.5) | read | LEV30.31 footnote 384 (written credit derivative fair value example) |
| LEX (LEX10, LEX20, LEX30.1-30.31) | read | none |

Not in the PDF: nothing requested is missing. ISDA SIMM and ORE are not BIS texts and were not read here.

### MAR22, default risk capital (DRC), standardised approach

- Scope and steps: MAR22.2-22.4 (non-securitisation, securitisation non-CTP, CTP; no diversification between the three). Gross JTD per exposure, offset per obligor, bucket, hedge benefit ratio, risk weights, simple sum over buckets (MAR22.3).
- Gross JTD, MAR22.11 (images, page 622): `JTD(long) = max(LGD x notional + P&L, 0)`, `JTD(short) = min(LGD x notional + P&L, 0)`. Notional is the bond-equivalent notional; P&L = market value minus notional (MAR22.11(2)). Long notional positive, short negative; P&L loss negative, gain positive (MAR22.13). Long/short is by loss or gain on default, not by bought or sold (MAR22.10; a sold put on a bond is long credit).
- LGD, MAR22.12 (page 622): equity and non-senior debt 100%; senior debt 75%; covered bonds (MAR21.51) 25%; no LGD multiplication when the price is not linked to recovery.
- Table 1, MAR22.14 (pages 623-624): bond (notional = face, P&L = MV - face); CDS (notional = CDS notional, bond-equivalent MV = notional + MtM, P&L = - MtM); sold put on a bond (notional = option notional, bond-equivalent MV = strike - |MtM|, P&L = (strike - |MtM|) - notional); bought call on a bond (notional 0, P&L = MtM). MtM of a CDS or option enters as an absolute value; option strike as a bond price.
- Maturity weighting: exposures under one year and their hedges scaled by the fraction of a year, none at one year or more (MAR22.15; footnote 296: it scales gross JTD). Text example: six months weighted one-half. Floor of one quarter (three months) for any product (MAR22.18). Cash equity: three months or more than one year, bank's choice, nothing in between (MAR22.16 and its FAQ). Derivatives use the contract maturity (MAR22.17).
- Offsetting, MAR22.19-22.21: long and short to the same obligor offset when the short is the same or lower seniority than the long (equity short may offset a bond long, not the reverse); over one year fully; under one year weighted by maturity (text example: a three-month short counts one quarter against a long of more than one year). Net long and net short positions are aggregated separately.
- Buckets, MAR22.22: corporates, sovereigns, local governments and municipalities.
- HBR, MAR22.23 (image page 627): `HBR = sum netJTD_long / (sum netJTD_long + sum |netJTD_short|)`, sums over rating bands, not risk weighted.
- Risk weights, MAR22.24 Table 2 (pages 627-628): AAA 0.5%, AA 2%, A 3%, BBB 6%, BB 15%, B 30%, CCC 50%, unrated 15%, defaulted 100%.
- Bucket capital, MAR22.25 (image page 628): `DRC_b = max[(sum_{i in Long} RW_i netJTD_i) - HBR (sum_{i in Short} RW_i |netJTD_i|); 0]`. Total = simple sum over buckets (MAR22.26).
- Securitisation non-CTP: JTD = market value, no LGD (MAR22.27); offsetting only within the same tranche and pool, maturity offsets as non-securitisation (MAR22.29-22.30); buckets: corporates plus 11 asset classes x 4 regions (MAR22.31); risk weights from the banking book securitisation framework CRE40-CRE44 with the maturity component set to zero (MAR22.34); same HBR and bucket formula (MAR22.33). Risk weights are not tabulated in MAR22.
- CTP: JTD = market value (MAR22.36-22.37); nth-to-default attachment `(N-1)/total names`, detachment `N/total names` (MAR22.38); each index is a bucket (MAR22.40); bucket formula (image page 633) `DRC_b = (sum_Long RW_i netJTD_i) - HBR_ctp (sum_Short RW_i |netJTD_i|)` with HBR_ctp computed over all CTP positions and **no floor** at the bucket (MAR22.44); total `DRC_CTP = max[sum_b (max[DRC_b,0] + 0.5 x min[DRC_b,0]), 0]` (MAR22.45, image page 633).
- **Printed examples.** (a) MAR22.16 FAQ (page 625): index future, market value EUR -10m, one month, hedged by EUR +10m of the stocks; both at three months; JTD "1/4*10 - 1/4*10 = 0". (b) MAR22.45 (page 633): bucket DRC +100 (CDX North America IG) and -100 (Major Sovereign) give "100 - 0.5 x 100 = 50" (image). (c) MAR22.15: six-month position weighted one-half. (d) MAR22.19(3)(b): three-month short counts one quarter.

### MAR23, residual risk add-on (RRAO)

- Scope: exotic underlying (MAR23.3; footnote 298 examples: longevity, weather, natural disasters, future realised volatility) and other residual risks (MAR23.4: vega or curvature instruments not replicable by a finite linear combination of single-underlying vanillas, and CTP instruments other than eligible hedges). MAR23.5 lists gap, correlation and behavioural risk instruments; MAR23.6 lists what alone does not trigger RRAO.
- Exclusions, MAR23.7: exact back-to-back third-party matches excluded; listed or centrally clearable instruments excluded from "other residual risks" but included when the underlying is exotic.
- Formula, MAR23.8(2): simple sum of gross notionals times risk weight; 1.0% exotic underlying, 0.1% other residual risks.
- The chapter ends at MAR23.8.

### MAR21.4, sensitivities-based aggregation (only as SA-CVA reuses it)

Read MAR21.4 (pages 570-571): within a bucket the quantity under the square root is floored at zero; across buckets `S_b = sum WS_k` is used first, and only if the overall sum under the root is negative the alternative `S_b = max(min(sum WS_k, K_b), -K_b)` is used. MAR50.53(2) states that the SA-CVA equation differs from MAR21.4, including the multiplier m_CVA (below).

### MAR31, risk factor eligibility test (RFET)

- Real price criteria, MAR31.12: a transaction of the bank, a verifiable arm's-length transaction, a committed quote (collected through a vendor, platform or exchange), or a vendor price meeting conditions. FAQ: committed quote is one the provider must deal at.
- Test, MAR31.13 (page 650): either (1) at least 24 real price observations per year over the ES calibration period, at most one per day, **and** no 90-day period in the previous 12 months with fewer than four, monitored monthly; or (2) at least 100 real price observations over the previous 12 months, at most one per day. Footnote 301: the RFET period may lag the calibration period by at most one month.
- Vendor counts, MAR31.14; representativeness, MAR31.15.
- Regulatory buckets, MAR31.16 Table 1 (page 652), lower bound inclusive, upper exclusive:
  - row A (IR, FX, commodity, one maturity dimension): 0-0.75, 0.75-1.5, 1.5-4, 4-7, 7-12, 12-18, 18-25, 25-35, 35+ years;
  - row B (several maturity dimensions): 0-0.75, 0.75-4, 4-10, 10-18, 18-30, 30+;
  - row C (credit spread and equity): 0-1.5, 1.5-3.5, 3.5-7.5, 7.5-15, 15+;
  - row D (delta of options): 0-0.05, 0.05-0.3, 0.3-0.7, 0.7-0.95, 0.95-1.00.
- MAR31.17-31.21: observations counted per bucket; one maturity bucket per observation; parametric curves tested at the level of the calibrating market data; systematic risk factors. MAR31.23: failing the data principles makes the factor an NMRF. MAR31.26: seven data principles (principle six: the stressed ES data, with the 75% reduced-set rule of MAR33.5(2)(b)).

### MAR32, backtesting and P&L attribution (PLA)

- Backtesting: one-day VaR against APL and HPL over 12 months (MAR32.4); bank-wide at 99% (MAR32.5); exceptions counted separately for APL and HPL, the larger counts (MAR32.5(1), MAR99.8); missing P&L or VaR counts as an exception (MAR32.5(2)).
- Zones, MAR32.9 Table 1 (page 661): 0-4 exceptions green, multiplier 1.50; 5 to 9 amber 1.70, 1.76, 1.83, 1.88, 1.92; 10 or more red 2.00. These are the multipliers themselves ("to be added to any qualitative add-on").
- Desk level, MAR32.18-32.19: 97.5% and 99% one-day VaR; more than 12 exceptions at 99% or 30 at 97.5% in 12 months sends the desk to the standardised approach.
- PLA: RTPL against HPL (MAR32.20-32.33). Metrics: Spearman correlation and Kolmogorov-Smirnov (MAR32.34) on the most recent 250 trading days (MAR32.35). Ranks: lowest value rank 1 (MAR32.36-32.37). Spearman (image page 666): `r_S = cov(R_HPL, R_RTPL) / (sigma_R_HPL x sigma_R_RTPL)` (MAR32.38). Empirical CDF: 0.004 times the number of observations less than or equal to the value (MAR32.39-32.40). KS = largest absolute difference of the two ECDFs at any P&L value (MAR32.41).
- Zones, MAR32.42 and Table 2 (page 667): green if correlation **above** 0.80 **and** KS **below** 0.09 ("p-value = 0.264"); red if correlation **less than** 0.70 **or** KS **above** 0.12 ("p-value = 0.055"); amber otherwise. Red desks leave the IMA (MAR32.43); amber desks pay the surcharge of MAR33.43 (MAR32.44).
- Printed p-values checked with SciPy (2026-11-19, scratch, not committed): the asymptotic two-sample Kolmogorov tail `kstwobign.sf(D x sqrt(250 x 250 / 500))` gives 0.26338 at D = 0.09 and 0.05465 at D = 0.12. The second rounds to the printed 0.055; the first rounds to 0.263, not the printed 0.264 (difference 0.0006). Exact two-sample values at the grid points either side differ more (0.288 at 22/250, 0.241 at 23/250). So the printed values are the asymptotic distribution with effective size 125, and 0.264 carries a small rounding difference. Evidence class: measured.

### MAR33, IMA capital

- ES at 97.5% one-tailed (MAR33.3), daily (MAR33.2).
- Liquidity horizons, MAR33.4 (image page 671): `ES = sqrt( (ES_T(P))^2 + sum_{j>=2} ( ES_T(P,j) sqrt((LH_j - LH_{j-1})/T) )^2 )`, T = 10 days; ES_T(P,j) shocks only the risk factors whose LH is at least LH_j, others constant; computed at horizon T without scaling from a shorter horizon; overlapping observations allowed. Table 1: LH_j = 10, 20, 40, 60, 120 for j = 1..5.
- Stress calibration, MAR33.5-33.7: reduced set of risk factors explaining at least 75% of the full ES on average over the preceding 12 weeks (MAR33.5(2)(b) and FAQ3); MAR33.6 (image page 672) `ES = ES_R,S x ES_F,C / ES_R,C`, and the text of MAR33.6(2) floors the ratio at 1 (the image does not show the floor); most severe 12-month period, lookback to 2007 at least (MAR33.7); current data updated at least every three months, shortened period not below six months (MAR33.8).
- Liquidity horizon table, MAR33.12 Table 2 (pages 674-675): IR specified currencies (EUR, USD, GBP, AUD, JPY, SEK, CAD, domestic) 10, unspecified 20, IR volatility 60, IR other 60; credit spread sovereign IG 20, sovereign HY 40, corporate IG 40, corporate HY 60, volatility 120, other 120; equity large cap 10, small cap 20, large cap volatility 20, small cap volatility 60, other 60; FX specified pairs (footnote 309: 23 pairs and their first-order crosses) 10, other pairs 20, FX volatility 40, FX other 40; energy and carbon 20, precious and non-ferrous metals 20, other commodities 60, energy and carbon volatility 60, metals volatility 60, other commodities volatility 120, commodity other types 120. A desk may raise n to 20, 40, 60 or 120 with approval; LH capped at the instrument maturity (MAR33.12(3)). FAQ1: equity repo and dividends 20 for large cap, 60 otherwise. FAQ2: basis risk follows the IR currency. FAQ3: inflation follows IR. **FAQ4 printed example**: IR volatility (60) on an instrument maturing in 30 days uses 40. **FAQ5 printed example**: multi-sector index with weighted average LH 12 uses 20.
- IMCC, MAR33.13-33.15 (image page 676): `IMCC = rho IMCC(C) + (1 - rho) sum_{i=1}^{B} IMCC(C_i)`, `IMCC(C) = ES_R,S x ES_F,C / ES_R,C`, `IMCC(C_i) = ES_R,S,i x ES_F,C,i / ES_R,C,i`, rho = 0.5, B = five broad classes (IR, equity, FX, commodity, credit spread); same stress period for the classes.
- NMRF, MAR33.16: stress scenario at least as prudent as ES (97.5% over a stress period), common 12-month stress period per risk class, LH = max(MAR33.12 LH, 20 days); idiosyncratic credit and equity NMRFs may be aggregated with zero correlation after supervisory analysis (footnote 310); if no acceptable scenario, maximum possible loss.
- SES, MAR33.17 (image page 678): `SES = sqrt(sum_{i=1}^{I} ISES_NM,i^2) + sqrt(sum_{j=1}^{J} ISES_NM,j^2) + sqrt( (rho sum_{k=1}^{K} SES_NM,k)^2 + (1 - rho^2) sum_{k=1}^{K} SES_NM,k^2 )`, rho = 0.6.
- IMA DRC model, MAR33.18-33.39: VaR at 99.9%, one year, weekly (MAR33.20(5)); two types of systematic factors (FAQ3); 60-day minimum for equity sub-portfolios (MAR33.20(4)); capital = max(12-week average, latest) (MAR33.22); PD floor 0.03% (MAR33.24(2)); correlations over at least 10 years (MAR33.27(4)). Not in K-8f scope (simulation model).
- Aggregation, MAR33.41 (image page 685): `C_A = max{IMCC_{t-1} + SES_{t-1}; m_c IMCC_avg + SES_avg}`, averages over 60 days. m_c = 1.5 plus a backtesting plus of 0 to 0.5 from the 99% VaR backtest (MAR33.42).
- MAR33.43 (images page 685): `IMA_G,A = C_A + DRC`; `ACR_total = min{IMA_G,A + Capital surcharge + C_U; SA_all desk} + max{0; IMA_G,A - SA_G,A}`.
- MAR33.45 (images page 686): `Capital surcharge = k max{0, SA_G,A - IMA_G,A}`, `k = 0.5 x sum_{i in A} SA_i / sum_{i in G,A} SA_i` (A: amber desks; G,A: green or amber).
- RWA = 12.5 x capital (MAR33.46).

### MAR50, CVA capital

- Scope: covered transactions (MAR50.5); standalone CVA portfolio (MAR50.6); BA-CVA unless SA-CVA approved (MAR50.7); carve-outs (MAR50.8); below EUR 100 billion non-centrally cleared notional a bank may set CVA capital = 100% of CCR capital (MAR50.9). RWA = 12.5 x capital (MAR50.1).
- BA-CVA reduced, MAR50.14 (image page 726): capital `DS_BA-CVA x K_reduced`, DS = 0.65, `K_reduced = sqrt( (rho sum_c SCVA_c)^2 + (1 - rho^2) sum_c SCVA_c^2 )`, rho = 50%.
- SCVA, MAR50.15 (image page 726): `SCVA_c = (1/alpha) RW_c sum_NS M_NS EAD_NS DF_NS`, alpha = 1.4; M_NS effective maturity (IMM banks: CRE53.20-53.21 without the five-year cap; others: CRE32.46-32.54 without the five-year cap); EAD as for CCR capital; DF = 1 for IMM banks, else `(1 - e^{-0.05 M_NS}) / (0.05 M_NS)` (footnote 357: average discount factor at 5% to the effective maturity).
- Risk weights, MAR50.16 Table 1 (page 727), IG / HY and NR: sovereigns, central banks, MDBs 0.5% / 2.0%; local government, government-backed non-financials, education, public administration 1.0% / 4.0%; financials 5.0% / 12.0%; basic materials, energy, industrials, agriculture, manufacturing, mining 3.0% / 7.0%; consumer goods and services, transportation, administrative 3.0% / 8.5%; technology, telecommunications 2.0% / 5.5%; health care, utilities, professional and technical 1.5% / 5.0%; other 5.0% / 12.0%.
- BA-CVA full, MAR50.17-50.26 (images pages 728-730): eligible hedges are single-name CDS, single-name contingent CDS and index CDS (MAR50.18); `K_full = beta K_reduced + (1 - beta) K_hedged`, beta = 0.25 (MAR50.20); `K_hedged = sqrt( (rho sum_c (SCVA_c - SNH_c) - IH)^2 + (1 - rho^2) sum_c (SCVA_c - SNH_c)^2 + sum_c HMA_c )` (MAR50.21); `SNH_c = sum_{h in c} r_hc RW_h M_h^SN B_h^SN DF_h^SN` (MAR50.23); `IH = sum_i RW_i M_i^ind B_i^ind DF_i^ind` (MAR50.24); `HMA_c = sum_{h in c} (1 - r_hc^2) (RW_h M_h^SN B_h^SN DF_h^SN)^2` (MAR50.25); hedge DFs use the same 5% formula on the hedge maturity; index RW = Table 1 value x 0.7, or the name-weighted average x 0.7 for mixed indices (MAR50.24(4)); r_hc (Table 2, MAR50.26): 100% direct, 80% legally related, 50% same sector and region.
- SA-CVA, MAR50.27-50.77: monthly (MAR50.28); delta for IR, FX, counterparty credit spread, reference credit spread, equity, commodity (MAR50.43); vega for the same less counterparty credit spread (MAR50.45); m_CVA = 1, supervisor may raise (MAR50.41); WS (images page 737) `WS_k^CVA = RW_k s_k^CVA`, `WS_k^Hdg = RW_k s_k^Hdg`, `WS_k = WS_k^CVA - WS_k^Hdg` (MAR50.51-50.52; footnote 359: CVA is a positive number, so the hedge enters with a minus sign).
- SA-CVA aggregation, MAR50.53 (images page 738): `K_b = sqrt( (sum_{k in b} WS_k^2 + sum_{k in b} sum_{l in b, l != k} rho_kl WS_k WS_l) + R sum_{k in b} (WS_k^Hdg)^2 )`, R = 0.01; `K = m_CVA sqrt( sum_b K_b^2 + sum_b sum_{c != b} gamma_bc S_b S_c )`; `S_b = max{-K_b; min(sum_{k in b} WS_k; K_b)}` always (no first try with the unclipped sum, unlike MAR21.4). No floor at zero is written under either root.
- IR: buckets per currency, gamma 0.5 (MAR50.54-50.55). Specified currencies (reporting, USD, EUR, GBP, AUD, CAD, SEK, JPY): tenors 1, 2, 5, 10, 30 years plus inflation, 1 bp shift divided by 0.0001; RW (Table 3) 1.11%, 0.93%, 0.74%, 0.74%, 0.74%, inflation 1.11%; rho (Table 4) 1Y-2Y 91%, 1Y-5Y 72%, 1Y-10Y 55%, 1Y-30Y 31%, 2Y-5Y 87%, 2Y-10Y 72%, 2Y-30Y 45%, 5Y-10Y 91%, 5Y-30Y 68%, 10Y-30Y 83%, any tenor with inflation 40% (MAR50.56). Other currencies: parallel shift and inflation, RW 1.58%, rho 40% (MAR50.57). IR vega: RW 100%, rho 40% (MAR50.58).
- FX: buckets per non-reporting currency, gamma 0.6 (MAR50.59-50.60); delta 1% relative shift / 0.01, RW 11% (MAR50.61); vega RW 100% (MAR50.62).
- Counterparty credit spread (delta only): buckets 1 (a sovereigns, b local government) to 7 by sector, 8 qualified indices (Table 5, MAR50.63); gamma Table 6 (MAR50.64): 1-2 10%, 1-3 20%, 1-4 25%, 1-5 20%, 1-6 15%, 2-3 5%, 2-4 15%, 2-5 20%, 2-6 5%, 3-4 20%, 3-5 25%, 3-6 5%, 4-5 25%, 4-6 5%, 5-6 5%, bucket 7 with any 0%, bucket 8 with 1-6 45%, 7-8 0%; tenors 0.5, 1, 3, 5, 10 years (MAR50.65(1)); RW Table 7 IG / HY-NR: 1a 0.5/2.0, 1b 1.0/4.0, 2 5.0/12.0, 3 3.0/7.0, 4 3.0/8.5, 5 2.0/5.5, 6 1.5/5.0, 7 5.0/12.0, 8 1.5/5.0 (%); `rho_kl = rho_tenor x rho_name x rho_quality` (image page 743): buckets 1-7 tenor 100%/90%, name 100% same, 90% legally related, 50% otherwise, quality 100%/80%; bucket 8 tenor 100%/90%, name 100% same index and series, 90% same index other series, 80% otherwise, quality 100%/80%.
- Reference credit spread: 17 buckets (Table 8: 1-7 IG by sector, 8-14 HY/NR by sector, 15 other, 16 IG indices, 17 HY indices), gamma Table 9 for the same credit quality and halved across qualities for buckets 1-14 (MAR50.67); one factor per bucket (all names, all tenors, 1 bp) (MAR50.68); RW Table 10 by bucket 1-17: 0.5, 1.0, 5.0, 3.0, 3.0, 2.0, 1.5, 2.0, 4.0, 12.0, 7.0, 8.5, 5.5, 5.0, 12.0, 1.5, 5.0 (%). Table 10 prints buckets 8 and 9 in the row labelled IG; by Table 8 they are HY/NR sovereign and local government, and the values (2.0%, 4.0%) match the HY column of MAR50.16. Vega RW 100% (MAR50.69).
- Equity: 13 buckets (Table 11; large cap at least USD 2 billion), gamma 15% within 1-10, 75% between 12 and 13, 45% between 12 or 13 and 1-10, 0% with 11 (MAR50.71); one factor per bucket, 1% relative; RW Table 12: 55, 60, 45, 55, 30, 35, 40, 50, 70, 50, 70, 15, 25 (%) (MAR50.72); vega RW 78% large cap, 100% other (MAR50.73).
- Commodity: 11 buckets (Table 13), gamma 20% within 1-10, 0% with 11 (MAR50.75); RW Table 14: 30, 35, 60, 80, 40, 45, 20, 35, 25, 35, 50 (%) (MAR50.76); vega RW 100% (MAR50.77).
- Regulatory CVA for SA-CVA, MAR50.32: MPoR floors 4 + N business days for SFTs and client-cleared trades (5 for daily margining) and 9 + N for others.

### MAR99

- MAR99.1-99.8: desk backtesting and the APL/HPL rule (the larger count).
- MAR99.11 Table 1 (pages 755-756), 250 independent observations; columns coverage 99% (exact, type 1), 98%, 97%, 96%, 95% (exact, type 2). Rows k = 0..15, all printed to 0.1%. Coverage 99% exact: 8.1, 20.5, 25.7, 21.5, 13.4, 6.7, 2.7, 1.0, 0.3, 0.1, 0.0 (k = 10 to 15); type 1: 100.0, 91.9, 71.4, 45.7, 24.2, 10.8, 4.1, 1.4, 0.4, 0.1, 0.0. Coverage 98% exact: 0.6, 3.3, 8.3, 14.0, 17.7, 17.7, 14.8, 10.5, 6.5, 3.6, 1.8, 0.8, 0.3, 0.1, 0.0, 0.0; type 2: 0.0, 0.6, 3.9, 12.2, 26.2, 43.9, 61.6, 76.4, 86.9, 93.4, 97.0, 98.7, 99.5, 99.8, 99.9, 100.0. Coverage 97% exact: 0.0, 0.4, 1.5, 3.8, 7.2, 10.9, 13.8, 14.9, 14.0, 11.6, 8.6, 5.8, 3.6, 2.0, 1.1, 0.5; type 2: 0.0, 0.0, 0.4, 1.9, 5.7, 12.8, 23.7, 37.5, 52.4, 66.3, 77.9, 86.6, 92.4, 96.0, 98.0, 99.1. Coverage 96% exact: 0.0, 0.0, 0.2, 0.7, 1.8, 3.6, 6.2, 9.0, 11.3, 12.7, 12.8, 11.6, 9.6, 7.3, 5.2, 3.4; type 2: 0.0, 0.0, 0.0, 0.2, 0.9, 2.7, 6.3, 12.5, 21.5, 32.8, 45.5, 58.3, 69.9, 79.5, 86.9, 92.1. Coverage 95% exact: 0.0, 0.0, 0.0, 0.1, 0.3, 0.9, 1.8, 3.4, 5.4, 7.6, 9.6, 11.1, 11.6, 11.2, 10.0, 8.2; type 2: 0.0, 0.0, 0.0, 0.0, 0.1, 0.5, 1.3, 3.1, 6.5, 11.9, 19.5, 29.1, 40.2, 51.8, 62.9, 72.9. Definitions (notes to Table 1): type 1 at k is P(X >= k) under 99%; type 2 at k is P(X < k) under the alternative.
- MAR99.17 Table 2 (page 758): as MAR32.9 plus cumulative probabilities 8.11, 28.58, 54.32, 75.81, 89.22, 95.88, 98.63, 99.60, 99.89, 99.97, 99.99 (%) for k = 0..10. SciPy `binom.cdf(k, 250, 0.01)` reproduces all eleven to two decimals (measured 2026-11-19). Other sample sizes: amber from cumulative >= 95%, red from >= 99.99%.
- MAR99.21: under normality the 99th/98th percentile ratio is about 1.14 and the needed increase about 1.13 (printed, approximate).
- MAR99.22: modellability evidence examples (qualitative).
- No SBM, DRC, RRAO, ES, NMRF or CVA examples are in MAR99.

### CRE53 (only MPoR and stressed exposure definitions)

- EAD = alpha x Effective EPE (CRE53.11, image page 465); alpha = 1.4 (CRE53.14); own alpha floor 1.2 (CRE53.16).
- Effective EE recursion `Effective EE_tk = max(Effective EE_tk-1, EE_tk)` and `Effective EPE = sum_{k=1}^{min(1 year, maturity)} Effective EE_tk x dt_k` (CRE53.12-53.13, images page 466).
- Effective maturity (CRE53.20, image page 467) with a five-year cap; one-year floor when all contracts are under one year (CRE53.21). BA-CVA drops the cap (MAR50.15(2)).
- Stressed exposure: capital is the larger of the portfolio-level requirement on Effective EPE with current data and with a stress calibration, compared at portfolio level, never per counterparty (CRE53.7). Stress calibration uses three years of data including a period of stress to counterparties' credit spreads, or market-implied data from a stress period; benchmark-portfolio checks (CRE53.51).
- MPoR floors, CRE53.24 (daily re-margining): 5 business days for repo-style-only netting sets, 10 for others; 20 when a netting set exceeds 5000 trades at any point in a quarter (next quarter) or holds illiquid collateral or hard-to-replace OTC derivatives. More than two disputes in two quarters longer than the MPoR: at least double the floor for two quarters (CRE53.25). Re-margining every N days: `MPoR = F + N - 1` (CRE53.26, image page 469).

### CRE99 (worked examples)

Contents (CRE99.1): illustrative IRB risk weights (CRE99.2-99.3), SEC-IRBA dilution examples (99.4-99.19), SA-CCR sample portfolios (99.20-99.97), margin agreement examples (99.98-99.115), equity investments in funds (99.116-99.133). None of these is a wave 2 item. The SA-CCR EADs, read from the images, agree with the BCBS 279 Annex 4a values recorded on 2026-11-15:
- Example 1 (CRE99.40, page 528): `EAD = 1.4 x (60 + 1 x 347) = 569`.
- Example 2 (CRE99.58, page 532): `EAD = 1.4 x (0 + 0.965 x 282) = 381`.
- Example 3 (CRE99.76, page 536): `EAD = 1.4 x (20 + 1 x 3,841) = 5,406`.
- Example 4 (CRE99.77-99.79, pages 536-537): RC = max{30 - 20 + 50 + 20 - 40 + 0; 0} = 40; add-on 347 + 282 = 629; `EAD = 1.4 x (40 + 1 x 629) = 936`.
- Example 5 (CRE99.80-99.97, pages 537-540): RC = max{80 - 200; 0 + 5 - 150; 0} = 0; energy 639, metals 639, commodity 1,278; aggregate 123 + 1,278 = 1,401; multiplier min(1; 0.05 + 0.95 exp((80 - 200)/(2 x 0.95 x 1,401))) = 0.958; `EAD = 1.4 x (0 + 0.958 x 1,401) = 1,879`.
The printed EADs are rounded from unrounded intermediates (1.4 x 407 = 569.8 printed 569; 1.4 x 3,861 = 5,405.4 printed 5,406).

### LEV (leverage ratio)

- Ratio = capital measure / exposure measure (LEV20.3, image page 788); capital measure = Tier 1 (LEV20.4); exposure = on-balance sheet (excluding derivatives and SFTs) + derivatives + SFTs + off-balance sheet (LEV20.5); quarter-end (LEV20.6); minimum 3% at all times (LEV20.7).
- General: gross accounting values; no netting or credit risk mitigation unless stated (LEV30.1-30.2); Tier 1 deductions may be deducted (LEV30.3); liabilities never (LEV30.4).
- On-balance sheet: accounting value less specific provisions; general provisions that reduced Tier 1 may be deducted (LEV30.8-30.9).
- Derivatives: `exposure measure = alpha x (RC + PFE)`, alpha = 1.4 (LEV30.14-30.16, image page 795); `RC = max(V - CVM_r + CVM_p, 0)` with eligible cash variation margin only (LEV30.16(2), LEV30.24); PFE per CRE52.20-52.76 with the multiplier fixed at one (LEV30.16(3)(a)); margined maturity factor allowed (LEV30.16(3)(b)); written options included (LEV30.16(3)(c)); collateral received never reduces RC (LEV30.22); provided collateral grossed up (LEV30.23).
- Written credit derivatives: effective notional added (LEV30.31), reducible by negative fair value changes taken into Tier 1 and by eligible purchased protection on the same reference name (conditions LEV30.31(1)-(5), 30.32-30.34); PFE for the unoffset written part may be excluded (LEV30.35). **Printed example (footnote 384, page 801):** fair value +20 then -10: effective notional may be reduced by 10, not by 30; if the later fair value is +5, no reduction.
- SFTs: gross SFT assets with limited netting (LEV30.37(1)) plus a counterparty measure without PFE (LEV30.37(2), images page 805): with a qualifying MNA `E* = max(0, sum E_i - sum C_i)`; without, per transaction `E_i* = max(0, E_i - C_i)`. Agent treatment LEV30.41-30.44.
- Off-balance sheet: notional x CCF (LEV30.46-30.47); provisions may reduce the converted amount, not below zero (LEV30.48); CCF 100% for direct credit substitutes, forward purchases, unsettled purchases under settlement-date accounting, other credit substitutes (LEV30.49); 50% NIFs and RUFs (LEV30.50) and transaction-related contingents (LEV30.51); 40% commitments (LEV30.52); 20% short-term self-liquidating trade letters of credit (LEV30.53); 10% unconditionally cancellable commitments (LEV30.54); the lower of two applicable CCFs (LEV30.55).
- G-SIB buffer: 50% of the G-SIB higher loss-absorbency requirement (LEV40.2).

### LEX (large exposures)

- Large exposure: sum of exposure values to a counterparty or group of connected counterparties at or above 10% of Tier 1 (LEX10.8). Limit: not higher than 25% of Tier 1 at all times; 15% for a G-SIB's exposures to another G-SIB (LEX20.1). Tier 1 per CAP10.2 (LEX20.2). Reporting: all exposures at or above 10% before and after CRM, exempted ones at or above 10%, and the largest 20 (LEX20.4).
- Connected counterparties: control (more than 50% of voting rights is automatic, LEX10.12; other control criteria LEX10.13) or economic interdependence (LEX10.16 criteria, including 50% of gross receipts or expenditures); investigation required where exposure to one counterparty exceeds 5% of Tier 1 (LEX10.18). Only sovereigns are outside the framework (LEX10.7).
- Exposure value: accounting value (LEX30.3); non-SFT counterparty credit risk = SA-CCR EAD (LEX30.4); SFTs: comprehensive approach with supervisory haircuts (LEX30.5); off-balance sheet: standardised credit risk CCFs with a 10% floor (LEX30.6).
- CRM: eligible as in the standardised approach (LEX30.7-30.9); maturity mismatch hedges only if original maturity at least one year and residual at least three months (LEX30.10); the exposure is reduced by the protected or collateralised amount (LEX30.13) and the same amount becomes an exposure to the protection provider (LEX30.14), except CDS where provider or reference is non-financial: the provider exposure is the SA-CCR EAD (LEX30.28).
- Trading book: added to banking book exposures (LEX30.15); exposure = gross JTD of MAR22.9-22.14 with LGD 100% and no risk weight (LEX30.17); no maturity scaling (LEX30.18); group = sum of positive net long JTDs (LEX30.19); offsets within the same issue (LEX30.22), across issues only if the short is junior or of the same seniority (LEX30.23-30.26); credit derivative hedges substitute to the provider (LEX30.27); no banking/trading book netting (LEX30.29); a net short is not an exposure (LEX30.30).

### Corrections to the older sections of STAGE_K_SOURCES.md

Marked in place with "corrected 2026-11-19" (nothing deleted):
1. NMRF/SES row: SES aggregation is MAR33.16-33.17; MAR33.15 is the IMCC formula.
2. PLA row: the metrics are MAR32.34-32.41 and the zones MAR32.42 (Table 2); MAR32.33 is the HPL alignment rule.
3. Backtesting row: backtesting is MAR32.4-32.19 (desk level MAR32.16-32.19); MAR32.20-32.33 is PLA. MAR32.9 Table 1 and MAR99 Table 2 print the multiplier itself (1.50 to 2.00); the plus of 0 to 0.5 is stated in MAR33.42(2).
4. FRTB SA row: MAR22 ends at MAR22.45 and MAR23 at MAR23.8. MAR99 has no SBM or DRC illustrations.
5. BA-CVA row: BA-CVA is MAR50.13-50.26 (MAR50.12 is the IRB maturity cap).
6. SA-CVA row: m_CVA is 1 (MAR50.41), not 1.25; the supervisor may require more.
7. xVA row: MPoR floors are CRE53.24-53.26; CRE53.20-53.21 are effective maturity and CRE53.22-53.23 margin modelling. Stressed exposure is CRE53.7 and CRE53.51.
8. MAR99 section: "CRE99 not read" is superseded: CRE99.20-99.97 (SA-CCR examples) read on 2026-11-19, values agree with BCBS 279.
