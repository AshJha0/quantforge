# Stage K: blind packet for the 13 aadadj_k value cases (K-8 AAD)

Written 2026-11-22 by lane k-v1-aad (Claude Opus 5.5). The packet builder is not the blind deriver. Pattern: `program/STAGE_K_BLIND_XVA.md` version 2 (DR-H2) and `program/STAGE_K_BLIND_K8.md` (leak check).

## Why

Plain idea: `aadadj_k` (`specifications/06-risk/xva-aad-adjustments.md`) has 13 value cases and 0 outside-checked (KR-268), so `tools/outside_shares.py --check` fails the D6 60% per-item floor. A second model, given only the stripped spec, the rulings that define the keys and the kink, and the case inputs, computes every output again. A case counts for the floor only if its `verified_by` records a DR-H2 MATCH and does not say "not blind" (`tools/outside_shares.py`, stage K rule; evidence class: read). The floor and the share rules are not changed.

## What was built (evidence class: measured, 2026-11-22, local laptop, not the acceptance machine)

| File | Role | Side |
|---|---|---|
| `program/stage_k_blind_aadadj/aadadj_make_packet.py` | writes the packet: spec with `strip` blocks, header, errors, envelope, convergence and limits sections removed, case ids and repo file names removed; rulings KR-262 to KR-265 rows; `inputs.json` (the golden `inputs` only); `template.json` (the expected object with every leaf null); README; MANIFEST | builds the packet |
| `program/stage_k_blind_aadadj/PACKET_README.md` | the deriver's instruction, copied into the packet | packet |
| `program/stage_k_blind_aadadj/aadadj_compare.py` | compare, with `--self-test` | hidden |
| `program/stage_k_blind_aadadj/aadadj_leaks.py` | leak check (model `k8_leaks.py`) | hidden |

Packet: `C:/Work/Claude/qf-blind/k_aadadj/` (outside every worktree; not committed). Files: README.md, spec.md, rulings.md, inputs.json, template.json, MANIFEST.sha256. MANIFEST.sha256 file hash: `5815ae6560f23ebd418eae44391cc779644232af12257a5b98ca9042f43d0c80`.

## Leak check

`python -I program/stage_k_blind_aadadj/aadadj_leaks.py . C:/Work/Claude/qf-blind/k_aadadj > C:/Work/Claude/qf-blind/k_aadadj_LEAKS.tsv`: **0 hard leaks** (exit 0; list file SHA-256 `feed11a58e2a3f68d2649120774d9066e4f791e03226ff493bd1e7251396a29a`, outside the packet). Searched: all 1,817 nonzero expected numbers as printed, with the opposite sign, comma-grouped and rounded to 0 to 4 decimals when three significant digits remain; every number of three or more significant digits in a prose file against the expected numbers (hard within 1%, near within 5%); case ids in prose; repo paths and file names. Result: 19 INPUT (a rounded expected number that equals an input value in `inputs.json`), 24 NEAR (all ruling numbers KR-161 to KR-267), 1 ALLOWED (`2008`, the citation year). A first run flagged `70.0` in `inputs.json` (an input `-70.0`, matched by sign) and `2008`; the input test was made sign-blind and the year listed, before this recorded run.

## Fixed now, before any blind result exists

- Tolerance: each golden's own `tolerance_limit` (KR-265), rule `|a - e| <= 1e-12 + 1e-10 max(|a|, |e|)`, on every value and gradient leaf. Strings, booleans and null exact. A missing leaf or an extra leaf is a mismatch.
- A case counts only if every leaf matches. All 13 value cases are comparable (every expected leaf is a frozen number).
- Self-test (`python -I program/stage_k_blind_aadadj/aadadj_compare.py . --self-test`): PASS. The goldens against themselves give 13 of 13; a planted pass (cva moved by 4e-11 relative, inside the tolerance) still matches; three planted fails (a gradient entry moved by 1e-9 relative, a missing `ene` array, an extra key) give exactly 3 MISMATCH.
- The deriver is a model other than Claude Opus 5.5, reads only the packet folder, uses Python with mpmath and numpy. It writes `answers.json`, `derive.py` and `notes.md` in the packet folder and reports the SHA-256 of `answers.json`. The builder copies those files unchanged to `stage_k_blind/aadadj/`, commits them, then runs the compare once: `python -I program/stage_k_blind_aadadj/aadadj_compare.py . stage_k_blind/aadadj/answers.json > stage_k_blind/aadadj/compare_output.txt`. No rerun, no tolerance change.
- Credit: each matched case gets a `verified_by` entry carrying "DR-H2" and "MATCH" in `datasets/golden/stage_k/aadadj_k.json` through its generator; a mismatch is recorded as one and not counted.

Known limits, stated before the run: the deriver reads the same rules this lane wrote, so a match shows the rules are unambiguous and the arithmetic agrees, not that the rules read their sources correctly (KF-26). The spec's backward-pass text describes the method; the deriver may use it or not. The inputs in `inputs.json` are the goldens' own, so an error in an input would be shared by both sides.

## Results

Run 2026-11-22, the first and only compare run (evidence class: measured).

- Order: packet, compare and tolerances pushed in 2996d142; the deriver ran after; its files copied unchanged to `stage_k_blind/aadadj/` (`answers.json`, `derive.py`, `notes.md`) and committed in 1b391b88; the compare ran once after that commit. `answers.json` SHA-256 as handed back `60e951d5ba64f66e8ec5d638025a74e7bb1e20f3fcf7f3020997b85b5c90dea8`, verified before the copy (git stores LF, so a checkout may hash differently, as KF-25).
- Deriver: a separate subagent on Claude Sonnet 5.5, given only the packet folder (its own statement, not logged). MANIFEST matched on all five files (its `notes.md`).
- Output `stage_k_blind/aadadj/compare_output.txt`: **13 MATCH of 13**, no mismatch, no missing or extra leaf.
- Credit: `oracle/python/gen_stage_k_aadadj.py` adds `blind re-derivation DR-H2 2026-11-22 (program/STAGE_K_BLIND_AADADJ.md): MATCH` to the `verified_by` of the 13 value goldens (only that label changed in `aadadj_k.json`). `tools/outside_shares.py --check` passes; K-8 AAD 13 of 13 (100.0%), stage K 184 of 231 (79.7%) (`oracle/OUTSIDE_SHARES.md` at the time; the generated share after the merge of `k-v1` is 184 of 232, 79.3%, and 184 of 236, 78.0%, after `g41tiny_k` on `k-v1-pt`; pre-tag audit PT-9c).

**Method, and what it makes independent.** The deriver used finite differences, not an adjoint: the G-41 formulas in mpmath at 60 digits and, for every gradient entry, the KR-265 Richardson central bump with the overlap branch fixed in binary64. No closed-form adjoint was written on its side. So the check is independent in code and in model (Sonnet 5.5 against Opus 5.5 for the goldens), but it uses the same bump definition as the golden check (KR-265). It does not test the backward pass text in the spec; it tests the values the goldens hold.

Deriver ambiguities (`notes.md`): the flat hazard entry moves every bucket together, with the floor; a bucket entry moves that bucket's floor too; the `wrt` case follows the template's reduced keys; at `h = 0` the central bump steps into negative hazard (the analytic formula's derivative, as KR-264 (b)).

What this does not show: same model family as the author; the deriver read the rules this lane wrote, so the match shows the rules are unambiguous and the arithmetic agrees, not that they read their sources correctly (KF-26). No second review (owner decision 2026-11-18).
