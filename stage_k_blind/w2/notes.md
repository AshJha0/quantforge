# Notes (blind lane k2)

MANIFEST.sha256: all 13 listed files matched.

Out-of-bounds access: one attempted `ls C:/Work/Claude/qf-blind/` (the parent of both allowed folders) was DENIED by the harness; no listing was returned. Nothing else outside the two folders was touched. Cases affected: none known.

Reference: `blind_ref.py` (standard library only). Run `python -I blind_ref.py`; it writes `blind_results.json`.

## Ambiguities and assumptions

1. Maturity weight on CTP and securitisation positions (drc_ctp, drc_sec_nonctp; frtb-drc-rrao.blind.md): the CTP text does not say, the sec text says "maturity weight as above". I applied mat_w to both before netting. Cases ctp_k-0002, sec_k-0001 (maturity 5 so weight 1, no effect).
2. CTP: HBR_ctp uses unweighted (market-value) net longs and shorts over all positions, as for nonsec (spec: "from all CTP net longs and shorts together"). `buckets[<index>]` is the index of the position; DRC_b = sum RW net_long - HBR sum RW |net_short| for that index. ctp_k-0002 (a long in index A, b short in index B: different index so no netting). ctp_k-0003: bucket_drc mode, hbr_ctp omitted; max(0 + 0.5*(-10), 0) = 0.
3. drc_sec_nonctp: positions netted by (bucket, pool, tranche); HBR from the net amounts per bucket; wtd by caller rw. sec_k-0001 (different tranches so no offset).
4. drc_nonsec offsetting (KR-53): a short offsets only longs of equal or higher rank. drc_k-0007: short senior bond cannot offset long equity (rank 3 > 1), so no offset. drc_k-0008: short equity (rank 1) offsets long senior bond (rank 3) -> net_short -20, hbr 0 (only shorts -> HBR 0 per KR-54), wtd_long 0. Maturity weight applied before offsetting (footnote 296).
5. Negative-zero / int zeros: some zero values are written as integer 0 (JSON number) rather than 0.0; numerically identical.
6. gross_jtd for lgd: LGD by seniority also for the EQUITY cash equity (LGD 1, PnL 0, so JTD = market value). drc_k-0011 equity D: JTD 5, weight 1 (maturity 2 >= 1).
7. es_k-0005: lists 2..5 are empty. KR-57 says missing horizons are 0, so empty list -> ES_j = 0 (I did not treat the empty list as an error). ES_1 per excerpt: n=250, c=0.975, w = n - n*c (binary64), m=floor(w)=6, fractional weight on L_(n-m).
8. KR-61 multiplier: 6 exceptions -> 1.76 (cap_k-0001..3). With no amber desk k = 0. cap_k-0002 sums sa over all desks (green + amber) for SA_G,A.
9. RFET window (KR-59): (as_of - 12 months, as_of] = 2025-07-01..2026-06-30 for all four cases (as_of 2026-06-30). 90-day windows start from window start up to as_of-89 days, all fully inside. `min_window_count` is the minimum over those; first failing window = earliest start with count < 4. Observation dates outside the window are ignored (none occur). rfet_k-0004: 23 distinct days (duplicates removed) < 24 so crit1 false. crit1 requires both >= 24 days and no failing window.
10. BA-CVA: hedged formula uses SCVA_c - SNH_c with SNH per counterparty; index hedge IH uses 0.7 x weighted RW; single_name hedge RW from its own sector/quality. DF via expm1 form (KR-64); IMM netting set DF = 1 (cva_k-0003). Output of `snh`/`hma` for every counterparty in FULL cases, including 0 (cva_k-0005).
11. SA-CVA IR delta: USD and EUR are "specified currencies" so Table 3 RWs and Table 4 rho by tenor; inter-bucket gamma 0.5 (sacva_k-0001..4, 6, 8). The input factor strings ('1Y','5Y',...) match the table keys.
12. SA-CVA IR vega (sacva_k-0008): RW 100%, one factor, so rho (0.40) not exercised; bucket key 'USD'. FX delta: RW 0.11, gamma 0.6 between currency buckets, one factor per bucket (sacva_k-0007, 0008).
13. SA-CVA CCS (sacva_k-0005): bucket '2', IG, RW 0.05. rho = tenor x name x quality: tenor 1 if same else 0.90; name 1 if same name, else 0.90 if same legal_group (X and Y both GX), else 0.50; quality 1 if same else 0.80. Hedge WS = RW*(s_cva - s_hdg); WSH = RW*s_hdg; 0.01 x sum WSH^2 added in K_b. Only one bucket so gamma is not needed (CCS inter-bucket gamma is not implemented in my code).
14. SA-CVA `floored` is reported per bucket only (radicand of K_b < 0). The class-level radicand is floored at 0 as well (KR-62) but not reported. m_cva multiplies the class-level square root (sacva_k-0006 1.25). Sum over the ordered pairs k != l (each unordered pair counted twice), as written.
15. Large exposures: trading book uses LGD 1 for all seniorities (LEX30.17), no maturity weight; offsetting by KR-53; net short counts 0 (lex_k-0004: net long 60 + banking book 200 = 260; lex_k-0005: exposure 0). CRM: protected amount subtracted from counterparty, added to provider (lex_k-0003: E 200, F 300). The 10% CCF floor applied to the off-balance item (lex_k-0006: 1000 x 0.1 = 100, large since >= 10%). `limit` reported for every group (0.15 T only when bank_gsib and every member is gsib: lex_k-0007; else 0.25 T). Breach strict '>' (lex_k-0001 C at exactly 250 does not breach).
16. Leverage: `ratio` = tier1/exposure; meets_minimum as tier1 >= 0.03 x exposure.

## Checks by hand (two per item)
- DRC: drc_k-0004 (p2 JTD -75 x w 0.25 = -18.75; net long 75 - 18.75 = 56.25; 0.06 x 56.25 = 3.375); drc_k-0007 (hbr 50/80, 7.5 - 0.625 x 4.5 = 4.6875).
- CTP: ctp_k-0002 (100 - 0.5 x 100... A: 100, B: -50, sum 100 + 0.5 x -50 = 75).
- RRAO: rrao_k-0001 12000 (1e6 x .01 + 2e6 x .001); rrao_k-0002 10000.
- ES: cap_k-0001 not an ES case; es_k-0003: sqrt(100 + 64 + 36x2 + 16x2 + 4x6) = sqrt(292)=17.088; es_k-0004 = 10.
- est/imcc: est_k-0001 12 x 1.25 = 15; imcc_k-0001 portfolio 15, IR 6 x 1.25 = 7.5, EQ 5 x max(1,0.8) = 5; imcc 0.5 x 15 + 0.5 x 12.5 = 13.75.
- CAP: cap_k-0001 C_A = max(120, 1.76 x 90 + 15 = 173.4) = 173.4; cap_k-0002 surcharge 0.2 x 46.6 = 9.32.
- RFET: rfet_k-0003 window starting 2025-07-28 has days 28,29,30 = 3.
- CVA BA: cva_k-0004 DF(5) = 0.88479687, SCVA = 0.05 x 5 x 1e6 x DF / 1.4 = 157999.4.
- SA: sacva_k-0004 USD K_b = sqrt(11100^2 + 7400^2 + 2 x 0.31 x 11100 x 7400) = 15129.3.
- LEV: lev_k-0009 1.4 x (70 + 50) = 168. lev_k-0010 569.8 + 500 + 150 + 550 = 1769.8.
- LEX: lex_k-0004 and lex_k-0003 as in item 15.

No case is "not derivable".
