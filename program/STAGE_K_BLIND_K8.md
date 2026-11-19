# Stage K: blind re-derivation (DR-H2) of the seven K-8 value cases

Written 2026-11-19 by the packet builder (Claude Opus 5.5, branch `k-k8-ports`). The packet builder is not the blind lane and ran no derivation. Process: `program/STAGE_H_BLIND_LANE.md` (DR-H2); pattern of `STAGE_K_BLIND_W2.md` (branch `k-w2-spec`) and `STAGE_K_BLIND_K5A.md` (branch `k-w1-fu`). Scope: k8_k-0001..0007, the value cases of `datasets/golden/stage_k/k8_k.json` (`rates.shortrate.bermudan_ladder` and `rates.shortrate.bermudan_swaption` with `method` `CN_RANNACHER_SMOOTHED`, spec `06-risk/bermudan-ladder-k8.md`). Status: **packet built, blind lane not yet run.**

## Plain idea

The seven K-8 goldens are the Python build's own output; the other three builds were ported from it, so their agreement says the ports are faithful, not that the spec is. A second model, which never sees our numbers or code, reads only the stripped rules and implements the scheme and its exact derivative itself. It freezes its answers with a hash before anyone compares. A script, fixed now, compares them with the goldens at the goldens' own tolerance.

## Part 1: can the QuantLib comparison count instead? No (evidence class: read)

`outside_shares.py --check` fails: stage K is at 57.1% of value cases (20 of 35), K-8 at 0 of 7. The question was whether k8_k-0001..0003, judged against the QuantLib 1.44 `FdHullWhiteSwaptionEngine` fine-grid bump reference (`oracle/K8_REFERENCE_QL.json`, acceptance 2 in `oracle/K8_ACCEPTANCE_W2.json`), may be marked library-checked. Under the rules as written they may not, and nothing was changed.

- The D6 rule counts a case "only if every compared output of the case is checked" (`tools/outside_shares.py`, docstring lines 9 and 10). Stage G applied it per case: `oracle/OUTSIDE_G_R6.json` says "a case passes only if every compared output is within its stated tolerance", and `aadladder_g-0001` did not count because one of its outputs (`d_price_d_mean_reversion`) missed (read, same file). Stage G did count QuantLib agreement at a method-fixed discretisation tolerance (`tol = 3 e_lib_grid + 3 e_lib_conv + 1e-6 |value|`, `oracle/python/outside_g_r6.py` docstring), not at golden tolerance; so the tolerance is not the obstacle.
- The obstacle is coverage. Each of k8_k-0001..0003 compares 13 outputs: `price`, ten discount-factor entries, `d/da`, `d/dsigma`. Acceptance 2 judged only the entries with `|reference| >= 1e-3 max |reference|` plus `d/da` and `d/dsigma` (spec, Acceptance 2). The golden itself records it: "the price and entries below the 1e-3 floor are not compared" (`verified_by` of each case). No price tolerance against QuantLib was fixed before the run, and the 0.4986-year row cannot be compared at all: the method gives exactly 0 (the price does not depend on that node), while QuantLib's bumped engine gives -14.27 (`K8_REFERENCE_QL.json`, row 0) because its scheme samples the curve inside time steps.
- KR-11 and acceptance 1 ("QuantLib is the counted outside check", owner decision K-QA) say QuantLib is the outside check for K-8, but they do not override D6's every-output rule, and `load_stage_k` in `outside_shares.py` has no library path at all (stage K counts only DR-H2 blind matches). Treating three partly-checked cases as library-checked would stretch D6, so it was not done.
- What the coordinator could decide instead (not done here): fix, in a commit and before any run, a per-output tolerance for the price and an absolute floor for the near-zero rows, then run a per-case QuantLib check as stage G did. That is a new acceptance test and needs a ruling.

Share unchanged: stage K 57.1%, K-8 0 of 7 on this branch. (Stage K reaches 25 of 35, 71.4%, once the K-5a blind result of branch `k-w1-fu` is integrated; K-8 stays at 0 of 7 until this blind lane runs.)

## What was built (evidence class: measured, 2026-11-19, local laptop, not the acceptance machine)

