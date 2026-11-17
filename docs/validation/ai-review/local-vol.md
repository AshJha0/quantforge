# Review request: Local volatility (QuantForge curve)

You are reviewing one curve of an open-source quantitative finance library. You have no access to its code or repository: everything you may use is below.

Rules for your answer:
- Answer only from the material given here and from standard, citable finance knowledge. Where the material is not enough, write "cannot check" rather than guess.
- Quote the spec line or the exact number you question.
- Return findings as one table with columns: curve, claim, issue, severity (high / medium / low / note), evidence (quote or your working).
- After the table, list the questions you answered "cannot check", and why.
- Your review is a second opinion. It is filed under a labelled "AI review" section and never counts as the human sign-off.

Status: Implemented, not Validated (stage E). Evidence line from the project's status table: 2 golden cases.

## Questions

1. Conventions: do the formulas, day counts, calendars, spot and payment lags in the spec match the cited market standard or source? Quote the line.
2. Interpolation and extrapolation: is the stated rule applied consistently, and what happens beyond the last pillar?
3. Tolerances: is each tolerance class justified for the quantity it guards (rate, factor, money)?
4. Edge cases: zero or negative rates, dates on as_of or on expiry, empty inputs, boundaries the cases do not cover.
5. Golden cases: recompute any case you can from its inputs with the spec's formulas. Report any number you get differently, with your working.
6. Outside-library and real-data evidence: does the check really test the same quantity? Is anything claimed beyond what it shows?
7. Anything that looks wrong, inconsistent or missing.

## Spec

### `specifications/05-volatility/local-and-forward-vol.md`

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


## Golden cases (4 of 6 value cases of this curve's operations shown, chosen in file order and skipping cases too large to fit; one JSON object per line; `verified_by` lists the sources that agreed)

