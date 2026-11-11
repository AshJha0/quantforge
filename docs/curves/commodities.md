# Commodity forward curves, with seasonality and storage carry

<p class="note">Status: Implemented, not Validated. Validation is self-assessment until the human review at the end of the project. Data: synthetic. These are constructed inputs, not market data, and nothing is traded.</p>

Generated on 2026-11-07 from commit `8dddd58`, by Java 0.4.0 (JDK 25.0.5+8-LTS), C++ 0.4.0 (GCC 16.2.0), Python 0.4.0 (CPython 3.15.2), Rust 0.4.0 (rustc 1.99.1), on one Windows machine.

## What it is

Forward prices by delivery month, with seasonality and carry shown apart. Stage D.

## Runs

Each run is labelled. Synthetic inputs are copied from a golden case's inputs, so they show the method, not a market. Real inputs name their source and date.

### `cmdty.curve.forward`

**Synthetic.** Synthetic inputs, not market data.

Input: [`examples/commodity_forward_d.json`](../../examples/commodity_forward_d.json). Command: `quantforge batch < examples/commodity_forward_d.json` (wrap as one line).

| Output | Python value |
|---|---|
| `forwards` | 9 values |

<div class="chart"><svg viewBox="0 0 480 300" role="img" aria-label="forwards, synthetic data" xmlns="http://www.w3.org/2000/svg" style="font:12px Segoe UI,Arial,sans-serif;fill:currentColor"><text x="54" y="15" style="font-weight:600;font-size:13px">forwards</text><line x1="54" x2="466" y1="254.0" y2="254.0" style="stroke:var(--line)"/><text x="48" y="258.0" text-anchor="end">2.8</text><line x1="54" x2="466" y1="212.4" y2="212.4" style="stroke:var(--line)"/><text x="48" y="216.4" text-anchor="end">3</text><line x1="54" x2="466" y1="170.8" y2="170.8" style="stroke:var(--line)"/><text x="48" y="174.8" text-anchor="end">3.2</text><line x1="54" x2="466" y1="129.2" y2="129.2" style="stroke:var(--line)"/><text x="48" y="133.2" text-anchor="end">3.4</text><line x1="54" x2="466" y1="87.6" y2="87.6" style="stroke:var(--line)"/><text x="48" y="91.6" text-anchor="end">3.6</text><line x1="54" x2="466" y1="46.0" y2="46.0" style="stroke:var(--line)"/><text x="48" y="50.0" text-anchor="end">3.8</text><text x="54.0" y="270" text-anchor="middle">0</text><text x="136.4" y="270" text-anchor="middle">2</text><text x="218.8" y="270" text-anchor="middle">4</text><text x="301.2" y="270" text-anchor="middle">6</text><text x="383.6" y="270" text-anchor="middle">8</text><text x="466.0" y="270" text-anchor="middle">10</text><text x="260.0" y="290" text-anchor="middle">Index</text><text transform="translate(12 150.0) rotate(-90)" text-anchor="middle">forwards</text><text x="466" y="290" text-anchor="end" style="font-style:italic">synthetic</text><polyline points="95.2,125.0 136.4,121.9 177.6,150.3 218.8,235.3 260.0,192.4 301.2,116.8 342.4,122.8 383.6,55.7 424.8,66.8" style="fill:none;stroke:var(--c1);stroke-width:2;stroke-linejoin:round"/></svg><p>forwards, Python CLI, from examples/commodity_forward_d.json. Synthetic inputs, not market data.</p></div>
### `cmdty.storage.carry`

**Synthetic.** Synthetic inputs, not market data.

Input: [`examples/commodity_carry_d.json`](../../examples/commodity_carry_d.json). Command: `quantforge batch < examples/commodity_carry_d.json` (wrap as one line).

| Output | Python value |
|---|---|
| `convenience_yields` | 4 values |
| `carry_values` | 4 values |
| `arbitrage` | 4 values |

