# Funding curve

<p class="note">Status: Implemented, not Validated. Validation is self-assessment until the human review at the end of the project. Data: synthetic. These are constructed inputs, not market data, and nothing is traded.</p>

Generated on 2026-11-11 from commit `dbf0843`, by Java 0.7.0 (JDK 25.0.5+8-LTS), C++ 0.7.0 (GCC 16.2.0), Python 0.7.0 (CPython 3.15.2), Rust 0.7.0 (rustc 1.99.1), on one Windows machine.

## What it is

Unsecured funding: the OIS curve times a spread factor, `D_f(t) = D_ois(t) exp(-integral of s)`, with the spread `s` piecewise flat between the dates of simple ACT/360 funding quotes. It discounts uncollateralised cash flows and feeds FVA (`specifications/02-curves/joint-solve-and-funding.md`). Stage F.

## Runs

Each run is labelled. Synthetic inputs are copied from a golden case's inputs, so they show the method, not a market. Real inputs name their source and date.

### `rates.funding.curve`

**Synthetic.** Synthetic inputs, not market data.

Input: [`examples/funding_curve_f.json`](../../examples/funding_curve_f.json). Command: `quantforge batch < examples/funding_curve_f.json` (wrap as one line).

| Output | Python value |
|---|---|
| `spreads` | 5 values |
| `pillars` | 5 values |
| `discount_factors` | 50 values |

<div class="chart"><svg viewBox="0 0 480 300" role="img" aria-label="spreads, synthetic data" xmlns="http://www.w3.org/2000/svg" style="font:12px Segoe UI,Arial,sans-serif;fill:currentColor"><text x="54" y="15" style="font-weight:600;font-size:13px">spreads</text><line x1="54" x2="466" y1="254.0" y2="254.0" style="stroke:var(--line)"/><text x="48" y="258.0" text-anchor="end">0.005</text><line x1="54" x2="466" y1="202.0" y2="202.0" style="stroke:var(--line)"/><text x="48" y="206.0" text-anchor="end">0.0055</text><line x1="54" x2="466" y1="150.0" y2="150.0" style="stroke:var(--line)"/><text x="48" y="154.0" text-anchor="end">0.006</text><line x1="54" x2="466" y1="98.0" y2="98.0" style="stroke:var(--line)"/><text x="48" y="102.0" text-anchor="end">0.0065</text><line x1="54" x2="466" y1="46.0" y2="46.0" style="stroke:var(--line)"/><text x="48" y="50.0" text-anchor="end">0.007</text><text x="54.0" y="270" text-anchor="middle">0</text><text x="136.4" y="270" text-anchor="middle">1</text><text x="218.8" y="270" text-anchor="middle">2</text><text x="301.2" y="270" text-anchor="middle">3</text><text x="383.6" y="270" text-anchor="middle">4</text><text x="466.0" y="270" text-anchor="middle">5</text><text x="260.0" y="290" text-anchor="middle">Index</text><text transform="translate(12 150.0) rotate(-90)" text-anchor="middle">spreads</text><text x="466" y="290" text-anchor="end" style="font-style:italic">synthetic</text><polyline points="136.4,246.5 218.8,178.3 301.2,127.6 383.6,62.5 466.0,233.5" style="fill:none;stroke:var(--c1);stroke-width:2;stroke-linejoin:round"/></svg><p>spreads, Python CLI, from examples/funding_curve_f.json. Synthetic inputs, not market data.</p></div>

<div class="chart"><svg viewBox="0 0 480 300" role="img" aria-label="pillars: discount_factor, synthetic data" xmlns="http://www.w3.org/2000/svg" style="font:12px Segoe UI,Arial,sans-serif;fill:currentColor"><text x="54" y="15" style="font-weight:600;font-size:13px">pillars: discount_factor</text><line x1="54" x2="466" y1="254.0" y2="254.0" style="stroke:var(--line)"/><text x="48" y="258.0" text-anchor="end">0.8</text><line x1="54" x2="466" y1="202.0" y2="202.0" style="stroke:var(--line)"/><text x="48" y="206.0" text-anchor="end">0.85</text><line x1="54" x2="466" y1="150.0" y2="150.0" style="stroke:var(--line)"/><text x="48" y="154.0" text-anchor="end">0.9</text><line x1="54" x2="466" y1="98.0" y2="98.0" style="stroke:var(--line)"/><text x="48" y="102.0" text-anchor="end">0.95</text><line x1="54" x2="466" y1="46.0" y2="46.0" style="stroke:var(--line)"/><text x="48" y="50.0" text-anchor="end">1</text><text x="54.0" y="270" text-anchor="middle">0</text><text x="136.4" y="270" text-anchor="middle">1</text><text x="218.8" y="270" text-anchor="middle">2</text><text x="301.2" y="270" text-anchor="middle">3</text><text x="383.6" y="270" text-anchor="middle">4</text><text x="466.0" y="270" text-anchor="middle">5</text><text x="260.0" y="290" text-anchor="middle">pillars number</text><text transform="translate(12 150.0) rotate(-90)" text-anchor="middle">pillars: discount_factor</text><text x="466" y="290" text-anchor="end" style="font-style:italic">synthetic</text><polyline points="136.4,58.3 218.8,69.9 301.2,91.6 383.6,131.4 466.0,238.2" style="fill:none;stroke:var(--c1);stroke-width:2;stroke-linejoin:round"/></svg><p>pillars: discount_factor, Python CLI, from examples/funding_curve_f.json. Synthetic inputs, not market data.</p></div>

