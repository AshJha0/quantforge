# Hedging against trading costs

<p class="note">Status: Implemented, not Validated. Validation is self-assessment until the human review at the end of the project. Data: synthetic. These are constructed inputs, not market data, and nothing is traded.</p>

Generated on 2026-11-12 from commit `5caedaa`, by Java 0.8.0 (JDK 25.0.5+8-LTS), C++ 0.8.0 (GCC 16.2.0), Python 0.8.0 (CPython 3.15.2), Rust 0.8.0 (rustc 1.99.1), on one Windows machine.

## What it is

A hedge that ignores trading costs can buy small amounts of every instrument. Once each trade pays a half-spread, removing a little risk may cost more than it is worth, and the best hedge leaves some instruments out entirely. This page shows two views of that trade-off. Stage I, target v0.8.0 (`specifications/08-hedging/hedge-costs-and-frontier.md`).

Formally, `hedge.qp.solve` minimises `sum_i w_i (A x + b)_i^2 + c sum_j h_j |x_j|`, risk plus a cost weight `c` times cost, and `hedge.frontier.solve` repeats the solve over a list of cost weights. An instrument held at zero stays there while its risk gradient satisfies `|g_j| <= c h_j`; where the two are equal it is at its switch point, and the answer must be exact there (ruling I-54).

## Inputs

The frontier: five risks, three instruments and seven cost weights from 0 to 50, from [`examples/hedge_frontier_i.json`](../../examples/hedge_frontier_i.json) (a copy of golden case `hedgefrontier_i-0001`). The switch point: the inputs of golden case `hedgecost_i-0023`, two independent risks `b = (-1, -2)` with one instrument each and half-spread 0.5 on instrument 2, with instrument 1's half-spread swept from 0 to 3. All synthetic.

## Command

Build a CLI as in the [Cookbook](../../COOKBOOK.md), then from the repository root:

```bash
rust/target/release/quantforge run < examples/hedge_frontier_i.json
```

Raw numbers: [`docs/curves/data/hedging-costs.json`](data/hedging-costs.json).

## Charts

<div class="chart"><svg viewBox="0 0 360 260" role="img" aria-label="Risk against cost along the frontier, synthetic data" xmlns="http://www.w3.org/2000/svg" style="font:12px Segoe UI,Arial,sans-serif;fill:currentColor"><text x="0" y="16" style="font-weight:600;font-size:13px">Risk against cost along the frontier</text><line x1="46" x2="350" y1="220.0" y2="220.0" style="stroke:var(--line)"/><text x="42" y="224.0" text-anchor="end">8</text><line x1="46" x2="350" y1="156.7" y2="156.7" style="stroke:var(--line)"/><text x="42" y="160.7" text-anchor="end">9</text><line x1="46" x2="350" y1="93.3" y2="93.3" style="stroke:var(--line)"/><text x="42" y="97.3" text-anchor="end">10</text><line x1="46" x2="350" y1="30.0" y2="30.0" style="stroke:var(--line)"/><text x="42" y="34.0" text-anchor="end">11</text><text x="46.0" y="235" text-anchor="middle">0</text><text x="147.3" y="235" text-anchor="middle">0.05</text><text x="248.7" y="235" text-anchor="middle">0.1</text><text x="350.0" y="235" text-anchor="middle">0.15</text><text x="198.0" y="252" text-anchor="middle">Cost</text><text transform="translate(11 125.0) rotate(-90)" text-anchor="middle">Risk</text><polyline points="319.4,174.6 315.0,174.5 310.5,174.4 301.7,174.0 275.1,171.1 230.9,160.7 55.6,44.1" style="fill:none;stroke:var(--c1);stroke-width:2;stroke-linejoin:round"><title>Frontier</title></polyline></svg><p>Synthetic inputs. From the Python CLI; exact values are in the data file.</p></div>

As the cost weight rises the hedge trades less: cost falls and risk rises. The curve is the set of hedges no other hedge beats on both.

