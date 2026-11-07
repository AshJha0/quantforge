# Model inventory and limitations register

Version 1.0.0. Plan 11.2.6: governance in the style of SR 11-7, written before stage E adds many models. Last full review: 2026-11-07, by the spec session (self-assessment).

**Status words.** *Implemented*: all four languages pass the goldens. *Outside-checked*: some goldens are re-priced by an outside library under rule 11.2.5 (`oracle/CONVENTION_MAP.md`). *Validated*: tested on real data against an independent benchmark, with a written report. **No model in QuantForge is Validated.** Every input to date is synthetic. Every review is self-assessment until the human review at the end of the project.

**Use restriction for every model.** Research, education and conformance testing only. Do not use for trading, valuation of record, risk limits or regulatory capital. Nothing here is investment advice.

Each model below gets one entry, the "page" the plan asks for. Outside-checked shares count stage D goldens by operation, from `oracle/outside_register.json` on 2026-11-07.

## Index

| # | Model | Spec | Stage | Status | Outside-checked |
|---|---|---|---|---|---|
| M1 | Discount curve framework and interpolation | `02-curves/curve-framework.md` | B, D | Implemented, outside-checked | `rates.curve.*` 2 of 7 |
| M2 | OIS curve bootstrap and swap PV | `02-curves/ois-curves.md` | B, D | Implemented, outside-checked | `rates.ois.*` 81 of 116 |
| M3 | Overnight compounding and IBOR fallbacks | `02-curves/overnight-compounding.md` | D | Implemented, outside-checked | in M2; `rates.fallback` 4 of 5 |
| M4 | Meeting-date step curve | `02-curves/meeting-steps.md` | D | Implemented | none |
| M5 | Projection curves, FRA, basis | `02-curves/projection-and-fra.md`, `csa-and-basis.md` | B, D | Implemented | `rates.basis` 0 of 5, `rates.csa` 0 of 8 |
| M6 | Futures convexity (Hull-White) | `02-curves/futures-convexity.md` | D | Implemented | 0 of 10 |
| M7 | FX forwards, cross-currency basis, NDF | `02-curves/fx.md`, `cross-currency.md` | B, D | Implemented | 0 of 16 |
| M8 | Fixed-rate bonds: price, yield, spreads | `04-pricing/bonds.md` | D | Implemented, outside-checked | price 143 of 148, yield 36 of 37, spreads 70 of 76 |
| M9 | FRNs, repo, bond futures | `04-pricing/bonds.md` | D | Implemented | 0 of 23 |
| M10 | Sovereign curve fits (Nelson-Siegel, smooth, robust) | `04-pricing/bonds.md`, `03-calibration/curve-fits.md` | D | Implemented | 0 of 23 |
| M11 | CDS: ISDA standard model, index intrinsic | `04-pricing/credit.md` | D | Implemented, outside-checked | `credit.cds` 29 of 39; index and composite 0 of 7 |
| M12 | Equity forwards, dividends, borrow, index, TRS | `02-curves/equity-forward.md`, `equity-curves.md`, `04-pricing/equity-index.md` | C, D | Implemented | 0 of 30 (stage D) |
| M13 | Inflation curve, ZCIS, linkers | `02-curves/inflation.md` | D | Implemented | 0 of 18 |
| M14 | Black-76 and Bachelier | `05-volatility/black-models.md` | C | Implemented, outside-checked (stage C, QuantLib formula) | not counted under 11.2.5 |
| M15 | Caps, floors, European swaptions | `05-volatility/caps-and-swaptions.md` | D | Implemented, outside-checked | caps 12 of 19, swaptions 10 of 13 |
| M16 | Smile, SVI, SSVI, surface | `05-volatility/smile-and-surface.md` | C | Implemented | stage C only |
| M17 | SABR (Hagan and arbitrage-free) | `05-volatility/sabr.md` | C | Implemented | stage C only |
| M18 | Commodity forward curve and storage carry | `02-curves/commodity.md` | D | Implemented | 0 of 12 |
| M19 | Agency MBS cash flows and price | `04-pricing/mbs.md` | D | Implemented | 0 of 14 |
| M20 | Rates sensitivities (bump and rebuild) | `06-risk/rates-sensitivities.md` | B | Implemented | stage B only |
| M21 | Vol Greeks | `06-risk/vol-greeks.md` | C | Implemented | stage C only |
| M22 | Least-squares calibration | `03-calibration/least-squares.md` | B | Implemented | known truth only |
| M23 | Linear-cost hedge solver | `08-hedging/stage-b-hedges.md` | B | Implemented | none |

