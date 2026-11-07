# Use cases 1 to 3

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

## Use case 3: `usecase.vol_surface`

Added in stage C. Inputs: `as_of`, `funding_curve`, `slices`, array of `{expiry, quotes}`, in expiry order, with `quotes` as `eq.forward.parity`; `k_grid`; `target`: `{option_type, strike, expiry, quantity, side}`; `currency`.

1. Per slice, `T = (expiry - as_of)/365`, `D = funding_curve(expiry)`, and `F` from `eq.forward.parity` with that `D`.
2. Per strike, the mid of the out-of-the-money option (call if `K >= F`, else put), inverted with `BLACK_76` on `F`, `D`, gives `w = v^2 T` at `k = ln(K/F)`.
3. Per slice, `vol.svi.calibrate` on `(k, w)`, unweighted.
4. A surface on `k_grid` and the slices' times from the fitted SVI, and `vol.surface.check`.
5. `target.expiry` must be a slice's, else `E_INPUT`. Vol from that slice's SVI at `ln(strike/F)`. Black-76 on `F`, `D`, with side and quantity as `vol.equity.price`. Here `delta` is against the forward: `sign q D phi N(phi d1)`.

Outputs: `forwards`, `svi_rmse`, `arbitrage_free`, `vol`, `valuation` (`model` `BLACK_76_EQUITY`, `conventions` `EQUITY_FORWARD`), `delta`, `vega`.

## Acceptance

Limits are in `stage-b-targets.md`. Oracle: replay built on parts that are checked against QuantLib. Use case 1's book PV and delta are checked against QuantLib `FxForward`. The hedge sums, and use case 2's, have no outside source. Trades, hedges and costs are calculations on synthetic data: nothing is traded. Real output is in `examples/README.md`.

## Sources

Added in R1 (v0.4.1) to meet plan 11.2.4 and 11.5. These are references only: they do not change any rule above. "(not opened)" means the reference was checked from memory for this backfill, not re-read; section numbers are given only where known.

- [S1] Hull, J. C., *Options, Futures, and Other Derivatives*, 10th ed., Pearson, 2018, chapters "Hedging Strategies Using Futures" and "Swaps" (not opened)
