# Use cases 1 and 2

Spec version 1.0.0. Status: Implemented, not Validated. All data in the cases is synthetic.

Each use case runs a slice from market data to a hedge, by composing other specs. Nothing new is defined here but the sums.

## Use case 1: `usecase.fx_hedge`

Inputs: `pair`, `spot`, `as_of`, `base_curve`, `quote_curve`, `book` (array of `fx.forward.pv` trades), `half_spread` (price units, at least 0, else `E_DOMAIN`).

Outputs: `pv` and `fx_delta`, sums over `book`; `hedge_spot_base = -fx_delta`, spot base units to trade; `residual_delta`, which is 0 by construction, as a spot trade has delta 1; `hedge_cost = |hedge_spot_base| * half_spread`.

## Use case 2: `usecase.rates_hedge`

Inputs: `as_of`, `quotes`, `interpolation`, `trade` (OIS, as `risk.ois.dv01`), `hedge_tenors`, `hedge_unit_notional`, `half_spread_bp` (at least 0).

1. Build the curve from `quotes`. `pv` from `rates.ois.pv`.
2. `dv01`, `key_rate` from `risk.ois.dv01`.
3. Each hedge is a `PAY` par OIS of its tenor, `hedge_unit_notional`, `fixed_rate` its par rate. Column `c_h` is its `key_rate`.
4. `hedge_units` is the least-squares solution of `min |C x + key_rate|^2`, as `hedge.solve` with unit weights and no cost.
5. `residual_key_rate = C x + key_rate`.
6. `hedge_cost = sum |x_h| * |sum(c_h)| * half_spread_bp`.

The hedges must have key-rate exposure in the trade's buckets. In the golden case a 6Y trade, off the quoted tenors, is hedged with 5Y and 7Y. A 7Y trade hedged with 5Y and 10Y has no overlap, so this method gives units of zero, correctly: par-quote buckets do not reach across tenors.

## Acceptance

Limits are in `stage-b-targets.md`. Oracle: replay built on parts that are checked against QuantLib. The use-case sums have no outside source. Trades, hedges and costs are calculations on synthetic data: nothing is traded. Real output is in `examples/README.md`.
