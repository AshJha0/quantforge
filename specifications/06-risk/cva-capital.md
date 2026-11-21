# CVA risk capital: BA-CVA (reduced and full) and SA-CVA

Spec version 0.1.0. Status: implemented in all four builds (Python `python/quantforge_core/cva.py`; Java, C++ and Rust ports per `program/STAGE_K_W2A_HANDOVER.md` and `program/STAGE_K_W2B_HANDOVER.md`) on the wave 2 integration branch `k-r3-w2` (2026-11-20), merge into `k-v1` pending; goldens in `datasets/golden/stage_k/` (spec lane 2026-11-19). The rulings stay PROPOSED except those confirmed in `stage-k-rulings-w2.md` (KR-312, KR-315, KR-319, KR-320, KR-324, KR-327, confirmed 2026-11-20). Rulings `stage-k-rulings-w2.md` KR-50, KR-62 to KR-64, KR-67 to KR-69. Parameters `specifications/tables/stage_k/mar50_cva.json`. Gate status: `program/STAGE_K_W2_GATE.md`.

Every output carries `label`: "regulatory formula on caller inputs; not a regulatory return" (KR-69).

**Plain idea.** CVA is the price discount a bank books because a derivatives counterparty might default. When that counterparty's credit spread widens, the CVA grows and the bank loses money even though nobody has defaulted; most of the 2008 counterparty losses came this way. The capital charge for this risk comes in two recipes. The basic one (BA-CVA) needs only each netting set's exposure and maturity and a risk weight by sector and rating, then adds counterparties as if their spreads shared one common factor with correlation 50%. The standardised one (SA-CVA) works like the market-risk sensitivities method: the bank computes how its CVA moves with interest rates, FX, spreads, equities and commodities, weights the sensitivities, and aggregates them, with hedges netted but never allowed to cancel risk perfectly.

## Sources

