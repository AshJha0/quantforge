# Calibration stability report

Spec version 1.0.0. Status: Specified (phase R2, plan 10 R2 and 11.5). This is a report, not a new operation. It runs existing operations through the CLI's batch mode and judges them on the metrics below. Tool: `tools/workflows/calib_stability.py`, built by infra from this spec. It holds no financial logic: it perturbs inputs with a seeded generator, sends cases, and measures differences in what comes back.

## Calibrations covered

| Id | Operation | Inputs perturbed | Judged on |
|---|---|---|---|
| C1 | `rates.ois.bootstrap` (SOFR, `LOG_LINEAR_DF`) | par quotes | pillar zero rates |
| C2 | `rates.ois.bootstrap` (SOFR, `LINEAR_ZERO`) | par quotes | pillar zero rates |
| C3 | `bond.fit.nelson_siegel` | bond prices | model prices of the input bonds, `market + residual` from the op's own `residuals`; betas reported only |
| C4 | `calib.curve.smooth` | zero rates | fitted forwards on a grid |
| C5 | `calib.curve.robust` | zero rates | fitted curve, and the outlier set |
| C6 | `vol.svi.calibrate` | implied vols, at `T = 1` | total variance on the strike grid |
| C7 | `vol.sabr.calibrate` | implied vols | vols on the strike grid; parameters reported only |

Base inputs are the golden inputs of each operation's first `ok` case in its stage suite, named in the report.

## Metrics

All perturbations use the seeded generator `core.rng` (xoshiro256**, seed 20261107, stream = calibration id), so every run and every language sees the same draws.

| # | Metric | Definition |
|---|---|---|
| S1 | Refit determinism | The same case sent twice in one batch, and again in a second process: outputs must be bit-identical within a language |
| S2 | Cross-language agreement | The four languages' outputs on the base case agree within the operation's golden tolerance |
| S3 | Noise amplification | 200 draws. Each input gets independent Gaussian noise `N(0, a^2)`, from `core.rng` standard normals (PPND16 transform) scaled by `a`. `a` is 0.1 bp for rates, 0.01 vol points (0.0001 in vol) for implied vols, and 0.001 per 100 for prices. `A = max over the output grid of sample std(output) / a`, in the units of the table below (ruling R2-A7) |
| S4 | Single-input response | Bump each input by `+a`. Report the largest output move per input, and the input with the largest response |
| S5 | Parameter stability | For C3 and C7: std of each parameter over the S3 draws, divided by its base value. Reported, never judged, because these models are poorly identified (`curve-fits.md`, `sabr.md`) |
| S6 | Discrete stability | For C5: the share of S3 draws whose outlier set equals the base set |
| S7 | Repricing under noise | Over the S3 draws, the RMS repricing error of the fitted model against the perturbed inputs. For exact-fit calibrations (C1, C2) this is a solve tolerance. For least-squares fits (C3 to C7) the perturbed inputs carry noise of size `a` that no smooth model can fit, so S7 is judged against the noise, not against zero (ruling R2-A2) |

**Units of `A` (S3).** C1, C2: bp of zero rate per bp of quote. C3: price per 100 of model price per price per 100 of input. C4, C5: bp of forward or zero per bp of input zero rate. C6: total variance per 0.0001 of vol. C7: vol points per vol point. Every input and output is converted to these units before the ratio.

**Rulings on the first run (R2-A9, R2-A10).**
- C3 (R2-A9): the tool must not evaluate the Nelson-Siegel formula itself, because tools hold no financial logic. No operation evaluates a Nelson-Siegel curve from betas, and none is added in R2. So C3 is judged on what the op returns: the model price of each input bond, `market + residual`. The zero-grid check from the first run is withdrawn, and infra reruns C3 on model prices. An evaluation operation may come with stage J's curve tools.
- C6 (R2-A10): `vol.svi.calibrate` takes total variance with no expiry, so vol noise is applied at `T = 1`: `w = (v + e)^2`, with `e ~ N(0, a^2)` and `a = 0.0001`. Accepted; the units of `A` follow.

## Thresholds (pass or fail)

| Calibration | S1 | S2 | S3 | S6 | S7 |
|---|---|---|---|---|---|
| C1, C2 | identical | golden tolerance | `A <= 3` on zero rates (a bootstrap passes noise through with little amplification) | | `<= 1e-12` in rate |
| C3 | identical | golden tolerance | `A <= 2` on model prices (a fit averages noise, so it should not amplify it) | | RMS `<= rms_0 + 1.5 a`, with `rms_0` the noise-free fit's RMS |
| C4 | identical | golden tolerance | `A <= 5` on forwards (smoothing damps noise) | | |
| C5 | identical | golden tolerance | `A <= 5` | `>= 0.95` | |
| C6 | identical | golden tolerance | `A <= 10` on total variance | | RMS `<= rms_0 + 1.5 a` (in vol) |
| C7 | identical | golden tolerance | `A <= 10` on vols inside the quoted strikes | | RMS `<= rms_0 + 1.5 a` (in vol) |

The thresholds come from what each method should do, not from a measured run, and are provisional until the first run. That run's results, and any change they force, go in the stage rulings. For a least-squares fit with `p` parameters on `n` inputs of noise `a`, the expected RMS residual from the noise is about `a sqrt((n - p)/n)`, which is below `a`. So `rms_0 + 1.5 a` fails only a fit that is worse than the noise can explain, for example a solver stopping early. A threshold failure is a finding to report and explain, not to hide. Changing a threshold needs a ruling in the stage rulings file.

## Report

The report is dated, with Markdown and a JSON twin, as in `tools/workflows/common.py`. It has one row per calibration and language: S1 to S7, pass or fail against the table, the seed, the base case id and the implementation version. It is labelled *synthetic inputs; stability of the method, not of any market*. It runs weekly in the scheduled job and before each tag.
