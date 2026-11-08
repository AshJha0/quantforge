# Real data: US Treasury curve with sanity bands

<p class="note">Status: Implemented, not Validated. This page uses <strong>real public data</strong>, unlike the rest of the gallery. USD proxy curve: Treasury par yields bootstrapped with SOFR OIS conventions. Not a SOFR swap curve. Par yields are fitted, not traded: this shows a working pipeline on real inputs, not a tradable curve. Nothing is traded.</p>

Snapshot of 2026-11-06 (fetched 2026-11-07), bootstrapped from commit `3cf8739` by Java 0.4.0, C++ 0.4.1, Python 0.4.0, Rust 0.4.1. Four-language agreement: largest discount-factor gap 1.04e-14. Bands: 12 checks, 0 failed.

## Why bands

The bands in [`tools/workflows/sanity_bands.json`](../../tools/workflows/sanity_bands.json) are wide on purpose. They catch a broken feed, a wrong unit or a failed build, not a market move. The same checks run every business day in workflow (a), `tools/workflows/eod_curves.py`, which writes a dated report to branch `forward-log`.

<div class="chart"><svg viewBox="0 0 480 300" role="img" aria-label="Zero rates against input par yields, synthetic data" xmlns="http://www.w3.org/2000/svg" style="font:12px Segoe UI,Arial,sans-serif;fill:currentColor"><text x="54" y="15" style="font-weight:600;font-size:13px">Zero rates against input par yields</text><line x1="54" x2="466" y1="254.0" y2="254.0" style="stroke:var(--line)"/><text x="48" y="258.0" text-anchor="end">4</text><line x1="54" x2="466" y1="184.7" y2="184.7" style="stroke:var(--line)"/><text x="48" y="188.7" text-anchor="end">4.5</text><line x1="54" x2="466" y1="115.3" y2="115.3" style="stroke:var(--line)"/><text x="48" y="119.3" text-anchor="end">5</text><line x1="54" x2="466" y1="46.0" y2="46.0" style="stroke:var(--line)"/><text x="48" y="50.0" text-anchor="end">5.5</text><text x="54.0" y="270" text-anchor="middle">0</text><text x="157.0" y="270" text-anchor="middle">10</text><text x="260.0" y="270" text-anchor="middle">20</text><text x="363.0" y="270" text-anchor="middle">30</text><text x="466.0" y="270" text-anchor="middle">40</text><text x="260.0" y="290" text-anchor="middle">Years from as-of date</text><text transform="translate(12 150.0) rotate(-90)" text-anchor="middle">Rate, %</text><text x="466" y="290" text-anchor="end" style="font-style:italic">synthetic</text><line x1="54" x2="70" y1="29" y2="29" style="stroke:var(--c1);stroke-width:2"/><text x="75" y="33">Zero rate (cc)</text><circle cx="178.8" cy="29" r="4" style="fill:var(--c2)"/><text x="191.8" y="33">Par yield</text><polyline points="55.1,244.4 55.9,227.7 56.8,223.4 57.6,224.4 59.3,220.6 64.6,213.1 74.9,188.3 85.2,177.3 105.7,170.3 126.4,155.4 157.3,136.8 260.4,61.1 363.5,76.5" style="fill:none;stroke:var(--c1);stroke-width:2;stroke-linejoin:round"/><circle cx="55.1" cy="251.2" r="4" style="fill:var(--c2);stroke:var(--bg);stroke-width:1"><title>1M: 4.02%</title></circle><circle cx="55.9" cy="233.2" r="4" style="fill:var(--c2);stroke:var(--bg);stroke-width:1"><title>2M: 4.15%</title></circle><circle cx="56.8" cy="227.7" r="4" style="fill:var(--c2);stroke:var(--bg);stroke-width:1"><title>3M: 4.19%</title></circle><circle cx="57.6" cy="227.7" r="4" style="fill:var(--c2);stroke:var(--bg);stroke-width:1"><title>4M: 4.19%</title></circle><circle cx="59.3" cy="222.1" r="4" style="fill:var(--c2);stroke:var(--bg);stroke-width:1"><title>6M: 4.23%</title></circle><circle cx="64.6" cy="208.2" r="4" style="fill:var(--c2);stroke:var(--bg);stroke-width:1"><title>1Y: 4.33%</title></circle><circle cx="74.9" cy="183.3" r="4" style="fill:var(--c2);stroke:var(--bg);stroke-width:1"><title>2Y: 4.51%</title></circle><circle cx="85.2" cy="172.2" r="4" style="fill:var(--c2);stroke:var(--bg);stroke-width:1"><title>3Y: 4.59%</title></circle><circle cx="105.7" cy="165.3" r="4" style="fill:var(--c2);stroke:var(--bg);stroke-width:1"><title>5Y: 4.64%</title></circle><circle cx="126.4" cy="151.4" r="4" style="fill:var(--c2);stroke:var(--bg);stroke-width:1"><title>7Y: 4.74%</title></circle><circle cx="157.3" cy="134.7" r="4" style="fill:var(--c2);stroke:var(--bg);stroke-width:1"><title>10Y: 4.86%</title></circle><circle cx="260.4" cy="75.1" r="4" style="fill:var(--c2);stroke:var(--bg);stroke-width:1"><title>20Y: 5.29%</title></circle><circle cx="363.5" cy="79.3" r="4" style="fill:var(--c2);stroke:var(--bg);stroke-width:1"><title>30Y: 5.26%</title></circle></svg><p>Real data: US Treasury par yields, 2026-11-06. USD proxy curve: Treasury par yields bootstrapped with SOFR OIS conventions. Not a SOFR swap curve.</p></div>

