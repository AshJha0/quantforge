# Rate futures convexity

Spec version 1.0.0. Status: Specified (stage D).

A futures rate settles daily, a forward does not, so the futures rate sits above the forward. Under Hull-White the gap has a closed form.

## `rates.futures.convexity`

Inputs: `price` (quoted, `100 - 100 x rate`), `start_years` `t`, `end_years` `T`, `sigma`, `mean_reversion` `a`. Outputs: `futures_rate = (100 - price)/100`, `convexity`, `forward_rate = futures_rate - convexity`.

With `d = T - t`, `Bd = (1 - e^{-a d})/a`, `L = (1 - e^{-2 a t})/a`, `Bt = (1 - e^{-a t})/a`, and at `a = 0` their limits `d`, `2t`, `t`:

`z = sigma^2/2 * (L Bd^2 + Bd Bt^2)`

`convexity = (1 - e^{-z}) (futures_rate + 1/d)`

Compute `1 - e^{-z}` as `-expm1(-z)`. This is QuantLib's `HullWhite::convexityBias`. Times are as given.

Checks, in order: `T <= t`: `E_INPUT`. `t < 0`, `sigma < 0`, `a < 0`: `E_DOMAIN`.

## Acceptance

Class `simple_analytic`. QuantLib agrees within 1e-15 plus 1e-12 relative. Suite `stage_d/futures_d`.
