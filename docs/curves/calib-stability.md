# Calibration stability

<p class="note">Status: Implemented, not Validated. <strong>Synthetic inputs; stability of the method, not of any market.</strong> The thresholds are the spec's provisional ones, and this is the first run, so a failure is a finding about the threshold or the method, reported as it is.</p>

From `tools/workflows/calib_stability.py` (spec `specifications/03-calibration/stability.md`), run on 2026-11-07 with python, java, cpp, rust: seed 20261107, 200 noise draws per calibration from the library's own generator (`core.rng.normals`, stream = calibration number). 0 of 28 rows fail a judged metric.

## What is measured

| # | Metric |
|---|---|
| S1 | The same case twice in one batch, and again in a new process, gives bit-identical outputs |
| S2 | Each language's base outputs agree with the first language's within the golden tolerance |
| S3 | Noise amplification: the largest standard deviation of the output over the draws, divided by the noise amplitude |
| S4 | The largest output move for a one-input bump, per unit of bump |
| S5 | For the bond fit and SABR, each parameter's standard deviation over its base value (reported, never judged) |
| S6 | For the robust fit, the share of draws keeping the base outlier set |
| S7 | The worst repricing error of the fitted model against the noisy inputs |

<div class="chart"><svg viewBox="0 0 480 300" role="img" aria-label="Noise amplification A (S3), first language, synthetic data" xmlns="http://www.w3.org/2000/svg" style="font:12px Segoe UI,Arial,sans-serif;fill:currentColor"><text x="54" y="15" style="font-weight:600;font-size:13px">Noise amplification A (S3), first language</text><line x1="54" x2="466" y1="254.0" y2="254.0" style="stroke:var(--line)"/><text x="48" y="258.0" text-anchor="end">0</text><line x1="54" x2="466" y1="212.4" y2="212.4" style="stroke:var(--line)"/><text x="48" y="216.4" text-anchor="end">2</text><line x1="54" x2="466" y1="170.8" y2="170.8" style="stroke:var(--line)"/><text x="48" y="174.8" text-anchor="end">4</text><line x1="54" x2="466" y1="129.2" y2="129.2" style="stroke:var(--line)"/><text x="48" y="133.2" text-anchor="end">6</text><line x1="54" x2="466" y1="87.6" y2="87.6" style="stroke:var(--line)"/><text x="48" y="91.6" text-anchor="end">8</text><line x1="54" x2="466" y1="46.0" y2="46.0" style="stroke:var(--line)"/><text x="48" y="50.0" text-anchor="end">10</text><text x="83.4" y="270" text-anchor="middle">C1</text><text x="142.3" y="270" text-anchor="middle">C2</text><text x="201.1" y="270" text-anchor="middle">C3</text><text x="260.0" y="270" text-anchor="middle">C4</text><text x="318.9" y="270" text-anchor="middle">C5</text><text x="377.7" y="270" text-anchor="middle">C6</text><text x="436.6" y="270" text-anchor="middle">C7</text><text x="260.0" y="290" text-anchor="middle">Quote tenor</text><text transform="translate(12 150.0) rotate(-90)" text-anchor="middle">A, output per input unit</text><text x="466" y="290" text-anchor="end" style="font-style:italic">synthetic</text><rect x="54" y="24" width="14" height="10" rx="2" style="fill:var(--c1)"/><text x="75" y="33">Before hedge</text><circle cx="166.4" cy="29" r="4" style="fill:var(--c2)"/><text x="179.4" y="33">After hedge</text><rect x="74.4" y="221.8" width="18" height="32.2" style="fill:var(--c1)"><title>C1: 1.5487</title></rect><circle cx="83.4" cy="191.6" r="4" style="fill:var(--c2);stroke:var(--bg);stroke-width:1"><title>C1 after hedge: 3.0000</title></circle><rect x="133.3" y="219.9" width="18" height="34.1" style="fill:var(--c1)"><title>C2: 1.6389</title></rect><circle cx="142.3" cy="191.6" r="4" style="fill:var(--c2);stroke:var(--bg);stroke-width:1"><title>C2 after hedge: 3.0000</title></circle><rect x="192.1" y="234.8" width="18" height="19.2" style="fill:var(--c1)"><title>C3: 0.9239</title></rect><circle cx="201.1" cy="212.4" r="4" style="fill:var(--c2);stroke:var(--bg);stroke-width:1"><title>C3 after hedge: 2.0000</title></circle><rect x="251.0" y="170.4" width="18" height="83.6" style="fill:var(--c1)"><title>C4: 4.0208</title></rect><circle cx="260.0" cy="150.0" r="4" style="fill:var(--c2);stroke:var(--bg);stroke-width:1"><title>C4 after hedge: 5.0000</title></circle><rect x="309.9" y="239.6" width="18" height="14.4" style="fill:var(--c1)"><title>C5: 0.6925</title></rect><circle cx="318.9" cy="150.0" r="4" style="fill:var(--c2);stroke:var(--bg);stroke-width:1"><title>C5 after hedge: 5.0000</title></circle><rect x="368.7" y="239.2" width="18" height="14.8" style="fill:var(--c1)"><title>C6: 0.7134</title></rect><circle cx="377.7" cy="46.0" r="4" style="fill:var(--c2);stroke:var(--bg);stroke-width:1"><title>C6 after hedge: 10.0000</title></circle><rect x="427.6" y="233.5" width="18" height="20.5" style="fill:var(--c1)"><title>C7: 0.9835</title></rect><circle cx="436.6" cy="46.0" r="4" style="fill:var(--c2);stroke:var(--bg);stroke-width:1"><title>C7 after hedge: 10.0000</title></circle></svg><p>Synthetic golden inputs; seed 20261107, 200 draws. Marks are the spec&#x27;s provisional S3 thresholds.</p></div>