Numerical engines in `01-core` (root finders, quadrature, PDE, Monte Carlo, COS, RNG, Sobol) are tools, not models. They are tested against analytic and library values in stage A.

## Entries

Each entry gives: purpose; inputs; known limitations; validation status; use restrictions beyond the general one; last review.

### M1 Discount curve framework
- **Purpose:** discount factors and zero rates between pillars, with optional turn-of-year jumps.
- **Inputs:** `as_of`, pillar dates and discount factors, interpolation (`LOG_LINEAR_DF`, `LINEAR_ZERO`), jumps.
- **Limitations:** curve time is ACT/365F whatever the instrument's day count. Flat-forward extrapolation past the last pillar. No smoothness constraint on forwards with `LOG_LINEAR_DF`, so forwards are step-shaped.
- **Validation:** QuantLib `DiscountCurve` agrees, jumps included. No real-data test. **Review:** 2026-11-07.

### M2 OIS bootstrap and PV
- **Purpose:** SOFR, ESTR and SONIA discount curves from par OIS quotes; PV, par rate and annuity of an OIS.
- **Inputs:** convention, `as_of`, tenor quotes, interpolation, jumps; trade terms.
- **Limitations:** single curve per currency, so no separate projection and discounting for OIS. No futures, meeting-date or turn instruments in the bootstrap. Quotes are mid; no bid/offer.
- **Validation:** QuantLib `OISRateHelper` and `MakeOIS` agree. Real-data sanity bands against published curves are R1.3, not done here. **Review:** 2026-11-07.

### M3 Overnight compounding and fallbacks
- **Purpose:** compounded overnight rates over dated periods, with lookback, observation shift and lockout; ISDA IBOR fallback rates.
- **Inputs:** convention, period, method, shift, fixings; IBOR name.
- **Limitations:** fixings are supplied by the caller. No revision handling (edge register E4). Lockout follows the ARRC rule, which is QuantLib's k-1. Cessation dates are not modelled (E6).
- **Validation:** exact-rational goldens; QuantLib `OvernightIndexedCoupon` agrees. Workflow (c) in R1 will compare with NY Fed published averages. **Review:** 2026-11-07.

### M4 Meeting-date step curve
- **Purpose:** front-end curve with flat forwards between central-bank meetings.
- **Inputs:** base rate, step dates and rates, jumps; or quotes to fit steps.
- **Limitations:** meeting dates are inputs, not a calendar. No probability-weighted steps.
- **Validation:** closed forms and known truth only. **Review:** 2026-11-07.

### M5 Projection, FRA, basis, CSA discounting
- **Purpose:** term-rate projection on a separate curve, FRA and swap PVs, OIS spreads, discounting under a collateral rate.
- **Inputs:** discount curve, projection quotes, collateral spread and FX forwards.
- **Limitations:** the term index `USD-TERM-3M` is synthetic. No real term-rate quotes are free (data survey 2026-11-07). CSA optionality (cheapest to deliver) is not modelled.
- **Validation:** independent replay; no outside library counted under 11.2.5 yet. **Review:** 2026-11-07.

### M6 Futures convexity
- **Purpose:** futures-to-forward rate adjustment under Hull-White.
- **Inputs:** futures price, start and end times, sigma, mean reversion.
- **Limitations:** Hull-White parameters are inputs, not calibrated. No SOFR-futures averaging adjustment beyond the closed form.
- **Validation:** closed form; no outside check counted. **Review:** 2026-11-07.

