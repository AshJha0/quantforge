# Stage K: K-5a blind packet, version 2 (prepared, not run)

Written 2026-11-19 by the audit-response lane (Claude Opus 5.5, branch `k-audit-a`). The packet builder is not the blind lane. Pattern and process: `program/STAGE_K_BLIND_K5A.md` (version 1) and `program/STAGE_H_BLIND_LANE.md` (DR-H2).

## Why a second packet

Ruling KR-234 (audit A finding KA-A6) changed the definition of the `bound` output of `risk.intraday.delta_gamma_bound`: it is now the Lagrange bound plus a binary64 rounding allowance, so that the bound holds for small moves too. The version 1 blind lane (5 of 5 MATCH) re-derived the old formula, so the `bound` of idr_k-0001 to 0005 is not blind any more (`06-risk/intraday-risk-bounds.md` 1.1.0). `estimate_pnl` did not change and keeps its version 1 match. The new values differ from the old by at most 1.7e-10 relative (KR-239), so a version 1 answer would still pass the 1e-9 tolerance on those five cases; the new small-move cases idr_k-0008 to 0010 are where the two formulas differ by orders of magnitude, which is what makes version 2 a real check of KR-234.

## What changed against version 1 (evidence class: measured, 2026-11-19, local laptop, not the acceptance machine)

| File | Change |
|---|---|
| `program/stage_h_blind_w2/k5a_v2_cases.py` | 11 value cases: idr_k-0001..0005, 0008..0010, 0012..0014. idr_k-0011 (h = 0, both outputs 0, stated by the formula) is left out |
| `program/stage_h_blind_w2/k5a_v2_make_packet.py` | the 1.1.0 spec; cuts its "Version 1.1.0 in brief" paragraph and the worked example of idr_k-0008 (they print case values); three acceptance sections cut; rulings KR-7, KR-10, KR-15, KR-17 and KR-234, with KR-234's "Effect" and "Acceptance" cut (KR-239 is not copied: it only corrects a figure in the cut part) |
| `program/stage_h_blind_w2/k5a_v2_expected.json` | expected values copied from `datasets/golden/stage_k/idr_k.json` after KR-234 (hidden) |
| `program/stage_h_blind_w2/k5a_v2_compare.py`, `k5a_v2_leaks.py` | copies of the version 1 scripts that read the v2 files; the self-test count of "bounds below 400" is 8 for these cases (idr_k-0004, 0013 and 0014 are above) |

Packet: `C:/Work/Claude/qf-blind/k5a_v2_packet/` (outside every worktree; not committed). **MANIFEST.sha256 file hash: `ceebd55713178170fc38892173d66fd8f8e81205ee6ec0e4ebb30cc0135740ba`.** Built with `python -I program/stage_h_blind_w2/k5a_v2_make_packet.py . C:/Work/Claude/qf-blind/k5a_v2_packet`.

- Leak check: `python -I program/stage_h_blind_w2/k5a_v2_leaks.py . C:/Work/Claude/qf-blind/k5a_v2_packet`: 0 hard leaks; 11 ALLOWED (the KR-10 label, stated by the rules). List `C:/Work/Claude/qf-blind/k5a_v2_LEAKS.tsv`, SHA-256 `a6dc488381490662b95b421d4b0ffd25fad6babfe8ef450d58e951e4adc915ff`.
- Compare self-test on fabricated data: 16/16 PASS (`python -I program/stage_h_blind_w2/k5a_v2_compare.py . --self-test`). Mapping and tolerance as version 1 (1e-9 relative on `estimate_pnl` and `bound`; `label` compared, no credit).
- Not repeated: the version 1 `k5a_recheck.py` evaluates the old bound and was not copied; the generator `oracle/python/gen_stage_k_w1.py` asserts every new case against a 50-digit revaluation instead (our own oracle, no outside credit).

## Fixed now, before any blind result exists

Eligible: 11 of 11; needed for the 60% floor: 7. The deriver must be a model other than Claude Opus 5.5. The procedure of version 1 applies unchanged (hash first, then compare). Until it runs, the K-5a outside share for `bound` is 0 of 5 on the old cases, and the outside-share inputs must say so (`tools/outside_shares.py` belongs to another lane tonight; the change it needs is listed in the audit response).
