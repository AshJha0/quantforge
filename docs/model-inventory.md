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

## Stage E models (E1 to E8)

Stage E is Implemented: all four languages pass every stage E golden (6,817 of 6,817 cases in the full set at merge `597abf2`, 2026-11-08). 557 of the 895 stage E cases (62.2%) are outside-checked under rule 11.2.5 and rulings E-A17 and E-B28. Every input is synthetic; no entry is Validated. Last full review of these entries: 2026-11-08.

### Slices E1, E2, E3, E5 (entries ME-A)

Outside-checked counts are from `oracle/outside_register_e_a.json`.

| # | Model | Spec | Stage | Status | Outside-checked |
|---|---|---|---|---|---|
| ME-A1 | SVI surface arbitrage checks, SSVI to SVI, SVI surface fit | `05-volatility/arb-free-surfaces.md` | E1 | Implemented, outside-checked partly outside: 9 surface checks (wing lists are own algebra), not counted (E-A17) |
| ME-A2 | Dupire local vol on SVI slices | `05-volatility/local-and-forward-vol.md` | E1 | Implemented | none (40-digit independent route) |
| ME-A3 | Forward vol, smile dynamics, vol of vol | `05-volatility/local-and-forward-vol.md` | E1 | Implemented, outside-checked | 16 of 22 value cases; 6 sticky-delta cases partly outside (E-A17) |

### ME-A1 SVI surface checks and fit
- **Purpose:** reject SVI surfaces with butterfly, calendar or wing arbitrage before they reach pricing.
- **Inputs:** SVI slices by expiry; a check grid in forward log-moneyness.
- **Limitations:** checks the grid and the asymptotes only, not every `k` between grid points. The fit reports arbitrage but does not remove it (ruling E-A3).
- **Validation:** QuantLib `SviSmileSection` and its density; published Vogt counterexample. **Review:** 2026-11-08.

### ME-A2 Dupire local vol
- **Purpose:** local vol from an SVI-slice surface, as input to local-vol and SLV pricing.
- **Limitations:** total variance is linear in time between slices, so local vol jumps at slice dates; `w_T` is one-sided at nodes. Undefined (`E_ARBITRAGE`) where the surface has arbitrage. No rates term structure: forward log-moneyness only.
- **Validation:** closed form against a 40-digit price-based Dupire. No outside library. **Review:** 2026-11-08.

