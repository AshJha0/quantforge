# Question bank 14: Stage K: data platform, intraday risk, capital and the paper ledger

This set covers the stage K round 1 work, which is **merged to main by 2026-11-20, not tagged, and released with v1.0.0** (stage K as a whole continues toward v1.0.0): the bitemporal store, incremental curve updates, recalibration triggers, intraday risk with error bounds, the Bermudan ladder convergence fix, SA-CCR and FRTB backtesting, and the daily paper ledger. All of it is in all four builds and on `main` (pull requests #58 and #59; there is no v0.10.1 tag). The fourth pass (Q14.68 to Q14.82, added 2026-11-21) covers curve methods (meeting steps, turns, joint solve, curve risk, incremental update) and K-5 and K-6 practice. The third pass (Q14.53 to Q14.67, added 2026-11-21) covers pull requests #60 to #64: wave 2 capital, the wrong-way CVA root fix KR-257, K-5 snapshots, K-3 adapters and feed codecs, and the K-6 soak and rehearsal. It is for a reader who has worked through [Tutorials 51 to 58](../getting-started/README.md#stage-k-in-progress). Every worked-example number is rechecked by `verify/v14_stage_k.py`, which restates the formulas with the standard library and compares them with the goldens' values. All data is synthetic, except the Basel examples, which are the regulator's own sample portfolios.

## Bitemporal store

### Q14.1 What are valid time and knowledge time, and why does a risk store need both?

*Level: foundation. Evidence: spec; golden (`bt_k-0001`, `bt_k-0002`). Source: `specifications/01-core/bitemporal-store.md`, [Tutorial 51](../getting-started/tutorial-51-bitemporal-store.md)*

Valid time is the period a value describes (February's rate); knowledge time is when we learned it. A store with one time can say what was known at a moment, but not separate "the February value as known in March" from "the February value as known in April".

The spec gives each record a valid interval `[valid_from, valid_to)` and a `knowledge_time`, and a query a pair `(K, V)`: knowledge as of `K`, valid at `V` (ruling KR-2).

**Worked example.** On the shared golden log, February was first covered by a value of 100 (learned 2 January) and corrected to 105 (learned 1 April). Asked in mid-March about mid-February the store returns 100 from record 1 (`bt_k-0001`); asked on 1 April it returns 105 from record 3 (`bt_k-0002`).

The pitfall is overwriting the old value: a report rerun "as of March" would then show a number nobody had in March.

### Q14.2 Which record wins when several are known and cover the date?

*Level: practitioner. Evidence: spec; golden (`bt_k-0004`, `bt_k-0005`). Source: `specifications/01-core/bitemporal-store.md`*

The latest one in the log that was already known: among the records known by `K` whose valid interval contains `V`, the one with the largest `sequence`.

Formally `C = { r : knowledge_time(r) <= K and valid_from(r) <= V < valid_to(r) }`; empty gives `NONE`; else `w = argmax sequence`; `w.deleted` gives `WITHDRAWN`, otherwise `FOUND` with `w`.

**Worked example.** From 2 April, record 4 withdraws March onward. For 10 March, records 1, 2 and 4 all cover the date and are known by 5 April; record 4 has the largest sequence, so the answer is `WITHDRAWN` with no row (`bt_k-0004`). For 15 January only record 1 covers the date, so 100 (`bt_k-0005`).

The pitfall is choosing by knowledge time: two records learned in the same second are ordered by `sequence` only.

### Q14.3 What property does the stage K acceptance test check, and with what evidence?

*Level: advanced. Evidence: spec; measured by the k-w1 lane. Source: `specifications/01-core/bitemporal-store.md`, `program/STAGE_K_W1_HANDOVER.md`*

That the past cannot be changed by the future: appending any record learned after `K` leaves every answer as of `K` unchanged, byte for byte (KR-4).

The test generated 10,000 seeded logs and asked 500,000 `(K, V)` pairs before and after appending later records.

**Worked example.** Result: 0 failures in Python and in Java (`program/stage_k_w1/acceptance_python.json` and `acceptance_java.jsonl`, key `kr4_correction_property`). C++ and Rust run the same property in their unit tests and write no evidence file.

The pitfall is reading this as a database: the operation reads a log passed in the request. There is no persistent store yet.

### Q14.4 Is `valid_to` inclusive, and how is a stage A record mapped into the bitemporal form?

*Level: practitioner. Evidence: spec; golden (`bt_k-0007`, `bt_k-0008`). Source: `specifications/stage-k-rulings-w1.md` KR-3, KR-16*

Exclusive: a record valid `[1 February, 1 March)` does not answer for 1 March itself. Instants are whole seconds.

A stage A as-of record with event time `t` is the bitemporal record `[t, t + 1 s)` (KR-16 corrects KR-3).

**Worked example.** On 1 April, for exactly 1 March, record 3 no longer applies and record 2 answers 110 (`bt_k-0007`); for 23:59:59 on 28 February record 3 still answers 105 (`bt_k-0008`).

The pitfall is an off-by-one at month ends when `valid_to` is treated as inclusive.

## Incremental curve update

### Q14.5 Why can an annual par bootstrap be patched from the first moved quote onwards?

*Level: foundation. Evidence: spec; golden (`inc_k-0001`). Source: `specifications/02-curves/incremental-update.md`, [Tutorial 52](../getting-started/tutorial-52-incremental-curve-update.md)*

Each discount factor uses only quotes up to its own maturity, so a later quote cannot change an earlier pillar.

The recursion is `P_k = (1 - S_k sum_{i<k} P_i) / (1 + S_k)`.

**Worked example.** Quotes 2%, 2.5%, 3%: `P_1 = 1/1.02 = 0.980392`, `P_2 = 0.951698`, `P_3 = 0.914599` (`inc_k-0001`). Moving only the 3-year quote can change only `P_3`.

The pitfall is assuming this for any curve: with a global spline every pillar's forwards depend on every quote.

### Q14.6 What does `curve.incremental.update` return for a move of the 2-year quote to 2.6%?

*Level: practitioner. Evidence: golden (`inc_k-0002`). Source: `specifications/02-curves/incremental-update.md`*

The patched curve, the first changed index and how many pillars were recomputed.

`first_changed_index` is 0-based; `recomputed = n - j`.

**Worked example.** `first_changed_index` 1, `recomputed` 2, `P_1` copied, `P_2 = 0.949815`, `P_3 = 0.914654` (`inc_k-0002`). `P_3` rises because the 3-year swap's fixed leg leans on `P_2`, which fell.

The pitfall is expecting later pillars to move in the same direction as the moved one; they need not.

### Q14.7 Why must the cached discount factors match the bootstrap bit for bit, not within a tolerance?

*Level: advanced. Evidence: spec; golden (`inc_k-0006`). Source: `specifications/02-curves/incremental-update.md`*

A cache built from other quotes would make the patched curve silently wrong, and "close" would hide exactly that bug.

The operation recomputes the bootstrap of `previous_quotes` and refuses with `E_INPUT` unless it equals `previous_discount_factors` exactly.

**Worked example.** The base curve with its last pillar raised by one unit in the last place (the next binary64 above 0.9145993230349208) is refused (`inc_k-0006`).

The pitfall is comparing binary64 values with the golden's exact decimals: the golden prints 0.951697752271640363, binary64 gives 0.9516977522716404, and only binary64 against binary64 is exact.

### Q14.8 What was checked on the production (stage B) bootstrap?

*Level: advanced. Evidence: measured by the k-w1 lane. Source: `program/STAGE_K_W1_HANDOVER.md`*

First the premise, that earlier pillars cannot move; then, in a follow-up lane, the patched-against-rebuild check itself, after the stage B bootstrap got incremental entry points in all four builds.

On 10 sequential log-linear stage B bootstrap goldens, each quote was moved by 1 bp in turn.

**Worked example.** 45 single-quote moves; in every one the first pillar that changed was the moved quote's pillar and every earlier pillar was bit-identical (key `incremental_property_stage_b`, Python and Java). On the hand set, 10,000 random vectors were bit-identical to a full rebuild (key `incremental_property`).

Follow-up (2026-11-19): 10,000 moves over the 25 sequential stage B instrument sets, 10,000 of 10,000 bit-identical to a full rebuild in each of the four builds (key `incremental_property_stage_b_patched`; `specifications/02-curves/incremental-update.md`, "Acceptance evidence").

The pitfall is reading the CLI operation as the production path: `curve.incremental.update` works on the hand-sized annual par set; the stage B entry points are library functions, not a CLI operation.

## Recalibration triggers

### Q14.9 When does `calib.trigger.check` fire?

*Level: foundation. Evidence: golden (`trig_k-0001`, `trig_k-0002`). Source: `specifications/03-calibration/recalibration-triggers.md`, [Tutorial 53](../getting-started/tutorial-53-recalibration-triggers.md)*

When the input has moved since calibration by more than `k` standard deviations of its daily changes, scaled for the days elapsed.

Fire iff `|x_now - x_ref| > k sigma sqrt(d)`, `sigma` the sample standard deviation with `n - 1`.

**Worked example.** Changes `+1, -1, +1, -1`: `sigma = 2/sqrt 3 = 1.1547`, threshold at `k = 3`, `d = 1` is 3.4641. A move of 5 fires, a move of 2 does not.

The pitfall is the population standard deviation: dividing by `n` gives 1.0 here.

### Q14.10 What false-alarm rate does `k = 3` give, and why does the simulation centre on 0.0030306 instead?

*Level: advanced. Evidence: spec; measured by the k-w1 lane. Source: `specifications/03-calibration/recalibration-triggers.md`*

`alpha = 2 (1 - Phi(3)) = 0.0027` if `sigma` were known. With `sigma` estimated from a 250-day window, the move is judged against an estimate, and the predictive rate is a Student-t tail.

The spec's centre is `2 t_249.sf(3 / sqrt(1 + 1/250)) = 0.0030306` (SciPy), with a 99% binomial interval for 100,000 paths.

**Worked example.** The interval is [259, 349]; Python fired 291 times and Java 287 (key `trigger_simulation`). A planted 6-sigma move fired on 100,000 of 100,000 paths.

The pitfall is testing an estimated-sigma trigger against the known-sigma rate: 0.0027 would put the expected count near 270 and a correct implementation would look slightly too trigger-happy.

### Q14.11 Does a move exactly at the threshold fire?

*Level: practitioner. Evidence: golden (`trig_k-0004`, `trig_k-0005`); ruling KR-13. Source: `specifications/stage-k-rulings-w1.md`*

No: the rule is strictly greater.

KR-6 says "fires iff greater than"; KR-13 confirms it after the blind lane asked.

**Worked example.** Changes with mean 0 and sum of squares 7 over 8 values give `sigma` exactly 1.0; at `k = 2.5` a move of 2.5 does not fire (`trig_k-0004`) and 2.5000001 fires (`trig_k-0005`). `alpha = 0.012419`.

The pitfall is `>=` in an implementation, which differs only on exact ties and so passes most random tests.

### Q14.12 Why scale the threshold by `sqrt(d)`?

*Level: foundation. Evidence: golden (`trig_k-0003`). Source: `specifications/03-calibration/recalibration-triggers.md`*

A move built up over several days should be compared with several days of noise; for independent daily changes the standard deviation of a `d`-day move is `sigma sqrt(d)`.

**Worked example.** Four days after calibration the threshold is `3 x 1.1547 x 2 = 6.9282`, so a move of 5 that fires on day 1 does not fire on day 4 (`trig_k-0003`).

The pitfall is fat tails and autocorrelation: real changes are neither normal nor independent, so the realised false-alarm rate will differ from `alpha`.

## Intraday risk with error bounds

### Q14.13 What is the delta-gamma estimate for a zero-coupon bond, and what bounds its error?

*Level: foundation. Evidence: golden (`idr_k-0001`). Source: `specifications/06-risk/intraday-risk-bounds.md`, [Tutorial 54](../getting-started/tutorial-54-intraday-risk-bounds.md)*

The first two Taylor terms of the price change; the Lagrange remainder bounds what they leave out.

`V(y) = N exp(-y T)`, estimate `V(-T h + T^2 h^2 / 2)`, bound `M3 |h|^3 / 6` with `M3 = T^3 |N| exp(-T min(y, y + h))`.

**Worked example.** `N = 1,000,000`, `T = 5`, `y = 4%`, `h = +1%`: `V = 818,730.75`, estimate -39,913.12, exact -39,929.97, error 16.85, bound 17.06 (`idr_k-0001`).

The pitfall is reporting the estimate alone: a fast number with no bound is the old intraday risk.

### Q14.14 Why is the bound larger for a fall in yield than for a rise of the same size?

*Level: practitioner. Evidence: golden (`idr_k-0002`). Source: `specifications/06-risk/intraday-risk-bounds.md`*

`|V'''| = T^3 V` grows as the yield falls, so its maximum on the segment is at the lower end, `y + h` when `h < 0`.

**Worked example.** For `h = -1%` the bound is 17.93 against 17.06 for `+1%`, and the error is -17.27 (`idr_k-0002`).

The pitfall is evaluating `M3` at the starting yield, which understates the bound for negative shifts.

### Q14.15 How are position bounds combined for a book, and why not net them?

*Level: advanced. Evidence: golden (`idr_k-0005`, oracle-filled, not blind). Source: `specifications/06-risk/intraday-risk-bounds.md`*

They are added in absolute value. The remainders' signs are not known in general, so they may add instead of cancel.

**Worked example.** Long 1,000,000 at 5 years (4%) and short 500,000 at 2 years (3%), `h = +1%`: estimate -30,589.66, exact -30,605.88, error 16.22, bound 17.68, error over bound 0.917 (`idr_k-0005`).

The pitfall is reading the expected value as an outside check: it was filled by our own 50-digit oracle; it counts as outside-checked only because the later K-5a blind packet re-derived it (`program/STAGE_K_BLIND_K5A.md`).

### Q14.16 Why did this item first fail the 60% outside-check rule, and what closed the gap?

*Level: advanced. Evidence: measured by the k-w1 lane. Source: `oracle/OUTSIDE_SHARES.md` stage K section, `program/STAGE_K_BLIND_W1.md`*

The first blind lane checked the four single-position bounds only to six decimals (the goldens were later filled to full precision), and the fifth case was not in its packet, so at first 0 of 5 value cases counted. A second, clean blind packet re-derived all five at 1e-9 relative: 5 of 5 MATCH, so the item then stood at 5 of 5 (`program/STAGE_K_BLIND_K5A.md`). Ruling KR-234 later changed the bound; the version 2 packet matched 9 of 11, so the item now stands at 9 of 12 (`program/STAGE_K_BLIND_K5A_V2.md`, `oracle/OUTSIDE_SHARES.md`). That shows the spec is unambiguous and the arithmetic right; it does not check the bound's derivation.

**Worked example.** What was measured: 1,000 seeded moves on a 50-position book, zero violations of `|estimate - full revaluation| <= bound` in Python (worst ratio 0.0105) and Java (0.382), rechecked at 50 digits with zero violations and rounding at most 2.3e-8 of the bound (`oracle/IDR_K_MOVES_CHECK_W1.json`). That recheck is our own oracle, not an outside check.

The pitfall is counting the oracle as outside: it shares the author's reading of the spec.

## The Bermudan ladder convergence fix (K-8)

### Q14.17 What is the observed order, and how did it expose the first K-8 build?

*Level: foundation. Evidence: measured by the K-8 lane. Source: `program/K8_DIAGNOSIS.md`, [Tutorial 55](../getting-started/tutorial-55-bermudan-ladder-convergence.md)*

From values on three grids, each twice as fine, `p = log2((f1 - f2)/(f2 - f3))`; a second-order scheme gives about 2.

`num.richardson.check` reports `OK` only if both differences have the same sign and `|p - 2| <= 0.5`.

**Worked example.** The first build gave the 0.4986-year node row -337.0, -104.9 and 11.1 on three time grids, where the model derivative is 0: differences -232.1 and -116.0, ratio 2, order 1.00, `ORDER_MISMATCH`. Eighteen entries failed in all.

The pitfall is trusting a size check alone: that build was already within 0.39% at the default grid.

### Q14.18 What were the two causes of lost second order?

*Level: advanced. Evidence: measured and derived by the K-8 lane. Source: `program/K8_DIAGNOSIS.md` section 3*

(A) In time, a curve node at 0.4986 years fell inside a time step, so the step used the wrong mix of two forward rates; the price hardly noticed but the derivative of the jump is of order one over the node spacing. (B) In space, the cell-average smoothing of the exercise `max` left a price error of size `dx^3` that depends on where the exercise boundary sits in its cell; differentiating with respect to an input that moves the boundary turns it into a `dx^2` ladder error whose coefficient changes from grid to grid.

**Worked example.** (A) on a time-only refinement: row 1 order 1.00, row 2 differences +117.7 and +58.9. (B) on a space-only refinement, row 2 error of the first definition: -1064, -997, -379, -223, -158, -63 on 101 to 601 nodes; scaled by the square of the grid ratio, hat smoothing without the end correction gives -392, -546, -467, -510, -527, and with it -481, -483, -476, -467, -454.

The pitfall is the obvious suspect: more Rannacher half steps changed the result by less than 1 in 2e5.

### Q14.19 What does `CN_RANNACHER_SMOOTHED` change, and what does the smoothing give on `f = (-1, 0, 1)`?

*Level: practitioner. Evidence: spec (worked example). Source: `specifications/06-risk/bermudan-ladder-k8.md` 0.2.0*

It solves for `U = V exp(-int alpha)` so the curve leaves the time stepping (fix A), and replaces the cell average by a hat-weighted smoothing with an end correction and a `1 - delta^2/6` stencil (fix B). Each interval starts with implicit half steps.

`M(p, q) = int_0^1 (1 - u) max(p + (q - p) u, 0) du`; `h_i = M(f_i, f_{i-1}) + M(f_i, f_{i+1})`; `S_i = h_i - (h_{i-1} - 2 h_i + h_{i+1})/6`.

**Worked example.** With `f = (-1, 0, 1)`: `h = (0, 1/6, 1)`, `S_1 = 1/6 - (0 - 1/3 + 1)/6 = 1/18`. The pointwise `max` gives 0 and the old cell average 1/8.

The pitfall is the end correction's origin: it is derived in the lane and supported by measurements, not taken from a paper.

### Q14.20 After the second run passed, what is lifted and what is still restricted?

*Level: advanced. Evidence: measured; owner decision 2026-11-19. Source: `oracle/K8_ACCEPTANCE_W2.json`, `specifications/06-risk/bermudan-ladder-k8.md`*

Nothing is lifted. The R6 use restriction stays for both methods (ruling KR-113, 2026-11-19). A lift for `CN_RANNACHER_SMOOTHED` was made on the integration branch and withdrawn the same day, before release, after a different-model audit. The default method is still `G18_IMPLICIT`. All four builds have the new method.

Acceptance 1 to 3 pass in Python (worst default-grid gap 0.40% against 1%; 24 entries `OK` with orders 1.84 to 2.15), and acceptance 3 in Java (equal to Python to 3.8e-14 of the row scale), C++ and Rust (within 3.85e-14, `oracle/K8_ACCEPTANCE_PORTS.json`). The audit's objections, each checked: the evidence is at 201/100 only, and at 101/50, which the restriction's own text calls the default grid, the worst entries are +0.93%, -1.53% and +1.49%; the three cases are the ones the method was developed on (in-sample); and a deep in-the-money receiver is 7% to 9% off on d/da. The pitfall is reading "passes its acceptance" as "accurate everywhere".

**Worked example.** Case `aadladder_g-0001`, row 2 at 201/401/801: 222,756.98, 223,121.25, 223,212.48, order 1.997, 0.218% from the QuantLib reference. The zero row (node 0.4986) is 0.0 on every grid and is not judged under the all-zero-row rule (owner decision 2026-11-19); `program/K8_ROW0_FINDING.md` found no bug: its true value is zero, and QuantLib's -14.27 there is that engine's own time-stepping error.

The pitfall is hedging from the default ladder because "K-8 passed": the default has not changed.

## SA-CCR

### Q14.21 What are RC, PFE and EAD under SA-CCR?

*Level: foundation. Evidence: read (CRE52); golden (`saccr_k-0001`). Source: `specifications/06-risk/sa-ccr.md`, [Tutorial 56](../getting-started/tutorial-56-sa-ccr-example-1.md)*

RC is what the bank loses now if the counterparty defaults; PFE is what the exposure could grow to before replacement; EAD is 1.4 times their sum.

`RC = max(V - C, 0)` unmargined; `PFE = m x AddOn`; `EAD = 1.4 (RC + PFE)`.

**Worked example.** CRE99 Example 1: `V = 60`, `C = 0`, add-on 346.76, multiplier 1: `EAD = 1.4 x 406.76 = 569.47`, printed 569.

The pitfall is rounding the add-on to 347 first: `1.4 x 407 = 569.8` would print 570.

### Q14.22 How do the two swaps of Example 1 offset each other?

*Level: practitioner. Evidence: golden (`saccr_k-0001`). Source: `specifications/06-risk/sa-ccr.md` step 6*

They are in one hedging set (USD) but in adjacent maturity buckets, which offset with correlation 0.7 in the aggregation formula.

`EN = sqrt(D1^2 + D2^2 + D3^2 + 1.4 D1 D2 + 1.4 D2 D3 + 0.6 D1 D3)`, buckets by end date: under 1, 1 to 5, over 5 years.

**Worked example.** `D2 = -36,254` (4-year receiver), `D3 = 78,694` (10-year payer): `EN = 59,270` against 114,948 gross; add-on `0.005 x 59,270 = 296.35`.

The pitfall is bucketing by time to start or by option expiry: the swaption (1 into 10) goes to the over-5-years bucket by its end date.

### Q14.23 How is the supervisory delta of the swaption found?

*Level: practitioner. Evidence: read (CRE52.40); golden (`saccr_k-0001`). Source: `specifications/06-risk/sa-ccr.md` step 3*

From a Black-type formula with a fixed supervisory volatility, 50% for interest rate options, not the market's volatility.

Bought put: `delta = -Phi(-d1)`, `d1 = (ln(P/K) + sigma^2 T/2) / (sigma sqrt T)`.

**Worked example.** `P = 6%`, `K = 5%`, `T = 1`: `d1 = (ln 1.2 + 0.125)/0.5 = 0.6146`, `delta = -0.2694`; `D = 37,428 x -0.2694 = -10,083`.

The pitfall is the sign: the swaption is short the floating rate, so it is a put on the rate even though it is bought.

### Q14.24 What is the SA-CCR outside-check share, and why are four matching cases excluded?

*Level: advanced. Evidence: measured; blind record. Source: `program/STAGE_K_BLIND_W1B.md`*

12 of 19 value cases, 63.2%: the five published Basel examples, counted through the blind packet that re-derived them (a printed figure alone does not count, ruling KR-250), plus seven blind re-derivations. The three audit cases saccr_k-0040 to 0042 have no blind check. Four more blind matches are excluded because the blind lane had read the unstripped spec once before the packet existed, which showed output facts for those four.

**Worked example.** Blind compare run 2: 11 of 11 MATCH; counted 7 (0007 to 0012, 0014); excluded 0006, 0013, 0015, 0016. Counting them would give 16 of 16, which the record does not claim. Run 1 compared nothing because of a wrapper-level bug in the compare script; no value was seen or changed.

The pitfall is "they matched, so count them": a blind check is only blind if the lane could not have known the answer.

## Backtesting traffic light

### Q14.25 Where do the amber and red boundaries come from?

*Level: foundation. Evidence: read (MAR99.17); computed. Source: `specifications/06-risk/frtb-ima-backtest.md`, [Tutorial 57](../getting-started/tutorial-57-backtesting-traffic-light.md)*

From the binomial distribution of exceptions for a correct 99% model: amber starts at the first count whose cumulative probability reaches 95%, red at 99.99%.

`X ~ Binomial(n, 0.01)`, `amber_from = min{k : P(X <= k) >= 0.95}`, `red_from = min{k : P(X <= k) >= 0.9999}`.

**Worked example.** At 250 days `P(X <= 4) = 89.22%` and `P(X <= 5) = 95.88%`, so amber from 5; `P(X <= 9) = 99.97%`, `P(X <= 10) = 99.99%`, so red from 10.

The pitfall is reading 95% as the chance of wrongly leaving green; that chance is `1 - P(X <= 4) = 10.78%`.

### Q14.26 Which exception count does FRTB use, and what multiplier follows?

*Level: practitioner. Evidence: read (MAR99.8, MAR32 Table 1). Source: `specifications/06-risk/frtb-ima-backtest.md`*

The greater of the actual and hypothetical P&L counts. At 250 days the multiplier is 1.50 for 0 to 4, then 1.70, 1.76, 1.83, 1.88, 1.92 for 5 to 9, and 2.00 from 10.

**Worked example.** 3 actual and 5 hypothetical exceptions: count 5, amber, cumulative 0.958817, multiplier 1.70.

The pitfall is the 1996 framework of stage F (`risk.backtest.traffic_light`), which adds a plus factor to a base of 3; that is why K-8e added new operations instead of extending the old one (KR-40).

### Q14.27 Why is zero exceptions in five days amber under the rule as written?

*Level: advanced. Evidence: spec (KR-42). Source: `specifications/stage-k-rulings-w1b.md`*

Because `P(X = 0) = 0.99^5 = 0.950990 >= 0.95`, so the first count reaching 95% is 0. The spec applies MAR99.17's general rule as written and records the oddity rather than adding a rule of its own.

**Worked example.** At 500 days the same rule gives amber from 9 and red from 15; no multiplier is published for 500 days, so the output is null.

The pitfall is "fixing" small samples quietly: any such rule is a new ruling and must be written down.

### Q14.28 When does a trading desk lose permission to use its model?

*Level: practitioner. Evidence: read (MAR32.19); ruling KR-44. Source: `specifications/06-risk/frtb-ima-backtest.md`*

With more than 12 exceptions at 99% or more than 30 at 97.5% in the most recent 12 months, each the greater of actual and hypothetical.

**Worked example.** 12 and 30: eligible. 13 and 30, or 12 and 31: not eligible (goldens `btk_k-0019` to `0021`).

The pitfall is the text: "more than 12 ... or 30" is read as "more than 30" for the second limit (KR-44, inferred and pinned by goldens).

## The daily paper ledger

### Q14.29 What does a DAY row's P&L explain contain, and why must the unexplained term be exactly zero?

*Level: foundation. Evidence: spec (worked example); computed. Source: `specifications/12-platform/paper-ledger-daily.md`, [Tutorial 58](../getting-started/tutorial-58-daily-paper-ledger.md)*

Carry (coupon accrual and cash interest), roll-down, curve move, and fills and costs; unexplained is the NAV change minus those.

Every term is an exact decimal product of recorded 6-decimal marks and whole lots, the three market terms telescope to `n x (mark - 100)`, and the only rounding (cash interest to the cent) is posted as rounded, so the residual is zero by construction (KR-79).

**Worked example.** The spec's worked day: carry 1,213.9355, roll-down 16.5625, curve move -1,993.7275, fills and costs -124.21875; sum -887.44825, equal to NAV 9,998,826.61425 minus 9,999,714.0625.

The pitfall is reading the zero as model quality: it is a bookkeeping test, with no performance claim.

### Q14.30 What can be verified from the ledger alone, with no CLI and no outside data?

*Level: practitioner. Evidence: spec. Source: `specifications/12-platform/paper-ledger-daily.md` "Verification"*

The chain (`PARSE`, `SEQ`, `HASH`, `LINK`, `LABEL`, `FORMAT`, `KIND`), the configuration against the genesis row, the dates (business days, none missing, timing label, holdout windows), and an exact replay: from the genesis cash each day opens at the previous close, and cash interest, every explain term, cash, positions, NAV and P&L are recomputed in exact decimal from the row's own marks and fills.

**Worked example.** `verify_ledger.py verify --ledger ledger.jsonl --no-cli` runs everything except the calendar checks and the CLI rebuild, and says so in its output (`"calendar_checked": false, "recomputed": false`).

The pitfall is thinking the replay checks the marks: a wrong mark replays consistently. The CLI rebuild (`RECOMPUTE`) is what catches it.

### Q14.31 What do the anchors add to the hash chain?

*Level: advanced. Evidence: spec (P5). Source: `specifications/12-platform/paper-ledger-daily.md` "Chain and anchor"*

A chain shows that rows were not edited after writing, but someone who rewrites an old row can recompute every later hash and get a valid chain. An anchor, the head hash and row count stamped with OpenTimestamps on a separate branch, fixes what the ledger was at a moment.

**Worked example.** Acceptance P5: a rewrite of an old row with every later hash recomputed passes the chain and the replay and fails the anchor check; a truncated ledger fails it too.

The pitfall is a ledger without published anchors: truncating the last line leaves a valid shorter chain.

### Q14.32 How many recorded trading days are there, and why are FedInvest prices not used?

*Level: foundation. Evidence: read (terms and robots file, 2026-11-19); handover. Source: `program/STAGE_K_PAPER_HANDOVER.md`*

Zero of the 20 that the v1.0.0 gate needs: the workflow has never run, and the earliest 20th on-time day is 20 US business days after it reaches `main`. FedInvest prices are not used because the site's robots file disallows automated agents and its terms limit use to personal viewing (KR-70); the ledger uses constant-maturity exposures on a curve through the five Treasury par yields the recorder already keeps.

**Worked example.** A day counts only if a Bitcoin block time, plus two hours, falls before its cut-off in a ledger that passes full verification; the row's own on-time label is not counted (KR-200, KR-201). The gate is `verify_ledger.py verify --ledger L --anchors A --forward-log F --bitcoin-headers H --require-days 20` (KR-202); it refuses with `--no-cli` or without the anchors, the recorder log or the headers. A 30-day ledger written in one sitting and stamped afterwards records 0 days (spec worked example, synthetic).

The pitfall is calling the marks prices: they are paper marks on a fitted curve, not tradable.

## Second pass: derivations and judgement (added 2026-11-20)

Questions Q14.33 to Q14.52 go one step further than the first pass: each asks for a derivation, a size or a judgement. Evidence classes as in the [index](README.md): `spec` and `golden` are read from the files named; `computed` numbers are recomputed by `verify/v14_stage_k.py` with the standard library; `observed` numbers were printed by the Python build on 2026-11-20 (local laptop, not the acceptance machine); `inferred` marks reasoning that no file states.

### Q14.33 Why can a store with one time axis not replace a bitemporal store, and what does a query before the first knowledge time return?

*Level: foundation. Evidence: spec (read); golden (`bt_k-0001`, `bt_k-0002`, `bt_k-0006`). Source: `specifications/01-core/bitemporal-store.md`*

A store keyed by valid time alone (one row per period, overwritten on correction) can say what the February value is now, but not what it was believed to be in March. A store keyed by knowledge time alone (daily snapshots) can say what was known on a date, but every snapshot repeats every period, and a correction to February must be copied into every later snapshot. The bitemporal record holds both, once.

Formally the query is a function of two times, `(K, V)`; fixing `K` to "now" gives the valid-time store and fixing `V` gives one snapshot. Before any record is known (`K` earlier than every `knowledge_time`) the candidate set is empty and the answer is `NONE`.

**Worked example.** On the shared golden log, `(15 March, 15 February)` gives 100 and `(1 April, 15 February)` gives 105 (`bt_k-0001`, `bt_k-0002`). Asked at 12:00 on 1 January, before record 1 (learned 2 January) existed, the answer is `NONE` with no row (`bt_k-0006`).

The pitfall is answering `NONE` with the earliest value known later; that is exactly the look-ahead a backtest must not have.

### Q14.34 A quote at 0-based index `j` of an `n`-pillar annual par curve moves. How many pillars does `curve.incremental.update` solve again, and what does the call cost?

*Level: practitioner. Evidence: spec (read); golden (`inc_k-0002` to `inc_k-0004`). Source: `specifications/02-curves/incremental-update.md`*

It solves `n - j` pillars and copies `j`. The call still costs at least one full bootstrap, because it rebuilds `previous_quotes` to check the cache bit for bit.

The recursion `P_k = (1 - S_k A_{k-1}) / (1 + S_k)` with `A_{k-1} = sum_{i<k} P_i` makes pillar `k` a function of `S_1..S_k` only, so a change at `j` leaves `P_0..P_{j-1}` and their running sum unchanged.

**Worked example.** On the three-pillar base curve: a move at index 1 gives `recomputed` 2 (`inc_k-0002`), a move at index 2 gives 1 (`inc_k-0003`), no move gives 0 and `first_changed_index` null (`inc_k-0004`).

The pitfall is quoting the operation's `recomputed` as a speed-up. The saving is in the library entry points without the check (`ois.bootstrap_incremental` in Python), which a caller uses when it already trusts its cache.

### Q14.35 Why does the spec ask for the incremental curve to be bit-identical to a full rebuild, not just within 1e-12?

*Level: advanced. Evidence: spec (read; KR-230, KR-235); inferred. Source: `specifications/02-curves/incremental-update.md` version 1.1.0 header*

Because it can be. The incremental path performs the same floating-point operations in the same order as the full path from the first changed pillar on: the copied running sum is the same bits, and each later step is one multiply, one subtract, one add and one divide, each correctly rounded (contract "Numeric rules": no contraction, sums in array order). Equal inputs and equal operations give equal bits.

The 1e-12 relative tolerance in the acceptance text is the K-4 claim; bit identity is the stronger property the builds meet.

**Worked example.** Observed: `curve.incremental.update` and `curve.bootstrap.par_annual` on quotes 2%, 2.6%, 3% both print `[0.9803921568627451, 0.9498146237052325, 0.9146541714397676]` (see the [cookbook recipe](../../COOKBOOK.md#update-one-curve-node-incrementally-and-compare-with-a-full-rebuild)). Goldens `inc_k-0007` and `inc_k-0008` use seeded quote vectors whose fused-multiply-add bootstrap differs from the contract's, so a build that contracts sees its own cache as stale and fails them.

The pitfall is an optimiser: a compiler allowed to fuse `S * acc` into the subtraction changes the last bit, and the bit-for-bit cache check then refuses every update.

### Q14.36 Why is a cache that is off by one unit in the last place refused instead of patched?

*Level: practitioner. Evidence: spec (read); golden (`inc_k-0006`). Source: `specifications/02-curves/incremental-update.md`*

A cache that is not the bootstrap of its own quotes has come from somewhere else: another curve, another build, an earlier bug. Patching it would mix two curves and the result would match neither. The operation cannot tell a harmless one-unit difference from a wrong curve, so it refuses both.

Formally `previous_discount_factors` must equal `curve.bootstrap.par_annual(previous_quotes)` bit for bit, else `E_INPUT`.

**Worked example.** `inc_k-0006` moves the last cached factor from `0.9145993230349208` to the next binary64 above it, `...9209`, and the answer is `E_INPUT`, "previous_discount_factors is not the bootstrap of previous_quotes" (observed).

The pitfall is treating `E_INPUT` here as a nuisance and loosening the check; the check is the only thing that ties the copied pillars to the quotes the caller says they came from.

### Q14.37 With two one-day changes, how often does `calib.trigger.check` fire on noise at `k = 3`?

*Level: advanced. Evidence: spec (read; KR-232); golden (`trig_k-0010`); computed. Source: `specifications/03-calibration/recalibration-triggers.md`*

About one time in five. With `n = 2` changes the sample standard deviation has one degree of freedom, and the move divided by it is Student-t with 1 degree of freedom, which is the Cauchy distribution.

`P(|T_1| > k) = 1 - (2/pi) atan(k) = (2/pi) atan(1/k)`.

**Worked example.** At `k = 3`: `(2/pi) atan(1/3) = 0.20483276469913345`, the golden's `false_alarm_rate` (`trig_k-0010`), against a `nominal_rate` of 0.0027. A trigger that promises 0.27% and delivers 20.5% is the two-change case of audit finding KA-A4 (which measured four changes) that version 1.1.0 corrected.

The pitfall is the normal tail with an estimated sigma: it is only right when the window is long enough that sigma is nearly known.

### Q14.38 And with three changes?

*Level: advanced. Evidence: spec (read); golden (`trig_k-0011`); computed. Source: `specifications/03-calibration/recalibration-triggers.md`*

About one time in ten. With 2 degrees of freedom the Student-t tail has a closed form.

`P(|T_2| > k) = 1 - k / sqrt(k^2 + 2)`.

**Worked example.** At `k = 3`: `1 - 3/sqrt(11) = 0.0954660`, the golden's 0.09546596626670913 (`trig_k-0011`). Four changes (3 degrees of freedom) give 0.0576689 (`trig_k-0001`).

The pitfall is reading `nominal_rate` as the operating characteristic; it is the rate for a sigma known exactly, which the trigger never has.

### Q14.39 How long must the window be before the as-used false-alarm rate is close to the nominal 0.27% at `k = 3`?

*Level: advanced. Evidence: golden (`trig_k-0013`, `trig_k-0014`); computed. Source: `specifications/03-calibration/recalibration-triggers.md`, "New cases (1.1.0)"*

Longer than a desk would like. The ratio of the as-used rate to the nominal rate falls slowly with the window.

`false_alarm_rate / nominal_rate = P(|T_(n-1)| > 3) / (2 Phi(-3))`, with `2 Phi(-3) = 0.0026998`.

**Worked example.** `n = 4`: 0.0577, 21.4 times nominal. `n = 30`: 0.0054992 (`trig_k-0013`), 2.04 times. `n = 250`: 0.0029738 (`trig_k-0014`), 1.10 times. So even a year of daily changes leaves the trigger firing on noise 10% more often than the normal tail says.

The pitfall is choosing `k` from the normal table; choose it from `false_alarm_rate` for the window you actually use.

### Q14.40 A move lands exactly on the threshold. Does the trigger fire, and why does the spec bother to say?

*Level: practitioner. Evidence: spec (read; KR-13); golden (`trig_k-0004`). Source: `specifications/stage-k-rulings-w1.md`*

It does not fire: the rule is strictly greater than. For continuous data a tie has probability zero, but rates and prices are quoted on grids, so ties happen, and two builds that disagree on a tie would disagree on whether to recalibrate.

`fire = |x_now - x_ref| > k sigma sqrt(d)`.

**Worked example.** Changes `[0.5, -1.0, 1.5, -0.5, 0.0, 1.0, -1.5, 0.0]` have mean 0 and sum of squares 7, so `sigma = sqrt(7/7) = 1` exactly; at `k = 2.5` the threshold is exactly 2.5 and a move of 2.5 does not fire (`trig_k-0004`).

The pitfall is a golden that cannot see the rule: a test case whose threshold is not exactly representable never exercises the tie.

### Q14.41 Why is a window of three equal changes refused?

*Level: practitioner. Evidence: spec (read; KR-233); golden (`trig_k-0017`). Source: `specifications/03-calibration/recalibration-triggers.md`*

Because the computed sigma is rounding noise, not a noise scale. `[0.1, 0.1, 0.1]` should have sigma 0; in binary64 the mean is not exactly 0.1 and the deviations are not exactly zero, so version 1.0.0 returned a sigma of about 1.7e-17 and any move fired.

KR-233: if `sigma <= 2^-26 max |c_i|` the result is `E_DOMAIN`. Below that level the computed sigma may be the rounding of a constant window (at most 3.2e-16 of the largest change); above it the computed sigma is right to 2.2e-8 relative.

**Worked example.** `trig_k-0017` (`[0.1] x 3`) and `trig_k-0019` (`[0, 0]`) are `E_DOMAIN`; `trig_k-0021` has sigma 1.56e-8, just above the floor, and is a value case compared at 3e-8 relative.

The pitfall is a threshold of zero: `k x 0 = 0`, and every move, however small, fires.

### Q14.42 Derive the bound of `idr_k-0001` by hand.

*Level: foundation. Evidence: spec (read); golden (`idr_k-0001`); computed. Source: `specifications/06-risk/intraday-risk-bounds.md`*

For `V(y) = N exp(-yT)` the third derivative is `-T^3 V`, largest in size at the lower of the two yields. Taylor's remainder gives the bound.

`L = |h|^3 T^3 |N| exp(-T min(y, y + h)) / 6`; the 1.1.0 `bound` adds a rounding allowance (KR-234).

**Worked example.** `N` 1,000,000, `T` 5, `y` 4%, `h` +1%: `V(y) = 818,730.753`, `L = 0.01^3 x 125 x 818,730.753 / 6 = 17.05689068912462`. The golden's `bound` is 17.056890689308766: the allowance is 1.8e-10, 1.1e-11 of the bound. Full revaluation gives -39,929.970, the estimate is -39,913.124, the error 16.846, so the bound is used to 98.8%.

The pitfall is reading the bound as loose: for one zero-coupon position it is nearly tight, because `V'''` barely changes over a 1% move.

### Q14.43 Why are position bounds added without netting, and what does a two-position book show?

*Level: practitioner. Evidence: spec (read; KR-15); golden (`idr_k-0005`); computed. Source: `specifications/06-risk/intraday-risk-bounds.md`*

The remainder of each position has a sign that depends on where in the move the third derivative is evaluated, which the bound does not know. The triangle inequality allows only the sum of absolute bounds.

`bound = sum_i L_i + sum_i rho_i`, with `|N_i|` in each `L_i`.

**Worked example.** `idr_k-0005` adds a short position, `N = -500,000`, `T` 2, `y` 3%: `L_2 = 0.01^3 x 8 x 500,000 x exp(-0.06) / 6 = 0.62784`, so `L_1 + L_2 = 17.68473`, and the golden's `bound` is 17.684733711514124. The error is 16.221, 91.7% of the bound: the short position's remainder offsets a little of the long one's, and the bound cannot use that.

The pitfall is a hedged book: two large offsetting positions have a small error and a large bound. The bound is a guarantee, not an estimate of the error.

### Q14.44 Why did version 1.0.0's bound fail for very small moves?

*Level: advanced. Evidence: spec (read; KA-A6, KR-234); inferred. Source: `specifications/06-risk/intraday-risk-bounds.md`, "Version 1.1.0 in brief"*

The Lagrange term shrinks as `h^3`, but the binary64 estimate carries a rounding error of order `eps |V| T |h|`, which shrinks only as `h`. Below some move the rounding error is larger than the exact-arithmetic bound, so the claim "error at most bound" fails in binary64.

KR-234 adds `rho_i = 2^-49 (1 + T|y| + T|h|) (|v| (T|h| + T^2 h^2) + ...)` per position, which scales with `h` like the rounding.

**Worked example.** At `h = 1e-9` on the `idr_k-0001` position, `L = 1e-27 x 125 x 818,730.753 / 6 = 1.7e-20`, while `eps |V| T |h| = 1.1e-16 x 818,730.753 x 5 x 1e-9 = 4.5e-19`, about 26 times larger (inferred, order of magnitude). The audit measured an error 21.6 times the 1.0.0 bound at that move (KA-A6, measured with a 60-digit reference).

The pitfall is testing a bound only on moves where it is comfortable: the 1,000-move acceptance run of 1.0.0 passed, presumably because none of its moves was that small (inferred; the moves are logged in `program/stage_k_w1/acceptance_python.json`).

### Q14.45 Two 10-year USD swaps, received on 10,000 (value +30) and paid on 5,000 (value -10), no collateral. What is the SA-CCR EAD?

*Level: practitioner. Evidence: spec (read; CRE52 as stated in the spec); computed; observed. Source: `specifications/06-risk/sa-ccr.md`, [cookbook recipe](../../COOKBOOK.md#sa-ccr-ead-for-a-small-netting-set-by-hand-and-by-cli)*

Both trades sit in the over-5-year bucket of the USD hedging set, so their effective notionals offset in full.

`SD = (exp(-0.05 S) - exp(-0.05 E)) / 0.05`, `D = delta x N x SD x MF`, add-on `0.005 x |D_3|` here, `RC = max(V, 0)`, `m = 1` for `V >= 0`, `EAD = 1.4 (RC + m AddOn)`.

**Worked example.** `SD = (1 - exp(-0.5)) / 0.05 = 7.869387`; `D = 78,693.87 - 39,346.93 = 39,346.93`; add-on `196.73`; `V = 20`; `EAD = 1.4 x 216.73 = 303.43`. The Python build prints 303.4285382011566 (observed). Without the short swap the EAD would be `1.4 x (30 + 393.47) = 592.86` (observed 592.8570764023132).

The pitfall is netting across buckets at 100%: the same two trades at 3 years and 10 years would offset only through the bucket correlations of Q14.46.

### Q14.46 Why does the interest-rate aggregation have cross terms 1.4 and 0.6, and what do they do to two offsetting trades?

*Level: advanced. Evidence: spec (read); computed; inferred. Source: `specifications/06-risk/sa-ccr.md`, Q14.22*

The three maturity buckets are aggregated as if correlated: 70% between adjacent buckets and 30% between the first and third. The formula is `sqrt(D' R D)` with that correlation matrix, and `2 x 0.7 = 1.4`, `2 x 0.3 = 0.6`.

`EN = sqrt(D_1^2 + D_2^2 + D_3^2 + 1.4 D_1 D_2 + 1.4 D_2 D_3 + 0.6 D_1 D_3)`.

**Worked example.** Equal and opposite effective notionals `X` and `-X`: in the same bucket `EN = 0`; in adjacent buckets `EN = X sqrt(2 - 1.4) = 0.7746 X`; in buckets 1 and 3 `EN = X sqrt(2 - 0.6) = 1.1832 X`, more than either trade alone. Basel Example 1's swaps (buckets 2 and 3) give 59,270 from 114,948 gross (Q14.22).

The pitfall is reading the 1.4 as the alpha of `EAD = 1.4 (RC + PFE)`; they are different numbers that happen to be equal.

### Q14.47 The same two swaps are worth -310 to us. What happens to the multiplier and the EAD?

*Level: practitioner. Evidence: spec (read); computed; observed. Source: `specifications/06-risk/sa-ccr.md`*

A netting set that is out of the money is less likely to become an exposure, so SA-CCR scales the add-on down, but never below 5%.

`m = min(1, 0.05 + 0.95 exp((V - C) / (2 x 0.95 x AddOn)))`, `RC = max(V - C, 0)`.

**Worked example.** `V = -310`, add-on 196.73: `m = 0.05 + 0.95 exp(-310 / 373.80) = 0.4645`; `RC = 0`; `EAD = 1.4 x 0.4645 x 196.73 = 127.94`. The Python build prints `multiplier` 0.4645246062932369 and `ead` 127.94333326981402 (observed).

The pitfall is expecting a large negative value to bring EAD to zero: the floor keeps at least 5% of the add-on, so here `EAD >= 1.4 x 0.05 x 196.73 = 13.77` however negative the set becomes.

### Q14.48 A desk's true 99% VaR is really a 98% VaR. How likely is a 250-day backtest to put it in amber or red?

*Level: advanced. Evidence: computed (exact binomial in `verify/v14_stage_k.py`); inferred. Source: `specifications/06-risk/frtb-ima-backtest.md`*

Only a little better than a coin toss. The test's boundaries are set so a correct model rarely leaves green; they are not set to catch a model that is moderately wrong.

With true exception rate `p`, `P(amber or red) = P(X >= 5)`, `X ~ Binomial(250, p)`.

**Worked example.** `p = 1%` (correct): 10.78%. `p = 2%`: 56.13%, and red (10 or more) only 3.04%. `p = 3%`: 87.18%, red 22.10%.

The pitfall is reading a green year as validation: a model whose exceptions come twice as often as it states stays green 44% of the time (`P(X <= 4) = 43.87%` at `p = 2%`).

### Q14.49 Why is one observation with no exception YELLOW at 95% confidence in `risk.backtest.traffic_light`?

*Level: advanced. Evidence: golden (`tlk_k-0016`); spec (read; KR-253). Source: `docs/known-issues.md`, `specifications/06-risk/var-es-and-backtests.md` 1.1.0*

Because `P(X <= 0) = c^1 = 0.95` exactly, which is on the green/yellow edge, and the rule puts the edge in yellow. Before KR-253 the operation computed the probability through `lgamma` and said GREEN there (CHANGELOG, "Changed"); that the old result fell just below 0.95 by rounding is inferred.

From 1.1.0 the non-exception probability is `q = c` as given; `x = 0` is `c^n` by double-double powering, so the edge is decided exactly.

**Worked example.** `tlk_k-0016`: `n` 1, `x` 0, `c` 0.95 gives 0.95, YELLOW; `tlk_k-0017` (`c` 0.99) gives 0.99, YELLOW; `tlk_k-0018` (`c` 0.9999) gives 0.9999, RED.

The pitfall is a "small" numerical change to a released operation: it moved a zone, so it is recorded as a behaviour change (KR-253) and listed in the known issues.

### Q14.50 An attacker edits row 7 of a hash-chained ledger. What does the verifier report if they recompute nothing, only row 7's hash, or every later hash?

*Level: practitioner. Evidence: spec (read; HR-45, HR-46); golden (`pt_h-0021`, `pt_h-0022`); observed. Source: `specifications/10-execution/paper-trading.md`, `specifications/12-platform/paper-ledger-daily.md`*

Nothing recomputed: `HASH` at row 7, because the stored hash no longer matches the row. Row 7's hash recomputed: `LINK` at row 8, because row 8's `prev` still holds the old hash. Every later hash recomputed: the chain passes, and only an anchor made before the edit (a head hash and row count stamped outside the repository) catches it.

`hash_k = SHA-256(canonical(row_k without hash))`, `prev_k = hash_(k-1)`, `prev_0` = 64 zeros.

**Worked example.** `pt_h-0021` changes `limit_price` from "101" to "102" in a one-row ledger: `HASH` at 0, because "101" hashes to `72c85984...7e81` and "102" to `937f6a4d...4e90` (observed). `pt_h-0022` is a two-row ledger whose second row's `prev` does not match: `LINK` at 1.

The pitfall is publishing a ledger without publishing its anchors: the third attack then leaves no trace.

### Q14.51 Show that the paper ledger's three market terms telescope on the spec's worked day.

*Level: practitioner. Evidence: spec (read); computed. Source: `specifications/12-platform/paper-ledger-daily.md`, "Daily P&L explain"*

Carry aside, the market terms are roll-down `n (clean_roll - 100)` and curve move `n (clean_close - clean_roll)`; `clean_roll` cancels, leaving `n (clean_close - 100)`, the change in mark since the position was struck at par. That is why their sum cannot leak.

**Worked example.** `n` 26,500, `clean_roll` 100.000625, `clean_close` 99.925390: roll-down 16.5625, curve move -1,993.7275, sum -1,977.165 = `26,500 x (99.925390 - 100)`. With carry 1,213.9355 and fills and costs -124.21875 the day is -887.44825, unexplained 0.

The pitfall is a roll-down computed on a different day count or curve than the curve move; the cancellation then fails and the residual is a bookkeeping defect, not a market effect.

### Q14.52 Why are the margin weights labelled "placeholder weights", and what can a result computed with them be used for?

*Level: foundation. Evidence: spec (read; KR-130, KR-150); golden (`sbim_alias_k-0001`); computed. Source: `specifications/06-risk/sbim-placeholder.md`, `specifications/stage-k-rulings-margin.md`*

Because they are invented by a visible rule, not taken from any calibration: risk weight `RW_k = 10 x k` and correlation `rho(k, l) = 1 - 0.1 |k - l|` on six tenors. The project uses no ISDA material (owner decision 2026-11-19). A result shows that the aggregation formula is implemented the same way in four builds; the number itself means nothing about real margin.

`WS_k = RW_k s_k CR`, `margin = sqrt(max(0, sum_k sum_l rho_kl WS_k WS_l))`.

**Worked example.** Sensitivities `[1,000, -500, 2,500, 4,000, -1,200, 300]` give `WS = [10,000, -10,000, 75,000, 160,000, -60,000, 18,000]` and margin 190,937.16 (`sbim_alias_k-0001`, observed for both the new id and the deprecated alias). The hand-typed weights of v0.7.0 to v0.10.0 gave 452,205.34 on the same sensitivities (`sbim_g-0001` before KR-150), which was no more meaningful.

The pitfall is quoting the margin figure outside the project: it would read as an initial margin, and it is not one.

## Third pass: wave 2 capital, wrong-way CVA, snapshots, adapters and soak (added 2026-11-21)

These questions cover what pull requests #60 to #64 added to main on 2026-11-20. Every worked number is from a golden or was recomputed by `verify/v14_stage_k.py`; the Python build agreed with each golden used here when run on 2026-11-21 (measured, local laptop, not the acceptance machine).

### Q14.53 A long stock of 50 and a short senior bond of 40 on the same BB issuer. Why does the bond not offset the stock in the default risk charge, and what is the DRC?

*Level: practitioner. Evidence: spec (read; KR-53); golden (`drc_k-0007`); computed. Source: `specifications/06-risk/frtb-drc-rrao.md`*

A short can offset a long on the same obligor only if it is no more senior: if the issuer defaults, a senior bond recovers more than the stock, so being short the bond does not pay back the full loss on the stock. The two stay on opposite sides of the bucket, and the hedge benefit ratio decides how much of the short still counts.

Jump-to-default is `LGD x notional + PnL` before netting; the bucket charge is `DRC_b = max(sum RW net_long - HBR sum RW |net_short|, 0)` with `HBR = sum net_long / (sum net_long + sum |net_short|)`.

**Worked example.** Stock JTD 50 (LGD 100%); bond JTD `0.75 x (-40) = -30` (LGD 75% for senior debt). BB risk weight 15%: weighted long 7.5, weighted short 4.5. `HBR = 50 / (50 + 30) = 0.625`, so `DRC = 7.5 - 0.625 x 4.5 = 4.6875` (`drc_k-0007`).

The pitfall is netting by obligor alone: treating the bond as a full offset gives `max(50 - 30, 0) x 0.15 = 3`, which understates the charge.

### Q14.54 Why does the IMCC take half a diversified figure and half an undiversified one, and what is it for the golden `imcc_k-0001`?

*Level: practitioner. Evidence: spec (read; MAR33.15, KR-58); golden (`imcc_k-0001`); computed. Source: `specifications/06-risk/frtb-ima.md`*

Diversification between risk classes is real on average but unreliable in a stress, so the rule gives it half credit: half the all-classes expected shortfall, half the sum of the class-by-class figures. Each figure is a stressed ES scaled from a reduced set of risk factors.

`ES = ES_R,S max(1, ES_F,C / ES_R,C)` for each triple, then `IMCC = 0.5 IMCC(C) + 0.5 sum_i IMCC(C_i)`.

**Worked example.** Portfolio (12, 10, 8): `12 x 1.25 = 15`. IR (6, 5, 4): `6 x 1.25 = 7.5`. EQ (5, 4, 5): the ratio 0.8 is floored at 1, so 5, and EQ appears in `classes_floored`. `IMCC = 0.5 x 15 + 0.5 x 12.5 = 13.75` (`imcc_k-0001`).

The pitfall is letting the ratio fall below 1: the reduced set would then be scaled down because today's full set happens to look calmer, which the floor forbids.

### Q14.55 An IMA bank has six backtesting exceptions and one amber desk. Walk through `risk.frtb.ima.capital` on `cap_k-0002`.

*Level: advanced. Evidence: spec (read; MAR33.41 to 33.45, KR-61); golden (`cap_k-0002`); computed. Source: `specifications/06-risk/frtb-ima.md`*

The model figure is the larger of yesterday's charge and a multiple of the 60-day average; the multiple rises with exceptions. If some desks are amber and the standardised charge is above the model charge, part of the gap is added back as a surcharge, and the total is capped by the standardised charge of all desks.

`C_A = max(imcc_prev + ses_prev, m_c imcc_avg + ses_avg)`; `IMA_G,A = C_A + drc`; `k = 0.5 sum_amber sa / sum sa`; `surcharge = k max(0, SA_G,A - IMA_G,A)`; `ACR = min(IMA_G,A + surcharge + c_u, sa_all) + max(0, IMA_G,A - SA_G,A)`.

**Worked example.** `m_c = 1.76` for six exceptions. `C_A = max(120, 1.76 x 90 + 15) = 173.4`; with DRC 30, `IMA_G,A = 203.4`. Desks GREEN 150 and AMBER 100: `SA_G,A = 250`, `k = 0.2`, `surcharge = 0.2 x 46.6 = 9.32`. With `c_u = 40` and `sa_all = 300`: `ACR = min(252.72, 300) + 0 = 252.72` (`cap_k-0002`).

The pitfall is reading `m_c` from the exception count alone: the qualitative add-on is added to the table value, and a bank-level count and a desk-level zone are different inputs.

### Q14.56 With one counterparty, why does reduced BA-CVA equal the standalone charge, and what does a second counterparty do?

*Level: practitioner. Evidence: spec (read; MAR50.14 to 50.16); golden (`cva_k-0001`, `cva_k-0002`); computed. Source: `specifications/06-risk/cva-capital.md`*

The reduced formula mixes a fully correlated part (weight `0.5^2 = 0.25`) and an independent part (weight 0.75). With one counterparty both parts are the same number, so they add back to it. With two, the independent part is smaller than the sum, so the charge is less than the sum of the standalone charges.

`K_reduced = sqrt((0.5 sum_c SCVA_c)^2 + 0.75 sum_c SCVA_c^2)`, capital `0.65 K_reduced`.

**Worked example.** `cva_k-0001`: `SCVA = 157,999.44`, `K_reduced = sqrt(0.25 S^2 + 0.75 S^2) = S`, capital `0.65 x S = 102,699.64`. `cva_k-0002` adds a high-yield sovereign with `SCVA = 231,806.85`: the sum is 389,806.29 and the root sum of squares 280,532.06, and `K_reduced = 311,465.75`, between the two; capital 202,452.74.

The pitfall is adding standalone CVA charges across counterparties: that is the perfectly correlated case and overstates the charge by about 25% here (389,806.29 against 311,465.75).

### Q14.57 Counterparty A is 26% of Tier 1 and C is exactly 25%. Which is a large exposure, and which is a breach?

*Level: foundation. Evidence: spec (read; LEX10.8, LEX20.1); golden (`lex_k-0001`); computed. Source: `specifications/06-risk/leverage-large-exposures.md`*

Large is at least 10% of Tier 1; a breach is strictly above the limit, which is 25% (15% between two G-SIBs). Both are large; only A breaches.

`large = exposure >= 0.10 tier1`; `breach = exposure > limit`.

**Worked example.** Tier 1 1,000 (`lex_k-0001`): A 260 is large and breaches the 250 limit; B 100 is large (exactly 10%); C 250 is large and does not breach; D 99.99 is not large.

The pitfall is a `>=` on the limit: C would then breach, and the golden would fail in every build.

### Q14.58 In `xva.wwr.cva_hw`, why is the hazard level `a_i = ln h - b V_i` when every path has the same exposure?

*Level: advanced. Evidence: spec (read; KR-257, G-44); golden (`wwr_g-0007`); computed. Source: `specifications/stage-k-rulings-wwr.md`*

If every path is identical, every path has the same survival, so the average over paths is just one path. Matching that survival to the curve `e^(-h t)` forces each bucket's hazard to equal the flat hazard `h`, so `exp(a_i + b V_i) = h`.

Per bucket `mean_p S_p(t_(i-1)) exp(-exp(a_i + b V_i) dt_i) = e^(-h t_i)`; by induction `S(t_(i-1)) = e^(-h t_(i-1))`, so `exp(a_i + b V_i) dt_i = h dt_i`.

**Worked example.** `V = 10`, `b = 1`, `h = 0.01`: `a = ln 0.01 - 10 = -14.605170185988092`, and `CVA = 0.6 x 10 x (0.97 (1 - e^(-0.01)) + 0.94 (e^(-0.01) - e^(-0.02))) = 0.11347051247504984` (`wwr_g-0007`). The builds before KR-257 returned `a = -2.56e33` and `CVA = 0` in Python and Rust on this input.

The pitfall is testing a root finder only where it is easy: the four older goldens had `|b V| <= 2.7`, inside the window where the unbracketed solver worked in every build.

### Q14.59 Why does the KR-257 bracket `[ln h - max bV - 1, ln h - min bV + 1]` always contain the root?

*Level: advanced. Evidence: spec (read; KR-257); inferred (proof restated). Source: `specifications/stage-k-rulings-wwr.md`*

Each path's default probability in the bucket rises with `a`. At `a = ln h - b V_p` path `p` defaults with exactly the target probability `1 - e^(-h dt)`. Below the smallest such `a`, every path is under target; above the largest, every path is over. The weighted average crosses the target in between.

With `x_p = exp(a + b V_p) dt`, `f(a) = sum_p S_p (1 - e^(-x_p)) - (1 - e^(-h dt)) sum_p S_p` is increasing; `f(ln h - max bV) <= 0 <= f(ln h - min bV)`; the margin of 1 keeps the signs after rounding.

**Worked example.** Identical paths with `bV = 10`, `h = 0.01`: the bracket is `[ln 0.01 - 11, ln 0.01 - 9] = [-15.605, -13.605]`, and the root -14.605 is its midpoint. For `bV = -60` (`wwr_g-0011`) the bracket is `[54.39, 56.39]` and the root is 55.39, outside the old C++ fixed bracket `[-800, 50]`.

The pitfall is a fixed bracket chosen from the inputs one has tried: it is right until the first case outside it, and then wrong without an error.

### Q14.60 A request to `xva.wwr.cva_hw` has a path of the wrong length and `|b V| = 705`. Which error comes back, and why?

*Level: practitioner. Evidence: spec (read; HR-66, KR-257); golden (`wwr_g-0023`). Source: `specifications/stage-k-rulings-wwr.md`, [ARCHITECTURE](../../ARCHITECTURE.md#the-four-build-conformance-model-and-why-two-wrong-inputs-give-one-error)*

The structural fault is found first. The repo-wide order is schema, size limit, finite, structural (`E_INPUT`), domain (`E_DOMAIN`); KR-257's limit on `|b V|` is a domain check placed after the G-44 domain checks.

**Worked example.** `wwr_g-0023` (values `[[10, 1], [10]]`, `b = 70.5`) answers `E_INPUT`, "every path and discount_factors need one value per time"; with the lengths fixed (`wwr_g-0022`) the answer is `E_DOMAIN`, "|wwr_b * value| must be at most 700 (KR-257)".

The pitfall is computing `b V` before checking the lengths: a ragged path then gives an index error or a domain error that differs between builds.

### Q14.61 Why does a K-5 snapshot pool with `R` readers need `R + 2` slots and not `R + 1`?

*Level: advanced. Evidence: spec (read; KR-280, KR-282); inferred. Source: `specifications/12-platform/lock-free-snapshots.md`*

The writer must always find a slot that no reader holds and that is not the current snapshot, without waiting. Up to `R` slots can be announced and one is current, so one more is needed for the new snapshot: `R + 2`.

Pigeonhole: of `R + 2` slots at most `R + 1` are excluded at the writer's scan, so at least one is free; with `R + 1`, all could be excluded, and the writer would have to wait, which breaks its wait-free bound.

**Worked example.** Four readers: 6 slots. At a scan, readers hold slots 0, 1, 2 and 3 and slot 4 is current; slot 5 is free. With 5 slots the same moment leaves none.

The pitfall is counting only readers: the current slot can be announced by no reader at all and still must not be overwritten, because a new reader may load it at any moment.

### Q14.62 Why did K-5 not use a seqlock, which is simpler and allocation-free?

*Level: advanced. Evidence: spec (read; KR-281). Source: `specifications/12-platform/lock-free-snapshots.md`*

In a seqlock the reader copies the data while the writer may be writing it and retries if a counter changed. Two problems: a writer stalled half-way blocks every reader, so readers are not lock-free; and the reader's copy reads memory that is being written, which the C++ and Rust memory models and ThreadSanitizer count as a data race unless every field is atomic.

The chosen scheme writes only slots no reader has announced, so no read ever races a write; the 64-bit checksum on each snapshot lets every read test that.

**Worked example.** Local evidence (`program/stage_k_k5/K5_RACE_EVIDENCE.md`, local laptop, not the acceptance machine): C++ under ThreadSanitizer, 20,000 publishes at 1, 4 and 16 readers, 0 races and 0 torn reads in 60,042,044 reads, while both planted ordering faults were reported as races. The CI race jobs have not yet run green.

The pitfall is calling a seqlock lock-free: its writer holds the readers hostage while it writes.

### Q14.63 Encode 300 as a FAST-style stop-bit unsigned integer, and 100 as a signed one.

*Level: foundation. Evidence: spec (read; KR-276); computed. Source: `specifications/12-platform/adapters.md` section 3.4*

Split the number into 7-bit groups, most significant first, and set the high bit on the last byte only. A signed integer uses bit 6 of the first group as its sign, so a positive number whose top group has bit 6 set needs an extra zero group.

Unsigned: minimum groups, last byte `| 0x80`. Signed: two's complement in 7-bit groups, minimum groups with the sign rule.

**Worked example.** `300 = 2 x 128 + 44`: bytes `02` and `44 | 0x80 = ac`, so `02 ac`. 100 is `1100100` in binary, one group with bit 6 set, so as a signed integer it needs `00 e4`; unsigned it is `e4`.

The pitfall is accepting a non-minimal form such as `00 82` for 2 unsigned: the encoding stops being canonical and `encode(decode(b)) = b` fails; the decoder must answer `E_OVERLONG`.

### Q14.64 A multicast receiver sees packets starting at 1 (3 messages), 4 (2), 8 (1), a heartbeat at 9 and the first packet again. What does it deliver?

*Level: practitioner. Evidence: spec (read; KR-278, KR-279); computed. Source: `specifications/12-platform/adapters.md` section 3.5*

It keeps the next expected sequence number. A packet starting above it means messages were lost: record the gap and deliver. A packet that ends at or before it is a duplicate: deliver nothing. A packet that straddles it: deliver only the new part.

`s > expected`: gap `[expected, s - 1]`; `s + n <= expected`: duplicate; otherwise deliver from `expected - s`; then `expected = max(expected, s + n)`.

**Worked example.** Delivered 1 to 5 and 8; one gap `[6, 7]`; one duplicate; `expected = 9`. The heartbeat at 9 carries no messages and matches `expected`, so it records nothing.

The pitfall is treating the repeated first packet as new data because the receiver forgot what it had seen: the book then applies three orders twice.

### Q14.65 Why is the K-3 round-trip hash taken over the canonical form of records sorted by `seq`, not over the bytes the store returns?

*Level: practitioner. Evidence: spec (read; KR-270, KR-271). Source: `specifications/12-platform/adapters.md` sections 1.2 and 1.4*

Stores legitimately change representation: PostgreSQL `jsonb` reorders keys and drops white space, and a consumer may read records in another order. Those changes do not change the data. Hashing a canonical form of records sorted by `seq` makes the test sensitive to the data only.

`H(R) = SHA-256(canon(r_1) LF ... canon(r_N) LF)` over `seq`-sorted records, after a count check that every `seq` from 1 to 10,000 appears once.

**Worked example.** The planted faults show what the rule sees: dropping or duplicating one record gives `COUNT`; changing one byte of a price string, or reading a `value` back as the next binary64 up, gives `HASH`; swapping two records gives `PASS`, on purpose.

The pitfall is hashing the stored text: every PostgreSQL run would fail, and the natural fix, relaxing the check, would also let a changed price through.

### Q14.66 A soak bound is 1 MiB per hour and the process handles 23 cases a second. What is the smallest average leak per case it can see?

*Level: practitioner. Evidence: spec (read; KR-218); measured (the soak's rate); computed. Source: `specifications/12-platform/soak-eod-capacity.md`, [LEARN](../../LEARN.md#does-it-stay-the-same-size-for-hours-soak-capacity-and-an-end-of-day-rehearsal-k-6)*

The bound is per hour; a leak is per request. Divide one by the number of requests in an hour.

`leak per case > 1 MiB / (rate x 3,600 s)`.

**Worked example.** `1,048,576 / (23 x 3,600) = 12.66` bytes per case. The proposed planted leak, 1 KiB every 100 cases (10.24 bytes per case), grows about 0.81 MiB an hour and was not flagged: a recorded miss of the planted-fault rule. 1 KiB per case (about 81 MiB an hour) was caught at 171.9 MiB/h. The spec's text puts the threshold at about 1.2 bytes per case; the division gives 12.7.

The pitfall is writing a soak rule for the throughput of a fast build and applying it to a slow one: the Python soak runs the golden mix at tens of cases a second, not thousands.

### Q14.67 The end-of-day rehearsal has seven planted faults. What must each one show, and why "no earlier step fails"?

*Level: foundation. Evidence: spec (read; KR-220, KR-221); measured (evidence files). Source: `specifications/12-platform/soak-eod-capacity.md` section 3, `benchmarks/results/k6/`*

A planted fault shows that a step can fail for the reason it is meant to catch. Requiring that every earlier step passes shows the fault was caught where intended, not by an unrelated check upstream.

Steps E1 to E8 run in order and stop at the first failure; the planted faults `GAP`, `HOLDOUT`, `HASH`, `EXPLAIN`, `DOMAIN`, `LABEL` and `WIDTH` target E1 to E7 in that order.

**Worked example.** On the recorded date 2026-11-19 every step passed; in the seven planted runs the failing step was E1, E2, E3, E4, E5, E6 and E7 respectively, every earlier step passed and every later step was "not run" (read 2026-11-21 from `eod-2026-11-19-*.json`; local laptop, not the acceptance machine).

The pitfall is a planted fault that fails at E1 every time: the run then proves only that the log check works.

## Fourth pass: curve methods, snapshots and soak practice (added 2026-11-21)

Curve questions here go with the hand-written [Curves method pages](../curves/README.md#method-pages); set 3 has the curve definitions. Numbers are from goldens, recomputed by `verify/v14_stage_k.py`; the Python build agreed with each golden used when run on 2026-11-21 (measured, local laptop, not the acceptance machine).

### Q14.68 A meeting step to 4.00% takes effect on 2026-12-10. Why is the discount factor to 2026-12-10 still computed entirely at the old 4.25%?

*Level: foundation. Evidence: spec (read); golden (`steps_d-0001`); computed. Source: `specifications/02-curves/meeting-steps.md`, [Meeting steps](../curves/meeting-steps.md)*

A discount factor to a date integrates the overnight forward up to that date. A step that takes effect on 2026-12-10 governs the night that starts on 2026-12-10, which is after the discount date, so it has not yet accrued.

`D(d) = exp(-integral_0^t(d) f)`, `f = base_rate` before the first step date and the step's rate from its date on.

**Worked example.** As of 2026-11-06 (34 days before the step): `D(2026-12-10) = exp(-0.0425 x 34/365) = 0.9960489220202466`; one day later `D(2026-12-11) = exp(-(0.0425 x 34 + 0.04)/365) = 0.9959397719549326` (`steps_d-0001`). The reported overnight forward on 2026-12-10 is already 4.00%.

The pitfall is reading "takes effect on" as "applies to the discount factor of that date": the curve would be one day early at every meeting.

### Q14.69 A year-end turn factor is 0.999989041155939. What funding spread does it represent, and which discount factors does it change?

*Level: practitioner. Evidence: spec (read); golden (`steps_d-0002`); computed. Source: `specifications/02-curves/meeting-steps.md`, `curve-framework.md`*

A turn is a one-off jump: one night of dearer funding. Its factor is the extra discounting of that night, so its log divided by the night's year fraction is the extra rate.

A jump dated `d_J` multiplies `D(d)` for every `d` strictly after `d_J`.

**Worked example.** `-ln(0.999989041155939) x 365 = 0.004`: 40 bp for one night. `D(2026-12-31)` is unchanged at 0.9937592807153228; `D(2027-01-01)` falls from 0.9936503815558554 to 0.9936394922962728, and every later factor is scaled by the same 0.99998904 (`steps_d-0002`).

The pitfall is spreading the turn over the month around year end with a smooth interpolation: the forward is then wrong on thirty days instead of one.

### Q14.70 In the joint solve of `joint_f-0003`, why does the 10-year pillar of the term curve depend on the SOFR 10-year quote?

*Level: advanced. Evidence: spec (read; F-24, F-25); golden (`joint_f-0003`). Source: `specifications/02-curves/joint-solve-and-funding.md`, [Joint solve](../curves/joint-solve.md)*

The 10-year term swap is discounted on the SOFR curve. If SOFR rates rise, the swap's legs are discounted more, and the term curve must move to keep the swap at its quoted rate.

`J = -(dR/dx)^(-1) (dR/dq)`; the term curve's residuals depend on SOFR unknowns, so its rows have non-zero entries in SOFR columns; SOFR rows have zeros in term columns (block lower triangular).

**Worked example.** `d ln D_term(2036-11-12) / d SOFR-10Y = +0.11329`, against `-10.732` for its own quote T-SW10; every SOFR row has 0 in all six term columns (`joint_f-0003`).

The pitfall is hedging a term-curve position with term swaps only: the SOFR column is a real exposure that a one-curve model does not show.

### Q14.71 Why is `d ln D / d quote` for the 1-month SOFR pillar close to -0.10?

*Level: foundation. Evidence: golden (`joint_f-0003`); inferred. Source: [Joint solve](../curves/joint-solve.md)*

For a one-period OIS, the par rate is `(1/D - 1) / tau`, so `ln D` is about `-tau x rate` and its derivative in the rate is about `-tau D`, with `tau` the ACT/360 year fraction of the period.

**Worked example.** As of 2026-11-09 the pillar is 2026-12-16, 37 days: `tau = 37/360 = 0.10278`, and the golden entry is -0.10239; the small gap is the factor `D` and the period's own dates (inferred from the formula).

The pitfall is reading Jacobian entries as "bp of zero per bp of quote" when the rows are `ln D`: in `rates.curve.joint_solve` they are `ln D`, while `risk.curve.jacobian` reports zero rates.

### Q14.72 A two-year receiver has par DV01 -4,806.94 but zero DV01 -4,913.22. Why do they differ by about 2%?

*Level: practitioner. Evidence: golden (`risk_r2-0001`, `-0003`, `-0031`); computed. Source: `specifications/06-risk/par-and-key-rate.md`, [Curve risk](../curves/curve-risk.md)*

They move different things. A 1 bp move in every par quote is not a 1 bp move in every continuously compounded zero rate: the Jacobian of zeros against quotes has a diagonal near but not at 1.

`par_buckets[j] ~ sum_i key_rates_PILLAR[i] J[i][j]`.

**Worked example.** `4,913.22 / 4,806.94 = 1.0221`. The Jacobian diagonal is 0.9804 at the 1-year pillar and 0.9957 at 2 years, and rises to 1.497 at 30 years on this curve (`risk_r2-0031`). Multiplying the pillar key rates by the 2-year column gives -4,808.1269, the par bucket to within 3e-6 (`risk_r2-0001`, `-0004`).

The pitfall is comparing a par DV01 from one system with a zero DV01 from another and calling the gap a model error.

### Q14.73 Why does a triangular key-rate set put -22.19 on the 5-year key for a two-year swap?

*Level: practitioner. Evidence: golden (`risk_r2-0003`, `-0004`); spec (read); inferred (why). Source: `specifications/06-risk/par-and-key-rate.md`*

A triangular key shifts zero rates with a tent that falls to zero at the neighbouring keys. With keys at 1, 2 and 5 years, the two-year key's tent covers the swap's cash flows only up to its own date on one side, so cash flows dated a little after the 2-year key time fall partly under the 5-year tent.

Weights `w_i(t)` are 1 at `k_i`, linear to 0 at `k_(i-1)` and `k_(i+1)`, and sum to 1 at every `t`.

**Worked example.** Keys 1Y, 2Y, 5Y, 10Y, 30Y: -56.60, -4,834.42, -22.19, 0, 0, summing to the zero DV01 -4,913.22 (`risk_r2-0003`). Pillar keys put the same risk on the 2-year pillar (-4,828.70) and 1-year pillar (-110.67) (`risk_r2-0004`).

The pitfall is hedging the 5-year key with a 5-year swap: the exposure is an artefact of the key dates, and moves when the key dates move.

### Q14.74 The 2-year par quote rises from 2.5% to 2.6%. Why does the 3-year discount factor rise?

*Level: advanced. Evidence: golden (`inc_k-0001`, `inc_k-0002`); computed. Source: [Incremental update](../curves/incremental-update.md)*

In the 3-year par equation the earlier discount factors appear as an annuity that the 3-year coupon is paid on. A higher 2-year quote lowers the 2-year factor, so that annuity is smaller, and the 3-year factor that solves the equation is larger.

`P_3 = (1 - S_3 (P_1 + P_2)) / (1 + S_3)`.

**Worked example.** `P_2` falls from 0.9516977522716404 to 0.9498146237052325, so `P_3` rises from 0.9145993230349208 to 0.9146541714397676, with `S_3 = 3%` unchanged (`inc_k-0001`, `inc_k-0002`).

The pitfall is expecting a quote move to change only its own pillar: a sequential bootstrap passes it on to every later one, with a sign that depends on the curve.

### Q14.75 Two instruments with the same dates and different quotes are given to the joint solve. What comes back, and why?

*Level: practitioner. Evidence: spec (read); golden (`joint_f-0015`). Source: `specifications/02-curves/joint-solve-and-funding.md`*

Two equations in one unknown that disagree have no solution; the Jacobian `dR/dx` is singular. The operation reports that it could not converge rather than return a curve that reprices neither quote.

**Worked example.** `joint_f-0015` expects `E_NO_CONVERGENCE`; the rule is that every residual must reach 1e-13 or the solve fails.

The pitfall is a least-squares fallback that quietly averages the two quotes: the curve looks fine and reprices neither instrument.

### Q14.76 The K-5 writer publishes version 1 with shift `h = 0.005`. How is the hedge notional 1,998,033.51 obtained?

*Level: practitioner. Evidence: spec (read; KR-283); scenario file; computed. Source: `specifications/12-platform/lock-free-snapshots.md` section 3*

Choose the number of hedge zeros whose parallel delta cancels the book's.

`book_delta = fsum_i(-T_i N_i exp(-(y_i + h) T_i))`, `hedge_unit_delta = -T_H exp(-(y_H + h) T_H)`, `hedge_notional = -book_delta / hedge_unit_delta`; version `k` has shift `((7919 k mod 401) - 200) x 5e-5`.

**Worked example.** Version 1: `7919 mod 401 = 300`, so `h = 100 x 5e-5 = 0.005`. `book_delta = 12,740,024.149` (scenario `datasets/scenarios/k5_snapshot.json`); hedge zero `T_H = 10`, `y_H = 4%`: `-10 exp(-0.45) = -6.37628`; `hedge_notional = 12,740,024.149 / 6.37628 = 1,998,033.51`.

The pitfall is calling this an order: it is a recommended quantity on simulated data; no order is formed and the hedge has no goldens.

### Q14.77 Why does the K-5 snapshot store results instead of computing them when a reader asks?

*Level: practitioner. Evidence: spec (read; KR-284). Source: `specifications/12-platform/lock-free-snapshots.md` section 1*

So that every reader sees the same numbers and those numbers equal a direct call. If readers computed, two readers of one snapshot could round differently, and the snapshot could not promise exactness.

Guarantee 5: every number read through a snapshot is bit-identical to calling the same functions directly with the same inputs; the scenario file holds expected values at 10 versions to 1e-9 relative.

**Worked example.** At version 1 the stored `estimate_pnl` 67,545.44 and `bound` 458.73 are those of `risk.intraday.delta_gamma_bound` on the scenario book at `h = 0.005`.

The pitfall is putting a cache of derived values next to the snapshot and updating it separately: a reader can then see a new snapshot with old derived numbers, which is a torn read by another name.

### Q14.78 What staleness does K-5 promise, and why not a bound in microseconds?

*Level: advanced. Evidence: spec (read; guarantee 4, KR-286); inferred (example). Source: `specifications/12-platform/lock-free-snapshots.md`*

A read returns the snapshot current at the reader's validating load, so while the reader uses it, newer snapshots may be published. Staleness is counted in publishes, not time, because no timing run has been made.

**Worked example.** If the writer publishes versions 5 and 6 while a reader prices from version 4, the reader's result is two publishes stale; its next read returns 6 or later, never 3 (monotone versions per reader).

The pitfall is quoting a latency from a laptop run as a property of the design: the targets S1 to S5 are fixed and unmeasured, and the label stays "latency-aware analytics on simulated data".

### Q14.79 Why is the K-5 Python snapshot useful although it is not lock-free?

*Level: foundation. Evidence: spec (read; KR-281). Source: `specifications/12-platform/lock-free-snapshots.md` section 2*

It is the reference for the numbers. Its publish takes a lock only to refuse a second writer, and a read is one reference load of a frozen object, so its values can be compared with the three lock-free builds without any concurrency doubt about the reference itself.

**Worked example.** The 1,000 shared moves in `datasets/scenarios/k5a_intraday_moves.json` ran in all four builds with 0 bound violations and the same worst error over bound, 0.0104814 (Rust prints 0.010481), measured 2026-11-20 by the K-5 lane.

The pitfall is reporting the Python build in a list of lock-free implementations.

### Q14.80 Why does the K-6 soak read memory only when no case is in flight?

*Level: foundation. Evidence: spec (read; KR-218). Source: `specifications/12-platform/soak-eod-capacity.md` section 1*

Some golden cases are heavy, for example a large Monte Carlo case, and briefly use a lot of memory. Reading in the middle of one would look like growth. At an idle point the process holds only what it keeps between requests, which is what a leak changes.

**Worked example.** The 145-minute Python soak took 671 judged samples after a 2,037 s warm-up; the range was 3.0% of the 432.6 MiB median, under the 5% rule, while the slope, 2.32 MiB/h, missed the 1 MiB/h bound: a recorded miss with cause not found.

The pitfall is reading every 10 s without draining: the range rule then measures the golden mix, not the process.

### Q14.81 On Windows the soak judges committed private bytes, not the working set. Why?

*Level: practitioner. Evidence: spec (read; the Windows effect recalled, not measured). Source: `specifications/12-platform/soak-eod-capacity.md` section 1*

Windows trims a process's working set on its own schedule, more so at below-normal priority, so the working set measures the memory manager as well as the program. Committed private bytes are what the program has asked for and not returned.

**Worked example.** The Python soak ran at below-normal priority on a shared laptop; its judged series was committed private bytes; Linux runs judge VmRSS; Java judges heap used after a requested full collection, with RSS reported but not judged.

The pitfall is a "flat" working set that only shows Windows trimming harder as the program grows.

### Q14.82 In `docs/capacity.md`, Java runs the cheap mix at 737 cases a second and Python at 7,421. Then Java reaches 5,275 a second on a million lines. What explains both?

*Level: practitioner. Evidence: measured (`docs/capacity.md`, local laptop, not the acceptance machine); inferred. Source: `specifications/12-platform/soak-eod-capacity.md` section 2*

Cases per second is measured over wall time with start-up included. One pass of 3,806 cheap cases is short, so the JVM's start and warm-up dominate; over a million lines they are amortised and the compiled code runs faster than the interpreter.

**Worked example.** Java: `mix/cheap` 737.2 cases a second, `batch/1000000` 5,275.4; Python: 7,420.9 and 1,105.4 (2026-11-20). Peak memory: Java about 354 to 368 MiB, Python about 17 to 20 MiB.

The pitfall is ranking builds by one row: the order flips with the length of the run, and neither figure is from the acceptance machine.
