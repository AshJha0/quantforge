# A3: drift detectors, operating characteristics on simulated data

Status: **unsigned draft**. Not signed. Signing is delegated by the owner (as for Q6-01, Q6-02 and the R3 amendments) and happens only after the runner `research/a3/a3_drift_study.py` and the detectors (`research.drift.*`, `specifications/11-research/drift-detectors.md`) are merged; at signing the header records the SHA-256 of the body below the marker line, of the runner and of `python/quantforge_core/drift.py`, and the freeze commit.
- No path of seed 20261109 or 20261110 has been drawn at the date of this draft (2026-11-15). Unit tests of the runner use other seeds and at most 50 paths.
- This file is not edited after signing; a change is a new prereg.

<!-- body -->
Plan item A3 (QUANTFORGE_PLAN.md 12.10). A method test of the four detectors on simulated data; no market data and no trading signal. Label: *method test on simulated i.i.d. Gaussian data*. The R3 common rules and the template's Sharpe verdict (TEMPLATE.md section 5) do not apply; the verdict is section "Pass rules" below.

## Data (draw order is part of the prereg)

1. `rng = numpy.random.default_rng(20261109)`; `null = rng.standard_normal((2000, 1000))`; then `arl = rng.standard_normal((2000, 5000))`.
2. `rng = numpy.random.default_rng(20261110)`; `mean_break = rng.standard_normal((2000, 1000))`, then `mean_break[:, 500:] += 1.0`; `var_break = rng.standard_normal((2000, 1000))`, then `var_break[:, 500:] *= sqrt(2.0)` (variance ratio 2.0).

## Detectors and parameters (fixed; rulings J-W3-10 to J-W3-13)

- **CUSUM** two-sided, `mu0 = 0`, `sigma = 1`, `k = 0.5`, `h = 5.0`, reset after each alarm. Siegmund approximation ([SIEG85]): one-sided ARL0 about 938, two-sided about 469; ARL1 at a 1 sigma shift about 10.3.
- **Page-Hinkley** `delta = 0.5`, `lambda = 50`, direction `both`, reset after each alarm.
- **PSI** 10 bins at the reference deciles, reference `x[0:250]`, test windows `x[250:500]`, `x[500:750]`, `x[750:1000]` (non-overlapping), threshold 0.25.
- **KS** two-sample, level 0.05, windows of 250: null test `x[0:250]` against `x[250:500]`; break test `x[250:500]` against `x[500:750]`.

## Measures

- CUSUM ARL0: on each `arl` path the index of the first alarm plus 1; a path with no alarm counts as 5,000 (censored; the count of censored paths is reported). Mean over 2,000 paths, with SE `sd / sqrt(2000)`.
- Delay (CUSUM, Page-Hinkley) on `mean_break`: `d = a - 500` for the first alarm `a >= 500`; alarms before 500 are false alarms (counted, the detector having restarted); a path with no alarm at or after 500 has `d = infinity`. Median `d` and the share of paths with `d <= 40`, each with a binomial SE (median: order-statistic interval).
- PSI false alarms: share of `null` paths with an alarm in any of the three test windows. PSI detection: share of `var_break` paths whose `x[500:750]` window alarms.
- KS size: rejection share of the null test on `null`. KS power: rejection share of the break test on `var_break`.
- Every number with its SE.

## Pass rules (from plan 12.10 A3, unchanged)

1. CUSUM: ARL0 in [400, 540]; median delay at most 15 steps; at least 95% of `mean_break` paths with `d <= 40`.
2. Page-Hinkley: median delay at most 15; at least 95% with `d <= 40`.
3. PSI: false alarms at most 2% of null paths; at least 95% of variance-break paths alarm by `t = 750`.
4. KS: size in [0.035, 0.065] (3.5 SE band at 2,000 paths); power at least 95%.

Each detector passes or fails on its own rule; the study reports four verdicts. A fail is published with the same prominence.

## Prior analysis (before any draw)

- CUSUM: the Siegmund figures above predict a pass on rules 1 if the implementation is right; that is what this study checks.
- **Page-Hinkley is expected to fail rule 2 with the plan's parameters.** After a +1 shift the up-statistic grows by about `1 - delta - (xbar_t - 0) = 0.5` per step at first, less as the running mean absorbs the shift, so reaching `lambda = 50` takes about 100 steps or more, well above 15. The plan fixed these parameters; this draft keeps them and flags the expected fail to the owner before signing. Changing `lambda` (for example to 5) is an owner decision recorded as a dated note here before signing, never after a draw.
- PSI: under the null, `PSI` is roughly `chi-square(9) (1/250 + 1/250)` with mean about 0.07; `P(PSI > 0.25)` per window is about 3e-4 (approximation), so rule 3's false-alarm part is expected to pass. Detection power for variance ratio 2 with 250 per window has not been computed.
- KS: the exact test at level 0.05 with `n = m = 250` has size a little below 0.05 because `D` is discrete; expected inside the band. Power against a pure scale change (same mean, sd ratio 1.41) is not computed here and may fall below 95%: KS is weak against scale changes.

## Run

Once, by `python research/a3/a3_drift_study.py`, which refuses unless this file is signed and unchanged, the runner and `drift.py` match the hashes in the header, and `research/a3/a3_output.json` does not exist. Output `research/a3/a3_output.json` and `research/a3/RESULTS.md`.

## AI assistance

Drafted by Claude (Opus 5.5, `claude-opus-5-5`) on 2026-11-15 in a QuantForge wave 3 lane: text, parameters copied from plan 12.10 A3, prior analysis. Prompts not stored beyond the session transcript. No human has checked these claims yet. Prior knowledge: general knowledge of these detectors; the data is simulated, so no holdout question arises.
