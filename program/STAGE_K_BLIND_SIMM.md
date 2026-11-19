# Stage K item K-8h: blind re-derivation (DR-H2) of the 29 SIMM-structure hand value cases, placeholder weights

Written 2026-11-19 by the K-8h spec lane and packet builder (Claude Opus 5.5, branch `k-simm-spec`). The packet builder is not the blind lane and ran no derivation beyond rechecking the spec's own arithmetic. Process: `program/STAGE_H_BLIND_LANE.md` (DR-H2); built exactly like `program/STAGE_K_BLIND_W2.md`, with the W1B lesson applied (`program/STAGE_K_BLIND_W1B.md`: the deriver is given the packet only, never the unstripped spec). Status: **packet built, blind lane not yet run.** Every number in this record and in the packet is computed on **placeholder weights**.

## Plain idea

A second model, which never sees our numbers, reads only the rules and the placeholder table and computes the 29 cases itself. It freezes its answers with a hash before anyone compares. A script, fixed now, compares them with the spec lane's values. A case counts as outside-checked (class B, KR-141 and KR-68) only if it matches and nothing in what the lane read gave the answer away.

## Sources read for this item (evidence classes)

| Source | URL or path | Date | Class |
|---|---|---|---|
| ISDA SIMM Methodology (public PDF per the stage K plan) | https://www.isda.org/isda-simm/ returned HTTP 403 to an automated fetch; no other isda.org page tried; no click-through, licence or registration screen seen or accepted | 2026-11-19 | **not read** |
| ISDA Risk Data Standards (CRIF) | not tried (same host) | 2026-11-19 | **not read** |
| Stage G SIMM-style IR delta, ruling G-43 | `specifications/06-risk/xva-framework.md`, `specifications/stage-g-rulings.md` | 2026-11-19 | read |
| K-8h gate note | `program/STAGE_K_W2_GATE.md` | 2026-11-19 | read |
| ORE survey section 5, licence register | `program/STAGE_K_ORE_SURVEY.md`, `oracle/LICENCES.md` | 2026-11-19 | read (ORE calibration files not opened) |
| SA-CVA clipped sum and radicand floor | `specifications/06-risk/cva-capital.md`, KR-62 | 2026-11-19 | read |

Everything the spec says about SIMM's structure is therefore **recalled, not read**; the spec's Sources section has the per-formula table.

## What was built (evidence class: measured, 2026-11-19, local laptop, not the acceptance machine)

| File | Role | Side |
|---|---|---|
| `tools/gen_simm_placeholder.py`, `specifications/tables/stage_k/simm-placeholder.json` | placeholder table and its generator (rule-made round numbers, header `placeholder: true`) | packet (table) |
| `tools/test_simm_placeholder.py` | fails if the table is not the generator's output or breaks the stated rule (5/5 PASS, incl. planted fault); added to `repo-gates.yml` | repo |
| `program/stage_h_blind_w2/simm_cases.py` | full inputs of the 29 cases | builds the packet |
| `program/stage_h_blind_w2/simm_make_packet.py` | writes the packet; never reads the expected file | builds the packet |
| `program/stage_h_blind_w2/simm_ref.py` | spec lane's own reference; writes `simm_expected.json`; also supplies the skeleton's keys with every leaf null | hidden |
| `program/stage_h_blind_w2/simm_expected.json` | 395 expected fields over 29 cases | hidden |
| `program/stage_h_blind_w2/simm_leaks.py` | leak check (copy of `k2_leaks.py`) | hidden |
| `program/stage_h_blind_w2/simm_compare.py` | compare, with `--self-test` (copy of `k2_compare.py`) | hidden |

Packet: `C:/Work/Claude/qf-blind/simm_packet/` (outside every worktree; not committed). 7 files: `README.md`, `specs/simm-placeholder.blind.md`, `rulings/stage-k-rulings-simm.blind.md`, `tables/simm-placeholder.json` (byte for byte), `inputs/K-8h.inputs.json`, `output_template.json` (field definitions and a results skeleton, every field null), `MANIFEST.sha256`.

**Packet MANIFEST.sha256 file hash: `f4eed98d89fbb07da596eaa28a12343b5e63999b4e3d63684aa839a85c493b70`.** Built from commit `4d4e7510` with `python -I program/stage_h_blind_w2/simm_make_packet.py . C:/Work/Claude/qf-blind/simm_packet`; a rebuild into a scratch folder gave the same manifest hash (reproducible), and `sha256sum -c MANIFEST.sha256` passed for all six files. Before handing the packet over, the coordinator checks that `sha256sum MANIFEST.sha256` still gives this value.

