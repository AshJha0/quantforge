# Stage K item K-8h: blind re-derivation (DR-H2) of the sensitivity-based initial margin hand value cases ("sbim"), placeholder weights

Written 2026-11-19 by the K-8h spec lane and packet builder (Claude Opus 5.5, branch `k-simm-spec`). The packet builder is not the blind lane and ran no derivation beyond rechecking the spec's own arithmetic. Process: `program/STAGE_H_BLIND_LANE.md` (DR-H2); built exactly like `program/STAGE_K_BLIND_W2.md`, with the W1B lesson applied (`program/STAGE_K_BLIND_W1B.md`: the deriver is given the packet only, never the unstripped spec). Every number in this record and in the packet is computed on **placeholder weights**.

**Renamed after the compare (owner decision 2026-11-19).** The packet, the compare and this record were first made under the name "SIMM structure" (this file was `program/STAGE_K_BLIND_SIMM.md`, case ids `simm_k-NNNN`). After the compare the owner ruled that the project uses no ISDA material (the ISDA SIMM methodology is licensed for a market participant's own transactions only and is covered by a patent) and that SIMM is not a named, delivered item. The item is now the project's own sensitivity-based aggregation, short id `sbim`; see the section "Rename after the compare" for what changed and what was checked. The blind result is a check of **our own stated algebra and arithmetic** and nothing else.

## Plain idea

A second model, which never sees our numbers, reads only the rules and the placeholder table and computes the cases itself. It freezes its answers with a hash before anyone compares. A script, fixed in advance, compares them with the spec lane's values. A case counts as outside-checked (class B, KR-141 and KR-68) only if it matches and nothing in what the lane read gave the answer away.

## Sources read for this item (evidence classes)

| Source | Path | Date | Class |
|---|---|---|---|
| Stage G single-bucket IR delta aggregation, ruling G-43 | `specifications/06-risk/xva-framework.md`, `specifications/stage-g-rulings.md` | 2026-11-19 | read |
| K-8h gate note | `program/STAGE_K_W2_GATE.md` | 2026-11-19 | read |
| ORE survey section 5, licence register | `program/STAGE_K_ORE_SURVEY.md`, `oracle/LICENCES.md` | 2026-11-19 | read (ORE calibration files not opened) |
| SA-CVA clipped sum and radicand floor | `specifications/06-risk/cva-capital.md`, KR-62 | 2026-11-19 | read |

No proprietary methodology document or parameter set was read. (The first version of this record noted that an automated fetch of a standards body's landing page returned HTTP 403, so nothing was read; under the owner decision no such document is to be opened at all.) Every formula of the spec has the evidence class **project definition**.

## What was built (evidence class: measured, 2026-11-19, local laptop, not the acceptance machine)

| File | Role | Side |
|---|---|---|
| `tools/gen_sbim_placeholder.py`, `specifications/tables/stage_k/sbim-placeholder.json` | placeholder table and its generator (rule-made round numbers, header `placeholder: true`) | packet (table) |
| `tools/test_sbim_placeholder.py` | fails if the table is not the generator's output or breaks the stated rule (5/5 PASS, incl. planted fault); in `repo-gates.yml` | repo |
| `program/stage_h_blind_w2/sbim_cases.py` | full inputs of the 29 blind cases (`CASES`) and of the case added afterwards (`ADDED_CASES`) | builds the packet (CASES only) |
| `program/stage_h_blind_w2/sbim_make_packet.py` | writes the packet; never reads the expected file | builds the packet |
| `program/stage_h_blind_w2/sbim_ref.py` | spec lane's own reference; writes `sbim_expected.json` (29 blind cases) and `sbim_added_expected.json` (added cases); also supplies the skeleton's keys with every leaf null | hidden |
| `program/stage_h_blind_w2/sbim_expected.json` | 395 expected fields over 29 cases | hidden |
| `program/stage_h_blind_w2/sbim_added_expected.json` | 20 expected fields of sbim_k-0030 (added after the blind run; not blind-checked) | hidden; never in the packet |
| `program/stage_h_blind_w2/sbim_leaks.py` | leak check (copy of `k2_leaks.py`) | hidden |
| `program/stage_h_blind_w2/sbim_compare.py` | compare, with `--self-test` (copy of `k2_compare.py`) | hidden |

Original packet (the one the deriver used): `C:/Work/Claude/qf-blind/simm_packet/` (outside every worktree; not committed). 7 files. **Original packet MANIFEST.sha256 file hash: `f4eed98d89fbb07da596eaa28a12343b5e63999b4e3d63684aa839a85c493b70`** (built from commit `4d4e7510`; rebuilt reproducibly; rechecked 2026-11-19 after the rename: unchanged on disk).

What was stripped: from the spec the sections "Worked example", "Hand cases" (every expected value and the arithmetic) and "Acceptance" (it names the gate count). Kept: header, label rule, plain idea, Sources, Scope, Formal statement (inputs, steps 1 to 9, outputs), Errors, Limits. From the rulings: KR-141 (gate classes).

## Fixed before any blind result existed

- **Compare mapping and tolerances: commit `4d4e7510`** (then `simm_compare.py`). Mapping: each expected field path is read from the blind case object at the same path as the packet skeleton. Tolerance KR-139 (= KR-67): `|blind - expected| <= max(1e-12 |expected|, 1e-15)`; no per-case exception. Representation rules R1 to R4 as in `k2_compare.py`.
- **Dry self-test on fabricated data: 14/14 PASS**, then and again after the rename (`python -I program/stage_h_blind_w2/sbim_compare.py . --self-test`).

## Spec arithmetic recheck

The 29 headline totals were recomputed from the closed-form expressions in the spec's Hand cases column, independently of the reference script: 29 of 29 agree with the expected file within 1e-12 relative. Our own second computation; counts as no outside check.

## Leak check (original packet)

0 hard leaks (list file SHA-256 `d2242d38517c1276ccefcae5a52224ae9471a8a46d189b93a24820add1eeaea6`, outside the packet). Hits: 189 PARAM, 187 INPUT, 237 LOWINFO. No case id appeared in any prose file.

## Cases that cannot count, fixed before the run

| Case | Why | Effect |
|---|---|---|
| sbim_k-0028 (was simm_k-0028) | The stripped rules text states the answer: step 9 and KR-136 say no records gives `total = 0`, and the input has no records. | Compared, never counted (`NOT_COUNTED`). |

## Gate note: what a blind match on placeholder weights does and does not show

A match shows two things: the spec states our aggregation algebra unambiguously enough that a second model, reading only the rules, computes the same numbers; and the spec lane's arithmetic on the placeholder table is right. It does **not** show agreement with any industry or regulatory margin model, and the item makes no such claim: the algebra is a project definition, written from general knowledge of sensitivity-based margin models, with no proprietary document read or used. A shared slip in our own definition would pass the blind lane unseen, because the deriver reads our rules.

## Results (2026-11-19; first and only compare run, under the old names)

- Deriver: a separate subagent on Claude Sonnet 5.5 (spec and packet by Opus 5.5), given only the packet folder and its own folder; standard-library Python. It states it used no outside knowledge (every constant from the packet table) and read or tried to read nothing outside the two folders (its own statement, not independently logged). The coordinator checked the packet manifest hash f4eed98d... before the hand-over.
- Blind results as received: now `stage_k_blind/sbim/` (moved from `stage_k_blind/simm/` by `git mv`; file contents unchanged, so they still carry the old case ids and key names), committed in a0d31fd1 before the compare. **SHA-256 of `blind_results.json`: `55d6d5da719284fb5ab4e5de4f0939e15e12096fa125d99bd70f33b47f1de12e`**, equal to the deriver's hash file `results.sha256`.
- Compare: `simm_compare.py` as fixed at 4d4e7510; output `stage_k_blind/sbim/compare_output.txt` (old ids). Results not changed afterwards; no rerun of the blind lane.

| Item | Cases | MATCH | MISMATCH | Eligible | Counted | Needed |
|---|---:|---:|---:|---:|---:|---:|
| K-8h (blind run, 29 cases) | 29 | 29 | 0 | 28 | 28 | 18 |

Ambiguities the deriver recorded (`stage_k_blind/sbim/notes.md`): the equity vega within-bucket correlation between different issuers, and its square for curvature, is not exercised by any case (case 22 has one factor per bucket); interest-rate deltas under another group; single-bucket margin equals K_b; the net-zero group; `label` absent from the template. Closed after the compare: spec step 4 now says the EQ bucket correlation applies between two different issuers for delta and vega alike and that a single bucket gives `M = K_b`; ruling KR-138 says the same; case sbim_k-0030 exercises the two-issuer vega and curvature path (not blind-checked).

## Rename after the compare (2026-11-19)

What changed: file names (`simm` to `sbim`), operation id (`risk.simm.placeholder` to `risk.sbim.placeholder`), case ids (`simm_k-NNNN` to `sbim_k-NNNN`), the level "product class" to "group" (output key `product_classes` to `groups`; labels `RatesFX` to `RATES`, `Equity` to `EQUITY`, now caller-chosen), input fields `qualifier` to `name` and `label1` to `tenor`, the cross-risk-class correlation `psi` to `rho_class`, the label string, the table's notice, and the framing of every doc. What did not change: every formula and every number.

Checked 2026-11-19 (evidence class: measured, local laptop, not the acceptance machine):

- `sbim_expected.json` equals the old `simm_expected.json` (from git HEAD 067a2bab) **byte for byte** after the identifier mapping above (395 fields, 29 cases).
- The rebuilt packet `C:/Work/Claude/qf-blind/sbim_packet/` (6 files; MANIFEST.sha256 file hash `e06d4bf5a2722eca3cd8abf3a031ff407725074392523e65868f17c4d423bc70`): `inputs/K-8h.inputs.json` equals the original packet's byte for byte after the mapping; `output_template.json` has the same skeleton and field list after the mapping; every number of the table is identical (only the header text and the key `psi` changed). The spec and rulings copies differ in wording (framing, names, and the two clarifications above). This rebuilt packet was **not** given to any deriver; it exists only to show the rename is a renaming.
- Leak check on the rebuilt packet: **0 hard leaks** (PARAM 189, INPUT 187, LOWINFO 225; list `C:/Work/Claude/qf-blind/sbim_LEAKS.tsv`, SHA-256 `c5aa38702fd23cf6b105769f1b28baa496140792c051ffc0375e20ab8f01a832`).
- The frozen blind results, mapped in memory to the new names (file not changed), compared with `sbim_compare.py`: 29 MATCH, 0 MISMATCH, 28 counted, as in the original run.

## Gate status (after the rename)

K-8h is a **project-defined model**, outside the plan's regulatory list, and is not presented as a regulatory or industry-standard item. The gate rule that applies is the one for project definitions: source = the spec and rulings (evidence class project definition); outside checks = the blind re-derivation share, 60% of the value cases (KR-141).

| Value cases | Blind-checked | Eligible | Counted blind MATCH | Needed (60% of 30) | Not blind-checked |
|---:|---:|---:|---:|---:|---|
| 30 | 29 | 28 | 28 | 18 | sbim_k-0030 (added after the blind run) |

Share 28 of 30 = 93%: met. The earlier condition "a source actually read" was the gate for a named regulatory item and no longer applies, because no such claim is made. The item stays PROPOSED until the coordinator confirms the rulings; it is not part of any release before that, and never under the name SIMM.