### ME-A3 Forward vol, smile dynamics, vol of vol
- **Purpose:** forward vol between expiries; scenario repricing under sticky-strike or sticky-delta; a historical vol-of-vol measure.
- **Limitations:** smile dynamics are the two textbook regimes only, at fixed expiry; no sticky-local-vol regime, no time decay. Vol of vol is historical, not implied (no VVIX-style index; that is spec B's E-slice for VIX-style indices).
- **Validation:** QuantLib `BlackVarianceCurve`, `SviSmileSection`, `blackFormula`, `BlackCalculator`, `IncrementalStatistics`. **Review:** 2026-11-08.
| ME-A4 | FX smile: delta and ATM conventions, RR/BF strikes, Garman-Kohlhagen | `05-volatility/fx-smile.md` | E3 | Implemented, outside-checked | 114 of 114 value cases |

### ME-A4 FX smile and Garman-Kohlhagen
- **Purpose:** FX vanilla prices and Greeks; strikes from delta quotes under the four market delta types and three ATM types.
- **Limitations:** flat continuous rates; no spot lag, premium or delivery date (ruling E-A9); smile strangle only, no broker strangle (E-A11); no smile interpolation between the quoted pillars.
- **Validation:** QuantLib `BlackDeltaCalculator`, Black-Scholes-Merton engine. **Review:** 2026-11-08.
| ME-A5 | Heston, Bates, Merton | `05-volatility/heston-family.md` | E2 | Implemented, outside-checked | Heston and Bates 18 of 18 value cases; Merton none |
| ME-A6 | SLV leverage, reference PDE scheme | `05-volatility/heston-family.md` | E2 | Implemented | none |

### ME-A5 Heston, Bates, Merton
- **Purpose:** European prices under stochastic vol, with or without log-normal jumps; jump diffusion alone.
- **Limitations:** flat rates and dividend yield; European exercise only; no calibration operation in stage E; `xi = 0` refused.
- **Validation:** QuantLib analytic Heston and Bates engines; 30-digit mpmath; Merton by two routes inside the oracle only. **Review:** 2026-11-08.

### ME-A6 SLV leverage
- **Purpose:** leverage function of a Heston SLV model fitted to an SVI-slice local vol surface.
- **Limitations:** first-order reference scheme, not converged (about 1% at the spot against a doubled grid); positivity floor and boundaries change mass by up to about 1%; Feller condition assumed; no repricing check of vanillas under the SLV model.
- **Validation:** grid refinement and the flat-vol limit only. No outside library. **Review:** 2026-11-08.
| ME-A7 | Exotics: digitals, barriers, geometric Asians, lookbacks, quanto, chooser, Kirk, moment-matched basket | `04-pricing/exotics.md` | E5 | Implemented, outside-checked | 103 of 109 value cases (basket not outside) |
| ME-A8 | American: CRR, BAW, FD | `04-pricing/exotics.md` | E5 | Implemented, outside-checked | BAW 12 of 12; CRR and FD none |

### ME-A7 Exotics
- **Purpose:** closed-form prices of the standard exotic options on one or two lognormal assets.
- **Limitations:** flat rates and vols; continuous barrier and lookback monitoring; geometric (not arithmetic) Asians; floating-strike lookbacks only; moment matching for positive-weight baskets only; Kirk is an approximation.
- **Validation:** QuantLib analytic engines; parity and limit checks. **Review:** 2026-11-08.

### ME-A8 American options
- **Purpose:** early-exercise prices by tree, by BAW approximation and by a fixed-grid FD scheme.
- **Limitations:** BAW is an approximation (errors near 1e-2); the FD scheme is first order in time; no discrete dividends.
- **Validation:** QuantLib BAW; tree and FD by replay, the Black-Scholes limit and cross-method agreement within 2e-2. **Review:** 2026-11-08.

### Slices E4, E6, E7, E8 (entries EB)

Outside-checked counts are from `oracle/outside_register_e_b.json`.

| # | Model | Spec | Stage | Status | Outside-checked |
|---|---|---|---|---|---|
| EB1 | GARCH(1,1) likelihood, forecast, fit | `05-volatility/garch.md` | E7 | Implemented | 0 of 27 (no QuantLib object in the Python wheel) |
| EB2 | Variance swap: replication and realized variance | `05-volatility/variance-swaps.md` | E7 | Implemented, outside-checked | `fair_strike` 18 of 27; realized 0 of 4 |
| EB3 | VIX-style index from a given strip | `05-volatility/vix-index.md` | E7 | Implemented | 0 of 14 (hand case is the outside reference) |
| EB4 | SABR swaption cube | `05-volatility/rates-vol-cube.md` | E4 | Implemented, outside-checked | 42 of 48 |
| EB5 | Caplet stripping | `05-volatility/rates-vol-cube.md` | E4 | Implemented, outside-checked (reprice) | 8 of 14 |
| EB6 | Bond futures options, price and yield vol | `05-volatility/rates-vol-cube.md` | E4 | Implemented, outside-checked (formula) | 10 of 12 |
| EB8 | Correlation validation and nearest correlation (Higham) | `06-risk/correlation.md` | E6 | Implemented, outside-checked | validate 15 of 17; nearest 10 of 18 |
| EB9 | Implied correlation and dispersion | `06-risk/correlation.md` | E6 | Implemented | 0 of 14 (closed forms, hand cases) |
| EB10 | CDS options (Black on the forward spread) | `04-pricing/credit-options-and-copulas.md` | E8 | Implemented, outside-checked | 168 of 176 |
| EB11 | Gaussian and Student-t default copulas | `04-pricing/credit-options-and-copulas.md` | E8 | Implemented (Gaussian re-evaluated in QuantLib, not counted: E-B28) | 0 of 14 |
| EB12 | Large homogeneous pool (Vasicek) | `04-pricing/credit-options-and-copulas.md` | E8 | Implemented (re-evaluated in QuantLib, not counted: E-B28) | 0 of 26 |
| EB7 | YoY and ZC inflation caps | `05-volatility/rates-vol-cube.md` | E4 | Implemented, outside-checked (formula, YoY only) | 4 of 11 |

### EB1 GARCH(1,1)
- **Purpose:** conditional variance path and Gaussian log-likelihood at given parameters; multi-step variance forecast; maximum-likelihood fit.
- **Inputs:** a return series (used as given, no mean), parameters, an initial-variance rule.
- **Limitations:** Gaussian innovations only (no Student-t), no mean equation, no leverage term (GJR, EGARCH), one asset. The fit is judged on the likelihood, so two languages may report different parameters on a flat likelihood. Synthetic series only.
- **Validation:** 50-digit replica, float replay, hand case; fit optimum checked by gradient and Hessian. **Review:** 2026-11-08.

### EB2 Variance swap
- **Purpose:** fair variance strike from an option strip; realized variance and payoff.
- **Inputs:** spot, flat r and q, strike lists with one Black vol each, extension step; or a price series.
- **Limitations:** discrete strip with linear weights, so the result depends on the strikes given (a coarse strip is biased: see the density grid in the goldens). No jumps or caps on realized variance, no volatility swap convexity, no dividends in the realized series. Flat rates.
- **Validation:** QuantLib `ReplicatingVarianceSwapEngine` agrees on all `q = 0` cases; differs by design at `q != 0` (ruling E-B3). **Review:** 2026-11-08.

### EB3 VIX-style index
- **Purpose:** the Cboe white-paper index from two caller-given strips.
- **Inputs:** minutes to expiry, a rate per term, call and put bids and asks by strike.
- **Limitations:** the caller picks the expiries and the rate; no Treasury interpolation, no special-opening-quotation handling, no data cleaning beyond the zero-bid rule. Not the official index and not licensed as one.
- **Validation:** hand-worked case; exact-rational replica; float replay. **Review:** 2026-11-08.
### EB4 SABR swaption cube
- **Purpose:** swaption prices off a cube of SABR parameters per expiry and tenor.
- **Inputs:** D7 curves, node grid and parameter matrices, trade.
- **Limitations:** parameters are inputs (no calibration to market quotes here); no shift, so no negative forwards; Hagan's expansion is not arbitrage-free in the wings (`sabr.md`); bilinear interpolation has kinks at nodes; no extrapolation; stylised D7 swap.
- **Validation:** QuantLib smile, interpolation and swaption engine objects agree on all 42 cases. **Review:** 2026-11-08.

### EB5 Caplet stripping
- **Purpose:** caplet vols from flat cap vols at one strike.
- **Limitations:** piecewise-constant shape (a smoother shape gives other caplet vols from the same quotes); one strike at a time; rejects rather than repairs arbitrage.
- **Validation:** reprice check in QuantLib cap engines. **Review:** 2026-11-08.

### EB6 Bond futures options
- **Purpose:** Black-76 price and implied price vol; yield vol through CTD duration.
- **Limitations:** premium-paid only; no delivery option or CTD switch; first-order yield-vol link.
- **Validation:** QuantLib Black formula and implied standard deviation. **Review:** 2026-11-08.

### EB7 Inflation caps
- **Purpose:** YoY caplets on given forwards; ZC caps on a forward index ratio.
- **Limitations:** forwards and vols are inputs (no YoY curve, convexity or seasonality); Black or Bachelier only.
- **Validation:** QuantLib Black and Bachelier formulas. **Review:** 2026-11-08.
### EB8 Correlation repair
- **Purpose:** test a correlation matrix and replace it by the nearest valid one.
- **Limitations:** unweighted Frobenius norm only, so all pairs are trusted equally; no rank or factor constraint; no fixed entries. The nearest matrix is usually singular (on the PSD boundary), which can make later Cholesky steps fail without a floor.
- **Validation:** two internal solvers; QuantLib Higham where it converges. **Review:** 2026-11-08.

### EB9 Implied correlation and dispersion
- **Purpose:** one average correlation from index and member vols; P&L of a vega-weighted variance dispersion trade.
- **Limitations:** a single average correlation (no pairwise structure); no cap on variance payoffs; the P&L takes realised vols as inputs.
- **Validation:** hand cases. **Review:** 2026-11-08.
### EB10 CDS options
- **Purpose:** European options on a forward CDS, with or without knock-out; implied vol.
- **Limitations:** stylised underlying (flat hazard and rate, mid-point legs, no IMM roll, no upfront or standard coupon); Black on the spread ignores the annuity measure's dependence on default; index options (with the index's own front-end and loss settlement) are not covered.
- **Validation:** QuantLib `BlackCdsOptionEngine` on all cases. **Review:** 2026-11-08.

