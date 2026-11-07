# Dividend and borrow curves

<p class="note">Status: Implemented, not Validated. Validation is self-assessment until the human review at the end of the project. Data: synthetic. These are constructed inputs, not market data, and nothing is traded.</p>

Generated on 2026-11-07 from commit `95cbf11`, by Java 0.4.0 (JDK 25.0.5+8-LTS), C++ 0.4.0 (GCC 16.2.0), Python 0.4.0 (CPython 3.15.2), Rust 0.4.0 (rustc 1.99.1), on one Windows machine.

## What it is

Dividend schedules and borrow cost by term, and their effect on equity forwards. Stage D, target v0.4.

## Runs

Synthetic inputs, not market data. The inputs are copied from a golden case's inputs, so the method is shown, not a market.

### `eq.dividend.implied`

Input: [`examples/dividend_implied_d.json`](../../examples/dividend_implied_d.json). Command: `quantforge batch < examples/dividend_implied_d.json` (wrap as one line).

| Output | Python value |
|---|---|
| `pv_dividends` | 4 values |
| `period_pv_dividends` | 4 values |
| `dividend_yields` | 4 values |

<div class="chart"><svg viewBox="0 0 480 300" role="img" aria-label="pv_dividends, synthetic data" xmlns="http://www.w3.org/2000/svg" style="font:12px Segoe UI,Arial,sans-serif;fill:currentColor"><text x="54" y="15" style="font-weight:600;font-size:13px">pv_dividends</text><line x1="54" x2="466" y1="254.0" y2="254.0" style="stroke:var(--line)"/><text x="48" y="258.0" text-anchor="end">0</text><line x1="54" x2="466" y1="212.4" y2="212.4" style="stroke:var(--line)"/><text x="48" y="216.4" text-anchor="end">20</text><line x1="54" x2="466" y1="170.8" y2="170.8" style="stroke:var(--line)"/><text x="48" y="174.8" text-anchor="end">40</text><line x1="54" x2="466" y1="129.2" y2="129.2" style="stroke:var(--line)"/><text x="48" y="133.2" text-anchor="end">60</text><line x1="54" x2="466" y1="87.6" y2="87.6" style="stroke:var(--line)"/><text x="48" y="91.6" text-anchor="end">80</text><line x1="54" x2="466" y1="46.0" y2="46.0" style="stroke:var(--line)"/><text x="48" y="50.0" text-anchor="end">100</text><text x="54.0" y="270" text-anchor="middle">0</text><text x="157.0" y="270" text-anchor="middle">1</text><text x="260.0" y="270" text-anchor="middle">2</text><text x="363.0" y="270" text-anchor="middle">3</text><text x="466.0" y="270" text-anchor="middle">4</text><text x="260.0" y="290" text-anchor="middle">Index</text><text transform="translate(12 150.0) rotate(-90)" text-anchor="middle">pv_dividends</text><text x="466" y="290" text-anchor="end" style="font-style:italic">synthetic</text><polyline points="157.0,216.7 260.0,182.9 363.0,140.2 466.0,67.0" style="fill:none;stroke:var(--c1);stroke-width:2;stroke-linejoin:round"/></svg><p>pv_dividends, Python CLI, from examples/dividend_implied_d.json. Synthetic inputs, not market data.</p></div>

<div class="chart"><svg viewBox="0 0 480 300" role="img" aria-label="period_pv_dividends, synthetic data" xmlns="http://www.w3.org/2000/svg" style="font:12px Segoe UI,Arial,sans-serif;fill:currentColor"><text x="54" y="15" style="font-weight:600;font-size:13px">period_pv_dividends</text><line x1="54" x2="466" y1="254.0" y2="254.0" style="stroke:var(--line)"/><text x="48" y="258.0" text-anchor="end">15</text><line x1="54" x2="466" y1="212.4" y2="212.4" style="stroke:var(--line)"/><text x="48" y="216.4" text-anchor="end">20</text><line x1="54" x2="466" y1="170.8" y2="170.8" style="stroke:var(--line)"/><text x="48" y="174.8" text-anchor="end">25</text><line x1="54" x2="466" y1="129.2" y2="129.2" style="stroke:var(--line)"/><text x="48" y="133.2" text-anchor="end">30</text><line x1="54" x2="466" y1="87.6" y2="87.6" style="stroke:var(--line)"/><text x="48" y="91.6" text-anchor="end">35</text><line x1="54" x2="466" y1="46.0" y2="46.0" style="stroke:var(--line)"/><text x="48" y="50.0" text-anchor="end">40</text><text x="54.0" y="270" text-anchor="middle">0</text><text x="157.0" y="270" text-anchor="middle">1</text><text x="260.0" y="270" text-anchor="middle">2</text><text x="363.0" y="270" text-anchor="middle">3</text><text x="466.0" y="270" text-anchor="middle">4</text><text x="260.0" y="290" text-anchor="middle">Index</text><text transform="translate(12 150.0) rotate(-90)" text-anchor="middle">period_pv_dividends</text><text x="466" y="290" text-anchor="end" style="font-style:italic">synthetic</text><polyline points="157.0,229.7 260.0,243.4 363.0,208.0 466.0,86.0" style="fill:none;stroke:var(--c1);stroke-width:2;stroke-linejoin:round"/></svg><p>period_pv_dividends, Python CLI, from examples/dividend_implied_d.json. Synthetic inputs, not market data.</p></div>

