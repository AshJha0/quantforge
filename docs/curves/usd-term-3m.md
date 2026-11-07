# USD-TERM-3M projection curve

<p class="note">Status: Implemented, not Validated. Validation is self-assessment until the human review at the end of the project. Data: synthetic. These are constructed inputs, not market data, and nothing is traded.</p>

Generated on 2026-11-07 from commit `95cbf11`, by Java 0.4.0 (JDK 25.0.5+8-LTS), C++ 0.4.0 (GCC 16.2.0), Python 0.4.0 (CPython 3.15.2), Rust 0.4.0 (rustc 1.99.1), on one Windows machine.

## What it is

Multi-curve means forecasting a rate on one curve and discounting on another. This curve forecasts a three-month term rate, while the SOFR curve discounts. The index `USD-TERM-3M` is itself synthetic: it exists to test multi-curve code, and no market index is implied.

Formally: Deposits and FRAs: model rate `(P(s)/P(e) - 1)/alpha`, with `P` the projection curve. Swaps: par rate `F/A`, with `A = sum alpha_i D(e_i)` on the fixed leg and `F = sum (P(s_j)/P(e_j) - 1) D(e_j)` on the quarterly floating leg. `D` stays fixed, and `P` is solved so that each quote reprices. Spec: `specifications/02-curves/projection-and-fra.md`.

## Inputs

As of 2026-11-06. Interpolation `LOG_LINEAR_DF`. The discount curve is the stored SOFR curve, 13 pillars. All rates are synthetic.

| Quote | Rate, % |
|---|---|
| Deposit 3M | 3.9500 |
| FRA 3x6 | 3.8500 |
| FRA 6x9 | 3.7500 |
| FRA 9x12 | 3.7000 |
| Swap 24M | 3.5500 |
| Swap 36M | 3.5000 |
| Swap 60M | 3.5500 |
| Swap 120M | 3.8000 |

## How to generate it

Input file: [`examples/projection_bootstrap.json`](../../examples/projection_bootstrap.json). Build a CLI as in the [Cookbook](../../COOKBOOK.md), then from the repository root:

```bash
rust/target/release/quantforge run < examples/projection_bootstrap.json
```

The charts then send the pillars to `rates.curve.discount` and `rates.curve.forward` on a grid of quarterly dates plus every pillar. To rebuild every page, with all four CLIs built:

```bash
python tools/build_gallery.py
```

Raw numbers: [`docs/curves/data/usd-term-3m.json`](data/usd-term-3m.json).

## Charts

Quotes are par or period rates, so they are marked for reference and need not sit on a zero or forward line.