### EB11 Default copulas
- **Purpose:** joint default probability of two names under a Gaussian or Student-t copula.
- **Limitations:** two names, static horizon, one `nu`; no calibration; the copula choice drives tail risk and is a model assumption, not an output.
- **Validation:** 50-digit quadrature; QuantLib bivariate normal for the Gaussian. **Review:** 2026-11-08.

### EB12 Large homogeneous pool
- **Purpose:** loss distribution and tranche expected loss for a large pool under the one-factor Gaussian copula.
- **Limitations:** infinitely granular, homogeneous pool; one correlation for all tranches (so no base-correlation skew); single horizon, no tranche premium leg. Known to underprice senior tranches against market quotes.
- **Validation:** closed form against a split fixed quadrature; QuantLib bivariate normal. **Review:** 2026-11-08.

### Mutation scores (stage E)

Measured on branch `stage-e`. Pooled CI score before the closeout tests: **84.3%** (2,360 killed, 439 survived; CI run 42590488102, `mutation-report.md`). Two columns: the score before the closeout tests, and the score after them where tests were added.

Evidence classes. Java: PIT on unit tests, full mutant set (observed, CI). C++ "before": local `--unit` runs on a 40-site sample, 0 timeouts (observed, local); the CI report's golden-only C++ scores are lower because they do not run the unit tests. Python and Rust "before": CI sample of 40 mutants, unit or golden (observed, CI). Every "after" score is a hand-applied survivor check: each surviving sampled mutant was applied by hand against the new tests (`cpp26/tests/test_mutants_e.cpp` after commit `996527c`, `python/tests/test_mutants_e.py`, `rust/crates/quantforge-core/tests/mutants_e.rs`). It is not a fresh full mutation run. Remaining survivors are classed as equivalent by the author, with reasons in those test files; a second reviewer's sign-off is scheduled (plan 13.2 T).

