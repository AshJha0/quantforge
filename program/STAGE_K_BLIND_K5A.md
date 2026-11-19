# Stage K: blind re-derivation (DR-H2) of the five K-5a value cases

Written 2026-11-19 by the packet builder (Claude Opus 5.5, branch `k-w1-fu`). The packet builder is not the blind lane and ran no derivation beyond rechecking the goldens at 50 digits. Process: `program/STAGE_H_BLIND_LANE.md` (DR-H2); pattern of `program/STAGE_K_BLIND_W2.md` (branch `k-w2-spec`). Scope: idr_k-0001..0005 of `risk.intraday.delta_gamma_bound` (`specifications/06-risk/intraday-risk-bounds.md`). Status: **run 2026-11-19: 5 of 5 MATCH** (results below).

## Plain idea

K-5a has 0 of 5 value cases with an outside check (`program/STAGE_K_W1_HANDOVER.md`): the wave-1 blind lane checked the four bounds only to 6 decimals (5e-7 absolute), and idr_k-0005 was not in its packet. A second model, which never sees our numbers, reads only the stripped rules and computes the five cases itself. It freezes its answers with a hash before anyone compares. A script, fixed now, compares them with the goldens at full binary64 precision and the spec's tolerance.

## What was built (evidence class: measured, 2026-11-19, local laptop, not the acceptance machine)

| File | Role | Side |
|---|---|---|
| `program/stage_h_blind_w2/k5a_cases.py` | inputs of the five cases, read from `datasets/golden/stage_k/idr_k.json` (inputs only) | builds the packet |
| `program/stage_h_blind_w2/k5a_make_packet.py` | writes the packet; never reads the expected file | builds the packet |
| `program/stage_h_blind_w2/k5a_expected.json` | expected `estimate_pnl`, `bound`, `label` per case, copied from the goldens (mpmath 50 digits, rounded once to binary64) | hidden |
| `program/stage_h_blind_w2/k5a_recheck.py` | builder's 50-digit recheck of every expected number, and of remainder over bound | hidden |
| `program/stage_h_blind_w2/k5a_leaks.py` | leak check (model `k2_leaks.py`) | hidden |
| `program/stage_h_blind_w2/k5a_compare.py` | compare, with `--self-test` | hidden |

Packet: `C:/Work/Claude/qf-blind/k5a_packet/` (outside every worktree; not committed). 5 files plus the manifest: `README.md`, `specs/intraday-risk-bounds.blind.md`, `rulings/stage-k-rulings-k5a.blind.md`, `inputs/K-5a.inputs.json`, `output_template.json` (field definitions and a skeleton with every field null), `MANIFEST.sha256`.

**Packet MANIFEST.sha256 file hash: `1a9c4cbc710ce17b634032696c26d6be04db699cd19071a4e431e1a8b5722529`.** Built with `python -I program/stage_h_blind_w2/k5a_make_packet.py . C:/Work/Claude/qf-blind/k5a_packet`; a rebuild into a scratch folder gave the same manifest hash (reproducible). Before handing the packet over, the coordinator checks that `sha256sum MANIFEST.sha256` still gives this value.

What was stripped. From the spec: the sections "Golden value cases" (the case table with every expected value and the check columns, both `blind:strip` blocks with the hand derivation of idr_k-0001 and the idr_k-0005 values, and the error cases), "Acceptance" and "Acceptance evidence". Kept: header, plain idea, formal statement (the formula, `M3`), the operation section (inputs, outputs). From the rulings only KR-7, KR-10, KR-15 and KR-17 are copied, as their own ruling rows (the confirmation table rows are not copied). Cut inside them: from KR-15 the sentence naming idr_k-0005 and its short 2-year leg; from KR-17 everything from "The 1,000-move acceptance is therefore also checked" to the end of the row (the acceptance results: violations, rounding share 2.3e-8, margin 0.62, and the history of the golden bounds). KR-12 (the `E_DOMAIN` code, which names idr_k-0006) is not copied: error cases are out of scope.

## Fixed now, before any blind result exists

