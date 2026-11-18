# Financing term structures: term repo spread and stock borrow

<p class="note">Data: synthetic. These are constructed inputs, not market data, and nothing is traded.</p>

Generated on 2026-11-15 from commit `cb525c5a`, by Java 0.8.3 (JDK 25.0.5+8-LTS), C++ 0.8.3 (GCC 16.2.0), Python 0.8.3 (CPython 3.15.2), Rust 0.8.3 (rustc 1.99.1), on one Windows machine.

## What it is

Secured financing and stock borrow as term structures over the funding curve: each simple term repo quote fixes one pillar of the cumulative spread `S(T) = ln(1 + R T) - Z(T) T`, borrow fees fix the cumulative fee `B(T)`, both linear between pillars (flat forwards), and the equity forward carries on `C(t) = exp(-Z(t) t - S(t) + B(t))` (`specifications/02-curves/financing-term-structure.md`, rulings J-C-2 to J-C-5, which extend D22). The charts show the term spread and the term and forward financing rates read on a 0.04-year grid. Stage J.

## Runs

Each run is labelled. Synthetic inputs are copied from a golden case's inputs, so they show the method, not a market. Real inputs name their source and date.

### `repo.term.curve`

**Synthetic.** Synthetic inputs, not market data.

Input: [`examples/repo_term_curve_j.json`](../../examples/repo_term_curve_j.json). Command: `quantforge batch < examples/repo_term_curve_j.json` (wrap as one line).

| Output | Python value |
|---|---|
| `pillar_spreads` | 4 values |
| `spread` | 25 values |
| `financing_df` | 25 values |
| `financing_rate` | 25 values |
| `forward_financing` | 25 values |
| `borrow_fee` | 25 values |

<div class="chart"><svg viewBox="0 0 480 300" role="img" aria-label="pillar_spreads, synthetic data" xmlns="http://www.w3.org/2000/svg" style="font:12px Segoe UI,Arial,sans-serif;fill:currentColor"><text x="54" y="15" style="font-weight:600;font-size:13px">pillar_spreads</text><line x1="54" x2="466" y1="254.0" y2="254.0" style="stroke:var(--line)"/><text x="48" y="258.0" text-anchor="end">0.0015</text><line x1="54" x2="466" y1="219.3" y2="219.3" style="stroke:var(--line)"/><text x="48" y="223.3" text-anchor="end">0.00175</text><line x1="54" x2="466" y1="184.7" y2="184.7" style="stroke:var(--line)"/><text x="48" y="188.7" text-anchor="end">0.002</text><line x1="54" x2="466" y1="150.0" y2="150.0" style="stroke:var(--line)"/><text x="48" y="154.0" text-anchor="end">0.00225</text><line x1="54" x2="466" y1="115.3" y2="115.3" style="stroke:var(--line)"/><text x="48" y="119.3" text-anchor="end">0.0025</text><line x1="54" x2="466" y1="80.7" y2="80.7" style="stroke:var(--line)"/><text x="48" y="84.7" text-anchor="end">0.00275</text><line x1="54" x2="466" y1="46.0" y2="46.0" style="stroke:var(--line)"/><text x="48" y="50.0" text-anchor="end">0.003</text><text x="54.0" y="270" text-anchor="middle">0</text><text x="157.0" y="270" text-anchor="middle">1</text><text x="260.0" y="270" text-anchor="middle">2</text><text x="363.0" y="270" text-anchor="middle">3</text><text x="466.0" y="270" text-anchor="middle">4</text><text x="260.0" y="290" text-anchor="middle">Index</text><text transform="translate(12 150.0) rotate(-90)" text-anchor="middle">pillar_spreads</text><text x="466" y="290" text-anchor="end" style="font-style:italic">synthetic</text><polyline points="157.0,125.7 260.0,77.8 363.0,180.0 466.0,245.8" style="fill:none;stroke:var(--c1);stroke-width:2;stroke-linejoin:round"/></svg><p>pillar_spreads, Python CLI, from examples/repo_term_curve_j.json. Synthetic inputs, not market data.</p></div>

