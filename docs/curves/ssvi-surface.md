# SSVI surface

<p class="note">Status: Implemented, not Validated. Validation is self-assessment until the human review at the end of the project. Data: synthetic. These are constructed inputs, not market data, and nothing is traded.</p>

Generated on 2026-11-07 from commit `a4c371f`, by Java 0.3.0 (JDK 25.0.5+8-LTS), C++ 0.3.0 (GCC 16.2.0), Python 0.3.0 (CPython 3.15.2), Rust 0.3.0 (rustc 1.99.1), on one Windows machine.

## What it is

A surface is a smile at every expiry. SSVI builds one from three shape numbers and the at-the-money total variance `theta` of each expiry, with simple conditions for freedom from calendar and butterfly arbitrage.

Formally: `w(k, theta) = theta / 2 * (1 + rho phi k + sqrt((phi k + rho)^2 + 1 - rho^2))`, with `phi` a decreasing function of `theta` set by `eta` and `gamma`. The CLI returns total variance for each `theta` and each log-moneyness, plus two flags. Spec: `specifications/05-volatility/smile-and-surface.md`.

## Inputs

Synthetic inputs, not market data. The input files are:

- [`examples/ssvi_surface.json`](../../examples/ssvi_surface.json)

They use the parameters of golden cases, so the same numbers are checked against the oracle elsewhere.

## Command

Build a CLI as in the [Cookbook](../../COOKBOOK.md), then from the repository root:

```bash
rust/target/release/quantforge run < examples/ssvi_surface.json
```

To rebuild every gallery page, with all four CLIs built:

```bash
python tools/build_gallery.py
```

Raw numbers: [`docs/curves/data/ssvi-surface.json`](data/ssvi-surface.json).

## Charts

