# Stage K wave 2: blind re-derivation (DR-H2) of the 58 hand value cases

Written 2026-11-19 by the packet builder (Claude Opus 5.5, branch `k-w2-spec`). The packet builder is not the blind lane and ran no derivation beyond rechecking the specs' own arithmetic. Process: `program/STAGE_H_BLIND_LANE.md` (DR-H2); record format of `STAGE_K_BLIND_W1.md` and `STAGE_K_BLIND_W1B.md` (branches `k-w1`, `k-w1b`). Scope: the 58 B candidates of `program/STAGE_K_W2_GATE.md` (K-8a 16, K-8f 15, K-8g 14, K-8i 13).

## Plain idea

A second model, which never sees our numbers, reads only the rules and computes the 58 cases itself. It freezes its answers with a hash before anyone compares. A script, fixed now, compares them with the specs' hand values. A case counts as outside-checked (class B, KR-68) only if it matches and nothing in what the lane read gave the answer away.

## What was built (evidence class: measured, 2026-11-19, local laptop, not the acceptance machine)

| File | Role | Side |
|---|---|---|
| `program/stage_h_blind_w2/k2_cases.py` | full inputs of the 58 cases (rows that say "as 0001 with ..." or "worked example" written out); input choices listed in `INPUT_CHOICES` | builds the packet |
| `program/stage_h_blind_w2/k2_make_packet.py` | writes the packet; never reads the expected file | builds the packet |
| `program/stage_h_blind_w2/k2_expected.json` | expected value per case and field, as printed in the specs (`src: spec`), one derived field (`src: builder`) | hidden |
| `program/stage_h_blind_w2/k2_recheck.py` | packet builder's recheck of every expected field from the inputs | hidden |
| `program/stage_h_blind_w2/k2_leaks.py` | leak check (model `paper2_leaks.py`) | hidden |
| `program/stage_h_blind_w2/k2_compare.py` | compare, with `--self-test` | hidden |

Packet: `C:/Work/Claude/qf-blind/k2_packet/` (outside every worktree; not committed). 21 files: README, the four specs stripped (`specs/*.blind.md`), the ES estimator excerpt that KR-57 points to, the rulings stripped, the nine parameter tables byte for byte, one inputs file per item, `output_template.json` (field definitions, units and a results skeleton with every field null), `MANIFEST.sha256`.

**Packet MANIFEST.sha256 file hash: `ebef66a754a84778a5bc8cc5cd2b7fa490cb48f3cee5e2df9f6327062e7eef1a`.** Built from commit `35563758` with `python -I program/stage_h_blind_w2/k2_make_packet.py . C:/Work/Claude/qf-blind/k2_packet`; a rebuild into a scratch folder gave the same manifest hash (reproducible). Before handing the packet over, the coordinator checks that `sha256sum MANIFEST.sha256` still gives this value.

What was stripped: from each spec the sections "Worked example(s)", "Golden cases" (which hold every expected value, the arithmetic columns, the error goldens and the illustration) and "Acceptance" (W1B lesson: an acceptance line named an output). Kept: header, plain idea, Sources, Formal statement (rules, formulas, input and output schemas), Errors, Limits. From the rulings: KR-56 (PLA only; prints p-values of PLA cases) and KR-68 (gate classes). KR-67, which states the numbers and tolerance rule, stays. From `var-es-and-backtests.md` only the units line, the order statistic rule and `risk.var.historical`; its history paragraph is cut.

## Fixed now, before any blind result exists

- **Compare mapping and tolerances: commit `35563758`** (`k2_compare.py`). Mapping: each expected field path is read from the blind case object at the same path as the packet skeleton; the self-test fills the real skeleton from `k2_expected.json` and fails if any of the 58 cases' paths is missing from it. Tolerance from KR-67 and every spec's Acceptance A1: `|blind - expected| <= max(1e-12 |expected|, 1e-15)`; booleans and ISO date strings exact; a boolean never equals a number. No case among the 58 has a per-case exception (the 1.0 and 1e-3 exceptions belong to lev_k-0001..0003 and pla_k-0007..0008, which are P cases and not in the packet).
- Representation rules R1 to R4 (top-level shape, one wrapper level such as `outputs`, a keyed list instead of a keyed object, a number as a decimal string) are written in the script so that the W1B run-1 failure (the script read the wrapper level and compared nothing) cannot recur; an unknown extra level is a SHAPE error with exit 2, never a pass.
- **Dry self-test on fabricated data: 13/13 PASS** (`python -I program/stage_h_blind_w2/k2_compare.py . --self-test`): exact values all MATCH; 1e-14 relative noise all MATCH; 1e-9 perturbation every numeric case MISMATCH; `outputs` wrapper, bare case map and case list all MATCH; an extra level above `cases` is SHAPE; two wrapper levels give no MATCH; the unfilled skeleton gives only MISSING; an absent case is MISSING; True for 1 and 1 for True MISMATCH; a decimal string and a keyed list MATCH; a wrong date and a wrong sign MISMATCH.

