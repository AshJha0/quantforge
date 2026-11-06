# Units and money

Spec version 1.0.0. Status: Specified.

A bare number invites mistakes: is 5 a percent or a decimal, and in which currency? Each implementation has distinct types for rates, basis points and money, and converts only at the edges. Inside the libraries a rate is a decimal, so 0.05 is 5%.

## `core.units.convert`

Inputs: `value` (real), `from`, `to`, each `DECIMAL`, `PERCENT` or `BP`. Output: `value`. 1 = 100 `PERCENT` = 10,000 `BP`.

## Money

An amount is a decimal string, exact, never binary: `^-?[0-9]{1,18}(\.[0-9]{1,8})?$`. More digits than that is `E_LIMIT`; any other form, such as `1e3`, is `E_SCHEMA`. Calculations such as PVs stay in binary64, and become money only when rounded at a boundary.

Currencies and minor units: `GBP`, `USD`, `EUR` have 2 places, `JPY` has 0. Others are `E_SCHEMA`.

`core.units.add_money`. Inputs: `a`, `b`, each `{amount, currency}`. Outputs: `amount`, `currency`. Different currencies: `E_CURRENCY_MISMATCH`.

`core.units.round_money`. Inputs: `amount`, `currency`. Outputs: `amount`, `currency`. Rounds half to even, at the currency's minor unit.

Output form: no trailing zeros are required by `add_money`, which writes the shortest form: `1.50 + -1.5` is `0`, `0.1 + 0.2` is `0.3`. `round_money` writes exactly the minor-unit places. There is no `-0`.

## Acceptance

Exact. Oracle: Python `decimal`, and hand cases.
