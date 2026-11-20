# Stage K: blind re-derivation (DR-H2) of the 28 cases checked only against printed regulator figures (KA-C18)

Written 2026-11-19 by the packet builder (Claude Opus 5.5, branch `k-audit-shares`, off the integration branch at `0b5ca451`). The packet builder is not the deriver and ran no derivation. Process: `program/STAGE_H_BLIND_LANE.md` (DR-H2); pattern and record format of `STAGE_K_BLIND_BTK.md` and `STAGE_K_BLIND_W1B.md` (including W1B's recorded process failure: there the lane read the unstripped spec before the packet existed; here the packet is the only thing to be handed over).

## Plain idea

Ruling KR-250 (`specifications/stage-k-rulings-audit-c.md`; response `program/STAGE_K_AUDIT_C18_RESPONSE.md`) holds 28 cases to the D6 text: a figure printed in the Basel text (CRE99 Examples 1 to 5, MAR99 Table 2) checks how we read the source, but only some outputs and only to the printed digits, so these cases do not count. A second model that never sees our numbers reads only the rules and computes every output of the 28 cases, freezes its answers with a hash, and a script fixed now compares them with the goldens at the goldens' own tolerance. A case counts only if every output matches.

What this adds, said plainly. The inputs are public Basel examples, so a deriver could in principle recall the printed answers. Recall cannot produce a match: the printed figures are rounded (569, 8.11%), the compare runs at 1e-12 absolute plus 1e-10 relative, and the self-test shows the printed figures themselves MISMATCH. What a blind match adds over the printed figures is agreement on every output at full precision, including the outputs the regulator never printed. What it does not add: the blind lane reads the same rules we wrote, so a match shows the rules are unambiguous and the arithmetic right, not that the rules read CRE52 or MAR99 correctly; that reading is what the printed figures check, and they stay recorded for it.

Outputs with no printed counterpart at all (read: `basel-framework-full.pdf` pp.524-540 and 758, text extracted 2026-11-19; formula images not re-read): saccr_k-0001 to 0005 `ead_unmargined` and `capped` (outputs of our KR-37 cap; for 0005 `ead_unmargined` is a real, 5,779.72, that CRE99 never computes), `mpor_days` for 0001 to 0004, `pfe` as a figure of its own; saccr_k-0004 (Example 4) every per-trade and hedging-set output (CRE99 prints only RC, the add-on and the EAD for it); btk_k-0012 `cumulative_probability` (Table 2 stops at "10 or more"); tlk_k-0001 to 0011 `plus_factor` (the 1996 table; source [S8] is marked "not opened" in `var-es-and-backtests.md`). Every other compared output is printed, if at all, only to its printed digits.

## What was built (evidence class: measured, 2026-11-19, local laptop, not the acceptance machine)

| File | Role | Side |
|---|---|---|
| `program/stage_h_blind_w2/pub_extract.py` | splits the 28 goldens into `pub_cases.json` (inputs) and `pub_expected.json` (outputs, per-output classes, SHA-256 of each golden file) | hidden |
| `program/stage_h_blind_w2/pub_cases.json` | case id, operation, inputs; the only case data the packet builder reads | builds the packet |
| `program/stage_h_blind_w2/pub_make_packet.py` | writes the packet; never reads `pub_expected.json` or a golden | builds the packet |
| `program/stage_h_blind_w2/pub_expected.json` | expected outputs (hidden; golden SHA-256: `saccr_k.json` e0fedebf..., `btk_k.json` a987ea2f..., `tlk_k.json` 0d9c72ea...) | hidden |
| `program/stage_h_blind_w2/pub_compare.py` | compare, with `--self-test` | hidden |
| `program/stage_h_blind_w2/pub_leaks.py` | leak check, with `--negative-control` | hidden |

Packet: `C:/Work/Claude/qf-blind/pub_packet/` (outside every worktree; not committed). Nine files plus the manifest: `README.md`, `specs/sa-ccr.blind.md`, `specs/frtb-ima-backtest.blind.md`, `specs/traffic-light.blind.md`, `rulings/stage-k-rulings.blind.md`, `tables/sa-ccr-parameters.json`, `tables/frtb-ima-backtest-tables.blind.json`, `inputs/pub.inputs.json`, `output_template.json`, `MANIFEST.sha256`.

**Packet MANIFEST.sha256 file hash: `447989d27fa84268ff722297ab7a500a6273a4ffd2d5f727638e69f2ee224c91`.** Built from commit `989e2c80` with `python -I program/stage_h_blind_w2/pub_make_packet.py . C:/Work/Claude/qf-blind/pub_packet`; a second build into a scratch folder gave the same manifest hash (reproducible), and `sha256sum -c MANIFEST.sha256` passes on every file. Before handing the packet over, the coordinator checks that `sha256sum MANIFEST.sha256` still gives this value.

What was stripped:
- SA-CCR spec: the sections "Worked example" (CRE99 Example 1 with every intermediate and EAD 569.47), "Goldens", "Acceptance" (KR-30 rule and the -7,100 / -7,099.30 figure), "Convergence and limit cases" (names cases); the Sources lines [CRE99] and [BCBS279] (the latter lists the five printed EADs; both name the examples); the CRE99 page pointer inside [CRE52]. Kept: plain idea, [CRE52] source, Formal statement, Operation (inputs and outputs), Errors, Limits and scope.
- Backtesting spec: as `btk_make_packet.strip_spec` (K-8e packet): worked example (6-decimal cumulative probabilities at 250), Goldens, Acceptance, the eleven printed MAR99 Table 2 percentages in Sources, the bis.org line, the `tlk_k` sentence.
- Traffic light: from `var-es-and-backtests.md` only the loss convention, the `risk.backtest.traffic_light` section and source [S8]; its Acceptance section (which cites MAR99 Table 2) and every other operation are cut.
- Rulings: KR-32 to KR-40, KR-42, KR-45 only; KR-33's pointer to a worked-example paragraph is reworded. Cut: KR-30, KR-31 (printed EAD and intermediate), KR-41, KR-43 (acceptance against printed tables), KR-44, KR-46, KR-47 (not used), the confirmation notes.
- Tables: `sa-ccr-parameters.json` unchanged (supervisory factors, correlations, volatilities, MPOR floors: rules, kept); the backtesting table as `btk_make_packet.strip_table` (multipliers at 250 and constants; no printed Table 1 or Table 2 probability for any sample size). No precomputed probability is shipped; the deriver computes every binomial sum.
- Inputs: the 28 cases only. README: the deriver reads only the packet and writes only to `C:/Work/Claude/qf-blind/pub_blind/`; standard-library Python only; **must not use any remembered published example value**, must say in `notes.md` if it recognises a case, and computes it from the rules regardless; tolerance classes stated without any value.

## Fixed now, before any blind result exists

- **Compare mapping and tolerances: commit `00167bf5`** (`pub_compare.py`, unchanged since). Every golden output is read from the blind case object under the same name, recursively (objects by key, arrays by position: the spec fixes the order of hedging sets and trades). Tolerances from the specs and the goldens' per-output classes with `conformance/tolerances/policy.yaml`: every real of `risk.saccr.ead` and every cumulative probability `|b - e| <= 1e-12 + 1e-10 max(|b|, |e|)`; exact for the golden's `date_and_convention` outputs (saccr `margined`, `capped`, `mpor_days`; btk `exceptions`, `zone`, `amber_from`, `red_from`, `multiplier`; tlk `zone`, `plus_factor`); strings, booleans and null always exact. Representation rules R1, R2, R4 as `btk_compare.py`.
- **Self-test 17/17 PASS** (`python -I program/stage_h_blind_w2/pub_compare.py . --self-test`): golden files unchanged (SHA-256); packet inputs equal the golden inputs; expected values equal the golden outputs; skeleton fields equal the expected fields; exact values all MATCH; 1e-13 relative noise on every real all MATCH; 1e-8 relative perturbation of every real makes every case MISMATCH; **the printed figures themselves (EAD 569, 0.0811, 0.9588) MISMATCH**, as do a wrong delta sign, reordered hedging sets, 0 for False, a multiplier off by 1e-10 and a wrong zone; null for a value is MISSING; 5.0 for 5 and a decimal-string real MATCH; an extra trade MISMATCH, a missing add-on class MISSING; wrapper, bare map and case list MATCH; an extra level is SHAPE; two wrapper levels and the unfilled skeleton give no MATCH; an absent case is MISSING.

## Leak check

`python -I program/stage_h_blind_w2/pub_leaks.py . C:/Work/Claude/qf-blind/pub_packet > C:/Work/Claude/qf-blind/pub_LEAKS.tsv`: **0 hard leaks** (exit 0; file SHA-256 `1c9c43912c474fb0d7800d94a27aaea07a7b51fe83c1d477444636599617b76d`, outside the packet). Counts: PARAM 130, INPUT 243, LOWINFO 297 (counts, floors, paragraph numbers in rule prose), ALLOWED 16: the MAR32.9 multiplier bands 1.76, 1.83, 1.88, 1.92 (rules; the multiplier is a rule field), and the MAR99.17 red-zone threshold 0.9999 / 99.99% (a rule the deriver must apply; equal to the 4-decimal rounding of the 10-exception probability only by coincidence, and worth nothing at the 1e-10 tolerance). Searched: every expected number as printed, rounded to 0 to 6 decimals while three significant digits remain, with thousands commas, probabilities as percents; every figure printed in CRE99 Examples 1 to 5, the five EADs, the sa-ccr.md worked-example intermediates and the eleven Table 2 percentages (list `PRINTED` in the script); case ids, suite names, "Example 1" to "Example 5" and CRE99.20 to 99.97 paragraph numbers in prose. **No printed CRE99 or MAR99 figure appears anywhere in the packet.**

Negative control: `pub_leaks.py . --negative-control` builds the same layout from the UNSTRIPPED specs, rulings and table and reports 239 HARD hits, including 569, 569.47, 5,406, 1,879, -7,100, 7,099.30, -0.2694, 8.11%, 28.58 and 0.958817 (exit 0 because every one of these is caught; file `C:/Work/Claude/qf-blind/pub_LEAKS_negctl.tsv`, SHA-256 `a5567c229c6139aad6c5747254779877d40ea3edf46d54ab71b17c10e69779dc`).

Not searchable by digits: booleans, null, zone names, ids and small integers. Their protection is the section stripping alone.

## Cases that cannot count, fixed now

None is excluded: no case's full answer is stated by the packet's rules text (the btk_k-0017 test). Fields compared but giving no credit on their own (`RULE_FIELDS` in `pub_compare.py`; all must still match for MATCH):
- btk_k-0001 to 0012: `exceptions` (the input), `zone`, `amber_from`, `red_from`, `multiplier` (the formal statement's bands at 250 and KR-42). Each counts on `cumulative_probability`, a full binomial sum.
- tlk_k-0001 to 0011: `zone`, `plus_factor` (the traffic-light section states the bands and the 1996 plus factors at 250 and 0.99). Each counts on `cumulative_probability`.
- saccr_k-0001 to 0005: `v`, `c`, `margined` (input echo or sum).

Stated plainly: tlk_k-000x and btk_k-000x (x = 1 to 11) have the same `cumulative_probability` (same binomial sum at 250 and 1%). They are separate goldens of separate operations and each counts, but the blind check of that sum is one computation for both.

**Eligible cases: 28 of 28.**

## Shares that would result (tool: `tools/outside_shares.py`, counts before the run measured 2026-11-19)

| Item | Value cases | (b) rule as written, now | Matches needed for 60% | (b) if all 28 match | (a) as the tool applied it (withdrawn) | (a) held to its own condition (every output printed) |
|---|---:|---:|---:|---:|---:|---:|
| Stage K | 87 | 50 (57.5%) | 3 (but every item below must also reach its floor) | 78 (89.7%) | 78 now and after | 61 now (btk_k-0001 to 0011 only), 78 after |
| K-8d `saccr_k` | 16 | 7 (43.8%) | 3 of 5 | 12 (75.0%) | 12 | 7 now, 12 after |
| K-8e `btk_k` | 24 | 11 (45.8%) | 4 of 12 | 23 (95.8%) | 23 | 22 now, 23 after |
| F (existing traffic_light) `tlk_k` | 11 | 0 (0%) | 7 of 11 | 11 (100%) | 11 | 0 now, 11 after |

Reading (a) is not the rule (Part 1 of the response); the columns are shown because the brief asks for both.

## Procedure

1. Coordinator: check the manifest hash above; hand the folder `C:/Work/Claude/qf-blind/pub_packet/` to a separate session on a different model from the spec lane. The SA-CCR and K-8e specs, rulings, goldens and this packet were written by Claude Opus 5.5, so the deriver must be another model (W1B, BTK and W2 used Claude Sonnet 5.5). The deriver works only in `C:/Work/Claude/qf-blind/pub_blind/` and is given no repository path.
2. Deriver, per the packet README: own reference (`blind_ref.py`, standard library only), `notes.md` (ambiguities, assumptions, manifest check, any case it recognises), `blind_results.json` filled from the skeleton at full binary64 precision, then `blind_results.sha256`, its hash the first line of the hand-back.
3. Coordinator: commit and push the frozen `blind_results.json` and its hash (copy into `stage_k_blind/pub/` with `notes.md` and `blind_ref.py`) **before** running the compare. Rule any gap from `notes.md` before the compare; a gap-decided field is compared but not counted. Record the deriver's own statement about access outside its two folders (its own statement, not independently logged).
4. Run `python -I program/stage_h_blind_w2/pub_compare.py . <frozen blind_results.json> > stage_k_blind/pub/compare_output.txt`. One run. A mismatch is investigated, never fixed by rerunning the deriver.
5. Fill the Results section; then the coordinator adds a DR-H2 MATCH line to each counted case's `verified_by` (the generator `oracle/python/gen_stage_k_w1b.py` writes it), reruns `tools/outside_shares.py`, and updates the outside-share lines.

## Results

(empty: to be filled by the coordinator after the one compare run: date, deriver and model, manifest check, frozen hash and commit, gaps and rulings, compare output path, per-case MATCH / MISMATCH / MISSING and counted, outside share after the run.)

## Results (2026-11-19; first and only compare run)

- Deriver: a separate subagent on Claude Sonnet 5.5 (specs, goldens and packet by Opus 5.5), given only the packet folder and its own folder; standard-library Python. It states that it recognised saccr_k-0001 to 0005 as resembling published SA-CCR worked examples and the btk/tlk cases as resembling the published 250-observation table, that it used no remembered value, and that it read nothing outside the two folders (its own statements, not independently logged). The coordinator checked the packet manifest hash 447989d2... before the hand-over.
- Blind results as received: `stage_k_blind/pub/`, committed in a13d107c before the compare. SHA-256 of `blind_results.json`: `8bab1ff8d258ad084f0e78ceb34be93feb3668ed34352b51c2108e80cdebee6d`, recomputed by the coordinator, equal to the deriver's hash file.
- Compare: `pub_compare.py` as fixed at 00167bf5; output `stage_k_blind/pub/compare_output.txt`. Results not changed afterwards; no rerun.

| Suite | Cases | MATCH | MISMATCH | Counted | Share after (rule as written, D6 and KR-250) |
|---|---:|---:|---:|---:|---|
| saccr_k (K-8d) | 5 | 5 | 0 | 5 | 12 of 16 (75.0%): 12 blind |
| btk_k (K-8e) | 12 | 12 | 0 | 12 | 23 of 24 (95.8%): 23 blind |
| tlk_k (existing traffic_light) | 11 | 11 | 0 | 11 | 11 of 11 |
| Stage K | 28 | 28 | 0 | 28 | 78 of 87 (89.7%) |

What this shows and does not. Every output of the 28 cases, including those no regulator prints, now agrees at full tolerance with a second model's derivation from the rules text; the printed Basel figures remain recorded as an extra check of the reading of the source. Limit: the inputs are public examples and the deriver recognised them, so recall of printed totals cannot be excluded for the few printed outputs; it cannot explain agreement at 1e-12 on unprinted intermediates. The 2026-11-19 audit finding KA-C18 stands as found: before this run the stage K share under the rule as written was 50 of 87.
