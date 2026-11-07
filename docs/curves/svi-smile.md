# SVI smile

<p class="note">Status: Implemented, not Validated. Validation is self-assessment until the human review at the end of the project. Data: synthetic. These are constructed inputs, not market data, and nothing is traded.</p>

Generated on 2026-11-07 from commit `95cbf11`, by Java 0.4.0 (JDK 25.0.5+8-LTS), C++ 0.4.0 (GCC 16.2.0), Python 0.4.0 (CPython 3.15.2), Rust 0.4.0 (rustc 1.99.1), on one Windows machine.

## What it is

An implied volatility smile shows how the volatility that reproduces option prices changes with strike at one expiry. SVI is a five-number formula for total variance, volatility squared times time, as a function of log-moneyness `k = ln(K/F)`. This page evaluates one SVI smile and checks whether it admits a butterfly arbitrage, meaning a negative density.

Formally: Total variance `w(k) = a + b (rho (k - m) + sqrt((k - m)^2 + sigma^2))`, implied volatility `sqrt(w / T)`. The butterfly condition is that the function `g(k)` stays non-negative. Spec: `specifications/05-volatility/smile-and-surface.md`.

## Inputs

Synthetic inputs, not market data. The input files are:

- [`examples/svi_smile.json`](../../examples/svi_smile.json)

They use the parameters of golden cases, so the same numbers are checked against the oracle elsewhere.

## Command

Build a CLI as in the [Cookbook](../../COOKBOOK.md), then from the repository root:

```bash
rust/target/release/quantforge run < examples/svi_smile.json
```

To rebuild every gallery page, with all four CLIs built:

```bash
python tools/build_gallery.py
```

Raw numbers: [`docs/curves/data/svi-smile.json`](data/svi-smile.json).

## Charts

<div class="chart"><svg viewBox="0 0 480 300" role="img" aria-label="SVI implied volatility, synthetic data" xmlns="http://www.w3.org/2000/svg" style="font:12px Segoe UI,Arial,sans-serif;fill:currentColor"><text x="54" y="15" style="font-weight:600;font-size:13px">SVI implied volatility</text><line x1="54" x2="466" y1="254.0" y2="254.0" style="stroke:var(--line)"/><text x="48" y="258.0" text-anchor="end">0.175</text><line x1="54" x2="466" y1="212.4" y2="212.4" style="stroke:var(--line)"/><text x="48" y="216.4" text-anchor="end">0.2</text><line x1="54" x2="466" y1="170.8" y2="170.8" style="stroke:var(--line)"/><text x="48" y="174.8" text-anchor="end">0.225</text><line x1="54" x2="466" y1="129.2" y2="129.2" style="stroke:var(--line)"/><text x="48" y="133.2" text-anchor="end">0.25</text><line x1="54" x2="466" y1="87.6" y2="87.6" style="stroke:var(--line)"/><text x="48" y="91.6" text-anchor="end">0.275</text><line x1="54" x2="466" y1="46.0" y2="46.0" style="stroke:var(--line)"/><text x="48" y="50.0" text-anchor="end">0.3</text><text x="54.0" y="270" text-anchor="middle">-0.75</text><text x="122.7" y="270" text-anchor="middle">-0.5</text><text x="191.3" y="270" text-anchor="middle">-0.25</text><text x="260.0" y="270" text-anchor="middle">0</text><text x="328.7" y="270" text-anchor="middle">0.25</text><text x="397.3" y="270" text-anchor="middle">0.5</text><text x="466.0" y="270" text-anchor="middle">0.75</text><text x="260.0" y="290" text-anchor="middle">Log-moneyness</text><text transform="translate(12 150.0) rotate(-90)" text-anchor="middle">Implied volatility</text><text x="466" y="290" text-anchor="end" style="font-style:italic">synthetic</text><polyline points="95.2,50.5 108.9,65.5 122.7,80.9 136.4,96.8 150.1,113.1 163.9,129.9 177.6,147.1 191.3,164.8 205.1,182.7 218.8,200.6 232.5,217.7 246.3,233.0 260.0,244.5 273.7,250.3 287.5,250.5 301.2,246.4 314.9,239.7 328.7,231.6 342.4,222.7 356.1,213.4 369.9,204.0 383.6,194.6 397.3,185.3 411.1,176.0 424.8,166.9" style="fill:none;stroke:var(--c1);stroke-width:2;stroke-linejoin:round"/></svg><p>Synthetic inputs, not market data. From the Python CLI; exact values are in the tables and data file.</p></div>

