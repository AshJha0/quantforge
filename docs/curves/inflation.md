# Inflation curves, with seasonality

<p class="note">Status: Implemented, not Validated. Validation is self-assessment until the human review at the end of the project. Data: synthetic. These are constructed inputs, not market data, and nothing is traded.</p>

Generated on 2026-11-07 from commit `95cbf11`, by Java 0.4.0 (JDK 25.0.5+8-LTS), C++ 0.4.0 (GCC 16.2.0), Python 0.4.0 (CPython 3.15.2), Rust 0.4.0 (rustc 1.99.1), on one Windows machine.

## What it is

Forward index levels with and without the seasonal adjustment. Stage D, target v0.4.

## Runs

Synthetic inputs, not market data. The inputs are copied from a golden case's inputs, so the method is shown, not a market.

### `infl.curve.cpi`

Input: [`examples/inflation_cpi_d.json`](../../examples/inflation_cpi_d.json). Command: `quantforge batch < examples/inflation_cpi_d.json` (wrap as one line).

| Output | Python value |
|---|---|
| `cpi` | 8 values |

<div class="chart"><svg viewBox="0 0 480 300" role="img" aria-label="cpi, synthetic data" xmlns="http://www.w3.org/2000/svg" style="font:12px Segoe UI,Arial,sans-serif;fill:currentColor"><text x="54" y="15" style="font-weight:600;font-size:13px">cpi</text><line x1="54" x2="466" y1="254.0" y2="254.0" style="stroke:var(--line)"/><text x="48" y="258.0" text-anchor="end">300</text><line x1="54" x2="466" y1="219.3" y2="219.3" style="stroke:var(--line)"/><text x="48" y="223.3" text-anchor="end">350</text><line x1="54" x2="466" y1="184.7" y2="184.7" style="stroke:var(--line)"/><text x="48" y="188.7" text-anchor="end">400</text><line x1="54" x2="466" y1="150.0" y2="150.0" style="stroke:var(--line)"/><text x="48" y="154.0" text-anchor="end">450</text><line x1="54" x2="466" y1="115.3" y2="115.3" style="stroke:var(--line)"/><text x="48" y="119.3" text-anchor="end">500</text><line x1="54" x2="466" y1="80.7" y2="80.7" style="stroke:var(--line)"/><text x="48" y="84.7" text-anchor="end">550</text><line x1="54" x2="466" y1="46.0" y2="46.0" style="stroke:var(--line)"/><text x="48" y="50.0" text-anchor="end">600</text><text x="54.0" y="270" text-anchor="middle">0</text><text x="157.0" y="270" text-anchor="middle">2</text><text x="260.0" y="270" text-anchor="middle">4</text><text x="363.0" y="270" text-anchor="middle">6</text><text x="466.0" y="270" text-anchor="middle">8</text><text x="260.0" y="290" text-anchor="middle">Index</text><text transform="translate(12 150.0) rotate(-90)" text-anchor="middle">cpi</text><text x="466" y="290" text-anchor="end" style="font-style:italic">synthetic</text><polyline points="105.5,238.6 157.0,236.7 208.5,236.2 260.0,232.7 311.5,229.5 363.0,209.9 414.5,174.2 466.0,77.9" style="fill:none;stroke:var(--c1);stroke-width:2;stroke-linejoin:round"/></svg><p>cpi, Python CLI, from examples/inflation_cpi_d.json. Synthetic inputs, not market data.</p></div>

## Four-language agreement

Each CLI built these numbers on its own, from the same input file. Agreement shows only that the four agree. It does not show that they are right, which is what the oracle is for.

| Output | Values | Last value: Java | C++ | Python | Rust | Largest difference, any value |
|---|---|---|---|---|---|---|
| infl.curve.cpi: cpi | 8 | 553.9781374577557 | 553.9781374577557 | 553.9781374577557 | 553.9781374577562 | 5.68e-13 |

## Oracle evidence and limits

2 golden cases with status ok in `datasets/golden/stage_d` for `infl.curve.cpi`, by `verified_by`:

| Operation: sources | Cases |
|---|---|
| infl.curve.cpi: analytic | 2 |

Limits: one synthetic input per operation; charts plot output index, not calendar time; the stage D specs are in `specifications/`.