- **Compare mapping and tolerances: the commit that adds this file** (`k5a_compare.py`). Mapping: `estimate_pnl`, `bound`, `label` at the top level of each blind case object, the packet skeleton's shape. Tolerance from the spec ("Golden value cases": "Tolerance 1e-9 relative on `estimate_pnl` and `bound`"; the goldens' `tolerance_limit` relative 1e-9, absolute 0): `|blind - expected| <= 1e-9 |expected|`, against the expected values at full binary64 precision; `label` exact. The compare prints the relative difference of every number. For the four bounds below 400 this is tighter than the wave-1 check (1e-9 x 17.06 = 1.7e-8 absolute against 5e-7; for idr_k-0003, 2.7e-10). For idr_k-0004 (bound 2132.11) 1e-9 relative is 2.1e-6 absolute, looser than 5e-7 absolute; the spec's tolerance is used as written, and the printed relative difference shows how close the match is.
- Representation rules R1, R2, R4 of `k2_compare.py` (top-level shape, one wrapper level, a number as a decimal string); an extra level above `cases` is a SHAPE error, exit 2, never a pass.
- **Dry self-test on fabricated data: 16/16 PASS** (`python -I program/stage_h_blind_w2/k5a_compare.py . --self-test`): exact values, 1e-12 and 0.9e-9 relative noise all MATCH; 2e-9 relative every case MISMATCH; a bound off by 4e-7 absolute (which passed the wave-1 check) MISMATCH on the four cases with bound below 400 and MATCH on idr_k-0004 (see above); one bound off by 1e-6 only that case MISMATCH; a sign flip MISMATCH; `outputs` wrapper, bare case map and case list all MATCH; an extra level SHAPE; two wrapper levels no MATCH; the unfilled skeleton all MISSING; an absent case MISSING; a label with a trailing space and `true` for a number MISMATCH; a decimal string MATCH.

## Spec arithmetic recheck

