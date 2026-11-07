# Equity forward with discrete dividends

<p class="note">Status: Implemented, not Validated. Validation is self-assessment until the human review at the end of the project. Data: synthetic. These are constructed inputs, not market data, and nothing is traded.</p>

Generated on 2026-11-07 from commit `a4c371f`, by Java 0.3.0 (JDK 25.0.5+8-LTS), C++ 0.3.0 (GCC 16.2.0), Python 0.3.0 (CPython 3.15.2), Rust 0.3.0 (rustc 1.99.1), on one Windows machine.

## What it is

A forward price is what you would agree today to pay for a share on a later date. Holding the share until then costs funding and earns any dividends, and a borrow cost applies if the share is shorted, so the forward is spot adjusted for all three. A dividend paid before the expiry takes value out of the share, so it lowers the forward.

Formally: The forward is spot less the present value of dividends paid on or before expiry, carried to expiry on the funding and borrow curves. The CLI returns the forward, the discount factor, the carry factor and the present value of the dividends. Spec: `specifications/05-volatility/smile-and-surface.md`.

## Inputs

Synthetic inputs, not market data. The input files are:

- [`examples/eq_forward_dividends.json`](../../examples/eq_forward_dividends.json)

They use the parameters of golden cases, so the same numbers are checked against the oracle elsewhere.

## Command

Build a CLI as in the [Cookbook](../../COOKBOOK.md), then from the repository root:

```bash
rust/target/release/quantforge run < examples/eq_forward_dividends.json
```

To rebuild every gallery page, with all four CLIs built:

```bash
python tools/build_gallery.py
```

Raw numbers: [`docs/curves/data/equity-forward.json`](data/equity-forward.json).

## Charts

<div class="chart"><svg viewBox="0 0 480 300" role="img" aria-label="Forward price against expiry, synthetic data" xmlns="http://www.w3.org/2000/svg" style="font:12px Segoe UI,Arial,sans-serif;fill:currentColor"><text x="54" y="15" style="font-weight:600;font-size:13px">Forward price against expiry</text><line x1="54" x2="466" y1="254.0" y2="254.0" style="stroke:var(--line)"/><text x="48" y="258.0" text-anchor="end">98</text><line x1="54" x2="466" y1="219.3" y2="219.3" style="stroke:var(--line)"/><text x="48" y="223.3" text-anchor="end">98.5</text><line x1="54" x2="466" y1="184.7" y2="184.7" style="stroke:var(--line)"/><text x="48" y="188.7" text-anchor="end">99</text><line x1="54" x2="466" y1="150.0" y2="150.0" style="stroke:var(--line)"/><text x="48" y="154.0" text-anchor="end">99.5</text><line x1="54" x2="466" y1="115.3" y2="115.3" style="stroke:var(--line)"/><text x="48" y="119.3" text-anchor="end">100</text><line x1="54" x2="466" y1="80.7" y2="80.7" style="stroke:var(--line)"/><text x="48" y="84.7" text-anchor="end">100.5</text><line x1="54" x2="466" y1="46.0" y2="46.0" style="stroke:var(--line)"/><text x="48" y="50.0" text-anchor="end">101</text><text x="54.0" y="270" text-anchor="middle">0</text><text x="136.4" y="270" text-anchor="middle">0.2</text><text x="218.8" y="270" text-anchor="middle">0.4</text><text x="301.2" y="270" text-anchor="middle">0.6</text><text x="383.6" y="270" text-anchor="middle">0.8</text><text x="466.0" y="270" text-anchor="middle">1</text><text x="260.0" y="290" text-anchor="middle">Years from as-of date</text><text transform="translate(12 150.0) rotate(-90)" text-anchor="middle">Forward price</text><text x="466" y="290" text-anchor="end" style="font-style:italic">synthetic</text><polyline points="54.0,115.3 87.9,98.2 122.9,80.5 157.8,166.9 189.5,151.0 224.4,237.5 258.3,220.6 293.3,203.2 327.2,186.3 362.2,168.8 397.1,151.3 431.0,134.2 466.0,185.9" style="fill:none;stroke:var(--c1);stroke-width:2;stroke-linejoin:round"/></svg><p>Synthetic inputs, not market data. From the Python CLI; exact values are in the tables and data file.</p></div>

<div class="chart"><svg viewBox="0 0 480 300" role="img" aria-label="Present value of dividends against expiry, synthetic data" xmlns="http://www.w3.org/2000/svg" style="font:12px Segoe UI,Arial,sans-serif;fill:currentColor"><text x="54" y="15" style="font-weight:600;font-size:13px">Present value of dividends against expiry</text><line x1="54" x2="466" y1="254.0" y2="254.0" style="stroke:var(--line)"/><text x="48" y="258.0" text-anchor="end">0</text><line x1="54" x2="466" y1="202.0" y2="202.0" style="stroke:var(--line)"/><text x="48" y="206.0" text-anchor="end">1</text><line x1="54" x2="466" y1="150.0" y2="150.0" style="stroke:var(--line)"/><text x="48" y="154.0" text-anchor="end">2</text><line x1="54" x2="466" y1="98.0" y2="98.0" style="stroke:var(--line)"/><text x="48" y="102.0" text-anchor="end">3</text><line x1="54" x2="466" y1="46.0" y2="46.0" style="stroke:var(--line)"/><text x="48" y="50.0" text-anchor="end">4</text><text x="54.0" y="270" text-anchor="middle">0</text><text x="136.4" y="270" text-anchor="middle">0.2</text><text x="218.8" y="270" text-anchor="middle">0.4</text><text x="301.2" y="270" text-anchor="middle">0.6</text><text x="383.6" y="270" text-anchor="middle">0.8</text><text x="466.0" y="270" text-anchor="middle">1</text><text x="260.0" y="290" text-anchor="middle">Years from as-of date</text><text transform="translate(12 150.0) rotate(-90)" text-anchor="middle">Present value</text><text x="466" y="290" text-anchor="end" style="font-style:italic">synthetic</text><polyline points="54.0,254.0 87.9,254.0 122.9,254.0 157.8,176.5 189.5,176.5 224.4,99.4 258.3,99.4 293.3,99.4 327.2,99.4 362.2,99.4 397.1,99.4 431.0,99.4 466.0,48.9" style="fill:none;stroke:var(--c1);stroke-width:2;stroke-linejoin:round"/></svg><p>Synthetic inputs, not market data. From the Python CLI; exact values are in the tables and data file.</p></div>

