# FX spot, forwards and swaps

Spec version 1.0.0. Status: Implemented, not Validated.

A rate of 1.28 for `GBPUSD` means 1 GBP (base) costs 1.28 USD (quote). A forward follows from no-arbitrage between the two currencies' discount curves.

## `fx.spot_date`

Inputs: `pair`, `trade_date`. Output: `spot_date`. Step forward `spot_lag` days, counting only days that are business days on both calendars of the pair. Unknown pair: `E_SCHEMA`.

## Forward

Common inputs: `pair`, `spot` (`<= 0`: `E_DOMAIN`), `as_of`, `base_curve`, `quote_curve`, optional `snapshot_id`. A curve whose `as_of` differs: `E_INPUT`. With `sp` the spot date of `as_of`:

`A(T) = D_base(T)/D_base(sp)`, `B(T) = D_quote(T)/D_quote(sp)`, and `F(T) = S A(T)/B(T)`.

Quoted spot settles on `sp`, which is why both are measured from it.

`fx.forward.outright`. Extra input: `value_date`. Any value date before `sp`, in any `fx.*` operation: `E_DATE_ORDER`. So is `near_date >= far_date`. Outputs: `forward`, `points`, with `points = (F - S)/pip`.

`fx.forward.pv`. Extra input: `trade`: `{notional_base, strike, value_date, side}`, `side` `BUY` or `SELL` of base. Outputs: `valuation` (`pv` in quote currency, `model` `FX_FORWARD_DISCOUNTING`, `conventions` the pair), `fx_delta`.

`pv = sign * N * (F - K) * D_quote(T)`. `fx_delta = dPV/dS = sign * N * (F/S) * D_quote(T)`, in base units, with curves held fixed.

`fx.swap.pv`. Extra input: `trade`: `{notional_base, near_date, near_rate, far_date, far_rate, far_side}`. The near leg has the opposite side to the far leg. Outputs: `valuation` (`model` `FX_SWAP_DISCOUNTING`), `fx_delta`, each the sum of the legs.

## Quote-driven basis

`fx.curve.implied`. Extra input: `points`: `{tenor, points}`, in tenor order, else `E_INPUT`. Tenors are in `M` or `Y`; others are `E_SCHEMA`. Output: `nodes`, each `{value_date, implied_ratio, basis_bp}`.

`value_date` is `sp` plus `tenor` (months, day clipped), `MODIFIED_FOLLOWING` on the pair's first calendar, then moved forward until it is a business day on both calendars. `F = S + points * pip`. `implied_ratio = (F/S) B(T)`: the base growth the quotes imply.

With `tau = (T - sp)/365`: `basis_bp = 10000 (-ln(implied_ratio)/tau + ln(A(T))/tau)`. It is the gap between the FX-implied base rate and the base OIS rate, taken straight from quotes. A curve built from basis swaps is stage D.

## Acceptance

Hand formulas, with forward PV and `fx_delta` also checked against QuantLib `FxForward`, whose source uses the same spot-normalised forward. Spot dates against QuantLib `JointCalendar`.
