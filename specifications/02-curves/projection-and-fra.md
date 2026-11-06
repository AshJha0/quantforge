# Projection curves, FRAs, swaps and basis

Spec version 1.0.0. Status: Specified.

Multi-curve means forecasting a rate on one curve and discounting on another. The index is `USD-TERM-3M`, which is synthetic (see `01-core/conventions.md`).

Throughout: `spot` is `as_of` plus 2 `USGS` business days. `alpha` is `ACT_360` unless stated. Dates use `MODIFIED_FOLLOWING`.

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

Oracle: replay against QuantLib `DepositRateHelper`, `FraRateHelper`, `SwapRateHelper` with exogenous discounting, and `MakeVanillaSwap`. Measured: pillars within 1.1e-14; swap PVs within 1e-2 on 1e6. FRA PV and basis spread have hand replay only.
