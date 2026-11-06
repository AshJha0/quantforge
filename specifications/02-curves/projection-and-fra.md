# Projection curves, FRAs, swaps and basis

Spec version 1.0.0. Status: Implemented, not Validated.

Multi-curve means forecasting a rate on one curve and discounting on another. The index is `USD-TERM-3M`, which is synthetic (see `01-core/conventions.md`).

Throughout: `spot` is `core.calendar.add_business_days(as_of, 2)` on `USGS`, as in `ois-curves.md`, and schedules and month steps use `end_of_month` false. A `FRA` end steps from its adjusted start. `months` and `tenor_months` run from 1 to 1200, and `start_months` from 0 to 1200, else `E_INPUT`. No quotes: `E_INPUT`. These operations take an optional `snapshot_id`. `alpha` is `ACT_360` unless stated. Dates use `MODIFIED_FOLLOWING`.

## `rates.projection.bootstrap`

Inputs: `discount` (curve), `index`, `as_of`, `quotes`, `interpolation`. Output: `pillars`.

| Quote `type` | Keys | Start, end, pillar | Model rate |
|---|---|---|---|
| `DEPOSIT` | `months` (3), `rate` | `spot` to `spot + 3M` | `(P(s)/P(e) - 1)/alpha` |
| `FRA` | `start_months`, `rate` | `s = spot + start_months`, `e = s + 3M` | As above |
| `SWAP` | `months`, `rate` | Fixed schedule end | Par rate below |

`P` is the projection curve. The pillar is the end date, and quotes must be in pillar order, else `E_INPUT`. Solve as in `ois-curves.md`, stopping below 1e-13.

## Swap

Fixed leg: annual, `THIRTY_360_BOND`, schedule from `spot` to `spot + months`. Floating leg: quarterly, same dates by `schedules.md`, no payment lag.

`A = sum alpha_i D(e_i)` over fixed periods. `F = sum (P(s_j)/P(e_j) - 1) D(e_j)` over floating periods. Par rate is `F/A`.

The floating forward runs on accrual dates, not on a separate index end date.

`rates.swap.pv`. Inputs: `discount`, `projection`, `trade`: `{index, tenor_months, fixed_rate, notional, side}`. Outputs: `valuation` (`model` `SWAP_DISCOUNTING`, `conventions` the index), `par_rate`. `pv = sign * notional * (F - fixed_rate * A)`, +1 for `PAY`.

## FRA

`rates.fra.pv`. Inputs: `discount`, `projection`, `trade`: `{index, start, fixed_rate, notional, side}`. `e = start + 3M`. Outputs: `valuation` (`model` `FRA_DISCOUNTING`), `forward_rate`.

`F = (P(start)/P(e) - 1)/alpha`, and it settles at `start`, discounted at the forward: `pv = sign * notional * alpha (F - K) / (1 + alpha F) * D(start)`.

`data_version` in these valuations is `null` when no `snapshot_id` is given.

## Tenor basis

`rates.basis.spread`. Inputs: `discount`, `projection`, `index`, `tenor_months`. Output: `spread`: the amount added to an overnight leg to match the term leg, on the quarterly schedule:

`sum (P(s)/P(e) - D(s)/D(e)) D(e)  /  sum alpha D(e)`

## Acceptance

Oracle: replay against QuantLib `DepositRateHelper`, `FraRateHelper`, `SwapRateHelper` with exogenous discounting, and `MakeVanillaSwap`. Measured: pillars within 1e-10; swap and FRA PVs within 1e-2 on 1e6. Basis spread has hand replay only. On an `as_of` that is not a business day QuantLib disagrees with itself: `DepositRateHelper` counts from `as_of`, `SwapRateHelper` adjusts first. So those dates have no outside check here.
