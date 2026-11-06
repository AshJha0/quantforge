# Compounding

Spec version 1.0.0. Status: Specified.

A rate means nothing until its compounding is stated. Rates are decimals: 0.05 is 5%, and one basis
point is 0.0001. Time `t` is a year fraction.

`compounding` is one of `SIMPLE`, `CONTINUOUS`, or `PERIODIC` with an integer `frequency` `n` in
{1, 2, 3, 4, 6, 12}.

| Compounding | Discount factor `D(r, t)` | Rate from `D` |
|---|---|---|
| `SIMPLE` | `1 / (1 + r t)` | `(1/D - 1) / t` |
| `PERIODIC` | `(1 + r/n)^(-n t)` | `n (D^(-1/(n t)) - 1)` |
| `CONTINUOUS` | `exp(-r t)` | `-ln(D) / t` |

## Operations

`core.compounding.discount_factor`. Inputs: `rate`, `t`, `compounding`, optional `frequency`.
Output: `discount_factor`.

`core.compounding.convert`. Inputs: `rate`, `t`, `from` and `to`, each an object
`{"compounding": ..., "frequency": ...}`. Output: `rate`. Computes `D` with `from`, then the rate
with `to`.

Checks, in order:
1. `frequency` missing with `PERIODIC`, or not listed: `E_SCHEMA`.
2. `t < 0`: `E_DOMAIN`.
3. `t = 0` in `convert`: `E_DOMAIN`, as the rate is undefined. `discount_factor` at `t = 0` is 1.
4. `SIMPLE` with `1 + r t <= 0`, or `PERIODIC` with `1 + r/n <= 0`: `E_DOMAIN`.

Negative rates are allowed.

## Examples

`D(0.05, 2)` is `1/1.1 = 0.909090909...` simple; `1.025^-4 = 0.905950645...` semi-annual;
`exp(-0.1) = 0.904837418...` continuous.

## Acceptance

Class `simple_analytic`. Oracle: mpmath at 50 digits, QuantLib `InterestRate` as a second check.