<div class="chart"><svg viewBox="0 0 480 300" role="img" aria-label="convenience_yields, synthetic data" xmlns="http://www.w3.org/2000/svg" style="font:12px Segoe UI,Arial,sans-serif;fill:currentColor"><text x="54" y="15" style="font-weight:600;font-size:13px">convenience_yields</text><line x1="54" x2="466" y1="254.0" y2="254.0" style="stroke:var(--line)"/><text x="48" y="258.0" text-anchor="end">-0.05</text><line x1="54" x2="466" y1="202.0" y2="202.0" style="stroke:var(--line)"/><text x="48" y="206.0" text-anchor="end">0</text><line x1="54" x2="466" y1="150.0" y2="150.0" style="stroke:var(--line)"/><text x="48" y="154.0" text-anchor="end">0.05</text><line x1="54" x2="466" y1="98.0" y2="98.0" style="stroke:var(--line)"/><text x="48" y="102.0" text-anchor="end">0.1</text><line x1="54" x2="466" y1="46.0" y2="46.0" style="stroke:var(--line)"/><text x="48" y="50.0" text-anchor="end">0.15</text><text x="54.0" y="270" text-anchor="middle">0</text><text x="157.0" y="270" text-anchor="middle">1</text><text x="260.0" y="270" text-anchor="middle">2</text><text x="363.0" y="270" text-anchor="middle">3</text><text x="466.0" y="270" text-anchor="middle">4</text><text x="260.0" y="290" text-anchor="middle">Index</text><text transform="translate(12 150.0) rotate(-90)" text-anchor="middle">convenience_yields</text><text x="466" y="290" text-anchor="end" style="font-style:italic">synthetic</text><polyline points="157.0,77.4 260.0,239.5 363.0,209.1 466.0,110.6" style="fill:none;stroke:var(--c1);stroke-width:2;stroke-linejoin:round"/></svg><p>convenience_yields, Python CLI, from examples/commodity_carry_d.json. Synthetic inputs, not market data.</p></div>

<div class="chart"><svg viewBox="0 0 480 300" role="img" aria-label="carry_values, synthetic data" xmlns="http://www.w3.org/2000/svg" style="font:12px Segoe UI,Arial,sans-serif;fill:currentColor"><text x="54" y="15" style="font-weight:600;font-size:13px">carry_values</text><line x1="54" x2="466" y1="254.0" y2="254.0" style="stroke:var(--line)"/><text x="48" y="258.0" text-anchor="end">-8</text><line x1="54" x2="466" y1="212.4" y2="212.4" style="stroke:var(--line)"/><text x="48" y="216.4" text-anchor="end">-6</text><line x1="54" x2="466" y1="170.8" y2="170.8" style="stroke:var(--line)"/><text x="48" y="174.8" text-anchor="end">-4</text><line x1="54" x2="466" y1="129.2" y2="129.2" style="stroke:var(--line)"/><text x="48" y="133.2" text-anchor="end">-2</text><line x1="54" x2="466" y1="87.6" y2="87.6" style="stroke:var(--line)"/><text x="48" y="91.6" text-anchor="end">0</text><line x1="54" x2="466" y1="46.0" y2="46.0" style="stroke:var(--line)"/><text x="48" y="50.0" text-anchor="end">2</text><text x="54.0" y="270" text-anchor="middle">0</text><text x="157.0" y="270" text-anchor="middle">1</text><text x="260.0" y="270" text-anchor="middle">2</text><text x="363.0" y="270" text-anchor="middle">3</text><text x="466.0" y="270" text-anchor="middle">4</text><text x="260.0" y="290" text-anchor="middle">Index</text><text transform="translate(12 150.0) rotate(-90)" text-anchor="middle">carry_values</text><text x="466" y="290" text-anchor="end" style="font-style:italic">synthetic</text><polyline points="157.0,133.1 260.0,73.6 363.0,82.3 466.0,222.1" style="fill:none;stroke:var(--c1);stroke-width:2;stroke-linejoin:round"/></svg><p>carry_values, Python CLI, from examples/commodity_carry_d.json. Synthetic inputs, not market data.</p></div>

## Four-language agreement

Each CLI built these numbers on its own, from the same input file. Agreement shows only that the four agree. It does not show that they are right, which is what the oracle is for.

| Output | Values | Last value: Java | C++ | Python | Rust | Largest difference, any value |
|---|---|---|---|---|---|---|
| cmdty.curve.forward: forwards | 9 | 3.7000000000000006 | 3.7000000000000006 | 3.7000000000000006 | 3.7000000000000006 | 0 |
| cmdty.storage.carry: convenience_yields | 4 | 0.087927141008683 | 0.087927141008683 | 0.087927141008683 | 0.087927141008683 | 0 |
| cmdty.storage.carry: carry_values | 4 | -6.466559878126418 | -6.466559878126418 | -6.466559878126418 | -6.466559878126418 | 0 |
| cmdty.storage.carry: arbitrage | 1 | list | list | list | list | 0 |

## Oracle evidence and limits

4 golden cases with status ok in `datasets/golden/stage_d` for `cmdty.curve.forward`, `cmdty.storage.carry`, by `verified_by`:

| Operation: sources | Cases |
|---|---|
| cmdty.curve.forward: analytic | 2 |
| cmdty.storage.carry: analytic | 2 |

Limits: one input per operation, synthetic unless labelled real; charts plot output index, not calendar time; the specs are in `specifications/`.
