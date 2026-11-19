# Stage K: blind re-derivation (DR-H2) of K-8e FRTB backtesting, the 12 btk_k value cases without a printed figure

Written 2026-11-19 by the packet builder (Claude Opus 5.5, branch `k-btk-blind`, off the integration branch at `2cef4f98`). The packet builder is not the deriver and ran no derivation beyond rechecking the goldens' own arithmetic. Process: `program/STAGE_H_BLIND_LANE.md` (DR-H2); pattern and record format of `STAGE_K_BLIND_W2.md` and `STAGE_K_BLIND_W1B.md`. Status: **packet built, deriver not yet run.**

## Plain idea

Suite `btk_k` has 24 value cases. Twelve (btk_k-0001 to 0012) are checked against the printed MAR99 Table 2 and count as outside-checked. The other twelve (btk_k-0013 to 0024) were checked only against SciPy's binomial functions, which do not count under the D6 precedent (integration commit `2cef4f98`, `tools/outside_shares.py`), so the item stands at 12 of 24 (50%) against a 60% floor. A second model that never sees our numbers reads only the rules and computes those twelve itself, freezes its answers with a hash, and a script fixed now compares them with the goldens. A case counts only if it matches and nothing in what the deriver read gave its answer away.

## What was built (evidence class: measured, 2026-11-19, local laptop, not the acceptance machine)

| File | Role | Side |
|---|---|---|
| `program/stage_h_blind_w2/btk_make_packet.py` | writes the packet; the 12 cases' inputs are written out in `CASES`; never reads the expected file or the golden | builds the packet |
| `program/stage_h_blind_w2/btk_expected.json` | the golden outputs of the 12 cases with each output's tolerance class, copied from `datasets/golden/stage_k/btk_k.json` (its SHA-256 recorded in the file) | hidden |
| `program/stage_h_blind_w2/btk_compare.py` | compare, with `--self-test` | hidden |
| `program/stage_h_blind_w2/btk_leaks.py` | leak check (model `k2_leaks.py`) | hidden |
| `program/stage_h_blind_w2/btk_recheck.py` | packet builder's recheck of every expected field with exact rational binomial sums | hidden |

Packet: `C:/Work/Claude/qf-blind/btk_packet/` (outside every worktree; not committed). Six files plus the manifest: `README.md`, `specs/frtb-ima-backtest.blind.md`, `rulings/stage-k-rulings-w1b.blind.md`, `tables/frtb-ima-backtest-tables.blind.json`, `inputs/btk.inputs.json`, `output_template.json` (field definitions and a results skeleton with every field null), `MANIFEST.sha256`.

**Packet MANIFEST.sha256 file hash: `03fdc75db2901f01e3b7a08fef75050edda6bc066df901f2786d1914a89e630c`.** Built from commit `21392489` with `python -I program/stage_h_blind_w2/btk_make_packet.py . C:/Work/Claude/qf-blind/btk_packet`; a build into a scratch folder gave the same manifest hash (reproducible), and `sha256sum -c MANIFEST.sha256` passes on every file. Before handing the packet over, the coordinator checks that `sha256sum MANIFEST.sha256` still gives this value.

