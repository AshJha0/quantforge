# Credit and correlation hedges

Spec version 1.0.0. Status: Specified (stage I, wave 2). Rulings: `stage-i-rulings.md` I-15 to I-19 (and I-1 to I-4, I-12 from wave 1). Suites in `datasets/golden/stage_i/`: `hedgecredit_i`, `hedgecorr_i`, written by `oracle/python/gen_stage_i_w2.py`.

**Plain idea.** Both hedges follow the wave 1 Greek hedge (`hedge-solvers.md`, `hedge.greeks.neutralise`). Compute each instrument's risk per unit, stack the targeted risks into a square matrix, and solve for the quantities that cancel the book's risk. The credit hedge uses the stage D ISDA CDS model. Its risks are CS01 (a parallel or bucketed hazard-rate bump scaled to about one basis point of spread) and jump to default. The correlation hedge uses Margrabe exchange options on two assets, single-asset vanillas and the two underlyings. A least-squares version of either hedge is `hedge.qp.solve` with the risk matrix as `a`.

Sources:
- [O11] D. O'Kane, *Modelling Single-name and Multi-name Credit Derivatives*, Wiley, 2008, chapters 6 (CDS pricing, risky PV01), 8 (CDS risk: spread and hazard-rate sensitivities, jump to default) and 9 (hedging a CDS position) (not opened in this session; definitions here are self-contained and checked against QuantLib).
- [M78] W. Margrabe, "The value of an option to exchange one asset for another", *Journal of Finance* 33(1), 1978, 177-186 (not opened; the formula is the one already used by `risk.sens.correlation`, `06-risk/f3-sensitivities.md`).
- [H18] J. C. Hull, *Options, Futures, and Other Derivatives*, 10th ed., Pearson, 2018, chapter 26 (exchange options) (not opened).
- `04-pricing/credit.md` (the ISDA CDS legs, `credit.cds.price`) and `06-risk/book-sensitivities.md` (`risk.credit.jtd`), both normative here.

## `hedge.credit.cds`

### Inputs

- `trade_date`, `discount`, `hazard`, `recovery` `R`: as `credit.cds.price` (`04-pricing/credit.md`). `discount` must have `interpolation` `LOG_LINEAR_DF`.
- `book`: CDS trades `{maturity, coupon, notional, side}`, as the `trade` of `credit.cds.price`.
- `hedges`: CDS contracts `{maturity, coupon}`, at most 50 (I-4 extended by I-19).
- `targets`: distinct values from `CS01`, `JTD`, `BUCKET_1` to `BUCKET_P` (`P` the number of hazard pillars), as many as `hedges`.

### Checks, in order

1. `discount` interpolation other than `LOG_LINEAR_DF`: `E_INPUT` (ruling R1-4, before any other rule check).
2. Empty `book` or `hedges`; `len(targets) != len(hedges)`; a repeated or unknown target (a bucket number outside `1..P`); a book or hedge maturity on or before `trade_date`: `E_INPUT`.
3. `R` outside `[0, 1)`; a book notional below 0; a coupon below 0: `E_DOMAIN`.
4. The square risk matrix (row per target, column per hedge, risks per unit notional of bought protection) has smallest singular value at most `1e-12` times its largest: `E_SINGULAR` (I-3).

### Risks, per unit notional of bought protection (I-15)

- `pv`: the `credit.cds.price` value for a buyer of unit notional, `protection_leg - coupon rpv01 + accrued Pcs`.
- Hazards: `h_k = ln(Q_{k-1}/Q_k) / (t_k - t_{k-1})` on the `k`-th hazard section, with `Q_0 = 1` at `t_0 = 0`; `t = (date - trade_date)/365`. The last section's hazard also covers the time after the last pillar.
- `eps = 1e-4 / (1 - R)`: a hazard bump that moves a flat curve's par spread by about one basis point (the credit triangle `s ~ (1 - R) h`).
- `CS01 = (pv(h + eps) - pv(h - eps)) / 2`, with every `h_k` shifted. This is a central difference fixed by the spec, not an approximation of a derivative, so every build returns the same number.
- `BUCKET_k`: the same, with only `h_k` shifted.
- `JTD = (1 - R) - pv`: the value change if the name defaults now, as `risk.credit.jtd`, with this pv in place of the market value.