<div class="chart"><svg viewBox="0 0 360 296" role="img" aria-label="Holding against instrument 1&#x27;s half-spread, synthetic data" xmlns="http://www.w3.org/2000/svg" style="font:12px Segoe UI,Arial,sans-serif;fill:currentColor"><text x="0" y="16" style="font-weight:600;font-size:13px">Holding against instrument 1&#x27;s half-spread</text><line x1="46" x2="350" y1="220.0" y2="220.0" style="stroke:var(--line)"/><text x="42" y="224.0" text-anchor="end">0</text><line x1="46" x2="350" y1="172.5" y2="172.5" style="stroke:var(--line)"/><text x="42" y="176.5" text-anchor="end">0.5</text><line x1="46" x2="350" y1="125.0" y2="125.0" style="stroke:var(--line)"/><text x="42" y="129.0" text-anchor="end">1</text><line x1="46" x2="350" y1="77.5" y2="77.5" style="stroke:var(--line)"/><text x="42" y="81.5" text-anchor="end">1.5</text><line x1="46" x2="350" y1="30.0" y2="30.0" style="stroke:var(--line)"/><text x="42" y="34.0" text-anchor="end">2</text><text x="46.0" y="235" text-anchor="middle">0</text><text x="147.3" y="235" text-anchor="middle">1</text><text x="248.7" y="235" text-anchor="middle">2</text><text x="350.0" y="235" text-anchor="middle">3</text><text x="198.0" y="252" text-anchor="middle">Half-spread of instrument 1</text><text transform="translate(11 125.0) rotate(-90)" text-anchor="middle">Units held</text><polyline points="46.0,125.0 71.3,136.9 96.7,148.8 122.0,160.6 147.3,172.5 172.7,184.4 198.0,196.2 223.3,208.1 248.7,220.0 274.0,220.0 299.3,220.0 350.0,220.0" style="fill:none;stroke:var(--c1);stroke-width:2;stroke-linejoin:round"><title>Instrument 1</title></polyline><line x1="46" x2="68" y1="266" y2="266" style="stroke:var(--c1);stroke-width:2;"/><text x="74" y="270">Instrument 1</text><polyline points="46.0,53.8 71.3,53.8 96.7,53.8 122.0,53.8 147.3,53.8 172.7,53.8 198.0,53.8 223.3,53.8 248.7,53.8 274.0,53.8 299.3,53.8 350.0,53.8" style="fill:none;stroke:var(--c2);stroke-width:2;stroke-linejoin:round"><title>Instrument 2</title></polyline><line x1="46" x2="68" y1="284" y2="284" style="stroke:var(--c2);stroke-width:2;"/><text x="74" y="288">Instrument 2</text></svg><p>Synthetic inputs. From the Python CLI; exact values are in the data file.</p></div>

Instrument 1's holding is `1 - h/2` while that is positive and exactly 0 from `h = 2`, its switch point; instrument 2 does not move, because the two risks are independent.

## Numbers

Frontier:

| Cost weight | Cost | Risk | x1 | x2 | x3 |
|---|---|---|---|---|---|
| 0.0 | 0.134899 | 8.717443 | 1.238948 | -0.579152 | -0.751805 |
| 0.5 | 0.132715 | 8.717989 | 1.220853 | -0.567184 | -0.747684 |
| 1.0 | 0.130531 | 8.719627 | 1.202758 | -0.555215 | -0.743562 |
| 2.0 | 0.126163 | 8.726179 | 1.166568 | -0.531279 | -0.735320 |
| 5.0 | 0.113059 | 8.772044 | 1.057998 | -0.459469 | -0.710593 |
| 10.0 | 0.091219 | 8.935844 | 0.877047 | -0.339786 | -0.669382 |
| 50.0 | 0.004731 | 10.777312 | 0.000000 | 0.000000 | -0.236559 |

Switch-point sweep:

| Half-spread 1 | x1 | x2 | Objective |
|---|---|---|---|
| 0.0 | 1.000000 | 1.750000 | 0.937500 |
| 0.25 | 0.875000 | 1.750000 | 1.171875 |
| 0.5 | 0.750000 | 1.750000 | 1.375000 |
| 0.75 | 0.625000 | 1.750000 | 1.546875 |
| 1.0 | 0.500000 | 1.750000 | 1.687500 |
| 1.25 | 0.375000 | 1.750000 | 1.796875 |
| 1.5 | 0.250000 | 1.750000 | 1.875000 |
| 1.75 | 0.125000 | 1.750000 | 1.921875 |
| 2.0 | 0.000000 | 1.750000 | 1.937500 |
| 2.25 | 0.000000 | 1.750000 | 1.937500 |
| 2.5 | 0.000000 | 1.750000 | 1.937500 |
| 3.0 | 0.000000 | 1.750000 | 1.937500 |

## Four-language agreement

Each CLI built these numbers on its own. Largest difference between any language and Java over 95 values: 1.8e-15. Agreement shows only that the four agree; the golden comparison below is the check against the oracle.

## Against the golden cases

The Python CLI's result against the golden cases it reproduces (class `root_finding`):

| Golden case | Largest difference |
|---|---|
| `hedgefrontier_i-0001` | 1.8e-15 |
| `hedgecost_i-0023` | 0 |

## Oracle evidence and limits

The golden cases are 50-digit mpmath solves over the sign states with subgradient checks. Outside checks are scipy 1.18 solvers on the same problem (`oracle/outside_register_i.json`):

| Suite | Cases | Outside-checked |
|---|---|---|
| `hedgecost_i` | 23 | 13 |
| `hedgefrontier_i` | 10 | 2 |
| `hedgeqp5_i` | 30 | 29 |

Stage I as a whole: 278 of 443 cases outside-checked, error cases in the denominator (ruling I-2). Limits: linear spread cost and synthetic risks, so the page shows the method, not a desk's costs; the hedge starts from no position.
