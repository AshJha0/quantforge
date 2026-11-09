# Volatility term structure and forward volatility

<p class="note">Status: Implemented, not Validated. Validation is self-assessment until the human review at the end of the project. Data: synthetic. These are constructed inputs, not market data, and nothing is traded.</p>

Generated on 2026-11-08 from commit `597abf2`, by Java 0.4.0 (JDK 25.0.5+8-LTS), C++ 0.4.2 (GCC 16.2.0), Python 0.4.0 (CPython 3.15.2), Rust 0.4.2 (rustc 1.99.1), on one Windows machine.

## What it is

At-the-money implied volatility by expiry, and the forward volatility between consecutive expiries that `vol.forward.vol` returns. A negative forward variance would mean calendar arbitrage. Stage E, target v0.5.

## Inputs

Four expiries and their volatilities, copied from golden case `lv_e-0007`. Synthetic inputs, not market data. Input: [`examples/vol_forward_term_e.json`](../../examples/vol_forward_term_e.json).

## Command

Build a CLI as in the [Cookbook](../../COOKBOOK.md), then from the repository root:

```bash
rust/target/release/quantforge run < examples/vol_forward_term_e.json
```

Raw numbers: [`docs/curves/data/vol-term-structure.json`](data/vol-term-structure.json).

## Charts

<div class="chart"><svg viewBox="0 0 360 296" role="img" aria-label="Volatility term structure, synthetic data" xmlns="http://www.w3.org/2000/svg" style="font:12px Segoe UI,Arial,sans-serif;fill:currentColor"><text x="0" y="16" style="font-weight:600;font-size:13px">Volatility term structure</text><line x1="46" x2="350" y1="220.0" y2="220.0" style="stroke:var(--line)"/><text x="42" y="224.0" text-anchor="end">0.2</text><line x1="46" x2="350" y1="156.7" y2="156.7" style="stroke:var(--line)"/><text x="42" y="160.7" text-anchor="end">0.21</text><line x1="46" x2="350" y1="93.3" y2="93.3" style="stroke:var(--line)"/><text x="42" y="97.3" text-anchor="end">0.22</text><line x1="46" x2="350" y1="30.0" y2="30.0" style="stroke:var(--line)"/><text x="42" y="34.0" text-anchor="end">0.23</text><text x="46.0" y="235" text-anchor="middle">0</text><text x="122.0" y="235" text-anchor="middle">0.5</text><text x="198.0" y="235" text-anchor="middle">1</text><text x="274.0" y="235" text-anchor="middle">1.5</text><text x="350.0" y="235" text-anchor="middle">2</text><text x="198.0" y="252" text-anchor="middle">Expiry, years</text><text transform="translate(11 125.0) rotate(-90)" text-anchor="middle">Volatility</text><polyline points="76.4,220.0 121.8,156.7 198.0,125.0 350.0,93.3" style="fill:none;stroke:var(--c1);stroke-width:2;stroke-linejoin:round"><title>ATM implied</title></polyline><line x1="46" x2="68" y1="266" y2="266" style="stroke:var(--c1);stroke-width:2;"/><text x="74" y="270">ATM implied</text><polyline points="76.4,220.0 121.8,115.9 198.0,94.2 350.0,62.4" style="fill:none;stroke:var(--c2);stroke-width:2;stroke-linejoin:round"><title>Forward</title></polyline><line x1="46" x2="68" y1="284" y2="284" style="stroke:var(--c2);stroke-width:2;"/><text x="74" y="288">Forward</text></svg><p>Synthetic inputs, not market data. From the Python CLI; exact values are in the tables and data file.</p></div>

## Numbers

| Expiry | ATM vol | Forward vol |
|---|---|---|
| 0.2 | 0.2 | 0.2 |
| 0.49863 | 0.21 | 0.216439 |
| 1 | 0.215 | 0.21986 |
| 2 | 0.22 | 0.224889 |

## Four-language agreement

Each CLI built these numbers on its own, from the same input file. Agreement shows only that the four agree. It does not show that they are right, which is what the oracle is for.

| Output | Values | Last value: Java | C++ | Python | Rust | Largest difference, any value |
|---|---|---|---|---|---|---|
| vol.forward.vol: forward_vols | 4 | 0.2248888614404902 | 0.2248888614404902 | 0.2248888614404902 | 0.2248888614404902 | 0 |

## Oracle evidence and limits

Forward volatility golden cases are checked against QuantLib 1.44 and analytic cases.

7 golden cases with status ok in `datasets/golden/stage_e*/` for `vol.forward.vol`, by `verified_by`:

| Operation: sources | Cases |
|---|---|
| vol.forward.vol: analytic | 1 |
| vol.forward.vol: quantlib-1.44, analytic | 6 |

Limits: one synthetic input, so the page shows the method, not a market. Arbitrage flags are checks at grid points only.

Synthetic inputs, not market data.
