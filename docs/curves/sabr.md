# SABR smile, density and arbitrage-free form

<p class="note">Status: Implemented, not Validated. Validation is self-assessment until the human review at the end of the project. Data: synthetic. These are constructed inputs, not market data, and nothing is traded.</p>

Generated on 2026-11-07 from commit `95cbf11`, by Java 0.4.0 (JDK 25.0.5+8-LTS), C++ 0.4.0 (GCC 16.2.0), Python 0.4.0 (CPython 3.15.2), Rust 0.4.0 (rustc 1.99.1), on one Windows machine.

## What it is

SABR is a stochastic-volatility model whose smile has a closed-form approximation, Hagan's formula. The approximation can fail far from the money or at long expiries, where it implies a negative density. A density check finds those strikes, and the arbitrage-free form solves the same model on a numerical grid so that the density cannot go negative.

Formally: Hagan's formula gives the implied volatility from `forward`, `strike`, `expiry`, `alpha`, `beta`, `rho` and `nu`. The density is the second derivative of the call price in strike, taken with a step `h_strike`. The arbitrage-free form uses `cells` grid points, `cells_below` of them below the forward, and `steps` time steps. Spec: `specifications/05-volatility/sabr.md`.

## Inputs

Synthetic inputs, not market data. The input files are:

- [`examples/sabr_hagan.json`](../../examples/sabr_hagan.json)
- [`examples/sabr_density.json`](../../examples/sabr_density.json)
- [`examples/sabr_arbfree.json`](../../examples/sabr_arbfree.json)

They use the parameters of golden cases, so the same numbers are checked against the oracle elsewhere.

## Command

Build a CLI as in the [Cookbook](../../COOKBOOK.md), then from the repository root:

```bash
rust/target/release/quantforge run < examples/sabr_hagan.json
```

To rebuild every gallery page, with all four CLIs built:

```bash
python tools/build_gallery.py
```

Raw numbers: [`docs/curves/data/sabr.json`](data/sabr.json).

## Charts

<div class="chart"><svg viewBox="0 0 480 300" role="img" aria-label="Hagan SABR smile, synthetic data" xmlns="http://www.w3.org/2000/svg" style="font:12px Segoe UI,Arial,sans-serif;fill:currentColor"><text x="54" y="15" style="font-weight:600;font-size:13px">Hagan SABR smile</text><line x1="54" x2="466" y1="254.0" y2="254.0" style="stroke:var(--line)"/><text x="48" y="258.0" text-anchor="end">0.2</text><line x1="54" x2="466" y1="202.0" y2="202.0" style="stroke:var(--line)"/><text x="48" y="206.0" text-anchor="end">0.25</text><line x1="54" x2="466" y1="150.0" y2="150.0" style="stroke:var(--line)"/><text x="48" y="154.0" text-anchor="end">0.3</text><line x1="54" x2="466" y1="98.0" y2="98.0" style="stroke:var(--line)"/><text x="48" y="102.0" text-anchor="end">0.35</text><line x1="54" x2="466" y1="46.0" y2="46.0" style="stroke:var(--line)"/><text x="48" y="50.0" text-anchor="end">0.4</text><text x="54.0" y="270" text-anchor="middle">0.01</text><text x="136.4" y="270" text-anchor="middle">0.02</text><text x="218.8" y="270" text-anchor="middle">0.03</text><text x="301.2" y="270" text-anchor="middle">0.04</text><text x="383.6" y="270" text-anchor="middle">0.05</text><text x="466.0" y="270" text-anchor="middle">0.06</text><text x="260.0" y="290" text-anchor="middle">Strike</text><text transform="translate(12 150.0) rotate(-90)" text-anchor="middle">Implied volatility</text><text x="466" y="290" text-anchor="end" style="font-style:italic">synthetic</text><polyline points="70.5,61.7 95.2,103.1 119.9,136.2 144.6,163.3 169.4,185.5 194.1,203.5 218.8,217.7 243.5,228.4 268.2,236.1 293.0,241.1 317.7,244.1 342.4,245.3 367.1,245.4 391.8,244.7 416.6,243.4 441.3,241.7 466.0,239.7" style="fill:none;stroke:var(--c1);stroke-width:2;stroke-linejoin:round"/></svg><p>Synthetic inputs, not market data. From the Python CLI; exact values are in the tables and data file.</p></div>

