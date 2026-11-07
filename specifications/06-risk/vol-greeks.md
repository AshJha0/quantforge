# Option Greeks and surface risk

Spec version 1.0.0. Status: Specified. Stage C.

All per unit of option, vol per 1.00 (not per point), time per year. Notation as in `../05-volatility/black-models.md`.

## Analytic

`risk.vol.greeks`. Inputs as `vol.option.price`. `vol <= 0` or `expiry_years <= 0`: `E_DOMAIN`. Outputs: `price`, `delta`, `gamma`, `vega`, `theta`, `rho`, `vanna`, `volga`.

`theta` is `-dV/dT`, other inputs fixed. `vanna = d delta/d vol`, `volga = d vega/d vol`.

| | `BLACK_SCHOLES`, with `Q = exp(-qT)` | `BLACK_76` | `BACHELIER`, `d = (F-K)/(v sqrt T)` |
|---|---|---|---|
| Underlying | Spot | Forward | Forward |
| delta | `Q phi N(phi d1)` | `D phi N(phi d1)` | `D phi N(phi d)` |
| gamma | `Q n(d1)/(S v sqrt T)` | `D n(d1)/(F v sqrt T)` | `D n(d)/(v sqrt T)` |
| vega | `S Q n(d1) sqrt T` | `D F n(d1) sqrt T` | `D sqrt T n(d)` |
| theta | `-S Q n(d1) v/(2 sqrt T) - phi r K D N(phi d2) + phi q S Q N(phi d1)` | `-D F n(d1) v/(2 sqrt T)` | `-D v n(d)/(2 sqrt T)` |
| rho | `phi K T D N(phi d2)` | `-T V` | `-T V` |
| vanna | `-Q n(d1) d2/v` | `-D n(d1) d2/v` | `-D n(d) d/v` |
| volga | `vega d1 d2/v` | `vega d1 d2/v` | `D sqrt T n(d) d^2/v` |

For `BLACK_76` and `BACHELIER`, `theta` holds `D` as a number, so has no `r` term; `rho` is `dV/dr` with `D = exp(-rT)` and `F` fixed. With `shift`, `F` and `K` above are the shifted values.

## Bump and revalue

`risk.vol.bump_greeks`. Inputs as `risk.vol.greeks`. Fixed bumps, on `vol.option.price`: `hu = 1e-4 U`, with `U` the `spot` or `forward` (`1e-4 max(|U|, 1)` for `BACHELIER`; shifted `forward` for a shifted `BLACK_76`), and `hv = 1e-4 v`. Central everywhere:

- `delta = (V(U+hu) - V(U-hu))/(2 hu)`; `gamma = (V(U+hu) - 2V + V(U-hu))/hu^2`
- `vega = (V(v+hv) - V(v-hv))/(2 hv)`; `volga = (V(v+hv) - 2V + V(v-hv))/hv^2`
- `vanna = (V(U+,v+) - V(U+,v-) - V(U-,v+) + V(U-,v-))/(4 hu hv)`

Outputs: those five.

## Equity option

`vol.equity.price`. Inputs: those of `eq.forward.outright`, then `option_type`, `strike`, `vol`, `quantity` (above 0), `side` (`BUY`, `SELL`), `currency`, optional `snapshot_id`. With `T = (expiry - as_of)/365`, Black-76 on `F`, `D(T)`. `T = 0`, `vol <= 0`, `strike <= 0`, `quantity <= 0`: `E_DOMAIN`, after the forward's checks.

Outputs: `valuation` (`model` `BLACK_76_EQUITY`, `conventions` `EQUITY_FORWARD`), `forward`, `delta`, `gamma`, `vega`, with `sign` the side:

`delta = sign q D phi N(phi d1)/C(T)`; `gamma = sign q D n(d1)/(F v sqrt T C(T)^2)`; `vega = sign q D F n(d1) sqrt T`. Dividends and curves held fixed: `dF/dS = 1/C(T)`.

## Surface risk

`risk.vol.surface_vega`. Inputs: `surface`, `positions`, array of `{option_type, forward, strike, discount_factor, expiry_years, quantity}` (signed `quantity`), at most 100.

Each position: Black-76 with vol from `vol.surface.query` at `(expiry_years, ln(strike/forward))`. `pv` is their sum.

`bucket_vega[j][i] = (pv(v[j][i] + 1e-4) - pv(v[j][i] - 1e-4))/2e-4`, one node at a time. `parallel_vega` the same, moving all nodes together. Outputs: `pv`, `bucket_vega`, `parallel_vega`, `bucket_sum`, added in row order. `bucket_sum` agrees with `parallel_vega` only to first order in the spread of node vols, as `w` is not linear in `v`. A node with `vol - 1e-4 <= 0`: `E_DOMAIN`.

## Acceptance

Analytic against bump is a target in `../05-volatility/stage-c-targets.md`. Suites `greeks`, `greeks_deep`.
