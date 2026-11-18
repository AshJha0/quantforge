# Liquidity cost curve

<p class="note">Data: synthetic. These are constructed inputs, not market data, and nothing is traded.</p>

Generated on 2026-11-15 from commit `cb525c5a`, by Java 0.8.3 (JDK 25.0.5+8-LTS), C++ 0.8.3 (GCC 16.2.0), Python 0.8.3 (CPython 3.15.2), Rust 0.8.3 (rustc 1.99.1), on one Windows machine.

## What it is

Cost per unit of liquidating `Q` units evenly over `h` days: half spread, square-root impact `Y sigma (Q/(V h))^delta` and timing risk `z sigma sqrt(h/3)`, with the closed-form cost-minimising horizon per size (`specifications/10-execution/liquidity-curve.md`, rulings J-C-6 to J-C-8). Stage H reuses it: at one day and `delta = 1/2` the impact equals the draft `exec.impact.sqrt`. Assumed parameters, not a calibration. The tables give the impact and total-cost matrices (row per size, column per horizon); the chart shows timing risk by horizon, and the optimal horizon and minimum cost by size. Stage J.

## Runs

Each run is labelled. Synthetic inputs are copied from a golden case's inputs, so they show the method, not a market. Real inputs name their source and date.

### `liq.curve.cost`

**Synthetic.** Synthetic inputs, not market data.

Input: [`examples/liq_curve_cost_j.json`](../../examples/liq_curve_cost_j.json). Command: `quantforge batch < examples/liq_curve_cost_j.json` (wrap as one line).

| Output | Python value |
|---|---|
| `spread_cost` | `0.0005` |
| `impact` | 4 values |
| `timing_risk` | 10 values |
| `total_cost` | 4 values |
| `optimal_horizon` | 4 values |
| `min_cost` | 4 values |

<div class="chart"><svg viewBox="0 0 480 300" role="img" aria-label="timing_risk, synthetic data" xmlns="http://www.w3.org/2000/svg" style="font:12px Segoe UI,Arial,sans-serif;fill:currentColor"><text x="54" y="15" style="font-weight:600;font-size:13px">timing_risk</text><line x1="54" x2="466" y1="254.0" y2="254.0" style="stroke:var(--line)"/><text x="48" y="258.0" text-anchor="end">0</text><line x1="54" x2="466" y1="212.4" y2="212.4" style="stroke:var(--line)"/><text x="48" y="216.4" text-anchor="end">0.02</text><line x1="54" x2="466" y1="170.8" y2="170.8" style="stroke:var(--line)"/><text x="48" y="174.8" text-anchor="end">0.04</text><line x1="54" x2="466" y1="129.2" y2="129.2" style="stroke:var(--line)"/><text x="48" y="133.2" text-anchor="end">0.06</text><line x1="54" x2="466" y1="87.6" y2="87.6" style="stroke:var(--line)"/><text x="48" y="91.6" text-anchor="end">0.08</text><line x1="54" x2="466" y1="46.0" y2="46.0" style="stroke:var(--line)"/><text x="48" y="50.0" text-anchor="end">0.1</text><text x="54.0" y="270" text-anchor="middle">0</text><text x="136.4" y="270" text-anchor="middle">2</text><text x="218.8" y="270" text-anchor="middle">4</text><text x="301.2" y="270" text-anchor="middle">6</text><text x="383.6" y="270" text-anchor="middle">8</text><text x="466.0" y="270" text-anchor="middle">10</text><text x="260.0" y="290" text-anchor="middle">Index</text><text transform="translate(12 150.0) rotate(-90)" text-anchor="middle">timing_risk</text><text x="466" y="290" text-anchor="end" style="font-style:italic">synthetic</text><polyline points="95.2,234.2 136.4,226.1 177.6,214.5 218.8,198.1 260.0,185.6 301.2,165.7 342.4,149.5 383.6,129.1 424.8,101.0 466.0,77.3" style="fill:none;stroke:var(--c1);stroke-width:2;stroke-linejoin:round"/></svg><p>timing_risk, Python CLI, from examples/liq_curve_cost_j.json. Synthetic inputs, not market data.</p></div>

