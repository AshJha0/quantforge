# K-8 diagnosis: why the first `CN_RANNACHER_SMOOTHED` missed acceptance 3, and what fixed it

Lane K-8c, 2026-11-19. Branch `k-k8`. Spec: `specifications/06-risk/bermudan-ladder-k8.md` (0.2.0). Rulings: KR-8, KR-18, KR-19. Evidence classes used below: *measured* (a run in this lane), *read* (source opened and the passage read), *recalled* (not opened), *inferred*, *derived here*.

## Result in one paragraph

The first definition of the method (spec 0.1.0, run of 2026-11-18, `oracle/K8_ACCEPTANCE_W1.json`) was already close in size: against the reference built here, its worst judged entry at the default grid 201/100 is 0.39% off (measured, table below). It failed because its ladder errors did not shrink in a regular way under refinement, so the order test (acceptance 3) failed on 18 entries. There were two separate causes, one in time and one in space. Both are fixed in the method (KR-18). The second run passes acceptance 1, 2 and 3 in Python, and acceptance 3 in Java with values equal to the Python record to 4e-14 of the row scale (`oracle/K8_ACCEPTANCE_W2.json`). The threshold, the default grid, the cases and the rule that picks the judged entries are unchanged.

## 1. The 18 entries

Rows: 1..10 are the discount-factor entries at curve nodes 0.4986, 1, 2, 3, 5.0027, 7.0055, 10.005, ... years; 11 is `d/da`, 12 is `d/dsigma`. Reference: QuantLib bump at tGrid 8,000 / xGrid 3,201, bump 1e-4 (`oracle/K8_REFERENCE_QL.json`). Gaps are first-run value minus reference (measured).

| Case | Row | First-run status, order | Gap at 201/100 | Gap at 801/400 | Where it sits | Cause |
|---|---|---|---|---|---|---|
| 0001 | 1 | ORDER_MISMATCH 1.00 | -323 absolute | +25 absolute | node 0.4986, inside a time step, before the first exercise | time (A); model derivative is exactly 0 |
| 0001 | 2 | ORDER_MISMATCH 0.25 | -0.098% | -0.013% | node 1.0 = first exercise date | time (A) and space (B) |
| 0001 | 3 | ORDER_MISMATCH 1.04 | +0.217% | +0.015% | node 2.0 = exercise date | space (B) |
| 0001 | 5 | ORDER_MISMATCH -1.91 | -0.027% | -0.002% | node 5.0027, just after the last exercise | space (B) |
| 0001 | 6 | ORDER_MISMATCH 1.43 | -0.012% | +0.003% | node 7.0055 (carries the last payment) | space (B) |
| 0002 | 1 | ORDER_MISMATCH 1.00 | -206 absolute | +17 absolute | as 0001 row 1 | time (A) |
| 0002 | 2 | NON_MONOTONE | -0.389% | -0.009% | node 1.0 | time (A) and space (B) |
| 0002 | 3 | NON_MONOTONE | +0.192% | +0.008% | node 2.0 | space (B) |
| 0002 | 4 | NON_MONOTONE | +0.021% | +0.002% | node 3.0 | space (B) |
| 0002 | 5 | NON_MONOTONE | -0.162% | +0.002% | node 5.0027 | space (B) |
| 0002 | 6 | ORDER_MISMATCH 3.36 | -0.018% | +0.004% | node 7.0055 | space (B) |
| 0002 | 11 | ORDER_MISMATCH 1.45 | +0.235% | +0.052% | `d/da` | not decomposed; (B) inferred |
| 0002 | 12 | ORDER_MISMATCH 1.34 | +0.078% | +0.017% | `d/dsigma` | not decomposed; (B) inferred |
| 0003 | 1 | ORDER_MISMATCH 1.00 | -199 absolute | +16 absolute | as 0001 row 1 | time (A) |
| 0003 | 2 | ORDER_MISMATCH 0.80 | -0.138% | -0.009% | node 1.0 | time (A) and space (B) |
| 0003 | 3 | NON_MONOTONE | +0.028% | +0.010% | node 2.0 | space (B) |
| 0003 | 5 | NON_MONOTONE | +0.042% | -0.004% | node 5.0027 | space (B) |
| 0003 | 6 | ORDER_MISMATCH 2.53 | +0.024% | +0.003% | node 7.0055 | space (B) |

Signs are mixed and change between grids, which is the mark of an error that depends on grid position, not of a slow smooth one. None of the 18 sits at the space-grid boundary. Three of them (row 1 of each case) are the near-zero kind: the model derivative is exactly zero, the largest entry of the row is about 3.5e5, and the first-run values were -337, -105, +11 on the three grids (case 0001). Acceptance 2 never judged them (below the 1e-3 floor); acceptance 3 did.

