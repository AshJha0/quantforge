# Stage K wave 2: outside-check gate per item (plan section 15)

Written 2026-11-19 by the wave 2 spec lane, before any implementation or run. Rule (plan 15): every item needs a source actually read, an acceptance test fixed before the run, and outside checks on at least 60% of its value cases, or it moves to a point release. Sources: all read 2026-11-19 from the Basel Framework PDF of 11/11/2026 (`program/STAGE_K_SOURCES_W2.md`). Acceptance: written in each spec, to be frozen when the coordinator confirms the spec. This file counts the third condition.

## How a case is counted (ruling KR-68)

- **P**: the expected output is a number printed in a read source (paragraph and page cited in the spec).
- **L**: the expected output is computed from the inputs by an independent library (SciPy 1.17.1; values measured 2026-11-19 in a scratch folder and quoted in the spec).
- **B**: re-derived by a blind lane under DR-H2. What DR-H2 requires (from `program/STAGE_H_BLIND_LANE.md`): a separate session, a different model where available, never this lane's context, working outside the repo; it receives only the spec text with every expected value, derivation and worked-example number removed by a script, the rulings files, and the cited source documents for meaning; it writes its own small reference with no repo imports, freezes `blind_results.json` with its hash before any comparison; a script compares; a mismatch is investigated and never "fixed" by rerunning the blind lane; any value that leaked into the prose it received makes that case NOT BLIND. **No B count below is claimed: no blind lane has run.** B appears only as "candidates".
- **T**: the output is a lookup in a printed table. Not counted in the strict share; shown separately.
- A hand case checked only by our own second implementation (another build, or the oracle) counts as none.

Leak warning for the blind packet: the specs' "Worked example" sections print values of these cases, so the stripping script must remove those sections too, or the cases are NOT BLIND: drc_k-0007, 0008, 0010; es_k-0002, 0003; ses_k-0001; cap_k-0002; cva_k-0001, 0004; sacva_k-0001, 0002, 0004; lev_k-0004, 0005, 0010, 0011; lex_k-0004; pla_k-0001.

## Gate table

| Item | Spec | Value cases | P | L | P or L (strict) | Strict share | T (not counted) | B candidates | Needed for 60% | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| K-8a FRTB DRC and RRAO | `06-risk/frtb-drc-rrao.md` | 18 | 2 | 0 | 2 | 11% | 0 | 16 | 11 | **Moves to a point release unless** a DR-H2 blind lane re-derives and matches at least 9 of the 16 hand cases |
| K-8f IMA ES/LH, stressed ES, IMCC, SES, RFET, PLA, capital | `06-risk/frtb-ima.md` | 33 | 4 | 10 | 12 | 36% | 6 (55% with T) | 15 | 20 | **Moves to a point release unless** a DR-H2 blind lane matches at least 8 of the 15 hand cases |
| K-8g BA-CVA and SA-CVA | `06-risk/cva-capital.md` | 16 | 0 | 2 | 2 | 12.5% | 0 | 14 | 10 | **Moves to a point release unless** a DR-H2 blind lane matches at least 8 of the 14 hand cases, or the ORE lane finds ORE BA-CVA/SA-CVA example outputs that map onto these inputs (unverified that they exist) |
| K-8i leverage ratio and large exposures (simplified) | `06-risk/leverage-large-exposures.md` | 18 | 5 | 0 | 5 | 28% | 0 | 13 | 11 | **Moves to a point release unless** a DR-H2 blind lane matches at least 6 of the 13 hand cases |

Totals: 85 value cases, 21 strict outside-checked (25%), 6 table lookups, 58 blind candidates.

Plain reading: **no wave 2 item can meet 60% from published examples and independent libraries alone.** The Basel texts print very few worked numbers for these chapters (MAR99 has backtesting tables only; MAR22 has two small illustrations; MAR33 two liquidity-horizon examples; MAR50 none; LEV one footnote example; LEX none). Every item depends on a DR-H2 blind lane. The hand cases are small (each fits on a few lines), so one blind session can cover all four items; recommended before any build lane freezes goldens.

