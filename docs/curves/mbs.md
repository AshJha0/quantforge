# MBS prepayment and valuation curves

<p class="note">Status: Implemented, not Validated. Validation is self-assessment until the human review at the end of the project. Data: synthetic. These are constructed inputs, not market data, and nothing is traded.</p>

Generated on 2026-11-07 from commit `8dddd58`, by Java 0.4.0 (JDK 25.0.5+8-LTS), C++ 0.4.0 (GCC 16.2.0), Python 0.4.0 (CPython 3.15.2), Rust 0.4.0 (rustc 1.99.1), on one Windows machine.

## What it is

Prepayment speeds by month and the resulting cash flows. Stage D.

## Runs

Each run is labelled. Synthetic inputs are copied from a golden case's inputs, so they show the method, not a market. Real inputs name their source and date.

### `mbs.cashflows`

**Synthetic.** Synthetic inputs, not market data.

Input: [`examples/mbs_cashflows_d.json`](../../examples/mbs_cashflows_d.json). Command: `quantforge batch < examples/mbs_cashflows_d.json` (wrap as one line).

| Output | Python value |
|---|---|
| `balance` | 60 values |
| `interest` | 60 values |
| `scheduled_principal` | 60 values |
| `prepayment` | 60 values |
| `wal` | `2.487278641739551` |

<div class="chart"><svg viewBox="0 0 480 300" role="img" aria-label="balance, synthetic data" xmlns="http://www.w3.org/2000/svg" style="font:12px Segoe UI,Arial,sans-serif;fill:currentColor"><text x="54" y="15" style="font-weight:600;font-size:13px">balance</text><line x1="54" x2="466" y1="254.0" y2="254.0" style="stroke:var(--line)"/><text x="48" y="258.0" text-anchor="end">0</text><line x1="54" x2="466" y1="212.4" y2="212.4" style="stroke:var(--line)"/><text x="48" y="216.4" text-anchor="end">200000</text><line x1="54" x2="466" y1="170.8" y2="170.8" style="stroke:var(--line)"/><text x="48" y="174.8" text-anchor="end">400000</text><line x1="54" x2="466" y1="129.2" y2="129.2" style="stroke:var(--line)"/><text x="48" y="133.2" text-anchor="end">600000</text><line x1="54" x2="466" y1="87.6" y2="87.6" style="stroke:var(--line)"/><text x="48" y="91.6" text-anchor="end">800000</text><line x1="54" x2="466" y1="46.0" y2="46.0" style="stroke:var(--line)"/><text x="48" y="50.0" text-anchor="end">1000000</text><text x="54.0" y="270" text-anchor="middle">0</text><text x="191.3" y="270" text-anchor="middle">20</text><text x="328.7" y="270" text-anchor="middle">40</text><text x="466.0" y="270" text-anchor="middle">60</text><text x="260.0" y="290" text-anchor="middle">Index</text><text transform="translate(12 150.0) rotate(-90)" text-anchor="middle">balance</text><text x="466" y="290" text-anchor="end" style="font-style:italic">synthetic</text><polyline points="60.9,46.0 67.7,49.0 74.6,52.1 81.5,55.2 88.3,58.4 95.2,61.6 102.1,64.9 108.9,68.3 115.8,71.7 122.7,75.1 129.5,78.6 136.4,82.2 143.3,85.7 150.1,89.4 157.0,93.0 163.9,96.7 170.7,100.5 177.6,104.2 184.5,108.0 191.3,111.8 198.2,115.6 205.1,119.5 211.9,123.3 218.8,127.2 225.7,131.0 232.5,134.9 239.4,138.8 246.3,142.7 253.1,146.6 260.0,150.4 266.9,154.3 273.7,158.1 280.6,161.9 287.5,165.7 294.3,169.4 301.2,173.1 308.1,176.7 314.9,180.3 321.8,183.9 328.7,187.4 335.5,190.9 342.4,194.4 349.3,197.8 356.1,201.2 363.0,204.6 369.9,207.9 376.7,211.2 383.6,214.5 390.5,217.7 397.3,220.9 404.2,224.1 411.1,227.2 417.9,230.3 424.8,233.4 431.7,236.4 438.5,239.4 445.4,242.4 452.3,245.3 459.1,248.3 466.0,251.1" style="fill:none;stroke:var(--c1);stroke-width:2;stroke-linejoin:round"/></svg><p>balance, Python CLI, from examples/mbs_cashflows_d.json. Synthetic inputs, not market data.</p></div>