## 2. Acceptance 2 reference (run before the fix was judged)

QuantLib 1.44 wheel in a local venv, `FdHullWhiteSwaptionEngine`, script `oracle/python/k8_acceptance.py reference`. Set-up check: one exercise date gives 15,409.2472 against QuantLib's own Jamshidian engine 15,409.2486 (measured).

**Bump-size study (measured, case 0001, row 2, central differences).** Eleven relative bumps from 1e-5 to 1.6e-2 at xGrid 3,201: 223,195 / 223,263 / 223,250 / 223,244 / 223,245 / 223,256 / 223,287 / 223,404 / 223,876 / 225,809 / 234,113. There is a plateau from 2e-5 to 5e-4 (spread 0.009%); below it the differences are noisy, above it the truncation error of the bump grows as the square of the bump. The two bumps the spec fixed (1e-4 and 5e-5) are on the plateau.

**Why the grid first proposed is not enough (measured).** QuantLib applies the exercise `max` pointwise, so its bumped derivative carries the grid-position noise of cause (B). At the proposed 2,000 / 801 the two bumps disagree by more than 0.1% on four judged entries (0.106%, 0.252%, 0.254%, 0.123%; a fifth, 0.097%, is just inside; corrected 2026-11-19, audit finding KA-B8), which the spec's own rule reports as unresolved. At 8,000 / 3,201 the worst disagreement is 0.016%. KR-19 moves the reference to the finer grid on that evidence alone, before the judged run. The proposed-grid numbers are kept in the reference file.

**Agreement of the two references (measured).** The method at 1601/800 against QuantLib: worst judged entry 0.030%. The method at 801/400 against 1601/800: worst 0.019% (limit 0.2%). QuantLib's value for row 1 (true value 0) is -14, -10, -10: it has the artefact of cause (A) too, at a size below the floor.

## 3. Root causes

### (A) Time: a curve node inside a time step

`alpha(t)` contains the forward rate, which for log-linear discount factors jumps at every curve node. The first definition sampled `alpha` at step ends. Nodes at 1, 2 and 3 years are time-grid points; the node at 0.4986 is not, so the one step that holds it used the wrong mixture of the two forwards. The price is hardly affected (the two forwards are close) but the derivative of the jump with respect to the two neighbouring discount factors is of order 1 over the node spacing, so rows 1 and 2 get an error of first order in `dt` with opposite signs.

Measured (first definition, case 0001, 401 nodes, 100 / 200 / 400 steps a year, time-only refinement): row 1 -337.0, -104.9, +11.1 (order 1.00); row 2 differences +117.7, +58.9 (order 1.00, half of row 1 and opposite, as the jump derivative predicts); every other row changes by less than 0.2.

Fix (KR-18 a): solve for `U = V exp(-int_0^t alpha)`. The curve term commutes with the rest of the operator, so this is exact, and the operator becomes time-independent. Measured after the change: observed order 2.00 on every row in the same study, and row 1 is exactly 0.0.

### (B) Space: the price error depends on where the exercise boundary sits in its cell

