# GBPUSD FX forward curve

<p class="note">Status: Implemented, not Validated. Validation is self-assessment until the human review at the end of the project. Data: synthetic. These are constructed inputs, not market data, and nothing is traded.</p>

Generated on 2026-11-06 from commit `c2379f1`, by Java 0.2.0 (JDK 25.0.5+8-LTS), C++ 0.2.0 (GCC 16.2.0), Python 0.2.0 (CPython 3.15.2), Rust 0.2.0 (rustc 1.99.1), on one Windows machine.

## What it is

A rate of 1.28 means 1 GBP costs 1.28 USD. Holding sterling for a year and holding dollars for a year must come to the same thing once the forward is fixed, so the forward follows from spot and the two discount curves.

Formally: `F(T) = S A(T) / B(T)`, with `A(T) = D_base(T)/D_base(sp)`, `B(T) = D_quote(T)/D_quote(sp)` and `sp` the spot date. Points are `(F - S)/pip`, with a pip of 0.0001. Spec: `specifications/02-curves/fx.md`.

## Inputs

Pair GBPUSD, spot 1.28 (synthetic), as of 2026-11-06, spot date 2026-11-10. Base curve: 13 sterling pillars, the curve on the [SONIA page](sonia-ois.md). Quote curve: 13 dollar pillars, the curve on the [SOFR page](sofr-ois.md). Largest gap between the pillars stored in this file and those pages: 5e-16.

## How to generate it

Input file: [`examples/fx_forward_outright.json`](../../examples/fx_forward_outright.json). Build a CLI as in the [Cookbook](../../COOKBOOK.md), then from the repository root:

```bash
rust/target/release/quantforge run < examples/fx_forward_outright.json
```

The gallery sends this case once per quarterly value date, changing only `value_date`, and sends [`examples/fx_curve_implied.json`](../../examples/fx_curve_implied.json) for the basis. To rebuild every page, with all four CLIs built:

```bash
python tools/build_gallery.py
```

Raw numbers: [`docs/curves/data/gbpusd-fx-forward.json`](data/gbpusd-fx-forward.json).

## Charts