## Numbers

| Expiry | Forward | PV of dividends |
|---|---|---|
| 2026-12-06 | 100.24687958947796 | 0.0 |
| 2027-01-06 | 100.50262882485043 | 0.0 |
| 2027-02-06 | 99.25668623037717 | 1.491026946080903 |
| 2027-03-06 | 99.48537562527706 | 1.491026946080903 |
| 2027-04-06 | 98.23856555128404 | 2.9731345153737987 |
| 2027-05-06 | 98.48109651862609 | 2.9731345153737987 |
| 2027-06-06 | 98.7323408988644 | 2.9731345153737987 |
| 2027-07-06 | 98.97609089675748 | 2.9731345153737987 |
| 2027-08-06 | 99.22859810367167 | 2.9731345153737987 |
| 2027-09-06 | 99.48174950545115 | 2.9731345153737987 |
| 2027-10-06 | 99.72734964023572 | 2.9731345153737987 |
| 2027-11-06 | 98.98177345393107 | 3.943580048922307 |

Input file result: `forward` 98.98177345393107, `discount_factor` 0.9607894391523232, `carry_factor` 0.970445533548508, `pv_dividends` 3.943580048922307.

## Four-language agreement

Each CLI built these numbers on its own, from the same input files. Agreement shows only that the four agree. It does not show that they are right, which is what the oracle is for.

| Output | Values | Last value: Java | C++ | Python | Rust | Largest difference, any value |
|---|---|---|---|---|---|---|
| main: forward | 1 | 98.98177345393108 | 98.98177345393107 | 98.98177345393107 | 98.98177345393107 | 1.42e-14 |
| main: discount_factor | 1 | 0.9607894391523232 | 0.9607894391523232 | 0.9607894391523232 | 0.9607894391523232 | 0 |
| main: carry_factor | 1 | 0.970445533548508 | 0.970445533548508 | 0.970445533548508 | 0.970445533548508 | 0 |
| main: pv_dividends | 1 | 3.943580048922307 | 3.943580048922307 | 3.943580048922307 | 3.943580048922307 | 0 |
| series: dates | 1 | ['2026-12-06', '2027-01-06', '2027-02-06', '2027-03-06', '2027-04-06', '2027-05-06', '2027-06-06', '2027-07-06', '2027-08-06', '2027-09-06', '2027-10-06', '2027-11-06'] | ['2026-12-06', '2027-01-06', '2027-02-06', '2027-03-06', '2027-04-06', '2027-05-06', '2027-06-06', '2027-07-06', '2027-08-06', '2027-09-06', '2027-10-06', '2027-11-06'] | ['2026-12-06', '2027-01-06', '2027-02-06', '2027-03-06', '2027-04-06', '2027-05-06', '2027-06-06', '2027-07-06', '2027-08-06', '2027-09-06', '2027-10-06', '2027-11-06'] | ['2026-12-06', '2027-01-06', '2027-02-06', '2027-03-06', '2027-04-06', '2027-05-06', '2027-06-06', '2027-07-06', '2027-08-06', '2027-09-06', '2027-10-06', '2027-11-06'] | 0 |
| series: forward | 12 | 98.98177345393108 | 98.98177345393107 | 98.98177345393107 | 98.98177345393107 | 1.42e-14 |
| series: pv_dividends | 12 | 3.943580048922307 | 3.943580048922307 | 3.943580048922307 | 3.943580048922307 | 0 |

## Oracle evidence and limits

Per `specifications/05-volatility/stage-c-targets.md`, the forward is checked against a rolled route that steps between dividends one at a time, and against a plan check case. No outside library prices an equity forward here: the cases are hand and analytic.

Golden cases with an `ok` result for `eq.forward.outright`: 4, counted from `verified_by` in `datasets/golden/stage_c/`. All four builds passed them locally, which is self-assessment.

| Verified by | Operation | Cases |
|---|---|---|
| analytic-rolled | eq.forward.outright | 1 |
| hand | eq.forward.outright | 3 |

Limits:

- Each curve has one pillar, so funding and borrow rates are constant. Curve shape is not exercised.
- Three dividends with fixed cash amounts. Dividend curves and forecasting are stage D.
- The chart moves only the expiry. Spot, curves and dividends stay as in the input file.

Synthetic inputs, not market data.