<div class="chart"><svg viewBox="0 0 480 300" role="img" aria-label="spread, synthetic data" xmlns="http://www.w3.org/2000/svg" style="font:12px Segoe UI,Arial,sans-serif;fill:currentColor"><text x="54" y="15" style="font-weight:600;font-size:13px">spread</text><line x1="54" x2="466" y1="254.0" y2="254.0" style="stroke:var(--line)"/><text x="48" y="258.0" text-anchor="end">0.0015</text><line x1="54" x2="466" y1="219.3" y2="219.3" style="stroke:var(--line)"/><text x="48" y="223.3" text-anchor="end">0.00175</text><line x1="54" x2="466" y1="184.7" y2="184.7" style="stroke:var(--line)"/><text x="48" y="188.7" text-anchor="end">0.002</text><line x1="54" x2="466" y1="150.0" y2="150.0" style="stroke:var(--line)"/><text x="48" y="154.0" text-anchor="end">0.00225</text><line x1="54" x2="466" y1="115.3" y2="115.3" style="stroke:var(--line)"/><text x="48" y="119.3" text-anchor="end">0.0025</text><line x1="54" x2="466" y1="80.7" y2="80.7" style="stroke:var(--line)"/><text x="48" y="84.7" text-anchor="end">0.00275</text><line x1="54" x2="466" y1="46.0" y2="46.0" style="stroke:var(--line)"/><text x="48" y="50.0" text-anchor="end">0.003</text><text x="54.0" y="270" text-anchor="middle">0</text><text x="136.4" y="270" text-anchor="middle">5</text><text x="218.8" y="270" text-anchor="middle">10</text><text x="301.2" y="270" text-anchor="middle">15</text><text x="383.6" y="270" text-anchor="middle">20</text><text x="466.0" y="270" text-anchor="middle">25</text><text x="260.0" y="290" text-anchor="middle">Index</text><text transform="translate(12 150.0) rotate(-90)" text-anchor="middle">spread</text><text x="466" y="290" text-anchor="end" style="font-style:italic">synthetic</text><polyline points="70.5,125.7 87.0,125.7 103.4,103.8 119.9,91.3 136.4,83.8 152.9,78.8 169.4,99.7 185.8,122.5 202.3,140.3 218.8,154.5 235.3,166.1 251.8,175.7 268.2,185.1 284.7,194.1 301.2,201.9 317.7,208.8 334.2,214.8 350.6,220.2 367.1,225.0 383.6,229.3 400.1,233.2 416.6,236.8 433.0,240.0 449.5,243.0 466.0,245.8" style="fill:none;stroke:var(--c1);stroke-width:2;stroke-linejoin:round"/></svg><p>spread, Python CLI, from examples/repo_term_curve_j.json. Synthetic inputs, not market data.</p></div>

<div class="chart"><svg viewBox="0 0 480 300" role="img" aria-label="financing_df, synthetic data" xmlns="http://www.w3.org/2000/svg" style="font:12px Segoe UI,Arial,sans-serif;fill:currentColor"><text x="54" y="15" style="font-weight:600;font-size:13px">financing_df</text><line x1="54" x2="466" y1="254.0" y2="254.0" style="stroke:var(--line)"/><text x="48" y="258.0" text-anchor="end">0.95</text><line x1="54" x2="466" y1="212.4" y2="212.4" style="stroke:var(--line)"/><text x="48" y="216.4" text-anchor="end">0.96</text><line x1="54" x2="466" y1="170.8" y2="170.8" style="stroke:var(--line)"/><text x="48" y="174.8" text-anchor="end">0.97</text><line x1="54" x2="466" y1="129.2" y2="129.2" style="stroke:var(--line)"/><text x="48" y="133.2" text-anchor="end">0.98</text><line x1="54" x2="466" y1="87.6" y2="87.6" style="stroke:var(--line)"/><text x="48" y="91.6" text-anchor="end">0.99</text><line x1="54" x2="466" y1="46.0" y2="46.0" style="stroke:var(--line)"/><text x="48" y="50.0" text-anchor="end">1</text><text x="54.0" y="270" text-anchor="middle">0</text><text x="136.4" y="270" text-anchor="middle">5</text><text x="218.8" y="270" text-anchor="middle">10</text><text x="301.2" y="270" text-anchor="middle">15</text><text x="383.6" y="270" text-anchor="middle">20</text><text x="466.0" y="270" text-anchor="middle">25</text><text x="260.0" y="290" text-anchor="middle">Index</text><text transform="translate(12 150.0) rotate(-90)" text-anchor="middle">financing_df</text><text x="466" y="290" text-anchor="end" style="font-style:italic">synthetic</text><polyline points="70.5,53.1 87.0,60.1 103.4,67.2 119.9,74.3 136.4,81.4 152.9,88.5 169.4,95.6 185.8,102.7 202.3,109.8 218.8,116.9 235.3,124.0 251.8,131.0 268.2,138.1 284.7,145.1 301.2,152.1 317.7,159.0 334.2,166.0 350.6,173.0 367.1,179.9 383.6,186.8 400.1,193.8 416.6,200.7 433.0,207.6 449.5,214.5 466.0,221.3" style="fill:none;stroke:var(--c1);stroke-width:2;stroke-linejoin:round"/></svg><p>financing_df, Python CLI, from examples/repo_term_curve_j.json. Synthetic inputs, not market data.</p></div>
### `eq.forward.term_financed`