<div class="chart"><svg viewBox="0 0 480 300" role="img" aria-label="GBPUSD forward outright, synthetic data" xmlns="http://www.w3.org/2000/svg" style="font:12px Segoe UI,Arial,sans-serif;fill:currentColor"><text x="54" y="15" style="font-weight:600;font-size:13px">GBPUSD forward outright</text><line x1="54" x2="466" y1="254.0" y2="254.0" style="stroke:var(--line)"/><text x="48" y="258.0" text-anchor="end">1.26</text><line x1="54" x2="466" y1="212.4" y2="212.4" style="stroke:var(--line)"/><text x="48" y="216.4" text-anchor="end">1.27</text><line x1="54" x2="466" y1="170.8" y2="170.8" style="stroke:var(--line)"/><text x="48" y="174.8" text-anchor="end">1.28</text><line x1="54" x2="466" y1="129.2" y2="129.2" style="stroke:var(--line)"/><text x="48" y="133.2" text-anchor="end">1.29</text><line x1="54" x2="466" y1="87.6" y2="87.6" style="stroke:var(--line)"/><text x="48" y="91.6" text-anchor="end">1.3</text><line x1="54" x2="466" y1="46.0" y2="46.0" style="stroke:var(--line)"/><text x="48" y="50.0" text-anchor="end">1.31</text><text x="54.0" y="270" text-anchor="middle">0</text><text x="136.4" y="270" text-anchor="middle">2.5</text><text x="218.8" y="270" text-anchor="middle">5</text><text x="301.2" y="270" text-anchor="middle">7.5</text><text x="383.6" y="270" text-anchor="middle">10</text><text x="466.0" y="270" text-anchor="middle">12.5</text><text x="260.0" y="290" text-anchor="middle">Years from spot date</text><text transform="translate(12 150.0) rotate(-90)" text-anchor="middle">USD per GBP</text><text x="466" y="290" text-anchor="end" style="font-style:italic">synthetic</text><line x1="54" x2="70" y1="29" y2="29" style="stroke:var(--c1);stroke-width:2"/><text x="75" y="33">Curve forward</text><circle cx="172.60000000000002" cy="29" r="4" style="fill:var(--c2)"/><text x="185.60000000000002" y="33">Input quotes</text><polyline points="54.0,170.8 62.3,168.0 70.3,165.3 78.7,162.7 87.0,160.2 95.3,157.6 103.4,155.1 111.7,152.5 120.0,150.0 128.3,147.4 136.4,144.9 144.7,142.4 153.0,139.9 161.3,137.5 169.3,134.9 177.6,132.3 185.9,129.6 194.2,127.0 202.3,124.5 210.6,121.8 218.9,119.4 227.2,116.8 235.3,114.1 243.6,111.4 251.9,108.7 260.2,106.0 268.3,103.3 276.6,100.6 284.9,98.0 293.2,95.5 301.2,92.8 309.6,90.0 317.9,87.2 326.2,84.4 334.2,81.7 342.5,78.9 350.8,76.1 359.1,73.3 367.3,70.6 375.6,67.8 383.9,65.1" style="fill:none;stroke:var(--c1);stroke-width:2;stroke-linejoin:round"/><circle cx="62.3" cy="178.5" r="4" style="fill:var(--c2);stroke:var(--bg);stroke-width:1"><title>3M: -18.5 points</title></circle><circle cx="70.3" cy="185.8" r="4" style="fill:var(--c2);stroke:var(--bg);stroke-width:1"><title>6M: -36.0 points</title></circle><circle cx="87.0" cy="200.3" r="4" style="fill:var(--c2);stroke:var(--bg);stroke-width:1"><title>1Y: -71.0 points</title></circle><circle cx="120.0" cy="229.0" r="4" style="fill:var(--c2);stroke:var(--bg);stroke-width:1"><title>2Y: -140.0 points</title></circle></svg><p>Synthetic inputs, not market data. As of 2026-11-06, spot 1.28. From the Python CLI; exact values are in the tables and data file.</p></div>