## Spec arithmetic recheck

`python -I program/stage_h_blind_w2/k2_recheck.py`: **every one of the 58 cases' fields reproduces** (169 fields, 0 DIFF at the KR-67 tolerance). The differences are in the last printed digit only, for example cva_k-0001 scva printed 157999.44066328226, recomputed 157999.44066328224; sec_k-0001 hbr printed with 15 digits (0.714285714285714) against 0.7142857142857143; cap_k-0002 surcharge 9.32 against 9.319999999999999. Inferred from the RFET recheck: the last 90-day window of rfet_k-0002 holds 5 dates, as the spec says. This recheck is our own second computation; it counts as no outside check.

## Leak check

`python -I program/stage_h_blind_w2/k2_leaks.py . C:/Work/Claude/qf-blind/k2_packet > C:/Work/Claude/qf-blind/k2_LEAKS.tsv`: **0 hard leaks** (exit 0; list file SHA-256 `4f5e4b1506d277f5376b2f10b0cd90cd747c5b6b762f8ff271e2c87a1e5cc4fb`, outside the packet). Searched: every expected number and date not equal to an input of its own case, as printed, signed, comma-grouped, rounded to 2 and 4 decimals when that keeps at least three significant digits, and as a percent for ratios, shares and hbr; 0 and 1 are not searched. Hits: 135 in parameter tables (PARAM, allowed; for example 1.76, the MAR32.9 multiplier of cap_k-0001 and 0002), 159 in some case's inputs (INPUT; coincidences such as 260 among the 250 P&L integers of es_k-0005), 81 LOWINFO (values of at most two significant digits: 3, 4, 5, 15, 20, 24, 0.2, 0.5, 100, 250, "50%" in rule prose, paragraph numbers and counts). No case id appears in any prose file. First run of the check found 3 hits, all from 2-decimal roundings of the two leverage ratios ("0.03", "0.02" in rule constants); those roundings carry one significant digit and are not "the printed digits", so the variant was restricted (script comment) and no packet file changed for it.

Not searchable by digits, stated so the coordinator knows the check says nothing about them: boolean fields (rfet crit flags, lex large and breach, meets_minimum, ratio_floored) and outputs equal to an input of the same case (es_k-0004 es 10, ses_k-0002 ses 10, rfet_k-0001 distinct_days 100). Their protection is the section stripping alone.

## Cases that cannot count, fixed now

| Case | Why | Effect |
|---|---|---|
| rrao_k-0003 | The stripped rules text states the answer: `risk.frtb.rrao` says "Empty list gives 0", and the input is the empty list. | Compared, never counted (`NOT_COUNTED` in `k2_compare.py`). |

Fields that are implied but do not disqualify their case (the case counts on its other fields; all fields must still match for MATCH):
- cap_k-0001 and cap_k-0002 `m_c` = 1.76: a lookup of the MAR32.9 table in `mar32_pla.json` (T, KR-68). `c_a` and the later intermediates are computed.
- drc_k-0008 `hbr` 0 and `drc` 0 follow from KR-54 ("a bucket with only shorts has HBR 0 and DRC 0") once the obligor is net short; `net_short` -20 needs the KR-53 offset and is the field that tests the case.

**Eligible cases per item: K-8a 15 of 16, K-8f 15 of 15, K-8g 14 of 14, K-8i 13 of 13 (57 of 58).** Gate needs (unchanged, `STAGE_K_W2_GATE.md`): K-8a 9, K-8f 8, K-8g 8, K-8i 6 blind matches.

## Input choices (the spec rows left these open; none changes a printed value)

From `k2_cases.INPUT_CHOICES`: bucket CORPORATE where none is named (X and Y of drc_k-0005, 0006 in the same bucket, as hbr 0.5 requires); cash equity written as notional = market value with `cash_equity: true`; ctp_k-0002 series S1, tranche T1; cap_k-0001 completed with drc 0, one GREEN desk SA 200, c_u 0, sa_all 1000 (only `m_c`, `c_a` compared); rfet_k-0004 dates listed twice adjacently; the EUR bucket of sacva_k-0003, 0004 is IR delta EUR 10Y 3,000,000 (WS 22,200 as printed); sacva_k-0005 names X, Y in legal group GX; IR vega factor `IR_VOL`; Tier 1 100 for lev_k-0006..0009 and 1000 for lex cases where unstated; `bank_gsib` input added for lex_k-0007 (KR-66 says "both flagged G-SIB" but names no field for the bank).

## Departure from DR-H2 as written, stated