<div class="chart"><svg viewBox="0 0 480 300" role="img" aria-label="Discount factors, synthetic data" xmlns="http://www.w3.org/2000/svg" style="font:12px Segoe UI,Arial,sans-serif;fill:currentColor"><text x="54" y="15" style="font-weight:600;font-size:13px">Discount factors</text><line x1="54" x2="466" y1="254.0" y2="254.0" style="stroke:var(--line)"/><text x="48" y="258.0" text-anchor="end">0.6</text><line x1="54" x2="466" y1="202.0" y2="202.0" style="stroke:var(--line)"/><text x="48" y="206.0" text-anchor="end">0.7</text><line x1="54" x2="466" y1="150.0" y2="150.0" style="stroke:var(--line)"/><text x="48" y="154.0" text-anchor="end">0.8</text><line x1="54" x2="466" y1="98.0" y2="98.0" style="stroke:var(--line)"/><text x="48" y="102.0" text-anchor="end">0.9</text><line x1="54" x2="466" y1="46.0" y2="46.0" style="stroke:var(--line)"/><text x="48" y="50.0" text-anchor="end">1</text><text x="54.0" y="270" text-anchor="middle">0</text><text x="136.4" y="270" text-anchor="middle">2.5</text><text x="218.8" y="270" text-anchor="middle">5</text><text x="301.2" y="270" text-anchor="middle">7.5</text><text x="383.6" y="270" text-anchor="middle">10</text><text x="466.0" y="270" text-anchor="middle">12.5</text><text x="260.0" y="290" text-anchor="middle">Years from as-of date</text><text transform="translate(12 150.0) rotate(-90)" text-anchor="middle">Discount factor</text><text x="466" y="290" text-anchor="end" style="font-style:italic">synthetic</text><line x1="54" x2="70" y1="29" y2="29" style="stroke:var(--c1);stroke-width:2"/><text x="75" y="33">Curve</text><circle cx="123.0" cy="29" r="4" style="fill:var(--c2)"/><text x="136.0" y="33">Solved pillars</text><polyline points="54.0,46.0 62.3,51.2 62.7,51.4 70.3,56.1 70.7,56.3 78.7,60.9 79.0,61.1 87.0,65.6 87.3,65.8 95.3,69.6 103.4,73.4 111.7,77.2 120.0,81.0 120.4,81.2 128.3,85.1 136.4,89.0 144.7,93.0 153.0,96.9 153.6,97.2 161.3,101.1 169.3,105.2 177.6,109.3 185.9,113.4 194.2,117.4 202.3,121.3 210.6,125.3 218.9,129.2 219.3,129.4 227.2,133.6 235.3,137.9 243.6,142.2 251.9,146.4 260.2,150.7 268.3,154.7 276.6,158.9 284.9,163.0 293.2,167.0 301.2,170.9 309.6,174.9 317.9,178.8 326.2,182.7 334.2,186.5 342.5,190.3 350.8,194.1 359.1,197.8 367.3,201.4 375.6,205.1 383.9,208.7 384.2,208.9" style="fill:none;stroke:var(--c1);stroke-width:2;stroke-linejoin:round"/><circle cx="62.7" cy="51.4" r="4" style="fill:var(--c2);stroke:var(--bg);stroke-width:1"><title>2027-02-10</title></circle><circle cx="70.7" cy="56.3" r="4" style="fill:var(--c2);stroke:var(--bg);stroke-width:1"><title>2027-05-10</title></circle><circle cx="79.0" cy="61.1" r="4" style="fill:var(--c2);stroke:var(--bg);stroke-width:1"><title>2027-08-10</title></circle><circle cx="87.3" cy="65.8" r="4" style="fill:var(--c2);stroke:var(--bg);stroke-width:1"><title>2027-11-10</title></circle><circle cx="120.4" cy="81.2" r="4" style="fill:var(--c2);stroke:var(--bg);stroke-width:1"><title>2028-11-10</title></circle><circle cx="153.6" cy="97.2" r="4" style="fill:var(--c2);stroke:var(--bg);stroke-width:1"><title>2029-11-13</title></circle><circle cx="219.3" cy="129.4" r="4" style="fill:var(--c2);stroke:var(--bg);stroke-width:1"><title>2031-11-10</title></circle><circle cx="384.2" cy="208.9" r="4" style="fill:var(--c2);stroke:var(--bg);stroke-width:1"><title>2036-11-10</title></circle></svg><p>Synthetic inputs, not market data. As of 2026-11-06. From the Python CLI; exact values are in the tables and data file.</p></div>