A trade of notional `N` and side `s` (+1 buyer, -1 seller) has `s N` times these. The book's risk is the sum over trades.

### Outputs

- `notionals`: one per hedge, signed (positive buys protection), solving `G n = -book` on the targets.
- `book`: `{pv, cs01, jtd, buckets}` of the book (`buckets` has length `P`).
- `after`: `{cs01, jtd, buckets}` of book plus hedges. Targeted entries are zero up to rounding.
- `hedge_upfront`: `sum_j n_j upfront_j`, with `upfront_j` the clean upfront per unit of `credit.cds.price`, which the buyer pays.

## `hedge.correlation.neutralise`

### Inputs

- `spot1`, `spot2`, `rate`, `yield1`, `yield2`, `vol1`, `vol2`, `correlation`.
- `book`: positions `{instrument, ..., quantity}`; `hedges`: instruments without `quantity`, at most 5. `instrument` is one of:
  - `EXCHANGE` with `quantity1`, `quantity2`, `expiry_years`: receive `quantity1 S1` for `quantity2 S2` at expiry [M78];
  - `CALL_1`, `PUT_1`, `CALL_2`, `PUT_2` with `strike`, `expiry_years`: a Black-Scholes-Merton vanilla on asset 1 or 2 (rate `rate`, yield of that asset);
  - `UNDERLYING_1`, `UNDERLYING_2`, with no other key.
- `targets`: distinct values from `DELTA_1`, `DELTA_2`, `VEGA_1`, `VEGA_2`, `CORRELATION`, as many as `hedges`.

### Checks, in order

1. An instrument with keys other than those listed for its kind; no hedges; `len(targets) != len(hedges)`; a repeated target: `E_INPUT`.
2. `spot1`, `spot2`, `vol1` or `vol2` at or below 0; `correlation` outside `[-1, 1]`; `quantity1`, `quantity2`, `strike` or `expiry_years` at or below 0: `E_DOMAIN`. With any `EXCHANGE`, a spread volatility `s = sqrt(vol1^2 + vol2^2 - 2 rho vol1 vol2)` of 0: `E_DOMAIN` (as `risk.sens.correlation`).
3. Risk matrix singular (I-3): `E_SINGULAR`.

### Greeks per unit

Exchange option, `F_k = Q_k S_k e^{-q_k T}`, `d1 = (ln(F1/F2) + s^2 T/2) / (s sqrt T)`, `d2 = d1 - s sqrt T`, `price = F1 N(d1) - F2 N(d2)`, `dV/ds = F1 n(d1) sqrt T`:

- `DELTA_1 = Q1 e^{-q1 T} N(d1)`, `DELTA_2 = -Q2 e^{-q2 T} N(d2)`;
- `VEGA_1 = dV/ds (vol1 - rho vol2)/s`, `VEGA_2 = dV/ds (vol2 - rho vol1)/s`;
- `CORRELATION = dV/ds (-vol1 vol2 / s) x 0.01`, per 0.01 of correlation, the `correlation01` of `risk.sens.correlation`.

Vanillas: the `hedge.greeks.neutralise` delta and vega on their own asset (vega per unit volatility), 0 for the other asset and for correlation. Underlyings: delta 1 on their own asset, all else 0.

### Outputs

`quantities` (one per hedge); `greeks_before` and `greeks_after`, objects with `delta_1`, `delta_2`, `vega_1`, `vega_2`, `correlation01`. Targeted entries of `greeks_after` carry an absolute tolerance of `1e-10 * max(1, max |greeks_before|)`.

### One spread-volatility factor (I-17)

A Margrabe price depends on `vol1`, `vol2` and `rho` only through `s`. Every exchange option's vega and correlation rows are therefore proportional, with factors `(vol1 - rho vol2)/s`, `(vol2 - rho vol1)/s` and `-0.01 vol1 vol2/s` common to all exchange options. Exchange options alone cannot hedge correlation separately from either vega. The hedge needs single-asset vanillas, whose vega carries no correlation. `hedgecorr_i` pins this: exchange options alone against `CORRELATION` and `VEGA_1` give `E_SINGULAR`, and an exchange option with a call on asset 1 solves the same targets.