| File | Role | Side |
|---|---|---|
| `program/stage_h_blind_w2/k8_make_packet.py` | writes the packet from the spec texts by exact anchors (the build stops if an anchor is missing or repeated); reads only `inputs` of the golden; never reads the expected file | builds the packet |
| `program/stage_h_blind_w2/k8_expected.json` | expected outputs of the seven cases, copied from the golden, with each case's tolerance class | hidden |
| `program/stage_h_blind_w2/k8_compare.py` | compare, with `--self-test` | hidden |
| `program/stage_h_blind_w2/k8_leaks.py` | leak check (model `k5a_leaks.py`, plus a proximity search) | hidden |

Packet: `C:/Work/Claude/qf-blind/k8_packet/` (outside every worktree; not committed). 8 files plus the manifest: `README.md`; `specs/bermudan-ladder-k8.blind.md` (the method section, steps 1 to 8, and the binary64 and tolerance paragraph); `specs/short-rate-models.excerpt.md` (curve conventions, the `rates.shortrate.swaption` input and G-12 convention lines, the G-18 Bermudan section); `specs/aad-core.excerpt.md` (ladder convention and outputs); `specs/cli-contract.excerpt.md` (the `method` input); `rulings/stage-k-rulings-k8.blind.md` (KR-8 with its confirmation note, KR-18, KR-19); `inputs/K-8.inputs.json`; `output_template.json`.

**Packet MANIFEST.sha256 file hash: `8f1241c072fe4e05da47d618f506b3b182f24d4142332709e46c4a488ac31334`.** Built from commit c09e5084 with `python -I program/stage_h_blind_w2/k8_make_packet.py . C:/Work/Claude/qf-blind/k8_packet`; a rebuild into a scratch folder gave the same hash (reproducible). Before handing the packet over, the coordinator checks that `sha256sum MANIFEST.sha256` still gives this value.

What was stripped. From `bermudan-ladder-k8.md`: the plain idea at the top (it quotes grid errors), the R6 grid table, the paragraph on version 0.1.0 (the first acceptance miss and the diagnosis), the worked example of the smoothing, the `num.richardson.check` section (its cases print G-18 ladder values on the same curve), the convergence table (QuantLib and method figures), the limits and the acceptance tests. From `short-rate-models.md`: every other operation, the Bermudan validation, convergence and evidence paragraphs, and the G-18 tolerance line. From `aad-core.md`: everything after the convention sentence of the formal statement (the 1-year entry on three grids), the use restriction, the bump reference of the stage G goldens, the tolerance line of G-9, the worked example and the performance test. From `cli-contract.md`: all but the two sentences that define `method`. From KR-18: the two "Cause" passages (diagnosis and measured orders) and the measured parenthesis on the end correction; the note after KR-18 (second-run results) and the K-8c introduction (first-run miss) are not copied. No file under `program/` (in particular `K8_DIAGNOSIS.md`, `K8_PORT_NOTE.md`) and no code is in the packet.

Allowed tools for the deriver (README): Python 3 standard library and numpy 2.x; no scipy, no QuantLib, no automatic-differentiation library, no repository import. The deriver must write the derivative itself.

## Spec gaps found and fixed (commit c09e5084; evidence class: read, code against spec)

The test was: could a numerical analyst with only the spec text implement the scheme to the last specified detail? The Python build (`python/quantforge_core/bermudan_k8.py`) was read line by line against the spec. Every discrete choice of the value (grid, knots, step counts, operator rows, boundary substitution, Rannacher start-up, smoothing formulas, end correction, stencil, read-out) was already stated. Five defects were found and fixed in `bermudan-ladder-k8.md`; no golden value changes.

