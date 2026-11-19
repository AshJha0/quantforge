# Walk-the-book cost curves (crypto venue, recorded)

<p class="note">Stage H, research item H-1(b). H-1 is a pilot only (owner decision 2026-11-18): it ran on the partial days 2026-11-12 to 11-18, recorded at 20 levels, labelled "pilot; partial days; no conclusions" (`research/H1-pilot-2026-11.md`). This page states the method and the data a full study would use; no full-study result exists. Every result, when published, is labelled "crypto venue; not equities or rates" and shows aggregates only.</p>

## What it is

The plain idea: a market order that is bigger than the best quote eats through the book. It takes the best ask, then the next price level, then the next, until it is filled. The average price it pays, compared with the mid, is the cost of trading that size right now. Doing this for many sizes gives a curve of immediate cost against size, read straight off the visible book.

Formally: for a buy of `Q` units against ask levels `(a_1, s_1), (a_2, s_2), ...` (price ascending, size at each), the fill takes `min(s_k, remaining)` at each `a_k` in turn. The average fill price is `p(Q) = sum_k a_k q_k / Q` and the cost in basis points is `(p(Q) / m - 1) x 1e4` against the mid `m`. A sell walks the bids the same way. If `Q` exceeds the depth on the book the cost is undefined for that snapshot and is counted, not extrapolated.

This is the cost of a single market order against the displayed book at one instant. It is not market impact over time (see [impact curves](impact-curves.md)): it ignores hidden orders, the book's refill, and other traders' reaction.

## The data

Kraken spot L2 book, BTC/USD and ETH/USD, recorded locally once a second at 100 levels per side from 2026-11-17 20:15 UTC (20 levels before). See [recorded feeds](../data/recorded-feeds.md) for provenance, terms and holdout checks. The plan requires at least 20 recorded days at the tag (plan 14.7 H-1).

## What will be published

Per symbol, aggregates over the recorded seconds: median and upper quantiles of cost in basis points for a fixed grid of sizes, the share of seconds in which each size exceeded the 100-level depth, and the number of days and seconds used. No raw book data and no per-second rows (venue terms; plan 11.4).

## What it will not show

- One crypto venue's lit book, around the clock. Not equities, not rates, and not a consolidated market.
- Displayed depth only. A real order can do better (hidden liquidity) or worse (the book thins as it is seen).
- Nothing about permanent impact; that is H-1(a), a separate proxy with a standard error.

## Related

The stage J [liquidity cost curve](liquidity.md) is a formula curve with assumed parameters; this page will be its empirical counterpart for one venue. Diagram H-D6 in [Diagrams](../diagrams/README.md#crypto-data-path-recorder-to-aggregate) shows the data path.
