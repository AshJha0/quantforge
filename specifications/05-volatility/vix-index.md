# VIX-style volatility index from a given option strip

Spec version 1.0.0. Status: Specified (stage E, E7, spec B). Rulings: `stage-e-rulings-b.md` E-B5, E-B6, E-B7, E-B14, E-B15, E-B17.

**Plain idea.** The VIX method is the variance-swap strip of `variance-swaps.md` applied to real quotes: take out-of-the-money option mid prices, weight each by `dK/K^2`, and correct for the at-the-money strike not being exactly the forward. Do it for two expiries around 30 days and interpolate to exactly 30 days. This page follows the Cboe methodology [S1], section 3(a) and 3(b), on a strip the caller gives; it does not choose the expiries or the rate.

## `vol.vix.term_variance`

Inputs: `minutes_to_expiry` `N` (integer), `rate` `R` (continuous), `strip`: array of `{strike, call_bid, call_ask, put_bid, put_ask}`. `T = N / 525600`. Mid `= (bid + ask)/2`, also when the bid is 0. The strip may come in any order; it is sorted by strike.

1. **Forward.** Over the whole strip (zero bids included: [S1] 3(a)(ii) removes only null quotes and bid above ask, which are errors here), the strike `K*` with the smallest `|C_mid - P_mid|`; on a tie the lowest such strike. `F = K* + e^{RT} (C_mid(K*) - P_mid(K*))`.
2. **K0.** The largest strike `<= F` ([S1] 3(a)(ii): "equal to or otherwise immediately below" F). If none: `E_INPUT`.
3. **Selection.** `K0` is used with `Q(K0) = (C_mid + P_mid)/2`. Walking down from `K0` through puts and up from `K0` through calls: an option with bid 0 is skipped; the walk on that side stops at the second consecutive bid of 0, and nothing beyond it is used ([S1] 3(a)(iii); a zero ask implies a zero bid since bid <= ask). If no put, or no call, is selected: `E_INPUT`. Other selected strikes use the out-of-the-money mid (`P_mid` below `K0`, `C_mid` above).
4. **Strike gaps.** Over the selected strikes in order, `dK_i = (K_{i+1} - K_{i-1})/2`; at the lowest and highest selected strike, the gap to the one neighbour ([S1] 3(a)(iv), rulings E-B5, E-B15).
5. **Variance.**

```
variance = (2/T) e^{RT} sum_i (dK_i / K_i^2) Q(K_i)  -  (1/T) (F/K0 - 1)^2      ([S1] formula (1))
```

Outputs: `forward`, `k0`, `variance`, `strikes_used` (ascending).

Checks, in order: a missing or `null` input: `E_SCHEMA`. `N < 1`: `E_INPUT`. Fewer than 3 strikes, or a repeated strike: `E_INPUT`. A bid above its ask: `E_INPUT`. A negative quote: `E_DOMAIN`. No strike at or below `F`: `E_INPUT`. No out-of-the-money put or no out-of-the-money call selected: `E_INPUT`. A negative variance is returned as computed (formula (1) does not forbid it); the index refuses it.

## `vol.vix.index`

Inputs: `near`, `next`, each a `vol.vix.term_variance` input. With `N1`, `N2` their minutes, `N30 = 43200`, `N365 = 525600`, and `T1`, `T2`, `sigma1^2`, `sigma2^2` from step 5:

```
index = 100 sqrt( [ T1 sigma1^2 (N2 - N30)/(N2 - N1) + T2 sigma2^2 (N30 - N1)/(N2 - N1) ] N365 / N30 )
```

Outputs: `index`, `near_variance`, `next_variance`. Checks, in order: unless `N1 < N2` and `N1 <= N30 <= N2`: `E_INPUT` (no extrapolation, ruling E-B6), before either term's own checks (ruling E-B34); then the near term's checks, then the next term's. A negative bracket (variance in time below 0) under the square root: `E_DOMAIN`.

## Worked example (case `vix_e-0001`)

Rate 0, `N = 43200` (`T = 30/365`), five strikes:

| K | call bid/ask | put bid/ask | C mid | P mid |
|---|---|---|---|---|
| 90 | 10.5 / 11.5 | 0.5 / 0.7 | 11.0 | 0.6 |
| 95 | 6.0 / 6.6 | 1.4 / 1.6 | 6.3 | 1.5 |
| 100 | 2.9 / 3.1 | 2.9 / 3.3 | 3.0 | 3.1 |
| 105 | 1.0 / 1.2 | 5.8 / 6.6 | 1.1 | 6.2 |
| 110 | 0.3 / 0.5 | 10.0 / 11.0 | 0.4 | 10.5 |

- Smallest `|C - P|` is 0.1 at 100, so `F = 100 + (3.0 - 3.1) = 99.9` and `K0 = 95`, not 100.
- `Q`: 0.6 at 90 (put), `(6.3 + 1.5)/2 = 3.9` at 95, then calls 3.0, 1.1, 0.4. All `dK = 5`.
- Sum `= 3.7037e-4 + 2.16066e-3 + 1.5e-3 + 4.98866e-4 + 1.65289e-4 = 4.695191e-3`; times `2/T = 24.3333`: `0.1142496`.
- Correction `(1/T)(99.9/95 - 1)^2 = 0.0323681`. Variance `0.0818816`.

Taking `K0 = 100` (the strike above `F`) or dropping the correction both move the result far past tolerance; both are wrong-convention checks.

## Acceptance

Suite `stage_e_b/vix_e`. Variance 1e-12 absolute plus 1e-10 relative (under 1e-5 index points), also inside index cases (`output_classes`, ruling E-B14); index 1e-8 absolute plus 1e-10 relative, far inside the 0.01 to which the index is published. Goldens: strike sums in exact rationals, `exp` and `sqrt` in mpmath; a separate float replay agrees. No outside library implements this method, so the hand case above is the outside reference.

Synthetic strips are Black prices on a skewed smile rounded to 0.05 ticks, with zero bids placed so that the skip rule and the stop rule both change the result. Wrong-convention checks, each caught: `K0` above `F`; no `(F/K0 - 1)^2` correction; `dK` from the full strip instead of the selected strikes; no stop after two zero bids; a 360-day year in minutes.

## Sources

- [S1] Cboe Global Indices, *Cboe Volatility Index Mathematics Methodology*, version 5.0, last revised 26 February 2026, cdn.cboe.com/resources/indices/Cboe_Volatility_Index_Mathematics_Methodology.pdf: section 3(a) single term (formula (1); (ii) forward price and K0; (iii) strike selection, zero bids; (iv) dK), section 3(b) constant-maturity interpolation, minutes in a 365-day year 525,600. Read 2026-11-08. It replaces the older VIX white paper
- [S2] Demeterfi, K., Derman, E., Kamal, M. and Zou, J., "A guide to volatility and variance swaps", *Journal of Derivatives* 6(4), 1999, 9-32 (the strip behind the method) (not opened)

The methodology also derives `R` from Treasury yields (section 2) and picks expiries by rule; those steps are the caller's here, so the caller passes `R` and the two strips.