## Results

| Cal | Method | Language | Base case | S1 | S2 | S3 | S4 | S5 | S6 | S7 | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| C1 | OIS bootstrap, LOG_LINEAR_DF | python | `ois-0009` | same | agree | 1.55 | 1.5 |  | — | 1.13e-14 | PASS |
| C1 | OIS bootstrap, LOG_LINEAR_DF | java | `ois-0009` | same | agree | 1.55 | 1.5 |  | — | 8.70e-15 | PASS |
| C1 | OIS bootstrap, LOG_LINEAR_DF | cpp | `ois-0009` | same | agree | 1.55 | 1.5 |  | — | 5.63e-15 | PASS |
| C1 | OIS bootstrap, LOG_LINEAR_DF | rust | `ois-0009` | same | agree | 1.55 | 1.5 |  | — | 5.63e-15 | PASS |
| C2 | OIS bootstrap, LINEAR_ZERO | python | `ois-0011` | same | agree | 1.64 | 1.53 |  | — | 1.13e-14 | PASS |
| C2 | OIS bootstrap, LINEAR_ZERO | java | `ois-0011` | same | agree | 1.64 | 1.53 |  | — | 7.05e-15 | PASS |
| C2 | OIS bootstrap, LINEAR_ZERO | cpp | `ois-0011` | same | agree | 1.64 | 1.53 |  | — | 5.70e-15 | PASS |
| C2 | OIS bootstrap, LINEAR_ZERO | rust | `ois-0011` | same | agree | 1.64 | 1.53 |  | — | 5.70e-15 | PASS |
| C3 | Bond Nelson-Siegel fit | python | `bondfit_d-0001` | same | agree | 0.924 | 0.907 | 3.7e-05, 0.0022, 0.0055 | — | 7.43e-04 | PASS |
| C3 | Bond Nelson-Siegel fit | java | `bondfit_d-0001` | same | agree | 0.924 | 0.907 | 3.7e-05, 0.0022, 0.0055 | — | 7.43e-04 | PASS |
| C3 | Bond Nelson-Siegel fit | cpp | `bondfit_d-0001` | same | agree | 0.924 | 0.907 | 3.7e-05, 0.0022, 0.0055 | — | 7.43e-04 | PASS |
| C3 | Bond Nelson-Siegel fit | rust | `bondfit_d-0001` | same | agree | 0.924 | 0.907 | 3.7e-05, 0.0022, 0.0055 | — | 7.43e-04 | PASS |
| C4 | Smoothing spline | python | `fits_d-0001` | same | agree | 4.02 | 3.5 |  | — |  | PASS |
| C4 | Smoothing spline | java | `fits_d-0001` | same | agree | 4.02 | 3.5 |  | — |  | PASS |
| C4 | Smoothing spline | cpp | `fits_d-0001` | same | agree | 4.02 | 3.5 |  | — |  | PASS |
| C4 | Smoothing spline | rust | `fits_d-0001` | same | agree | 4.02 | 3.5 |  | — |  | PASS |
| C5 | Robust Nelson-Siegel | python | `fits_d-0009` | same | agree | 0.693 | 0.487 |  | 1.00 |  | PASS |
| C5 | Robust Nelson-Siegel | java | `fits_d-0009` | same | agree | 0.693 | 0.487 |  | 1.00 |  | PASS |
| C5 | Robust Nelson-Siegel | cpp | `fits_d-0009` | same | agree | 0.693 | 0.487 |  | 1.00 |  | PASS |
| C5 | Robust Nelson-Siegel | rust | `fits_d-0009` | same | agree | 0.693 | 0.487 |  | 1.00 |  | PASS |
| C6 | SVI smile | python | `smile-0034` | same | agree | 0.713 | 0.632 |  | — | 6.91e-05 | PASS |
| C6 | SVI smile | java | `smile-0034` | same | agree | 0.713 | 0.632 |  | — | 6.91e-05 | PASS |
| C6 | SVI smile | cpp | `smile-0034` | same | agree | 0.713 | 0.632 |  | — | 6.91e-05 | PASS |
| C6 | SVI smile | rust | `smile-0034` | same | agree | 0.713 | 0.632 |  | — | 6.91e-05 | PASS |
| C7 | SABR smile | python | `sabr-0019` | same | agree | 0.983 | 0.847 | 0.00026, 0.0018, 0.0015 | — | 7.64e-05 | PASS |
| C7 | SABR smile | java | `sabr-0019` | same | agree | 0.983 | 0.847 | 0.00026, 0.0018, 0.0015 | — | 7.64e-05 | PASS |
| C7 | SABR smile | cpp | `sabr-0019` | same | agree | 0.983 | 0.847 | 0.00026, 0.0018, 0.0015 | — | 7.64e-05 | PASS |
| C7 | SABR smile | rust | `sabr-0019` | same | agree | 0.983 | 0.847 | 0.00026, 0.0018, 0.0015 | — | 7.64e-05 | PASS |

