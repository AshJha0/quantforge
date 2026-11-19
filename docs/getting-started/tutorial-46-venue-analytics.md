# Tutorial 46: which venue's fills were good? Markouts, toxicity and fill rates

<!-- tutorial:only python -->

The plain idea: after a fill, watch the mid. If you bought and the mid then rose, the fill was good for you; if it fell, someone who knew more traded with you. Averaged over a venue's fills at a fixed horizon, that is the venue's markout. The share of quantity that went the wrong way is a simple toxicity measure, and filled over sent is the fill rate.

You will compute markouts at two horizons and fill rates for two venues. Budget 10 minutes. The fills are synthetic.

<p class="note">Available from v0.10.0. The operation `exec.venue.analytics` (H-16) is implemented in all four languages; this page restates the spec in plain Python with exact fractions as a hand check. Every number is a golden from <code>specifications/10-execution/venue-analytics.md</code>, hand calculations checked with mpmath by the spec lane; 5 of 5 value cases agree with a second, fresh blind re-derivation (<code>program/STAGE_H_BLIND_MICRO.md</code>). Nothing here is measured on real venue data.</p>

Terms, defined here. `s` is +1 for a buy and -1 for a sell, `q` the fill quantity, `p` its price, `m(u)` the last mid at or before time `u` (ruling HR-72) and `h` the horizon. **Markout** is `sum s q (m(t+h) - p) / sum q`, positive when the fill was good for us; **markout_bps** divides by `sum q p` instead and scales by 10,000; **toxicity** is the share of quantity whose own markout is negative.

## What you need

- A clone of the repository, with commands run from its root.
- [uv](https://docs.astral.sh/uv/): `uv sync --locked --project python`. The script uses the Python standard library only.

## Step 1: check the numbers

<!-- tutorial:run python -->
```python
# Venue markouts, toxicity and fill rates restated from the spec, goldens venue_h-0001, 0002, 0004.
from fractions import Fraction as F

mids = [(0, F("100.00")), (1, F("100.02")), (5, F("100.05")), (10, F("99.98"))]
fills = [("A", 1, 100, F("100.01"), 0), ("A", -1, 200, F("100.03"), 1), ("B", 1, 300, F("100.00"), 1)]
orders = [("A", 500, 300), ("B", 300, 300)]


def mid_at(u):
    return [m for t, m in mids if t <= u][-1]  # last mid at or before u (HR-72)


for h in (5, 10):
    for v in ("A", "B"):
        rows = [(s, q, p, s * (mid_at(t + h) - p)) for venue, s, q, p, t in fills if venue == v]
        pnl = sum(q * e for s, q, p, e in rows)
        qty = sum(q for _, q, _, _ in rows)
        notional = sum(q * p for _, q, p, _ in rows)
        toxic = sum(q for _, q, _, e in rows if e < 0) / qty
        print(f"h {h:2d} venue {v}: markout {float(pnl / qty):.15g} markout_bps {float(pnl / notional * 10000):.15g}"
              f" toxicity {float(toxic):.15g}")
for v in ("A", "B"):
    sent = sum(s for venue, s, _ in orders if venue == v)
    filled = sum(f for venue, _, f in orders if venue == v)
    print(f"venue {v}: fill_rate {float(F(filled, sent)):g}")
```

Output (CI checks these lines):

<!-- tutorial:expect -->
```text
h  5 venue A: markout 0 markout_bps 0 toxicity 0.666666666666667
h  5 venue B: markout 0.05 markout_bps 5 toxicity 0
h 10 venue A: markout 0.0233333333333333 markout_bps 2.33278901589629 toxicity 0.333333333333333
h 10 venue B: markout -0.02 markout_bps -2 toxicity 1
venue A: fill_rate 0.6
venue B: fill_rate 1
```

### Reading the numbers

- **Five seconds.** Venue A's buy of 100 at 100.01 gains 0.04 a share against the mid 100.05 (+4) and its sell of 200 at 100.03 loses 0.02 a share (-4): the markout nets to 0, but two thirds of the quantity went the wrong way, so toxicity is 0.667. Venue B's buy of 300 at 100.00 gains 15, or 5 bp (`venue_h-0001`).
- **Ten seconds.** The mid has fallen to 99.98. A's sell now looks good and its buy bad (+7 net, 2.33 bp, toxicity 1/3); B's buy is now entirely toxic, -2 bp (`venue_h-0002`). The ranking of the two venues flips with the horizon, which is why markouts are always reported at several.
- **Fill rates.** A filled 300 of 500 sent, B all 300 (`venue_h-0004`).

### The formal statement, checked against the spec

From `specifications/10-execution/venue-analytics.md` (available from v0.10.0; rulings HR-72, HR-73).

- Sums and the sign test are exact on the decimals as printed; each output is rounded once to binary64. Without this, A's zero markout at 5 seconds comes out near 5e-15 in binary64.
- Property tests: `markout_bps` has the sign of `markout`; toxicity lies in [0, 1]; reflecting every price and mid about a constant and reversing every side leaves the markout unchanged.
- VPIN is not specified: the worked bucket example in the source paper could not be verified, so it was left out (HR-73).

## For practitioners

- **Mid only.** No microprice and no spread-adjusted variant; a passive fill at the bid starts half a spread ahead against the mid, so compare venues on the same order type.
- **Clock time, not event time.** A quiet market and a busy one look alike at 5 seconds; the spec states this limitation.

## Common mistakes

- **Reading one horizon.** As the example shows, a venue can look best at one horizon and worst at another.
- **Averaging per fill instead of per share.** The spec weights by quantity; one small toxic fill should not count as much as a large good one.

## What you just did

You marked out three synthetic fills at two horizons, saw the venue ranking flip, and computed fill rates.

## Try next

- Add the horizon 0 and predict A's markout before running it; the spec's answer is `venue_h-0003`.

## References and further reading

- This project: the spec above, and the simulated dark pool's own markouts in [Tutorial 43](tutorial-43-dark-pool-and-routing.md); all sources in [References](../references.md).
