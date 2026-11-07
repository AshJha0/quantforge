# Index dividends, dividend futures, rebalancing, corporate actions, TRS

Spec version 1.0.0. Status: Specified (stage D, D5).

## `eq.index.dividends`

Index dividends against single-stock dividends. Inputs: `divisor`, `constituents` `[{id, shares, price, dividends: [{ex_date, amount}]}]`, `periods` `[{start, end}]`, `implied_period_points` (one per period). Outputs:

- `level = sum shares price / divisor`
- `ex_dates` (sorted, distinct) and `points` on each: `sum shares amount / divisor` over the constituents going ex that day
- `period_points`: points with ex-date in `[start, end]`, both ends included: the fair price of a dividend future on that period, as dividends are known
- `basis = implied_period_points - period_points`

Checks: `divisor <= 0`: `E_DOMAIN`. `end < start`: `E_DATE_ORDER`. Lengths of `periods` and `implied_period_points` differ: `E_INPUT`.

## `eq.index.rebalance`

Inputs: `divisor`, `constituents` `[{id, shares, price}]`, `new_constituents`. The level is continuous: `new_divisor = sum new shares price / level`. Outputs: `level`, `new_divisor`, `weights` (each new constituent's share of new capitalisation). Duplicate `id` in a list: `E_INPUT`.

## `eq.corporate_action.adjust`

Inputs: `action`, `cum_price` `P`, `shares`, `strike`, and per action: `SPLIT`/`REVERSE_SPLIT` `ratio` (new shares per old), `RIGHTS` `new_per_old` `m` and `subscription_price` `K`, `SPECIAL_DIVIDEND` `amount`. Factor `f`: `1/ratio`; rights `TERP/P`, `TERP = (P + m K)/(1 + m)`; special dividend `(P - amount)/P`. Outputs: `factor`, `ex_price = f P`, `adjusted_shares = shares/f`, `adjusted_strike = f strike`. A ratio, `m`, `K` `<= 0`, or `amount >= P` or `<= 0`: `E_DOMAIN`.

## `eq.trs.pv`

Single-period total return swap on `shares` `n`. Inputs: `spot`, `funding`, `borrow_rate`, `dividends`, `trade` `{start, end, initial_price S0, shares, spread, side}`, `current_rate` (required key; a number when `start < as_of`, else `E_INPUT`; may be `null` otherwise). Payment at `end`; dividends with ex-date in `(as_of, end]` are paid at `end`.

`equity_leg = n D(end) [F(end) + sum div - S0]`, with `F` from `equity-curves.md`.
`funding_leg = n S0 (r + spread) alpha D(end)`, `alpha = (end - start)/360`, `r = current_rate` if given, else `(D(start)/D(end) - 1)/alpha`.
`pv = sign (equity_leg - funding_leg)`, +1 for `RECEIVE_EQUITY`.

## Acceptance

Index, rebalance, corporate actions: within 1e-12 relative of exact-rational goldens (`simple_analytic`); `ex_dates` exact. TRS: `simple_analytic`, analytic. Suites `stage_d/index_d`, `trs_d`.
