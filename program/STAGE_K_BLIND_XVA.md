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
