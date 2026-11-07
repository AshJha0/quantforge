# Equity dividend, borrow and financing curves

Spec version 1.0.0. Status: Specified (stage D, D5).

Builds on `equity-forward.md` and ruling C2: dividends carry on `C = D/B`, never on `D` alone. Here `B(t) = exp(-b t)` for a flat `borrow_rate` `b`, and a financing spread `s` multiplies `C` by `exp(-s t)`. `t = (d - as_of)/365`, `as_of` the funding curve's.

`F(T) = [S - sum_{as_of < t_i <= T} div_i C(t_i)] / C(T)`.

## `eq.dividend.implied`

Inputs: `spot`, `funding` (curve), `borrow_rate`, `futures` `[{expiry, price}]` (expiries strictly increasing and after `as_of`, else `E_INPUT`). Outputs, per expiry:

- `pv_dividends`: `X(T) = S - F(T) C(T)`, the carry-discounted dividends to `T`
- `period_pv_dividends`: `X(T_1)`, then `X(T_k) - X(T_{k-1})`
- `dividend_yields`: `q(T) = -ln(F(T) C(T)/S)/T`

`spot` or a price `<= 0`: `E_DOMAIN`.

## `eq.borrow.implied`

Inputs: `spot`, `funding`, `dividends` `[{ex_date, amount}]`, `expiry`, `forward`. Output: `borrow_rate`, the `b` with `F(expiry) = forward`. `F` falls as `b` rises, so `b` is unique; solve below 1e-14 in `b`. No solution in `[-0.5, 0.5]`: `E_NOT_BRACKETED`.

## `eq.futures.basis`

Inputs: `spot`, `funding`, `borrow_rate`, `financing_spread`, `dividends`, `expiry`, `futures_price`. Outputs: `fair_price = F(expiry)` with that spread, `basis = futures_price - fair_price`, `implied_financing_spread` (the `s` that makes them equal, unique, as for borrow). `expiry <= as_of`: `E_DATE_ORDER`.

## Acceptance

`simple_analytic`; implied rates `root_finding`, known truth. Suite `stage_d/equity_d`.