<div class="chart"><svg viewBox="0 0 480 300" role="img" aria-label="Hagan density, long expiry, synthetic data" xmlns="http://www.w3.org/2000/svg" style="font:12px Segoe UI,Arial,sans-serif;fill:currentColor"><text x="54" y="15" style="font-weight:600;font-size:13px">Hagan density, long expiry</text><line x1="54" x2="466" y1="254.0" y2="254.0" style="stroke:var(--line)"/><text x="48" y="258.0" text-anchor="end">-200</text><line x1="54" x2="466" y1="212.4" y2="212.4" style="stroke:var(--line)"/><text x="48" y="216.4" text-anchor="end">-150</text><line x1="54" x2="466" y1="170.8" y2="170.8" style="stroke:var(--line)"/><text x="48" y="174.8" text-anchor="end">-100</text><line x1="54" x2="466" y1="129.2" y2="129.2" style="stroke:var(--line)"/><text x="48" y="133.2" text-anchor="end">-50</text><line x1="54" x2="466" y1="87.6" y2="87.6" style="stroke:var(--line)"/><text x="48" y="91.6" text-anchor="end">0</text><line x1="54" x2="466" y1="46.0" y2="46.0" style="stroke:var(--line)"/><text x="48" y="50.0" text-anchor="end">50</text><text x="54.0" y="270" text-anchor="middle">0</text><text x="136.4" y="270" text-anchor="middle">0.01</text><text x="218.8" y="270" text-anchor="middle">0.02</text><text x="301.2" y="270" text-anchor="middle">0.03</text><text x="383.6" y="270" text-anchor="middle">0.04</text><text x="466.0" y="270" text-anchor="middle">0.05</text><text x="260.0" y="290" text-anchor="middle">Strike</text><text transform="translate(12 150.0) rotate(-90)" text-anchor="middle">Density</text><text x="466" y="290" text-anchor="end" style="font-style:italic">synthetic</text><polyline points="58.1,232.8 62.2,201.1 70.5,167.1 87.0,134.7 119.9,107.3 152.9,91.1 218.8,51.2 301.2,71.3 466.0,86.8" style="fill:none;stroke:var(--c1);stroke-width:2;stroke-linejoin:round"/></svg><p>Synthetic inputs, not market data. From the Python CLI; exact values are in the tables and data file.</p></div>

<div class="chart"><svg viewBox="0 0 480 300" role="img" aria-label="Arbitrage-free SABR smile, synthetic data" xmlns="http://www.w3.org/2000/svg" style="font:12px Segoe UI,Arial,sans-serif;fill:currentColor"><text x="54" y="15" style="font-weight:600;font-size:13px">Arbitrage-free SABR smile</text><line x1="54" x2="466" y1="254.0" y2="254.0" style="stroke:var(--line)"/><text x="48" y="258.0" text-anchor="end">0.25</text><line x1="54" x2="466" y1="202.0" y2="202.0" style="stroke:var(--line)"/><text x="48" y="206.0" text-anchor="end">0.3</text><line x1="54" x2="466" y1="150.0" y2="150.0" style="stroke:var(--line)"/><text x="48" y="154.0" text-anchor="end">0.35</text><line x1="54" x2="466" y1="98.0" y2="98.0" style="stroke:var(--line)"/><text x="48" y="102.0" text-anchor="end">0.4</text><line x1="54" x2="466" y1="46.0" y2="46.0" style="stroke:var(--line)"/><text x="48" y="50.0" text-anchor="end">0.45</text><text x="54.0" y="270" text-anchor="middle">0.5</text><text x="191.3" y="270" text-anchor="middle">1</text><text x="328.7" y="270" text-anchor="middle">1.5</text><text x="466.0" y="270" text-anchor="middle">2</text><text x="260.0" y="290" text-anchor="middle">Strike</text><text transform="translate(12 150.0) rotate(-90)" text-anchor="middle">Implied volatility</text><text x="466" y="290" text-anchor="end" style="font-style:italic">synthetic</text><polyline points="54.0,77.5 81.5,112.9 108.9,141.5 136.4,164.9 163.9,184.1 191.3,199.6 218.8,212.1 246.3,221.8 287.5,232.2 328.7,238.6 397.3,243.3 466.0,243.5" style="fill:none;stroke:var(--c1);stroke-width:2;stroke-linejoin:round"/></svg><p>Synthetic inputs, not market data. From the Python CLI; exact values are in the tables and data file.</p></div>

## Numbers

Hagan volatilities:

| Strike | Volatility |
|---|---|
| 0.012 | 0.3848835866995331 |
| 0.015 | 0.3450907067776042 |
| 0.018 | 0.3132312101373863 |
| 0.021 | 0.2872116803720879 |
| 0.024 | 0.2658807994902696 |
| 0.027 | 0.24858490513522943 |
| 0.03 | 0.23492372627921312 |
| 0.033 | 0.22458064100738545 |
| 0.036 | 0.21720450115594048 |
| 0.039 | 0.21236178229663047 |
| 0.042 | 0.2095629701091013 |
| 0.045 | 0.20832630537077312 |
| 0.048 | 0.20823170937759167 |
| 0.051 | 0.20894405962227625 |
| 0.054 | 0.21021126428792442 |
| 0.057 | 0.21185034256686164 |
| 0.06 | 0.21373111846197942 |

Density check (Hagan, 20 years):