1. **Wrong exact-zero rule (a real error).** Step 7 said an input the price does not depend on is "a curve node before the first exercise date with no node between, or after the last payment". The node at 7.005 years is after the last payment (6 years) yet its entry is not zero (the 6-year discount factor is interpolated from it). A deriver who trusted the sentence would have set it to zero. Fixed: the rule is now stated through the interpolation weight (no exercise or payment time strictly between the node's neighbours), with two examples; the Limits line was reworded to match. The compare self-test checks that the corrected rule picks exactly the 20 ladder positions where the goldens are 0.0.
2. **Grid by reference to a step that brings in the wrong quantities.** Step 1 said "As G-18 steps 1 to 3"; G-18 step 1 defines the state through `alpha(t)` and the right-hand forward, which this method never evaluates. Fixed: `sx`, `g`, `h`, `dx`, `x_i`, the centre node and `dt` written out, and a sentence that the curve enters only through `ln P(0, s)`.
3. **Curve rule not restated where it is used.** The log-linear rule with `(0, 1)` as the first node and the meaning of "flat forward beyond the last pillar" (the last segment's line continues) are now stated in step 2.
4. **Derivative at branches and constants not stated.** Added to step 7: every comparison in step 5 is made on the binary64 value, the derivative is that of the branch taken, a constant contributes nothing to a derivative, the discount-factor entry is per unit absolute change of `DF_j` (divide by `DF_j` when differentiating in logs), and any exact differentiation is acceptable while finite differences are not.
5. **Golden tolerance and operation order not in the spec.** The spec named no tolerance for its goldens. Added the paragraph "Binary64 and tolerance": the order of floating-point operations, the form of the tridiagonal solve and division against reciprocal are open (rounding only); classes `aad_sensitivity` (1e-10 absolute, 1e-8 relative) for every ladder-case output and `root_finding` (1e-10, 1e-10) for price cases, compared as `|a - e| <= absolute + relative x max(|a|, |e|)` on the notional-scaled outputs, as the runner applies `conformance/tolerances/policy.yaml`.

Not changed, stated so the coordinator knows: the `K8_PORT_NOTE.md` list "things that will bite" (divide rather than multiply by a reciprocal; a constant added to a dual changes the value only) is covered by items 4 and 5; nothing else in the note is a choice the spec leaves open. The after-spec-edit generators (`build_references.py`, `build_checklists.py --check`, `gen_name_map.py`, `case_figures.py --write`, `outside_shares.py`) changed no file; `research/test_preregs.py` passes (10 tests).

## Fixed now, before any blind result exists

- **Compare mapping and tolerances: commit c09e5084** (`k8_compare.py`, `k8_expected.json`). Mapping: `price`, `d_price_d_discount_factors[0..9]` (a list of the curve's length, in curve order), `d_price_d_mean_reversion`, `d_price_d_sigma` at the top level of each blind case object, the packet skeleton's shape. Tolerance: the goldens' own, `|blind - expected| <= absolute + relative x max(|blind|, |expected|)`, `aad_sensitivity` (1e-10, 1e-8) on every output of k8_k-0001, 0002, 0003, 0005 (ladder cases, price included), `root_finding` (1e-10, 1e-10) on the price of k8_k-0004, 0006, 0007. A list of the wrong length, a boolean, a non-finite value or a non-number is a MISMATCH. Representation rules R1, R2, R4 of `k5a_compare.py`.
- **Dry self-test on fabricated data: 20/20 PASS** (`python -I program/stage_h_blind_w2/k8_compare.py . --self-test`): the expected file equals the golden's value cases; the tolerances equal `policy.yaml`; the R-fields equal the nodes the corrected step 7 gives weight 0; exact values, 3e-14 and 5e-11 relative noise all MATCH; 5e-9 relative MATCH on ladder cases and MISMATCH on price cases; 3e-8 relative every case MISMATCH; one ladder entry off by 2e-8 only that case MISMATCH; a structural zero given as 1e-12 MATCH (inside the 1e-10 absolute term) and as 1e-6 MISMATCH; sign flip, NaN and a short list MISMATCH; `outputs` wrapper, bare case map and case list MATCH; an extra level SHAPE; two wrapper levels no MATCH; the unfilled skeleton all MISSING; an absent case MISSING; a decimal string MATCH and `true` for a number MISMATCH.

## Leak check

`python -I program/stage_h_blind_w2/k8_leaks.py . C:/Work/Claude/qf-blind/k8_packet > C:/Work/Claude/qf-blind/k8_LEAKS.tsv`: **0 hard leaks** (exit 0; list file SHA-256 `7d50c4808bbb498cd7d3c11437843d6b58b32ffc328946f46d81cb26961258ac`, outside the packet). Searched: (1) every nonzero expected number as printed, with the opposite sign, comma-grouped, and rounded to 0, 1, 2 and 4 decimals when that keeps three significant digits; (2) every number with at least three significant digits written in a prose file, against every expected number and 91 hint numbers (QuantLib reference prices and bump-1e-4 entries of acceptance 1, the stage G `aadladder_g` and `bermudan_g` outputs on the same curve), hard if within 1%, listed if within 5%. Result: 1 NEAR (`14.1`, a plan section number in the aad-core excerpt, 1.2% from QuantLib's -14.27 on row 0), 1 ALLOWED (`10.000000000000009`, the binary64 example of G-18 step 3), 0 input coincidences. Case ids appear only in `inputs/` and in the output skeleton.

## Cases and fields that cannot count, fixed now

- No whole case is excluded: none of the seven is stated by the rules text.
- **R-fields (compared, no credit on their own):** the discount-factor entries that the corrected step 7 says are exactly 0: positions 0 and 6 to 9 of each of the four ladder cases, 20 fields. Each ladder case still has five nonzero discount-factor entries, `d/da`, `d/dsigma` and the price to count on.
- **k8_k-0004** has the inputs of k8_k-0001 under the price operation. It counts under the rule as written (a separate golden case, a separate MATCH), but its MATCH adds no evidence beyond k8_k-0001's price field; stated so the share is not over-read.
- The QuantLib comparison of part 1 is not touched by this lane and stays uncounted.

**Eligible: 7 of 7. Needed for the 60% per-item floor: 5 (ceil of 0.6 x 7).** Stage K meets its 60% floor once the K-5a result is integrated; without it, one K-8 match lifts stage K from 20 to 21 of 35 (exactly 60%). The K-8 item floor needs 5 regardless.

## What a MATCH means for a PDE scheme, and what it does not

Plainly: two programs that run the same discrete scheme agree to rounding only if every discrete choice is pinned. A MATCH at 1e-8 relative on all 13 outputs of a ladder case (1e-10 on a price) therefore shows that the spec text pins the scheme completely: grid, knots, step counts, start-up, boundary rows, smoothing and end correction, and the derivative through all of them, including the grid's dependence on `a` and `sigma`. That is the point of the exercise, because the goldens are one build's output and the ports copied that build.

It does not show that the scheme approximates the Hull-White model well; that is acceptance 2 against QuantLib (worst judged entry 0.40% at the default grid, recorded) and acceptance 3 (order 2). It does not show that the end correction is right in any deeper sense: the deriver implements the formula it is given. A shared misreading of the model by the spec would pass.

A MISMATCH can mean either a defect in the deriver's code or a choice the spec still leaves open. Because the tolerance is far above rounding (builds agree to 3.85e-14 of the row scale, `oracle/K8_ACCEPTANCE_PORTS.json`) and far below discretisation (inferred: a different start-up rule, smoothing or boundary row changes the discretisation error, which on the judged entries is of the order of 0.1% at the default grid, convergence table of the spec), a mismatch is almost never a rounding question: it is a discrete choice made differently. Each one is investigated against the deriver's `notes.md` before anything is concluded, and is never fixed by rerunning the deriver. A tangent discontinuity exists where some `f_i` passes through 0 (the end correction switches on); if a node of a judged case sat within rounding of that point, two exact implementations could differ in the ladder by more than rounding. None of the builds shows this (four builds within 4e-14), but the compare output prints the relative difference of every field so it would be visible.

## Procedure

1. Coordinator: check the manifest hash above; hand the folder `C:/Work/Claude/qf-blind/k8_packet/` to a separate session on a model that took no part in the K-8 method or this packet. The method commits carry the trailers Claude Fable 5.2 and Claude Opus 5.5, and this builder is Claude Opus 5.5, so the deriver must be another model, for example Claude Sonnet 5.5 as for K-5a. It works only in `C:/Work/Claude/qf-blind/k8_blind/` and is given no repository path.
2. Blind lane, per the packet README: own implementation (`blind_ref.py`, standard library and numpy only), `notes.md` with every ambiguity and every discrete choice it had to make, `blind_results.json` filled from the skeleton at full binary64 precision, then `blind_results.sha256`, the hash reported first in its hand-back.
3. Coordinator: commit and push the frozen `blind_results.json` and its hash (copy into `stage_k_blind/k8/` with `notes.md` and `blind_ref.py`) **before** running the compare. Rule any gap from `notes.md` before the compare; a field decided by such a ruling is compared but not counted.
4. Run `python -I program/stage_h_blind_w2/k8_compare.py . <frozen blind_results.json> > stage_k_blind/k8/compare_output.txt`. One run.
5. On MATCH: record the DR-H2 MATCH in `verified_by` of each matched case of `datasets/golden/stage_k/k8_k.json` through `oracle/python/gen_stage_k_k8.py` (that is what `load_stage_k` reads), without the words "not blind"; rerun the after-spec-edit generators; fill the results below.

## Results

Not run. (Date, deriver and model, manifest check, frozen hash and commit, gaps and rulings, compare run and output path, per-case table of MATCH / MISMATCH / MISSING and counted, resolution of each mismatch: to be filled by the coordinator.)

## Results (2026-11-19; first and only compare run)

- Deriver: a separate subagent on Claude Sonnet 5.5 (the spec, the method and the packet were written by Fable 5.2 and Opus 5.5 lanes), given only the packet folder and its own folder; numpy 2.4.6 and the standard library. It states that it read and tried to read nothing outside the two folders (its own statement, not independently logged). The coordinator checked the packet manifest hash 8f1241c0... before the hand-over.
- Blind results as received: `stage_k_blind/k8/` (script, results, notes, self-checks, hash), committed in 9209a411 before the compare. SHA-256 of `blind_results.json`: `71c5a3790edff1ce8dcf83f9282a2afb47c164b31f9b7b6a31a8f53058ee42ce`, recomputed by the coordinator and equal to the deriver's hash file.
- Compare: `python -I program/stage_h_blind_w2/k8_compare.py . <blind_results.json>` at the commit that fixed the script and tolerances (c09e5084). Output `stage_k_blind/k8/compare_output.txt`. Results not changed afterwards; no rerun.

| Item | Cases | MATCH | MISMATCH | Eligible | Counted | Needed |
|---|---:|---:|---:|---:|---:|---:|
| K-8 | 7 | 7 | 0 | 7 | 7 | 5 |

Largest relative difference per case: 1.70e-14, 1.81e-14, 1.94e-14 (ladder cases 0001 to 0003), 4.80e-16, 1.19e-15, 3.89e-16, 1.90e-16. k8_k-0004 has the inputs of 0001 and adds no evidence beyond 0001's price.

Deriver's own checks, from the packet alone: single-exercise case against its own Gaussian quadrature converges at second order (errors -3.0e-3, -7.6e-4, -1.9e-4 over three grid doublings); its ladder against its own central bump agrees within 5e-9 relative on all 12 entries of case 5.

Spec defects the deriver recorded (`stage_k_blind/k8/notes.md`), to be fixed in the spec text without changing a value:
1. The "x" in the end correction can be read as multiplication or as the node coordinate; the other reading moves the price by 1e-5 to 5e-5 relative, far above tolerance. Must be made unambiguous.
2. Whether the Crank-Nicolson explicit side uses the boundary-substituted rows or the stored boundary values (identical on the cases tried; state one).
3. The half-step size and which steps are the first two of each interval, including [0, t_1].
4. Whether the end nodes are re-extrapolated after smoothing.
5. "Payments after t": strictly after.
6. Branch order of M(p,q) at p = 0.
7. Form of the interpolation weight (rounding only).

What this shows and does not show. A second model implemented the scheme from the rules text alone and reproduced every golden to about 1e-14, so the goldens are the specified scheme and not an accident of one code base. It says nothing about model accuracy (that is acceptance 2, against QuantLib) and it does not settle the open question on the ladder row at the 0.4986y node, where the method gives exactly 0 and the QuantLib bump reference about -14.27 (`program/K8_ROW0_FINDING.md`, in progress): a blind deriver following the same rules reproduces the same zero. Outside share for K-8 by blind re-derivation: 7 of 7, counted only once that question is closed.
