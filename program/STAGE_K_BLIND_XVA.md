# Stage K: xVA extras blind packet, version 1 (K-8b specs)

Written 2026-11-20 by lane k-xva-spec (Claude Opus 5.5). The packet builder is not the blind lane. Pattern: `program/STAGE_K_BLIND_TLK_V2.md` on k-r2 (DR-H2). Gate: `program/STAGE_K_XVA_GATE.md` section 5 (41 B candidates).

## Why

Plain idea: the K-8b specs have 41 value cases marked B (blind candidate) and no outside check. A second model, given only the specs with every strip block removed and the case inputs, computes the cases again.

## What was built (evidence class: measured, 2026-11-20, local laptop, not the acceptance machine)

| File | Role | Side |
|---|---|---|
| `program/stage_k_blind_xva/xva_make_packet.py` | writes the packet from the six spec files with `strip` blocks and the "Outside-check design" section removed; never reads the expected file | builds the packet |
| `program/stage_k_blind_xva/xva_expected.json` | expected outputs copied from the specs' "Golden cases" tables, with each spec's own tolerance | hidden |
| `program/stage_k_blind_xva/xva_compare.py` | compare, with `--self-test` (PASS) | hidden |

Packet: `C:/Work/Claude/qf-blind/xva_v1_packet/` (outside every worktree; not committed). MANIFEST.sha256 file hash: `d38a2aef5564aae17e5b8b07e048643352b0c79f2770a04f331bb55a20c580f7`. `program/STAGE_K_SOURCES_XVA.md` is excluded (it prints reference values, gate file section 5).

Leak check (grep of every non-integer expected value at 4 or more digits in the packet): no hit. Integer outputs (MPoR floors, EEPE 12 and 15) are not searchable this way.

## Fixed now, before any blind result exists

- Tolerances, the goldens' own (spec Acceptance A1; AAD A2), rule `|a - e| <= abs + rel * max(|a|, |e|)`: aadx rel 1e-10 abs 1e-12; colva, mva, str, fva rel 1e-12 abs 1e-12; mpor rel 1e-12 abs 1e-9. Strings and booleans exact.
- A case counts only if every output matches.
- **Comparable: 21 of the 41 B candidates**, the ones whose expected value is printed as a number in the spec: aadx_k-0001; colva_k-0001 to 0003; mva_k-0001 to 0003; str_k-0001 to 0004; mpor_k-0001 to 0006; fva_k-0001 to 0003 and 0006.
- **Not comparable: 20**, expected value written as "oracle" or "as above" (no frozen number): aadx_k-0002 to 0008, colva_k-0004 to 0006, mva_k-0004, 0005, str_k-0005, 0006, clp_k-0001, fva_k-0004, 0005, shk_k-0001, 0002, wwr_k-0010. They need the oracle lane first.
- Known risk, stated before the run: str_k-0001 and 0002 print `k_current` and `k_stressed` to 4 or 5 digits (2.828, 3.696, 1.2852, 1.2488). If these are rounded, the 1e-12 tolerance fails them; the miss is recorded, not tuned.
- No xVA golden file exists on this branch (specs PROPOSED, nothing implemented), so there is no generator to credit matches through; the credit is recorded here and in the gate file for the implementation lane.
- The deriver is a model other than Claude Opus 5.5. Hash first, commit the frozen results, then one compare run.

## Results

Run 2026-11-20, the first and only compare run (evidence class: measured).

- Time gap: packet, compare and tolerances pushed in 54a3a328 (12:23:12 UTC); deriver started after; frozen results committed in d9cbc596 (12:24:38 UTC); compare ran after that commit.
- Deriver: a separate subagent on Claude Sonnet, given only the packet folder and its own output folder, told not to read the repository (its own statement, not logged). Method: its own Python at 60-digit mpmath, rounded once to binary64. Manifest matched on all files.
- Frozen results: `stage_k_blind/xva_v1/` (`blind_results.json`, `blind_ref.py`, `notes.md`). SHA-256 as handed back (CRLF): `d4a1a655ceba7eb41443b4407948690cb29b7ee85fe935d3a6d46093edd896b3`; git stores LF, so `sha256sum -c` in a checkout differs (as KF-25).
- Output: `stage_k_blind/xva_v1/compare_output.txt`. **18 MATCH, 3 MISMATCH of 21.**

| Item | Compared | MATCH | MISMATCH | Outside share after (value cases) |
|---|---:|---:|---:|---|
| AAD (`aadx`) | 1 | 0 | 1 | 0 of 12, 0% (not met) |
| ColVA | 3 | 3 | 0 | 3 of 10, 30% (not met) |
| MVA | 3 | 3 | 0 | 3 of 10, 30% (not met) |
| Stressed exposure | 4 | 4 | 0 | 4 of 8, 50% (not met; 5 needed) |
| MPoR (5 L + B) | 6 | 6 | 0 | 11 of 13, 85% (met) |
| Funding asymmetric | 4 | 2 | 2 | 2 of 10, 20% (not met) |

The three mismatches are all null outputs, not wrong numbers: aadx_k-0001, fva_k-0003 and fva_k-0006 depend on the inputs of `xvaadj_g-0001` and the `xva.adjustments.value` formulas (stage G), which the packet did not carry. That is a packet gap of this builder's making; they stay recorded as MISMATCH under the rule, and a version 2 packet that adds the G-41 spec and the xvaadj_g-0001 inputs is the fix. The str_k-0001 and 0002 printed 4-digit `k` values matched at 1e-12, so they were exact.

Deriver ambiguities (`notes.md`): fva survival taken at `t_(i-1)` as written, mva at `t_i` as written (the two specs differ; flag for the spec owner); beyond-pillar extrapolation unused by any case; ties go to "current".

