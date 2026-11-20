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

**Correction, 2026-11-19 (packet builder of the second blind lane, Claude Opus 5.5).** The K-8f figure "27 of 33 (82%)" in the table above is corrected 2026-11-19: it counted SciPy-only cases, which D6 does not count; **K-8f is 19 of 33 (58%) until the blind lane below reports.** The old line is kept as written. Rule: the D6 precedent applied to K-8e at integration (commit `2cef4f98` on `k-r1`, `tools/outside_shares.py`; `program/STAGE_K_BLIND_BTK.md` on `k-btk-blind`): a library primitive computing the same quantity is a reimplementation, not an outside check. Case list verified from the `verified_by` and `tags` fields of `datasets/golden/stage_k/ima_k.json` (sha256 `ca5bb2ed4affc74d248865a8299e9047ec1dad15acf71ed425ee4a1f958fc24d`, branch `k-w2-py-a` at `54ee228a`; evidence class read): 4 printed (pla_k-0007, 0008 MAR32.42; lh_k-0001, 0002 MAR33.12 FAQ4, FAQ5), 15 blind matches above, 6 table lookups (rfet_k-0005 to 0008, lh_k-0003, 0004; KR-68, not counted), and 8 whose only outside check is SciPy: pla_k-0001 to 0006 (`spearmanr`, `ks_2samp`, `kstwobign.sf`) and es_k-0001, 0002 (`integrate.quad` of the normal tail). 4 + 15 = 19 of 33. The handover's alternative of counting the two `quad` cases as D6 `library-primitive` (21 of 33) is not taken here; both go to the second blind lane, so the question no longer decides the gate. Corrected in the same commit: `STAGE_K_W2_GATE.md` (K-8f row), `specifications/06-risk/frtb-ima.md` (golden-table summary and A4), `STAGE_K_W2A_HANDOVER.md`.

What this does and does not show. Every hand case was reproduced from the rules text and inputs alone by a second model, so the specs are unambiguous enough to implement and the expected values are not one author's arithmetic slip. It does not show that the rules text reads the Basel paragraphs correctly: the deriver did not see the Basel text (the packet left it out), so a misreading shared by the spec would pass. The seven ambiguities the deriver recorded (`stage_k_blind/w2/notes.md`: maturity weight on CTP and securitisation positions, CTP HBR on unweighted net amounts, empty ES lists for horizons 2 to 5, the RFET window convention, the 0.9 name correlation by legal group, `floored` per bucket, seniority offsetting direction) all resolved to the spec's reading; each should be tightened in the spec text before the specs are confirmed. Verdict under the gate rule: all four items can meet 60%, subject to the four-language builds reproducing the same goldens.

## Second blind lane (SciPy-only cases)

Written 2026-11-19 by the packet builder (Claude Opus 5.5, branch `k-w2-py-a`), who is not the deriver and ran no derivation beyond the recheck below. Status: **packet built, blind lane not yet run.** Why: the correction above leaves K-8f at 19 of 33 (58%), one case under the 60% floor. The eight value cases of `ima_k` whose only outside check was SciPy get the DR-H2 treatment the other fifteen had. Evidence class of everything in this section: measured, 2026-11-19, local laptop, not the acceptance machine.

**Plain idea.** A second model that never sees our numbers reads only the PLA and ES rules, implements Spearman's rank correlation, the two-sample KS statistic, its asymptotic p-value and the normal ES from the definitions in standard-library Python (no SciPy, no NumPy, no `statistics` module), freezes its answers by hash, and a script fixed now compares them with the goldens.