<div class="chart"><svg viewBox="0 0 480 300" role="img" aria-label="Forward rate between pillars, synthetic data" xmlns="http://www.w3.org/2000/svg" style="font:12px Segoe UI,Arial,sans-serif;fill:currentColor"><text x="54" y="15" style="font-weight:600;font-size:13px">Forward rate between pillars</text><line x1="54" x2="466" y1="254.0" y2="254.0" style="stroke:var(--line)"/><text x="48" y="258.0" text-anchor="end">4</text><line x1="54" x2="466" y1="202.0" y2="202.0" style="stroke:var(--line)"/><text x="48" y="206.0" text-anchor="end">4.5</text><line x1="54" x2="466" y1="150.0" y2="150.0" style="stroke:var(--line)"/><text x="48" y="154.0" text-anchor="end">5</text><line x1="54" x2="466" y1="98.0" y2="98.0" style="stroke:var(--line)"/><text x="48" y="102.0" text-anchor="end">5.5</text><line x1="54" x2="466" y1="46.0" y2="46.0" style="stroke:var(--line)"/><text x="48" y="50.0" text-anchor="end">6</text><text x="54.0" y="270" text-anchor="middle">0</text><text x="157.0" y="270" text-anchor="middle">10</text><text x="260.0" y="270" text-anchor="middle">20</text><text x="363.0" y="270" text-anchor="middle">30</text><text x="466.0" y="270" text-anchor="middle">40</text><text x="260.0" y="290" text-anchor="middle">Years from as-of date</text><text transform="translate(12 150.0) rotate(-90)" text-anchor="middle">Rate, %</text><text x="466" y="290" text-anchor="end" style="font-style:italic">synthetic</text><polyline points="54.0,246.8 55.1,246.8 55.1,218.3 55.9,218.3 55.9,223.8 56.8,223.8 56.8,234.3 57.6,234.3 57.6,223.2 59.3,223.2 59.3,217.7 64.6,217.7 64.6,185.6 74.9,185.6 74.9,179.8 85.2,179.8 85.2,183.3 105.7,183.3 105.7,152.0 126.4,152.0 126.4,133.6 157.3,133.6 157.3,52.4 260.4,52.4 260.4,143.9 363.5,143.9" style="fill:none;stroke:var(--c1);stroke-width:2;stroke-linejoin:round"/></svg><p>Real data: US Treasury par yields, 2026-11-06. USD proxy curve: Treasury par yields bootstrapped with SOFR OIS conventions. Not a SOFR swap curve.</p></div>