## Thresholds (provisional)

| Cal | Method | S3 at most | S6 at least | S7 at most |
|---|---|---|---|---|
| C1 | OIS bootstrap, LOG_LINEAR_DF | 3 |  | 1e-12 |
| C2 | OIS bootstrap, LINEAR_ZERO | 3 |  | 1e-12 |
| C3 | Bond Nelson-Siegel fit | 2 |  | rms_0 + 1.5a |
| C4 | Smoothing spline | 5 |  |  |
| C5 | Robust Nelson-Siegel | 5 | 0.95 |  |
| C6 | SVI smile | 10 |  | rms_0 + 1.5a (vol) |
| C7 | SABR smile | 10 |  | rms_0 + 1.5a (vol) |

## Reading the run

- **Rulings applied (`specifications/r2-rulings.md`).** R2-A7: Gaussian noise `N(0, a^2)`. The amplitudes are 0.1 bp for rates, 0.0001 for vol and 0.001 per 100 for prices, and A is in the spec's units: bp per bp for C1, C2, C4 and C5; price per price for C3 (model prices of the input bonds, R2-A9); total variance per 0.0001 of vol for C6; vol per vol for C7. R2-A2: S7 for the least-squares fits (C3, C6, C7) is the pooled RMS repricing error, which must be at most `rms_0 + 1.5 a`, where `rms_0` is the noise-free fit's RMS. C1 and C2 keep a 1e-12 solve tolerance.
- **C6 noise on vol.** SVI calibration takes total variance and no expiry, so the noise goes on `sqrt(total variance)`, which is vol at T = 1. That reading is infra's and is stated here.
- **C3 (ruling R2-A9).** C3 is judged on the op's own outputs, the model prices of the input bonds (market plus residual), in price per price, with A at most 2. No formula is evaluated in the tool. C3 was rerun in all four languages after the ruling; the other calibrations are from the full run.
- **An earlier run under the original thresholds** failed S7 on C3, C6 and C7. That is what led to ruling R2-A2.

## Limits

- Golden inputs only, so this is the stability of the method on clean, synthetic cases. Market-data stability is the daily key-rate explain job's calibration section.
- One seed. Other draws would move the numbers slightly; the thresholds carry the margin.
