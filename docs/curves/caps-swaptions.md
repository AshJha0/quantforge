# Cap surface and swaption cube

<p class="note">Status: Implemented, not Validated. Validation is self-assessment until the human review at the end of the project. Data: synthetic. These are constructed inputs, not market data, and nothing is traded.</p>

Generated on 2026-11-07 from commit `8dddd58`, by Java 0.4.0 (JDK 25.0.5+8-LTS), C++ 0.4.0 (GCC 16.2.0), Python 0.4.0 (CPython 3.15.2), Rust 0.4.0 (rustc 1.99.1), on one Windows machine.

## What it is

Cap volatilities by strike and expiry, and swaption volatilities by expiry, tenor and strike. The conventions are stylised: a synthetic term index, no fixing lag and an annual 30/360 fixed leg (ruling R1-5). Stage D, target v0.4.

## Runs

Each run is labelled. Synthetic inputs are copied from a golden case's inputs, so they show the method, not a market. Real inputs name their source and date.

### `rates.cap.price`

**Synthetic.** Synthetic inputs, not market data.

Input: [`examples/cap_price_d.json`](../../examples/cap_price_d.json). Command: `quantforge batch < examples/cap_price_d.json` (wrap as one line).

| Output | Python value |
|---|---|
| `price` | `31564.463394283095` |
| `caplets` | 8 values |

<div class="chart"><svg viewBox="0 0 480 300" role="img" aria-label="caplets, synthetic data" xmlns="http://www.w3.org/2000/svg" style="font:12px Segoe UI,Arial,sans-serif;fill:currentColor"><text x="54" y="15" style="font-weight:600;font-size:13px">caplets</text><line x1="54" x2="466" y1="254.0" y2="254.0" style="stroke:var(--line)"/><text x="48" y="258.0" text-anchor="end">1000</text><line x1="54" x2="466" y1="212.4" y2="212.4" style="stroke:var(--line)"/><text x="48" y="216.4" text-anchor="end">2000</text><line x1="54" x2="466" y1="170.8" y2="170.8" style="stroke:var(--line)"/><text x="48" y="174.8" text-anchor="end">3000</text><line x1="54" x2="466" y1="129.2" y2="129.2" style="stroke:var(--line)"/><text x="48" y="133.2" text-anchor="end">4000</text><line x1="54" x2="466" y1="87.6" y2="87.6" style="stroke:var(--line)"/><text x="48" y="91.6" text-anchor="end">5000</text><line x1="54" x2="466" y1="46.0" y2="46.0" style="stroke:var(--line)"/><text x="48" y="50.0" text-anchor="end">6000</text><text x="54.0" y="270" text-anchor="middle">0</text><text x="157.0" y="270" text-anchor="middle">2</text><text x="260.0" y="270" text-anchor="middle">4</text><text x="363.0" y="270" text-anchor="middle">6</text><text x="466.0" y="270" text-anchor="middle">8</text><text x="260.0" y="290" text-anchor="middle">Index</text><text transform="translate(12 150.0) rotate(-90)" text-anchor="middle">caplets</text><text x="466" y="290" text-anchor="end" style="font-style:italic">synthetic</text><polyline points="105.5,95.6 157.0,77.0 208.5,50.6 260.0,225.6 311.5,204.6 363.0,180.9 414.5,159.9 466.0,57.6" style="fill:none;stroke:var(--c1);stroke-width:2;stroke-linejoin:round"/></svg><p>caplets, Python CLI, from examples/cap_price_d.json. Synthetic inputs, not market data.</p></div>
### `rates.swaption.price`

**Synthetic.** Synthetic inputs, not market data.

Input: [`examples/swaption_price_d.json`](../../examples/swaption_price_d.json). Command: `quantforge batch < examples/swaption_price_d.json` (wrap as one line).

| Output | Python value |
|---|---|
| `price` | `106969.44213342645` |
| `forward_rate` | `0.035718133968365824` |
| `annuity` | `4.351040526247382` |



## Four-language agreement

Each CLI built these numbers on its own, from the same input file. Agreement shows only that the four agree. It does not show that they are right, which is what the oracle is for.

| Output | Values | Last value: Java | C++ | Python | Rust | Largest difference, any value |
|---|---|---|---|---|---|---|
| rates.cap.price: price | 1 | 31564.463394283095 | 31564.46339428309 | 31564.463394283095 | 31564.463394283088 | 7.28e-12 |
| rates.cap.price: caplets | 8 | 5721.643587465708 | 5721.643587465708 | 5721.643587465708 | 5721.643587465708 | 1.27e-11 |
| rates.swaption.price: price | 1 | 106969.44213342645 | 106969.44213342645 | 106969.44213342645 | 106969.44213342645 | 0 |
| rates.swaption.price: forward_rate | 1 | 0.035718133968365824 | 0.035718133968365824 | 0.035718133968365824 | 0.035718133968365824 | 0 |
| rates.swaption.price: annuity | 1 | 4.351040526247382 | 4.351040526247382 | 4.351040526247382 | 4.351040526247382 | 0 |

## Oracle evidence and limits

22 golden cases with status ok in `datasets/golden/stage_d` for `rates.cap.price`, `rates.swaption.price`, by `verified_by`:

| Operation: sources | Cases |
|---|---|
| rates.cap.price: independent-replay, quantlib-1.44 | 12 |
| rates.swaption.price: independent-replay, quantlib-1.44 | 10 |

Limits: one input per operation, synthetic unless labelled real; charts plot output index, not calendar time; the stage D specs are in `specifications/`.
