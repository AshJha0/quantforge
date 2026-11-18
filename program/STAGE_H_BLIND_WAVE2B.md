# Stage H blind golden lane, wave 2b: record

Process: `program/STAGE_H_BLIND_LANE.md` (DR-H2, HR-31).

- Date: 2026-11-18.
- Spec lane: Claude Opus 5.5 (commit 4375f9be), dark_h and sor_h cases and expected outputs written first; pt_h goldens from the H-21 spec (commit eabbb443).
- Blind lane: separate context, given only packet 2b (dark-pool.blind.md, smart-order-router.blind.md, paper-trading.blind.md, stage-h-rulings-w1.md, -w1b.md, -h21.md; hashes in `stage_h_blind/wave2b/packet_MANIFEST.sha256`), built by `wave2_make_packet.sh <repo> <dir> b`. Own plain-Python reference; results frozen before comparison: `blind_results.json` SHA-256 `75856d3012237785452d033e262cb504407b53b621abef3f4007c02eae1352b0` (verified before comparing).
- Comparison: `program/stage_h_blind_w2/wave2_compare.py` (canonical JSON byte compare; then a second, shape-only pass: decimal-string normalisation, per-item `label` placement, and for pt_h a field-name map from the prose Expected column; values are never mapped). pt_h compares only the quantities the spec states; extra blind fields are not checked.

## Result: 10 MATCH, 19 SHAPE-ONLY, 0 VALUE MISMATCH (29 cases)

| Case | Result | Note |
|---|---|---|
| dark_h-0001, 0002, 0004 | MATCH | |
| dark_h-0003 | MATCH, NOT BLIND | golden-plan Content "limit below mid" hints at the no-fill part |
| dark_h-0007 | SHAPE-ONLY | blind put no per-fill `label`; values identical. Spec fix: label placement stated |
| sor_h-0001, 0002 | MATCH, NOT BLIND | golden-plan Content and the convergence table give the regime, so the allocation |
| sor_h-0003, 0005, 0006 | MATCH | 0006 is the two-venue cost-ordering case, full ranking equal |
| pt_h-0001..0006, 0010..0018, 0020 | SHAPE-ONLY | output shapes undefined in the spec; blind invented them; decimals normalised ("-0.60" vs "-0.6") |
| pt_h-0021..0023 | SHAPE-ONLY, NOT BLIND | the input names the corruption, which implies the failure reason |

Spec fixes (shape only, no value changed): `dark-pool.md` states that each markout element carries `label`; `paper-trading.md` gains the golden output shapes, using the blind lane's field names.

Blind-lane interpretations (its notes.md): 0002 financing 0 with no rate given; 0005 `cash_delta`; 0010..0017 defaults from 0010; ledger `hash` excluded from canonical bytes; 0022's second record invented. All agree with the spec-lane values.

Outside-checked by re-derivation (DR-H2): 23 of 29 (dark_h 4/5, sor_h 3/5, pt_h 16/19). Not counted: the six NOT BLIND cases.

Files: `stage_h_blind/wave2b/` (blind_ref.py, blind_results.json, blind_results.sha256, notes.md, packet_MANIFEST.sha256).

## Post-blind shape change (2026-11-18, H-13 implementation lane)

sor_h-0006: the input gains `"ranking":true`, the flag that asks for the `ranking` output (the conformance runner requires identical output keys, and the other sor_h inputs have the same shape). No expected value changed; the blind comparison above was made before this change and is not affected.

## pt_h field-by-field comparison (2026-11-18, paper CLI lane)

Rule now in force: a shape-only match counts only after a field-by-field comparison against the frozen file with a mapping written before comparing. Script `program/stage_h_blind_w2/pt_compare.py`, mapping in its docstring, committed before its first run; frozen file SHA-256 checked against the value above.

| Case | Verdict | Counted |
|---|---|---|
| pt_h-0001..0006, 0010..0017 | MATCH | yes (14) |
| pt_h-0018 | blind `E_UNSUPPORTED_OPERATION` equals the spec; not in the golden file (runner reads the code as not implemented) | no |
| pt_h-0020 | SHAPE MISMATCH: blind adds `verify` fields | no |
| pt_h-0021, 0022 | VALUE MISMATCH on `records` (blind counts all lines; the CLI counts records verified before the bad one, defined after the blind run); not blind anyway | no |
| pt_h-0023 | SHAPE MISMATCH: blind returns `hash` and `record` as well; not blind anyway | no |

This replaces the SHAPE-ONLY rows for pt_h above: pt_h outside-checked by re-derivation is 14 of 19, not 16.

## Blind lane 2: pt_h value cases with no blind check (2026-11-18, coordinator decision)

Why: the cases added after the first lane (pt_h-0030 to 0032, 0050, 0051, 0054) were hand only, and H-21 had fallen to 14 of 24 value cases (58.3%), under the 60% item floor.

- Packet: `wave2_make_packet.sh <stage-h3> <dir> paper2` (stripped `paper-trading.md` with HR-77 and HR-78, the paper section of `cli-contract.md`, `stage-h-rulings-h21.md`, inputs-only `pt_h.inputs.json`; passages naming a packet case's result removed by `paper2_blind.py`). Manifest copied to `stage_h_blind/paper2/packet_MANIFEST.sha256`. Leak list (`paper2_leaks.py`, outside the packet): 0 hard leaks. Building it found that the column-stripping awk split cells at escaped pipes and cut the HR-77 row; fixed before the packet was frozen (earlier packets had no escaped pipe, so they are unchanged).
- Blind lane: a separate Sonnet context with the packet only. Frozen output `stage_h_blind/paper2/blind_results.json`, SHA-256 `8964eebcaba91aeab49db01887c16b389dd8eb770f0485d7d1186c6cb6636627` (checked by the script; copied unedited with `blind_ref.py`, `notes.md`, `blind_results.sha256`). 6 cases.
- Compare: `python -I program/stage_h_blind_w2/paper2_compare.py .`, mapping committed before the first run (identity names; no `status` wrapper and key order are representation only; strings including decimals and hashes exact; JSON numbers at 1e-12 relative, 1e-15 absolute at 0). The first run crashed on pt_h-0054, where `records` is a count, not a list, in the not-blind check; that check was fixed (the mapping did not change) and the rerun of the script is the record.

| Case | Compare | Counts as blind-checked |
|---|---|---|
| pt_h-0030 | MATCH | no: LIT `child_id` was not specified in the packet; the lane assumed the order id, and the child id enters each FILL record's hash, the next `prev` and `head`, so the assumption decided those fields |
| pt_h-0031 | MATCH | no: same reason |
| pt_h-0032 | VALUE MISMATCH: FILL `child_id` (golden `P1.M`, `P1.L0`; blind `P1-LIT`, `P1-DARK`) and the hashes, `prev` and `head` that follow from them; every other field (fills, fees, trim, cash, position) agrees | no: packet gap. The router (`exec.sor.allocate`) and the dark simulator were not in the packet, so the lane guessed the allocation and invented the child ids. Who was wrong: the lane, on child ids only, and only because the packet lacked the specs that name them; the golden follows `smart-order-router.md` |
| pt_h-0050 | MATCH | yes |
| pt_h-0051 | MATCH | yes |
| pt_h-0054 | MATCH | yes |

Result: H-21 is 17 of 24 value cases blind-checked (70.8%), above the 60% item floor. The goldens record this in `verified_by` (`oracle/python/gen_stage_h_pt.py`); no expected value changed. No rerun.