| Module | Java (PIT) | C++ before | C++ after | Python before | Python after | Rust before | Rust after |
|---|---|---|---|---|---|---|---|
| surfaces_local_vol (E1) | 91.7% | 85.0% | unchanged | 70.0% | 97.5% (39/40) | 85.0% | unchanged |
| heston_slv (E2) | 94.6% | 82.5% | unchanged | 75.0% | 100% (40/40) | 87.5% | unchanged |
| fx_smile (E3) | 81.7% | 85.0% | unchanged | 72.5% | 90.0% (36/40) | 87.5% | unchanged |
| rates_vol (E4) | 91.7% | 66.7% | 97.4% (38/39) | 57.5% | 90.0% (36/40) | 87.5% | unchanged |
| exotics (E5) | 93.9% | 85.0% | unchanged | 65.0% | 97.5% (39/40) | 97.5% | unchanged |
| correlation (E6) | 86.3% | 85.0% | unchanged | 80.0% | unchanged | 90.0% | unchanged |
| garch_varswap_vix (E7) | 82.2% | 75.0% | 82.5% (33/40) | 65.0% | 100% (40/40) | 70.0% | 87.5% (35/40) |
| credit_options (E8) | 90.4% | 60.0% | 92.5% (37/40) | 70.0% | 82.5% (33/40) | 95.0% | unchanged |

Every cell is at or above the 80% target after the closeout tests, on the evidence classes above.

## Stage F models (wave 1: F1 curve layer, F6 model fixes)

Every entry carries the plan A2 fields. The data-lineage hash is the SHA-256 of the golden suite file that pins the model, as committed by the spec session (`sha256sum datasets/golden/stage_f/<suite>.json`); a golden regeneration changes it and must be recorded here. Tier: 1 = feeds prices or risk that a desk would act on; 2 = feeds analytics and reports; 3 = research or challenger.

| # | Model | Spec | Stage | Status | Outside-checked |
|---|---|---|---|---|---|
| MF-1 | CDS index option, Pedersen adjusted forward | `04-pricing/credit-options-and-copulas.md` | F (R7) | Specified | none (no free outside source) |
| MF-2 | GARCH(1,1) estimate with standard errors, Student-t, demeaning | `05-volatility/garch.md` | F (R8) | Specified | none |
| MF-3 | VIX null-quote rule; local vol at slice expiries | `05-volatility/vix-index.md`, `05-volatility/local-and-forward-vol.md` | F (R10) | Specified | VIX: Cboe sample calculation, 3 of 10 |
| MF-4 | Curve interpolation: monotone convex, monotonic log cubic, tension spline, hybrid | `02-curves/curve-framework.md` | F (Q1) | Specified | 48 of 84 (QuantLib 1.44) |
| MF-5 | Joint multi-curve solve with turns, futures-fitted steps and IFT Jacobian | `02-curves/joint-solve-and-funding.md` | F (Q4) | Specified | 1 of 13 (QuantLib 1.44 rebuild with Jacobian) |
| MF-6 | Funding curve (spread over OIS) | `02-curves/joint-solve-and-funding.md` | F | Specified | none |

