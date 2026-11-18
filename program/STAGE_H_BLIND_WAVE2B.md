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