What was stripped: from the spec the sections "Worked example", "Hand cases" (every expected value and the arithmetic) and "Acceptance" (it names the gate count). Kept: header, label rule, plain idea, Sources (with the per-formula read/recalled table; no number), Scope, Formal statement (inputs, steps 1 to 9, outputs), Errors, Limits. From the rulings: KR-141 (gate classes).

## Fixed now, before any blind result exists

- **Compare mapping and tolerances: commit `4d4e7510`** (`simm_compare.py`). Mapping: each expected field path is read from the blind case object at the same path as the packet skeleton; the self-test fills the real skeleton from `simm_expected.json` and fails if any path is missing from it. Tolerance KR-139 (= KR-67): `|blind - expected| <= max(1e-12 |expected|, 1e-15)`; no per-case exception. Representation rules R1 to R4 as in `k2_compare.py` (an unknown extra level is a SHAPE error, exit 2, never a pass).
- **Dry self-test on fabricated data: 14/14 PASS** (`python -I program/stage_h_blind_w2/simm_compare.py . --self-test`): exact values all MATCH; 1e-14 relative noise all MATCH; 1e-9 perturbation every case MISMATCH; `outputs` wrapper, bare case map and case list all MATCH; an extra level above `cases` is SHAPE; two wrapper levels give no MATCH; the unfilled skeleton gives only MISSING; an absent case is MISSING; `true` for a number MISMATCH; a decimal string and a keyed bucket list MATCH; a sign-flipped clipped `S_b` and an unfloored `theta` MISMATCH; a missing product class MISSING.

## Spec arithmetic recheck

The 29 headline totals were recomputed from the closed-form expressions written in the spec's Hand cases column (for example `sqrt(6,880 + 30 sqrt(3,280))`, `sqrt(2,028,080) - 5 + (7/3) sqrt(44)`), independently of `simm_ref.py`: 29 of 29 agree with `simm_expected.json` within 1e-12 relative. This is our own second computation and counts as no outside check.

## Leak check

`python -I program/stage_h_blind_w2/simm_leaks.py . C:/Work/Claude/qf-blind/simm_packet > C:/Work/Claude/qf-blind/simm_LEAKS.tsv`: **0 hard leaks** (exit 0; list file SHA-256 `d2242d38517c1276ccefcae5a52224ae9471a8a46d189b93a24820add1eeaea6`, outside the packet). Hits: 189 PARAM (table values such as the weights 10 to 40 and thresholds 100 and 1000, which many single-factor outputs equal), 187 INPUT (coincidences with input amounts), 237 LOWINFO (values of at most two significant digits in rule prose: 2, 3, 5, 20, 100, 1000). No case id appears in any prose file.

Not searchable by digits: outputs equal to an input of the same case, and the null structure of the skeleton. The skeleton shows which buckets, factors and groups exist for each case, and whether a residual or a non-residual curvature part exists; that follows from the rules and inputs and carries no value.

## Cases that cannot count, fixed now

| Case | Why | Effect |
|---|---|---|
| simm_k-0028 | The stripped rules text states the answer: step 9 and KR-136 say no records gives `total = 0`, and the input has no records. | Compared, never counted (`NOT_COUNTED` in `simm_compare.py`). |

Fields that are implied but do not disqualify their case: concentration factors equal to 1 where the absolute group sum is at or below the threshold (step 2 states when `CR = 1`); single-factor buckets where `K_b = abs(WS)`. These cases still require the weights, the netting and every higher level.

**Value cases 29; eligible 28; matches needed 18** (60% of 29 is 17.4, rounded up; no class P or L check exists, KR-141). Below 18 counted matches, K-8h moves to a point release (owner).

## Procedure

1. Coordinator: check the manifest hash above; hand `C:/Work/Claude/qf-blind/simm_packet/` to a separate session on a different model from the spec lane (this lane is Claude Opus 5.5; for example Claude Sonnet, as in W1B and W2). The lane works in its own folder next to the packet, for example `C:/Work/Claude/qf-blind/simm_blind/`, and is given no repository path.
2. Blind lane, per the packet README: own reference, `notes.md`, `blind_results.json` from the skeleton at full binary64 precision, then `blind_results.sha256`, reporting the hash first.
3. Coordinator: commit and push the frozen results and hash (copy into `stage_k_blind/simm/` with `notes.md` and `blind_ref.py`) **before** running the compare. Rule any gap from `notes.md` before the compare, as a numbered ruling (KR-142 onward); a gap-decided field is compared but not counted.
4. Run `python -I program/stage_h_blind_w2/simm_compare.py . <frozen blind_results.json> > stage_k_blind/simm/compare_output.txt`. One run. A mismatch is investigated, never fixed by rerunning the blind lane.
5. Fill the results section below.