<div class="chart"><svg viewBox="0 0 480 300" role="img" aria-label="SSVI total variance" xmlns="http://www.w3.org/2000/svg"><text x="54" y="20" style="fill:var(--ink);font-size:14px;font-weight:600">SSVI total variance</text><text x="48" y="76.0" text-anchor="end" style="fill:var(--ink);font-size:11px">theta 0.01</text><rect x="54.0" y="46.0" width="45.8" height="52.0" style="fill:var(--c1);fill-opacity:0.25;stroke:var(--bg)"><title>theta 0.01, strike -0.4: 0.0353353</title></rect><rect x="99.8" y="46.0" width="45.8" height="52.0" style="fill:var(--c1);fill-opacity:0.22;stroke:var(--bg)"><title>theta 0.01, strike -0.3: 0.0285052</title></rect><rect x="145.6" y="46.0" width="45.8" height="52.0" style="fill:var(--c1);fill-opacity:0.20;stroke:var(--bg)"><title>theta 0.01, strike -0.2: 0.021779</title></rect><rect x="191.3" y="46.0" width="45.8" height="52.0" style="fill:var(--c1);fill-opacity:0.18;stroke:var(--bg)"><title>theta 0.01, strike -0.1: 0.0153359</title></rect><rect x="237.1" y="46.0" width="45.8" height="52.0" style="fill:var(--c1);fill-opacity:0.16;stroke:var(--bg)"><title>theta 0.01, strike 0: 0.01</title></rect><rect x="282.9" y="46.0" width="45.8" height="52.0" style="fill:var(--c1);fill-opacity:0.15;stroke:var(--bg)"><title>theta 0.01, strike 0.1: 0.0084736</title></rect><rect x="328.7" y="46.0" width="45.8" height="52.0" style="fill:var(--c1);fill-opacity:0.16;stroke:var(--bg)"><title>theta 0.01, strike 0.2: 0.0101964</title></rect><rect x="374.4" y="46.0" width="45.8" height="52.0" style="fill:var(--c1);fill-opacity:0.17;stroke:var(--bg)"><title>theta 0.01, strike 0.3: 0.0127436</title></rect><rect x="420.2" y="46.0" width="45.8" height="52.0" style="fill:var(--c1);fill-opacity:0.18;stroke:var(--bg)"><title>theta 0.01, strike 0.4: 0.0155177</title></rect><text x="48" y="128.0" text-anchor="end" style="fill:var(--ink);font-size:11px">theta 0.04</text><rect x="54.0" y="98.0" width="45.8" height="52.0" style="fill:var(--c1);fill-opacity:0.44;stroke:var(--bg)"><title>theta 0.04, strike -0.4: 0.0863453</title></rect><rect x="99.8" y="98.0" width="45.8" height="52.0" style="fill:var(--c1);fill-opacity:0.39;stroke:var(--bg)"><title>theta 0.04, strike -0.3: 0.0734331</title></rect><rect x="145.6" y="98.0" width="45.8" height="52.0" style="fill:var(--c1);fill-opacity:0.34;stroke:var(--bg)"><title>theta 0.04, strike -0.2: 0.0609868</title></rect><rect x="191.3" y="98.0" width="45.8" height="52.0" style="fill:var(--c1);fill-opacity:0.30;stroke:var(--bg)"><title>theta 0.04, strike -0.1: 0.0494771</title></rect><rect x="237.1" y="98.0" width="45.8" height="52.0" style="fill:var(--c1);fill-opacity:0.27;stroke:var(--bg)"><title>theta 0.04, strike 0: 0.04</title></rect><rect x="282.9" y="98.0" width="45.8" height="52.0" style="fill:var(--c1);fill-opacity:0.25;stroke:var(--bg)"><title>theta 0.04, strike 0.1: 0.0344967</title></rect><rect x="328.7" y="98.0" width="45.8" height="52.0" style="fill:var(--c1);fill-opacity:0.24;stroke:var(--bg)"><title>theta 0.04, strike 0.2: 0.033854</title></rect><rect x="374.4" y="98.0" width="45.8" height="52.0" style="fill:var(--c1);fill-opacity:0.25;stroke:var(--bg)"><title>theta 0.04, strike 0.3: 0.0364236</title></rect><rect x="420.2" y="98.0" width="45.8" height="52.0" style="fill:var(--c1);fill-opacity:0.27;stroke:var(--bg)"><title>theta 0.04, strike 0.4: 0.0405169</title></rect><text x="48" y="180.0" text-anchor="end" style="fill:var(--ink);font-size:11px">theta 0.09</text><rect x="54.0" y="150.0" width="45.8" height="52.0" style="fill:var(--c1);fill-opacity:0.69;stroke:var(--bg)"><title>theta 0.09, strike -0.4: 0.153992</title></rect><rect x="99.8" y="150.0" width="45.8" height="52.0" style="fill:var(--c1);fill-opacity:0.62;stroke:var(--bg)"><title>theta 0.09, strike -0.3: 0.13596</title></rect><rect x="145.6" y="150.0" width="45.8" height="52.0" style="fill:var(--c1);fill-opacity:0.56;stroke:var(--bg)"><title>theta 0.09, strike -0.2: 0.118825</title></rect><rect x="191.3" y="150.0" width="45.8" height="52.0" style="fill:var(--c1);fill-opacity:0.50;stroke:var(--bg)"><title>theta 0.09, strike -0.1: 0.103175</title></rect><rect x="237.1" y="150.0" width="45.8" height="52.0" style="fill:var(--c1);fill-opacity:0.45;stroke:var(--bg)"><title>theta 0.09, strike 0: 0.09</title></rect><rect x="282.9" y="150.0" width="45.8" height="52.0" style="fill:var(--c1);fill-opacity:0.42;stroke:var(--bg)"><title>theta 0.09, strike 0.1: 0.0806559</title></rect><rect x="328.7" y="150.0" width="45.8" height="52.0" style="fill:var(--c1);fill-opacity:0.40;stroke:var(--bg)"><title>theta 0.09, strike 0.2: 0.0761234</title></rect><rect x="374.4" y="150.0" width="45.8" height="52.0" style="fill:var(--c1);fill-opacity:0.40;stroke:var(--bg)"><title>theta 0.09, strike 0.3: 0.0760408</title></rect><rect x="420.2" y="150.0" width="45.8" height="52.0" style="fill:var(--c1);fill-opacity:0.41;stroke:var(--bg)"><title>theta 0.09, strike 0.4: 0.0790985</title></rect><text x="48" y="232.0" text-anchor="end" style="fill:var(--ink);font-size:11px">theta 0.16</text><rect x="54.0" y="202.0" width="45.8" height="52.0" style="fill:var(--c1);fill-opacity:1.00;stroke:var(--bg)"><title>theta 0.16, strike -0.4: 0.238828</title></rect><rect x="99.8" y="202.0" width="45.8" height="52.0" style="fill:var(--c1);fill-opacity:0.92;stroke:var(--bg)"><title>theta 0.16, strike -0.3: 0.216602</title></rect><rect x="145.6" y="202.0" width="45.8" height="52.0" style="fill:var(--c1);fill-opacity:0.84;stroke:var(--bg)"><title>theta 0.16, strike -0.2: 0.195634</title></rect><rect x="191.3" y="202.0" width="45.8" height="52.0" style="fill:var(--c1);fill-opacity:0.77;stroke:var(--bg)"><title>theta 0.16, strike -0.1: 0.176497</title></rect><rect x="237.1" y="202.0" width="45.8" height="52.0" style="fill:var(--c1);fill-opacity:0.71;stroke:var(--bg)"><title>theta 0.16, strike 0: 0.16</title></rect><rect x="282.9" y="202.0" width="45.8" height="52.0" style="fill:var(--c1);fill-opacity:0.66;stroke:var(--bg)"><title>theta 0.16, strike 0.1: 0.147113</title></rect><rect x="328.7" y="202.0" width="45.8" height="52.0" style="fill:var(--c1);fill-opacity:0.63;stroke:var(--bg)"><title>theta 0.16, strike 0.2: 0.138645</title></rect><rect x="374.4" y="202.0" width="45.8" height="52.0" style="fill:var(--c1);fill-opacity:0.62;stroke:var(--bg)"><title>theta 0.16, strike 0.3: 0.134776</title></rect><rect x="420.2" y="202.0" width="45.8" height="52.0" style="fill:var(--c1);fill-opacity:0.62;stroke:var(--bg)"><title>theta 0.16, strike 0.4: 0.134926</title></rect><text x="76.9" y="270" text-anchor="middle" style="fill:var(--ink);font-size:11px">-0.4</text><text x="122.7" y="270" text-anchor="middle" style="fill:var(--ink);font-size:11px">-0.3</text><text x="168.4" y="270" text-anchor="middle" style="fill:var(--ink);font-size:11px">-0.2</text><text x="214.2" y="270" text-anchor="middle" style="fill:var(--ink);font-size:11px">-0.1</text><text x="260.0" y="270" text-anchor="middle" style="fill:var(--ink);font-size:11px">0</text><text x="305.8" y="270" text-anchor="middle" style="fill:var(--ink);font-size:11px">0.1</text><text x="351.6" y="270" text-anchor="middle" style="fill:var(--ink);font-size:11px">0.2</text><text x="397.3" y="270" text-anchor="middle" style="fill:var(--ink);font-size:11px">0.3</text><text x="443.1" y="270" text-anchor="middle" style="fill:var(--ink);font-size:11px">0.4</text><text x="260.0" y="292" text-anchor="middle" style="fill:var(--ink);font-size:12px">Log-moneyness (darker is higher total variance)</text></svg><p>Synthetic inputs, not market data. From the Python CLI; exact values are in the tables and data file.</p></div>