## Validation cases and oracle

| Suite | Cases (value + error) | Oracle and self-checks | Outside (I-2) |
|---|---|---|---|
| `hedgecredit_i` | 10 + 9 | The stage D ISDA replay (agrees with QuantLib's `IsdaCdsEngine` to 7e-16 per unit there); targeted `after` risks below 1e-6 asserted; hedging a sold 7Y with the same 7Y contract returns exactly its notional | 10 of 19: QuantLib 1.44 `IsdaCdsEngine` NPVs on bumped `HazardRateCurve`s give CS01, buckets and JTD by the same central difference, then numpy `linalg.solve`; notionals, book `pv`, `cs01`, `jtd` and `hedge_upfront` within the case limit |
| `hedgecorr_i` | 9 + 11 | 50-digit Greeks and solve; the sign of `correlation01` (negative for a long exchange option) asserted | 9 of 20: QuantLib 1.44 `AnalyticEuropeanMargrabeEngine` `delta1`, `delta2`; `BlackCalculator.vega` for `dV/ds` (the Margrabe price is a Black price in `s`, asserted against the engine NPV); `AnalyticEuropeanEngine` for the vanillas; numpy solve |

Stage I so far: 63 of 160 = 39.4% outside (error cases in the denominator).

Mutants caught: a one-sided CS01 bump; JTD without subtracting the position's value; correlation sensitivity per unit instead of per 0.01; `VEGA_1` without the `-rho vol2` term.

A finite-difference stencil on QuantLib's Margrabe NPV was tried first for the outside vega. Its noise (about 1e-9 relative at step 5e-4) is above the 1e-10 tolerance, so the analytic `BlackCalculator.vega` replaced it. This is recorded so that it is not tried again.

## Convergence and limit cases

| Method | Asserted behaviour | Measured on | Limit case | Reference |
|---|---|---|---|---|
| Square risk solve | Exact in one step; targeted risks after the hedge below 1e-6 (credit) or the case tolerance (correlation) | Every value case | Hedging with the book's own contract returns its notional (`hedgecredit_i-0002`) | QuantLib and numpy |
| CS01 central difference | Fixed bump `1e-4/(1-R)`; no step-size limit is taken | All credit cases | A section beyond a contract's maturity has zero bucket risk exactly (`E_SINGULAR` case) | QuantLib `IsdaCdsEngine` |
| Margrabe Greeks | Closed form | All exchange cases | `rho = 1` with unequal vols (`s = 0.05`) is regular; `s = 0` is `E_DOMAIN` | QuantLib `AnalyticEuropeanMargrabeEngine` |

## Limitations

- Single-name CDS only: no index, tranche or basis hedge. The CS01 is a hazard bump, not a re-bootstrap from bumped quotes (I-15).
- Recovery is not hedged and not bumped.
- The correlation hedge is for two assets and one flat volatility per asset.

## Spec questions and rulings

| # | Question | Ruling |
|---|---|---|
| Q-I5 | CS01 by bumping quotes and re-bootstrapping, or by bumping hazards? | Hazards (I-15). A quote bump needs the quotes, which the hazard-curve input does not carry, and a bootstrap inside a risk call. The two differ by second-order terms. A quote-based CS01 can be added later as a new target name |
| Q-I6 | JTD with or without the accrued premium? | With: `pv` already includes `accrued Pcs`, and `JTD = (1 - R) - pv` uses it unchanged. `risk.credit.jtd` takes a clean market value as input; here the value is computed, so no input convention is needed (I-16) |
| Q-I7 | Can exchange options hedge correlation on their own? | No (I-17); a singular case pins it |

## R6 amendments (R6-11.8, R6-11.9, R6-11.16)

- `CS01` together with every bucket is a degenerate target set: CS01 is the sum of the buckets to first order, so the system is nearly dependent and the hedge notionals depend on the bump size. The scaled I-3 test decides; no special refusal.
- A downward CS01 bump that makes any hazard `h_k - eps` negative is `E_DOMAIN`.
- `hedge.correlation.neutralise`: a spread volatility `s <= 1e-12 (v1 + v2)` is `E_DOMAIN`.
