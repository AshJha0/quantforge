# Recalibration triggers (stage K)

Spec version 1.1.0 (audit A response, 2026-11-19: the false-alarm rate, the noise floor and the error order; rulings KR-230, KR-232, KR-233). Version 1.0.0 status: **CONFIRMED** 2026-11-19, confirmed by the stage K coordinator lane (branch k-w1; was PROPOSED, version 0.1.0, stage K wave 1, plan 14.8 K-4). Rulings: `stage-k-rulings-w1.md` KR-6, superseded in part by KR-232 and completed by KR-233.

**Version 1.1.0 in brief.** The different-model audit (`institutional-quant-engine-plan/STAGE_K_R1_AUDIT_A.md`, KA-A4, KA-A5, KA-A9) showed that the published `false_alarm_rate`, `2 Phi(-k)`, is the rate only when sigma is known. The trigger estimates sigma from the window, and with a window of 4 changes it fires on noise 5.8% of the time at k = 3, not 0.27% (measured: 22,977 fires in 400,000 simulated paths, numpy seed 20261119; derived: Student-t with 3 degrees of freedom). From 1.1.0 `false_alarm_rate` is the rate of the trigger as used, `P(abs(T_(n-1)) > k)` (KR-232), and the old number is kept as `nominal_rate`. A window whose binary64 standard deviation is at most `2^-26 max abs(c_i)` is `E_DOMAIN` (KR-233), which catches a constant window such as [0.1, 0.1, 0.1] whatever the rounding. The text below keeps the 1.0.0 statements where they still hold and marks the rest.

**Plain idea.** Recalibrating a model on every tick wastes effort and adds noise; never recalibrating lets it drift. A trigger compares how far a monitored input has moved since the last calibration with how much it normally moves, and fires only when the move is too large to be noise at a stated level.

**Formal statement.** Given past one-day changes `c_1..c_n` (n >= 2), `sigma = sqrt(sum (c_i - c_bar)^2 / (n - 1))`. With reference `x_ref` (value at last calibration), current `x_now`, `d >= 1` days since calibration and level `k > 0`, the trigger fires iff `|x_now - x_ref| > k sigma sqrt(d)`. Under independent normal changes with that scale and a known sigma, the false-alarm rate would be `alpha_0 = 2 (1 - Phi(k))` (output `nominal_rate` from 1.1.0) [Page, "Continuous inspection schemes", *Biometrika* 41 (1954) for the control-chart idea (UNVERIFIED, not opened); the formula itself is the normal two-sided tail]. Evaluation of `alpha` (added 2026-11-19, branch k-w1-fu): `1 - Phi(k) = Phi(-k)` exactly, so every build computes `2 Phi(-k)` with a normal CDF that keeps full relative precision in the far tail. The form `erfc(k / sqrt 2)` is the same number in exact arithmetic, but rounding `k / sqrt 2` first costs about `2 y^2 eps` relative (`y = k / sqrt 2`), 1.2e-13 at k = 30 (measured against mpmath at 50 digits), over the 1e-14 tolerance; trig_k-0009 holds this. CUSUM and EWMA variants are out of wave 1.

**The rate with an estimated sigma (1.1.0, KR-232).** Plain idea: a sigma taken from a few past changes is itself noisy, and when it comes out low the threshold is low, so the trigger fires on noise more often than the normal tail says. Formal statement: if the changes are independent N(0, sigma^2), the move `x_now - x_ref` is N(0, d sigma^2) and independent of the window, and `s` is the sample standard deviation (divisor n - 1), then `(x_now - x_ref) / (s sqrt d)` is Student-t with `n - 1` degrees of freedom, so the trigger fires on noise with probability `alpha = P(abs(T_(n-1)) > k)`; that is `false_alarm_rate`. The window mean is subtracted from the changes, not from the move, so there is no `sqrt(1 + 1/n)` factor. Worked example: n = 2, k = 3: one degree of freedom, `alpha = (2/pi) atan(1/3) = 0.2048` (trig_k-0010), against `nominal_rate` 0.0027. The algorithm, which uses only arithmetic, `sqrt` and one `atan2`, is stated in KR-232; it is within 4e-12 relative of 50-digit values (KR-241) and is compared in the tolerance class `tail_probability` (1e-11 relative). Outside check: `scipy.stats.t.sf`.