## Numbers

| theta | k=-0.4 | k=-0.3 | k=-0.2 | k=-0.1 | k=0 | k=0.1 | k=0.2 | k=0.3 | k=0.4 |
|---|---|---|---|---|---|---|---|---|---|
| 0.01 | 0.0353353 | 0.0285052 | 0.021779 | 0.0153359 | 0.01 | 0.0084736 | 0.0101964 | 0.0127436 | 0.0155177 |
| 0.04 | 0.0863453 | 0.0734331 | 0.0609868 | 0.0494771 | 0.04 | 0.0344967 | 0.033854 | 0.0364236 | 0.0405169 |
| 0.09 | 0.153992 | 0.13596 | 0.118825 | 0.103175 | 0.09 | 0.0806559 | 0.0761234 | 0.0760408 | 0.0790985 |
| 0.16 | 0.238828 | 0.216602 | 0.195634 | 0.176497 | 0.16 | 0.147113 | 0.138645 | 0.134776 | 0.134926 |

Butterfly free: True. Calendar free: True.

## Four-language agreement

Each CLI built these numbers on its own, from the same input files. Agreement shows only that the four agree. It does not show that they are right, which is what the oracle is for.

| Output | Values | Last value: Java | C++ | Python | Rust | Largest difference, any value |
|---|---|---|---|---|---|---|
| main: total_variance | 36 | 0.13492585785786426 | 0.13492585785786426 | 0.13492585785786426 | 0.13492585785786426 | 0 |
| main: butterfly_free | 1 | True | True | True | True | 0 |
| main: calendar_free | 1 | True | True | True | True | 0 |

## Oracle evidence and limits

SSVI evaluation has analytic cases only, including the check that total variance at `k = 0` equals `theta` (1e-15). No outside library evaluates SSVI here (`specifications/05-volatility/stage-c-targets.md`).

Golden cases with an `ok` result for `vol.ssvi.evaluate`: 3, counted from `verified_by` in `datasets/golden/stage_c/`. All four builds passed them locally, which is self-assessment.

| Verified by | Operation | Cases |
|---|---|---|
| analytic | vol.ssvi.evaluate | 2 |
| analytic, atm-equals-theta | vol.ssvi.evaluate | 1 |

Limits:

- The grid is total variance against `theta`, because the SSVI operation takes `theta` and not calendar time. Expiry in years is not an input.
- The flags are checks at the grid points. A wider grid could find a violation this one does not.
- One parameter set, chosen by hand.

Synthetic inputs, not market data.