What was stripped:
- Spec: the sections "Worked example" (it prints the 250 and 500 boundaries, the latter being btk_k-0014's answer), "Goldens" and "Acceptance"; from Sources the eleven printed MAR99 Table 2 cumulative probabilities (they are the 2-decimal roundings of btk_k-0013, 0021 and 0022 probabilities) and the note that Table 1 is transcribed into the table file; the bis.org cross-read line; the sentence about suite `tlk_k`; the repository table path (replaced by the packet path). Kept: header, plain idea, Sources otherwise, the relation to `risk.backtest.traffic_light`, Formal statement, Operations, Errors, Limits.
- Rulings: only KR-40, KR-42, KR-44, KR-45, KR-46, KR-47 (the K-8e rulings these operations use). KR-44 is labelled **inferred** in a note above the table, as the confirmation records; its sentence naming btk_k-0019 and 0021 and their outcomes is cut. Cut entirely: KR-30 to KR-39 (SA-CCR), KR-41 (acceptance against printed figures), KR-43 (the stage F check), the confirmation notes.
- Table: only the keys the rules use as a lookup or a constant: `coverage`, `amber_from_cumulative`, `red_from_cumulative`, `table_observations`, `multiplier_250`, `multiplier_red`, `desk_limit_99`, `desk_limit_975`, `max_observations`, `source`. Cut: `printed_table2_cumulative_percent`, `printed_table2_zone`, every `printed_table1_*` key. The rules define the cumulative probability and the zone boundaries by the binomial rule (MAR99.17 for any n, KR-42), not as a lookup, so no precomputed probability is shipped for any sample size, 250 included; the deriver computes every binomial sum itself.
- Inputs: the 12 cases only. README: the deriver reads only the packet and writes only to `C:/Work/Claude/qf-blind/btk_blind/`; standard-library Python only (no SciPy, NumPy or mpmath); exact rational or high-precision decimal arithmetic for the binomial sums is the deriver's choice, stated in its notes; the tolerance classes are stated (below) without any value.

## Fixed now, before any blind result exists

- **Compare mapping and tolerances: commit `21392489`** (`btk_compare.py`). Mapping: every golden output of a case is read from the blind case object under the same name; the self-test fails if the skeleton's fields differ from the expected fields of any case. Tolerances from the spec ("Probabilities are binary64 (tolerance class `simple_analytic`); counts, zones, flags and the tabulated multiplier compare exactly") and the golden's per-output classes, with `conformance/tolerances/policy.yaml`: probabilities `|b - e| <= 1e-12 + 1e-10 max(|b|, |e|)`; everything else exact (integers by value, strings, booleans, null, the multiplier as binary64, day lists element by element); a boolean never equals a number; a value where null is expected is a MISMATCH.
- Representation rules R1, R2, R4 as in `k2_compare.py` (top-level shapes, one wrapper level, a number as a decimal string); an unknown extra level is a SHAPE error, exit 2, never a pass.
- **Self-test 16/16 PASS** (`python -I program/stage_h_blind_w2/btk_compare.py . --self-test`): the packet's written-out inputs equal the golden inputs; the expected values equal the golden outputs; the skeleton fields equal the expected fields; exact values all MATCH; 1e-13 relative noise on probabilities all MATCH; 1e-8 relative perturbation gives MISMATCH in every case with a probability; a wrong integer, a wrong zone, 1 for True, a multiplier off by 1e-10, a short day list and a value where null is expected each MISMATCH; 9.0 for 9 and a decimal-string probability MATCH; an `outputs` wrapper, a bare case map and a case list MATCH; an extra level is SHAPE; two wrapper levels give no MATCH; the unfilled skeleton gives no MATCH; an absent case and an absent field are MISSING.

## Golden arithmetic recheck

`python -I program/stage_h_blind_w2/btk_recheck.py .`: **77 fields, 0 DIFF**; all 16 probabilities are bit-equal to the correctly rounded value of the exact rational sum. This is our own second computation and counts as no outside check.

## Leak check

`python -I program/stage_h_blind_w2/btk_leaks.py . C:/Work/Claude/qf-blind/btk_packet > C:/Work/Claude/qf-blind/btk_LEAKS.tsv`: **0 hard leaks** (exit 0; list file SHA-256 `36e7760a20474918e29f041ee2b4e346784615306c4649ef995cc886f8b52014`, outside the packet). Counts: PARAM 2 (1.83 in `multiplier_250`, 0.99 the coverage), INPUT 11, LOWINFO 46 (counts such as 3, 5, 10 and "99%" in rule prose), ALLOWED 2 (1.83 in the MAR32.9 multiplier band in Sources and the Formal statement; btk_k-0013's multiplier is a rule field). Searched: every expected number as printed, rounded to 2, 4 and 6 decimals when that keeps three significant digits, probabilities also as percents; the day lists as printed; case ids and the suite names `btk_k`, `tlk_k` in prose. Negative control: the same check run on the unstripped spec and rulings reports 99.60%, 8.11% and 98.63% (Table 2 figures equal to the roundings of three case probabilities) and every case id and suite name as HARD, so the check would have caught them.

Not searchable by digits, stated so the coordinator knows the check says nothing about them: booleans, null, the zone names (an enumeration the schema states) and small integers (amber_from, red_from, counts). Their protection is the section stripping alone; the worked example, which printed amber from 9 and red from 15 at 500 observations (btk_k-0014), is cut.

## Cases that cannot count, fixed now

| Case | Why | Effect |
|---|---|---|
| btk_k-0017 | The rules text states its answer. The spec Limits and KR-42 say that for n <= 5 zero exceptions is amber, with P(X = 0) = 0.99^n; at n = 1 this gives `cumulative_probability` 0.99, `zone` AMBER and `amber_from` 0, and `red_from` 1 follows from cdf(n) = 1 in the Formal statement. KR-42 is kept whole because it is the ruling that decides this reading. | Compared, never counted (`NOT_COUNTED` in `btk_compare.py`). |

No unchecked case is a direct table lookup: the only table-lookup output among them is `multiplier`, and no case consists of it alone. Fields that are implied by a table or a rule, compared but giving no credit on their own (`RULE_FIELDS`; the case counts on its computed fields, all fields must still match for MATCH):
- btk_k-0013 (n = 250): `multiplier` 1.83 is a lookup of `multiplier_250`; `zone`, `amber_from`, `red_from` follow from the multiplier bands (0 to 4, 5 to 9, from 10) printed in the Formal statement. The case counts on `cumulative_probability`, which needs the full binomial sum (the Table 2 rounding is cut).
- btk_k-0014, 0015, 0016, 0018: `multiplier` null by KR-42 (n is not 250).
- btk_k-0019 to 0023: `breach_99`, `breach_975`, `eligible` follow from the counts by KR-44.
- btk_k-0024 (`risk.frtb.backtest.count`): no table; the counts and day lists apply KR-45 to the inputs. It was a hand case, not a SciPy case, but it is one of the 12 value cases not counted today, so it is in the packet.

Weak discrimination, stated: three probabilities lie within the tolerance of 1.0 (btk_k-0019 and 0021 `cumulative_probability_975`, about 1 - 4e-13 and 1 - 7e-14; btk_k-0023 `cumulative_probability_975`, 1 - 1e-11), so a deriver that reported 1.0 there would still match. Each of these cases also has a `cumulative_probability_99` at least 1.9e-6 away from 1 (0.081 for 0021), which the tolerance does discriminate, so no case rests on a non-discriminating field alone.

**Eligible cases: 11 of 12** (btk_k-0013 to 0016, 0018 to 0024). **Matches needed: 3** (12 published + 3 = 15 of 24 = 62.5%, the first count at or above 60%; 14 of 24 is 58.3%). All 11 matching would give 23 of 24 (95.8%).

## Procedure

1. Coordinator: check the manifest hash above; hand the folder `C:/Work/Claude/qf-blind/btk_packet/` to a separate session on a different model from the spec lane. The K-8e spec, rulings, goldens and this packet were all written by Claude Opus 5.5 (commits a3a999bc, 31a9fa0a, e85d43ec, ed3090aa, 2cef4f98, 21392489), so the deriver must be another model, for example Claude Sonnet as in W1B and W2. The deriver works only in `C:/Work/Claude/qf-blind/btk_blind/` and is given no repository path.
2. Deriver, per the packet README: own reference (`blind_ref.py`, standard library only, no repository imports), `notes.md` with every ambiguity and assumption and the manifest check, `blind_results.json` filled from the skeleton at full binary64 precision, then `blind_results.sha256` written and the hash reported first in its hand-back, before it sees anything else.
3. Coordinator: commit and push the frozen `blind_results.json` and its hash (copy into `stage_k_blind/btk/` with `notes.md` and `blind_ref.py`) **before** running the compare. Rule any gap from `notes.md` that the spec left open, before the compare, as a numbered ruling; a gap-decided field is compared but not counted. Record the deriver's own report of any access outside its two folders (W1B's process failure was a read of the unstripped spec before the packet existed; here the packet is the only thing handed over).
4. Run `python -I program/stage_h_blind_w2/btk_compare.py . <frozen blind_results.json> > stage_k_blind/btk/compare_output.txt`. One run. A mismatch is investigated, never fixed by rerunning the deriver; if the golden was wrong it is corrected with the reason; if the deriver was wrong its error is recorded.
5. Fill the results section below; then the coordinator updates the counted cases' `verified_by` (a DR-H2 MATCH entry), `tools/outside_shares.py` output, the spec's outside-share line and `docs/model-inventory.md`.

## Results

Not run. (Date, deriver and model, packet manifest check, frozen hash and commit, gaps and rulings, compare run and output path, per-case MATCH / MISMATCH / MISSING and counted, resolution of each mismatch, outside share after the run: to be filled by the coordinator.)
