# FX smile and Garman-Kohlhagen vanillas

Spec version 1.0.0. Status: Specified. Stage E, slice E3 (spec A). `stage-e-rulings.md` is normative.

Quote convention: `spot` is domestic currency per unit of foreign (EURUSD 1.0850 is USD per EUR; USD is domestic). Rates are flat continuous: `domestic_rate` `rd`, `foreign_rate` `rf`, any sign. `T = expiry_years`. `F = S e^{(rd-rf)T}`, `Dd = e^{-rd T}`, `Df = e^{-rf T}`. `phi = +1` call, `-1` put. `d1 = ln(F/K)/(v sqrt T) + v sqrt T/2`, `d2 = d1 - v sqrt T`.

Sources:
- [GK83] M. Garman, S. Kohlhagen, "Foreign currency option values", *Journal of International Money and Finance* 2(3), 1983, pp. 231-237.
- [RW12] D. Reiswich, U. Wystup, "FX volatility smile construction", Centre for Practical Quantitative Finance working paper No. 20, 2009 (published in *Wilmott* 2012): section 1.3 (delta types), section 1.4 (ATM types, Table 3), section 1.5 (strike from delta; two strikes for one premium-adjusted call delta, the larger one used). Section numbers checked by the R5 audit (ruling E-A32).
- [Cla11] I. Clark, *Foreign Exchange Option Pricing: A Practitioner's Guide*, Wiley, 2011, chapter 3 (market quotes: ATM, risk reversal, strangle).

Common checks: `spot`, `expiry_years`, `vol`, `strike` (where present), `notional` above 0, else `E_DOMAIN`. Unlisted enum: `E_SCHEMA`.

## `fx.option.price`

Inputs: `spot`, `strike`, `expiry_years`, `domestic_rate`, `foreign_rate`, `vol`, `option_type`, `notional` (foreign units).

Per unit foreign [GK83]: `p = phi Dd (F N(phi d1) - K N(phi d2))`, in domestic currency.

Outputs: `price = notional p` (domestic); `premium_pct_foreign = p/S` (the premium as a fraction of foreign notional); `forward = F`; `delta = notional phi Df N(phi d1)` (spot delta, foreign units); `gamma = notional Df n(d1)/(S v sqrt T)`; `vega = notional S Df n(d1) sqrt T` (per unit vol, domestic).

## Delta types [RW12 section 1.3]

| `delta_type` | Delta |
|---|---|
| `SPOT` | `phi Df N(phi d1)` |
| `FORWARD` | `phi N(phi d1)` |
| `SPOT_PA` | `phi Df (K/F) N(phi d2)` |
| `FORWARD_PA` | `phi (K/F) N(phi d2)` |

PA (premium-adjusted) deltas are for a pair whose premium is paid in foreign currency (USDJPY quoted with USD premium, for example): the hedge is reduced by the premium. Which pairs use which type is a market convention the caller chooses; the library has no pair table (ruling E-A9).

## `fx.delta.from_strike`

Inputs: `spot`, `strike`, `expiry_years`, `domestic_rate`, `foreign_rate`, `vol`, `option_type`. Output `deltas`: object with keys `SPOT`, `FORWARD`, `SPOT_PA`, `FORWARD_PA`.

## `fx.delta.to_strike`

Inputs as above with `delta` and `delta_type` in place of `strike`. Output `strike`, the `K` with delta(`K`) = `delta`.

Range, else `E_DOMAIN`: a call delta must be above 0, a put delta below 0. Non-PA: `|delta|` below `Df` (`SPOT`) or 1 (`FORWARD`). PA put: any negative delta. PA call: delta below the maximum `delta(K*)`, where `K*` solves `v sqrt T N(d2) = n(d2)`, that is `K* = F exp(-v sqrt T d2* - v^2 T/2)`. A PA call delta below the maximum has two strikes; the result is the one above `K*` (ruling E-A10, [RW12 section 1.5]).

Any root finder; the result must match to the stated tolerance.

## `fx.atm.strike`

Inputs: `spot`, `expiry_years`, `domestic_rate`, `foreign_rate`, `vol`, `atm_type`, `delta_type`. Output `strike`:

| `atm_type` | Strike |
|---|---|
| `SPOT` | `S` |
| `FORWARD` | `F` |
| `DNS` (delta-neutral straddle) | `F e^{+v^2 T/2}` for `SPOT`, `FORWARD`; `F e^{-v^2 T/2}` for `SPOT_PA`, `FORWARD_PA` [RW12 section 1.4] |

`delta_type` is required for every `atm_type` and only changes `DNS`.

## `fx.smile.from_quotes`

Inputs: `spot`, `expiry_years`, `domestic_rate`, `foreign_rate`, `atm_vol`, `rr`, `bf`, `delta` (in the open interval `(0, 0.5)`, such as 0.25 or 0.10, else `E_DOMAIN`), `delta_type`, `atm_type`.

`call_vol = atm_vol + bf + rr/2`, `put_vol = atm_vol + bf - rr/2` [Cla11 ch. 3]; a vol `<= 0`: `E_DOMAIN`. `bf` is the smile strangle; the broker (market) strangle needs a fitted smile and is out of scope (ruling E-A11).

Outputs: `atm_strike` (`fx.atm.strike` at `atm_vol`), `call_vol`, `put_vol`, `call_strike` (`fx.delta.to_strike` with `+delta` at `call_vol`), `put_strike` (with `-delta` at `put_vol`).

## Wrong conventions the goldens catch

- domestic and foreign rates swapped; spot delta discounted at `rd`;
- spot delta given as forward delta; premium adjustment omitted;
- PA call strike on the low-strike branch;
- PA DNS with `+v^2 T/2`;
- risk-reversal sign reversed.