<div class="chart"><svg viewBox="0 0 480 300" role="img" aria-label="SVI total variance, synthetic data" xmlns="http://www.w3.org/2000/svg" style="font:12px Segoe UI,Arial,sans-serif;fill:currentColor"><text x="54" y="15" style="font-weight:600;font-size:13px">SVI total variance</text><line x1="54" x2="466" y1="254.0" y2="254.0" style="stroke:var(--line)"/><text x="48" y="258.0" text-anchor="end">0.04</text><line x1="54" x2="466" y1="212.4" y2="212.4" style="stroke:var(--line)"/><text x="48" y="216.4" text-anchor="end">0.06</text><line x1="54" x2="466" y1="170.8" y2="170.8" style="stroke:var(--line)"/><text x="48" y="174.8" text-anchor="end">0.08</text><line x1="54" x2="466" y1="129.2" y2="129.2" style="stroke:var(--line)"/><text x="48" y="133.2" text-anchor="end">0.1</text><line x1="54" x2="466" y1="87.6" y2="87.6" style="stroke:var(--line)"/><text x="48" y="91.6" text-anchor="end">0.12</text><line x1="54" x2="466" y1="46.0" y2="46.0" style="stroke:var(--line)"/><text x="48" y="50.0" text-anchor="end">0.14</text><text x="54.0" y="270" text-anchor="middle">-0.75</text><text x="122.7" y="270" text-anchor="middle">-0.5</text><text x="191.3" y="270" text-anchor="middle">-0.25</text><text x="260.0" y="270" text-anchor="middle">0</text><text x="328.7" y="270" text-anchor="middle">0.25</text><text x="397.3" y="270" text-anchor="middle">0.5</text><text x="466.0" y="270" text-anchor="middle">0.75</text><text x="260.0" y="290" text-anchor="middle">Log-moneyness</text><text transform="translate(12 150.0) rotate(-90)" text-anchor="middle">Total variance</text><text x="466" y="290" text-anchor="end" style="font-style:italic">synthetic</text><polyline points="95.2,61.4 108.9,77.9 122.7,94.3 136.4,110.6 150.1,126.8 163.9,142.8 177.6,158.6 191.3,174.1 205.1,189.1 218.8,203.4 232.5,216.4 246.3,227.4 260.0,235.3 273.7,239.2 287.5,239.4 301.2,236.6 314.9,232.0 328.7,226.4 342.4,220.0 356.1,213.2 369.9,206.0 383.6,198.7 397.3,191.2 411.1,183.6 424.8,175.9" style="fill:none;stroke:var(--c1);stroke-width:2;stroke-linejoin:round"/></svg><p>Synthetic inputs, not market data. From the Python CLI; exact values are in the tables and data file.</p></div>

<div class="chart"><svg viewBox="0 0 480 300" role="img" aria-label="Butterfly function g(k), synthetic data" xmlns="http://www.w3.org/2000/svg" style="font:12px Segoe UI,Arial,sans-serif;fill:currentColor"><text x="54" y="15" style="font-weight:600;font-size:13px">Butterfly function g(k)</text><line x1="54" x2="466" y1="254.0" y2="254.0" style="stroke:var(--line)"/><text x="48" y="258.0" text-anchor="end">0</text><line x1="54" x2="466" y1="184.7" y2="184.7" style="stroke:var(--line)"/><text x="48" y="188.7" text-anchor="end">0.5</text><line x1="54" x2="466" y1="115.3" y2="115.3" style="stroke:var(--line)"/><text x="48" y="119.3" text-anchor="end">1</text><line x1="54" x2="466" y1="46.0" y2="46.0" style="stroke:var(--line)"/><text x="48" y="50.0" text-anchor="end">1.5</text><text x="54.0" y="270" text-anchor="middle">-0.75</text><text x="122.7" y="270" text-anchor="middle">-0.5</text><text x="191.3" y="270" text-anchor="middle">-0.25</text><text x="260.0" y="270" text-anchor="middle">0</text><text x="328.7" y="270" text-anchor="middle">0.25</text><text x="397.3" y="270" text-anchor="middle">0.5</text><text x="466.0" y="270" text-anchor="middle">0.75</text><text x="260.0" y="290" text-anchor="middle">Log-moneyness</text><text transform="translate(12 150.0) rotate(-90)" text-anchor="middle">g</text><text x="466" y="290" text-anchor="end" style="font-style:italic">synthetic</text><polyline points="95.2,203.1 108.9,201.4 122.7,199.4 136.4,196.8 150.1,193.6 163.9,189.5 177.6,183.8 191.3,176.1 205.1,164.8 218.8,148.2 232.5,123.7 246.3,91.7 260.0,63.7 273.7,60.6 287.5,81.6 301.2,107.7 314.9,128.7 328.7,144.0 342.4,155.1 356.1,163.4 369.9,169.8 383.6,174.8 397.3,178.9 411.1,182.3 424.8,185.1" style="fill:none;stroke:var(--c1);stroke-width:2;stroke-linejoin:round"/></svg><p>Synthetic inputs, not market data. From the Python CLI; exact values are in the tables and data file.</p></div>

