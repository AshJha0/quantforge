# Stage K: K-4c blind packet, version 2 (trig_k after KR-232 and KR-233)

Written 2026-11-20 by lane k-r2-blind (Claude Opus 5.5, branch `k-r2-blind`). The packet builder is not the blind lane. Pattern and process: `program/STAGE_K_BLIND_K5A_V2.md`, `program/STAGE_K_BLIND_K5A.md` and `program/STAGE_H_BLIND_LANE.md` (DR-H2).

## Why a second packet

Plain idea: the wave-1 blind lane (`program/STAGE_K_BLIND_W1.md`) checked trig_k-0001..0005 against the 1.0.0 `false_alarm_rate`, `2 Phi(-k)`. Ruling KR-232 (audit A, KA-A4, KA-A9) redefined `false_alarm_rate` as the Student-t rate `P(abs(T_(n-1)) > k)` and kept the old number as `nominal_rate`; KR-233 added the noise floor and fixed the arithmetic of `sigma`. The old match covers no case at every compared output any more, so `tools/outside_shares.py` counts K-4c at 0 of 14 (evidence class: read, `oracle/OUTSIDE_SHARES.md` on `k-r2` 0c225b83), below the 60% per-item floor. A second model, given only the stripped 1.1.0 rules and the case inputs, computes the 14 value cases again.

## What was built (evidence class: measured, 2026-11-20, local laptop, not the acceptance machine)

| File | Role | Side |
|---|---|---|
| `program/stage_h_blind_w2/trig_v2_cases.py` | inputs of every trig_k value case (status ok), read from `datasets/golden/stage_k/trig_k.json`, inputs only | builds the packet |
| `program/stage_h_blind_w2/trig_v2_make_packet.py` | writes the packet; never reads the expected file | builds the packet |
| `program/stage_h_blind_w2/trig_v2_expected.json` | expected outputs and each case's `tolerance_limit.relative`, copied from the goldens | hidden |
| `program/stage_h_blind_w2/trig_v2_leaks.py` | leak check | hidden |
| `program/stage_h_blind_w2/trig_v2_compare.py` | compare, with `--self-test` | hidden |

Cases: trig_k-0001..0005, 0009..0016 and 0021 (14 value cases). The seven error cases (0006..0008, 0017..0020) are out of scope, as in every value packet.

Packet: `C:/Work/Claude/qf-blind/trig_k_v2_packet/` (outside every worktree; not committed). Files: `README.md`, `specs/recalibration-triggers.blind.md`, `rulings/stage-k-rulings-trig.blind.md`, `inputs/K-4c.inputs.json`, `output_template.json`, `MANIFEST.sha256`. **MANIFEST.sha256 file hash: `5e5e7852d2e38c3b124e7e069f2b05e65dcfa323af6f9e7dc298165e3afddf1e`.** Built with `python -I program/stage_h_blind_w2/trig_v2_make_packet.py . C:/Work/Claude/qf-blind/trig_k_v2_packet`.

What was stripped. From the spec (1.1.0): the "Version 1.1.0 in brief" paragraph (audit figures), the n = 2 worked example (prints the trig_k-0010 rate), the case id in the far-tail sentence, and the sections "Golden value cases", the three "Acceptance" sections and "Limits and open issues". Kept: header, plain idea, formal statement, the 1.1.0 rate and noise-floor paragraphs, the operation section. Rulings copied: KR-6, KR-13, KR-232, KR-233. Cut inside them: from KR-13 the sentences naming trig_k-0004 and its blind status (the sentence "Implementations decide equality on the computed binary64 values" is kept); from KR-232 the case id of the far-tail case, the "Golden values" sentence and the acceptance paragraph; from KR-233 the golden list.

- Leak check: `python -I program/stage_h_blind_w2/trig_v2_leaks.py . C:/Work/Claude/qf-blind/trig_k_v2_packet`: **0 hard leaks**, exit 0. Searched: every expected number as printed, with the opposite sign, rounded to 3, 4, 6, 8, 10 and 12 significant digits, in e-notation and as a percentage; case ids in prose files. A first run flagged trig_k-0016 `threshold` 1000 in the inputs file: it equals the input `k` (sigma 1, d 1), so it is listed as allowed with 1.0 and 2.5. List `C:/Work/Claude/qf-blind/trig_k_v2_LEAKS.tsv`, SHA-256 `17a274bcdb3e04e399318baadff6909b4d492595793c3f0012d182b867cdec5c`.
- Compare self-test on fabricated data: **14/14 PASS** (`python -I program/stage_h_blind_w2/trig_v2_compare.py . --self-test`).

## Fixed now, before any blind result exists

- **Tolerances, the goldens' own, with the runner's rule** (`conformance/runner/runner.py`, `same_number`: `|a - e| <= abs + rel * max(|a|, |e|)`): `fire` exact boolean; `false_alarm_rate` class `tail_probability`, relative 1e-11, absolute 0 (the replay tables of the C++, Rust and Java builds); `sigma`, `threshold`, `nominal_rate` the case's `tolerance_limit`, relative 1e-14 (trig_k-0021: 3e-8, KR-233), absolute 0.
- A case counts only if every compared output matches.
- trig_k-0004: its `fire` is gap-decided by KR-13 (the equality case), as in wave 1. It is compared, but the case is **not counted** whatever the result (`R_NOCREDIT`).
- **Eligible: 13 of 14. Needed for the 60% per-item floor: 9 of 14.**
- The deriver must be a model other than Claude Opus 5.5 (the 1.1.0 spec, the fix and this packet were written by Opus 5.5). Procedure as version 1 of K-5a: hash first, commit the frozen results, then one compare run; a mismatch is recorded, never tuned and never fixed by rerunning the blind lane.

## Results

(Filled after the compare.)
