# H-1 crypto microstructure study: protocol (DRAFT)

Status: draft protocol, 2026-11-18, stage H research lane (Claude, claude-opus-5-5). Writing only; no data row has been read. Plan 14.7 H-1 (Q8 restated). This is a measurement study, not a trading test, so it has no Sharpe threshold; its fixed choices below are set before any data is read and changes are logged as deviations.

**Required label on every result, table and chart:** *crypto venue; not equities or rates.* Item (a) also carries *venue-level proxy; metaorders not observed.* **Aggregates only**: no individual order, trade or book row is published; outputs are per-day or pooled statistics and curves.

## Data and dates

- Kraken public L2 (depth 100) and trades, BTC-USD and ETH-USD, from the QuantForge recorder. Qualifying day as defined in `preregs/H18-01-market-making.md` section 1 (24 hourly files, coverage at least 23.5 h, no gap above 10 min, H-2 checkpoint pass rate at least 99.9%).
- At least 20 qualifying days at the v0.10.0 tag; refreshed at v1.0.0.
- Rule 14.10.6: H-1 uses only days **outside** the H18-01 holdout window. Before any H-1 result or docs page is committed, its date list is checked against every prereg holdout in `research/preregs/` and the check is recorded in the report. If H-1 must ship before 20 non-holdout days exist, it ships with fewer days and says so.

## (a) Concave impact proxy

- Buckets of `b` in {10 s, 60 s, 300 s}. Per bucket: signed trade volume `V` (buyer-initiated minus seller-initiated, from the trade side flag) normalised by the day's mean bucket volume; mid-price change `dm` in basis points.
- Model: `E[dm | V] = c * sign(V) * |V|^delta`, fitted by nonlinear least squares on bucket pairs with `|V|` above the 5th percentile.
- Standard error of `delta`: day-block bootstrap (resample days, 2,000 draws); also the HAC (Newey-West, lag 5 buckets) SE, both reported.
- Reported: `delta` with SE and 95% CI per symbol and bucket; whether the CI lies below 1 (concave). No threshold is a pass/fail; the estimate is published whatever it is.

## (b) Walk-the-book cost curves

- At one-minute snapshots, cost in bps against mid of an immediate market order of notional `N` in {1k, 10k, 100k, 1M} USD per side, walking the recorded depth (100 levels). Orders larger than visible depth are flagged and counted, not extrapolated.
- Reported: median, 90th and 99th percentile cost per notional, symbol and side; time-of-day profile (UTC hour).

## (c) Queue fill simulator bounds

- Queue position is not observed (no order IDs). A passive order placed at time `t` at a price level is assumed at the back of the queue (lower bound) or with only the size depleted since `t` ahead of it (upper bound).
- Fill events: a trade through the level (fills fully) or depletion of the queue ahead by trades at the level (fills by the excess). Cancellations ahead are treated as not advancing the queue in the lower bound and as advancing it in the upper bound.
- Acceptance (14.7): every simulated fill lies within [lower, upper] computed from recorded trade-through and depletion events; a unit test plants a known sequence and checks both bounds exactly.
- Reported: fill probability within 1 s, 10 s, 60 s at touch and touch+1 tick, as a [lower, upper] interval.

## (d) Arrival-price TCA on simulated orders

- Simulated parent orders (TWAP and POV 10%, sizes 10k, 100k, 1M USD, start at a random minute per day with fixed seed 20261118) executed on the simulated lit engine replaying the book.
- Shortfall against arrival mid in bps, decomposed into delay, spread and impact (H-17; sums to total to 1e-10).
- Reported: mean and percentiles per size and algo, pooled over days, with the fill-bound range from (c).

## Outputs

- `research/h1/` report on the 11.3 template sections that apply (identity, data, method, results, limitations, AI assistance); date-list check against holdouts; per-day aggregate CSV only.

## AI assistance

Drafted by Claude (claude-opus-5-5) 2026-11-18. Only file names, sizes and timestamps of the recorded data were listed. Unchecked by a human.
