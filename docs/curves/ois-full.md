# OIS curves: full SOFR, ESTR and SONIA

<p class="note">Status: Implemented, not Validated. Validation is self-assessment until the human review at the end of the project. Data: synthetic. These are constructed inputs, not market data, and nothing is traded.</p>

Generated on 2026-11-07 from commit `8dddd58`, by Java 0.4.0 (JDK 25.0.5+8-LTS), C++ 0.4.0 (GCC 16.2.0), Python 0.4.0 (CPython 3.15.2), Rust 0.4.0 (rustc 1.99.1), on one Windows machine.

## What it is

Discount factors and forwards, with meeting-date steps and observation conventions, and compounding of published overnight fixings. The ESTR payment lag of 2 days is a library choice, from Strata 2.12.78, not a market standard; TP ICAP terms use 1 (ruling R1-2). Stage D, target v0.4.

## Runs

Each run is labelled. Synthetic inputs are copied from a golden case's inputs, so they show the method, not a market. Real inputs name their source and date.

### `rates.ois.bootstrap`

**Synthetic.** Synthetic inputs, not market data.

Input: [`examples/estr_ois_d.json`](../../examples/estr_ois_d.json). Command: `quantforge batch < examples/estr_ois_d.json` (wrap as one line).

| Output | Python value |
|---|---|
| `pillars` | 13 values |

<div class="chart"><svg viewBox="0 0 480 300" role="img" aria-label="pillars: discount_factor, synthetic data" xmlns="http://www.w3.org/2000/svg" style="font:12px Segoe UI,Arial,sans-serif;fill:currentColor"><text x="54" y="15" style="font-weight:600;font-size:13px">pillars: discount_factor</text><line x1="54" x2="466" y1="254.0" y2="254.0" style="stroke:var(--line)"/><text x="48" y="258.0" text-anchor="end">0.5</text><line x1="54" x2="466" y1="212.4" y2="212.4" style="stroke:var(--line)"/><text x="48" y="216.4" text-anchor="end">0.6</text><line x1="54" x2="466" y1="170.8" y2="170.8" style="stroke:var(--line)"/><text x="48" y="174.8" text-anchor="end">0.7</text><line x1="54" x2="466" y1="129.2" y2="129.2" style="stroke:var(--line)"/><text x="48" y="133.2" text-anchor="end">0.8</text><line x1="54" x2="466" y1="87.6" y2="87.6" style="stroke:var(--line)"/><text x="48" y="91.6" text-anchor="end">0.9</text><line x1="54" x2="466" y1="46.0" y2="46.0" style="stroke:var(--line)"/><text x="48" y="50.0" text-anchor="end">1</text><text x="54.0" y="270" text-anchor="middle">0</text><text x="191.3" y="270" text-anchor="middle">5</text><text x="328.7" y="270" text-anchor="middle">10</text><text x="466.0" y="270" text-anchor="middle">15</text><text x="260.0" y="290" text-anchor="middle">pillars number</text><text transform="translate(12 150.0) rotate(-90)" text-anchor="middle">pillars: discount_factor</text><text x="466" y="290" text-anchor="end" style="font-style:italic">synthetic</text><polyline points="81.5,46.3 108.9,47.0 136.4,48.5 163.9,50.6 191.3,54.6 218.8,61.8 246.3,68.7 273.7,84.0 301.2,100.9 328.7,127.4 356.1,169.2 383.6,204.2 411.1,250.4" style="fill:none;stroke:var(--c1);stroke-width:2;stroke-linejoin:round"/></svg><p>pillars: discount_factor, Python CLI, from examples/estr_ois_d.json. Synthetic inputs, not market data.</p></div>
### `rates.ois.compound_dated`

**Real data.** Real data: SOFR fixings from 2026-09-21 to 2026-11-05, from the Federal Reserve Bank of New York markets API, fetched 2026-11-07, converted from percent to decimal (the only modification). The SOFR data is subject to the Terms of Use posted at newyorkfed.org; the New York Fed does not endorse this use, and SOFR is calculated using data licensed from DTCC Solutions LLC.

Input: [`examples/real_sofr_compound_2026_10.json`](../../examples/real_sofr_compound_2026_10.json). Command: `quantforge batch < examples/real_sofr_compound_2026_10.json` (wrap as one line).

| Output | Python value |
|---|---|
| `compounded_rate` | `0.0390412317293215` |
| `accrual` | `0.08888888888888889` |
| `interest` | `0.0034703317092730224` |



## Four-language agreement

Each CLI built these numbers on its own, from the same input file. Agreement shows only that the four agree. It does not show that they are right, which is what the oracle is for.

| Output | Values | Last value: Java | C++ | Python | Rust | Largest difference, any value |
|---|---|---|---|---|---|---|
| rates.ois.bootstrap: pillars | 13 | 0.5087217489424135 | 0.5087217489424133 | 0.5087217489424133 | 0.5087217489424135 | 3.89e-15 |
| rates.ois.compound_dated: compounded_rate | 1 | 0.0390412317293215 | 0.0390412317293215 | 0.0390412317293215 | 0.0390412317293215 | 0 |
| rates.ois.compound_dated: accrual | 1 | 0.08888888888888889 | 0.08888888888888889 | 0.08888888888888889 | 0.08888888888888889 | 0 |
| rates.ois.compound_dated: interest | 1 | 0.0034703317092730224 | 0.0034703317092730224 | 0.0034703317092730224 | 0.0034703317092730224 | 0 |

## Oracle evidence and limits

79 golden cases with status ok in `datasets/golden/stage_d` for `rates.ois.bootstrap`, `rates.ois.compound_dated`, by `verified_by`:

| Operation: sources | Cases |
|---|---|
| rates.ois.bootstrap: independent-replay, quantlib-1.44 | 10 |
| rates.ois.compound_dated: exact-rational, quantlib-1.44 | 69 |

Limits: one input per operation, synthetic unless labelled real; charts plot output index, not calendar time; the stage D specs are in `specifications/`.
