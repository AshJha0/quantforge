# K-8: the 0.4986-year ladder row, 0 against QuantLib's -14.27 (2026-11-19)

Branch `k-k8-row0` (off `k-k8-ports` at 6b3cbed5). Python only. No rule, threshold, grid, golden or acceptance record was changed. Evidence files are in `program/k8_row0/`.

## Verdict

**The skip is sound. There is no bug. But the two numbers are not derivatives of different things: they are the same derivative, the model's value of it is exactly 0, and QuantLib's -14.27 is the time-stepping error of QuantLib's finite-difference engine.** The brief offered "definitions differ" or "bug"; neither is what the evidence shows. The first holds in its conclusion (row structurally zero, skip sound) and not in its reason.

The owner's premise ("the model derivative there is zero") is correct and is now supported by an argument and by two measurements that the earlier lanes did not have. Nothing here undermines the owner's decision.

Naming: the row is "row 1" in `K8_ACCEPTANCE_W2.json`, `K8_DIAGNOSIS.md` and the spec (row 0 there is the price) and "row 0" in `K8_REFERENCE_QL.json` and `STAGE_K_BLIND_K8.md` (0-based index into the discount factors). Below it is "the 0.4986 row".

## 1. What each number is the derivative of

| | Ladder entry (spec step 7; `bermudan_k8.scheme`, `bermudan_ladder`) | QuantLib reference (`oracle/python/k8_acceptance.py`, `ql_price`, `reference`) |
|---|---|---|
| Input moved | `DF_j`, the discount factor of curve node `j`, alone | the same: `d[k] = x`, relative bump `h`, central difference |
| Node parameterisation | discount factors at the node times; tangent taken in `ln DF_j`, then divided by `DF_j` (code line `notional * r[1 + j] / d`) | discount factors at the same times, as whole days over 365 |
| Curve | `ln P` linear in time between nodes, flat forward beyond the last (`_Curve.log_discount`) | `ql.DiscountCurve` (log-linear discount factors), rebuilt from the bumped list |
| Held fixed | `a`, `sigma`, the other nine discount factors, the schedule, the strike | the same: `ql.HullWhite(handle, a, sigma)`; no calibration, no refit, one curve for discounting and the index |
| Unit | per unit absolute change of `DF_j`, times `notional` | the same: divided by `2 h DF_j`, swap notional in the instrument |
| How the curve enters the numerics | only `ln P(0, s)` at `s` in {1, 2, 3, 4, 5, 6} years (exercise and payment times); the operator has no curve term | the fitted drift, which needs the forward rate `f(0, t)` at every time step |

Source: read from the spec and the two files named (evidence class: read). So the comparison in acceptance 2 is between like quantities, for this row as for the others.

## 2. Why the model derivative is exactly zero (inferred, from the model)

Plain idea: a Bermudan swaption in Hull-White sees the curve only at the dates on which something can happen, the exercise dates and the payment dates. The node at 0.4986 years shapes the curve only between 0 and 1 year, and nothing happens there.

Formal statement. Write `r(t) = x(t) + alpha(t)` with `x` the curve-free Ornstein-Uhlenbeck state started at 0. Then `exp(-int_0^t alpha) = P(0, t) exp(-c2 I(t))` (spec step 2) and `P(t, T | x) = [P(0, T) / P(0, t)] G(t, T, x)` with `G` free of the curve (spec step 3). The value of exercising at `t` discounted to 0 is `exp(-int_0^t x) phi [P(0, t) g_0 - P(0, T_n) g_n - K sum tau_j P(0, T_j) g_j]` with curve-free `g`. The price is the supremum over exercise rules of the expectation of that, so it is a function of `P(0, s)` for `s` in the exercise and payment times only. Under the log-linear rule `DF_1` (0.4986 years) changes `P(0, s)` only for `0 < s < 1`; the first exercise is at 1.0, which is itself a node. Hence `d price / d DF_1 = 0` exactly, in the model, on any grid.

## 3. Bump-and-revalue of our pricer (measured 2026-11-19)

`program/k8_row0/ours.py`, project Python (uv, CPython 3.15.2), `bermudan_price` with `CN_RANNACHER_SMOOTHED`, relative bumps up and down on one discount factor.

| Case | Grid | Rows bumped | Relative bumps (up and down) | Largest price change | Bump derivative | AAD |
|---|---|---|---|---|---|---|
| 0001, 0002, 0003 | 41/20 and 201/100 (default) | 0.4986 row and the four tail rows | 1e-6, 1e-4, 1.6e-2, 0.2 | 0.0 (prices bit-identical) | 0.0 | 0.0 |
| 0001 | 801/400 | 0.4986 row | 1e-4, 1.6e-2 | 0.0 (bit-identical) | 0.0 | 0.0 |
| 0001 (first run, `ours_first_run.log`) | 801/400 | 0.4986 row and the four tail rows | 1e-6, 1e-5, 1e-4, 1e-3, 1.6e-2, 0.2 | 0.0 (bit-identical) | 0.0 | 0.0 |

