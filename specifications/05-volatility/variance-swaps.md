# Variance swaps: replication and realized variance

Spec version 1.0.0. Status: Specified (stage E, E7, spec B). Rulings: `stage-e-rulings-b.md` E-B3, E-B4, E-B7.

**Plain idea.** A variance swap pays the difference between realised variance and a strike agreed today. Its fair strike can be built from today's option prices: a log contract on the underlying has a payoff whose value is the expected variance, and a log contract can be copied with a strip of out-of-the-money puts and calls, each weighted by about `2/K^2`.

## `vol.varswap.fair_strike`

Inputs: `as_of`, `maturity` (dates), `spot` `S0`, `rate` `r` and `dividend_yield` `q` (flat, continuous, ACT/365F), `put_strikes`, `call_strikes`, `vols` (array of `{strike, vol}`: one Black vol per listed strike), `extension_step` `dk`, `variance_strike` `K_var`, `variance_notional` `N_var` (currency per unit of annualised variance). Time `T = ACT_365F(as_of, maturity)`; `D = e^{-rT}`; `F = S0 e^{(r-q)T}`.

Replication, Demeterfi, Derman, Kamal and Zou [S1], discrete, reference point `S* = S0` (ruling E-B3):

```
f(K) = (2/T) [ (K - S0)/S0 - ln(K/S0) ]
```

Calls: strikes sorted up, with one extra strike `K_max + dk` appended. Puts: strikes sorted down, with one extra strike `K_min - dk` appended. Walking each list in that order, with `s_j = |f(K_{j+1}) - f(K_j)| / |K_{j+1} - K_j|` and `s_{-1} = 0`, the weight on the option struck at `K_j` is `w_j = s_j - s_{j-1}`. The extra strikes carry no option; they only close the last slope. A strike equal to `S0` may appear in both lists and is then held as a put and as a call.

```
Pi           = sum over calls w_j C(K_j) + sum over puts w_j P(K_j)      (Black-Scholes prices: spot S0, r, q, vol of the strike, time T)
fair_variance = (2/T) [ (r - q) T - (F/S0 - 1) ] + Pi / D
fair_vol      = sqrt(fair_variance)
pv            = N_var D (fair_variance - K_var)                            (long variance)
```

Outputs: `fair_variance`, `fair_vol`, `pv`.

Checks, in order: `maturity <= as_of`: `E_INPUT`. An empty strike list, or a repeated strike within one list: `E_INPUT`. A put strike above `S0` or a call strike below `S0`: `E_INPUT`. `vols` not listing each strike of the union exactly once: `E_INPUT`. `S0 <= 0`, a vol `<= 0`, `dk <= 0`, or `K_min - dk <= 0`: `E_DOMAIN`.

## `vol.varswap.realized`

Inputs: `prices` (at least 2, all positive), `periods_per_year` `A`, `variance_strike`, `variance_notional`. With `x_i = ln(p_i / p_{i-1})`, `i = 1..m`:

```
realized_variance = (A/m) sum x_i^2           (no mean removed, divisor m: ruling E-B4)
realized_vol      = sqrt(realized_variance)
payoff            = N_var (realized_variance - K_var)    (at maturity, not discounted)
```

Checks: fewer than 2 prices: `E_INPUT`; a price `<= 0`: `E_DOMAIN`.

## Worked examples

Realized (case `varswap_e-0030`): prices `100, 101, 99.5, 100.25, 102, 101.5`, `A = 252`. Log returns `0.0099503, -0.0149629, 0.0075094, 0.0173057, -0.0049140`; sum of squares `7.02924e-4`; `252/5` of that is `0.0354274`; vol `18.82%`; against a strike of 0.04 on `N_var = 1e6` the payoff is `-4572.61`.

Replication weights, first case (`varswap_e-0001`, `S0 = 100`, `T = 1`, calls `100..150` step 10, `dk = 10`): `f(110) - f(100) = 2 (0.1 - ln 1.1) = 0.0093796`, so `s_0 = 9.3796e-4` and the call at 100 has weight `9.3796e-4`; the next slope `(f(120) - f(110))/10 = 2.5977e-3` gives the call at 110 weight `1.6598e-3`, close to the continuous `2 dK / K^2 = 2 (10)/110^2 = 1.6529e-3`. The goldens include the same smile on strips of step 20, 10, 5 and 2.5 at three maturities; fair vol falls towards the continuous value as the strip gets finer (27.77%, 23.75%, 22.64%, 22.35% at three months).

## Acceptance

Suite `stage_e_b/varswap_e`. `fair_variance`, `fair_vol`, `realized_variance`, `realized_vol`: 1e-12 absolute plus 1e-10 relative (class `simple_analytic` by `output_classes`, ruling E-B14). `pv` and `payoff`: 1e-12 per unit of variance notional plus 1e-10 relative, which is 1e-6 currency on `N_var = 1e6`. Goldens: mpmath at 50 digits. Every `q = 0` replication case is re-priced by QuantLib 1.44 `VarianceSwap` with `ReplicatingVarianceSwapEngine` through `oracle/python/outside_e_b.py` and the map `oracle/CONVENTION_MAP_E_B.md`.

QuantLib's engine writes the drift term as `(2/T)(rT - (e^{rT} - 1))`, which omits `q`; with `q != 0` it is not the value of the log contract on a dividend-paying underlying. This spec keeps `q` (ruling E-B3), and QuantLib's form is a wrong-convention check on the `q != 0` cases. Other checks, each caught: strip not grown at the rate (`Pi` instead of `Pi/D`); realized variance demeaned with divisor `m - 1`.

## Sources

- [S1] Demeterfi, K., Derman, E., Kamal, M. and Zou, J., "A guide to volatility and variance swaps", *Journal of Derivatives* 6(4), 1999, 9-32; also Goldman Sachs Quantitative Strategies Research Notes, "More than you ever wanted to know about volatility swaps", March 1999 (the log contract, the discrete strip and its piecewise-linear weights) (not opened)
- [S2] QuantLib 1.44, `ql/pricingengines/forward/replicatingvarianceswapengine.hpp` (the weight walk and reference point; read by behaviour through the Python wheel, not as source)
- [S3] Carr, P. and Madan, D., "Towards a theory of volatility trading", in *Volatility: New Estimation Techniques for Pricing Derivatives*, Risk Books, 1998, 417-427 (spanning a payoff with options) (not opened)