**No noise scale (1.1.0, KR-233).** `sigma` is computed with exactly rounded sums (`mean = S1 / n`, then the exactly rounded sum of squared deviations, divided by n - 1, square root). If `sigma <= 2^-26 max abs(c_i)` the result is `E_DOMAIN`: below that level the computed sigma may be the rounding of a constant window (at most 3.2e-16 of the largest change), and above it the computed sigma is right to 2.2e-8 relative (derivation in KR-233).

## `calib.trigger.check`

Inputs: `changes`, `x_ref`, `x_now`, `days_since`, `k`. Outputs: `fire` (bool), `sigma`, `threshold` (`k sigma sqrt(d)`), `false_alarm_rate` (1.1.0: the Student-t rate, KR-232), `nominal_rate` (1.1.0: `2 Phi(-k)`). Errors per KR-6 and KR-233, in the order of KR-230: `changes` longer than 100,000 `E_LIMIT` (`01-core/limits.md`); a non-finite input `E_DOMAIN`; fewer than two changes `E_INPUT`; `k <= 0`, then `d < 1`, then no noise scale, `E_DOMAIN`. Sums are exactly rounded (KA-A18).

## Golden value cases (hand-derived)

Output fields compared: `fire` (boolean), `sigma` (binary64), `threshold` (binary64), `false_alarm_rate` (binary64), `nominal_rate` (binary64, from 1.1.0). Error cases compare `error.code` (string) only. The `Expected false_alarm_rate` column below is the 1.0.0 value, which is `nominal_rate` from 1.1.0; the 1.1.0 `false_alarm_rate` of each case is in the table after the error cases.

| Case | changes | x_ref | x_now | days_since | k | Expected sigma | Expected threshold | Expected fire | Expected false_alarm_rate | Why |
|---|---|---|---|---|---|---|---|---|---|---|
| trig_k-0001 | [1, -1, 1, -1] | 100 | 105 | 1 | 3 | 1.1547005383792515 (= 2/sqrt 3) | 3.4641016151377546 | true | 0.002699796063260186 | planted move |
| trig_k-0002 | [1, -1, 1, -1] | 100 | 102 | 1 | 3 | 1.1547005383792515 | 3.4641016151377546 | false | 0.002699796063260186 | noise |
| trig_k-0003 | [1, -1, 1, -1] | 100 | 105 | 4 | 3 | 1.1547005383792515 | 6.928203230275509 | false | 0.002699796063260186 | |
| trig_k-0004 | [0.5, -1.0, 1.5, -0.5, 0.0, 1.0, -1.5, 0.0] | 0 | 2.5 | 1 | 2.5 | 1.0 exactly (mean 0, sum of squares 7, / 7) | 2.5 | false | 0.012419330651552265 | equality does not fire |
| trig_k-0005 | [0.5, -1.0, 1.5, -0.5, 0.0, 1.0, -1.5, 0.0] | 0 | -2.5000001 | 1 | 2.5 | 1.0 | 2.5 | true | 0.012419330651552265 | |
| trig_k-0009 | [1, -1, 1, -1] | 100 | 105 | 1 | 30 | 1.1547005383792515 | 34.64101615137755 | false | 9.813427854296374e-198 | far tail: the stated `2 (1 - Phi(k))`, not a bare `erfc(k / sqrt 2)` (added 2026-11-19; mpmath 50 digits; not blind) |

<!-- blind:strip -->
`false_alarm_rate` by SciPy `2*norm.sf(k)` (outside check, KR-11), except trig_k-0009: SciPy 1.18.1 gives 9.813427854295816e-198, 5.7e-14 relative off, because its normal tail also rounds `k / sqrt 2` before erfc; that case has no outside check.
<!-- /blind:strip -->

| Case | changes | x_ref | x_now | days_since | k | Expected error.code |
|---|---|---|---|---|---|---|
| trig_k-0006 | [1] | 100 | 105 | 1 | 3 | E_INPUT |
| trig_k-0007 | [1, -1, 1, -1] | 100 | 105 | 1 | 0 | E_DOMAIN |
| trig_k-0008 | [1, 1, 1] | 100 | 105 | 1 | 3 | E_DOMAIN |

**`false_alarm_rate` before and after KR-232** (oracle `oracle/python/gen_stage_k_w1.py`, mpmath 50 digits, `I_x(nu/2, 1/2)` with `x = nu / (nu + k^2)`; also in `oracle/STAGE_K_AUDIT_A_CHANGES.json`). The blind re-derivation of trig_k-0001 to 0005 matched the 1.0.0 rate, which is `nominal_rate` now; the 1.1.0 rate is not blind, and its outside check is `scipy.stats.t.sf`.