Idea. By the envelope property a discount-factor entry is an exercise probability times a discount factor, so the data it evolves from are a step at the exercise boundary. If the price error has a part that depends on the boundary's position inside its cell, differentiating it with respect to an input that moves the boundary divides that part by `dx`. A price error term of size `dx^3 g(position)` therefore gives a ladder error of size `dx^2 g'`, the same order as the regular error but with a coefficient that changes from grid to grid. That is what the order test sees.

Measured (first definition with cause A removed, case 0001, space-only refinement at 100 steps a year on 101, 151, 201, 301, 401, 601 nodes, error against 1601): row 2 -1064, -997, -379, -223, -158, -63; row 4 +798, +206, -12, +165, -2, +12. The price on the same grids is clean second order. A strike scan at 201 nodes (two exercise dates, 25 strikes 1 bp apart) shows the slope of the price error swinging between 0.009 and 0.048 per bp with a period of about 8 bp, one cell.

Where the term comes from (derived here, checked by the runs below):
1. The cell average is a first-order smoothing operator in the sense of Kreiss, Thomee and Widlund (recalled): its transform has simple zeros at the grid frequencies. It leaves a position-dependent price error of order `dx^3` for kink data. The hat function has double zeros and pushes that to `dx^4`. Pooley, Vetzal and Forsyth (read, sections 2.2 and 2.4) define the average over the half-cells, credit its validity to that 1970 paper, and note that averaged data may still have kinks.
2. With `f = V - E` taken linear between nodes, the functional is `int G_lin max(f_lin, 0)`. In whole cells the interpolation error sums to a smooth term. In the cell with the crossing, where the part with `f > 0` is a fraction `rho`, the leftover is `G f'' dx^3 rho (1 - rho)(2 rho - 1)/12`. The end correction of spec step 5 subtracts exactly this, with `f'' dx^2` taken as the mean second difference at the two nodes of the cell.
3. The stencil `1 - delta^2/6` removes the `dx^2 f''/6` that the hat average of a piecewise-linear function adds at every node, so that away from the boundary the result is the pointwise `max`.

Measured (case 0001, same space-only study, error times `((nx-1)/200)^2`, rows 2 and 4):

| Smoothing | 101 | 151 | 201 | 301 | 401 |
|---|---|---|---|---|---|
| hat, stencil, no end correction: row 2 | -392 | -546 | -467 | -510 | -527 |
| same: row 4 | 166 | 186 | 89 | 241 | 93 |
| hat, stencil, end correction (adopted): row 2 | -481 | -483 | -476 | -467 | -454 |
| same: row 4 | 169 | 171 | 168 | 165 | 160 |

The slow drift in the adopted rows is the error of the 1601 comparison grid itself. A unit test repeats this on smaller, non-nested grids (60 to 160 cells against 320): the scaled error is within 4.5% of its mean on every row (tolerance in the test 10%).

### Candidates checked and not found to be the cause

| Candidate | Finding |
|---|---|
| Rannacher start-up missing after each exercise date | Already present in the first definition. Going from two to four half steps changed the space-only study by less than 1 in 2e5 (measured): not the cause here. Four are adopted on the source's analysis, Giles and Carter 2006 section 1 and Table 1 (read): for step data two half steps leave a high-wavenumber error of the same order as the leading error |
| Time grid not containing the exercise dates | Not the case: the exercise dates are the knots (G-18 step 3). The time-grid problem was the curve node, cause (A) |
| Boundary conditions | Not tested separately. The grid ends at 6 standard deviations and after the fix every row is second order (measured), so they are not a cause at this accuracy (inferred) |
| Tangent through the `max` with a kink | The smoothed scheme is differentiable and the ladder equals its own Richardson bumps to 1e-8 (measured, unit test). The derivative is right; what it differentiates had a grid-position term, cause (B) |
| Interpolation at the short-rate origin | None: the centre node is `x = 0` |
| Calibration (theta fit) differentiated inconsistently | The fit is analytic. Its only discretisation was the sampling of `alpha`, cause (A). QuantLib's bump has the same artefact at a small size (section 2) |

## 4. Second run (`oracle/K8_ACCEPTANCE_W2.json`, measured)

| Test | Result | Worst figure |
|---|---|---|
| 1. Reference | PASS | QuantLib bumps 1e-4 against 5e-5: 0.016% (limit 0.1%); method 801/400 against 1601/800: 0.019% (limit 0.2%) |
| 2. Default grid 201/100 within 1% | PASS | 0.40% against QuantLib (case 0002 row 2); 0.39% against the method at 1601/800. 21 judged entries |
| 3. Observed order on 201/401/801 | PASS | 24 entries (3 prices, 21 ladder), all `OK`, orders 1.84 to 2.15 |

Java: acceptance 3 passes with the same test, values equal to the Python record to 3.8e-14 of the row scale.

## 5. Points for the coordinator

1. **Row 1 (node 0.4986) is now exactly 0.0 on every grid** and is therefore skipped by the rule the first-run test already had (an entry exactly zero on all three grids is not put through `num.richardson.check`). The rule is unchanged; the set it selects grew by one row per case because the scheme now reproduces a true zero. If the owner wants that row judged in some absolute way instead, that is an owner ruling. Its values: first run -337 / -105 / +11 (case 0001), second run 0 / 0 / 0, model value 0.
2. Acceptance 2 would also have passed with the first definition (worst 0.39%). The first run failed on acceptance 3 only.
3. The method definition changed under the same name (KR-18). No golden of the first definition was published; the new goldens are `datasets/golden/stage_k/k8_k.json`.
4. The end correction is derived in this lane, not taken from a paper. It is supported by the measurements above and by the unit tests, not by an outside source.
5. Kreiss, Thomee and Widlund 1970 was not read (not free); Rannacher 1984 was not read. Pooley, Vetzal, Forsyth and Giles, Carter were read from the free preprints on 2026-11-19.
