# Stage K: K-8i blind packet (risk.capital.leverage, risk.capital.large_exposures)

Written 2026-11-20 by lane k-r3-w2 (Claude Opus 5.5, branch `k-r3-w2`). The packet builder is not the blind lane. Pattern: `program/STAGE_K_BLIND_TLK_V2.md` (DR-H2).

## Why

Plain idea: `tools/outside_shares.py` counts K-8i (`lev_k`, `lex_k`) at 13 of 22 (59.1%), under the 60% per-item floor (evidence class: read, `oracle/OUTSIDE_SHARES.md` on k-r3-w2 60772ab9). Nine value cases carry no DR-H2 blind match: lev_k-0001 to -0005 (printed CRE99 and LEV30 figures, which the counting rule does not credit), lev_k-0012, -0013, lex_k-0008, -0009 (hand cases added by the wave 2b lane). A second model, given only the stripped rules and the case inputs, computes the nine cases again.

## What was built (evidence class: measured, 2026-11-20, local laptop, not the acceptance machine)

| File | Role | Side |
|---|---|---|
| `program/stage_h_blind_w2/levx_make_packet.py` | writes the packet from the spec "Formal statement" section, rulings KR-51, KR-53, KR-65, KR-66, KR-319, KR-320, KR-322 to KR-326, the two parameter tables and the case inputs; runs the leak check | builds the packet |
| `program/stage_h_blind_w2/levx_expected.json` | expected outputs and each case's `tolerance_limit`, copied from the goldens | hidden |
| `program/stage_h_blind_w2/levx_compare.py` | compare, with `--self-test` | hidden |

Packet: `C:/Work/Claude/qf-blind/k8i_packet/` (outside every worktree; not committed). **MANIFEST.sha256 file hash: `c60ccaf7e3ed52f471c76c1b2e17085f99bc5f48614933e33609b1c88adfa0ab`.**

What was stripped: the spec's sources table and CRE99 paragraph, worked examples, error list, golden table, acceptance and limits sections are not in the packet; from KR-320 the golden ids; from KR-324 the earlier blind lane's assumption and the golden remark; from KR-326 the boundary-golden remark.

- Leak check (inline, run by the builder): every expected number, as repr, 6 and 4 significant digits and integer forms, searched in every non-input packet file, skipping strings present in the case's own inputs. 6 hits, all coincidences: 0.03 and 0.4 (shares of lex_k-0008) are the leverage minimum and the commitment CCF of the other operation; "-8" (an output of lex_k-0009) matches the item names "K-8i" and "K-8d". None gives an answer; no case is excluded for them.
- Compare self-test on fabricated data: PASS (`python -I program/stage_h_blind_w2/levx_compare.py . --self-test`).

## Fixed now, before any blind result exists

This file, the compare script and the expected file are committed and pushed before the deriver is started; the results commit comes after, in a separate commit.

- Tolerances, the goldens' own, with the runner's rule (`|a - e| <= abs + rel * max(|a|, |e|)`): every number relative 1e-12, absolute 1e-15; strings, booleans, list lengths, list order and object keys exact.
- A case counts only if every output matches.
- **Eligible: 9 of 9.** K-8i after this lane: 13 + counted, of 22. Needed for 60%: 14 of 22 (13.2 rounded up), so at least 1 match. If fewer, the floor is recorded as missed.
- lev_k-0001 to -0005 are short (one netting set or one written credit derivative); they count if they match, under the rule as written, and this is stated, not hidden.
- The deriver must be a model other than Claude Opus 5.5. Hash first, commit the frozen results, then one compare run; a mismatch is recorded, never tuned.

## Results

Run 2026-11-20, the first and only compare run (evidence class: measured; hashes and output are in the repository).

- Time gap: packet, compare and tolerances committed and pushed in a735c83b (12:27:17 UTC); the deriver was started after the push; frozen results committed in 50b17b88 (12:29:18 UTC); the compare ran after that commit.
- Deriver: a separate subagent on Claude Sonnet (not Opus 5.5), given only the packet folder and its own folder `C:/Work/Claude/qf-blind/k8i_blind/`. Value source: exact `fractions.Fraction` arithmetic on the binary64 inputs, rounded once; binary64 comparisons where the rules state them. Its own statements, not independently logged: it read nothing outside the two folders; the manifest matched on all 7 files.
- Frozen results: `stage_k_blind/k8i/` (`blind_results.json`, `blind_ref.py`, `notes.md`). SHA-256 of `blind_results.json` as handed back: `600ed8d334cb6415a064de53ba9f5aeb27b681fb0d95f3d6dcb17410b31f452b`, recomputed by the builder, equal (git stores it with LF line ends).
- Compare: `python -I program/stage_h_blind_w2/levx_compare.py . stage_k_blind/k8i/blind_results.json`; output `stage_k_blind/k8i/compare_output.txt`.

| Item | Cases | MATCH | MISMATCH | Eligible | Counted |
|---|---:|---:|---:|---:|---:|
| K-8i `lev_k`, `lex_k` | 9 | 9 | 0 | 9 | 9 |

Assumptions the deriver recorded (`notes.md`): written credit derivative notionals in `derivatives` (KR-320); KR-53 greedy offsets; a group takes 15% when `bank_gsib` and any member is G-SIB (KR-324).

Credit: `oracle/python/gen_stage_k_w2b.py` adds `BLIND_K8I` to the nine cases (and drops the "not blind" note from the four hand cases). `python tools/outside_shares.py`: K-8i **22 of 22, 100.0%, met** (was 13 of 22, 59.1%).

What this does not show: lev_k-0001 to -0005 are one-line formulas, so their blind match adds little beyond the printed figures they already had; the deriver is a model, not a person.
