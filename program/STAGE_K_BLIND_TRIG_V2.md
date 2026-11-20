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

Run 2026-11-20, the first and only compare run (evidence class: measured; the hashes and the output are in the repository and can be rechecked).

- Deriver: a separate subagent on Claude Sonnet 5.5 (not Opus 5.5), given only the packet folder and its own folder `C:/Work/Claude/qf-blind/trig_k_v2/`; standard-library Python. Its own statements, not independently logged: it read nothing outside the two folders; the manifest matched on all 5 files.
- Frozen results: `stage_k_blind/trig_v2/` (with `notes.md` and `blind_ref.py`), committed in 59ef92f2 before the compare. SHA-256 of `blind_results.json` as handed back (CRLF line ends): `c7feabfb28bcdc91314dadcfc9f32dc81ebf06fa40f4503d90456cd1cebb21ea`, recomputed by the builder, equal to the deriver's hash. Git stores the file with LF line ends; the committed blob hashes to `24ab2462c1cdfcb18927e0953bf765a313b940fbf7b6e9367af83219269c3ee2`. The JSON content is the same.
- Compare: `python -I program/stage_h_blind_w2/trig_v2_compare.py . stage_k_blind/trig_v2/blind_results.json`, script and tolerances fixed in 1aaa62b4; output `stage_k_blind/trig_v2/compare_output.txt`; exit code 0.

| Item | Cases | MATCH | MISMATCH | Eligible | Counted | Needed for 60% | Share |
|---|---:|---:|---:|---:|---:|---:|---|
| K-4c (spec 1.1.0) | 14 | 14 | 0 | 13 | 13 | 9 | 13 of 14 (92.9%) |

Every output of every case matches; the largest relative difference on any number is 5.98e-15 (inside 1e-14 and 1e-11). trig_k-0004 matches too (fire false at equality) but is not counted, as fixed above. No mismatch, so nothing to resolve.

Readings the deriver recorded (`stage_k_blind/trig_v2/notes.md`), none ruled as a gap: threshold computed as `(k * sigma) * sqrt(d)`; in the KR-232 remainder loop the stop test before the 2^-500 rescale (the text's order); `nominal_rate` from its own 700-digit Decimal normal tail, rounded once; trig_k-0016 `nominal_rate` underflows to 0.0, which it took as the value. Its notes contain two loose remarks it flagged itself (a wrong degrees-of-freedom guess for one case); the results do not depend on them.

Credit: `verified_by` of the 13 counted cases records this MATCH through `oracle/python/gen_stage_k_w1.py` (`trig_v2_credit`; the earlier "not blind" notes restated as history); trig_k-0004 gets the entry but keeps its KR-13 "not blind" note. `python tools/outside_shares.py --check`: K-4c 13 of 14, 92.9%, met.

What this shows and what it does not: a second model, from the stripped 1.1.0 rules alone, reproduced every output, so KR-232's algorithm and KR-233's arithmetic are stated well enough to implement, and the goldens are not one author's slip. The deriver implemented the algorithm KR-232 gives; this does not show the t-distribution model is the right one (that is the acceptance simulation's job).
