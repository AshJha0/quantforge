# Recalibration triggers (stage K)

Spec version 1.0.0. Status: **CONFIRMED** 2026-11-19, confirmed by the stage K coordinator lane (branch k-w1; was PROPOSED, version 0.1.0, stage K wave 1, plan 14.8 K-4). Rulings: `stage-k-rulings-w1.md` KR-6.

**Plain idea.** Recalibrating a model on every tick wastes effort and adds noise; never recalibrating lets it drift. A trigger compares how far a monitored input has moved since the last calibration with how much it normally moves, and fires only when the move is too large to be noise at a stated level.

**Formal statement.** Given past one-day changes `c_1..c_n` (n >= 2), `sigma = sqrt(sum (c_i - c_bar)^2 / (n - 1))`. With reference `x_ref` (value at last calibration), current `x_now`, `d >= 1` days since calibration and level `k > 0`, the trigger fires iff `|x_now - x_ref| > k sigma sqrt(d)`. Under independent normal changes with that scale, the false-alarm rate is `alpha = 2 (1 - Phi(k))` [Page, "Continuous inspection schemes", *Biometrika* 41 (1954) for the control-chart idea (UNVERIFIED, not opened); the formula itself is the normal two-sided tail]. Evaluation of `alpha` (added 2026-11-19, branch k-w1-fu): `1 - Phi(k) = Phi(-k)` exactly, so every build computes `2 Phi(-k)` with a normal CDF that keeps full relative precision in the far tail. The form `erfc(k / sqrt 2)` is the same number in exact arithmetic, but rounding `k / sqrt 2` first costs about `2 y^2 eps` relative (`y = k / sqrt 2`), 1.2e-13 at k = 30 (measured against mpmath at 50 digits), over the 1e-14 tolerance; trig_k-0009 holds this. CUSUM and EWMA variants are out of wave 1.

## `calib.trigger.check`

Inputs: `changes`, `x_ref`, `x_now`, `days_since`, `k`. Outputs: `fire` (bool), `sigma`, `threshold` (`k sigma sqrt(d)`), `false_alarm_rate`. Errors per KR-6; `changes` longer than 100,000 is `E_LIMIT`.

## Golden value cases (hand-derived)

Output fields compared: `fire` (boolean), `sigma` (binary64), `threshold` (binary64), `false_alarm_rate` (binary64). Error cases compare `error.code` (string) only.

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

## Acceptance (fixed before any run; plan K-4 "fires on a planted move and not on noise at its stated level")

- trig_k-0001..0008 in four languages; sigma and threshold to 1e-14 relative.
- Added 2026-11-19 (branch k-w1-fu, before its run): trig_k-0009 in four languages, every output at the golden's 1e-14 relative.
- Simulation, seed fixed in the oracle: 100,000 noise-only paths of N(0, 1) changes, window 250, k = 3, d = 1: observed fire rate within the 99% binomial interval of 0.0027 (the window's sigma is estimated, so the expected rate is slightly above 0.0027; the test uses the Student-t predictive rate `2 t_{249}.sf(3 / sqrt(1 + 1/250))`, computed by SciPy, as the centre). Planted move of 6 sigma: fires on at least 99.9% of paths.

## Acceptance evidence (2026-11-19)

- trig_k-0001..0008 and the `e2_k` cases: pass in all four builds.
- Simulation (key `trigger_simulation`): Python (numpy seed 20261118) 291 fires in 100,000 noise paths, Java (java.util.Random seed 20261118) 287; the 99% binomial interval of the Student-t predictive rate 0.0030306 is [259, 349] (SciPy `binom.interval`; Java computes the same interval exactly from the binomial pmf). The planted 6-sigma move fires on 100,000 of 100,000 paths in both (at least 99.9% required). Pass.

## Limits and open issues

- **Open audit findings (2026-11-19): KA-A4, KA-A5.** `false_alarm_rate` is the rate if sigma were known exactly (0.27% at `k` = 3); with sigma estimated from a window of 4 changes the trigger fires on noise 5.8% of the time. A constant window such as `[0.1, 0.1, 0.1]` gives a sigma of 1.7e-17 instead of `E_DOMAIN`. Register: `docs/known-issues.md`.
