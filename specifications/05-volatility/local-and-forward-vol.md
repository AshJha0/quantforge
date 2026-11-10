# Local vol, forward vol, smile dynamics, vol of vol

Spec version 1.0.0. Status: Specified. Stage E, slice E1 (spec A). `stage-e-rulings.md` is normative.

Notation as `arb-free-surfaces.md`: `k = ln(K/F(T))`, `w = sigma^2 T`, `slices` the SVI slice object with its checks.

Sources:
- [Dup94] B. Dupire, "Pricing with a smile", *Risk* 7(1), 1994, pp. 18-20 (not opened).
- [Gat06] J. Gatheral, *The Volatility Surface*, Wiley, 2006, chapter 1, equation (1.10): local variance in total-variance form (not opened; the formula is checked here by a 40-digit price-based Dupire).
- [GJ14] as `arb-free-surfaces.md`, equation (2.1), the function `g`.
- [Der99] E. Derman, "Regimes of volatility", *Risk* 12(4), 1999, pp. 55-59: sticky-strike and sticky-delta (sticky-moneyness) regimes (not opened).
- [Hull] J. Hull, *Options, Futures, and Other Derivatives*, 10th ed., Pearson, 2018, chapter "Volatility Smiles and Volatility Surfaces" (volatility term structure; variance is additive over time) (not opened; 10th edition as every other spec).

## Surface between slices (ruling E-A4)

For a time `T` and log-moneyness `k`, with slices at `T_1 < ... < T_n` and `w_j(k)` the raw SVI value of slice `j`:

- `T < T_1`, or `T >= T_n`, or `n = 1`: `w = w_j(k) T/T_j` with `j = 1` if `T < T_1`, else `j = n`; so implied vol is flat in `T` at fixed `k`. Then `w_T = w_j(k)/T_j`.
- Otherwise take the `j` with `T_j <= T < T_{j+1}` (a node uses the interval to its right), `lambda = (T - T_j)/(T_{j+1} - T_j)`, `w = (1-lambda) w_j + lambda w_{j+1}`, and `w_T = (w_{j+1}(k) - w_j(k))/(T_{j+1} - T_j)`.