<div class="chart"><svg viewBox="0 0 480 300" role="img" aria-label="Zero rates, continuous, synthetic data" xmlns="http://www.w3.org/2000/svg" style="font:12px Segoe UI,Arial,sans-serif;fill:currentColor"><text x="54" y="15" style="font-weight:600;font-size:13px">Zero rates, continuous</text><line x1="54" x2="466" y1="254.0" y2="254.0" style="stroke:var(--line)"/><text x="48" y="258.0" text-anchor="end">3.4</text><line x1="54" x2="466" y1="184.7" y2="184.7" style="stroke:var(--line)"/><text x="48" y="188.7" text-anchor="end">3.6</text><line x1="54" x2="466" y1="115.3" y2="115.3" style="stroke:var(--line)"/><text x="48" y="119.3" text-anchor="end">3.8</text><line x1="54" x2="466" y1="46.0" y2="46.0" style="stroke:var(--line)"/><text x="48" y="50.0" text-anchor="end">4</text><text x="54.0" y="270" text-anchor="middle">0</text><text x="136.4" y="270" text-anchor="middle">2.5</text><text x="218.8" y="270" text-anchor="middle">5</text><text x="301.2" y="270" text-anchor="middle">7.5</text><text x="383.6" y="270" text-anchor="middle">10</text><text x="466.0" y="270" text-anchor="middle">12.5</text><text x="260.0" y="290" text-anchor="middle">Years from as-of date</text><text transform="translate(12 150.0) rotate(-90)" text-anchor="middle">Rate, %</text><text x="466" y="290" text-anchor="end" style="font-style:italic">synthetic</text><line x1="54" x2="70" y1="29" y2="29" style="stroke:var(--c1);stroke-width:2"/><text x="75" y="33">Zero rate</text><circle cx="147.8" cy="29" r="4" style="fill:var(--c2)"/><text x="160.8" y="33">Input quotes</text><polyline points="62.3,51.3 62.7,51.3 70.3,67.5 70.7,67.9 78.7,85.0 79.0,85.5 87.0,98.2 87.3,98.7 95.3,148.0 103.4,182.0 111.7,206.9 120.0,225.5 120.4,226.2 128.3,231.4 136.4,235.7 144.7,239.3 153.0,242.3 153.6,242.5 161.3,239.1 169.3,236.1 177.6,233.4 185.9,231.0 194.2,228.9 202.3,227.1 210.6,225.5 218.9,224.0 219.3,223.9 227.2,215.5 235.3,207.7 243.6,200.3 251.9,193.6 260.2,187.5 268.3,182.0 276.6,176.7 284.9,171.8 293.2,167.2 301.2,163.1 309.6,159.1 317.9,155.4 326.2,151.9 334.2,148.7 342.5,145.6 350.8,142.7 359.1,139.9 367.3,137.3 375.6,134.8 383.9,132.4 384.2,132.3" style="fill:none;stroke:var(--c1);stroke-width:2;stroke-linejoin:round"/><circle cx="62.7" cy="63.3" r="4" style="fill:var(--c2);stroke:var(--bg);stroke-width:1"><title>Deposit 3M: 3.9500%</title></circle><circle cx="70.7" cy="98.0" r="4" style="fill:var(--c2);stroke:var(--bg);stroke-width:1"><title>FRA 3x6: 3.8500%</title></circle><circle cx="79.0" cy="132.7" r="4" style="fill:var(--c2);stroke:var(--bg);stroke-width:1"><title>FRA 6x9: 3.7500%</title></circle><circle cx="87.3" cy="150.0" r="4" style="fill:var(--c2);stroke:var(--bg);stroke-width:1"><title>FRA 9x12: 3.7000%</title></circle><circle cx="120.4" cy="202.0" r="4" style="fill:var(--c2);stroke:var(--bg);stroke-width:1"><title>Swap 24M: 3.5500%</title></circle><circle cx="153.6" cy="219.3" r="4" style="fill:var(--c2);stroke:var(--bg);stroke-width:1"><title>Swap 36M: 3.5000%</title></circle><circle cx="219.3" cy="202.0" r="4" style="fill:var(--c2);stroke:var(--bg);stroke-width:1"><title>Swap 60M: 3.5500%</title></circle><circle cx="384.2" cy="115.3" r="4" style="fill:var(--c2);stroke:var(--bg);stroke-width:1"><title>Swap 120M: 3.8000%</title></circle></svg><p>Synthetic inputs, not market data. As of 2026-11-06. From the Python CLI; exact values are in the tables and data file.</p></div>

