# Credit curves and ISDA CDS

<p class="note">Status: Implemented, not Validated. Validation is self-assessment until the human review at the end of the project. Data: synthetic. These are constructed inputs, not market data, and nothing is traded.</p>

Generated on 2026-11-07 from commit `8dddd58`, by Java 0.4.0 (JDK 25.0.5+8-LTS), C++ 0.4.0 (GCC 16.2.0), Python 0.4.0 (CPython 3.15.2), Rust 0.4.0 (rustc 1.99.1), on one Windows machine.

## What it is

Survival probabilities and hazard rates from CDS quotes. Stage D, target v0.4.

## Runs

Each run is labelled. Synthetic inputs are copied from a golden case's inputs, so they show the method, not a market. Real inputs name their source and date.

### `credit.cds.bootstrap`

**Synthetic.** Synthetic inputs, not market data.

Input: [`examples/cds_bootstrap_d.json`](../../examples/cds_bootstrap_d.json). Command: `quantforge batch < examples/cds_bootstrap_d.json` (wrap as one line).

| Output | Python value |
|---|---|
| `pillars` | 6 values |

<div class="chart"><svg viewBox="0 0 480 300" role="img" aria-label="pillars: survival, synthetic data" xmlns="http://www.w3.org/2000/svg" style="font:12px Segoe UI,Arial,sans-serif;fill:currentColor"><text x="54" y="15" style="font-weight:600;font-size:13px">pillars: survival</text><line x1="54" x2="466" y1="254.0" y2="254.0" style="stroke:var(--line)"/><text x="48" y="258.0" text-anchor="end">0.75</text><line x1="54" x2="466" y1="212.4" y2="212.4" style="stroke:var(--line)"/><text x="48" y="216.4" text-anchor="end">0.8</text><line x1="54" x2="466" y1="170.8" y2="170.8" style="stroke:var(--line)"/><text x="48" y="174.8" text-anchor="end">0.85</text><line x1="54" x2="466" y1="129.2" y2="129.2" style="stroke:var(--line)"/><text x="48" y="133.2" text-anchor="end">0.9</text><line x1="54" x2="466" y1="87.6" y2="87.6" style="stroke:var(--line)"/><text x="48" y="91.6" text-anchor="end">0.95</text><line x1="54" x2="466" y1="46.0" y2="46.0" style="stroke:var(--line)"/><text x="48" y="50.0" text-anchor="end">1</text><text x="54.0" y="270" text-anchor="middle">0</text><text x="191.3" y="270" text-anchor="middle">2</text><text x="328.7" y="270" text-anchor="middle">4</text><text x="466.0" y="270" text-anchor="middle">6</text><text x="260.0" y="290" text-anchor="middle">pillars number</text><text transform="translate(12 150.0) rotate(-90)" text-anchor="middle">pillars: survival</text><text x="466" y="290" text-anchor="end" style="font-style:italic">synthetic</text><polyline points="122.7,49.9 191.3,55.4 260.0,84.8 328.7,130.1 397.3,175.0 466.0,242.7" style="fill:none;stroke:var(--c1);stroke-width:2;stroke-linejoin:round"/></svg><p>pillars: survival, Python CLI, from examples/cds_bootstrap_d.json. Synthetic inputs, not market data.</p></div>

## Four-language agreement

Each CLI built these numbers on its own, from the same input file. Agreement shows only that the four agree. It does not show that they are right, which is what the oracle is for.

| Output | Values | Last value: Java | C++ | Python | Rust | Largest difference, any value |
|---|---|---|---|---|---|---|
| credit.cds.bootstrap: pillars | 6 | 0.7635674704223003 | 0.7635674704223001 | 0.7635674704223002 | 0.7635674704223002 | 3.33e-16 |

## Oracle evidence and limits

5 golden cases with status ok in `datasets/golden/stage_d` for `credit.cds.bootstrap`, by `verified_by`:

| Operation: sources | Cases |
|---|---|
| credit.cds.bootstrap: independent-replay, quantlib-1.44-isda-cds-engine | 5 |

Limits: one input per operation, synthetic unless labelled real; charts plot output index, not calendar time; the stage D specs are in `specifications/`.
