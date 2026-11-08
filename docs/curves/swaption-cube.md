# Swaption volatility cube (SABR)

<p class="note">Status: Implemented, not Validated. Validation is self-assessment until the human review at the end of the project. Data: synthetic. These are constructed inputs, not market data, and nothing is traded.</p>

Generated on 2026-11-08 from commit `597abf2`, by Java 0.4.0 (JDK 25.0.5+8-LTS), C++ 0.4.2 (GCC 16.2.0), Python 0.4.0 (CPython 3.15.2), Rust 0.4.2 (rustc 1.99.1), on one Windows machine.

## What it is

Swaption volatilities from a SABR cube by option expiry, underlying swap tenor and strike: the at-the-money matrix as a heat grid, and smiles for the shortest and longest tenor at a middle expiry. `rates.swaption.price_cube` interpolates the SABR parameters between cube nodes and returns the volatility, forward rate and price of one swaption; the gallery sends one case per expiry, tenor and strike. Stage E, target v0.5.

## Inputs

Discount and projection curves and a four by three SABR cube copied from golden case `ratesvol_e-0001`. Each case changes only the trade: expiry and tenor at the cube nodes, and strike at the forward rate plus -100, -50, 0, 50 and 100 bp, the forward read from a first run of the same case. Synthetic inputs, not market data. Input: [`examples/swaption_cube_e.json`](../../examples/swaption_cube_e.json).

## Command

Build a CLI as in the [Cookbook](../../COOKBOOK.md), then from the repository root:

```bash
rust/target/release/quantforge run < examples/swaption_cube_e.json
```

Raw numbers: [`docs/curves/data/swaption-cube.json`](data/swaption-cube.json).

## Charts

<div class="chart"><svg viewBox="0 0 360 294" role="img" aria-label="ATM black volatility, expiry by tenor, synthetic data" xmlns="http://www.w3.org/2000/svg" style="font:12px Segoe UI,Arial,sans-serif;fill:currentColor"><text x="0" y="16" style="font-weight:600;font-size:13px">ATM black volatility, expiry by tenor</text><text x="42" y="57.8" text-anchor="end">0.5y</text><rect x="46.0" y="30.0" width="101.3" height="47.5" style="fill:var(--c1);fill-opacity:1.00;stroke:var(--bg);stroke-width:.5"><title>0.5y, Swap tenor, years 2: 0.287958</title></rect><rect x="147.3" y="30.0" width="101.3" height="47.5" style="fill:var(--c1);fill-opacity:0.71;stroke:var(--bg);stroke-width:.5"><title>0.5y, Swap tenor, years 5: 0.261853</title></rect><rect x="248.7" y="30.0" width="101.3" height="47.5" style="fill:var(--c1);fill-opacity:0.43;stroke:var(--bg);stroke-width:.5"><title>0.5y, Swap tenor, years 10: 0.237111</title></rect><text x="42" y="105.2" text-anchor="end">1y</text><rect x="46.0" y="77.5" width="101.3" height="47.5" style="fill:var(--c1);fill-opacity:0.98;stroke:var(--bg);stroke-width:.5"><title>1y, Swap tenor, years 2: 0.286176</title></rect><rect x="147.3" y="77.5" width="101.3" height="47.5" style="fill:var(--c1);fill-opacity:0.65;stroke:var(--bg);stroke-width:.5"><title>1y, Swap tenor, years 5: 0.256872</title></rect><rect x="248.7" y="77.5" width="101.3" height="47.5" style="fill:var(--c1);fill-opacity:0.38;stroke:var(--bg);stroke-width:.5"><title>1y, Swap tenor, years 10: 0.232367</title></rect><text x="42" y="152.8" text-anchor="end">2y</text><rect x="46.0" y="125.0" width="101.3" height="47.5" style="fill:var(--c1);fill-opacity:0.77;stroke:var(--bg);stroke-width:.5"><title>2y, Swap tenor, years 2: 0.267675</title></rect><rect x="147.3" y="125.0" width="101.3" height="47.5" style="fill:var(--c1);fill-opacity:0.51;stroke:var(--bg);stroke-width:.5"><title>2y, Swap tenor, years 5: 0.243871</title></rect><rect x="248.7" y="125.0" width="101.3" height="47.5" style="fill:var(--c1);fill-opacity:0.30;stroke:var(--bg);stroke-width:.5"><title>2y, Swap tenor, years 10: 0.225052</title></rect><text x="42" y="200.2" text-anchor="end">5y</text><rect x="46.0" y="172.5" width="101.3" height="47.5" style="fill:var(--c1);fill-opacity:0.36;stroke:var(--bg);stroke-width:.5"><title>5y, Swap tenor, years 2: 0.230292</title></rect><rect x="147.3" y="172.5" width="101.3" height="47.5" style="fill:var(--c1);fill-opacity:0.25;stroke:var(--bg);stroke-width:.5"><title>5y, Swap tenor, years 5: 0.220703</title></rect><rect x="248.7" y="172.5" width="101.3" height="47.5" style="fill:var(--c1);fill-opacity:0.12;stroke:var(--bg);stroke-width:.5"><title>5y, Swap tenor, years 10: 0.208863</title></rect><text x="96.7" y="235" text-anchor="middle">2</text><text x="198.0" y="235" text-anchor="middle">5</text><text x="299.3" y="235" text-anchor="middle">10</text><text x="198.0" y="252" text-anchor="middle">Swap tenor, years</text><rect x="46.0" y="264" width="60.8" height="10" style="fill:var(--c1);fill-opacity:0.12;stroke:var(--line);stroke-width:.5"/><rect x="106.8" y="264" width="60.8" height="10" style="fill:var(--c1);fill-opacity:0.34;stroke:var(--line);stroke-width:.5"/><rect x="167.6" y="264" width="60.8" height="10" style="fill:var(--c1);fill-opacity:0.56;stroke:var(--line);stroke-width:.5"/><rect x="228.4" y="264" width="60.8" height="10" style="fill:var(--c1);fill-opacity:0.78;stroke:var(--line);stroke-width:.5"/><rect x="289.2" y="264" width="60.8" height="10" style="fill:var(--c1);fill-opacity:1.00;stroke:var(--line);stroke-width:.5"/><text x="46" y="288">Vol 0.2089</text><text x="350" y="288" text-anchor="end">0.288</text><text x="198.0" y="288" text-anchor="middle" style="font-style:italic">synthetic</text></svg><p>Synthetic inputs, not market data. From the Python CLI; exact values are in the tables and data file.</p></div>
<div class="chart"><svg viewBox="0 0 360 296" role="img" aria-label="Smiles at 2y expiry, synthetic data" xmlns="http://www.w3.org/2000/svg" style="font:12px Segoe UI,Arial,sans-serif;fill:currentColor"><text x="0" y="16" style="font-weight:600;font-size:13px">Smiles at 2y expiry</text><line x1="46" x2="350" y1="220.0" y2="220.0" style="stroke:var(--line)"/><text x="42" y="224.0" text-anchor="end">0.2</text><line x1="46" x2="350" y1="156.7" y2="156.7" style="stroke:var(--line)"/><text x="42" y="160.7" text-anchor="end">0.25</text><line x1="46" x2="350" y1="93.3" y2="93.3" style="stroke:var(--line)"/><text x="42" y="97.3" text-anchor="end">0.3</text><line x1="46" x2="350" y1="30.0" y2="30.0" style="stroke:var(--line)"/><text x="42" y="34.0" text-anchor="end">0.35</text><text x="46.0" y="235" text-anchor="middle">-100</text><text x="122.0" y="235" text-anchor="middle">-50</text><text x="198.0" y="235" text-anchor="middle">0</text><text x="274.0" y="235" text-anchor="middle">50</text><text x="350.0" y="235" text-anchor="middle">100</text><text x="198.0" y="252" text-anchor="middle">Strike offset, bp</text><text transform="translate(11 125.0) rotate(-90)" text-anchor="middle">Black volatility</text><polyline points="46.0,69.2 122.0,107.2 198.0,134.3 274.0,152.1 350.0,162.3" style="fill:none;stroke:var(--c1);stroke-width:2;stroke-linejoin:round"><title>2y tenor</title></polyline><line x1="46" x2="68" y1="266" y2="266" style="stroke:var(--c1);stroke-width:2;"/><text x="74" y="270">2y tenor</text><polyline points="46.0,138.6 122.0,166.7 198.0,188.3 274.0,204.0 350.0,214.8" style="fill:none;stroke:var(--c2);stroke-width:2;stroke-linejoin:round"><title>10y tenor</title></polyline><line x1="46" x2="68" y1="284" y2="284" style="stroke:var(--c2);stroke-width:2;"/><text x="74" y="288">10y tenor</text></svg><p>Synthetic inputs, not market data. From the Python CLI; exact values are in the tables and data file.</p></div>