<div class="chart"><svg viewBox="0 0 480 300" role="img" aria-label="Simple forward rates, ACT_360, synthetic data" xmlns="http://www.w3.org/2000/svg" style="font:12px Segoe UI,Arial,sans-serif;fill:currentColor"><text x="54" y="15" style="font-weight:600;font-size:13px">Simple forward rates, ACT_360</text><line x1="54" x2="466" y1="254.0" y2="254.0" style="stroke:var(--line)"/><text x="48" y="258.0" text-anchor="end">3</text><line x1="54" x2="466" y1="212.4" y2="212.4" style="stroke:var(--line)"/><text x="48" y="216.4" text-anchor="end">3.2</text><line x1="54" x2="466" y1="170.8" y2="170.8" style="stroke:var(--line)"/><text x="48" y="174.8" text-anchor="end">3.4</text><line x1="54" x2="466" y1="129.2" y2="129.2" style="stroke:var(--line)"/><text x="48" y="133.2" text-anchor="end">3.6</text><line x1="54" x2="466" y1="87.6" y2="87.6" style="stroke:var(--line)"/><text x="48" y="91.6" text-anchor="end">3.8</text><line x1="54" x2="466" y1="46.0" y2="46.0" style="stroke:var(--line)"/><text x="48" y="50.0" text-anchor="end">4</text><text x="54.0" y="270" text-anchor="middle">0</text><text x="136.4" y="270" text-anchor="middle">2.5</text><text x="218.8" y="270" text-anchor="middle">5</text><text x="301.2" y="270" text-anchor="middle">7.5</text><text x="383.6" y="270" text-anchor="middle">10</text><text x="466.0" y="270" text-anchor="middle">12.5</text><text x="260.0" y="290" text-anchor="middle">Years from as-of date</text><text transform="translate(12 150.0) rotate(-90)" text-anchor="middle">Rate, %</text><text x="466" y="290" text-anchor="end" style="font-style:italic">synthetic</text><line x1="54" x2="70" y1="29" y2="29" style="stroke:var(--c1);stroke-width:2"/><text x="75" y="33">Forward between grid dates</text><circle cx="253.20000000000002" cy="29" r="4" style="fill:var(--c2)"/><text x="266.20000000000005" y="33">Input quotes</text><polyline points="54.0,56.4 62.3,56.4 62.3,60.3 62.7,60.3 62.7,77.4 70.3,77.4 70.3,80.8 70.7,80.8 70.7,98.2 78.7,98.2 78.7,101.6 79.0,101.6 79.0,108.6 87.0,108.6 87.0,111.9 87.3,111.9 87.3,237.7 95.3,237.7 95.3,237.6 103.4,237.6 103.4,237.6 111.7,237.6 111.7,237.6 120.0,237.6 120.0,240.0 120.4,240.0 120.4,190.2 128.3,190.2 128.3,190.1 136.4,190.1 136.4,190.1 144.7,190.1 144.7,190.1 153.0,190.1 153.0,192.7 153.6,192.7 153.6,143.0 161.3,143.0 161.3,142.8 169.3,142.8 169.3,142.7 177.6,142.7 177.6,142.7 185.9,142.7 185.9,142.7 194.2,142.7 194.2,142.8 202.3,142.8 202.3,142.7 210.6,142.7 210.6,142.7 218.9,142.7 218.9,145.9 219.3,145.9 219.3,50.2 227.2,50.2 227.2,50.1 235.3,50.1 235.3,50.0 243.6,50.0 243.6,50.0 251.9,50.0 251.9,50.0 260.2,50.0 260.2,50.2 268.3,50.2 268.3,50.0 276.6,50.0 276.6,50.0 284.9,50.0 284.9,50.0 293.2,50.0 293.2,50.2 301.2,50.2 301.2,50.0 309.6,50.0 309.6,50.0 317.9,50.0 317.9,50.0 326.2,50.0 326.2,50.2 334.2,50.2 334.2,50.0 342.5,50.0 342.5,50.0 350.8,50.0 350.8,50.0 359.1,50.0 359.1,50.1 367.3,50.1 367.3,50.0 375.6,50.0 375.6,50.0 383.9,50.0 383.9,54.0 384.2,54.0" style="fill:none;stroke:var(--c1);stroke-width:2;stroke-linejoin:round"/><circle cx="62.7" cy="56.4" r="4" style="fill:var(--c2);stroke:var(--bg);stroke-width:1"><title>Deposit 3M: 3.9500%</title></circle><circle cx="70.7" cy="77.2" r="4" style="fill:var(--c2);stroke:var(--bg);stroke-width:1"><title>FRA 3x6: 3.8500%</title></circle><circle cx="79.0" cy="98.0" r="4" style="fill:var(--c2);stroke:var(--bg);stroke-width:1"><title>FRA 6x9: 3.7500%</title></circle><circle cx="87.3" cy="108.4" r="4" style="fill:var(--c2);stroke:var(--bg);stroke-width:1"><title>FRA 9x12: 3.7000%</title></circle><circle cx="120.4" cy="139.6" r="4" style="fill:var(--c2);stroke:var(--bg);stroke-width:1"><title>Swap 24M: 3.5500%</title></circle><circle cx="153.6" cy="150.0" r="4" style="fill:var(--c2);stroke:var(--bg);stroke-width:1"><title>Swap 36M: 3.5000%</title></circle><circle cx="219.3" cy="139.6" r="4" style="fill:var(--c2);stroke:var(--bg);stroke-width:1"><title>Swap 60M: 3.5500%</title></circle><circle cx="384.2" cy="87.6" r="4" style="fill:var(--c2);stroke:var(--bg);stroke-width:1"><title>Swap 120M: 3.8000%</title></circle></svg><p>Synthetic inputs, not market data. As of 2026-11-06. From the Python CLI; exact values are in the tables and data file.</p></div>