<div class="chart"><svg viewBox="0 0 480 300" role="img" aria-label="dividend_yields, synthetic data" xmlns="http://www.w3.org/2000/svg" style="font:12px Segoe UI,Arial,sans-serif;fill:currentColor"><text x="54" y="15" style="font-weight:600;font-size:13px">dividend_yields</text><line x1="54" x2="466" y1="254.0" y2="254.0" style="stroke:var(--line)"/><text x="48" y="258.0" text-anchor="end">0.015</text><line x1="54" x2="466" y1="202.0" y2="202.0" style="stroke:var(--line)"/><text x="48" y="206.0" text-anchor="end">0.02</text><line x1="54" x2="466" y1="150.0" y2="150.0" style="stroke:var(--line)"/><text x="48" y="154.0" text-anchor="end">0.025</text><line x1="54" x2="466" y1="98.0" y2="98.0" style="stroke:var(--line)"/><text x="48" y="102.0" text-anchor="end">0.03</text><line x1="54" x2="466" y1="46.0" y2="46.0" style="stroke:var(--line)"/><text x="48" y="50.0" text-anchor="end">0.035</text><text x="54.0" y="270" text-anchor="middle">0</text><text x="157.0" y="270" text-anchor="middle">1</text><text x="260.0" y="270" text-anchor="middle">2</text><text x="363.0" y="270" text-anchor="middle">3</text><text x="466.0" y="270" text-anchor="middle">4</text><text x="260.0" y="290" text-anchor="middle">Index</text><text transform="translate(12 150.0) rotate(-90)" text-anchor="middle">dividend_yields</text><text x="466" y="290" text-anchor="end" style="font-style:italic">synthetic</text><polyline points="157.0,86.3 260.0,214.6 363.0,224.0 466.0,240.8" style="fill:none;stroke:var(--c1);stroke-width:2;stroke-linejoin:round"/></svg><p>dividend_yields, Python CLI, from examples/dividend_implied_d.json. Synthetic inputs, not market data.</p></div>
### `eq.borrow.implied`

Input: [`examples/borrow_implied_d.json`](../../examples/borrow_implied_d.json). Command: `quantforge batch < examples/borrow_implied_d.json` (wrap as one line).

| Output | Python value |
|---|---|
| `borrow_rate` | `0.0030000000000000382` |



## Four-language agreement

Each CLI built these numbers on its own, from the same input file. Agreement shows only that the four agree. It does not show that they are right, which is what the oracle is for.

| Output | Values | Last value: Java | C++ | Python | Rust | Largest difference, any value |
|---|---|---|---|---|---|---|
| eq.dividend.implied: pv_dividends | 4 | 89.91207626349205 | 89.91207626349205 | 89.91207626349205 | 89.91207626349205 | 0 |
| eq.dividend.implied: period_pv_dividends | 4 | 35.188922901902515 | 35.188922901902515 | 35.188922901902515 | 35.188922901902515 | 0 |
| eq.dividend.implied: dividend_yields | 4 | 0.01627252678696537 | 0.01627252678696537 | 0.01627252678696537 | 0.01627252678696537 | 0 |
| eq.borrow.implied: borrow_rate | 1 | 0.0029999999999997195 | 0.0030000000000005578 | 0.0030000000000000382 | 0.0030000000000001137 | 8.38e-16 |

## Oracle evidence and limits

4 golden cases with status ok in `datasets/golden/stage_d` for `eq.dividend.implied`, `eq.borrow.implied`, by `verified_by`:

| Operation: sources | Cases |
|---|---|
| eq.borrow.implied: known-truth | 3 |
| eq.dividend.implied: analytic | 1 |

Limits: one synthetic input per operation; charts plot output index, not calendar time; the stage D specs are in `specifications/`.
