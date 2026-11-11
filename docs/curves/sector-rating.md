# Sector and rating curves

<p class="note">Status: Implemented, not Validated. Validation is self-assessment until the human review at the end of the project. Data: synthetic. These are constructed inputs, not market data, and nothing is traded.</p>

Generated on 2026-11-11 from commit `e150116`, by Java 0.6.0 (JDK 25.0.5+8-LTS), C++ 0.6.0 (GCC 16.2.0), Python 0.6.0 (CPython 3.15.2), Rust 0.6.0 (rustc 1.99.1), on one Windows machine.

## What it is

A sector or rating curve built as the weighted average of constituent CDS spread curves, times a rating multiplier (`scale`, 1 for the sector itself), then bootstrapped to survival probabilities with the ISDA rules (`specifications/04-pricing/credit.md`). The constituents and weights are synthetic. Stage D.

## Runs

Each run is labelled. Synthetic inputs are copied from a golden case's inputs, so they show the method, not a market. Real inputs name their source and date.

### `credit.curve.composite`

**Synthetic.** Synthetic inputs, not market data.

Input: [`examples/credit_composite_d.json`](../../examples/credit_composite_d.json). Command: `quantforge batch < examples/credit_composite_d.json` (wrap as one line).

| Output | Python value |
|---|---|
| `spreads` | 6 values |
| `pillars` | 6 values |

<div class="chart"><svg viewBox="0 0 480 300" role="img" aria-label="spreads, synthetic data" xmlns="http://www.w3.org/2000/svg" style="font:12px Segoe UI,Arial,sans-serif;fill:currentColor"><text x="54" y="15" style="font-weight:600;font-size:13px">spreads</text><line x1="54" x2="466" y1="254.0" y2="254.0" style="stroke:var(--line)"/><text x="48" y="258.0" text-anchor="end">0.0025</text><line x1="54" x2="466" y1="219.3" y2="219.3" style="stroke:var(--line)"/><text x="48" y="223.3" text-anchor="end">0.005</text><line x1="54" x2="466" y1="184.7" y2="184.7" style="stroke:var(--line)"/><text x="48" y="188.7" text-anchor="end">0.0075</text><line x1="54" x2="466" y1="150.0" y2="150.0" style="stroke:var(--line)"/><text x="48" y="154.0" text-anchor="end">0.01</text><line x1="54" x2="466" y1="115.3" y2="115.3" style="stroke:var(--line)"/><text x="48" y="119.3" text-anchor="end">0.0125</text><line x1="54" x2="466" y1="80.7" y2="80.7" style="stroke:var(--line)"/><text x="48" y="84.7" text-anchor="end">0.015</text><line x1="54" x2="466" y1="46.0" y2="46.0" style="stroke:var(--line)"/><text x="48" y="50.0" text-anchor="end">0.0175</text><text x="54.0" y="270" text-anchor="middle">0</text><text x="191.3" y="270" text-anchor="middle">2</text><text x="328.7" y="270" text-anchor="middle">4</text><text x="466.0" y="270" text-anchor="middle">6</text><text x="260.0" y="290" text-anchor="middle">Index</text><text transform="translate(12 150.0) rotate(-90)" text-anchor="middle">spreads</text><text x="466" y="290" text-anchor="end" style="font-style:italic">synthetic</text><polyline points="122.7,224.7 191.3,203.4 260.0,160.7 328.7,118.1 397.3,96.8 466.0,75.5" style="fill:none;stroke:var(--c1);stroke-width:2;stroke-linejoin:round"/></svg><p>spreads, Python CLI, from examples/credit_composite_d.json. Synthetic inputs, not market data.</p></div>

<div class="chart"><svg viewBox="0 0 480 300" role="img" aria-label="pillars: survival, synthetic data" xmlns="http://www.w3.org/2000/svg" style="font:12px Segoe UI,Arial,sans-serif;fill:currentColor"><text x="54" y="15" style="font-weight:600;font-size:13px">pillars: survival</text><line x1="54" x2="466" y1="254.0" y2="254.0" style="stroke:var(--line)"/><text x="48" y="258.0" text-anchor="end">0.75</text><line x1="54" x2="466" y1="212.4" y2="212.4" style="stroke:var(--line)"/><text x="48" y="216.4" text-anchor="end">0.8</text><line x1="54" x2="466" y1="170.8" y2="170.8" style="stroke:var(--line)"/><text x="48" y="174.8" text-anchor="end">0.85</text><line x1="54" x2="466" y1="129.2" y2="129.2" style="stroke:var(--line)"/><text x="48" y="133.2" text-anchor="end">0.9</text><line x1="54" x2="466" y1="87.6" y2="87.6" style="stroke:var(--line)"/><text x="48" y="91.6" text-anchor="end">0.95</text><line x1="54" x2="466" y1="46.0" y2="46.0" style="stroke:var(--line)"/><text x="48" y="50.0" text-anchor="end">1</text><text x="54.0" y="270" text-anchor="middle">0</text><text x="191.3" y="270" text-anchor="middle">2</text><text x="328.7" y="270" text-anchor="middle">4</text><text x="466.0" y="270" text-anchor="middle">6</text><text x="260.0" y="290" text-anchor="middle">pillars number</text><text transform="translate(12 150.0) rotate(-90)" text-anchor="middle">pillars: survival</text><text x="466" y="290" text-anchor="end" style="font-style:italic">synthetic</text><polyline points="122.7,50.0 191.3,55.6 260.0,85.8 328.7,132.1 397.3,178.0 466.0,247.1" style="fill:none;stroke:var(--c1);stroke-width:2;stroke-linejoin:round"/></svg><p>pillars: survival, Python CLI, from examples/credit_composite_d.json. Synthetic inputs, not market data.</p></div>

## Four-language agreement

Each CLI built these numbers on its own, from the same input file. Agreement shows only that the four agree. It does not show that they are right, which is what the oracle is for.

| Output | Values | Last value: Java | C++ | Python | Rust | Largest difference, any value |
|---|---|---|---|---|---|---|
| credit.curve.composite: spreads | 6 | 0.015375 | 0.015375 | 0.015375 | 0.015375 | 0 |
| credit.curve.composite: pillars | 6 | 0.7583012931616858 | 0.7583012931616859 | 0.7583012931616859 | 0.758301293161686 | 2.22e-16 |

## Oracle evidence and limits

2 golden cases with status ok in `datasets/golden/stage_d` for `credit.curve.composite`, by `verified_by`:

| Operation: sources | Cases |
|---|---|
| credit.curve.composite: independent-replay, quantlib-1.44-isda-cds-engine | 2 |

Limits: one input per operation, synthetic unless labelled real; charts plot output index, not calendar time; the stage D specs are in `specifications/`.