<div class="chart"><svg viewBox="0 0 480 300" role="img" aria-label="optimal_horizon, synthetic data" xmlns="http://www.w3.org/2000/svg" style="font:12px Segoe UI,Arial,sans-serif;fill:currentColor"><text x="54" y="15" style="font-weight:600;font-size:13px">optimal_horizon</text><line x1="54" x2="466" y1="254.0" y2="254.0" style="stroke:var(--line)"/><text x="48" y="258.0" text-anchor="end">0</text><line x1="54" x2="466" y1="202.0" y2="202.0" style="stroke:var(--line)"/><text x="48" y="206.0" text-anchor="end">0.2</text><line x1="54" x2="466" y1="150.0" y2="150.0" style="stroke:var(--line)"/><text x="48" y="154.0" text-anchor="end">0.4</text><line x1="54" x2="466" y1="98.0" y2="98.0" style="stroke:var(--line)"/><text x="48" y="102.0" text-anchor="end">0.6</text><line x1="54" x2="466" y1="46.0" y2="46.0" style="stroke:var(--line)"/><text x="48" y="50.0" text-anchor="end">0.8</text><text x="54.0" y="270" text-anchor="middle">0</text><text x="157.0" y="270" text-anchor="middle">1</text><text x="260.0" y="270" text-anchor="middle">2</text><text x="363.0" y="270" text-anchor="middle">3</text><text x="466.0" y="270" text-anchor="middle">4</text><text x="260.0" y="290" text-anchor="middle">Index</text><text transform="translate(12 150.0) rotate(-90)" text-anchor="middle">optimal_horizon</text><text x="466" y="290" text-anchor="end" style="font-style:italic">synthetic</text><polyline points="157.0,245.3 260.0,226.6 363.0,167.4 466.0,60.4" style="fill:none;stroke:var(--c1);stroke-width:2;stroke-linejoin:round"/></svg><p>optimal_horizon, Python CLI, from examples/liq_curve_cost_j.json. Synthetic inputs, not market data.</p></div>

<div class="chart"><svg viewBox="0 0 480 300" role="img" aria-label="min_cost, synthetic data" xmlns="http://www.w3.org/2000/svg" style="font:12px Segoe UI,Arial,sans-serif;fill:currentColor"><text x="54" y="15" style="font-weight:600;font-size:13px">min_cost</text><line x1="54" x2="466" y1="254.0" y2="254.0" style="stroke:var(--line)"/><text x="48" y="258.0" text-anchor="end">0</text><line x1="54" x2="466" y1="202.0" y2="202.0" style="stroke:var(--line)"/><text x="48" y="206.0" text-anchor="end">0.01</text><line x1="54" x2="466" y1="150.0" y2="150.0" style="stroke:var(--line)"/><text x="48" y="154.0" text-anchor="end">0.02</text><line x1="54" x2="466" y1="98.0" y2="98.0" style="stroke:var(--line)"/><text x="48" y="102.0" text-anchor="end">0.03</text><line x1="54" x2="466" y1="46.0" y2="46.0" style="stroke:var(--line)"/><text x="48" y="50.0" text-anchor="end">0.04</text><text x="54.0" y="270" text-anchor="middle">0</text><text x="157.0" y="270" text-anchor="middle">1</text><text x="260.0" y="270" text-anchor="middle">2</text><text x="363.0" y="270" text-anchor="middle">3</text><text x="466.0" y="270" text-anchor="middle">4</text><text x="260.0" y="290" text-anchor="middle">Index</text><text transform="translate(12 150.0) rotate(-90)" text-anchor="middle">min_cost</text><text x="466" y="290" text-anchor="end" style="font-style:italic">synthetic</text><polyline points="157.0,215.4 260.0,187.3 363.0,137.4 466.0,80.9" style="fill:none;stroke:var(--c1);stroke-width:2;stroke-linejoin:round"/></svg><p>min_cost, Python CLI, from examples/liq_curve_cost_j.json. Synthetic inputs, not market data.</p></div>

## Four-language agreement

Each CLI built these numbers on its own, from the same input file. Agreement shows only that the four agree. It does not show that they are right, which is what the oracle is for.

| Output | Values | Last value: Java | C++ | Python | Rust | Largest difference, any value |
|---|---|---|---|---|---|---|
| liq.curve.cost: spread_cost | 1 | 0.0005 | 0.0005 | 0.0005 | 0.0005 | 0 |
| liq.curve.cost: impact | 40 | 0.0031622776601683794 | 0.0031622776601683794 | 0.0031622776601683794 | 0.0031622776601683794 | 0 |
| liq.curve.cost: timing_risk | 10 | 0.084947434726816 | 0.084947434726816 | 0.084947434726816 | 0.084947434726816 | 0 |
| liq.curve.cost: total_cost | 40 | 0.08860971238698438 | 0.08860971238698438 | 0.08860971238698438 | 0.08860971238698438 | 0 |
| liq.curve.cost: optimal_horizon | 4 | 0.7445257576848566 | 0.7445257576848566 | 0.7445257576848566 | 0.7445257576848566 | 0 |
| liq.curve.cost: min_cost | 4 | 0.033279711720832564 | 0.033279711720832564 | 0.033279711720832564 | 0.033279711720832564 | 0 |

## Oracle evidence and limits

7 golden cases with status ok in `datasets/golden/stage_j` for `liq.curve.cost`, by `verified_by`:

| Operation: sources | Cases |
|---|---|
| liq.curve.cost: hand, reference-computed | 2 |
| liq.curve.cost: reference-computed | 5 |

Limits: one input per operation, synthetic unless labelled real; charts plot output index, not calendar time; the specs are in `specifications/`.