DR-H2 allows the blind lane the cited source documents for meaning. This packet gives none (the Basel PDF is a 1,429-page local file that is not committed), and the README forbids reading anything outside the packet, as the coordinator's brief asks. The rules text plus tables is meant to be complete; any gap the lane hits goes in its `notes.md` and is ruled before the compare, as in wave 1 (KR-12 to KR-14).

## Procedure

1. Coordinator: check the manifest hash above; hand the folder `C:/Work/Claude/qf-blind/k2_packet/` to a separate session on a different model from the spec lane (the spec lane commits 2a92f2cd, 49338627, 4d2512b2 carry the trailer Claude Opus 5.5, and this builder is also Claude Opus 5.5, so the blind lane must be another model, for example Claude Sonnet as in W1B). The lane works in its own folder next to the packet, for example `C:/Work/Claude/qf-blind/k2_blind/`, and is given no repository path.
2. Blind lane, per the packet README: own reference (`blind_ref.py`, no repository imports), `notes.md` with every ambiguity and assumption, `blind_results.json` filled from the skeleton at full binary64 precision, then `blind_results.sha256` written and the hash reported first in its hand-back, before it sees anything else.
3. Coordinator: commit and push the frozen `blind_results.json` and its hash (copy into `stage_k_blind/w2/` with `notes.md` and `blind_ref.py`) **before** running the compare. Rule any gap from `notes.md` that the specs left open, before the compare, as a numbered ruling; a gap-decided field is compared but not counted.
4. Run `python -I program/stage_h_blind_w2/k2_compare.py . <frozen blind_results.json> > stage_k_blind/w2/compare_output.txt`. One run. A mismatch is investigated, never fixed by rerunning the blind lane; if the spec was wrong the spec value is corrected with the reason; if the lane was wrong its error is recorded.
5. Fill the results section below; update the shares in `STAGE_K_W2_GATE.md` and each spec's gate line (coordinator).

## Results (run of 2026-11-19, the first and only compare run)

- Deriver: a different model from the spec lane (Sonnet 5.5; the specs and the packet were written by Opus 5.5), given only the packet folder and its own results folder. It reports one attempted directory listing of the parent folder `qf-blind/`, which was denied and returned nothing; no other access outside the two folders. Evidence class for that statement: the deriver's own report, not independently logged.
- Blind results as received: `stage_k_blind/w2/` (script, results, notes, hash), committed in d2274256 before the compare was run. SHA-256 of `blind_results.json`: `86a797bca1afed321e9f21340ac14a361490b64fe83d126b08a9abe4666cfb1e` (recomputed by the coordinator before the commit; equal to the deriver's `results.sha256`).
- Compare: `python -I program/stage_h_blind_w2/k2_compare.py . <blind_results.json>` with the script and tolerances fixed at 35563758. Output: `stage_k_blind/w2/compare_output.txt`. The blind results were not changed after the compare and no rerun was made.

| Item | Hand cases | MATCH | MISMATCH | Eligible | Counted blind | Needed for 60% | Outside share after the blind lane |
|---|---:|---:|---:|---:|---:|---:|---|
| K-8a DRC, RRAO | 16 | 16 | 0 | 15 | 15 | 9 | 17 of 18 (94%) |
| K-8f IMA ES, NMRF/SES, PLA | 15 | 15 | 0 | 15 | 15 | 8 | 27 of 33 (82%) |
| K-8g BA-CVA, SA-CVA | 14 | 14 | 0 | 14 | 14 | 8 | 16 of 16 (100%) |
| K-8i leverage, large exposures | 13 | 13 | 0 | 13 | 13 | 6 | 18 of 18 (100%) |

Not counted: rrao_k-0003 (its answer is stated by the rules text). Fields that are table lookups or follow directly from a ruling (m_c of cap_k-0001 and cap_k-0002; hbr and drc of drc_k-0008) matched but those cases count on their other fields only. Table-lookup value cases stay excluded (KR-68), which is why K-8f is 27 of 33.

What this does and does not show. Every hand case was reproduced from the rules text and inputs alone by a second model, so the specs are unambiguous enough to implement and the expected values are not one author's arithmetic slip. It does not show that the rules text reads the Basel paragraphs correctly: the deriver did not see the Basel text (the packet left it out), so a misreading shared by the spec would pass. The seven ambiguities the deriver recorded (`stage_k_blind/w2/notes.md`: maturity weight on CTP and securitisation positions, CTP HBR on unweighted net amounts, empty ES lists for horizons 2 to 5, the RFET window convention, the 0.9 name correlation by legal group, `floored` per bucket, seniority offsetting direction) all resolved to the spec's reading; each should be tightened in the spec text before the specs are confirmed. Verdict under the gate rule: all four items can meet 60%, subject to the four-language builds reproducing the same goldens.