`w_k` and `w_kk` use the same weights on the slices' analytic `w'` and `w''` (`smile-and-surface.md`). Interpolation is at fixed forward log-moneyness, as the stage C grid surface.

## `vol.local.dupire`

Inputs: `slices`, `points` (array of `{expiry_years, log_moneyness}`, at least 1, else `E_INPUT`; at most 10,000, else `E_LIMIT`). A point with `expiry_years <= 0`: `E_DOMAIN`.

At each point, with `w, w_k, w_kk, w_T` from the rule above:

`g = (1 - k w_k/(2w))^2 - (w_k^2/4)(1/w + 1/4) + w_kk/2`,

`local_vol = sqrt(w_T / g)`.

This is Dupire's local variance [Dup94] in Gatheral's total-variance form [Gat06, eq. 1.10]: the denominator expands to `1 - (k/w) w_k + (1/4)(-1/4 - 1/w + k^2/w^2) w_k^2 + (1/2) w_kk`, which equals `g`. In `k` at the forward, rates and dividend yields do not appear: a caller with strike `K` and flat `r`, `q` uses `k = ln(K/(S e^{(r-q)T}))`.

If `w_T <= 0` (calendar arbitrage) or `g <= 0` (butterfly arbitrage) at any point: `E_ARBITRAGE`. No point is skipped.

Outputs, arrays in point order: `total_variance`, `implied_vol` (`sqrt(w/T)`), `local_vol`.

## `vol.forward.vol`

Inputs: `expiry_years` (strictly increasing, at least 1, else `E_INPUT`; the first above 0, else `E_DOMAIN`, ruling E-A36; at most 100, else `E_LIMIT`), `vols` (same length, else `E_INPUT`; each above 0, else `E_DOMAIN`). Vols are at one fixed moneyness (for example ATM forward).

Output `forward_vols`: `forward_vols[0] = vols[0]`, and for `i >= 1`

`forward_vols[i] = sqrt((vols[i]^2 T_i - vols[i-1]^2 T_{i-1}) / (T_i - T_{i-1}))` [Hull].

A negative radicand is calendar arbitrage: `E_ARBITRAGE`. Zero is allowed and gives 0 (ruling E-A5).

## `vol.smile.dynamics`

How a smile moves when spot moves from `spot` to `spot_shifted`, at fixed expiry.

Inputs: `svi` (one slice at `expiry_years`, in `k` against the base forward), `expiry_years` (> 0), `spot`, `spot_shifted` (> 0), `rate`, `dividend_yield` (continuous, any sign), `strikes` (at least 1, else `E_INPUT`; each > 0, else `E_DOMAIN`), `rule` (`STICKY_STRIKE` or `STICKY_DELTA`), `option_type` (`CALL`, `PUT`). Errors in input order: `E_INPUT` before `E_DOMAIN`.

With `F(S) = S e^{(r-q)T}`, `D = e^{-rT}`, `F0 = F(spot)`, `F1 = F(spot_shifted)`:

- base vol at strike `K`: `v0(K) = sqrt(w(ln(K/F0))/T)`;
- `STICKY_STRIKE`: `v1(K) = v0(K)` [Der99];
- `STICKY_DELTA`: `v1(K) = sqrt(w(ln(K/F1))/T)`. The smile is fixed in forward moneyness. At fixed expiry this is the same as fixing it in forward Black delta without premium adjustment, since that delta is a function of `k` alone once the smile is (ruling E-A6).

Prices are Black on the forward: `D (F N(d1) - K N(d2))` for a call, `D (K N(-d2) - F N(-d1))` for a put, `d1 = ln(F/K)/(v sqrt T) + v sqrt T/2`.

`deltas` are smile-consistent spot deltas at the base spot: `delta = Delta_BS + vega * dv/dS`, with `Delta_BS = e^{-qT} N(d1)` (call) or `-e^{-qT} N(-d1)` (put), `vega = S e^{-qT} n(d1) sqrt T`, and `dv/dS = 0` for `STICKY_STRIKE`, `dv/dS = -(w'(k)/(2 v0 T))/S` for `STICKY_DELTA`.

Outputs, arrays in strike order: `vols_base`, `vols_shifted`, `prices_base` (at `spot`, `v0`), `prices_shifted` (at `spot_shifted`, `v1`), `deltas`.

## `vol.volofvol.measure`

Inputs: `vols` (a time series of one implied vol, oldest first, at least 3, else `E_INPUT`; at most 10,000, else `E_LIMIT`, which lifts the stage C cap of 100 for this list (ruling E-A35); each > 0, else `E_DOMAIN`), `periods_per_year` (> 0, else `E_DOMAIN`), `method` (`LOG` or `ABSOLUTE`).

Changes `x_i = ln(v_i/v_{i-1})` (`LOG`) or `v_i - v_{i-1}` (`ABSOLUTE`). Outputs: `mean_change` (mean of `x`, not annualised) and `vol_of_vol = sqrt(periods_per_year) * s`, with `s` the sample standard deviation, divisor `n - 1` (ruling E-A7).

## Wrong conventions the goldens catch

- local variance `w_T` alone (smile terms dropped);
- left-hand `w_T` at a node;
- forward vol linear in vol rather than in variance;
- sticky delta on spot moneyness `K/S` instead of `K/F`;
- sticky-delta delta without the smile term;
- vol of vol with divisor `n`, or not annualised.

## Continuity at slice expiries (stage F, plan item R10)

Ruling `stage-f-rulings.md` F-17. Suite `stage_f/lvc_f`. Nothing above changes: this section states, and the goldens pin, how the surface behaves at each slice expiry `T_j`, including the short end `T_1`.

**What is continuous.** At fixed `k`, `w(T, k)` is continuous in `T` everywhere (both sides of `T_j` give `w_j(k)`), and so are `implied_vol`, `w_k` and `w_kk`. Within each open interval `(0, T_1)`, `(T_j, T_{j+1})` and `(T_n, infinity)` local vol is continuous (smooth) in `T` and `k`.

**What jumps, and by how much.** `w_T` is piecewise constant in `T` at fixed `k`, so local vol jumps at every slice expiry. At `T_1` (the short end) the left value uses the flat-vol extrapolation and the right value the first interval:

```
left  w_T(T_1-) = w_1(k) / T_1
right w_T(T_1+) = (w_2(k) - w_1(k)) / (T_2 - T_1)        (n >= 2)
local_vol(T_1-) = sqrt(w_T(T_1-) / g(T_1, k)),  local_vol(T_1+) = sqrt(w_T(T_1+) / g(T_1, k))
```

and at an inner `T_j` the two neighbouring interval slopes. `g` is the same on both sides (it uses only `w`, `w_k`, `w_kk`). The jump is zero only where the slopes agree, for example when all slices have the same implied vol at that `k` and the interval slopes equal `w_j/T_j`. A node itself uses the interval to its right (ruling E-A4), so the value at `T_j` equals the right limit.

**Why not smooth it here.** A C1 interpolation in `T` (for example monotone cubic in `w`) would remove the jump but changes every stage E local-vol and SLV golden and the SLV leverage calibration; that is a model change for the stage G rates and vol model work, not a fix. Plan item R10 allows "fixed or documented with a continuity test"; this is the documented route.

**Continuity test (goldens and property).** For the stage E three-slice surface and for a two-slice surface, at `k` in {-0.4, 0, 0.3}: points at `T_j (1 - 1e-9)`, at `T_j`, and at `T_j (1 + 1e-9)` for every slice expiry, and five points spread inside each interval. Each language also asserts, as a property test on its own outputs: `|w(T_j(1 - 1e-9)) - w(T_j)| <= 1e-9 (T_j |w_T(T_j-)| + w(T_j))`, with `w_T(T_j-)` the left slope in `T` (ruling F-37; a step of `1e-9 T_j` moves `w` by about `1e-9 T_j w_T`, so the earlier bound `1e-9 w(T_j)` failed at an inner node with a steep interval), and the same form for `implied_vol`; the left and right local vols equal the two formulas above to 1e-8 relative; and inside an interval, local vol at `T` and `T(1 + 1e-9)` differ by at most 1e-6 relative.

### Convergence and limit cases

| Method | Asserted order | Measured on | Limit case | Reference |
|---|---|---|---|---|
| Local vol from the slice surface | closed form at each point (no grid) | none | one slice: no jump at all (flat vol on both sides, `w_T = w_1/T_1`) | the 40-digit price-based Dupire `mp_dupire` of stage E |