<div class="chart"><svg viewBox="0 0 480 300" role="img" aria-label="interest, synthetic data" xmlns="http://www.w3.org/2000/svg" style="font:12px Segoe UI,Arial,sans-serif;fill:currentColor"><text x="54" y="15" style="font-weight:600;font-size:13px">interest</text><line x1="54" x2="466" y1="254.0" y2="254.0" style="stroke:var(--line)"/><text x="48" y="258.0" text-anchor="end">0</text><line x1="54" x2="466" y1="212.4" y2="212.4" style="stroke:var(--line)"/><text x="48" y="216.4" text-anchor="end">1000</text><line x1="54" x2="466" y1="170.8" y2="170.8" style="stroke:var(--line)"/><text x="48" y="174.8" text-anchor="end">2000</text><line x1="54" x2="466" y1="129.2" y2="129.2" style="stroke:var(--line)"/><text x="48" y="133.2" text-anchor="end">3000</text><line x1="54" x2="466" y1="87.6" y2="87.6" style="stroke:var(--line)"/><text x="48" y="91.6" text-anchor="end">4000</text><line x1="54" x2="466" y1="46.0" y2="46.0" style="stroke:var(--line)"/><text x="48" y="50.0" text-anchor="end">5000</text><text x="54.0" y="270" text-anchor="middle">0</text><text x="191.3" y="270" text-anchor="middle">20</text><text x="328.7" y="270" text-anchor="middle">40</text><text x="466.0" y="270" text-anchor="middle">60</text><text x="260.0" y="290" text-anchor="middle">Index</text><text transform="translate(12 150.0) rotate(-90)" text-anchor="middle">interest</text><text x="466" y="290" text-anchor="end" style="font-style:italic">synthetic</text><polyline points="60.9,46.0 67.7,49.0 74.6,52.1 81.5,55.2 88.3,58.4 95.2,61.6 102.1,64.9 108.9,68.3 115.8,71.7 122.7,75.1 129.5,78.6 136.4,82.2 143.3,85.7 150.1,89.4 157.0,93.0 163.9,96.7 170.7,100.5 177.6,104.2 184.5,108.0 191.3,111.8 198.2,115.6 205.1,119.5 211.9,123.3 218.8,127.2 225.7,131.0 232.5,134.9 239.4,138.8 246.3,142.7 253.1,146.6 260.0,150.4 266.9,154.3 273.7,158.1 280.6,161.9 287.5,165.7 294.3,169.4 301.2,173.1 308.1,176.7 314.9,180.3 321.8,183.9 328.7,187.4 335.5,190.9 342.4,194.4 349.3,197.8 356.1,201.2 363.0,204.6 369.9,207.9 376.7,211.2 383.6,214.5 390.5,217.7 397.3,220.9 404.2,224.1 411.1,227.2 417.9,230.3 424.8,233.4 431.7,236.4 438.5,239.4 445.4,242.4 452.3,245.3 459.1,248.3 466.0,251.1" style="fill:none;stroke:var(--c1);stroke-width:2;stroke-linejoin:round"/></svg><p>interest, Python CLI, from examples/mbs_cashflows_d.json. Synthetic inputs, not market data.</p></div>