**Synthetic.** Synthetic inputs, not market data.

Input: [`examples/eq_forward_term_financed_j.json`](../../examples/eq_forward_term_financed_j.json). Command: `quantforge batch < examples/eq_forward_term_financed_j.json` (wrap as one line).

| Output | Python value |
|---|---|
| `forward` | `50.79389914716966` |
| `carry` | `0.793899147169661` |
| `carry_factor` | `0.9717032367465726` |
| `financing_df` | `0.9682275311731344` |
| `pv_dividends` | `0.6434037917162647` |



## Four-language agreement

Each CLI built these numbers on its own, from the same input file. Agreement shows only that the four agree. It does not show that they are right, which is what the oracle is for.

| Output | Values | Last value: Java | C++ | Python | Rust | Largest difference, any value |
|---|---|---|---|---|---|---|
| repo.term.curve: pillar_spreads | 4 | 0.0015594894604469695 | 0.0015594894604469695 | 0.0015594894604469695 | 0.0015594894604469695 | 6.94e-18 |
| repo.term.curve: spread | 25 | 0.0015594894604469695 | 0.0015594894604469695 | 0.0015594894604469695 | 0.0015594894604469695 | 6.94e-18 |
| repo.term.curve: financing_df | 25 | 0.9578544061302682 | 0.9578544061302682 | 0.9578544061302682 | 0.9578544061302682 | 0 |
| repo.term.curve: financing_rate | 25 | 0.04400000000000004 | 0.04400000000000004 | 0.04400000000000004 | 0.04400000000000004 | 0 |
| repo.term.curve: forward_financing | 25 | 0.04312244018159768 | 0.04312244018159768 | 0.04312244018159768 | 0.04312244018159768 | 0 |
| repo.term.curve: borrow_fee | 25 | 0.005 | 0.005 | 0.005 | 0.005 | 0 |
| eq.forward.term_financed: forward | 1 | 50.79389914716966 | 50.79389914716966 | 50.79389914716966 | 50.79389914716966 | 0 |
| eq.forward.term_financed: carry | 1 | 0.793899147169661 | 0.793899147169661 | 0.793899147169661 | 0.793899147169661 | 0 |
| eq.forward.term_financed: carry_factor | 1 | 0.9717032367465726 | 0.9717032367465726 | 0.9717032367465726 | 0.9717032367465726 | 0 |
| eq.forward.term_financed: financing_df | 1 | 0.9682275311731344 | 0.9682275311731344 | 0.9682275311731344 | 0.9682275311731344 | 0 |
| eq.forward.term_financed: pv_dividends | 1 | 0.6434037917162647 | 0.6434037917162647 | 0.6434037917162647 | 0.6434037917162647 | 0 |

## Oracle evidence and limits

13 golden cases with status ok in `datasets/golden/stage_j` for `repo.term.curve`, `eq.forward.term_financed`, by `verified_by`:

| Operation: sources | Cases |
|---|---|
| eq.forward.term_financed: hand, reference-computed, quantlib-1.44-interp | 2 |
| eq.forward.term_financed: reference-computed, quantlib-1.44-interp | 3 |
| repo.term.curve: hand, reference-computed, quantlib-1.44-interp | 3 |
| repo.term.curve: reference-computed, quantlib-1.44-interp | 5 |

Limits: one input per operation, synthetic unless labelled real; charts plot output index, not calendar time; the specs are in `specifications/`.
