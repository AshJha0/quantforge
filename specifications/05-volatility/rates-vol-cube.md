# Rates and inflation vol: SABR swaption cube, caplet stripping, bond futures options, inflation caps

Spec version 1.0.0. Status: Specified (stage E, E4, spec B). Builds on `caps-and-swaptions.md` (D7), `sabr.md` and `black-models.md`. Rulings: `stage-e-rulings-b.md` E-B8 to E-B13.

**Stylised conventions (ruling R1-5 carries over).** The index, schedules, curves and the exercise-at-start rule are D7's. They test the vol machinery, not a market convention.

## `rates.swaption.price_cube`

**Plain idea.** A swaption's vol depends on its expiry, the length of the swap and the strike. A SABR cube keeps four SABR parameters at each (expiry, tenor) node, interpolates the parameters (not the vols) to the swaption, and reads the smile at its strike.

Inputs: `discount`, `projection` (as D7), `cube` `{expiries_months, tenors_months, alpha, beta, rho, nu}` (each parameter a matrix, rows by expiry, columns by tenor), `trade` `{type, expiry_months, tenor_months, strike, notional}`, `type` `PAYER` or `RECEIVER`.

1. Node expiry dates `x_i = adjust(spot + expiries_months_i)` (`USGS`, `MODIFIED_FOLLOWING`, `spot = as_of + 2` business days), node times `t_i = (x_i - as_of)/365`; node tenors `L_j = tenors_months_j / 12`.
2. The swaption is D7's: swap start and exercise `s = adjust(spot + expiry_months)`, `t = (s - as_of)/365`, `L = tenor_months/12`; `forward_rate` `F` and `annuity` `A` as `caps-and-swaptions.md`.
3. Each parameter bilinear in `(t, L)` on the node grid (ruling E-B8). Outside the grid: `E_INPUT` (no extrapolation).
4. `vol` = the Hagan lognormal vol of `sabr.md` at `F`, `strike`, `t` and the interpolated parameters (unshifted).
5. `price = N A Black(F, K, vol, t)`, call for payers.

Outputs: `price`, `forward_rate`, `annuity`, `vol`, `sabr` `{alpha, beta, rho, nu}` (the interpolated parameters).

Checks, in order: matrix shapes not `len(expiries) x len(tenors)`, or node months not strictly increasing: `E_INPUT`; expiry or tenor outside the grid: `E_INPUT`; `alpha <= 0`, `beta` outside `[0, 1]`, `|rho| >= 1`, `nu < 0`: `E_DOMAIN`; `strike <= 0` or `F <= 0`: `E_DOMAIN`.

## `rates.cap.strip`

**Plain idea.** Caps are quoted with one flat vol each, but the caplets inside a long cap overlap with shorter caps. Stripping finds caplet vols such that every cap, priced caplet by caplet, gives the same price as at its flat vol.

Inputs: `discount`, `projection`, `model` (`BLACK_76` or `BACHELIER`), `start_months`, `strike`, `cap_tenors_months` (strictly increasing multiples of 3), `flat_vols` (one per tenor), `notional`. Caplets are D7's (`rates.cap.price`: quarterly from `adjust(spot + start_months)`, fixing at the period start, no lag).

Cap `k` holds the first `M_k/3` caplets. Its target is its price with every caplet at `flat_vols_k`. Caplet vols are piecewise constant: one value `v_k` on the caplets of cap `k` that are not in cap `k-1` (ruling E-B9). For `k = 1, 2, ...` in turn, `v_k` solves `sum of known caplets + sum of new caplets at v_k = target_k`. The left side rises with `v_k`, so the root is unique when it exists; the root is searched in `[1e-10, 5]` for `BLACK_76` and `[1e-10, 0.5]` for `BACHELIER`. If the left side already exceeds the target at the lower bound, the quotes hold calendar arbitrage: `E_ARBITRAGE` (ruling E-B10). If it is still below the target at the upper bound: `E_DOMAIN` (ruling E-B32).