```json
{"case_id":"lv_e-0001","operation":"vol.local.dupire","inputs":{"slices":[{"expiry_years":0.25,"svi":{"a":0.02,"b":0.1,"rho":-0.4,"m":0.02,"sigma":0.2}},{"expiry_years":1.0,"svi":{"a":0.035,"b":0.11,"rho":-0.35,"m":0.03,"sigma":0.25}},{"expiry_years":2.0,"svi":{"a":0.06,"b":0.12,"rho":-0.3,"m":0.04,"sigma":0.3}}],"points":[{"expiry_years":0.1,"log_moneyness":0.0},{"expiry_years":0.25,"log_moneyness":-0.2},{"expiry_years":0.5,"log_moneyness":0.0},{"expiry_years":0.5,"log_moneyness":0.15},{"expiry_years":1.0,"log_moneyness":-0.3},{"expiry_years":1.0,"log_moneyness":0.0},{"expiry_years":1.5,"log_moneyness":0.1},{"expiry_years":2.0,"log_moneyness":0.0},{"expiry_years":3.0,"log_moneyness":-0.1}]},"expected":{"status":"ok","outputs":{"total_variance":[0.01635990049689671,0.058532137494637024,0.04855059825697158,0.04606379198000092,0.09324553139786579,0.06385229228643119,0.07770780073325592,0.09775859028101173,0.15715060328608865],"implied_vol":[0.40447373829331257,0.48386831884155024,0.3116106489097302,0.30352526082684095,0.3053613128702878,0.2526901111765777,0.22760755806615315,0.2210866236127954,0.22887449492832576],"local_vol":[0.3869909723376669,0.21278356533802728,0.1582078092483187,0.16339889255941614,0.22846701886205661,0.16776207113021416,0.16714652895968385,0.20286275992019143,0.21683205475712045]}},"tolerance_class":"interpolation","tolerance_limit":null,"verified_by":["analytic","mpmath-price-dupire-40-digits"]}
{"case_id":"lv_e-0002","operation":"vol.local.dupire","inputs":{"slices":[{"expiry_years":1.0,"svi":{"a":0.035,"b":0.11,"rho":-0.35,"m":0.03,"sigma":0.25}}],"points":[{"expiry_years":0.5,"log_moneyness":-0.2},{"expiry_years":1.0,"log_moneyness":0.0},{"expiry_years":2.0,"log_moneyness":0.25}]},"expected":{"status":"ok","outputs":{"total_variance":[0.040611316526609334,0.06385229228643119,0.12632363354352555],"implied_vol":[0.28499584743153483,0.2526901111765777,0.2513201479622411],"local_vol":[0.3258086529569957,0.23021935790781908,0.24573777168126917]}},"tolerance_class":"interpolation","tolerance_limit":null,"verified_by":["analytic","mpmath-price-dupire-40-digits"]}
{"case_id":"lvc_f-0001","operation":"vol.local.dupire","inputs":{"slices":[{"expiry_years":0.25,"svi":{"a":0.02,"b":0.1,"rho":-0.4,"m":0.02,"sigma":0.2}},{"expiry_years":1.0,"svi":{"a":0.035,"b":0.11,"rho":-0.35,"m":0.03,"sigma":0.25}},{"expiry_years":2.0,"svi":{"a":0.06,"b":0.12,"rho":-0.3,"m":0.04,"sigma":0.3}}],"points":[{"expiry_years":0.24999999975,"log_moneyness":-0.4},{"expiry_years":0.25,"log_moneyness":-0.4},{"expiry_years":0.25000000025,"log_moneyness":-0.4},{"expiry_years":0.999999999,"log_moneyness":-0.4},{"expiry_years":1.0,"log_moneyness":-0.4},{"expiry_years":1.000000001,"log_moneyness":-0.4},{"expiry_years":1.999999998,"log_moneyness":-0.4},{"expiry_years":2.0,"log_moneyness":-0.4},{"expiry_years":2.000000002,"log_moneyness":-0.4},{"expiry_years":0.025,"log_moneyness":-0.4},{"expiry_years":0.075,"log_moneyness":-0.4},{"expiry_years":0.125,"log_moneyness":-0.4},{"expiry_years":0.175,"log_moneyness":-0.4},{"expiry_years":0.225,"log_moneyness":-0.4},{"expiry_years":0.325,"log_moneyness":-0.4},{"expiry_years":0.475,"log_moneyness":-0.4},{"expiry_years":0.625,"log_moneyness":-0.4},{"expiry_years":0.7749999999999999,"log_moneyness":-0.4},{"expiry_years":0.925,"log_moneyness":-0.4},{"expiry_years":1.1,"log_moneyness":-0.4},{"expiry_years":1.3,"log_moneyness":-0.4},{"expiry_years":1.5,"log_moneyness":-0.4},{"expiry_years":1.7,"log_moneyness":-0.4},{"expiry_years":1.9,"log_moneyness":-0.4},{"expiry_years":2.1,"log_moneyness":-0.4},{"expiry_years":2.3,"log_moneyness":-0.4},{"expiry_years":2.5,"log_moneyness":-0.4},{"expiry_years":2.7,"log_moneyness":-0.4},{"expiry_years":2.9,"log_moneyness":-0.4},{"expiry_years":0.24999999975,"log_moneyness":0.0},{"expiry_years":0.25,"log_moneyness":0.0},{"expiry_years":0.25000000025,"log_moneyness":0.0},{"expiry_years":0.999999999,"log_moneyness":0.0},{"expiry_years":1.0,"log_moneyness":0.0},{"expiry_years":1.000000001,"log_moneyness":0.0},{"expiry_years":1.999999998,"log_moneyness":0.0},{"expiry_years":2.0,"log_moneyness":0.0},{"expiry_years":2.000000002,"log_moneyness":0.0},{"expiry_years":0.025,"log_moneyness":0.0},{"expiry_years":0.075,"log_moneyness":0.0},{"expiry_years":0.125,"log_moneyness":0.0},{"expiry_years":0.175,"log_moneyness":0.0},{"expiry_years":0.225,"log_moneyness":0.0},{"expiry_years":0.325,"log_moneyness":0.0},{"expiry_years":0.475,"log_moneyness":0.0},{"expiry_years":0.625,"log_moneyness":0.0},{"expiry_years":0.7749999999999999,"log_moneyness":0.0},{"expiry_years":0.925,"log_moneyness":0.0},{"expiry_years":1.1,"log_moneyness":0.0},{"expiry_years":1.3,"log_moneyness":0.0},{"expiry_years":1.5,"log_moneyness":0.0},{"expiry_years":1.7,"log_moneyness":0.0},{"expiry_years":1.9,"log_moneyness":0.0},{"expiry_years":2.1,"log_moneyness":0.0},{"expiry_years":2.3,"log_moneyness":0.0},{"expiry_years":2.5,"log_moneyness":0.0},{"expiry_years":2.7,"log_moneyness":0.0},{"expiry_years":2.9,"log_moneyness":0.0},{"expiry_years":0.24999999975,"log_moneyness":0.3},{"expiry_years":0.25,"log_moneyness":0.3},{"expiry_years":0.25000000025,"log_moneyness":0.3},{"expiry_years":0.999999999,"log_moneyness":0.3},{"expiry_years":1.0,"log_moneyness":0.3},{"expiry_years":1.000000001,"log_moneyness":0.3},{"expiry_years":1.999999998,"log_moneyness":0.3},{"expiry_years":2.0,"log_moneyness":0.3},{"expiry_years":2.000000002,"log_moneyness":0.3},{"expiry_years":0.025,"log_moneyness":0.3},{"expiry_years":0.075,"log_moneyness":0.3},{"expiry_years":0.125,"log_moneyness":0.3},{"expiry_years":0.175,"log_moneyness":0.3},{"expiry_years":0.225,"log_moneyness":0.3},{"expiry_years":0.325,"log_moneyness":0.3},{"expiry_years":0.475,"log_moneyness":0.3},{"expiry_years":0.625,"log_moneyness":0.3},{"expiry_years":0.7749999999999999,"log_moneyness":0.3},{"expiry_years":0.925,"log_moneyness":0.3},{"expiry_years":1.1,"log_moneyness":0.3},{"expiry_years":1.3,"log_moneyness":0.3},{"expiry_years":1.5,"log_moneyness":0.3},{"expiry_years":1.7,"log_moneyness":0.3},{"expiry_years":1.9,"log_moneyness":0.3},{"expiry_years":2.1,"log_moneyness":0.3},{"expiry_years":2.3,"log_moneyness":0.3},{"expiry_years":2.5,"log_moneyness":0.3},{"expiry_years":2.7,"log_moneyness":0.3},{"expiry_years":2.9,"log_moneyness":0.3}]},"expected":{"status":"ok","outputs":{"total_variance":[0.08331881331513323,0.08331881339845204,0.08331881340610185,0.10626825247736266,0.10626825250796192,0.1062682525414386,0.1397449293203795,0.13974492938733285,0.1397449295270778,0.008331881339845205,0.02499564401953561,0.04165940669922602,0.05832316937891643,0.07498693205860683,0.08561375730940303,0.090203645131305,0.09479353295320697,0.09938342077510895,0.10397330859701093,0.10961592019589902,0.1163112555717732,0.12300659094764738,0.12970192632352157,0.13639726169939576,0.1467321758566995,0.16070666879543277,0.17468116173416606,0.18865565467289935,0.20263014761163262,0.04089975120134203,0.04089975124224178,0.040899751249892626,0.06385229225582781,0.06385229228643119,0.06385229232033748,0.09775859021319915,0.09775859028101173,0.09775859037877033,0.004089975124224178,0.012269925372672534,0.02044987562112089,0.028629825869569244,0.036809776118017605,0.04319500534666072,0.0477855135554986,0.052376021764336485,0.05696652997317436,0.06155703818201225,0.06724292208588925,0.07402418168480535,0.08080544128372147,0.08758670088263756,0.09436796048155367,0.10264651979506233,0.11242237882316349,0.12219823785126467,0.13197409687936584,0.141749955907467,0.04320930102496121,0.04320930106817051,0.04320930107546121,0.06508141285538022,0.06508141288454303,0.06508141291774026,0.09827863971267566,0.0982786397790701,0.09827863987734875,0.0043209301068170515,0.012962790320451152,0.021604650534085255,0.030246510747719356,0.03888837096135346,0.045396512249807765,0.04977093461308227,0.054145356976356765,0.05851977933963127,0.06289420170290577,0.06840113557399574,0.07504058095290114,0.08168002633180657,0.08831947171071197,0.09495891708961739,0.10319257176802361,0.11302043574593061,0.12284829972383762,0.13267616370174465,0.14250402767965165],"implied_vol":[0.5772999684685668,0.5772999684685668,0.5772999682064187,0.3259881172429923,0.3259881171269314,0.32598811701528374,0.264334002220793,0.2643340021519487,0.2643340021519487,0.5772999684685668,0.5772999684685668,0.5772999684685668,0.5772999684685668,0.5772999684685668,0.5132513473605247,0.43577793748966615,0.3894478819112144,0.3581014827781121,0.3352664266842617,0.31567520735991667,0.2991156909853973,0.2863640933586092,0.2762159495368472,0.2679328880025112,0.2643340021519487,0.2643340021519487,0.2643340021519487,0.2643340021519487,0.2643340021519487,0.40447373829331257,0.40447373829331257,0.4044737381289068,0.25269011124236757,0.2526901111765777,0.25269011111732326,0.2210866236466577,0.2210866236127954,0.2210866236127954,0.40447373829331257,0.40447373829331257,0.40447373829331257,0.40447373829331257,0.40447373829331257,0.3645650953656371,0.317176734912053,0.28948512020989675,0.27111842424554305,0.2579692799268145,0.24724467470299583,0.23862455493741844,0.23209975051504828,0.22698367508367795,0.22286172309723884,0.2210866236127954,0.2210866236127954,0.2210866236127954,0.2210866236127954,0.2210866236127954,0.4157369411932046,0.4157369411932046,0.4157369410204097,0.25511058958902827,0.2551105895186302,0.2551105894561393,0.22167390443053314,0.2216739043945747,0.2216739043945747,0.4157369411932046,0.4157369411932046,0.4157369411932046,0.4157369411932046,0.4157369411932046,0.3737399846862183,0.32369880286295477,0.29433411484598726,0.2747897245100304,0.2607560767665999,0.24936489432519227,0.2402572034506436,0.23335241778878368,0.227931196675808,0.22355844295304103,0.2216739043945747,0.2216739043945747,0.2216739043945747,0.2216739043945747,0.2216739043945747],"local_vol":[0.870115401981745,0.2636517926693846,0.26365179265671335,0.23690967521816844,0.2477984362325442,0.24779843620203296,0.22650499152418427,0.3272349171238577,0.327234917123658,0.8427890949686281,0.8485027286259804,0.8544135763718591,0.8605308271209592,0.8668643111273844,0.260005686006946,0.25353672929692944,0.24796826591523977,0.2431195886421205,0.23885560391406213,0.24487522279381385,0.23970482788636527,0.23527022045154602,0.23142050972705122,0.22804357848378368,0.32722564718177966,0.3272114023217003,0.32720288238507866,0.3272000860305093,0.32720301281776615,0.3645698962843903,0.1576794986270321,0.15767949862753228,0.15938166024439504,0.16776207113021416,0.16776207113126668,0.16895850174259658,0.20286275992019143,0.2028627599041733,0.39988089389793524,0.3911475645388274,0.3829646722112026,0.37527676695315787,0.3680359158656438,0.1578323511330784,0.1581527573181846,0.15848912502241047,0.15883833624020985,0.15919821990401248,0.1678693325983174,0.16809440739559417,0.1683308997246469,0.1685764972504519,0.16882955880476042,0.20206659899775084,0.20050220812485373,0.19897386881394502,0.19748021941363544,0.196019969187897,0.4730225148042486,0.19430229187394782,0.1943022918679095,0.18236263532211838,0.19456827828151702,0.19456827826945688,0.1863668306083855,0.22674216382950055,0.22674216381983722,0.4841707082473136,0.4816204378113739,0.47911276957256954,0.4766465492792433,0.4742206659522111,0.19258353808425055,0.18961870212049187,0.18714037985695242,0.18502670638159016,0.18319350810657772,0.19341934660152757,0.19141446867592735,0.18971447698701088,0.1882456257460715,0.1869562646626685,0.226260569814956,0.22530671462066748,0.22436508280172987,0.22343541669813044,0.22251746618620385]}},"tolerance_class":"interpolation","tolerance_limit":null,"verified_by":["analytic","mpmath-price-dupire-40-digits"]}
{"case_id":"lvc_f-0003","operation":"vol.local.dupire","inputs":{"slices":[{"expiry_years":1.0,"svi":{"a":0.035,"b":0.11,"rho":-0.35,"m":0.03,"sigma":0.25}}],"points":[{"expiry_years":0.999999999,"log_moneyness":0.0},{"expiry_years":1.0,"log_moneyness":0.0},{"expiry_years":1.000000001,"log_moneyness":0.0},{"expiry_years":0.3,"log_moneyness":-0.2},{"expiry_years":2.5,"log_moneyness":0.2}]},"expected":{"status":"ok","outputs":{"total_variance":[0.0638522922225789,0.06385229228643119,0.06385229235028349,0.0243667899159656,0.15427669051807036],"implied_vol":[0.2526901111765777,0.2526901111765777,0.2526901111765777,0.28499584743153483,0.24841633643387495],"local_vol":[0.23021935792736542,0.23021935790781908,0.23021935788827272,0.3278616533017508,0.22389770579348608]}},"tolerance_class":"interpolation","tolerance_limit":null,"verified_by":["analytic"]}
```

## Outside-library evidence and limits (from the project's own page)

Golden cases are analytic and a 40-digit mpmath reference that differentiates call prices directly, an independent route to the same Dupire formula.

2 golden cases with status ok in `datasets/golden/stage_e*/` for `vol.local.dupire`, by `verified_by`:

| Operation: sources | Cases |
|---|---|
| vol.local.dupire: analytic, mpmath-price-dupire-40-digits | 2 |

Limits: one synthetic input, so the page shows the method, not a market. Arbitrage flags are checks at grid points only.

Synthetic inputs, not market data.

## Real-data reconciliation

- No free data: the stage C/D data surveys (LEARN.md) found no free option quotes or vol surfaces. No reconciliation is possible without paid data, which the project does not buy.

## Rulings that name this curve's operations

- (stage-e-rulings.md) | E-A8 | Local vol inputs | `vol.local.dupire` takes SVI slices, not the stage C grid surface: the grid surface is piecewise linear in `k`, so `w_kk` is zero between nodes and undefined at them, and its local vol would be meaningless |