<div class="chart"><svg viewBox="0 0 480 300" role="img" aria-label="scheduled_principal, synthetic data" xmlns="http://www.w3.org/2000/svg" style="font:12px Segoe UI,Arial,sans-serif;fill:currentColor"><text x="54" y="15" style="font-weight:600;font-size:13px">scheduled_principal</text><line x1="54" x2="466" y1="254.0" y2="254.0" style="stroke:var(--line)"/><text x="48" y="258.0" text-anchor="end">13500</text><line x1="54" x2="466" y1="219.3" y2="219.3" style="stroke:var(--line)"/><text x="48" y="223.3" text-anchor="end">13750</text><line x1="54" x2="466" y1="184.7" y2="184.7" style="stroke:var(--line)"/><text x="48" y="188.7" text-anchor="end">14000</text><line x1="54" x2="466" y1="150.0" y2="150.0" style="stroke:var(--line)"/><text x="48" y="154.0" text-anchor="end">14250</text><line x1="54" x2="466" y1="115.3" y2="115.3" style="stroke:var(--line)"/><text x="48" y="119.3" text-anchor="end">14500</text><line x1="54" x2="466" y1="80.7" y2="80.7" style="stroke:var(--line)"/><text x="48" y="84.7" text-anchor="end">14750</text><line x1="54" x2="466" y1="46.0" y2="46.0" style="stroke:var(--line)"/><text x="48" y="50.0" text-anchor="end">15000</text><text x="54.0" y="270" text-anchor="middle">0</text><text x="191.3" y="270" text-anchor="middle">20</text><text x="328.7" y="270" text-anchor="middle">40</text><text x="466.0" y="270" text-anchor="middle">60</text><text x="260.0" y="290" text-anchor="middle">Index</text><text transform="translate(12 150.0) rotate(-90)" text-anchor="middle">scheduled_principal</text><text x="466" y="290" text-anchor="end" style="font-style:italic">synthetic</text><polyline points="60.9,163.9 67.7,153.8 74.6,144.1 81.5,134.9 88.3,126.1 95.2,117.8 102.1,110.0 108.9,102.6 115.8,95.8 122.7,89.5 129.5,83.6 136.4,78.3 143.3,73.5 150.1,69.2 157.0,65.4 163.9,62.2 170.7,59.5 177.6,57.4 184.5,55.8 191.3,54.7 198.2,54.2 205.1,54.2 211.9,54.8 218.8,56.0 225.7,57.7 232.5,59.9 239.4,62.8 246.3,66.1 253.1,70.1 260.0,74.5 266.9,79.6 273.7,84.6 280.6,89.6 287.5,94.6 294.3,99.6 301.2,104.6 308.1,109.5 314.9,114.5 321.8,119.4 328.7,124.3 335.5,129.3 342.4,134.2 349.3,139.0 356.1,143.9 363.0,148.8 369.9,153.6 376.7,158.5 383.6,163.3 390.5,168.1 397.3,172.9 404.2,177.7 411.1,182.5 417.9,187.3 424.8,192.0 431.7,196.8 438.5,201.5 445.4,206.2 452.3,210.9 459.1,215.6 466.0,220.3" style="fill:none;stroke:var(--c1);stroke-width:2;stroke-linejoin:round"/></svg><p>scheduled_principal, Python CLI, from examples/mbs_cashflows_d.json. Synthetic inputs, not market data.</p></div>

## Four-language agreement

Each CLI built these numbers on its own, from the same input file. Agreement shows only that the four agree. It does not show that they are right, which is what the oracle is for.

| Output | Values | Last value: Java | C++ | Python | Rust | Largest difference, any value |
|---|---|---|---|---|---|---|
| mbs.cashflows: balance | 60 | 13742.78751754656 | 13742.787517545994 | 13742.787517545994 | 13742.787517545994 | 2.79e-09 |
| mbs.cashflows: interest | 60 | 68.71393758773279 | 68.71393758772997 | 68.71393758772997 | 68.71393758772997 | 1.41e-11 |
| mbs.cashflows: scheduled_principal | 60 | 13742.78751754656 | 13742.787517545994 | 13742.787517545994 | 13742.787517545994 | 5.66e-10 |
| mbs.cashflows: prepayment | 60 | 0.0 | 0.0 | 0.0 | 0.0 | 4.64e-11 |
| mbs.cashflows: wal | 1 | 2.4872786417395614 | 2.487278641739551 | 2.487278641739551 | 2.487278641739551 | 1.02e-14 |

## Oracle evidence and limits

3 golden cases with status ok in `datasets/golden/stage_d` for `mbs.cashflows`, by `verified_by`:

| Operation: sources | Cases |
|---|---|
| mbs.cashflows: analytic, psa-standard | 3 |

Limits: one input per operation, synthetic unless labelled real; charts plot output index, not calendar time; the specs are in `specifications/`.