## Pillars

| Pillar | t (y) | Par yield (%) | Discount factor | Zero, cc (%) | Forward to pillar (%) | Day move (bp) |
|---|---|---|---|---|---|---|
| 2026-12-14 | 0.104 | 4.02 | 0.99577272 | 4.0690 | 4.0690 | -1 |
| 2027-01-13 | 0.186 | 4.15 | 0.99222470 | 4.1898 | 4.3428 | +0 |
| 2027-02-12 | 0.268 | 4.19 | 0.98873211 | 4.2205 | 4.2902 | +2 |
| 2027-03-12 | 0.345 | 4.19 | 0.98555978 | 4.2136 | 4.1892 | +3 |
| 2027-05-12 | 0.512 | 4.23 | 0.97850846 | 4.2406 | 4.2964 | +4 |
| 2027-11-15 | 1.025 | 4.33 | 0.95694755 | 4.2948 | 4.3489 | +5 |
| 2028-11-14 | 2.025 | 4.51 | 0.91340181 | 4.4738 | 4.6573 | +5 |
| 2029-11-15 | 3.027 | 4.59 | 0.87123470 | 4.5532 | 4.7135 | +6 |
| 2031-11-13 | 5.022 | 4.64 | 0.79359463 | 4.6035 | 4.6798 | +5 |
| 2033-11-15 | 7.030 | 4.74 | 0.71804960 | 4.7114 | 4.9812 | +4 |
| 2036-11-13 | 10.027 | 4.86 | 0.61519263 | 4.8449 | 5.1582 | +2 |
| 2046-11-15 | 20.038 | 5.29 | 0.33950352 | 5.3910 | 5.9380 | +2 |
| 2056-11-14 | 30.044 | 5.26 | 0.20466555 | 5.2802 | 5.0583 | +1 |

## Band checks

| Check | Level | Result | Detail |
|---|---|---|---|
| Par quotes quote levels | fail | ok | outside band: none |
| Par quotes adjacent tenor gaps | warn | ok | none |
| Par quotes day change | fail | ok | largest 3Y 0.0006 |
| Par quotes day change (warn) | warn | ok | largest 3Y 0.0006 |
| SOFR level | fail | ok | 2026-11-05: 0.0392 |
| SOFR day change | fail | ok | 0.0002 vs 0.01 |
| SOFR day change (warn) | warn | ok | 0.0002 vs 0.0025 |
| Curve discount factors in band | fail | ok | min 0.204666, max 0.995773 |
| Curve discount factors non-increasing | warn | ok | rises after none |
| Curve zero rates in band | fail | ok | min 0.0406902, max 0.0539102 |
| Curve forwards in band | fail | ok | min 0.0406902, max 0.05938 |
| Front end fixing vs shortest quote | warn | ok | -0.001 vs ±0.0075 |

## Limits

- Treasury par yields are bootstrapped as SOFR OIS par rates. The Treasury curve has a different credit, liquidity and day-count basis from SOFR swaps, so these are not SOFR discount factors.
- 1.5-month yields are left out, because the bootstrap takes standard tenors only.
- One date. The daily workflow keeps the history; this page is refreshed by hand with `python tools/build_gallery.py --refresh-real`.

## Data notices

- Source: US Department of the Treasury.
- The SOFR data is subject to the Terms of Use posted at newyorkfed.org. The New York Fed is not responsible for publication of the SOFR data by QuantForge, does not sanction or endorse any particular republication, and has no liability for your use. QuantForge is not affiliated with the New York Fed. The New York Fed does not sanction, endorse, or recommend any products or services offered by QuantForge. The Secured Overnight Financing Rate (SOFR) Data are calculated using data provided under a license granted to the New York Fed by DTCC Solutions LLC ("Solutions"), an affiliate of The Depository Trust & Clearing Corporation. Solutions, its affiliates, and third parties from which they obtained data have no liability for the content of this material.