`python -I program/stage_h_blind_w2/k5a_recheck.py .`: every expected number reproduces exactly (relative difference 0 on all ten numbers) when recomputed at 50 digits from the binary64 inputs and rounded once. Exact remainder over bound: 0.988, 0.963, 0.997, 0.940, 0.917 (all at most 1, as Taylor's theorem requires). This is our own second computation and counts as no outside check.

## Leak check

`python -I program/stage_h_blind_w2/k5a_leaks.py . C:/Work/Claude/qf-blind/k5a_packet > C:/Work/Claude/qf-blind/k5a_LEAKS.tsv`: **0 hard leaks** (exit 0; list file SHA-256 `48d3907fe36c1767a0d6812c2cb9b46437651d84d2fe4eb2fcbae57fe4570de2`, outside the packet). Searched: every expected number and the spec's check-column intermediates recomputed at 50 digits (V(y), exact V(y + h), the estimate of V(y + h), the exact P&L, est - exact, error over bound, |h|^3), each as printed, with the opposite sign, comma-grouped, and rounded to 2, 3, 4 and 6 decimals when that keeps at least three significant digits (6 because the wave-1 packet carried the bounds at 6 decimals). Hits: 5 ALLOWED, all the label string in KR-10. No case id appears in any prose file. A first build copied the confirmation-table rows of KR-7 and KR-10 instead of the ruling rows (the script kept the last row with each number); fixed to keep the first, before the leak run that is recorded here.

## Cases and fields that cannot count, fixed now

- No whole case is excluded: none of the five is stated by the rules text, and idr_k-0005 (filled by the oracle lane, never in a blind packet) is eligible like the others.
- `label` of every case is stated by KR-10. It is compared (exact) but gives no credit on its own (`R_FIELDS` in `k5a_compare.py`); each case counts on `estimate_pnl` and `bound`.

**Eligible: 5 of 5. Needed for the 60% per-item floor: 3.**

The deriver must be a different model from the spec lane, the oracle lane and this builder, which are all Claude Opus 5.5 (trailers of 1bbfdf7e, a5edea3b, 28db90df and this branch). A session that took part in the wave-1 blind lane may be used only as a new session given nothing but the packet.

## Outside check by an independent library: what exists and what may count

Plain answer: no. Evidence class: read (`tools/outside_shares.py` docstring and `load_stage_k`, ruling KR-11).

- The 1,000-move check at 50 digits (`oracle/python/check_stage_k_idr_moves.py`, `oracle/IDR_K_MOVES_CHECK_W1.json`) uses mpmath, which is a third-party library independent of our four builds. But it evaluates the spec's own formulas (estimate, revaluation, bound) in mpmath arithmetic. Under D6 that is `reimplementation` ("the spec formula written again around a library call"), not `library-primitive` ("numpy or scipy numerics applied to a different formulation of the same problem"). It also checks the inequality on the 1,000 acceptance moves, not the compared outputs of the five golden cases, and D6 counts a case only if every compared output is checked. KR-11 says the same: the mpmath values are our own oracle. It may not count.
- An interval-arithmetic (`mpmath.iv`) evaluation of `|estimate - revaluation| <= bound` on the five cases would be the same class for the same reasons: a stronger check of the inequality, not an outside check of the outputs.
- A route that might qualify was considered and not built: `estimate_pnl` from library numerical derivatives (a different formulation of V' and V'') and `M3` from a library bounded maximiser of |V'''| over the segment. The bound would still be `|h|^3 M3 / 6`, the spec's own arithmetic, and a numerical third derivative at 1e-9 relative is doubtful. Whether such a check is `library-primitive` is a reading of D6 the coordinator would have to rule; this lane does not stretch it. The blind re-derivation above is the route that the rules already count (DR-H2, `load_stage_k`).

## Procedure

1. Coordinator: check the manifest hash above; hand the folder `C:/Work/Claude/qf-blind/k5a_packet/` to a separate session on a model other than Claude Opus 5.5. The lane works in its own folder next to the packet, for example `C:/Work/Claude/qf-blind/k5a_blind/`, and is given no repository path.
2. Blind lane, per the packet README: own reference (`blind_ref.py`, no repository imports), `notes.md`, `blind_results.json` filled from the skeleton at full binary64 precision, then `blind_results.sha256`, the hash reported first in its hand-back.
3. Coordinator: commit and push the frozen `blind_results.json` and its hash (copy into `stage_k_blind/k5a/` with `notes.md` and `blind_ref.py`) **before** running the compare. Rule any gap from `notes.md` before the compare; a gap-decided field is compared but not counted.
4. Run `python -I program/stage_h_blind_w2/k5a_compare.py . <frozen blind_results.json> > stage_k_blind/k5a/compare_output.txt`. One run. A mismatch is investigated, never fixed by rerunning the blind lane.
5. On MATCH: change `verified_by` of each matched case in `datasets/golden/stage_k/idr_k.json` so that it records the DR-H2 MATCH at 1e-9 relative and no longer says "only to 6 decimals" or "not blind" (that is what `tools/outside_shares.py` `load_stage_k` reads), regenerate with the after-spec-edit generators, and fill the results section below.

## Results (run of 2026-11-19, the first and only compare run)

Facts from the coordinator (evidence class: the coordinator's report, read; the hashes and the compare output are in the repository and can be rechecked).

- Deriver: a separate subagent on Claude Sonnet 5.5 (a different model from the spec lane, the oracle lane and this builder, all Claude Opus 5.5), given only the packet folder and its own folder `C:/Work/Claude/qf-blind/k5a_blind/`. It states that it read, and tried to read, nothing outside the two folders; that is its own statement, not independently logged.
- Packet: the coordinator checked the manifest hash `1a9c4cbc710ce17b634032696c26d6be04db699cd19071a4e431e1a8b5722529` before the handover; the deriver's `notes.md` records that all 5 files matched the manifest.
- Frozen results: `stage_k_blind/k5a/blind_results.json`, SHA-256 `e31fc25071f71ac5d01931297e119060510542516a0c504d8aa45910d1d211eb` (recomputed by the coordinator, equal to the deriver's `results.sha256`), committed in b75776d5 before the compare. The deriver's script and notes are beside it.
- Compare: `python -I program/stage_h_blind_w2/k5a_compare.py . stage_k_blind/k5a/blind_results.json`, with the script and tolerances fixed in 3d446c5a; first and only run; output `stage_k_blind/k5a/compare_output.txt` (ee19ae3d).

| Case | estimate_pnl | bound | label | Result | Counted |
|---|---|---|---|---|---|
| idr_k-0001 | MATCH | MATCH | MATCH (no credit) | MATCH | yes |
| idr_k-0002 | MATCH | MATCH, 1.98e-16 relative | MATCH (no credit) | MATCH | yes |
| idr_k-0003 | MATCH, 0 | MATCH, 2.08e-16 | MATCH (no credit) | MATCH | yes |
| idr_k-0004 | MATCH, 0 | MATCH, 0 | MATCH (no credit) | MATCH | yes |
| idr_k-0005 | MATCH, 1.19e-16 | MATCH, 0 | MATCH (no credit) | MATCH | yes |

**K-5a: 5 of 5 MATCH, 5 counted, 3 needed for 60%.** Largest relative difference 2.08e-16 against a tolerance of 1e-9. No mismatch, so nothing to resolve. Outside share of K-5a: 5 of 5 (100%), blind re-derivation only; goldens' `verified_by` updated through `oracle/python/gen_stage_k_w1.py` so that `tools/outside_shares.py` counts them.

Ambiguities the deriver recorded (`stage_k_blind/k5a/notes.md`) and what was done:
1. It summed the estimate with an exactly rounded sum although the rules require that only for the bound (affects idr_k-0005 only). 2. The rules do not fix the binary64 operation order per position, so last-bit differences are possible. Both are now stated in `intraday-risk-bounds.md` (operation section): the order is open, the estimate sum may be exactly rounded or left to right, the bound sum is exactly rounded, and the 1e-9 tolerance is what makes the order irrelevant. No value changed. 3. The label taken from KR-10 and 4. `abs(N)` per KR-15 are the rules' reading; no change.

What this shows and what it does not. A second model, reading only our stripped rules, reproduced all ten numbers to the last bit or two, so the spec is unambiguous enough to implement and the goldens are not one author's arithmetic slip. It does not show that the bound's derivation is right: the deriver used the formula the rules give. The evidence for the inequality itself (the remainder never exceeds the bound) is the 50-digit recheck of the 1,000 acceptance moves (`oracle/IDR_K_MOVES_CHECK_W1.json`), which is our own oracle, and the five exact remainder-over-bound ratios above (0.917 to 0.997).