## Numbers

| Log-moneyness | Total variance | Implied vol | g |
|---|---|---|---|
| -0.6 | 0.1325864564823219 | 0.297306190632174 | 0.36713661487548577 |
| -0.55 | 0.1246687777357986 | 0.28829241837157704 | 0.37922116115641946 |
| -0.5 | 0.11678428381312708 | 0.27902721947643633 | 0.3939306137512249 |
| -0.45 | 0.10894270264101125 | 0.2694966946501215 | 0.4121769470396088 |
| -0.4 | 0.10115784749034662 | 0.25968936249597213 | 0.43531956289452356 |
| -0.35 | 0.0934499154664251 | 0.24959956659474272 | 0.46545073397551096 |
| -0.3 | 0.0858494329129735 | 0.23923410140553888 | 0.5058979857506058 |
| -0.25 | 0.0784042685075532 | 0.22862526618545204 | 0.5621070238421383 |
| -0.2 | 0.07119246469366644 | 0.21785693270839687 | 0.6430888045339345 |
| -0.15 | 0.06434588171701111 | 0.2071165239134903 | 0.7630808316045984 |
| -0.1 | 0.058091247254758255 | 0.19679303384479552 | 0.9395165933214249 |
| -0.05 | 0.05280353442869622 | 0.1876229098106025 | 1.170494125840285 |
| 0.0 | 0.04899929514050587 | 0.180737922861632 | 1.372275771715203 |
| 0.05 | 0.04709647024893403 | 0.17719381149640268 | 1.395015604411617 |
| 0.1 | 0.04704 | 0.17708754896942924 | 1.2431295086934995 |
| 0.15 | 0.04835931988953505 | 0.17955374291009188 | 1.0553349762303537 |
| 0.2 | 0.050556898833263954 | 0.18358812385929535 | 0.903655207373293 |
| 0.25 | 0.05329087252259035 | 0.18848673255270135 | 0.7932665186296156 |
| 0.3 | 0.05635771241824462 | 0.19383448681498797 | 0.7131405108752498 |
| 0.35 | 0.05963896550494045 | 0.199397367928032 | 0.6534076737659212 |
| 0.4 | 0.06306407571795719 | 0.20504320799603384 | 0.6074557139283969 |
| 0.45 | 0.06658942817633134 | 0.21069635050838975 | 0.5710739861074521 |
| 0.5 | 0.07018699661126476 | 0.21631303953801886 | 0.5415553284899004 |
| 0.55 | 0.07383810889881798 | 0.22186799213168473 | 0.5171108243587054 |
| 0.6 | 0.07752991584360076 | 0.22734689477184533 | 0.49652076958101377 |

Minimum g: 0.36713661487548577. Butterfly free at these points: True.

## Four-language agreement

Each CLI built these numbers on its own, from the same input files. Agreement shows only that the four agree. It does not show that they are right, which is what the oracle is for.

| Output | Values | Last value: Java | C++ | Python | Rust | Largest difference, any value |
|---|---|---|---|---|---|---|
| main: total_variance | 25 | 0.07752991584360076 | 0.07752991584360076 | 0.07752991584360076 | 0.07752991584360076 | 0 |
| main: implied_vol | 25 | 0.22734689477184533 | 0.22734689477184533 | 0.22734689477184533 | 0.22734689477184533 | 0 |
| main: g | 25 | 0.49652076958101377 | 0.49652076958101377 | 0.49652076958101377 | 0.49652076958101377 | 0 |
| main: min_g | 1 | 0.36713661487548577 | 0.36713661487548577 | 0.36713661487548577 | 0.36713661487548577 | 0 |
| main: butterfly_free | 1 | True | True | True | True | 0 |

## Oracle evidence and limits

SVI evaluation is compared with QuantLib `SviSmileSection` and with a published counterexample, a smile that looks fine and still admits arbitrage. The measured gap to QuantLib is within 1e-12 (`specifications/05-volatility/stage-c-targets.md`).

Golden cases with an `ok` result for `vol.svi.evaluate`: 2, counted from `verified_by` in `datasets/golden/stage_c/`. All four builds passed them locally, which is self-assessment.

| Verified by | Operation | Cases |
|---|---|---|
| published-counterexample, analytic | vol.svi.evaluate | 1 |
| quantlib-1.44, analytic | vol.svi.evaluate | 1 |

Limits:

- One expiry and one hand-chosen parameter set. Nothing here is fitted to quotes; the SVI fit has its own golden cases.
- Log-moneyness is the horizontal axis, because the SVI input is log-moneyness and no forward is needed.
- `butterfly_free` is a check at the grid points only, not a proof for all strikes.

Synthetic inputs, not market data.