| Ref | Source | Evidence class | Used for |
|---|---|---|---|
| [MAR50] | Basel Framework MAR50, effective 1 January 2023 (July 2020 targeted revisions), consolidated PDF of 11/11/2026, pp. 722-750 | read 2026-11-19 (formulas from images pp. 726, 728-730, 737-738, 743) | every rule and parameter |
| [MAR21] | MAR21.4, pp. 570-571 | read 2026-11-19 | the aggregation SA-CVA departs from (MAR50.53(2)) |
| [CRE53] | CRE53.20-53.21, p. 467 | read 2026-11-19 | effective maturity for IMM banks (no five-year cap here) |
| [CRE99] | SA-CCR examples, pp. 524-540 | read 2026-11-19 | EAD inputs for an illustrative BA-CVA chain (not a check) |
| [SciPy] | SciPy 1.17.1 `integrate.quad` | measured 2026-11-19 | DF as the time average of exp(-0.05 t) (footnote 357's own definition) |
| [ORE] | Open Source Risk Engine (Modified BSD, `license.txt` at tag 1.8.17.0, as recorded in `oracle/LICENCES.md`; evidence class: read) | recalled, UNVERIFIED: whether ORE ships BA-CVA or SA-CVA example inputs and outputs was not checked in this lane | possible independent check, to be confirmed by the ORE lane (K-8b) |

## Formal statement

### `risk.cva.ba`

Inputs (KR-64): `counterparties` [{id, sector, quality, netting_sets [{ead >= 0, m > 0, imm}]}], `version` (`REDUCED` or `FULL`), and for `FULL`: `single_name_hedges` [{counterparty, relation, sector, quality, m, notional}], `index_hedges` [{m, notional, constituents [{sector, quality, weight}]}].

- `DF(m) = 1` if `imm`, else `-expm1(-0.05 m) / (0.05 m)` (MAR50.15(4), footnote 357; KR-64).
- `SCVA_c = (1/1.4) RW_c sum_NS m_NS ead_NS DF_NS` (MAR50.15), RW from MAR50.16 Table 1.
- `K_reduced = sqrt((0.5 sum_c SCVA_c)^2 + 0.75 sum_c SCVA_c^2)` (MAR50.14).
- `SNH_c = sum_h r_hc RW_h m_h notional_h DF(m_h)`, r_hc = 1, 0.8, 0.5 for `DIRECT`, `LEGAL`, `SECTOR_REGION` (MAR50.23, MAR50.26).
- `IH = sum_i RW_i m_i notional_i DF(m_i)`, `RW_i = 0.7 x sum_k weight_k RW(sector_k, quality_k)` (MAR50.24).
- `HMA_c = sum_h (1 - r_hc^2) (RW_h m_h notional_h DF(m_h))^2` (MAR50.25).
- `K_hedged = sqrt((0.5 sum_c (SCVA_c - SNH_c) - IH)^2 + 0.75 sum_c (SCVA_c - SNH_c)^2 + sum_c HMA_c)` (MAR50.21).
- `K_full = 0.25 K_reduced + 0.75 K_hedged` (MAR50.20).
- Capital = `0.65 K_reduced` (`REDUCED`) or `0.65 K_full` (`FULL`) (MAR50.14, MAR50.20).

Outputs: per counterparty `scva`, `snh`, `hma`; `ih`; `k_reduced`; `k_hedged` and `k_full` for `FULL`; `capital`; `rwa = 12.5 x capital` (MAR50.1).

### `risk.cva.sa`

Inputs (KR-63): `classes`, a map from (`IR`, `FX`, `CCS`, `RCS`, `EQ`, `COM`) x (`DELTA`, `VEGA`) to sensitivity lists `[{bucket, factor, s_cva, s_hdg}]` (`CCS` delta only, MAR50.45), plus `m_cva` (default 1), `reporting_currency`.

Per class and kind (MAR50.51-50.53, KR-62):
- `WS_k = RW_k s_cva_k - RW_k s_hdg_k`; `WSH_k = RW_k s_hdg_k`.
- `K_b = sqrt(max(0, sum WS_k^2 + sum_{k != l} rho_kl WS_k WS_l + 0.01 sum WSH_k^2))`.
- `S_b = max(-K_b, min(sum_{k in b} WS_k, K_b))`.
- `K = m_cva sqrt(max(0, sum_b K_b^2 + sum_{b != c} gamma_bc S_b S_c))`.

Total SA-CVA = sum over the delta and vega capital of every class (MAR50.42-50.45). Risk weights, rho and gamma per MAR50.54-50.77 as tabulated in `mar50_cva.json`: IR specified currencies Table 3/4, other currencies 1.58% and 40%, gamma 0.5; FX 11%, gamma 0.6; CCS Table 7 RW, rho = rho_tenor x rho_name x rho_quality, gamma Table 6 (buckets 1 to 7: rho_name is 1 for the same `name`, 0.90 for different names with the same `legal_group`, 0.50 otherwise; sacva_k-0005: X and Y share a legal group, so rho(X 5Y, Y 5Y) = 0.90 and rho(X 1Y, Y 5Y) = 0.81; inferred from the expected values; blind lane note, stage_k_blind/w2/notes.md); RCS Table 10 RW, gamma Table 9 (halved across quality); EQ Table 12 RW, gamma per MAR50.71; COM Table 14 RW, gamma per MAR50.75; all vega RW 100% except equity large cap 78% (KR-315: buckets 1 to 8 and 12; Table 11 prints size "Large" for 1 to 8 and "Large cap, advanced economies" for the index bucket 12, evidence class read; that MAR50.73(3)'s "large market capitalisation buckets" covers bucket 12 is inferred, since the paragraph lists no buckets). CCS buckets `1a` and `1b` select the Table 7 risk weight only and are aggregated as one bucket `1` (KR-312; read: Table 5 prints one bucket 1 with sub-sectors a) and b), and Table 6 has one row and column for bucket 1).

Outputs: per class and kind `buckets` [{bucket, k_b, s_b, sum_ws, floored}], `k`; `total`; `rwa`. `floored` is a per-bucket flag, true when that bucket's `K_b` radicand was negative and set to 0; the class-level radicand under `K` is floored at 0 as well (KR-62) but carries no flag. No golden case has a negative radicand, so no expected value exercises either floor.

## Worked examples (written out)

**One counterparty, reduced (cva_k-0001).** Financial, investment grade: RW 5%. One netting set, EAD 1,000,000, M 5 years, not IMM. DF = (1 - e^{-0.25}) / 0.25 = 0.8847968677143805. SCVA = (1/1.4) x 0.05 x 5 x 1,000,000 x 0.8847968677143805 = 178,571.4286 x 0.8848 = 157,999.44066328226. With one counterparty, K_reduced = sqrt(0.25 S^2 + 0.75 S^2) = S, so capital = 0.65 x 157,999.44 = 102,699.63643113348. The single-counterparty case is a useful check: the correlation split must add back to the whole.

**Direct hedge, full (cva_k-0004).** Add a CDS bought on the same name, notional 500,000, 5 years: SNH = 1 x 0.05 x 5 x 500,000 x 0.8848 = 110,599.60846429756; HMA = 0 (r = 1). K_hedged = sqrt(0.25 (S - SNH)^2 + 0.75 (S - SNH)^2) = S - SNH = 47,399.8321989847. K_full = 0.25 x 157,999.44 + 0.75 x 47,399.83 = 75,049.73431505909; capital 48,782.32730478841. Even a perfect single-name hedge keeps a quarter of the unhedged charge (beta).

**SA-CVA interest rate delta (sacva_k-0002).** USD (a specified currency). CVA sensitivities: 1Y +1,000,000, 5Y -2,000,000; hedge sensitivity at 5Y -1,500,000. RW 1.11% at 1Y and 0.74% at 5Y; rho(1Y, 5Y) = 72%. WS_1Y = 11,100; WS_5Y = 0.0074 x (-2,000,000) - 0.0074 x (-1,500,000) = -14,800 + 11,100 = -3,700. Hedge term 0.01 x 11,100^2 = 1,232,100. K_b^2 = 11,100^2 + 3,700^2 + 2 x 0.72 x 11,100 x (-3,700) + 1,232,100 = 123,210,000 + 13,690,000 - 59,140,800 + 1,232,100 = 78,991,300; K_b = 8,887.704990603592. Without the hedge (sacva_k-0001) K_b = 10,280.408552192855; the hedge cuts the charge, and the R term keeps a floor under a perfect hedge.

**Clipping (sacva_k-0004).** USD 1Y and 30Y sensitivities of +1,000,000 each: WS 11,100 and 7,400, rho 31%; K_b = sqrt(11,100^2 + 7,400^2 + 2 x 0.31 x 11,100 x 7,400) = 15,129.335742193045 while the sum of WS is 18,500, so S_b is clipped to 15,129.34 (MAR50.53(3)). With an EUR bucket of K = S = 22,200: K = sqrt(15,129.34^2 + 22,200^2 + 2 x 0.5 x 15,129.34 x 22,200) = 32,520.8864189875. Under MAR21.4 the unclipped sum would have been used first, giving 33,651.698322670134; the difference is the point of this case.

## Errors (order KR-67 = HR-122)

`E_SCHEMA`: missing field, wrong type, unlisted enum (`sector`, `quality`, `relation`, `version`, class, kind, tenor). `E_LIMIT`: more than 100,000 counterparties, netting sets or sensitivities. Finite rule: `E_DOMAIN`. Structural `E_INPUT`: hedge referencing an unknown counterparty; hedges given with `REDUCED`; `CCS` with `VEGA`; duplicate (bucket, factor); a sensitivity in a bucket of the wrong class; reporting currency used as an FX bucket. `E_DOMAIN`: `ead < 0`; `m <= 0`; `notional < 0`; index weights not summing to 1 within 1e-12; `m_cva < 1`.

## Golden cases (designed 2026-11-19; not yet frozen)

| Case | Input | Expected | Arithmetic | Outside check |
|---|---|---|---|---|
| cva_k-0001 | worked example | scva 157999.44066328226; k_reduced = scva; capital 102699.63643113348 | above | B |
| cva_k-0002 | cva_k-0001 plus C2 sovereign HY (RW 2%): NS (500,000, 1), (2,000,000, 10) | scva2 231806.8480926789; k_reduced 311465.7513160206; capital 202452.7383554134 | DF(1) 0.9754115099857197, DF(10) 0.7869386805747332; (0.02/1.4)(487,705.75 + 15,738,773.61); sqrt((0.5 x 389,806.29)^2 + 0.75 (S1^2 + S2^2)) | B |
| cva_k-0003 | industrials IG (3%), NS (1,000,000, 2.5, imm) | scva 53571.42857142857; capital 34821.42857142857 | DF 1; 0.03 x 2.5 x 1e6 / 1.4 | B |
| cva_k-0004 | worked example (direct hedge) | snh 110599.60846429756; k_hedged 47399.8321989847; k_full 75049.73431505909; capital 48782.32730478841 | above | B |
| cva_k-0005 | cva_k-0002 counterparties, FULL, index hedge all financial IG, m 5, notional 1,000,000 | ih 154839.45185001657; k_hedged 246229.11690822538; k_full 262538.2755101742; capital 170649.87908161324 | RW_i 0.7 x 0.05 = 0.035; IH = 0.035 x 5 x 1e6 x DF(5) | B |
| cva_k-0006 | cva_k-0001, FULL, hedge SECTOR_REGION, financial IG, m 5, notional 500,000 | snh 55299.80423214878; hma 9174205044.341942; k_hedged 140432.9746442371; k_full 144824.5911489984; capital 94135.98424684897 | x = 110,599.61; SNH = 0.5 x; HMA = 0.75 x^2 | B |
| df_k-0001 | DF(5) | 0.8847968677143805 | | **L** (`quad`: 0.8847968677143806) |
| df_k-0002 | DF(0.1) | 0.9975041614635374 | expm1 form; the naive form gives ...358 | **L** (`quad`: 0.9975041614635374) |
| sacva_k-0001 | IR USD delta 1Y +1e6, 5Y -2e6 | k_b 10280.408552192855; s_b -3700; k 10280.408552192855 | 11,100^2 + 14,800^2 - 2 x 0.72 x 11,100 x 14,800 = 105,686,800 | B |
| sacva_k-0002 | worked example (hedge) | k_b 8887.704990603592 | above | B |
| sacva_k-0003 | sacva_k-0001 plus EUR 10Y +3e6 | k 22724.14574852045 | 105,686,800 + 22,200^2 + 2 x 0.5 x (-3,700) x 22,200 | B |
| sacva_k-0004 | worked example (clipping) | k_b 15129.335742193045; s_b clipped; k 32520.8864189875 | above | B |
| sacva_k-0005 | CCS bucket 2: X IG 1Y s_cva 1e5; X IG 5Y s_cva 1e5; Y (legal group of X) IG 5Y s_hdg 8e4 | k_b 6539.113089708726; s_b 6000 | WS 5,000, 5,000, -4,000; rho 0.9, 0.81, 0.9; K^2 = 66e6 + 2(22.5e6 - 16.2e6 - 18e6) + 0.16e6 = 42.76e6 | B |
| sacva_k-0006 | sacva_k-0001 with m_cva 1.25 | 12850.51069024107 | | B |
| sacva_k-0007 | FX delta (reporting USD): EUR s 2e5, JPY s -1e5 | k 17736.96704625681 | 22,000^2 + 11,000^2 - 2 x 0.6 x 22,000 x 11,000 = 314.6e6 | B |
| sacva_k-0008 | IR delta of 0001 + FX delta of 0007 + IR vega USD s 1000 | total 29017.375598449667 | 10,280.41 + 17,736.97 + 1,000 | B |

Error goldens: cva_ke-0001 `m` 0 (`E_DOMAIN`); cva_ke-0002 hedge with `REDUCED` (`E_INPUT`); cva_ke-0003 sector `SPACE` and `m` 0 at once (`E_SCHEMA`); sacva_ke-0001 `CCS` vega (`E_INPUT`); sacva_ke-0002 `m_cva` 0.9 (`E_DOMAIN`).

Value cases 16; printed (P) 0; library (L) 2 (DF only). Strict share 2/16 = 12.5%.

Illustration only, not a value case: with the CRE99 Example 1 EAD (569, USD thousands) as one netting set of a financial IG counterparty at M 5 the reduced capital is 0.65 x (0.05/1.4) x 5 x 569 x 0.8848 = 58.44 (58.436); the EAD input is published, the capital is not.

## Acceptance (fixed before any run; proposed, frozen on confirmation)

- A1 All value goldens in all four builds to 1e-12 relative.
- A2 Properties (10,000 random cases): with one counterparty and no hedges K_reduced = SCVA; K_full <= K_reduced is **not** asserted (an index hedge can raise K_hedged), but K_full >= 0.25 K_reduced always; with one counterparty, IH = 0 and only DIRECT hedges, K_hedged = |SCVA - SNH|; SA-CVA K_b >= 0.1 sqrt(sum WSH_k^2) (the R term) and S_b within [-K_b, K_b]; scaling every sensitivity by c scales every K by |c|.
- A3 Gate (plan 15): 60% of the 16 value cases outside-checked under KR-68. Strict share now 12.5%; K-8g moves to a point release unless a DR-H2 blind lane re-derives at least 8 B cases (2 + 8 = 10 of 16 = 62.5%), or the ORE lane confirms ORE example outputs for BA-CVA/SA-CVA that can be mapped onto these inputs (`program/STAGE_K_W2_GATE.md`). Measured 2026-11-20 after the DR-H2 blind lane (`program/STAGE_K_BLIND_W2.md`): 14 of 21 value cases of `cva_k`, `df_k`, `sacva_k` (66.7%), so the 60% gate is met (`oracle/OUTSIDE_SHARES.md`, generated by `tools/outside_shares.py`; evidence class measured).

## Limits

- No exposure model: EAD, M and every SA-CVA sensitivity are inputs. Regulatory CVA itself (MAR50.31-50.36: market-implied PDs, ELGD, simulated discounted exposure, MPoR floors 4 + N and 9 + N days) is out of K-8g and belongs with the xVA lane (K-8b).
- Eligibility of hedges (MAR50.17-50.19, MAR50.37-50.39) is the caller's; the operation applies the formulas to the hedges given.
- Qualified-index option of MAR50.50 (bucket 8 of CCS, buckets 16-17 of RCS, 12-13 of EQ) is supported only through the caller's bucket assignment; the 75% sector rule is the caller's.
- The materiality alternative of MAR50.9 (100% of CCR capital) and the netting-set carve-out of MAR50.8 are not modelled.
- KR-62 floors are a ruling; the text has none.
- CCS buckets `1a` and `1b` are one aggregation bucket (KR-312, read from Table 6); there is no gamma between them because the text prints none.