### +1 bp scenario

Every quote is raised by 1 bp, the CLI rebuilds the curve, and the change in zero rate is taken at each grid date.

<div class="chart"><svg viewBox="0 0 480 300" role="img" aria-label="Zero-rate change for +1 bp on every quote, synthetic data" xmlns="http://www.w3.org/2000/svg" style="font:12px Segoe UI,Arial,sans-serif;fill:currentColor"><text x="54" y="15" style="font-weight:600;font-size:13px">Zero-rate change for +1 bp on every quote</text><line x1="54" x2="466" y1="254.0" y2="254.0" style="stroke:var(--line)"/><text x="48" y="258.0" text-anchor="end">0</text><line x1="54" x2="466" y1="212.4" y2="212.4" style="stroke:var(--line)"/><text x="48" y="216.4" text-anchor="end">0.25</text><line x1="54" x2="466" y1="170.8" y2="170.8" style="stroke:var(--line)"/><text x="48" y="174.8" text-anchor="end">0.5</text><line x1="54" x2="466" y1="129.2" y2="129.2" style="stroke:var(--line)"/><text x="48" y="133.2" text-anchor="end">0.75</text><line x1="54" x2="466" y1="87.6" y2="87.6" style="stroke:var(--line)"/><text x="48" y="91.6" text-anchor="end">1</text><line x1="54" x2="466" y1="46.0" y2="46.0" style="stroke:var(--line)"/><text x="48" y="50.0" text-anchor="end">1.25</text><text x="54.0" y="270" text-anchor="middle">0</text><text x="136.4" y="270" text-anchor="middle">2.5</text><text x="218.8" y="270" text-anchor="middle">5</text><text x="301.2" y="270" text-anchor="middle">7.5</text><text x="383.6" y="270" text-anchor="middle">10</text><text x="466.0" y="270" text-anchor="middle">12.5</text><text x="260.0" y="290" text-anchor="middle">Years from as-of date</text><text transform="translate(12 150.0) rotate(-90)" text-anchor="middle">Change, bp</text><text x="466" y="290" text-anchor="end" style="font-style:italic">synthetic</text><polyline points="62.3,87.0 62.7,87.0 70.3,86.9 70.7,86.9 78.7,86.9 79.0,86.9 87.0,86.9 87.3,86.9 95.3,88.7 103.4,89.9 111.7,90.8 120.0,91.4 120.4,91.4 128.3,91.4 136.4,91.4 144.7,91.3 153.0,91.3 153.6,91.3 161.3,91.3 169.3,91.3 177.6,91.3 185.9,91.3 194.2,91.3 202.3,91.3 210.6,91.3 218.9,91.3 219.3,91.3 227.2,91.3 235.3,91.4 243.6,91.4 251.9,91.4 260.2,91.4 268.3,91.4 276.6,91.5 284.9,91.5 293.2,91.5 301.2,91.5 309.6,91.5 317.9,91.5 326.2,91.5 334.2,91.6 342.5,91.6 350.8,91.6 359.1,91.6 367.3,91.6 375.6,91.6 383.9,91.6 384.2,91.6" style="fill:none;stroke:var(--c1);stroke-width:2;stroke-linejoin:round"/></svg><p>Synthetic inputs, not market data. As of 2026-11-06. From the Python CLI; exact values are in the tables and data file.</p></div>