## Gate note: what a blind match on placeholder weights does and does not show

A match shows two things: the spec states the aggregation algebra unambiguously enough that a second model, reading only the rules, computes the same numbers; and the spec lane's arithmetic on the placeholder table is right. It does **not** show that our algebra is ISDA SIMM's algebra. Only a read of the methodology (which this lane could not obtain: isda.org refused the fetch) or a licensed ISDA test pack (which the owner has ruled out) could show that, and on placeholder weights even a correct algebra cannot reproduce any ISDA-printed number. A shared misreading of the methodology would pass the blind lane unseen, because the deriver reads our rules, not ISDA's.

Per formula (spec Sources table): F1 netting, F2 concentration factor, F3 weighted sensitivity, F4 intra-bucket aggregation with `f_kl`, F5 clipped sum and inter-bucket aggregation with `g_bc`, F6 residual bucket outside the root, F7 vega, F8 curvature (`SF`, squared correlations, `theta`, `lambda`, floor), F9 delta plus vega plus curvature, F10 aggregation across risk classes with `psi`, F11 sum over product classes: **all recalled, not read**. The forms of F2 and F3, and of F4 without `f_kl`, are also in the repository's stage G spec (read), which itself cites the methodology without having read it in that session (`xva-framework.md`: "none opened in this session"), so that is not independent evidence. The clipping in F5 is read only in Basel MAR50, a different framework. The radicand floors, `theta` at 0/0 and the empty-input rule are our rulings (KR-134 to KR-136), not SIMM statements. No formula on the page is in the "read" class with respect to SIMM. The docs must say "the algebra matches a blind re-derivation on placeholder weights; agreement with ISDA SIMM is not checked".

## Results

Not run. (Date, lane and model, packet manifest check, frozen hash and commit, gaps and rulings, compare run and output path, MATCH / MISMATCH / MISSING / counted, resolution of each mismatch: to be filled by the coordinator.)

## Results (2026-11-19; first and only compare run)

- Deriver: a separate subagent on Claude Sonnet 5.5 (spec and packet by Opus 5.5), given only the packet folder and its own folder; standard-library Python. It states it used no outside knowledge (every constant from the packet table) and read or tried to read nothing outside the two folders (its own statement, not independently logged). The coordinator checked the packet manifest hash f4eed98d... before the hand-over.
- Blind results as received: `stage_k_blind/simm/`, committed in a0d31fd1 before the compare. SHA-256 of `blind_results.json`: `55d6d5da719284fb5ab4e5de4f0939e15e12096fa125d99bd70f33b47f1de12e`, recomputed by the coordinator, equal to the deriver's hash file.
- Compare: `simm_compare.py` as fixed at 4d4e7510; output `stage_k_blind/simm/compare_output.txt`. Results not changed afterwards; no rerun.

| Item | Cases | MATCH | MISMATCH | Eligible | Counted | Needed |
|---|---:|---:|---:|---:|---:|---:|
| K-8h | 29 | 29 | 0 | 28 | 28 | 18 |

Not counted: simm_k-0028 (answer stated by the rules text). Ambiguities the deriver recorded (`stage_k_blind/simm/notes.md`), to be closed in the spec text: the equity vega within-bucket correlation between different issuers, and its square for curvature, is not exercised by any case (case 22 has one factor per bucket): ADD a case that exercises it before the spec is confirmed; interest-rate deltas under the Equity product class; single-bucket margin equals K_b; the net-zero group; `label` absent from the template.

**Gate status: NOT MET, whatever this table says.** The outside-check share is met (28 of 29), but the gate rule also requires a source actually read, and every SIMM formula in the spec is "recalled, not read" (isda.org returned HTTP 403 to the fetch on 2026-11-19). A blind match shows our statement of the aggregation is unambiguous and the arithmetic right. It does not show the aggregation is the methodology's. Until the methodology document is read and each formula's evidence class moves to "read", K-8h stays PROPOSED and is not part of any release.