Outputs: `caplet_vols` (one per caplet), `cap_prices` (the targets). Checks: tenors not multiples of 3 or not increasing, or flat vols of the wrong count: `E_INPUT`; a flat vol `<= 0`: `E_DOMAIN`; no root above the lower bound: `E_ARBITRAGE`; no root below the upper bound: `E_DOMAIN`.

## `rates.bondfut.option_price`, `rates.bondfut.implied_vol`

**Plain idea.** Options on bond futures are quoted in price vol (Black-76 on the futures price). Traders think in yield vol; the two are linked through the cheapest-to-deliver's duration and yield.

`option_price`: inputs `type` (`CALL`, `PUT`), `futures_price` `F`, `strike` `K`, `expiry_years` `t`, `discount_factor` `D`, `vol`, `contract_size`. `price = Black(F, K, vol, t) D` per 100 face; `contract_value = price * contract_size / 100`. The option is premium-paid at the discount date given; futures-style margining is out of scope (ruling E-B11).

`implied_vol`: inputs as above with `premium` instead of `vol`, plus `ctd_yield` `y` and `ctd_modified_duration` `Dm` (from `04-pricing/bonds.md`). `price_vol` solves `Black(...) D = premium`; `yield_vol = price_vol / (Dm y)` (the first-order link between relative price and relative yield moves, ruling E-B11).

Checks: `t <= 0`, `F <= 0`, `K <= 0`, `D <= 0`, `vol < 0`: `E_DOMAIN` (`vol = 0` gives discounted intrinsic); a premium at or below discounted intrinsic, or at or above the no-arbitrage bound: `E_DOMAIN`; then `ctd_yield <= 0` or `ctd_modified_duration <= 0`: `E_DOMAIN` (ruling E-B38).

## `infl.cap.yoy_price`, `infl.cap.zc_price`

**Plain idea.** A year-on-year inflation caplet pays when one year's inflation exceeds the strike, so it is an option on a forward inflation rate. A zero-coupon inflation cap pays once, when cumulative inflation exceeds `(1+K)^T - 1`, so it is an option on the forward index ratio.

`yoy_price`: inputs `model`, `type` (`CAP`, `FLOOR`), `strike`, `notional`, `periods`: array of `{accrual, discount_factor, yoy_forward, expiry_years, vol}`. Caplet `i = N accrual_i option(yoy_forward_i, K, vol_i, expiry_years_i) discount_factor_i`; time runs to the fixing (`expiry_years`), not to payment (ruling E-B12). Outputs `caplets`, `price` (sum in order). The YoY forwards are inputs: building them from a CPI curve (with the convexity between ZC and YoY swaps) belongs with the inflation curve, `02-curves/inflation.md`.

`zc_price`: inputs `model`, `type`, `forward_index_ratio` `F_I` (forward `I(T)/I(0)`), `years` `T`, `strike` `K`, `discount_factor`, `vol`, `notional`. `strike_ratio = (1+K)^T` (compounded, ruling E-B13); `price = N D option(F_I, strike_ratio, vol, T)`. Outputs `price`, `strike_ratio`.

Checks: `BLACK_76` with a strike `<= 0` (YoY) or a forward `<= 0`: `E_DOMAIN`, so a YoY floor at 0% needs `BACHELIER` (ruling E-B32); for `zc_price` the strike ratio at 0% is 1, which Black accepts. Under `BACHELIER`, `vol` is a normal vol of the quantity optioned: of the YoY rate for `yoy_price`, of the index ratio `I(T)/I(0)` for `zc_price`; `T <= 0` or an `expiry_years <= 0`: `E_DOMAIN`; an empty `periods`: `E_INPUT`. A `vol < 0`: `E_DOMAIN`; `vol = 0` gives discounted intrinsic (ruling E-B38). For `zc_price`, `1 + K <= 0`: `E_DOMAIN`, after the forward check and before `years`; a negative `K` with `1 + K > 0` is priced under both models (ruling E-B37).