<div class="chart"><svg viewBox="0 0 480 300" role="img" aria-label="discount_factors, synthetic data" xmlns="http://www.w3.org/2000/svg" style="font:12px Segoe UI,Arial,sans-serif;fill:currentColor"><text x="54" y="15" style="font-weight:600;font-size:13px">discount_factors</text><line x1="54" x2="466" y1="254.0" y2="254.0" style="stroke:var(--line)"/><text x="48" y="258.0" text-anchor="end">0.6</text><line x1="54" x2="466" y1="202.0" y2="202.0" style="stroke:var(--line)"/><text x="48" y="206.0" text-anchor="end">0.7</text><line x1="54" x2="466" y1="150.0" y2="150.0" style="stroke:var(--line)"/><text x="48" y="154.0" text-anchor="end">0.8</text><line x1="54" x2="466" y1="98.0" y2="98.0" style="stroke:var(--line)"/><text x="48" y="102.0" text-anchor="end">0.9</text><line x1="54" x2="466" y1="46.0" y2="46.0" style="stroke:var(--line)"/><text x="48" y="50.0" text-anchor="end">1</text><text x="54.0" y="270" text-anchor="middle">0</text><text x="136.4" y="270" text-anchor="middle">10</text><text x="218.8" y="270" text-anchor="middle">20</text><text x="301.2" y="270" text-anchor="middle">30</text><text x="383.6" y="270" text-anchor="middle">40</text><text x="466.0" y="270" text-anchor="middle">50</text><text x="260.0" y="290" text-anchor="middle">Index</text><text transform="translate(12 150.0) rotate(-90)" text-anchor="middle">discount_factors</text><text x="466" y="290" text-anchor="end" style="font-style:italic">synthetic</text><polyline points="62.2,46.0 70.5,52.1 78.7,57.8 87.0,63.2 95.2,68.5 103.4,73.5 111.7,78.4 119.9,83.3 128.2,88.1 136.4,92.8 144.6,97.4 152.9,101.9 161.1,106.4 169.4,110.9 177.6,115.3 185.8,119.7 194.1,124.0 202.3,128.3 210.6,132.5 218.8,136.7 227.0,140.9 235.3,145.0 243.5,149.1 251.8,153.2 260.0,157.2 268.2,161.1 276.5,165.1 284.7,168.9 293.0,172.8 301.2,176.6 309.4,180.4 317.7,184.1 325.9,187.8 334.2,191.5 342.4,195.1 350.6,198.7 358.9,202.3 367.1,205.8 375.4,209.3 383.6,212.8 391.8,216.2 400.1,219.6 408.3,223.0 416.6,226.3 424.8,229.6 433.0,232.8 441.3,236.1 449.5,239.3 457.8,242.4 466.0,245.6" style="fill:none;stroke:var(--c1);stroke-width:2;stroke-linejoin:round"/></svg><p>discount_factors, Python CLI, from examples/funding_curve_f.json. Synthetic inputs, not market data.</p></div>

## Four-language agreement

Each CLI built these numbers on its own, from the same input file. Agreement shows only that the four agree. It does not show that they are right, which is what the oracle is for.

| Output | Values | Last value: Java | C++ | Python | Rust | Largest difference, any value |
|---|---|---|---|---|---|---|
| rates.funding.curve: spreads | 5 | 0.005196674683710448 | 0.005196674683710485 | 0.005196674683710448 | 0.005196674683710448 | 2.98e-16 |
| rates.funding.curve: pillars | 5 | 0.8151764109684703 | 0.8151764109684703 | 0.8151764109684703 | 0.8151764109684703 | 1.11e-16 |
| rates.funding.curve: discount_factors | 50 | 0.6161855590552184 | 0.6161855590552182 | 0.6161855590552184 | 0.6161855590552184 | 2.22e-16 |

## Oracle evidence and limits

3 golden cases with status ok in `datasets/golden/stage_f` for `rates.funding.curve`, by `verified_by`:

| Operation: sources | Cases |
|---|---|
| rates.funding.curve: analytic | 1 |
| rates.funding.curve: analytic, independent-replay | 2 |

Limits: one input per operation, synthetic unless labelled real; charts plot output index, not calendar time; the specs are in `specifications/`.