### MF-1 CDS index option (Pedersen)
- **Purpose:** payer and receiver options on a CDS index with front-end protection inside the forward and the strike converted for the fixed coupon.
- **Inputs:** dates, flat index rate and hazard, recovery, strike spread, index coupon, notional, vol.
- **Limitations:** stylised legs (ruling E-B22), not the ISDA standard model; flat hazard for the strike annuity; Black on the adjusted pair is Pedersen's approximation, not his exact integral; no index factor or defaulted-name bookkeeping.
- **Validation:** parity `payer - receiver = N A (F_adj - K_adj)` on every pair; limit cases; five wrong conventions caught. The Pedersen (2003) worked example is not reproduced (paper not freely available). **Review:** 2026-11-09.
- **Tier:** 1 (prices a traded option).
- **Challenger:** Pedersen's exact model (lognormal loss-adjusted index value integrated numerically), stage G.
- **Monitoring thresholds:** parity residual above 1e-10 relative, or any golden outside 1e-9 per unit notional, fails conformance.
- **Data lineage hash:** sha256 227d670739edb4e6a0c79e5de1c6918034a36153a013cc61d4c4316c6b1f5b7d
- **Retirement trigger:** an ISDA-standard-model index option (stage G) that matches market upfronts replaces the stylised legs.
- **Validation report:** `oracle/REPORT.md` (stage F section) and `specifications/04-pricing/credit-options-and-copulas.md` (R7 acceptance).

### MF-2 GARCH estimate
- **Purpose:** maximum-likelihood GARCH(1,1) parameters with observed-information standard errors, Gaussian or unit-variance Student-t innovations, optional two-step demeaning.
- **Inputs:** returns, initial variance rule, distribution, demean flag.
- **Limitations:** interior optima only (boundary fits return `E_NO_CONVERGENCE`); the demeaning step's error is not in the standard errors; no QML sandwich; univariate only.
- **Validation:** 50-digit Newton optimum with exact second derivatives; scipy multi-start does not beat it; simulated parameters recovered within 2 SE on the golden series; coverage study over 200 series per distribution in `oracle/R8_COVERAGE.json`. **Review:** 2026-11-09.
- **Tier:** 2 (volatility forecasts for analytics and VaR filtering).
- **Challenger:** the `arch` Python package (not a dependency; an offline comparison is allowed in stage J).
- **Monitoring thresholds:** parameters outside 1e-6 relative or standard errors outside 1e-5 relative across languages fail conformance; coverage outside [0.90, 0.99] fails the oracle run.
- **Data lineage hash:** sha256 1825dd623364b4a2e09c9fa1020c59afac1b06a0628733c2561a67b7624ae78f
- **Retirement trigger:** a multivariate or asymmetric (GJR, EGARCH) model with its own goldens supersedes it for VaR filtering.
- **Validation report:** `oracle/REPORT.md`; `oracle/R8_COVERAGE.json`.

### MF-3 VIX null quotes and local-vol continuity
- **Purpose:** the Cboe rule for null quotes in the VIX strip; a stated and tested behaviour of Dupire local vol at SVI slice expiries.
- **Inputs:** option strip with nullable quotes; SVI slices and points.
- **Limitations:** crossed quotes are refused, not filtered (Cboe filters them with quote history); local vol jumps at slice expiries by construction (linear total variance in time).
- **Validation:** the Cboe v6.0 sample calculation reproduced to every printed digit; continuity and jump formulas asserted at every slice expiry. **Review:** 2026-11-09.
- **Tier:** 2.
- **Challenger:** a C1-in-time surface (stage G) for local vol.
- **Monitoring thresholds:** the Cboe sample case must round to the printed values; any continuity assertion failing stops the oracle run.
- **Data lineage hash:** sha256 c2a308ff9004a417aa74c2c2c6c99f2458078c9ccc12debdae6c745eba5ac2c2; sha256 41d4979e50effaa54a0a0dcca8bda0f50d352d6ebafaa420caf8ec27b16cb6cc
- **Retirement trigger:** a C1 surface interpolation in time replaces the documented jump.
- **Validation report:** `specifications/05-volatility/vix-index.md` and `local-and-forward-vol.md` (stage F sections).