| File | Role | Side |
|---|---|---|
| `program/stage_h_blind_w2/ima2_make_packet.py` | writes the packet; inputs written out (`CASES`, the 250-day series generated from the spec's integer formulas); never reads the expected file or the golden | builds the packet |
| `program/stage_h_blind_w2/ima2_expected.json` | expected outputs copied from `datasets/golden/stage_k/ima_k.json` (sha256 `ca5bb2ed...fc24d`); omitted, with reasons: `n`, `regulatory_window`, `label`, `mode` (input length, a rule on it, a fixed string, the input mode) | hidden |
| `program/stage_h_blind_w2/ima2_compare.py` | compare, with `--self-test` | hidden |
| `program/stage_h_blind_w2/ima2_leaks.py` | leak check (model `btk_leaks.py`) | hidden |
| `program/stage_h_blind_w2/ima2_recheck.py` | builder's recheck from the inputs, standard library only | hidden |

Packet: `C:/Work/Claude/qf-blind/ima2_packet/` (outside every worktree; not committed). Six files: `README.md` (read nothing outside the packet and the deriver's own folder `C:/Work/Claude/qf-blind/ima2_blind/`; standard library only; output, notes and freeze-by-hash rules), `specs/frtb-ima.blind.md`, `rulings/stage-k-rulings-w2.blind.md`, `inputs/ima2.inputs.json`, `output_template.json`, `MANIFEST.sha256`.

**Packet MANIFEST.sha256 file hash: `3de017bf0820e349d4b9d13886b7165fa85d88fef676433fce489296d56f49b9`.** Built from commit `629234a1` with `python -I program/stage_h_blind_w2/ima2_make_packet.py . C:/Work/Claude/qf-blind/ima2_packet`; a rebuild into a scratch folder gave the same hash, and `sha256sum -c MANIFEST.sha256` passes in the packet. Before handing it over, the coordinator checks that `sha256sum MANIFEST.sha256` still gives this value.

What was stripped. From `frtb-ima.md`: everything except the title, plain idea, Sources (the SciPy row cut), the formal statement of `risk.frtb.pla` and `risk.frtb.ima.es_lh`, Errors and Limits; inside those, the `risk.frtb.pla.ks_pvalue` paragraph (it names the KS values of the printed p-values, one of which is pla_k-0003's), the es_k-0005 parenthetical, and the builder's measurement sentence on the two Q_KS forms. From the rulings only KR-56, KR-57, KR-67 and KR-117 are kept; cut inside them: the KR-56 clause quoting the MAR32.42 p-values with our values (0.0546 is pla_k-0003's p-value), **the KR-57 normal ES factor, which is es_k-0001's answer and would have made es_k-0001 and es_k-0002 not blind**, the KR-117 SciPy sentence and an error-case id.

### Spec defects found and fixed (in `629234a1`, before the packet)

1. **Normal ES formula only in a ruling.** The spec's `es_lh` text named a `sigma` mode but gave no formula; KR-57 had it. Fixed: the spec now states `ES_j = sigma_j phi(z) / (1 - 0.975)`, `z = Phi^-1(0.975)`, mean 0, losses positive, `sigma_j = 0` gives 0.
2. **Q_KS not defined at x = 0 in the spec text.** The spec gave only the alternating series, which does not converge at 0; the theta form and the switch at x = 1 were only in KR-117. Fixed: the spec now states the KR-117 evaluation and the KR-67 tolerance for it. Measured (packet builder, standard-library Python against a 60-digit `decimal` reference, x = 0.01 to 7.99): either form alone stays within `max(1e-12 |Q|, 1e-15)` for x > 0 (worst: theta form 0.78 of the tolerance near x = 5.8, under the absolute floor; alternating series 0.001 at x = 0.01). So the p-value was already reproducible to tolerance from the earlier text at every x > 0, including all six cases here; the defect is the undefined point and the missing tolerance statement, not a value. No expected value changed.

Not a defect, stated so nobody is surprised: the KS p-value is the asymptotic Kolmogorov tail `Q_KS(ks sqrt(n/2))`, which the spec fixes exactly; it is not SciPy's default exact two-sample p-value, and the packet does not mention SciPy's method.

### Fixed now, before any blind result exists

- **Compare script and tolerances: commit `629234a1`** (`ima2_compare.py`). Tolerance from KR-67, `frtb-ima.md` A1 and the golden `tolerance_limit` (relative 1e-12, absolute 1e-15), in the form `k2_compare.py` used for the same specs: reals `|b - e| <= max(1e-12 |e|, 1e-15)` (spearman, ks, ks_pvalue_asymptotic, es, each `es_by_horizon` element); `ks_count` by integer value, `zone` exactly; a boolean never equals a number. Representation rules R1, R2, R4 as `btk_compare.py`. pla_k-0004's p-value is 1.88e-17, so the absolute floor accepts any value within 1e-15 there; that case still counts on its other four fields.
- **Self-test 18/18 PASS** (`python -I program/stage_h_blind_w2/ima2_compare.py . --self-test`): packet inputs equal the golden inputs; expected equals the golden minus the four omitted fields; the 8 cases are exactly the `ima_k` value cases with no printed figure, no blind match and no table lookup (computed from the golden's tags and `verified_by`); skeleton paths equal expected paths; exact values MATCH; 1e-14 noise MATCH; 1e-9 perturbation MISMATCH everywhere; wrong zone, wrong count, a p-value 2e-15 off, a short list, es 2e-12 off, True for a count each MISMATCH; 1e-16 for 0 and 0 for the 1.9e-17 p-value MATCH; 30.0 and a decimal string MATCH; wrapper, bare map and case list MATCH; extra level SHAPE; two wrappers and the empty skeleton never MATCH; absent case or field MISSING.
- **Leak check: 0 hard leaks** (`python -I program/stage_h_blind_w2/ima2_leaks.py . C:/Work/Claude/qf-blind/ima2_packet > C:/Work/Claude/qf-blind/ima2_LEAKS.tsv`, exit 0; list file sha256 `e60eed62521f68713563fd8678d34a4d70b6e1779411142c327c052bc1cd3734`, outside the packet). Searched: every expected number not equal to an input of its own case, as printed and rounded to 2, 4, 6 decimals (at least three significant digits), KS values and p-values also as percents, `es_by_horizon` element by element, the normal quantile 1.95996 at 4 and 6 decimals, and any `pla_k`, `es_k`, `ima_k` or `pla_ke` id outside the inputs and template. Hits: 8 INPUT, 2 LOWINFO (the `9` of the green threshold `100 d < 9 n` in the spec and KR-56, equal to pla_k-0002's `ks_count`). Not searchable: zones (an enumeration the schema states).
- **Builder recheck** (`python -I program/stage_h_blind_w2/ima2_recheck.py .`): all 8 cases reproduce from the stripped rules within tolerance (worst 0.00057 of the tolerance, from the bisected normal quantile); every zone and count equal. Our own computation; counts as no outside check.

### Eligibility and what is needed

| Case | Operation | Fields compared | Eligible |
|---|---|---|---|
| pla_k-0001 to 0006 | `risk.frtb.pla` | spearman, ks, ks_count, zone, ks_pvalue_asymptotic | yes (6) |
| es_k-0001, es_k-0002 | `risk.frtb.ima.es_lh`, `sigma` mode | es_by_horizon, es | yes (2) |

**Eligible 8 of 8. Cases that cannot count: none** (`NOT_COUNTED` is empty: with the KR-57 factor cut, no rules text in the packet states an answer). The table-lookup cases (rfet_k-0005 to 0008, lh_k-0003, 0004) stay outside, KR-68.

**Matches needed for 60%: 1** (19 + 1 = 20 of 33 = 61%). If all 8 match: 27 of 33 (82%).

Procedure: as for the first lane (steps 1 to 5 above), with the packet `C:/Work/Claude/qf-blind/ima2_packet/`, the deriver's folder `C:/Work/Claude/qf-blind/ima2_blind/`, the frozen results committed under `stage_k_blind/ima2/` before the compare, and `python -I program/stage_h_blind_w2/ima2_compare.py . <frozen blind_results.json> > stage_k_blind/ima2/compare_output.txt`, one run. The deriver must be a different model from this builder and from the spec and lane A authors (all Claude Opus 5.5).

### Results (second lane)

Not run. (Date, deriver and model, packet manifest check, frozen hash and commit, notes and any rulings, compare output path, MATCH / MISMATCH / MISSING per case, counted, K-8f share: to be filled by the coordinator.)

### Second blind lane: results (2026-11-19; first and only compare run)

- Deriver: a separate subagent on Claude Sonnet 5.5, given only the packet folder and its own folder; standard library only (no SciPy, numpy or mpmath), statistics implemented from their definitions. Its own statement: read and tried to read nothing outside the two folders (not independently logged). Coordinator checked the packet manifest hash 3de017bf... before the hand-over.
- Blind results as received: `stage_k_blind/ima2/`, committed in fa6d42d0 before the compare. SHA-256 of `blind_results.json`: `5b10910fa72eb77e69c0337f325bd0814a4c232ae05ce72e02106b73797a7df5`, recomputed by the coordinator, equal to the deriver's hash file.
- Compare: `ima2_compare.py` as fixed at 629234a1 (tolerance max(1e-12|e|, 1e-15)); output `stage_k_blind/ima2/compare_output.txt`. No rerun; results unchanged.

| Lane | Cases | MATCH | MISMATCH | Eligible | Counted | K-8f outside share after it |
|---|---:|---:|---:|---:|---:|---|
| Second (SciPy-only cases) | 8 | 8 | 0 | 8 | 8 | 27 of 33 (81.8%): 4 printed, 23 blind |

Largest difference seen: the normal ES factor, 2.3378027922014146 (golden) against 2.337802792201402 (blind), relative 5.4e-15, inside the tolerance; it comes from how 1 - 0.975 and the tail are evaluated in binary64. Deriver's recorded readings (`stage_k_blind/ima2/notes.md`): Spearman last-ulp rounding depends on integer or float product under the square root; pla_k-0001 is RED from the KS rule at n = 5 despite a rank correlation of 0.9, applied literally; the Q_KS series summed plainly; pla_k-0005 gives exactly 1.0. The spec should state the Spearman evaluation order or accept the tolerance explicitly.

Correction also applying to K-8g (2026-11-19): its "16 of 16" above counted two discount-factor cases checked only by SciPy quad (df_k-0001, df_k-0002). Under D6 those do not count: K-8g is 14 of 16 (87.5%).