### M7 FX, cross-currency, NDF
- **Purpose:** FX spot dates and forwards; a basis-adjusted foreign discount curve from cross-currency basis swaps; NDF PV.
- **Inputs:** pair, curves, basis quotes, fixing and settlement terms.
- **Limitations:** domestic currency is USD only in this stage. Mark-to-market resets are simplified as `cross-currency.md` states. No free basis quotes exist, so all tests are synthetic.
- **Validation:** independent replay only. **Review:** 2026-11-07.

### M8 Fixed-rate bonds
- **Purpose:** price from yield and yield from price, with accrued, durations and convexity; price on a curve; Z-spread; par-par asset swap spread.
- **Inputs:** bond (maturity, coupon, frequency), settlement, yield, price or curve.
- **Limitations:** unadjusted coupon dates, ACT/ACT ICMA only. No ex-dividend period (E9), no odd first or last coupons beyond the backward rule, no sinking funds, calls or puts. Street-convention yield only (no true yield or money-market yield in the last period).
- **Validation:** QuantLib `FixedRateBond`, `BondFunctions` and `DiscountingBondEngine` agree on price, yield, curve price and Z-spread. Asset swap has no outside check. Rich/cheap on real Treasury and gilt data is workflow (b), in R2. **Review:** 2026-11-07.

### M9 FRNs, repo, bond futures
- **Purpose:** FRN price with a discount margin; repo forward price and implied repo; conversion factor, basis and cheapest to deliver.
- **Inputs:** FRN terms and curves; bond, repo dates and rates; futures delivery month and price.
- **Limitations:** the conversion factor follows the CBOT formula for one contract family. Delivery options (timing, wild card) are not valued. No special-repo data.
- **Validation:** analytic and hand only. **Review:** 2026-11-07.

### M10 Sovereign curve fits
- **Purpose:** Nelson-Siegel fit to bond prices; smooth and robust zero-curve fits.
- **Inputs:** bonds and prices or zero rates, weights, smoothing and robustness parameters.
- **Limitations:** Nelson-Siegel is poorly identified, so goldens judge repricing, not parameters. No Svensson term. Robust fits depend on the outlier threshold, which is guarded in the goldens.
- **Validation:** known truth and SciPy. No comparison yet with published BoE or Fed fitted curves. **Review:** 2026-11-07.

### M11 CDS
- **Purpose:** CDS PV, upfront, par spread and RPV01 under the ISDA standard model; hazard curve bootstrap; index intrinsic value.
- **Inputs:** trade date, discount curve, hazard pillars or spread quotes, recovery, trade terms.
- **Limitations:** flat recovery. No default event, auction or succession handling (E8). Discount curve is supplied; the ISDA standard curve-building conventions are not reproduced.
- **Validation:** QuantLib `IsdaCdsEngine` agrees on price outputs and reprices bootstrap quotes. The ISDA C library itself is not run (licence check pending). **Review:** 2026-11-07.

### M12 Equity
- **Purpose:** forwards with discrete dividends and borrow; implied dividends and borrow; index dividends and rebalancing; corporate-action adjustment; total return swap PV.
- **Inputs:** spot, dividend schedule, funding curve, borrow rate, index constituents.
- **Limitations:** dividends are deterministic. No dividend risk or tax treatment. Corporate actions cover the spec's listed types only.
- **Validation:** stage C forwards were outside-checked by a QuantLib replay of discount factors only; stage D has hand and analytic checks. **Review:** 2026-11-07.

### M13 Inflation
- **Purpose:** CPI curve from ZCIS quotes with seasonality; ZCIS PV; TIPS-style linker price from real yield or a curve.
- **Inputs:** base month and CPI, ZCIS quotes, seasonality, fixings, bond terms.
- **Limitations:** US TIPS lag rule only (three months, daily interpolation). UK 3-month and 8-month linkers are not covered. No deflation floor. No rebasing (E7).
- **Validation:** exact-rational and hand. QuantLib uses other lag and interpolation conventions, so it is not used. **Review:** 2026-11-07.