<div class="chart"><svg viewBox="0 0 480 300" role="img" aria-label="GBPUSD forward points, synthetic data" xmlns="http://www.w3.org/2000/svg" style="font:12px Segoe UI,Arial,sans-serif;fill:currentColor"><text x="54" y="15" style="font-weight:600;font-size:13px">GBPUSD forward points</text><line x1="54" x2="466" y1="254.0" y2="254.0" style="stroke:var(--line)"/><text x="48" y="258.0" text-anchor="end">-200</text><line x1="54" x2="466" y1="212.4" y2="212.4" style="stroke:var(--line)"/><text x="48" y="216.4" text-anchor="end">-100</text><line x1="54" x2="466" y1="170.8" y2="170.8" style="stroke:var(--line)"/><text x="48" y="174.8" text-anchor="end">0</text><line x1="54" x2="466" y1="129.2" y2="129.2" style="stroke:var(--line)"/><text x="48" y="133.2" text-anchor="end">100</text><line x1="54" x2="466" y1="87.6" y2="87.6" style="stroke:var(--line)"/><text x="48" y="91.6" text-anchor="end">200</text><line x1="54" x2="466" y1="46.0" y2="46.0" style="stroke:var(--line)"/><text x="48" y="50.0" text-anchor="end">300</text><text x="54.0" y="270" text-anchor="middle">0</text><text x="136.4" y="270" text-anchor="middle">2.5</text><text x="218.8" y="270" text-anchor="middle">5</text><text x="301.2" y="270" text-anchor="middle">7.5</text><text x="383.6" y="270" text-anchor="middle">10</text><text x="466.0" y="270" text-anchor="middle">12.5</text><text x="260.0" y="290" text-anchor="middle">Years from spot date</text><text transform="translate(12 150.0) rotate(-90)" text-anchor="middle">Points (pips)</text><text x="466" y="290" text-anchor="end" style="font-style:italic">synthetic</text><line x1="54" x2="70" y1="29" y2="29" style="stroke:var(--c1);stroke-width:2"/><text x="75" y="33">Curve points</text><circle cx="166.4" cy="29" r="4" style="fill:var(--c2)"/><text x="179.4" y="33">Input quotes</text><polyline points="54.0,170.8 62.3,168.0 70.3,165.3 78.7,162.7 87.0,160.2 95.3,157.6 103.4,155.1 111.7,152.5 120.0,150.0 128.3,147.4 136.4,144.9 144.7,142.4 153.0,139.9 161.3,137.5 169.3,134.9 177.6,132.3 185.9,129.6 194.2,127.0 202.3,124.5 210.6,121.8 218.9,119.4 227.2,116.8 235.3,114.1 243.6,111.4 251.9,108.7 260.2,106.0 268.3,103.3 276.6,100.6 284.9,98.0 293.2,95.5 301.2,92.8 309.6,90.0 317.9,87.2 326.2,84.4 334.2,81.7 342.5,78.9 350.8,76.1 359.1,73.3 367.3,70.6 375.6,67.8 383.9,65.1" style="fill:none;stroke:var(--c1);stroke-width:2;stroke-linejoin:round"/><circle cx="62.3" cy="178.5" r="4" style="fill:var(--c2);stroke:var(--bg);stroke-width:1"><title>3M: -18.5 points</title></circle><circle cx="70.3" cy="185.8" r="4" style="fill:var(--c2);stroke:var(--bg);stroke-width:1"><title>6M: -36.0 points</title></circle><circle cx="87.0" cy="200.3" r="4" style="fill:var(--c2);stroke:var(--bg);stroke-width:1"><title>1Y: -71.0 points</title></circle><circle cx="120.0" cy="229.0" r="4" style="fill:var(--c2);stroke:var(--bg);stroke-width:1"><title>2Y: -140.0 points</title></circle></svg><p>Synthetic inputs, not market data. As of 2026-11-06, spot 1.28. From the Python CLI; exact values are in the tables and data file.</p></div>

<div class="chart"><svg viewBox="0 0 480 300" role="img" aria-label="Quote-driven basis, synthetic data" xmlns="http://www.w3.org/2000/svg" style="font:12px Segoe UI,Arial,sans-serif;fill:currentColor"><text x="54" y="15" style="font-weight:600;font-size:13px">Quote-driven basis</text><line x1="54" x2="466" y1="254.0" y2="254.0" style="stroke:var(--line)"/><text x="48" y="258.0" text-anchor="end">0</text><line x1="54" x2="466" y1="202.0" y2="202.0" style="stroke:var(--line)"/><text x="48" y="206.0" text-anchor="end">20</text><line x1="54" x2="466" y1="150.0" y2="150.0" style="stroke:var(--line)"/><text x="48" y="154.0" text-anchor="end">40</text><line x1="54" x2="466" y1="98.0" y2="98.0" style="stroke:var(--line)"/><text x="48" y="102.0" text-anchor="end">60</text><line x1="54" x2="466" y1="46.0" y2="46.0" style="stroke:var(--line)"/><text x="48" y="50.0" text-anchor="end">80</text><text x="54.0" y="270" text-anchor="middle">0</text><text x="136.4" y="270" text-anchor="middle">0.5</text><text x="218.8" y="270" text-anchor="middle">1</text><text x="301.2" y="270" text-anchor="middle">1.5</text><text x="383.6" y="270" text-anchor="middle">2</text><text x="466.0" y="270" text-anchor="middle">2.5</text><text x="260.0" y="290" text-anchor="middle">Years from spot date</text><text transform="translate(12 150.0) rotate(-90)" text-anchor="middle">Basis, bp</text><text x="466" y="290" text-anchor="end" style="font-style:italic">synthetic</text><circle cx="95.5" cy="50.9" r="4" style="fill:var(--c2);stroke:var(--bg);stroke-width:1"><title>2027-02-10</title></circle><circle cx="135.7" cy="52.2" r="4" style="fill:var(--c2);stroke:var(--bg);stroke-width:1"><title>2027-05-10</title></circle><circle cx="218.8" cy="57.7" r="4" style="fill:var(--c2);stroke:var(--bg);stroke-width:1"><title>2027-11-10</title></circle><circle cx="384.1" cy="60.5" r="4" style="fill:var(--c2);stroke:var(--bg);stroke-width:1"><title>2028-11-10</title></circle></svg><p>Synthetic inputs, not market data. As of 2026-11-06, spot 1.28. From the Python CLI; exact values are in the tables and data file.</p></div>