## Worked examples

- Cube at a node (`ratesvol_e-0001`, payer 12M x 5Y, strike 3.70%): the swaption expiry date equals the 12M node date, so the parameters are the node's exactly (`alpha 0.048, beta 0.5, rho -0.27, nu 0.44`). Forward 3.5718%, annuity 4.35104, Hagan vol 25.265%, price 133,536.05 on 10m.
- Cube between nodes (`ratesvol_e-0006`, 18M x 5Y): the 18M expiry sits between the 12M and 24M node times, so `rho = -0.27995` lies between -0.27 and -0.29, weighted by time (not by months).
- Strip (`ratesvol_e-0049`, Black, strike 3.70%, flat vols 24.0, 23.5, 22.8, 22.2, 21.5%): caplet vols 24.000, 23.143, 21.956, 21.096, 19.706% on the five yearly segments. The first segment equals the first flat vol; later segments fall faster than the flat vols, as they must when flat vols fall.
- Bond futures (`ratesvol_e-0064`, the implied vol of case `ratesvol_e-0063`): price vol 5.5%, CTD yield 4.25%, modified duration 6.4: yield vol `0.055 / (6.4 x 0.0425) = 20.22%`.

## Acceptance

Suite `stage_e_b/ratesvol_e`. Money outputs 1e-9 per unit notional (D7's curve tolerance); option prices on given inputs 1e-12 per unit notional; implied and stripped vols class `root_finding` (1e-10). All 35 non-error cases are outside-checked by QuantLib 1.44 (`oracle/outside_register_e_b.json`): the cube through QuantLib `BilinearInterpolation`, `SabrSmileSection`, `VanillaSwap` and `BlackSwaptionEngine`; the strip by a reprice check in QuantLib's `CapFloor` engines (each cap at the golden caplet vols equals the cap at its flat vol); bond futures and inflation caps through QuantLib's `blackFormula`, `bachelierBlackFormula` and `blackFormulaImpliedStdDev` (formula level).

QuantLib's `SabrSwaptionVolatilityCube` is not used: it reads the smile at its swap index's forward, which starts two business days after expiry, while this cube, like D7, exercises at the swap start. QuantLib's `OptionletStripper1` is not used: it strips caplet by caplet from a term-vol surface interpolated in time, a different (also valid) rule from the piecewise-constant one here.

Wrong-convention checks (34, each caught): vols interpolated instead of parameters; expiry axis in months/12 instead of ACT/365F time; flat vol used as caplet vol; yield vol without the yield factor; YoY time to payment instead of fixing; ZC strike `1 + KT`.

## Sources

- [S1] Hagan, P. S., Kumar, D., Lesniewski, A. S. and Woodward, D. E., "Managing smile risk", *Wilmott Magazine*, September 2002, 84-108 (the SABR expansion used per node) (not opened)
- [S2] Brigo, D. and Mercurio, F., *Interest Rate Models: Theory and Practice*, 2nd ed., Springer, 2006, chapter 6 (cap and swaption market formulas, caplet volatility stripping) (not opened)
- [S3] Hull, J. C., *Options, Futures, and Other Derivatives*, 10th ed., Pearson, 2018, chapter "Futures Options and Black's Model" (Black-76 on a futures price) and chapter "Interest Rate Derivatives: The Standard Market Models" (bond options, price vol and yield vol linked by duration and yield) (not opened)
- [S4] Kerkhof, J., "Inflation derivatives explained", Lehman Brothers Fixed Income Quantitative Research, July 2005 (YoY and ZC inflation caps and floors priced with Black and Bachelier) (not opened)
- [S5] QuantLib 1.44 Python wheel: `SabrSmileSection`, `BilinearInterpolation`, `BlackSwaptionEngine`, `BlackCapFloorEngine`, `BachelierCapFloorEngine`, `blackFormula`, `bachelierBlackFormula`, `blackFormulaImpliedStdDev` (used by behaviour)