## Pillars

Largest repricing error reported by the Python CLI: 2.8449465006019636e-16.

| Quote | Pillar date | Years | Quote, % | Discount factor | Zero rate, % |
|---|---|---|---|---|---|
| Deposit 3M | 2027-02-10 | 0.2630 | 3.9500 | 0.9895742049842319 | 3.984783 |
| FRA 3x6 | 2027-05-10 | 0.5068 | 3.8500 | 0.9802441863604427 | 3.936785 |
| FRA 6x9 | 2027-08-10 | 0.7589 | 3.7500 | 0.9709393509141818 | 3.886034 |
| FRA 9x12 | 2027-11-10 | 1.0110 | 3.7000 | 0.961844576089161 | 3.848070 |
| Swap 24M | 2028-11-10 | 2.0137 | 3.5500 | 0.9323166788327009 | 3.480299 |
| Swap 36M | 2029-11-13 | 3.0219 | 3.5000 | 0.9014506533357644 | 3.433249 |
| Swap 60M | 2031-11-10 | 5.0137 | 3.5500 | 0.8396105741150826 | 3.486789 |
| Swap 120M | 2036-11-10 | 10.0192 | 3.8000 | 0.6867313481800762 | 3.750928 |

## Four-language agreement

Each CLI built these numbers on its own, from the same input file. Agreement shows only that the four agree. It does not show that they are right, which is what the oracle is for.

| Output | Values | Last value: Java | C++ | Python | Rust | Largest difference, any value |
|---|---|---|---|---|---|---|
| Pillar discount factors | 8 | 0.6867313481800768 | 0.6867313481800765 | 0.6867313481800762 | 0.6867313481800703 | 6.44e-15 |
| Grid discount factors | 48 | 0.6867313481800768 | 0.6867313481800765 | 0.6867313481800762 | 0.6867313481800703 | 6.44e-15 |
| Zero rates | 48 | 0.03750927579499172 | 0.037509275794991755 | 0.0375092757949918 | 0.03750927579499266 | 9.37e-16 |
| Forward rates | 48 | 0.03961364491321895 | 0.03961364491321895 | 0.039613644913198964 | 0.03961364491321895 | 2e-14 |
| Zero rates after +1 bp | 48 | 0.03760686518871946 | 0.037606865188719474 | 0.037606865188719495 | 0.03760686518872036 | 9.02e-16 |

## Oracle evidence and limits

Pillars are compared with QuantLib `DepositRateHelper`, `FraRateHelper` and `SwapRateHelper` with exogenous discounting, and the oracle's measured gap is within 1e-10. The tenor basis operation has hand replay only. On an as-of date that is not a business day QuantLib disagrees with itself, so those dates have no outside check.

Golden cases for `rates.projection.bootstrap` with an `ok` result: 6, counted from `verified_by` in `datasets/golden/stage_b/`. All four builds passed them locally, which is self-assessment.

| Suite | Verified by | Cases |
|---|---|---|
| projection | independent-replay, quantlib-1.44 | 1 |
| projection_deep | independent-replay, quantlib-1.44 | 4 |
| rulings_b | independent-replay | 1 |

Limits:

- The discount curve in the example file is the stored SOFR curve, the same values as the golden SOFR case. It does not change in the +1 bp chart: only the projection quotes move.
- The curve stops at 10Y, its last quote.
- The first pillar is three months after spot, so the segment before it has no quote of its own.