There is no +1 bp chart here: the FX operations take finished curves, so a bump belongs to the curve pages.

## Pillars

Yearly rows from the quarterly grid:

| Value date | Forward | Points |
|---|---|---|
| 2027-11-10 | 1.2825461006120924 | 25.4610 |
| 2028-11-10 | 1.2850081009840248 | 50.0810 |
| 2029-11-10 | 1.2874232979396116 | 74.2330 |
| 2030-11-10 | 1.2898918938444068 | 98.9189 |
| 2031-11-10 | 1.292365496113428 | 123.6550 |
| 2032-11-10 | 1.2949290645548654 | 149.2906 |
| 2033-11-10 | 1.2974922805323859 | 174.9228 |
| 2034-11-10 | 1.3000992491404064 | 200.9925 |
| 2035-11-10 | 1.3027621265952998 | 227.6213 |
| 2036-11-10 | 1.305419814640692 | 254.1981 |

Input forward-point quotes and what they imply:

| Tenor | Value date | Input points | Implied ratio | Basis, bp |
|---|---|---|---|---|
| 3M | 2027-02-10 | -18.5 | 0.9888757910077915 | 78.1286 |
| 6M | 2027-05-10 | -36.0 | 0.9786376943474481 | 77.6002 |
| 1Y | 2027-11-10 | -71.0 | 0.9589647690669594 | 75.4948 |
| 2Y | 2028-11-10 | -140.0 | 0.9223949853893691 | 74.4116 |

## Four-language agreement

Each CLI built these numbers on its own, from the same input file. Agreement shows only that the four agree. It does not show that they are right, which is what the oracle is for.

| Output | Values | Last value: Java | C++ | Python | Rust | Largest difference, any value |
|---|---|---|---|---|---|---|
| Forward outrights | 40 | 1.305419814640692 | 1.305419814640692 | 1.305419814640692 | 1.305419814640692 | 0 |
| Forward points | 40 | 254.1981464069187 | 254.1981464069187 | 254.1981464069187 | 254.1981464069187 | 0 |
| Basis, bp | 4 | 74.4115607204305 | 74.4115607204305 | 74.4115607204305 | 74.4115607204305 | 0 |

## Oracle evidence and limits

Per `specifications/stage-b-rulings.md`, outright points are analytic formulas with no outside library. QuantLib checks the spot dates, implied ratios (`FxSwapRateHelper`), and forward PV and delta (`FxForward`, a different operation from the one charted here). Basis is analytic.

Golden cases for `fx.forward.outright` with an `ok` result: 11, counted from `verified_by` in `datasets/golden/stage_b/`. All four builds passed them locally, which is self-assessment.

| Suite | Verified by | Cases |
|---|---|---|
| fx | hand | 3 |
| fx_deep | hand | 8 |

Limits:

- The value dates charted are plain quarterly dates from spot, some of which may not be business days. `fx.forward.outright` does not require one.
- The input forward points are constructed to exercise the basis calculation. They have the opposite sign to the curve forwards, which is why the basis is near 75 bp. No market is implied.
- Basis here is taken straight from quotes. A curve built from basis swaps is stage D.
