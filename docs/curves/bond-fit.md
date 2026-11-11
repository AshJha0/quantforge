# Bond and sovereign curve fits

<p class="note">Status: Implemented, not Validated. Validation is self-assessment until the human review at the end of the project. Data: synthetic. These are constructed inputs, not market data, and nothing is traded.</p>

Generated on 2026-11-07 from commit `8dddd58`, by Java 0.4.0 (JDK 25.0.5+8-LTS), C++ 0.4.0 (GCC 16.2.0), Python 0.4.0 (CPython 3.15.2), Rust 0.4.0 (rustc 1.99.1), on one Windows machine.

## What it is

A fitted yield curve against bond yields, with residuals per bond. Stage D.

## Runs

Each run is labelled. Synthetic inputs are copied from a golden case's inputs, so they show the method, not a market. Real inputs name their source and date.

### `bond.fit.nelson_siegel`

**Synthetic.** Synthetic inputs, not market data.

Input: [`examples/bond_fit_ns_d.json`](../../examples/bond_fit_ns_d.json). Command: `quantforge batch < examples/bond_fit_ns_d.json` (wrap as one line).

| Output | Python value |
|---|---|
| `betas` | 3 values |
| `residuals` | 7 values |

<div class="chart"><svg viewBox="0 0 480 300" role="img" aria-label="betas, synthetic data" xmlns="http://www.w3.org/2000/svg" style="font:12px Segoe UI,Arial,sans-serif;fill:currentColor"><text x="54" y="15" style="font-weight:600;font-size:13px">betas</text><line x1="54" x2="466" y1="254.0" y2="254.0" style="stroke:var(--line)"/><text x="48" y="258.0" text-anchor="end">-0.01</text><line x1="54" x2="466" y1="219.3" y2="219.3" style="stroke:var(--line)"/><text x="48" y="223.3" text-anchor="end">0</text><line x1="54" x2="466" y1="184.7" y2="184.7" style="stroke:var(--line)"/><text x="48" y="188.7" text-anchor="end">0.01</text><line x1="54" x2="466" y1="150.0" y2="150.0" style="stroke:var(--line)"/><text x="48" y="154.0" text-anchor="end">0.02</text><line x1="54" x2="466" y1="115.3" y2="115.3" style="stroke:var(--line)"/><text x="48" y="119.3" text-anchor="end">0.03</text><line x1="54" x2="466" y1="80.7" y2="80.7" style="stroke:var(--line)"/><text x="48" y="84.7" text-anchor="end">0.04</text><line x1="54" x2="466" y1="46.0" y2="46.0" style="stroke:var(--line)"/><text x="48" y="50.0" text-anchor="end">0.05</text><text x="54.0" y="270" text-anchor="middle">0</text><text x="191.3" y="270" text-anchor="middle">1</text><text x="328.7" y="270" text-anchor="middle">2</text><text x="466.0" y="270" text-anchor="middle">3</text><text x="260.0" y="290" text-anchor="middle">Index</text><text transform="translate(12 150.0) rotate(-90)" text-anchor="middle">betas</text><text x="466" y="290" text-anchor="end" style="font-style:italic">synthetic</text><polyline points="191.3,73.7 328.7,240.1 466.0,205.5" style="fill:none;stroke:var(--c1);stroke-width:2;stroke-linejoin:round"/></svg><p>betas, Python CLI, from examples/bond_fit_ns_d.json. Synthetic inputs, not market data.</p></div>

## Four-language agreement

Each CLI built these numbers on its own, from the same input file. Agreement shows only that the four agree. It does not show that they are right, which is what the oracle is for.

| Output | Values | Last value: Java | C++ | Python | Rust | Largest difference, any value |
|---|---|---|---|---|---|---|
| bond.fit.nelson_siegel: betas | 3 | 0.003999999999999921 | 0.004000000000000049 | 0.004000000000000049 | 0.0040000000000005 | 5.79e-16 |
| bond.fit.nelson_siegel: residuals | 7 | 1.4210854715202004e-14 | 1.4210854715202004e-14 | 1.4210854715202004e-14 | 1.4210854715202004e-14 | 1.42e-14 |

## Oracle evidence and limits

2 golden cases with status ok in `datasets/golden/stage_d` for `bond.fit.nelson_siegel`, by `verified_by`:

| Operation: sources | Cases |
|---|---|
| bond.fit.nelson_siegel: known-truth, scipy-least-squares | 2 |

Limits: one input per operation, synthetic unless labelled real; charts plot output index, not calendar time; the stage D specs are in `specifications/`.