### M14 Black-76 and Bachelier
- **Purpose:** European option prices and implied vols, lognormal and normal.
- **Inputs:** model, option type, strike, forward, discount factor, expiry, vol.
- **Limitations:** no smile in the model itself; that is M16 and M17. Implied vol inversion has a domain limit near intrinsic value.
- **Validation:** QuantLib formula functions agree (stage C), not counted under 11.2.5 because the stage D rule is scoped to stage D. **Review:** 2026-11-07.

### M15 Caps, floors, swaptions
- **Purpose:** cap and floor prices caplet by caplet; European swaption prices, with the forward swap rate and annuity.
- **Inputs:** discount and projection curves, model, flat or per-caplet vol, trade terms.
- **Limitations:** no vol cube, no SABR-in-the-cube, no Bermudans (stage G). Physical settlement only.
- **Validation:** QuantLib `CapFloor` with `BlackCapFloorEngine` and `BachelierCapFloorEngine`, and `Swaption` with the Black and Bachelier engines, agree. **Review:** 2026-11-07.

### M16 Smile, SVI, SSVI, surface
- **Purpose:** delta conventions, smile interpolation, SVI and SSVI fits, arbitrage checks on a surface.
- **Inputs:** strikes or deltas, vols, forwards and expiries.
- **Limitations:** no local vol or stochastic-vol surface (stage E). Arbitrage checks are discrete.
- **Validation:** stage C rulings name the sources. **Review:** 2026-11-07.

### M17 SABR
- **Purpose:** Hagan SABR vols with a density check; an arbitrage-free SABR price.
- **Inputs:** alpha, beta, rho, nu, shift, forward, strikes, expiry.
- **Limitations:** Hagan's expansion is not arbitrage-free, as the spec says. No tight outside source for arbitrage-free SABR at `nu > 0`.
- **Validation:** partial; see `05-volatility/sabr.md` and `stage-c-rulings.md`. **Review:** 2026-11-07.

### M18 Commodities
- **Purpose:** monthly forward curve with seasonality; storage carry.
- **Inputs:** monthly quotes, seasonality, storage and financing costs.
- **Limitations:** no convenience-yield model, no options, no free curve data.
- **Validation:** hand only. **Review:** 2026-11-07.

### M19 Agency MBS
- **Purpose:** pool cash flows under CPR or PSA prepayment; price on a curve.
- **Inputs:** pool terms, prepayment assumption, curve.
- **Limitations:** prepayment is a fixed assumption, not a model of rates or burnout. No TBA, no OAS (stage G at the earliest). No free pool factor data.
- **Validation:** hand only. **Review:** 2026-11-07.

### M20 Rates sensitivities
- **Purpose:** DV01 and key-rate risk by bump and rebuild.
- **Inputs:** quotes, interpolation, trade.
- **Limitations:** stage B products only; R2 extends par and key-rate risk to every stage B to D product and adds P&L explain.
- **Validation:** finite-difference consistency only. **Review:** 2026-11-07.

### M21 Vol Greeks
- **Purpose:** analytic and bumped Greeks for Black options.
- **Limitations:** second-order Greeks carry finite-difference error, which the goldens bound.
- **Validation:** analytic against bumped. **Review:** 2026-11-07.

### M22 Least-squares calibration
- **Purpose:** generic weighted least squares, judged on repricing.
- **Limitations:** results are judged on the objective, not on parameters, unless the minimum is unique.
- **Validation:** known truth and SciPy. **Review:** 2026-11-07.

### M23 Hedge solver
- **Purpose:** minimise residual risk plus linear trading cost.
- **Limitations:** linear costs only, no impact, no integer lot sizes.
- **Validation:** optimality conditions only. **Review:** 2026-11-07.

## Review cycle

Each stage's definition of done adds entries for its new models and re-dates every entry it touched. An entry moves to *Validated* only with a dated report on real data against an independent benchmark. The R5 audit uses a different model from the spec session and reads this register.