## Numbers

At the money:

| Expiry \ tenor | 2y | 5y | 10y |
|---|---|---|---|
| 0.5y | 0.287958 | 0.261853 | 0.237111 |
| 1y | 0.286176 | 0.256872 | 0.232367 |
| 2y | 0.267675 | 0.243871 | 0.225052 |
| 5y | 0.230292 | 0.220703 | 0.208863 |

## Four-language agreement

Each CLI built these numbers on its own, from the same input file. Agreement shows only that the four agree. It does not show that they are right, which is what the oracle is for.

| Output | Values | Last value: Java | C++ | Python | Rust | Largest difference, any value |
|---|---|---|---|---|---|---|
| rates.swaption.price_cube: expiries | 4 | 5.0 | 5.0 | 5.0 | 5.0 | 0 |
| rates.swaption.price_cube: tenors | 3 | 10.0 | 10.0 | 10.0 | 10.0 | 0 |
| rates.swaption.price_cube: strikes | 5 | 100.0 | 100.0 | 100.0 | 100.0 | 0 |
| rates.swaption.price_cube: forward_rates | 12 | 0.04102647589834267 | 0.04102647589834267 | 0.04102647589834267 | 0.04102647589834267 | 0 |
| rates.swaption.price_cube: vols | 60 | 0.18957720383596222 | 0.18957720383596222 | 0.18957720383596222 | 0.18957720383596222 | 0 |

## Oracle evidence and limits

`rates.swaption.price_cube` cases are checked by an independent replay and by 50-digit mpmath arithmetic.

42 golden cases with status ok in `datasets/golden/stage_e*/` for `rates.swaption.price_cube`, by `verified_by`:

| Operation: sources | Cases |
|---|---|
| rates.swaption.price_cube: independent-replay, mpmath-50 | 42 |

Limits: one synthetic input, so the page shows the method, not a market. Arbitrage flags are checks at grid points only.

Synthetic inputs, not market data.