| Strike | Density |
|---|---|
| 0.0005 | -174.57449723243258 |
| 0.001 | -136.37248758805592 |
| 0.002 | -95.58399617654727 |
| 0.004 | -56.625225555717584 |
| 0.008 | -23.736961640100777 |
| 0.012 | -4.214178303107302 |
| 0.02 | 43.79727575653039 |
| 0.03 | 19.603041425124598 |
| 0.05 | 0.9313033021195529 |

Minimum density -174.57449723243258; negative density found: True.

Arbitrage-free form:

| Strike | Call price | Volatility |
|---|---|---|
| 0.5 | 0.5060040244406397 | 0.4197159265934692 |
| 0.6 | 0.41274314949012897 | 0.38568285459512297 |
| 0.7 | 0.32490914203569393 | 0.35815772714983657 |
| 0.8 | 0.24515416397650963 | 0.33564864938651257 |
| 0.9 | 0.17620712473493455 | 0.31722871291555466 |
| 1.0 | 0.12013156633591428 | 0.30227200280192856 |
| 1.1 | 0.07760251640425335 | 0.29030776102014993 |
| 1.2 | 0.047637302209191455 | 0.2809367583108969 |
| 1.35 | 0.021148934166029906 | 0.27093747192025397 |
| 1.5 | 0.008787580641447423 | 0.2647692670980877 |
| 1.75 | 0.001923957270174921 | 0.2602696807142938 |
| 2.0 | 0.0004332139065810953 | 0.26005100598966585 |

Mass 0.999999999999998, mean 0.9999999999999978, absorbed 0.0002559617098430114, minimum density 4.9112023424180915e-09.

## Four-language agreement

Each CLI built these numbers on its own, from the same input files. Agreement shows only that the four agree. It does not show that they are right, which is what the oracle is for.

| Output | Values | Last value: Java | C++ | Python | Rust | Largest difference, any value |
|---|---|---|---|---|---|---|
| hagan: vols | 17 | 0.21373111846197942 | 0.21373111846197942 | 0.21373111846197942 | 0.21373111846197942 | 0 |
| density: density | 9 | 0.9313033019243966 | 0.9313033020978689 | 0.9313033021195529 | 0.9313033020978689 | 3.47e-10 |
| density: min_density | 1 | -174.57449723243258 | -174.57449723243258 | -174.57449723243258 | -174.57449723243258 | 0 |
| density: negative_density | 1 | True | True | True | True | 0 |
| arbfree: call_prices | 12 | 0.000433213906581095 | 0.00043321390658109367 | 0.0004332139065810953 | 0.0004332139065810959 | 1.11e-15 |
| arbfree: vols | 12 | 0.26005100598966563 | 0.2600510059896658 | 0.26005100598966585 | 0.2600510059896657 | 1.59e-14 |
| arbfree: mass | 1 | 0.9999999999999961 | 0.9999999999999977 | 0.999999999999998 | 0.9999999999999962 | 1.89e-15 |
| arbfree: mean | 1 | 0.9999999999999967 | 0.9999999999999984 | 0.9999999999999978 | 0.9999999999999967 | 1.78e-15 |
| arbfree: absorbed | 1 | 0.0002559617098430113 | 0.00025596170984301127 | 0.0002559617098430114 | 0.00025596170984301144 | 1.63e-19 |
| arbfree: min_density | 1 | 4.9112023424180915e-09 | 4.9112023424180866e-09 | 4.9112023424180915e-09 | 4.9112023424180915e-09 | 4.96e-24 |

## Oracle evidence and limits

Hagan volatilities are compared with QuantLib 1.44, and with Strata 2.12.78 on 18 of the golden cases. The density has replay cases only. The arbitrage-free form is compared with QuantLib's CEV engine at `nu = 0` and, coarsely, with `NoArbSabrSmileSection`, a different model of the floor. Targets and measured gaps are in `specifications/05-volatility/stage-c-targets.md`.

Golden cases with an `ok` result for `vol.sabr.hagan`, `vol.sabr.density`, `vol.sabr.arbfree`: 32, counted from `verified_by` in `datasets/golden/stage_c/`. All four builds passed them locally, which is self-assessment.

| Verified by | Operation | Cases |
|---|---|---|
| hagan-formula-near, quantlib-1.44-noarbsabr-near | vol.sabr.arbfree | 1 |
| mass-and-mean | vol.sabr.arbfree | 3 |
| quantlib-1.44-cev | vol.sabr.arbfree | 2 |
| analytic-replay | vol.sabr.density | 3 |
| quantlib-1.44 | vol.sabr.hagan | 5 |
| strata-2.12.78, quantlib-1.44 | vol.sabr.hagan | 18 |

Limits:

- The density input is the golden long-expiry case: 20 years, forward 2%. The formula gives a negative density at most of these strikes. That is the point of the chart, and it does not say how SABR behaves at market parameters.
- The arbitrage-free form has a method error against Hagan where Hagan is safe. Mass, mean and absorbed mass are reported, and it is not a fit.
- Three separate inputs with different parameters, so the charts are not comparable with each other.

Synthetic inputs, not market data.