### MF-4 Curve interpolation (Q1)
- **Purpose:** four more interpolations for discount and projection curves: monotone convex (Hagan-West), monotonic log cubic (Hyman), exponential tension spline, hybrid step-then-smooth.
- **Inputs:** curve object with `interpolation`, `tension`, `step_end`.
- **Limitations:** monotone convex without QuantLib's forcePositive (it breaks repricing; ruling F-19), so a negative forward is possible on steep data; tension is a single global parameter; non-local methods need a global bootstrap.
- **Validation:** QuantLib 1.44 `ConvexMonotoneInterpolation`, `MonotonicLogCubicDiscountCurve` and full `PiecewiseYieldCurve` builds; locality, continuity and limit cases. **Review:** 2026-11-09.
- **Tier:** 1 (curves feed every price).
- **Challenger:** `LOG_LINEAR_DF` (the stage B default) on the same quotes; the hybrid against `MONOTONE_CONVEX`.
- **Monitoring thresholds:** pillars or zero rates more than 1e-10 from QuantLib on the golden builds; a forward jump above 1e-12 at an interior pillar.
- **Data lineage hash:** sha256 036a7971c773ca5e910de9168301574f34016a236ebfbb52f47442458ad84d46
- **Retirement trigger:** a smoothing method with a published market standard (for example an ISDA SIMM curve rule) that QuantLib also implements.
- **Validation report:** `oracle/outside_register_f.json`; `specifications/02-curves/curve-framework.md` (stage F acceptance).

### MF-5 Joint multi-curve solve (Q4)
- **Purpose:** OIS, term projection and cross-currency curves solved together, with year-end turns solved from quotes, meeting-date steps fitted to SOFR futures after Hull-White convexity, and the full Jacobian of curve unknowns to quotes.
- **Inputs:** curve definitions in dependency order; instruments with quotes.
- **Limitations:** constant-notional cross-currency swaps only (synthetic, ruling R1-1); convexity from a one-factor Hull-White model with caller-given parameters; no bid/offer; turn sizes are solved, so a turn needs a quote that spans it.
- **Validation:** repricing to 1e-13; IFT Jacobian against bump-and-rebuild of the whole system; turn sensitivity zero on non-spanning instruments; QuantLib repricing of the curves it can build. **Review:** 2026-11-09.
- **Tier:** 1.
- **Challenger:** sequential stage B and D bootstraps on the same quotes (`rates.ois.bootstrap`, `rates.curve.joint_bootstrap`).
- **Monitoring thresholds:** any residual above 1e-13; Jacobian outside `1e-9 + 1e-6 |ref|` of bump-and-rebuild.
- **Data lineage hash:** sha256 05d94767453f1447c65daa1b33e69a6b83f729dd2ffe0bb17879f4dc7ebd62a7
- **Retirement trigger:** mark-to-market cross-currency swaps and a calibrated convexity model (stage G) replace the synthetic pieces.
- **Validation report:** `specifications/02-curves/joint-solve-and-funding.md` (acceptance); `oracle/outside_register_f.json`.

### MF-6 Funding curve
- **Purpose:** an unsecured funding discount curve as OIS times a piecewise-flat spread, for uncollateralised discounting and stage G FVA.
- **Inputs:** OIS curve, simple ACT/360 funding quotes, dates.
- **Limitations:** zero-coupon money-market quotes only (no bond-implied funding); flat spread beyond the last quote; one funding curve per currency.
- **Validation:** closed form, the zero-spread limit, repricing of every quote to 1e-15. **Review:** 2026-11-09.
- **Tier:** 2 (feeds FVA, not prices, until stage G).
- **Challenger:** a bond-implied funding curve (Z-spread of own issuance) in stage G.
- **Monitoring thresholds:** a quote not repriced to 1e-12.
- **Data lineage hash:** sha256 05d94767453f1447c65daa1b33e69a6b83f729dd2ffe0bb17879f4dc7ebd62a7
- **Retirement trigger:** a funding model with term structure from issued bonds and CDS supersedes the money-market version.
- **Validation report:** `specifications/02-curves/joint-solve-and-funding.md`.

## Review cycle

Each stage's definition of done adds entries for its new models and re-dates every entry it touched. An entry moves to *Validated* only with a dated report on real data against an independent benchmark. The R5 audit uses a different model from the spec session and reads this register.