Credit: no xVA golden or generator exists on this branch, so matched cases carry `BLIND_XVA` here only; the implementation lane must tag the 18 matched cases when it writes the goldens. `tools/outside_shares.py` does not yet see these items.

What this does not show: same model family as the author (Sonnet against Opus 5.5); the match shows the rules are unambiguous and the arithmetic agrees, not that the rules read the sources correctly (KF-26).

## ORE licence wording (evidence class: read)

`oracle/LICENCES.md` records ORE 1.8.17.0 as Modified BSD (3-clause), from `license.txt` read through the GitHub API on 2026-11-12. The two specs that said "Apache 2.0" (`cva-capital.md`, `xva-exposure-portfolio.md`) now say Modified BSD and state the use: an outside oracle run locally on inputs we generate, no ORE code kept. Open for the coordinator: whether the PyPI wheel carries the same licence as the repository tag was not read on this branch.

## Version 2 (2026-11-20, lane k-xva-spec, Claude Opus 5.5 as builder)

**Why.** Version 1 lacked the G-40 and G-41 rules and the `xvaadj_g-0001` inputs (3 MISMATCH, all null outputs), and 20 of the 41 B candidates had no frozen value. Version 1 and its frozen results (`stage_k_blind/xva_v1/`) are unchanged.

**What changed before the run (evidence class: measured unless stated).**
- Oracle values for all 41 B candidates, and the 23 other spec value cases computable without ORE, by `oracle/python/gen_stage_k_xva_k8b.py` (mpmath 50 digits, rounded once). Held as candidate goldens under `oracle/xva_k8b_candidates/` (KR-299), because the conformance runner fails on an unimplemented operation. The generator first reproduces `xvaadj_g-0001`, `-0002`, `collexp_g-0004` and `expsim_g-0003`, and it reproduces every value printed in the specs except the three that the survival ruling moves.
- Proposed rulings KR-296 (one survival point, the bucket start, for FCA, FBA, MVA) and KR-297 (ColVA `BOTH` likewise), and KR-298 (the spec gaps an implementer needs), in `specifications/stage-k-rulings-xva.md`. The specs carry them.
- Packet builder `program/stage_k_blind_xva/xva_make_packet_v2.py`: eight stripped specs, a stage G excerpt (formal statements only), the ruling rows with their numerical-effect sentences removed, `inputs.json` (inputs only, read from the candidate files), `template.json`, `fixed_inputs.json` (the `expsim_g-0003` EE held fixed for aadx_k-0008). Packet at `C:/Work/Claude/qf-blind/xva_v2_packet/` (not committed). MANIFEST.sha256 file hash: `2fb743050b478768edc3b8ce71d98ac9b605b093136f2e15820b66c7e8463d6b`. Leak check (every non-integer expected leaf, full and 8-character prefix, in every packet file except the inputs): 0 hits.
- Compare `program/stage_k_blind_xva/xva_compare_v2.py` (`--self-test` PASS), each case at its own `tolerance_limit` (spec A1; AAD 1e-10 relative), every leaf must match. Commit 24979d8e (18:00:32 UTC), before the deriver started.

**Run.** Deriver: a separate subagent on Claude Sonnet, given only the packet folder and its own output folder, told not to read the repository (its own statement, not logged); its own Python at 60-digit mpmath, gradients by 4th-order central differences at 60 digits. Manifest verified. Frozen results `stage_k_blind/xva_v2/` committed in 9930309c (18:08:43 UTC); SHA-256 as handed back (CRLF) `0111c2ed64de2b3005ec4ba603d9dcf4ec64883b4e0a89302be8b01e76ba804e`. One compare run after that commit: `stage_k_blind/xva_v2/compare_output.txt`, **41 MATCH of 41**, no null leaf.

| Item | Value cases | Outside-checked once implemented | Share | Floor 60% | Still missing |
|---|---:|---|---:|---|---|
| AAD | 12 | 8 B (aadx 0001-0008) | 66.7% | met | ORE bump cases 0009-0012 not run |
| ColVA | 10 | 6 B | 60.0% | met (exactly) | ORE `colva` 0007-0010 not run |
| MVA | 10 | 5 B | 50.0% | **NOT MET** | one ORE `dimModel Flat` case (0006 or 0007) must pass; WSL run not done |
| WWR copula | 10 | 9 L + 1 B | 100% | met | the D6 reading of L (gate file section 3.1) |
| Stressed exposure | 8 | 6 B | 75.0% | met | ORE `BaselEEPE` definition unread |
| MPoR and close-out | 14 counted from the spec (the gate table says 13) | 7 B + 5 L | 85.7% | met | ORE close-out cases clp 0002, 0003 |
| Funding | 10 | 6 B | 60.0% | met (exactly) | ORE `fva` 0007-0010 |
| Shock library | 6 | 2 B | 33.3% | **NOT MET** | at least 2 ORE cases (WSL) |

These shares hold only once the implementation lane writes the goldens with the `DR-H2 ... MATCH` mark (`tools/outside_shares.py` counts that mark for stage K); today `tools/outside_shares.py` sees none of these suites. The v1 credits of mva_k-0001, 0002 and colva_k-0002 were for the old survival point and are replaced by the v2 matches.

**What this does not show.** Same model family as the builder (Sonnet against Opus 5.5); the match shows that the packet's rules are unambiguous and the arithmetic agrees, not that the rules read the sources correctly (KF-26). The deriver read KR-296 and KR-297, so the match does not test the survival choice itself. The case inputs in `inputs.json` were written by the builder from the case tables; an error there would be shared by both sides.