What was not done to raise the shares, on purpose: adding further SciPy-checkable PLA or normal-ES cases (each would be honest, but they would test the same few lines of code and inflate K-8f's share without testing more of the item), and counting the T lookups (they test that a table was copied, which the JSON table and a build test against it already cover).

Where the printed source and our computation differ slightly, the difference is recorded and the tolerance fixed now: the MAR32.42 KS p-value printed as 0.264 is 0.26338 by the asymptotic Kolmogorov tail (tolerance 1e-3); CRE99 EADs are rounded (tolerance 1.0 on 569.8 vs 569, 5,405.4 vs 5,406, 936.6 vs 936).

## Per item: which cases have which check

- K-8a: P = drc_k-0003 (MAR22.16 FAQ, net 0), ctp_k-0001 (MAR22.45, 50). drc_k-0002 and drc_k-0004 use factors printed in the text (one-half, one quarter) but the DRC values are ours: counted B candidates, not P.
- K-8f: P = pla_k-0007, pla_k-0008 (MAR32.42 p-values), lh_k-0001 (FAQ4: 40), lh_k-0002 (FAQ5: 20). L = pla_k-0001 to 0008 (SciPy `spearmanr`, `ks_2samp`, `kstwobign`), es_k-0001, 0002 (SciPy `quad` of the normal tail). T = rfet_k-0005 to 0008, lh_k-0003, 0004. B candidates: es_k-0003 to 0005, est_k-0001, 0002, imcc_k-0001, ses_k-0001, 0002, cap_k-0001 to 0003, rfet_k-0001 to 0004.
- K-8g: L = df_k-0001, 0002 (SciPy `quad` of the time-averaged discount factor, the definition in MAR50 footnote 357). B candidates: cva_k-0001 to 0006, sacva_k-0001 to 0008. The START file's idea that "SA-CVA reuses SBM aggregation tests" does not give an outside check: those tests check our own code, and MAR50.53 differs from MAR21.4 (always-clipped S_b, the R hedge term, m_CVA, no correlation scenarios).
- K-8i: P = lev_k-0001 to 0003 (CRE99 EADs, valid because multiplier 1 in both formulas), lev_k-0004, 0005 (LEV30.31 footnote 384). B candidates: lev_k-0006 to 0011, lex_k-0001 to 0007.

## SIMM (K-8h) on placeholder weights: what can honestly be outside-checked

Not specified in this lane. The owner decided SIMM runs on placeholder weights, labelled (K-QE, 2026-11-18). What that leaves open to an outside check:

- **Published numbers: none.** ISDA's SIMM unit tests and CRIF test portfolios go to licensees only (STAGE_K_SOURCES, 2026-11-15; the methodology PDF itself was not read in this lane and stays R). Even if the methodology prints example values, they are computed with the real (licensed) weights, so a placeholder-weight build cannot reproduce them.
- **Independent library: none known to be usable.** SciPy has nothing for SIMM. An open-source SIMM implementation (ORE ships one, recalled and unverified) could be run with our placeholder weights only if its parameter tables can be replaced from outside; whether that is possible, and whether its bundled ISDA parameters carry licence terms, is unverified. If both are confirmed, structure and aggregation cases computed by that implementation with our placeholder weights would count as L.
- **What hand cases can check**: the structure and the algebra, not the calibration. Weighted sensitivities, concentration thresholds and factors, the within-bucket root `sqrt(sum WS^2 + sum rho f WS WS)`, cross-bucket `S_b` clipping, the class aggregation with the psi matrix across risk classes, delta plus vega plus curvature per class, the curvature scaling and the lambda term, the product-class sum and the add-on. Each can be written as arithmetic a second person can check, as done for SA-CVA here.
- **Can it reach 60%?** Only through B (a DR-H2 blind lane re-deriving the hand cases from the spec with the placeholder table in hand) or through the ORE route above if it is confirmed. From published sources and libraries alone the share is 0%. With a blind lane covering at least 60% of the value cases it can pass the gate as written, but the result says only "the algebra matches a blind re-derivation on placeholder weights"; it says nothing about agreement with ISDA SIMM numbers, and the docs must say so. Without a blind lane SIMM moves to a point release, which the owner's K-QE answer already anticipates.

xVA extras (K-8b) are not counted here; their outside check is ORE example outputs (STAGE_K_START), for the ORE lane to confirm.

## For the coordinator to decide

1. Whether to run one DR-H2 blind lane over the 58 wave 2 candidates (recommended; without it all four items move to a point release under the gate rule).
2. Whether to accept KR-68's exclusion of table lookups (T). Counting them would change only K-8f (36% to 55%), still below 60%.
3. Confirm the rulings KR-50 to KR-69 (all PROPOSED), in particular KR-56 (boundary equality in PLA is amber), KR-58 (text over image for the ratio floor) and KR-62 (floor under the SA-CVA roots, a ruling not in the text).