"Bit-identical" means `P(bumped) - P(base)` is the binary64 value 0.0, not a small number: a 20% move of `DF_1` (from 0.98085 to 1.177, a curve that is not even decreasing) leaves the default-grid price at 22,737.43110152093 to the last bit. There is no bump-size study to show because every bump gives 0; the central difference is 0.0 at every size, equal to the AAD value and to the model value, and 14.27 away from QuantLib's number. Files: `ours.json` (every up and down difference), `ours.log`. The first run used six bump sizes and all five rows at 801/400 as well; it was stopped by hand during case 0003 at 201/100 because of its length, and its completed lines (all 0.0) are kept in `ours_first_run.log`.

Control (same script): the curve without its 1-year node, default grid, case 0001. The 0.4986 node now carries weight for `s = 1` and its entry is 146,291.154 by AAD against 146,291.248 by a plain central bump of 1e-4 (6.4e-7 relative, the size of the bump's own curvature error). The method returns zero only where the interpolation weight is zero.

The repo's own AAD-against-bump test, `test_k8_ladder_equals_its_own_bumps` (`python/tests/test_stage_k_w1.py`), loops over all ten discount-factor entries with an absolute tolerance of `1e-8 x` the largest entry, so it does cover this row and the four other zero rows; it does not skip them. It runs case 0002 on the 41/20 grid only. The exact zeros are also asserted by `test_k8_curve_nodes_the_price_does_not_depend_on_give_exact_zeros` (three cases, 41/20) and by the goldens `k8_k-0001, 0002, 0003, 0005`.

## 4. What QuantLib's -14.27 is (measured 2026-11-19, QuantLib 1.44)

`program/k8_row0/qlrow0.py` calls the unchanged `k8_acceptance.ql_price`; bump 1e-4. It reproduces the reference value to the last digit (-14.274062255665008 at tGrid 8,000 / xGrid 3,201).

Case 0001, 0.4986 row, xGrid 801:

| Node (day 182 of 1,825) on a time-grid point | tGrid | Row value | Row of the 1-year node, for scale |
|---|---|---|---|
| yes | 1,825 | +15.767 | 223,252.7 |
| yes | 3,650 | +7.883 | 223,262.4 |
| yes | 7,300 | +3.942 | 223,267.2 |
| yes | 14,600 | +1.971 | 223,269.6 |
| no | 1,000 | -76.110 | 223,290.3 |
| no | 2,000 | +25.512 | 223,248.8 |
| no | 4,000 | -39.687 | 223,287.0 |
| no | 8,000 | -14.281 | 223,276.7 |
| no | 16,000 | -1.579 | 223,271.6 |

With the node on the time grid the value halves each time the step halves (ratios 2.000, 2.000, 2.000): a first-order time error going to 0. With the node inside a step the sign and size depend on where in the step it falls. The same at xGrid 3,201: 8,000 gives -14.274, 7,300 gives +3.950. Cases 0002 and 0003 at 3,201: -9.998 and -9.590 at tGrid 8,000 (the recorded values), +1.572 and +1.567 at 7,300.

A number that changes sign with the time grid and halves with the step is not a property of the model. It is the artefact the diagnosis already named as cause (A) for our first definition (`K8_DIAGNOSIS.md` section 2, "QuantLib's value for row 1 (true value 0) is -14, -10, -10"); that sentence was stated there without a measurement, and this table is the measurement.

Mechanism (measured in part, inferred in part). QuantLib's Hull-White fit needs the instantaneous forward `f(0, t)`. For a log-linear curve the forward is a step function with a jump at every node. `program/k8_row0/jam.py` shows QuantLib returning at `t = 1.0` (a node and the first exercise date) the mean of the forwards on the two sides, 0.038798 between 0.038911 and 0.038684, and moving it to 0.048721 when `DF_1` is raised by 1%: the engine's input at 1 year depends on the 0.4986 node (measured). In exact arithmetic the forward cancels (spec step 3); in a time-stepping scheme that samples it the cancellation holds only up to the step size (inferred; consistent with the halving above).

Size. -14.27 is 4.1e-5 of the largest entry of that ladder (347,583). The reference's own two bumps differ by 6 to 20 on rows 2 to 5 (5.97, 5.52, 18.18, 19.66) of the same case, and the method at 1601/800 differs from the reference by 8 on row 2. The row's reference error is the same size as the reference's error on the rows that were judged, and 24 times below the floor of acceptance 2 (347.6).

Side check with one exercise date (same file): QuantLib's analytic Jamshidian engine gives 3.83, 3.84, 3.84, 2.38, -0.00002 for this row at bumps 1e-6 to 1e-2 against 508,360 for the 1-year row. It is not a smooth function of the bump, so it is root-finder and forward-at-the-kink noise of 7.5e-6 of the scale, not a derivative. Even QuantLib's closed form is not exactly insensitive to this node in floating point; ours is, because it never reads the forward.

## 5. Every other exact zero, and the 7.0055-year node

All K-8 goldens (`datasets/golden/stage_k/k8_k.json`) and all three acceptance cases use one curve (nodes 0.4986, 1, 2, 3, 5.0027, 7.0055, 10.0055, 15.011, 20.014, 30.019 years) and one schedule (exercise 1 to 5, payments 2 to 6). The price reads `ln P(0, s)` at `s` = 1, 2, 3, 4, 5, 6.

| Node (years) | Times it carries weight for | Entry | Why |
|---|---|---|---|
| 0.4986 | none (affects only 0 < s < 1) | exactly 0 | section 2 |
| 1, 2, 3 | 1, 2, 3 (own value) | non-zero, judged | |
| 3 and 5.0027 | 4 and 5, interpolated between them | non-zero, judged | |
| 5.0027 and 7.0055 | 6, interpolated between them | non-zero, judged | the last payment's discount factor comes from both |
| 10.0055, 15.011, 20.014, 30.019 | none (each affects only s > 7.0055) | exactly 0 | no payment after 6 years; the flat-forward tail of the last two nodes starts at 15.011 |

So the 20 zero ladder entries are positions 1 and 7 to 10 of the four ladder goldens (`k8_k-0001, 0002, 0003, 0005`), 5 each, and each is a true zero under the ladder's definition for the reason in the table. The four tail nodes are 0.0 in QuantLib as well, at every bump and both grids (`K8_REFERENCE_QL.json`), because QuantLib's engine never reads the curve beyond the last payment. Bump-and-revalue of our pricer on these four rows: section 3.

The 7.0055-year node is not zero and was never returned as zero by the code: -347,574 at 201/100 against QuantLib's -347,583 (0.003%), judged by acceptance 2 and 3 in all three cases. What was wrong was one sentence of spec step 7 ("or after the last payment"), which the blind-packet lane corrected. The code followed the interpolation, not the sentence. No acceptance result is affected.

A control that the method does not zero a node blindly (`ours.py`, last block): with the 1-year node removed from the curve, so that the 0.4986 node carries weight for `s = 1`, the ladder entry of that node is non-zero and equals its own bump. Values in section 3.

## 6. Why 21 judged entries in one test and 24 in the other

Read from `oracle/K8_ACCEPTANCE_W2.json` and `k8_acceptance.py`.

- Acceptance 2 (within 1% of the reference): per case, rows 2 to 6 (five discount factors above the floor `1e-3 x max |reference|`), `d/da`, `d/dsigma`: 7. Three cases: **21**. The price is not in this test.
- Acceptance 3 (observed order): per case, the price and the same seven: 8. Three cases: **24**. The spec's own line says "3 prices and 21 ladder entries".

The difference is the three prices. The ladder entries judged are the same 21 in both.

Entries left out, per case: the 0.4986 row and the four tail rows, 15 in all.

- Acceptance 2 leaves out the 0.4986 row because its reference is under the floor (14.27 against 347.6; 10.00 against 278.7; 9.59 against 278.6), a rule fixed before the first run and independent of what our method returns. It would have been left out with our first definition's -337 too. The tail rows have reference 0.0.
- Acceptance 3 does not use the reference at all. It leaves out an entry that is exactly 0 on all three grids, since 0, 0, 0 has no observed order.

So three entries with a non-zero reference were not judged (the 0.4986 row of each case, references -14.27, -10.00, -9.59). None was dropped by the all-zero rule from a comparison with the reference: the floor did that. And the non-zero reference values are reference error (section 4). No entry with a real non-zero sensitivity was dropped.

## 7. What is still true after this

- No acceptance test checks the 0.4986 row. That is what the spec's Limits section says and it stays so. The row now has more than a unit test behind it: the argument of section 2, the bit-identical prices of section 3, and QuantLib's own values going to 0 with the time step (section 4). These are evidence in this file, not an acceptance test, and no ruling was made.
- `STAGE_K_BLIND_K8.md` line 14 ("the 0.4986-year row cannot be compared at all") is right as a statement about the fixed-grid reference file. It should not be read as a disagreement between the method and the model.
- For a port in another language nothing changes. The exact-zero contract of `K8_PORT_NOTE.md` stands.

## 8. Changes on this branch

- `specifications/06-risk/bermudan-ladder-k8.md`, Limits: one new bullet under the owner-decision bullet (which is untouched), with the two definitions side by side and what QuantLib's number measures; inside `blind:strip` markers because it quotes reference values. Generators rerun after the spec edit (`build_references.py`, `build_checklists.py --check`, `gen_name_map.py`, `case_figures.py --write`, `outside_shares.py`, `research/test_preregs.py`): no file changed; `outside_shares.py` prints the stage K 57.1% under-floor line that commit 3f82dbd1 already recorded.
- `program/K8_ROW0_FINDING.md` (this file) and `program/k8_row0/` (scripts, their outputs).
- No code, test, golden, oracle record or ruling changed. No Python test run was needed for that reason; none was run.