| Case | n | k | 1.0.0 (now `nominal_rate`) | 1.1.0 `false_alarm_rate` |
|---|---|---|---|---|
| trig_k-0001 to 0003 | 4 | 3 | 0.002699796063260189 | 0.057668885622437306 |
| trig_k-0004, 0005 | 8 | 2.5 | 0.01241933065155227 | 0.040992218585752895 |
| trig_k-0009 | 4 | 30 | 9.813427854296374e-198 | 8.135280427163959e-05 |

New cases (1.1.0; hand and oracle, not blind): trig_k-0010 (n = 2, rate 0.20483276469913345 = `(2/pi) atan(1/3)`), 0011 (n = 3, `1 - 3 / sqrt(11)` = 0.09546596626670913), 0012 (n = 5, k = 2, d = 2), 0013 (n = 30, 0.0054991921339034066), 0014 (n = 250, 0.0029737859324150116), 0015 (k = 0.5, the complement branch), 0016 (k = 1,000, n = 8, 2.6409838375211874e-19). KR-233: trig_k-0017 [0.1] x 3, 0018 [0.2] x 6, 0019 [0, 0] and 0020 (sigma 1.41e-8, just below the floor) are `E_DOMAIN`; 0021 (sigma 1.56e-8, just above the floor) is a value case compared at 3e-8 relative, the bound KR-233 derives for it.

## Acceptance 1.1.0 (KR-232, fixed before the run; plan K-4 "fires on a planted move and not on noise at its stated level")

- Every trig_k case in four languages; `sigma`, `threshold` and `nominal_rate` to 1e-14 relative (trig_k-0021 to 3e-8), `false_alarm_rate` in class `tail_probability`.
- Simulation drawn the way the trigger is used: for n in {2, 4, 30, 250}, k = 3, d = 1, 100,000 noise paths per n, each a fresh window of n N(0, 1) changes and an independent N(0, 1) move: the fire count lies in the 99% binomial interval of `paths x false_alarm_rate`, the operation's own output. A 6-sigma planted move fires on at least 99.9% of the n = 250 paths. The 1.0.0 output fails this test at n = 2, 4 and 30: `python/tests/test_stage_k_audit_a.py::test_ka_a4_*` on the unfixed code (commit 9edc7348) counted 22,977 fires in 400,000 paths at n = 4, against a 99.9% interval of [974, 1190] around the 1.0.0 rate.

## Acceptance 1.0.0 (superseded by the 1.1.0 acceptance above; kept as it was)

- trig_k-0001..0008 in four languages; sigma and threshold to 1e-14 relative.
- Added 2026-11-19 (branch k-w1-fu, before its run): trig_k-0009 in four languages, every output at the golden's 1e-14 relative.
- Simulation, seed fixed in the oracle: 100,000 noise-only paths of N(0, 1) changes, window 250, k = 3, d = 1: observed fire rate within the 99% binomial interval of 0.0027 (the window's sigma is estimated, so the expected rate is slightly above 0.0027; the test uses the Student-t predictive rate `2 t_{249}.sf(3 / sqrt(1 + 1/250))`, computed by SciPy, as the centre). Planted move of 6 sigma: fires on at least 99.9% of paths.

## Acceptance evidence 1.0.0 (2026-11-19; the simulation passed only because it did not compare with the output: KA-A4, KA-A9)

- trig_k-0001..0008 and the `e2_k` cases: pass in all four builds.
- Simulation (key `trigger_simulation`): Python (numpy seed 20261118) 291 fires in 100,000 noise paths, Java (java.util.Random seed 20261118) 287; the 99% binomial interval of the Student-t predictive rate 0.0030306 is [259, 349] (SciPy `binom.interval`; Java computes the same interval exactly from the binomial pmf). The planted 6-sigma move fires on 100,000 of 100,000 paths in both (at least 99.9% required). Pass.

## Limits and open issues

- **Open audit findings (2026-11-19): KA-A4, KA-A5.** `false_alarm_rate` is the rate if sigma were known exactly (0.27% at `k` = 3); with sigma estimated from a window of 4 changes the trigger fires on noise 5.8% of the time. A constant window such as `[0.1, 0.1, 0.1]` gives a sigma of 1.7e-17 instead of `E_DOMAIN`. Register: `docs/known-issues.md`.
