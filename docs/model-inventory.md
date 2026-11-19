# Model inventory and limitations register

Version 1.0.0. Plan 11.2.6: governance in the style of SR 11-7, written before stage E adds many models. Last full review: 2026-11-07, by the spec session (self-assessment).

**Status words.** *Implemented*: all four languages pass the goldens. *Outside-checked*: some goldens are re-priced by an outside library under rule 11.2.5 (`oracle/CONVENTION_MAP.md`). *Validated*: tested on real data against an independent benchmark, with a written report. **No model in QuantForge is Validated.** Every input to date is synthetic. Every review is self-assessment; there is no second review (owner decision, 2026-11-18).

**Use restriction for every model.** Research, education and conformance testing only. Do not use for trading, valuation of record, risk limits or regulatory capital. Nothing here is investment advice.

Each model below gets one entry, the "page" the plan asks for. Outside-checked shares count stage D goldens by operation, from `oracle/outside_register.json` on 2026-11-07. The H-19 checks of 2026-11-18 are not in the index column yet: current stage D figures are in `oracle/OUTSIDE_SHARES.md` (451 of 526 value cases, 85.7%; 19 further H-19 agreements are spec-closed and counted as reimplementation, not as outside checks).

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
| M24 | Coupon schedule generation | `02-curves/schedules.md` | B | Implemented | QuantLib Schedule, 53 of 54 |

Stage E has its own index tables (ME-A1 to ME-A8, EB1 to EB12) under "Stage E models". Stages F, G and I, with fields taken from each entry below (outside-checked counts as the entry's Validation line states them, "see entry" where it gives none):

| # | Model | Spec | Stage | Status | Outside-checked |
|---|---|---|---|---|---|
| MF-1 | CDS index option (Pedersen) | `04-pricing/credit-options-and-copulas.md` | F | Implemented | see entry |
| MF-2 | GARCH estimate | `oracle/REPORT.md` | F | Implemented | see entry |
| MF-3 | VIX null quotes and local-vol continuity | `05-volatility/vix-index.md` | F | Implemented | see entry |
| MF-4 | Curve interpolation (Q1) | `02-curves/curve-framework.md` | F | Implemented | see entry |
| MF-5 | Joint multi-curve solve (Q4) | `02-curves/joint-solve-and-funding.md` | F | Implemented | see entry |
| MF-6 | Funding curve | `02-curves/joint-solve-and-funding.md` | F | Implemented | see entry |
| MF-7 | Book sensitivities (Q3a, F3) | `06-risk/book-sensitivities.md` | F | Implemented | see entry |
| MF-8 | VaR, ES and backtests (Q2) | `06-risk/var-es-and-backtests.md` | F | Implemented | see entry |
| MF-9 | FRTB-SA GIRR delta (Q2) | `06-risk/frtb-sa-girr.md` | F | Implemented | see entry |
| MF-10 | Book lifecycle and marks (F5) | `07-portfolio/book-lifecycle.md` | F | Implemented | see entry |
| MF-11 | Factor attribution (use case 4) | `04-pricing/use-cases.md` | F | Implemented | see entry |
| MG-1 | One-factor short-rate models (G1) | `04-pricing/short-rate-models.md` | G | Implemented | 218 of 231 (215 library object, 3 numpy or scipy primitive; D6, generated) |
| MG-2 | Discrete barrier correction (R9) | `04-pricing/exotics.md` | G | Implemented | 8 of 9 (8 library object, 0 numpy or scipy primitive; D6, generated) |
| MG-3 | Monte Carlo Greeks (Q9 part 1) | `06-risk/mc-greeks.md` | G | Implemented | 0 of 12 (0 library object, 0 numpy or scipy primitive; D6, generated) |
| MG-4 | Closed-form swap exposure and CVA (G5a) | `06-risk/xva-exposure.md` | G | Implemented | 0 of 7 (0 library object, 0 numpy or scipy primitive; D6, generated) |
| MG-5 | LIBOR market model, closed-form layer and simulation (G4a, waves 3b and 3c) | `04-pricing/lmm.md` | G | Implemented | 53 of 53 (0 library object, 53 numpy or scipy primitive; D6, generated) |
| MG-6 | AAD ladder of the Bermudan scheme (Q3b) | `06-risk/aad-core.md` | G | Implemented | 0 of 3 (0 library object, 0 numpy or scipy primitive; D6, generated) |
| MG-7 | Model-reserve dispersion (Q9 part 2) | `06-risk/model-reserve.md` | G | Implemented | 0 of 6 (0 library object, 0 numpy or scipy primitive; D6, generated) |
| MG-8 | Deterministic xVA layer (G5b) | `06-risk/xva-framework.md` | G | Implemented | 0 of 24 (0 library object, 0 numpy or scipy primitive; D6, generated) |
| MG-9 | Portfolio exposure under Hull-White, ORE-checked (G5c) | `06-risk/xva-exposure-portfolio.md` | G | Implemented | 80 of 96 (80 library object, 0 numpy or scipy primitive; D6, generated) |
| MG-10 | F3 sensitivities (inflation01, dividend and borrow, correlation) | `06-risk/f3-sensitivities.md` | G | Implemented | 9 of 18 |
| MG-11 | FRTB-SA delta for FX, equity, CSR and commodity | `06-risk/frtb-sa-fx-equity.md` | G | Implemented | see entry |
| MG-12 | FRTB-SA vega and curvature | `06-risk/frtb-sa-vega-curvature.md` | G | Implemented | see entry |
| MG-13 | F4 portfolio-risk tools | `06-risk/portfolio-risk-tools.md` | G | Implemented | see entry |
| MG-14 | Heston and SABR calibration surrogate (A5, challenger) | `11-research/a5-surrogate.md` | G | Challenger only; acceptance harness, no surrogate trained yet | see entry |
| MI-1 | Hedge solvers (stage I wave 1) | `08-hedging/hedge-solvers.md` | I | Implemented | 57 of 88 (0 library object, 57 numpy or scipy primitive; D6, generated) |
| MI-2 | Credit and correlation hedges (stage I wave 2) | `08-hedging/credit-and-correlation-hedges.md` | I | Implemented | 19 of 19 (0 library object, 19 numpy or scipy primitive; D6, generated) |
| MI-3 | Cross-asset hedge, equity and rates (stage I wave 3) | `08-hedging/cross-asset-hedge.md` | I | Implemented | 9 of 9 (0 library object, 9 numpy or scipy primitive; D6, generated) |
| MI-4 | Hedge costs, impact, margin and the risk-against-cost frontier (stage I wave 4a) | `08-hedging/hedge-costs-and-frontier.md` | I | Implemented | 2 of 4 (0 library object, 2 numpy or scipy primitive; D6, generated) |
| MI-5 | Dynamic delta-hedge backtest and hedge effectiveness (stage I wave 4b) | `08-hedging/dynamic-hedge-and-effectiveness.md` | I | Implemented | 5 of 17 (0 library object, 5 numpy or scipy primitive; D6, generated) |
| MI-6 | Instrument selection (stage I wave 4c) | `08-hedging/instrument-selection.md` | I | Implemented | 10 of 10 (0 library object, 10 numpy or scipy primitive; D6, generated) |
| MI-7 | Hedge slippage report (stage I wave 4d) | `08-hedging/hedge-slippage.md` | I | Implemented | 0 of 6 (0 library object, 0 numpy or scipy primitive; D6, generated) |
| MJ-1 | Backtester (stage J wave 1) | `11-research/backtester.md` | J | Implemented (v0.9.0, four languages) | 14 of 14 value cases (stage J register, `oracle/OUTSIDE_SHARES.md`; not yet generated by `tools/inventory_counts.py`) |
| MJ-2 | Purged cross-validation (stage J wave 1) | `11-research/purged-cv.md` | J | Implemented (v0.9.0, four languages) | 12 of 15 value cases (stage J register, `oracle/OUTSIDE_SHARES.md`; not yet generated by `tools/inventory_counts.py`) |
| MJ-3 | Regime labelling (stage J wave 1) | `11-research/regimes.md` | J | Implemented (v0.9.0, four languages) | 10 of 10 value cases (stage J register, `oracle/OUTSIDE_SHARES.md`; not yet generated by `tools/inventory_counts.py`) |
| MJ-4 | Research statistics (stage J wave 1) | `11-research/research-statistics.md` | J | Implemented (v0.9.0, four languages) | 5 of 24 value cases (stage J register, `oracle/OUTSIDE_SHARES.md`; not yet generated by `tools/inventory_counts.py`) |
| MJ-5 | Portfolio optimisation (stage J wave 2) | `07-portfolio/optimisation.md` | J | Implemented (wave 2, v0.9.0), all four builds | 0 library checks (J-W2-15) |
| MJ-6 | Covariance and return estimation (stage J wave 2) | `07-portfolio/estimation.md` | J | Implemented (wave 2, v0.9.0), all four builds | 0 library checks (J-W2-15) |
| MJ-7 | Expected-shortfall backtest Z2 (stage J wave 2) | `06-risk/es-backtest.md` | J | Implemented (wave 2, v0.9.0), all four builds | 0 library checks (J-W2-15) |
| MJ-8 | Baum-Welch regime estimation (stage J wave 2) | `11-research/baum-welch.md` | J | Implemented (wave 2, v0.9.0), all four builds | 0 library checks (J-W2-15) |
| MJ-9 | Historical scenario stress (stage J wave 3) | `06-risk/scenario-stress.md` | J | Implemented (v0.9.0, four languages) | 8 of 13 value cases (numpy interp on the replays; the 5 historical-shock lookups are not counted) |
| MJ-10 | Interpolation backtests (stage J wave 3) | `11-research/interp-backtest.md` | J | Implemented (v0.9.0, four languages) | 16 of 16 value cases (numpy, scipy; the same interpolant calls that generated the goldens) |
| MJ-11 | Drift detectors (stage J wave 3) | `11-research/drift-detectors.md` | J | Implemented (v0.9.0, four languages) | 7 of 27 value cases (scipy KS exact; PSI, CUSUM and Page-Hinkley not counted) |
| MJ-12 | Financing term structure (stage J curves lane) | `02-curves/financing-term-structure.md` | J | Implemented (v0.9.0, four languages) | 0 library checks; 5 hand cases (J-C-9) |
| MJ-13 | Liquidity cost curve (stage J curves lane) | `10-execution/liquidity-curve.md` | J | Implemented (v0.9.0, four languages) | 0 library checks; 2 hand cases (J-C-9) |

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

### M24 Coupon schedule generation
- **Purpose:** regular coupon periods with one short first stub, business-day adjusted, with payment dates (`rates.schedule.generate`).
- **Inputs:** start and end dates, frequency in months, calendar, end-of-month flag, payment lag.
- **Limitations:** short first stub only; long stubs and ex-dividend periods are stage D; `MODIFIED_FOLLOWING` only.
- **Validation:** oracle `oracle/python/gen_stage_b.py`; suites `schedule` (7 cases) and `schedule_deep` (48 cases). The spec's acceptance is exact agreement with QuantLib `Schedule` (backward generation). Outside check (H-19, 2026-11-18): `oracle/python/outside_validation.py` compares every value case with QuantLib 1.44 `Schedule` and `Calendar.advance`; 53 of 54 agree exactly (`oracle/OUTSIDE_VALIDATION.json`, tag `quantlib-1.44-schedule`); QuantLib refuses the remaining degenerate case (end adjusts back onto start), which rests on the spec's rule 4. **Review:** 2026-11-18.
- **Tier:** 2.
- **Challenger:** the Python oracle against each of the three ported builds (Rust, Java, C++).
- **Monitoring thresholds:** any period date differing from the oracle (exact match required).
- **Data lineage hash:** sha256 77c6d2bdd6ec6430efc8f591b6ae70a1bea18a1c5e0699e2f13616fbd912d4f5 (`schedule`); sha256 a48de7508e7b29803800ac149acecc45546cf173a33534b75cdca88feee5e247 (`schedule_deep`).
- **Retirement trigger:** the stage D long-stub schedule superseding this operation, or a superseding ruling.
- **Validation report:** `specifications/02-curves/schedules.md`.

## Stage E models (E1 to E8)

Stage E is Implemented: all four languages pass every stage E golden (6,817 of 6,817 cases (value-checked and error cases counted together) in the full set at merge `597abf2`, 2026-11-08). 557 of the 895 stage E cases (62.2%) are outside-checked under rule 11.2.5 and rulings E-A17 and E-B28. Every input is synthetic; no entry is Validated. Last full review of these entries: 2026-11-08.

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

Evidence classes. Java: PIT on unit tests, full mutant set (observed, CI). C++ "before": local `--unit` runs on a 40-site sample, 0 timeouts (observed, local); the CI report's golden-only C++ scores are lower because they do not run the unit tests. Python and Rust "before": CI sample of 40 mutants, unit or golden (observed, CI). Every "after" score is a hand-applied survivor check: each surviving sampled mutant was applied by hand against the new tests (`cpp26/tests/test_boundaries_vol_credit.cpp`, first added as `test_mutants_e.cpp` in commit `996527c`, `python/tests/test_mutants_e.py`, `rust/crates/quantforge-core/tests/garch_mutants.rs`). It is not a fresh full mutation run. Remaining survivors are classed as equivalent by the author, with reasons in those test files; there is no second review (owner decision, 2026-11-18).

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

## Stage F, G and I models (MF-1 to MF-11 stage F; MG-1 to MG-14 stage G; MI-1 to MI-7 stage I)

Every entry carries the plan A2 fields. The data-lineage hash is the SHA-256 of the golden suite file that pins the model, as committed by the spec session (`sha256sum datasets/golden/stage_f/<suite>.json`); a golden regeneration changes it and must be recorded here. Tier: 1 = feeds prices or risk that a desk would act on; 2 = feeds analytics and reports; 3 = research or challenger.

| # | Model | Spec | Stage | Status | Outside-checked |
|---|---|---|---|---|---|
| MF-1 | CDS index option, Pedersen adjusted forward | `04-pricing/credit-options-and-copulas.md` | F (R7) | Implemented | none (no free outside source) |
| MF-2 | GARCH(1,1) estimate with standard errors, Student-t, demeaning | `05-volatility/garch.md` | F (R8) | Implemented | arch 7.2.0, 8 of 17 |
| MF-3 | VIX null-quote rule; local vol at slice expiries | `05-volatility/vix-index.md`, `05-volatility/local-and-forward-vol.md` | F (R10) | Implemented | VIX: Cboe sample calculation, 3 of 10 |
| MF-4 | Curve interpolation: monotone convex, monotonic log cubic, tension spline, hybrid | `02-curves/curve-framework.md` | F (Q1) | Implemented | 67 of 86 (QuantLib 1.44, SciPy quad) |
| MF-5 | Joint multi-curve solve with turns, futures-fitted steps and IFT Jacobian | `02-curves/joint-solve-and-funding.md` | F (Q4) | Implemented | 1 of 15 (QuantLib 1.44 rebuild with Jacobian) |
| MF-6 | Funding curve (spread over OIS) | `02-curves/joint-solve-and-funding.md` | F | Implemented | none |
| MF-7 | Book sensitivities: AAD reference, IFT zero Jacobian, PCA, cross gamma, jump to default | `06-risk/book-sensitivities.md` | F (Q3a, F3) | Implemented | PCA: SciPy; cross gamma: QuantLib (30 of 57) |
| MF-8 | VaR and ES (historical, filtered historical, parametric, Monte Carlo) and backtests | `06-risk/var-es-and-backtests.md` | F (Q2) | Implemented | SciPy, NumPy, arch (92 of 108) |
| MF-9 | FRTB-SA GIRR delta | `06-risk/frtb-sa-girr.md` | F (Q2) | Implemented | none (no worked example in MAR21) |
| MF-10 | Book lifecycle and end-of-day marks | `07-portfolio/book-lifecycle.md` | F (F5) | Implemented | none (own conventions) |
| MF-11 | Factor attribution (use case 4) | `04-pricing/use-cases.md` | F (F5) | Implemented | SciPy lstsq (24 of 27) |

### MF-1 CDS index option (Pedersen)
- **Purpose:** payer and receiver options on a CDS index with front-end protection inside the forward and the strike converted for the fixed coupon.
- **Inputs:** dates, flat index rate and hazard, recovery, strike spread, index coupon, notional, vol.
- **Limitations:** stylised legs (ruling E-B22), not the ISDA standard model; flat hazard for the strike annuity; Black on the adjusted pair is Pedersen's approximation, not his exact integral; no index factor or defaulted-name bookkeeping.
- **Validation:** parity `payer - receiver = N A (F_adj - K_adj)` on every pair; limit cases; five wrong conventions caught. The Pedersen (2003) worked example is not reproduced (paper not freely available). **Review:** 2026-11-09.
- **Tier:** 1 (prices a traded option).
- **Challenger:** Pedersen's exact model (lognormal loss-adjusted index value integrated numerically), stage G.
- **Monitoring thresholds:** parity residual above 1e-10 relative, or any golden outside 1e-9 per unit notional, fails conformance.
- **Data lineage hash:** sha256 ad2336be619b7ed8d6f51621479f34c7986ae8b0f5334dfebffa4444538d6f25
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
- **Data lineage hash:** sha256 e84b9fe4a6af37a249755f1545110840883360bd464f79898a559cb4eceeb457
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
- **Data lineage hash:** sha256 c2a308ff9004a417aa74c2c2c6c99f2458078c9ccc12debdae6c745eba5ac2c2; sha256 04a242b21faacd43475d19edbd9aa649614f07588a41a9b6a97d04674cf14491
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
- **Data lineage hash:** sha256 291dd8a43870fa08437b0557e65e93f50a61eb865b584ae5fc5bb76733cdcbbf
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
- **Data lineage hash:** sha256 9e85177418877d2d7de85f831f16863820248b9d93a154c0262696cf41fe208f
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
- **Data lineage hash:** sha256 9e85177418877d2d7de85f831f16863820248b9d93a154c0262696cf41fe208f
- **Retirement trigger:** a funding model with term structure from issued bonds and CDS supersedes the money-market version.
- **Validation report:** `specifications/02-curves/joint-solve-and-funding.md`.

### MF-7 Book sensitivities (Q3a, F3)
- **Purpose:** exact par-quote sensitivities of an OIS swap book and the zero-rate Jacobian of the curve (AAD in Rust, IFT elsewhere); principal components of curve moves; cross gamma on pillar zero rates; jump-to-default loss.
- **Inputs:** OIS quotes and a swap book; a matrix of curve changes; a curve object and an OIS trade; credit positions.
- **Limitations:** OIS books only for AAD; JTD without accrued premium or the FRTB default risk charge weighting; PCA rejects repeated eigenvalues.
- **Validation:** 40-digit IFT goldens (no bump in the golden); T row Q3a bounds; PCA against SciPy. **Review:** 2026-11-10.
- **Tier:** 1.
- **Challenger:** bump and revalue (`risk.curve.par`, R2).
- **Monitoring thresholds:** AAD outside `1e-10 + 1e-8 |ref|` of the Richardson bump in the Rust unit tests.
- **Data lineage hash:** sha256 4038828afe7c4244702949e846effbf7c2837adfab623c267bec655060e7fade
- **Retirement trigger:** AAD through every pricer replaces bump risk as the default (a later stage, by ADR).
- **Validation report:** `specifications/06-risk/book-sensitivities.md`; `oracle/outside_register_f.json`.

### MF-8 VaR, ES and backtests (Q2)
- **Purpose:** loss quantile and tail mean from historical, volatility-rescaled, normal and simulated P&L; Kupiec, Christoffersen and the Basel traffic light.
- **Inputs:** P&L or return series, positions, covariance, exception series.
- **Limitations:** one-asset FHS; normal parametric only; Monte Carlo on a multivariate normal; no liquidity horizon scaling.
- **Validation:** 40-digit replicas; SciPy and NumPy outside checks. **Review:** 2026-11-10.
- **Tier:** 1.
- **Challenger:** full revaluation against sensitivity P&L (`risk.pnl.explain`).
- **Monitoring thresholds:** a traffic-light zone of YELLOW or RED on the bank's own backtest.
- **Data lineage hash:** sha256 325cffa5419606d7099fe040897e0dc14f77b9836538c467f90448b2d72beaaa
- **Retirement trigger:** a full-revaluation historical engine on real positions (stage G and later).
- **Validation report:** `specifications/06-risk/var-es-and-backtests.md`.

### MF-9 FRTB-SA GIRR delta (Q2)
- **Purpose:** standardised capital for interest rate delta under MAR21.
- **Inputs:** delta sensitivities per currency, curve and tenor.
- **Limitations:** GIRR delta only; the `low` scenario formula is confirmed by the owner on 2026-11-10 against the MAR21.6 formula images (BIS page of 2026-03-23): rho_low = max(2 x rho - 100%; 75% x rho) and gamma_low = max(2 x gamma - 100%; 75% x gamma) (ruling F-33).
- **Validation:** 40-digit replica; tenor correlation reproduces MAR21.46 Table 2. **Review:** 2026-11-10.
- **Tier:** 1.
- **Challenger:** none free.
- **Monitoring thresholds:** a change in MAR21 parameters.
- **Data lineage hash:** sha256 19af72de698789e30aae463a478edb8686b86c0a49fd566adf72a70c00e2c7b9
- **Retirement trigger:** the full SBM (all risk classes, vega and curvature).
- **Validation report:** `specifications/06-risk/frtb-sa-girr.md`.

### MF-10 Book lifecycle and marks (F5)
- **Purpose:** positions, average cost and realised P&L through trades, expiry, default and rolls; fixings; end-of-day marks with source fallback and independent price verification.
- **Inputs:** opening positions and dated events; quote sources in priority order; independent prices.
- **Limitations:** average cost only; no corporate actions, settlement dates or multi-currency cash.
- **Validation:** exact rational replay. **Review:** 2026-11-10.
- **Tier:** 1.
- **Challenger:** none (own conventions).
- **Monitoring thresholds:** any IPV breach; any MISSING mark.
- **Data lineage hash:** sha256 9da28acc6934e4b88f5d32ca702a2ac32c0ba94216a03c6ab46c7897bd2b255b
- **Retirement trigger:** a lot-level book with settlement accounting.
- **Validation report:** `specifications/07-portfolio/book-lifecycle.md`.

### MF-11 Factor attribution (use case 4)
- **Purpose:** split a portfolio's mean return into factor contributions and alpha by least squares with an intercept.
- **Inputs:** portfolio and factor return series.
- **Limitations:** static betas over the window; no Brinson sector attribution.
- **Validation:** 40-digit normal equations; SciPy lstsq outside check. **Review:** 2026-11-10.
- **Tier:** 2.
- **Challenger:** rolling-window regression.
- **Monitoring thresholds:** `r_squared` below a desk-set floor.
- **Data lineage hash:** sha256 64021394cb4fe8252e1724f76054935cdee1a23eb8006db0925c767673efc6f5
- **Retirement trigger:** a holdings-based factor model.
- **Validation report:** `specifications/04-pricing/use-cases.md`.

### MG-1 One-factor short-rate models (G1)
- **Purpose:** zero-coupon bond prices and European bond options under Vasicek, CIR and Hull-White, and European swaptions on Hull-White by Jamshidian, sigma calibration, Bermudan swaptions by a pinned FD scheme, caps and floors under all three models, and issuer-callable bonds; the base of the stage G Bermudan, callable-bond and exposure models.
- **Inputs:** model parameters (`a`, `sigma`, `b`), short rate, and for Hull-White a log-linear discount curve.
- **Limitations:** one factor (perfectly correlated rates); constant parameters (no time-dependent `sigma`); Vasicek and Hull-White allow negative rates without bound; no market price of risk; calibration of `sigma` only with `a` fixed (wave 2c). Bermudan swaptions and callable bonds use a first-order reference scheme, and the goldens embed its bias: measured gaps of 0.17% to 1.2% against a refined grid (review, low items; plan row R6-25). The goldens pin the scheme, not the converged price.
- **Validation:** 50-digit mpmath replicas; QuantLib 1.44 `Vasicek`, `CoxIngersollRoss`, `HullWhite` outside check (61 of 78 bond cases, 33 of 40 swaption cases). **Review:** 2026-11-10.
- **Tier:** 1.
- **Challenger:** G2++ (`rates.g2pp.*`, wave 2b; QuantLib `G2` outside check, 30 of 38).
- **Monitoring thresholds:** calibration error once calibration lands.
- **Data lineage hash:** sha256 3defdc4d6df794b7deac5e9caaa70aa91845410365a9ff1342d88e014df2ea39 (`shortrate_g`); aee7b1b9e7f78a730de81a1578af139895ed1bf13f7462e347353b5064fce1ba (`swaption_g`); 71c1f5c30547898916e4d9271ecb602a8008c03cde1cf5279d73014a90753b2d (`g2pp_g`); f2f683d408b844b83fa054864b36bf089491c6c6a277f701a1045c69d75c0a49 (`hwcal_g`); bfb7a473ab04fac0d7c67e1ec50d08736c14d3b2be63a2a64492ee52c6e624af (`bermudan_g`); f444c1dddfe9d2faa43e4eff2b9870df184761531264a389d6f3e3c2b125a1bf (`capfloor_g`); f0f6e80f5740683fc4da985dd249517ea3184118b9829202369badf520fc1352 (`swaption_affine_g`); db24a20790d13d0e3bfe0b00e76f86c0d6f634a4b024d221ea63e7196ce5f923 (`callable_g`)
- **Lineage regenerated 2026-11-11:** the hashes of shortrate_g, swaption_g, g2pp_g, bermudan_g, capfloor_g and callable_g were refreshed after later stage G commits (among them the R5 fixes 21237dc and the G-50 corrections f2243bd) appended or corrected cases; values are the SHA-256 of the committed files at `stage-g-int`.
- **Retirement trigger:** a multi-factor or market model for the desk's products.
- **Validation report:** `specifications/04-pricing/short-rate-models.md`.

### MG-2 Discrete barrier correction (R9)
- **Purpose:** price discretely monitored barriers by the Broadie-Glasserman-Kou shift of the continuous formula.
- **Inputs:** as `exotic.barrier.price`, plus monitoring frequency.
- **Limitations:** an approximation; error grows when spot is near the barrier or monitoring is sparse (monthly); flat vol only.
- **Validation:** exact-date Monte Carlo within 3 SE at daily monitoring (`oracle/R9_ACCEPTANCE.json`). **Review:** 2026-11-10.
- **Tier:** 2.
- **Challenger:** exact-date Monte Carlo.
- **Monitoring thresholds:** BGK against MC beyond 3 SE on a desk sample.
- **Data lineage hash:** sha256 482a63c90c04c1a63cf1841be39f194bcd11597df670d8927fac522d71e34f08
- **Lineage regenerated 2026-11-11:** the hashes of barrier_g were refreshed after later stage G commits (among them the R5 fixes 21237dc and the G-50 corrections f2243bd) appended or corrected cases; values are the SHA-256 of the committed files at `stage-g-int`.
- **Retirement trigger:** a PDE or MC barrier engine in the library.
- **Validation report:** `specifications/04-pricing/exotics.md`, section "Stage G addition".

### MG-3 Monte Carlo Greeks (Q9 part 1)
- **Purpose:** delta and vega of GBM payoffs by pathwise, likelihood-ratio, smoothed-digital and common-draw bump estimators, with standard errors.
- **Inputs:** Black-Scholes inputs, payoff, method, paths and seed; smoothing width or bump size.
- **Limitations:** one-step GBM only (no path-dependent payoffs yet); three payoffs; the smoothed digital is biased by `O(eps^2)`.
- **Validation:** float64 replica on the `core.rng` stream; Black-Scholes closed forms (`oracle/Q9_ACCEPTANCE.json`). **Review:** 2026-11-10.
- **Tier:** 2.
- **Challenger:** closed-form Greeks where they exist.
- **Monitoring thresholds:** MC Greek beyond 3 SE of a closed form on a desk sample.
- **Data lineage hash:** sha256 f166dba11c41869d3fce6bf2b1ccb1db29c49c024ae95c2a3e458e83d4a75be4
- **Lineage regenerated 2026-11-11:** the hashes of mcgreeks_g were refreshed after later stage G commits (among them the R5 fixes 21237dc and the G-50 corrections f2243bd) appended or corrected cases; values are the SHA-256 of the committed files at `stage-g-int`.
- **Retirement trigger:** AAD through the MC engine (Q3b) for smooth payoffs.
- **Validation report:** `specifications/06-risk/mc-greeks.md`.

### MG-4 Closed-form swap exposure and CVA (G5a)
- **Purpose:** discounted expected exposure of a vanilla swap under Hull-White at its reset dates, and a bucketed unilateral CVA; the exact anchor for the simulated exposure engine.
- **Inputs:** Hull-White model and curve; swap times, rate, side, notional; exposure dates; flat hazard and recovery.
- **Limitations:** single swap, no netting or collateral; reset dates only; independence of default and rates (no wrong-way risk); flat hazard; single curve.
- **Validation:** 50-digit Jamshidian; QuantLib 1.44 `HullWhite` objects (7 of 15 as typed at v0.8.0; the current D6 count is generated in the summary table). **Review:** 2026-11-10.
- **Tier:** 1.
- **Challenger:** the simulated exposure engine (next xVA wave) and ORE.
- **Monitoring thresholds:** simulated EE beyond 3 SE of these values.
- **Data lineage hash:** sha256 f3ddc91403fa738130721d6c29116a7e4fbfdc9ba43a0779d515949cdbdd36f2
- **Lineage regenerated 2026-11-11:** the hashes of exposure_g were refreshed after later stage G commits (among them the R5 fixes 21237dc and the G-50 corrections f2243bd) appended or corrected cases; values are the SHA-256 of the committed files at `stage-g-int`.
- **Retirement trigger:** the netting-set simulation engine.
- **Validation report:** `specifications/06-risk/xva-exposure.md`.

### MG-5 LIBOR market model, closed-form layer and simulation (G4a, waves 3b and 3c)
- **Purpose:** caplets and floorlets in Black form on the integrated abcd variance, and European swaptions by Rebonato's frozen-weight formula with exponential correlation; the terminal-measure simulation is judged against the caplets.
- **Inputs:** discount curve; abcd volatility; correlation decay `beta`; period or payment times, strike, notional.
- **Limitations:** lognormal forwards only (no negative forwards; shifted or normal LMM later, G-24); single curve; Rebonato is an approximation (0.4-0.5% from the simulation, evidence only, G-25); no calibration to market caps yet.
- **Validation:** 50-digit mpmath; QuantLib 1.44 `AbcdFunction`, `DiscountCurve`, `blackFormula` (17 of 26 and 36 of 42); simulation acceptance six caplets within 3 SE (`oracle/LMM_ACCEPTANCE.json`). **Review:** 2026-11-11.
- **Tier:** 1.
- **Challenger:** the simulated LMM (wave 3c) for swaptions; Hull-White caps (`capfloor_g`) for the short end.
- **Monitoring thresholds:** caplet acceptance outside 3 SE, or a Rebonato error above 1% against the simulation.
- **Data lineage hash:** sha256 f07163a3e2957dc3bb5f69619586c04757c930013fff1de65ad8dd09aecd5a2f (`lmmcap_g`); 70a67eeeb7899af24d27d7eb6d9d6f53a53b297133748169bfb23432d23f121b (`lmmswn_g`)
- **Retirement trigger:** a calibrated multi-curve LMM or SABR-LMM for the desk's cap and swaption books.
- **Validation report:** `specifications/04-pricing/lmm.md`.

### MG-6 AAD ladder of the Bermudan scheme (Q3b)
- **Purpose:** price plus the full curve, `a` and `sigma` ladder of the G-18 Hull-White Bermudan scheme by reverse-mode AAD.
- **Inputs:** the `rates.shortrate.bermudan_swaption` inputs.
- **Limitations:** derivative of the discrete scheme at the case grid, **not for hedging at the default grid 101/50** with the default method `G18_IMPLICIT` (for `method` `CN_RANNACHER_SMOOTHED` see MK-5: restriction lifted 2026-11-19, KR-110) (curve entries 15% to 18% from the converged model; golden `aadladder_r6` at 501/250 is within 0.99% of 801/400; convergence not monotone; fix in stage K item K-8; `oracle/R6_LADDER_GRIDS.json`); undefined where a bump moves an exercise decision across a node (such cases are dropped); no performance number recorded by the spec session.
- **Validation:** Richardson central differences, two pairs agreeing within 1e-9 relative (3 value cases). **Review:** 2026-11-11.
- **Tier:** 1.
- **Challenger:** bump-and-reprice with Richardson extrapolation (the golden reference itself).
- **Monitoring thresholds:** AAD against bump beyond `1e-10 + 1e-8 |ref|`, or the G-9 cost ratio above 5.
- **Data lineage hash:** sha256 2ad88cb8807f0aa3a0e71d5df3214e6ad5042d9c1e8e8b7d47288dbf0c367d55 (`aadladder_g`)
- **Retirement trigger:** an AAD tape covering every stage G pricer.
- **Validation report:** `specifications/06-risk/aad-core.md`.

### MG-7 Model-reserve dispersion (Q9 part 2)
- **Purpose:** the spread of one exotic's prices across models (range, half range, reserve against the booked model).
- **Inputs:** prices by model name; the booked model.
- **Limitations:** the statistic only; the Heston, local vol and SLV report is registered (G-36) and not yet run; multi-asset exotics out of scope.
- **Validation:** exact rational arithmetic (6 value cases). **Review:** 2026-11-11.
- **Tier:** 2.
- **Challenger:** a reserve from a calibrated model family (Cont 2006 worst case over the set).
- **Monitoring thresholds:** a relative reserve above a desk-set limit on any exotic.
- **Data lineage hash:** sha256 ba612cb1d337bf8acb73733f9e870ba83ef27a2516f009b878f89e88e3b8d113 (`reserve_g`)
- **Retirement trigger:** a prudent-valuation model-risk AVA process (EU 2016/101 Article 11).
- **Validation report:** `specifications/06-risk/model-reserve.md`.

### MG-8 Deterministic xVA layer (G5b)
- **Purpose:** collateralised exposure with netting sets, CSA thresholds, MTA, independent amount and MPoR; CVA, DVA, FCA, FBA (DVA overlap rule), MVA, KVA; SIMM-style IR delta margin; Hull-White wrong-way CVA.
- **Inputs:** simulated paths per trade; CSA terms; exposure, discount, IM and capital profiles; hazard and recovery; sensitivities with weights and correlations.
- **Limitations:** paths are inputs (no simulation here); SIMM weights are inputs, not an ISDA calibration; bucket-end exposure; independence except in the WWR model.
- **Validation:** 50-digit mpmath, asserted limit cases (zero thresholds give zero exposure, `b = 0` gives the independent CVA). **Review:** 2026-11-11.
- **Tier:** 1.
- **Challenger:** ORE's collateral and xVA engine: not run (no stage set). ORE checks only MG-9.
- **Monitoring thresholds:** any asserted limit case failing, or exposure differing from ORE beyond 3 SE once compared.
- **Data lineage hash:** sha256 fef567a51bb097b31a202ab9ab1536819849f12f42fe8f801e7e2375e29b8647 (`collexp_g`); d51113f2e26b021d3e71ab18fa992782592b2c727640c68efe9c21bc0b33de39 (`xvaadj_g`); 2b477e2f2be440985d9c41e1d767609483f591aa00642543e9959f6f906d512b (`simm_g`); d7f291fe26868f3174c9696986b050ae38e60d98e000937ea6c01957352582db (`wwr_g`)
- **Retirement trigger:** a full simulated xVA engine with the bank's CSA library.
- **Validation report:** `specifications/06-risk/xva-framework.md`.

### MG-9 Portfolio exposure under Hull-White, ORE-checked (G5c)
- **Purpose:** discounted EE, ENE, PFE 95/99, EPE and CVA of netting sets of swaps at common reset dates, by exact one-factor integration.
- **Inputs:** curve, `a`, `sigma`; swaps of the set; exposure times; quantiles; hazard and recovery.
- **Limitations:** common annual resets only; no collateral; PFE is a quantile of the discounted exposure under the LGM measure; 16 of 96 value cases do not meet the registered ORE check (G-42; stage share 71.7% of value-checked cases under the tight rule D6, `oracle/OUTSIDE_SHARES.md`), G-42b carried to stage I, then to stage J (not run at v0.8.1) (G-52).
- **Validation:** 40-digit and binary64 quadrature, self-check P = q at each PFE; ORE 1.8.17 within 3 MC SE (80 of 102, `oracle/ore/ORE_CHECK_4C.json`). **Review:** 2026-11-11.
- **Tier:** 1.
- **Challenger:** ORE 1.8.17 simulation (LGM), and the wave 4a Jamshidian EE for single swaps.
- **Monitoring thresholds:** EE or CVA against ORE beyond the G-42 bound on a rerun.
- **Data lineage hash:** sha256 49b806c2c32644e5ac4a9faa4a9902cee2e8a5e2125f6074e614c4ae9f7465ba (`expsim_g`)
- **Retirement trigger:** a multi-factor or cross-currency exposure engine.
- **Validation report:** `specifications/06-risk/xva-exposure-portfolio.md`.

### MG-10 F3 sensitivities (inflation01, dividend and borrow, correlation)
- **Purpose:** inflation01 of a zero-coupon inflation swap; dividend and borrow sensitivities of a European option; correlation sensitivity of an exchange option.
- **Inputs:** swap terms and inflation rate; option terms with yield and borrow; two-asset Margrabe terms.
- **Limitations:** closed-form products only; book-level bump-and-reprice across all pricers is not in this slice.
- **Validation:** 50-digit mpmath; QuantLib 1.44 `dividendRho` and Margrabe central bump (9 of 18 as typed at v0.8.0; the current D6 count is generated in the summary table). **Review:** 2026-11-11.
- **Tier:** 2.
- **Challenger:** bump-and-reprice on the full pricers.
- **Monitoring thresholds:** analytic against bump beyond 1e-6 relative.
- **Data lineage hash:** sha256 eabc21e88a41947948b81ef7eeb31a36c3a884597ff298e4f564c4ee7f24b7d7 (`risk_f3b`)
- **Retirement trigger:** book-level AAD sensitivities for every risk factor.
- **Validation report:** `specifications/06-risk/f3-sensitivities.md`.

### MG-11 FRTB-SA delta for FX, equity, CSR and commodity
- **Purpose:** sensitivities-based delta charge for four more risk classes with the three correlation scenarios.
- **Inputs:** weighted-sensitivity inputs per class, bucket and risk factor.
- **Limitations:** CSR securitisations out of scope; inputs are the caller's sensitivities.
- **Validation:** 50-digit mpmath on the MAR21 text and the owner-supplied PDF (Table 5 checked); no outside implementation. **Review:** 2026-11-11.
- **Tier:** 1.
- **Challenger:** a vendor FRTB engine on the same sensitivities.
- **Monitoring thresholds:** any difference from a vendor engine on a shared portfolio.
- **Data lineage hash:** sha256 b0976e56e10fb32a2249a1668256b82a56650483b3897abe26d1e52e0e21a7d3 (`frtb_f2b`)
- **Retirement trigger:** a regulatory engine approved for reporting.
- **Validation report:** `specifications/06-risk/frtb-sa-fx-equity.md`.

### MG-12 FRTB-SA vega and curvature
- **Purpose:** vega and curvature charges for GIRR, CSR non-securitisations, equity, commodity and FX.
- **Inputs:** vega sensitivities with maturities; CVR up and down per risk factor.
- **Limitations:** CVR inputs are bank-computed; CSR securitisations out of scope.
- **Validation:** 50-digit mpmath on the owner-supplied Basel PDF (MAR21.4, 21.5, 21.92 to 21.101); no outside implementation. **Review:** 2026-11-11.
- **Tier:** 1.
- **Challenger:** a vendor FRTB engine on the same inputs.
- **Monitoring thresholds:** any difference from a vendor engine on a shared portfolio.
- **Data lineage hash:** sha256 cb9f26e439ed29b7c8033aec1055ffc7b1b09872d8053d485373274c751971cb (`frtb_f2c`)
- **Retirement trigger:** a regulatory engine approved for reporting.
- **Validation report:** `specifications/06-risk/frtb-sa-vega-curvature.md`.

### MG-13 F4 portfolio-risk tools
- **Purpose:** reverse stress along a direction, limit utilisation, concentration (HHI), liquidity-adjusted VaR (Bangia), volatility by horizon under AR(1).
- **Inputs:** delta and gamma with a direction; measures and limits; exposures; VaR with spreads; daily volatility and autocorrelation.
- **Limitations:** delta-gamma reverse stress only; exogenous spreads; AR(1) only.
- **Validation:** 50-digit mpmath closed forms (16 value cases). **Review:** 2026-11-11.
- **Tier:** 2.
- **Challenger:** full revaluation reverse stress; empirical multi-day volatility.
- **Monitoring thresholds:** reverse-stress scale against full revaluation beyond 1%.
- **Data lineage hash:** sha256 8256155601beadbe35795813c559a3ddcade7d708fabfc1051f4db467d809347 (`risk_f4b`)
- **Retirement trigger:** an enterprise limits and stress platform.
- **Validation report:** `specifications/06-risk/portfolio-risk-tools.md`.

### MG-14 Heston and SABR calibration surrogate (A5, challenger)
- **Purpose:** a cheap implied-volatility approximation for calibration, accepted only against a fixed 110,000-point test set.
- **Inputs:** Heston or SABR parameters, log-moneyness, expiry inside the G-11 box.
- **Limitations:** challenger only, never in goldens or the four-language conformance; no surrogate trained yet; refuses inputs outside the box.
- **Validation:** acceptance harness self-test (exact pricer passes, 2 bp shift and unguarded pricer fail); Lewis reference checked against QuantLib to 1.6e-14. **Review:** 2026-11-11.
- **Tier:** 3.
- **Challenger:** the full Lewis and Hagan pricers (the reference).
- **Monitoring thresholds:** any test-set point above 1 bp, the 99.9th percentile above 0.5 bp, or a missing domain error.
- **Data lineage hash:** sha256 harness `oracle/python/a5_acceptance.py` (no golden suite by G-11)
- **Retirement trigger:** a surrogate that fails the acceptance after a model or domain change.
- **Validation report:** `specifications/11-research/a5-surrogate.md`.

### MI-1 Hedge solvers (stage I wave 1)
- **Purpose:** hedge positions by constrained weighted least squares (bounds, equalities, ridge, minimum-norm), integer lots, minimum-variance ratios, Black-Scholes-Merton delta, gamma and vega neutralisation, beta futures; residual risk report.
- **Inputs:** instrument sensitivities by risk factor, the book's existing risk, weights, constraints; covariances or return series; flat Black-Scholes-Merton market.
- **Limitations:** costs, liquidity and margin are in MI-4 and instrument selection in MI-6; at v0.8.0 the largest golden was 6 by 4, so the scalable method (I-48) rests on unit tests (review finding 7; goldens at n = 50 and 200 are R6-6); the rank test is not invariant to instrument units (finding 21, R6-6); `MIN_NORM` refuses bounds; integer lots need a strictly convex problem; Greek hedges use one flat volatility.
- **Validation:** active-set enumeration at 50 digits with KKT re-check; exact rational enumeration for integer lots; HiGHS confirms infeasibility; scipy, numpy and QuantLib outside checks (44 of 121 as typed at v0.8.0; the current D6 count is generated in the summary table). **Review:** 2026-11-11.
- **Tier:** 2.
- **Challenger:** scipy 1.18 `lsq_linear` (BVLS) and `minimize` (SLSQP) on the same problems.
- **Monitoring thresholds:** a KKT residual above 1e-8 of the gradient scale, or a hedge effectiveness below the desk's floor on the dynamic backtest (MI-5).
- **Data lineage hash:** sha256 0a45713450573d2bbf6f9f363269f572b86cd577033258c3fd82ad123c512f8e (`hedgeqp_i`); 8659c72326be4654ac75059b61319efd96ffb472f8adb99ef7117b55a10a071c (`hedgeint_i`); 2cd58f846b05db9a4f43ea70f78fe842cd240c25559411e96eff3a301c5a1cbc (`hedgemv_i`); e013dbe82448fecfe4c1c9bbcea8ca0f7ce06a50978c09499db1e40ecd1e06d8 (`hedgegreeks_i`); 03f02bc3a95fcc215d27d652df70d66ed2642abe33439e7bef198fcd31b7e87e (`hedgebeta_i`); 2531eeb9dc4eddd57cf4d9dfb6c577ffb62bb583487d1b40845b0731762d1794 (`hedgeres_i`); d7ddbc7b28ad0cf16ead1e02e50be1e013e0f158c38c3ee8b7c9cc94b723aac5 (`hedgegreeks5_i`, wave 5); 8e6030343dabc17948b78be0e8960faee5dbcdf55193cad0e707575921038d5d (`hedgemv5_i`, wave 5); ae1842ca8734960cd4ffb90e990c9976c23c8dfac249cfbd7715781dc2418e2b (`hedgeqp5_i`, wave 5)
- **Lineage regenerated 2026-11-11:** `hedgeint_i` hash refreshed after a second check (a wide-box float search with the I-7 tie rule) was added to its `verified_by` lists; no value or error code changed.
- **Lineage regenerated 2026-11-11 (after the builds):** `hedgegreeks_i`, `hedgeint_i`, `hedgemv_i` gained computed cases for rulings I-41, I-42, I-44, I-45; earlier cases unchanged.
- **Retirement trigger:** a hedge that needs costs or non-convex constraints the solver cannot express.
- **Validation report:** `specifications/08-hedging/hedge-solvers.md`.

### MI-2 Credit and correlation hedges (stage I wave 2)
- **Purpose:** CDS hedges against CS01 (parallel and bucketed hazard bumps) and jump to default; correlation, vega and delta hedges of two-asset exchange-option books.
- **Inputs:** ISDA CDS market (discount, hazard, recovery) and trades; two-asset Black-Scholes-Merton market with correlation; exchange options, vanillas, underlyings.
- **Limitations:** single-name CDS only; CS01 is a hazard bump, not a quote re-bootstrap; recovery not hedged; two assets, flat volatilities.
- **Validation:** QuantLib IsdaCdsEngine and Margrabe engine outside checks (19 of 39 as typed at v0.8.0; the current D6 count is generated in the summary table); same-contract hedge returns its notional. **Review:** 2026-11-11.
- **Tier:** 2.
- **Challenger:** QuantLib 1.44 `IsdaCdsEngine` and `AnalyticEuropeanMargrabeEngine` on the same trades.
- **Monitoring thresholds:** targeted risk after the hedge above 1e-6 of the book's, or a hedge notional above 10 times the book's on a regular matrix.
- **Data lineage hash:** sha256 c73a9d5138891138da19b7fda4d48768e610baebfa059a755e8d1be3a3e25931 (`hedgecredit_i`); 0d673c90931655b80d5797f28ddfa7b152969aa017efc6e8af643810f9c726d3 (`hedgecorr_i`); 42d960e1b6ca1ad8d6751341a3ff937e0e49dbbf45c5d378d8552a85db555863 (`hedgecorr5_i`, wave 5)
- **Retirement trigger:** a desk need for index, tranche or recovery hedges.
- **Validation report:** `specifications/08-hedging/credit-and-correlation-hedges.md`.

### MI-3 Cross-asset hedge, equity and rates (stage I wave 3)
- **Purpose:** one weighted least-squares hedge of a book's equity move and key-rate risks with forwards, options, bonds and the underlying.
- **Inputs:** spot, dividend yield, flat volatility, a linear-in-zero discount curve; book and hedge instruments; factor weights.
- **Limitations:** one equity, one curve, no extrapolation beyond the last pillar; the singularity test depends on instrument units (I-22).
- **Validation:** QuantLib ZeroCurve and AnalyticEuropeanEngine outside check on every value case (9 of 17 as typed at v0.8.0; the current D6 count is generated in the summary table). **Review:** 2026-11-11.
- **Tier:** 2.
- **Challenger:** QuantLib 1.44 values with numpy least squares on the same risk definitions.
- **Monitoring thresholds:** residual equity or key-rate risk above the desk's limit after the hedge.
- **Data lineage hash:** sha256 ac4424db9b094def5344ca102b4da3e08252472ffce4ec85440423ac9b2b6dc2 (`hedgexa_i`)
- **Retirement trigger:** a multi-curve or dividend-term-structure need.
- **Validation report:** `specifications/08-hedging/cross-asset-hedge.md`.

### MI-4 Hedge costs, impact, margin and the risk-against-cost frontier (stage I wave 4a)
- **Purpose:** weighted least-squares hedge with spread cost, linear market impact, liquidity bounds and a margin limit; frontier of risk against cost.
- **Inputs:** the `hedge.qp.solve` inputs plus half-spreads, impact coefficients, cost weight(s), margin rates and limit.
- **Limitations:** linear impact only (no square-root impact); the hedge starts from no position; margin is per instrument with no netting. No build caps the instrument count below the 200 of ruling I-4 (I-48: Java and C++ replaced their 20-instrument orthant enumeration with a sign-state active-set method), and costs are exact at a hold/not-hold switch point (I-54, `hedgecost_i-0023`).
- **Validation:** 50-digit state enumeration with subgradient checks; wave 1 goldens reproduced exactly; HiGHS infeasibility; scipy BVLS, trust-constr and SLSQP outside checks (15 of 33 as typed at v0.8.0; the current D6 count is generated in the summary table). **Review:** 2026-11-11.
- **Tier:** 2.
- **Challenger:** scipy 1.18 trust-constr and SLSQP on the split-variable QP.
- **Monitoring thresholds:** a frontier that is not monotone, or a realised cost above the modelled cost by more than the desk's tolerance.
- **Data lineage hash:** sha256 fc651b04e30a976effc3cbcbe9bb84e2f858d422b1c201e482c1460689e74afc (`hedgecost_i`); 7e4a0069d2d7eb68d4c4f2153ef2fdaff4a4e75b98f4e0ef368c4dfbb37246b7 (`hedgefrontier_i`)
- **Retirement trigger:** a need for square-root impact or portfolio margin.
- **Validation report:** `specifications/08-hedging/hedge-costs-and-frontier.md`.

### MI-5 Dynamic delta-hedge backtest and hedge effectiveness (stage I wave 4b)
- **Purpose:** replay a delta hedge of one European option on a given path with a self-financing cash account; dollar-offset, regression and variance-reduction effectiveness.
- **Inputs:** option, quantity, rate, dividend yield, hedge volatility, a dated spot path; or two series of value changes.
- **Limitations:** flat hedge volatility, no transaction costs in the replay, continuous dividend yield; the dollar offset is unstable for small item changes.
- **Validation:** QuantLib AnalyticEuropeanEngine on every date and numpy statistics outside checks on every value case (12 of 25 as typed at v0.8.0; the current D6 count is generated in the summary table). **Review:** 2026-11-11.
- **Tier:** 2.
- **Challenger:** QuantLib 1.44 values on each date with the same cash arithmetic; numpy regression.
- **Monitoring thresholds:** a live hedge's regression R² below 0.8 or dollar offset outside [0.8, 1.25] over a quarter.
- **Data lineage hash:** sha256 2de452d8b296754bb2626f530d4cebd982863e5fb34afe2e025c080f72ae566a (`hedgebt_i`); 785a5ae423b3f45dc831f7557e048dfd1014e6759313796547fa055389a6dd20 (`hedgeeff_i`); 4d8d4cf5d70a3dbd497fe4678a656409b137d1be9303d054ecc3750ff1dbbbb8 (`hedgebtcost_i`, wave 4e: costs in the backtest); cff4f2c54880a5bbed20a1656092ad86ce2fc5d4fcd258c1fb38506035bc1c2c (`hedgeeff5_i`, wave 5)
- **Lineage regenerated 2026-11-11 (after the builds):** `hedgebt_i` gained case 0016 for ruling I-43; earlier cases unchanged.
- **Retirement trigger:** a need for cost-aware rebalancing or stochastic-volatility hedging.
- **Validation report:** `specifications/08-hedging/dynamic-hedge-and-effectiveness.md`.

### MI-6 Instrument selection (stage I wave 4c)
- **Purpose:** the best weighted least-squares hedge using at most K of n instruments.
- **Inputs:** the `hedge.qp.solve` inputs without equalities, and K.
- **Limitations:** exhaustive search, at most 20 instruments and at most 100,000 candidate subsets (`E_LIMIT`, ruling I-53, `hedgeselect_i-0018`); no fixed cost per instrument; bounds must admit zero.
- **Validation:** 50-digit solve of every subset; scipy per-subset outside check (10 of 17 as typed at v0.8.0; the current D6 count is generated in the summary table); greedy counterexample pinned. **Review:** 2026-11-11.
- **Tier:** 2.
- **Challenger:** the same enumeration with scipy solvers.
- **Monitoring thresholds:** a selected hedge whose residual risk exceeds the full hedge's by more than the desk's tolerance.
- **Data lineage hash:** sha256 4d1d1d7168fd2628dfb2c2d1de57f39fc2885b19d5932f2b56397730ec128f02 (`hedgeselect_i`)
- **Retirement trigger:** universes above 20 instruments or fixed costs per instrument.
- **Validation report:** `specifications/08-hedging/instrument-selection.md`.

### MI-7 Hedge slippage report (stage I wave 4d)
- **Purpose:** implementation shortfall of executed hedge orders (execution and opportunity cost) and slippage against the wave 4a cost model.
- **Inputs:** orders with decision and final prices, cost-model parameters and fills.
- **Limitations:** one decision-price benchmark; fees not separated; no estimation across many hedges.
- **Validation:** exact rational arithmetic with the shortfall and slippage identities asserted; no outside library (0 of 12 as typed at v0.8.0; the current D6 count is generated in the summary table). **Review:** 2026-11-11.
- **Tier:** 3.
- **Challenger:** none; the identities are the check.
- **Monitoring thresholds:** mean slippage over a month above zero by more than two standard errors (the cost model is optimistic).
- **Data lineage hash:** sha256 b296e48d8f4919622a433d1a14fa05ed96d54222c2a2e125fbde831e9c66347e (`hedgeslip_i`)
- **Retirement trigger:** a benchmark other than the decision price becomes the desk standard.
- **Validation report:** `specifications/08-hedging/hedge-slippage.md`.

## Review cycle

Each stage's definition of done adds entries for its new models and re-dates every entry it touched. An entry moves to *Validated* only with a dated report on real data against an independent benchmark. The R5 audit uses a different model from the spec session and reads this register.

### MJ-1 Backtester (stage J wave 1)
- **Purpose:** event loop, order and fill model, costs, P&L and attribution.
- **Inputs:** as in the spec page.
- **Limitations:** research tool, tier 3; descriptive results only, no claim of out-of-sample profit; page limits replace the general array limit (ruling J-20); see the spec page for the rest.
- **Validation:** oracle `oracle/python/gen_stage_j_w1.py`; vectorbt 1.2.1 `Portfolio.from_orders` outside check on 14 of 14 value cases (`oracle/OUTSIDE_J.json`); operations `research.backtest.run` pass 15,514 of 15,514 conformance cases (value-checked, error and invariance cases counted together) in all four languages with the rest of the suite (2026-11-15, contract 1.15.0). **Review:** 2026-11-14.
- **Tier:** 3.
- **Challenger:** the Python oracle against each of the three ported builds (Rust, Java, C++).
- **Monitoring thresholds:** a P&L identity break (cash plus marked position minus costs) above 1e-9 of gross notional.
- **Data lineage hash:** sha256 f43ab5b2af1a846ff465185a5b30eff75cecbf8e54058dfb03cf6b52a5d1a72b (`backtest_j`).
- **Retirement trigger:** a superseding stage J ruling.
- **Validation report:** `specifications/11-research/backtester.md`.

### MJ-2 Purged cross-validation (stage J wave 1)
- **Purpose:** purged and embargoed k-fold splits for time-ordered research data.
- **Inputs:** as in the spec page.
- **Limitations:** research tool, tier 3; descriptive results only, no claim of out-of-sample profit; page limits replace the general array limit (ruling J-20); see the spec page for the rest.
- **Validation:** oracle `oracle/python/gen_stage_j_w1.py`; timeseriescv 0.2, scikit-learn 1.9.1 `KFold` and skfolio 1.12.12 outside checks on 12 of 15 value cases (`oracle/OUTSIDE_J.json`); operations `research.cv.purged_kfold`, `research.cv.cpcv_paths` pass 15,514 of 15,514 conformance cases (value-checked, error and invariance cases counted together) in all four languages with the rest of the suite (2026-11-15, contract 1.15.0). **Review:** 2026-11-14.
- **Tier:** 3.
- **Challenger:** the Python oracle against each of the three ported builds (Rust, Java, C++).
- **Monitoring thresholds:** any test index that overlaps a training label interval.
- **Data lineage hash:** sha256 8e2c26af318d1f82a9044fb94bbfa640d7e7b395337e3f5e72d92564159e7602 (`purgedcv_j`).
- **Retirement trigger:** a superseding stage J ruling.
- **Validation report:** `specifications/11-research/purged-cv.md`.

### MJ-3 Regime labelling (stage J wave 1)
- **Purpose:** descriptive regime labels (Viterbi path on a given hidden Markov model).
- **Inputs:** as in the spec page.
- **Limitations:** research tool, tier 3; descriptive results only, no claim of out-of-sample profit; page limits replace the general array limit (ruling J-20); see the spec page for the rest.
- **Validation:** oracle `oracle/python/gen_stage_j_w1.py`; brute-force path enumeration on 5 cases; hmmlearn 0.3.3 Viterbi decode outside check on 10 of 10 value cases (`oracle/OUTSIDE_J.json`); operations `research.regime.viterbi` pass 15,514 of 15,514 conformance cases (value-checked, error and invariance cases counted together) in all four languages with the rest of the suite (2026-11-15, contract 1.15.0). **Review:** 2026-11-14.
- **Tier:** 3.
- **Challenger:** the Python oracle against each of the three ported builds (Rust, Java, C++).
- **Monitoring thresholds:** a path whose log-likelihood is below the brute-force best on any monitored model.
- **Data lineage hash:** sha256 bf1c3b6cede3608c473c39ce6e73ca9a24ea8b077e49007dfec4cc50f6cabf10 (`regime_j`).
- **Retirement trigger:** a superseding stage J ruling.
- **Validation report:** `specifications/11-research/regimes.md`.

### MJ-4 Research statistics (stage J wave 1)
- **Purpose:** deflated Sharpe ratio, PBO and related research statistics.
- **Inputs:** as in the spec page.
- **Limitations:** research tool, tier 3; descriptive results only, no claim of out-of-sample profit; page limits replace the general array limit (ruling J-20); see the spec page for the rest.
- **Validation:** oracle `oracle/python/gen_stage_j_w1.py`; textbook and hand cases; statsmodels 0.15.0 `NormalIndPower` outside check on the 5 power cases; DSR, PSR and PBO have no library check yet (5 of 24 value cases, `oracle/OUTSIDE_J.json`); operations `research.stats.dsr`, `.psr`, `.power`, `.pbo` pass 15,514 of 15,514 conformance cases (value-checked, error and invariance cases counted together) in all four languages with the rest of the suite (2026-11-15, contract 1.15.0). **Review:** 2026-11-14.
- **Tier:** 3.
- **Challenger:** the Python oracle against each of the three ported builds (Rust, Java, C++).
- **Monitoring thresholds:** a PBO or DSR that moves by more than its stated tolerance when the inputs are permuted.
- **Data lineage hash:** sha256 39bc63000fd78c04875f543b306d470a520fb280715991edb5056bf55c2845f7 (`rstats_j`).
- **Retirement trigger:** a superseding stage J ruling.
- **Validation report:** `specifications/11-research/research-statistics.md`.

### MJ-5 Portfolio optimisation (stage J wave 2)
- **Purpose:** mean-variance, risk parity and Euler risk contributions.
- **Inputs:** as in the spec page.
- **Limitations:** research tool, tier 3; built in Python, Rust, Java and C++ and merged to `main` (PR #40, 2026-11-14), each build passing every golden case of its suite; see the spec page.
- **Validation:** oracle `oracle/python/gen_stage_j_w2.py`; exact KKT certificate per mean-variance case; scipy SLSQP agreement within 1.8e-8; outside checks since J-W2-16: DAQP 0.11.2 (mean-variance), cvxpy 1.9.3 with Clarabel 0.11.1 (risk parity, 33 of 35 `optim_j` value cases with the two misses explained in Tutorial 25), autograd 1.9.1 (Euler); per case in `oracle/OUTSIDE_J.json`. **Review:** 2026-11-14.
- **Tier:** 3.
- **Challenger:** the Python oracle against each build once built.
- **Monitoring thresholds:** KKT residual above 1e-9 or risk-parity shares off budget by more than 1e-10.
- **Data lineage hash:** sha256 71afd0f9995240e31d4dba0fdd459a34c3b855a3ac7deb983f365d4588a35ef1 (`optim_j`).
- **Retirement trigger:** a superseding stage J ruling.
- **Validation report:** `specifications/07-portfolio/optimisation.md`.

### MJ-6 Covariance and return estimation (stage J wave 2)
- **Purpose:** Ledoit-Wolf shrinkage and the Black-Litterman posterior.
- **Inputs:** as in the spec page.
- **Limitations:** research tool, tier 3; built in Python, Rust, Java and C++ and merged to `main` (PR #40, 2026-11-14), each build passing every golden case of its suite; see the spec page.
- **Validation:** oracle `oracle/python/gen_stage_j_w2.py`; two algebraic forms equal in exact arithmetic for both estimators; outside checks since J-W2-16 and J-W2-23: scikit-learn 1.9.1 `LedoitWolf` and PyPortfolioOpt 1.6.0 Black-Litterman reproduce all 19 value-checked `estim_j` cases (`oracle/OUTSIDE_J.json`). **Review:** 2026-11-14.
- **Tier:** 3.
- **Challenger:** the Python oracle against each build once built.
- **Monitoring thresholds:** shrinkage outside [0, 1] or a non-symmetric output.
- **Data lineage hash:** sha256 06928d23c0aa75488cf0c5bfc184afc67aaec9d7b9aff0bc53b68075b815031a (`estim_j`).
- **Retirement trigger:** a superseding stage J ruling.
- **Validation report:** `specifications/07-portfolio/estimation.md`.

### MJ-7 Expected-shortfall backtest Z2 (stage J wave 2)
- **Purpose:** the Acerbi-Szekely Z2 statistic.
- **Inputs:** as in the spec page.
- **Limitations:** research tool, tier 3; built in Python, Rust, Java and C++ and merged to `main` (PR #40, 2026-11-14), each build passing every golden case of its suite; see the spec page.
- **Validation:** oracle `oracle/python/gen_stage_j_w2.py`; hand case; size study (J-8) is research-lane gap G13. **Review:** 2026-11-14.
- **Tier:** 3.
- **Challenger:** the Python oracle against each build once built.
- **Monitoring thresholds:** Z2 not equal to 1 on a series with no exceptions.
- **Data lineage hash:** sha256 3801dbe21a026bbb46d6a25a03355075a2723f18f6c8813fa24dcbf79eb14ef8 (`esbt_j`).
- **Retirement trigger:** a superseding stage J ruling.
- **Validation report:** `specifications/06-risk/es-backtest.md`.

### MJ-8 Baum-Welch regime estimation (stage J wave 2)
- **Purpose:** Gaussian HMM parameters by EM.
- **Inputs:** as in the spec page.
- **Limitations:** research tool, tier 3; built in Python, Rust, Java and C++ and merged to `main` (PR #40, 2026-11-14), each build passing every golden case of its suite; see the spec page.
- **Validation:** oracle `oracle/python/gen_stage_j_w2.py`; one-state closed form; log-space forward pass re-checks every log-likelihood; hmmlearn 0.3.3 checks the `baumwelch_j` value cases it can reproduce (J-W2-16; per case in `oracle/OUTSIDE_J.json`). **Review:** 2026-11-14.
- **Tier:** 3.
- **Challenger:** the Python oracle against each build once built.
- **Monitoring thresholds:** a log-likelihood decrease above 1e-9 relative between iterations.
- **Data lineage hash:** sha256 c50b9b94932f0d24e397b866f2efe461f68488318820bda3f2e09bee5c0d4385 (`baumwelch_j`).
- **Retirement trigger:** a superseding stage J ruling.
- **Validation report:** `specifications/11-research/baum-welch.md`.

### MJ-9 Historical scenario stress (stage J wave 3)
- **Purpose:** measure a historical yield-curve move between two stored dates and replay it on a curve and DV01 ladder.
- **Inputs:** as in the spec page; shock library `datasets/scenarios/us_treasury_shocks.json` (Treasury par yields, H.15-checked).
- **Limitations:** research tool, tier 3; one historical path per scenario, not a distribution; linear interpolation in tenor, flat outside; par yields, not zero rates. **Review:** 2026-11-15.
- **Validation:** oracle `oracle/python/gen_stage_j_w3.py` in exact fractions; H.15 match on all 88 start and end values; numpy `interp` on the 8 replay value cases (`oracle/OUTSIDE_J.json`); the 5 historical-shock cases are a date lookup plus arithmetic and are not counted.
- **Tier:** 3.
- **Challenger:** the Python oracle against each build; the H.15 release for the data.
- **Monitoring thresholds:** a library value differing from H.15 by more than 0.005 percentage points.
- **Data lineage hash:** sha256 380fb95c17d673dd4dd4757460b5cb83c4b0a0478990e23eeae61f82c7e04c7c (`scen_j`).
- **Retirement trigger:** a superseding stage J ruling.
- **Validation report:** `specifications/06-risk/scenario-stress.md`.

### MJ-10 Interpolation backtests (stage J wave 3)
- **Purpose:** leave-one-knot-out and held-out-strike errors of the core interpolants.
- **Inputs:** as in the spec page.
- **Limitations:** research tool, tier 3; errors at quoted points understate errors between quotes; B1 failed on a synthetic SSVI surface, real option quotes not tested (`research/interp_backtest/RESULTS.md`). **Review:** 2026-11-15.
- **Validation:** oracle `oracle/python/gen_stage_j_w3.py`; numpy and scipy interpolants on all 16 value cases (the calls that generated the goldens, so a weak second check).
- **Tier:** 3.
- **Challenger:** the Python oracle against each build; scipy interpolants.
- **Monitoring thresholds:** the B1 and B2 pass rules of the spec page.
- **Data lineage hash:** sha256 74646ff7a0befd72eb3e4d1d8523cd75313b6d792006b9048972750c76e5aff0 (`interpbt_j`).
- **Retirement trigger:** a superseding stage J ruling.
- **Validation report:** `specifications/11-research/interp-backtest.md`.

### MJ-11 Drift detectors (stage J wave 3)
- **Purpose:** CUSUM, Page-Hinkley, PSI and two-sample KS for change detection.
- **Inputs:** as in the spec page.
- **Limitations:** research tool, tier 3; operating characteristics (A3 study) not yet measured, prereg `research/preregs/A3-drift.md` unsigned; CUSUM and Page-Hinkley have no outside library check. **Review:** 2026-11-15.
- **Validation:** oracle `oracle/python/gen_stage_j_w3.py` (rational re-implementation, hand cases); scipy `ks_2samp` exact on 7 of the 8 KS value cases; PSI, CUSUM and Page-Hinkley have no counted outside check.
- **Tier:** 3.
- **Challenger:** the Python oracle against each build; the A3 study once run.
- **Monitoring thresholds:** the A3 pass rules (CUSUM ARL0 in [400, 540], median delay at most 15).
- **Data lineage hash:** sha256 de5884e4660a3953dce47720870f2b2b41b6076381e0a0bbd34dcb3dd828ee27 (`drift_j`).
- **Retirement trigger:** a superseding stage J ruling.
- **Validation report:** `specifications/11-research/drift-detectors.md`.

### MJ-12 Financing term structure (stage J curves lane)
- **Purpose:** term repo spread and stock borrow curves over the funding curve, and the equity forward that carries on them (`repo.term.curve`, `eq.forward.term_financed`).
- **Inputs:** funding zero rates, simple term repo quotes, term-average borrow fees, query times or a forward's spot, maturity and dividends.
- **Limitations:** one year-fraction axis, no extrapolation, no collateral classes; extends ruling D22 without changing the stage D operations (J-C-2); see the spec page.
- **Validation:** oracle `oracle/python/gen_stage_j_curves.py` (mpmath, 50 digits); 5 hand cases; no outside library or published example (J-C-9); suite `termfin_j` passes 33 of 33 in all four languages (2026-11-15, contract 1.15.0, local). **Review:** 2026-11-15.
- **Tier:** 2.
- **Challenger:** the Python oracle against each of the four builds; the D22 flat-case reduction property test in each language.
- **Monitoring thresholds:** a quote that does not round-trip to 1e-13.
- **Data lineage hash:** sha256 2407b175b6da0cd2d6b9dab585015e002e6f318a632f4c1a0faf477809e86eeb (`termfin_j`).
- **Retirement trigger:** a superseding ruling.
- **Validation report:** `specifications/02-curves/financing-term-structure.md`.

### MJ-13 Liquidity cost curve (stage J curves lane)
- **Purpose:** cost per unit by order size and liquidation horizon: half spread, square-root impact, timing risk, optimal horizon (`liq.curve.cost`).
- **Inputs:** half spread, daily volume and volatility, impact coefficient and exponent, risk multiplier, sizes, horizons.
- **Limitations:** assumed parameters, not calibrated; even trading only; no permanent impact or resilience; FRTB liquidity horizons not built (J-C-6).
- **Validation:** oracle `oracle/python/gen_stage_j_curves.py`; 2 hand cases; no outside library (J-C-9); suite `liqcurve_j` passes 18 of 18 in all four languages (2026-11-15, contract 1.15.0, local). **Review:** 2026-11-15.
- **Tier:** 3.
- **Challenger:** the Python oracle against each of the four builds; the optimum-is-a-minimum property test in each language.
- **Monitoring thresholds:** the one-day, exponent 1/2 impact differing from stage H `exec.impact.sqrt`.
- **Data lineage hash:** sha256 97453653a9c27a1f1a0c4c3044cad141549911e87ffde2091a7c55e55bde5ee6 (`liqcurve_j`).
- **Retirement trigger:** calibration in stage H item H-1, or a superseding ruling.
- **Validation report:** `specifications/10-execution/liquidity-curve.md`.

## Stage H (v0.10.0, not tagged)

Entries for the stage H specs, confirmed 2026-11-18 (spec version 0.1.0, rulings HR-1 to HR-41; HR-42 to HR-55 for paper trading; HR-56 for wave 1 input rules; HR-80 to HR-120 for the multi-asset round; HR-121 to HR-129 from the different-model audit of 2026-11-19, which reported 0 Critical, 17 Major and 15 Minor findings, all ruled, with three code faults fixed in all four builds). The wave 1 operations (MH-6 to MH-10, and use case 5) are implemented in all four languages on branch `stage-h` with a generated suite in `datasets/golden/stage_h/` (63 cases with `e1_h`, each build passes all, local, 2026-11-18); their outside check is a blind second-lane re-derivation or a printed paper figure (DR-H2), 23 of 29 value cases, no library. The wave 2 operations (book rebuild, lit matching, dark pool, router) are implemented in all four languages on branch `stage-h2` (round 2, 2026-11-18); round 3 adds the estimators, venue analytics, adaptive algos, TCA and the `paper.*` operations, all in four languages. Round 4 adds the multi-asset conventions and venues (MH-17 to MH-20), in all four languages. Stage H has 160 of 205 value cases (78.0%) outside-checked by DR-H2 blind re-derivation or printed paper figures, none by a library (`oracle/OUTSIDE_SHARES.md`). A blind lane reads the same rules as the first lane, so it catches arithmetic and convention slips, not a wrong rule (the HR-120 compliance dates were corrected by reading the SEC order). Each entry is re-dated when its operation lands.

### MH-1 Order book rebuild (stage H wave 1b)
- **Purpose:** MBP book rebuilt from the Kraken v2 L2 feed, checksum, crossed, locked and gap counting (`micro.book.rebuild`, H-2).
- **Inputs:** as in the spec page.
- **Limitations:** spec confirmed 2026-11-18; implemented in all four languages; see the spec page. Real data is the Kraken crypto venue only (lit); simulated venues are labelled.
- **Validation:** generated suite `ob_h`, passed by every build (observed, local, 2026-11-18); blind re-derivation (DR-H2), counts per plan item in `oracle/OUTSIDE_SHARES.md`. **Review:** 2026-11-18.
- **Tier:** 3.
- **Challenger:** the venue's CRC32 checksum on every recorded message or row.
- **Monitoring thresholds:** any checksum failure on a form B row with `ok = true`, or any form A failure.
- **Data lineage hash:** sha256 9a269a85e55d99fd5f01e3791c232b558e3b6b0d302687d95ddf6505caeed2ad (`ob_h`, 17 cases) (2026-11-18).
- **Retirement trigger:** a superseding stage H ruling.
- **Validation report:** `specifications/09-microstructure/order-book.md`.

### MH-2 Low-latency order book (stage H wave 1b)
- **Purpose:** the same book as MH-1 built for speed; per-message latency, allocation-free hot path, CI regression gate (H-9).
- **Inputs:** as in the spec page.
- **Limitations:** spec confirmed 2026-11-18; implemented in all four languages; see the spec page. Real data is the Kraken crypto venue only (lit); simulated venues are labelled.
- **Validation:** generated suite `ob_h`, passed by every build (observed, local, 2026-11-18); blind re-derivation (DR-H2), counts per plan item in `oracle/OUTSIDE_SHARES.md`. **Review:** 2026-11-18.
- **Tier:** 3.
- **Challenger:** MH-1 (Python reference) on the same stream, exact `top(100)` equality.
- **Monitoring thresholds:** p99 above the CI threshold of HR-24, or any steady-state allocation in C++ or Rust.
- **Data lineage hash:** sha256 9a269a85e55d99fd5f01e3791c232b558e3b6b0d302687d95ddf6505caeed2ad (`ob_h`, 17 cases) (2026-11-18).
- **Retirement trigger:** a superseding stage H ruling.
- **Validation report:** `specifications/09-microstructure/low-latency-book.md`.

### MH-3 Simulated lit matching engine (stage H wave 1b)
- **Purpose:** price-time matching with limit, market, IOC, FOK, iceberg, post-only and pegged orders (`exec.sim.lit.run`).
- **Inputs:** as in the spec page.
- **Limitations:** spec confirmed 2026-11-18; implemented in all four languages; see the spec page. Real data is the Kraken crypto venue only (lit); simulated venues are labelled.
- **Validation:** generated suite `lit_h`, passed by every build (observed, local, 2026-11-18); blind re-derivation (DR-H2), counts per plan item in `oracle/OUTSIDE_SHARES.md`. **Review:** 2026-11-18.
- **Tier:** 3.
- **Challenger:** the Python oracle against each ported build; invariants (no crossed book, quantity conserved, FIFO).
- **Monitoring thresholds:** any invariant break in the property tests.
- **Data lineage hash:** sha256 9a14b16085baccbc95018550ce6b35ec1585ebaf5ad16810db3354574ed8d9a6 (`lit_h`, 20 cases) (2026-11-18).
- **Retirement trigger:** a superseding stage H ruling.
- **Validation report:** `specifications/10-execution/lit-matching.md`.

### MH-4 Simulated dark pool (stage H wave 1b)
- **Purpose:** midpoint crossing, minimum quantity, conditionals, fill probability and markouts (`exec.sim.dark.run`).
- **Inputs:** as in the spec page.
- **Limitations:** spec confirmed 2026-11-18; implemented in all four languages; see the spec page. Real data is the Kraken crypto venue only (lit); simulated venues are labelled.
- **Validation:** generated suite `dark_h`, passed by every build (observed, local, 2026-11-18); blind re-derivation (DR-H2), counts per plan item in `oracle/OUTSIDE_SHARES.md`. **Review:** 2026-11-18.
- **Tier:** 3.
- **Challenger:** Monte Carlo of the same model for the Laplace-inversion fill probability; lifelines for Kaplan-Meier.
- **Monitoring thresholds:** planted leakage not recovered within 3 SE.
- **Data lineage hash:** sha256 10292d4d34eb80313b639cf44d36a2237e15827481e19326b2e10505f2e7f228 (`dark_h`, 8 cases) (2026-11-18).
- **Retirement trigger:** a superseding stage H ruling.
- **Validation report:** `specifications/10-execution/dark-pool.md`.

### MH-5 Smart order router (stage H wave 1b)
- **Purpose:** Cont-Kukanov split across simulated lit and dark venues (`exec.sor.allocate`), scored against single-venue routing.
- **Inputs:** as in the spec page.
- **Limitations:** spec confirmed 2026-11-18; implemented in all four languages; see the spec page. Real data is the Kraken crypto venue only (lit); simulated venues are labelled.
- **Validation:** generated suite `sor_h`, `sorx_h`, passed by every build (observed, local, 2026-11-18); blind re-derivation (DR-H2), counts per plan item in `oracle/OUTSIDE_SHARES.md`. **Review:** 2026-11-18.
- **Tier:** 3.
- **Challenger:** `SAMPLE_AVERAGE` against `STOCHASTIC_APPROX` and Prop. 3 closed form.
- **Monitoring thresholds:** router split outside 3 SE of the planted optimum.
- **Data lineage hash:** sha256 ccaf2af583fa8147998539b039b49189d20b0d485477004ac0f1ae9897890132 (`sor_h`, 9 cases); sha256 67ee66847d2f62fe75dc5b489ddbf7b8d5689ad371d32fbe28ae3d8e5c6b8d00 (`sorx_h`, 2 cases) (2026-11-18).
- **Retirement trigger:** a superseding stage H ruling.
- **Validation report:** `specifications/10-execution/smart-order-router.md`.

### MH-6 Almgren-Chriss trajectory and frontier (stage H wave 1)
- **Purpose:** optimal liquidation trajectory and efficient frontier (`exec.ac.trajectory`, `exec.ac.frontier`).
- **Inputs:** as in the spec page.
- **Limitations:** spec confirmed 2026-11-18; implemented in all four languages; see the spec page. Real data is the Kraken crypto venue only (lit); simulated venues are labelled.
- **Validation:** golden values written in the spec, blind re-derived (DR-H2); generated suite `ac_h`, passed by every build (observed, local, 2026-11-18). **Review:** 2026-11-18.
- **Tier:** 3.
- **Challenger:** blind re-derivation (DR-H2) and printed [AC00] figures.
- **Monitoring thresholds:** trajectory or frontier off the closed form by more than 1e-12.
- **Data lineage hash:** sha256 788f27b90a995537f547c0a3abe1783e75095db22ecaeade4e369dfdf0aac9b4 (`ac_h`, 10 cases) (2026-11-18).
- **Retirement trigger:** a superseding stage H ruling.
- **Validation report:** `specifications/10-execution/almgren-chriss.md`.

### MH-7 Market impact (stage H wave 1)
- **Purpose:** square-root and Obizhaeva-Wang transient impact (`exec.impact.sqrt`, `exec.impact.ow_optimal`).
- **Inputs:** as in the spec page.
- **Limitations:** spec confirmed 2026-11-18; implemented in all four languages; see the spec page. Real data is the Kraken crypto venue only (lit); simulated venues are labelled.
- **Validation:** golden values written in the spec, blind re-derived (DR-H2); generated suite `imp_h`, passed by every build (observed, local, 2026-11-18). **Review:** 2026-11-18.
- **Tier:** 3.
- **Challenger:** printed paper figures and blind re-derivation.
- **Monitoring thresholds:** calibrated exponent standard error not reported (H-1).
- **Data lineage hash:** sha256 af5c20a676f01adf754c3870178be92f97db29e343f9f8aae05aafc5cf318c88 (`imp_h`, 9 cases) (2026-11-18).
- **Retirement trigger:** a superseding stage H ruling.
- **Validation report:** `specifications/10-execution/impact.md`.

### MH-8 Execution schedules (stage H wave 1)
- **Purpose:** TWAP, VWAP and POV schedules (`exec.schedule.*`).
- **Inputs:** as in the spec page.
- **Limitations:** spec confirmed 2026-11-18; implemented in all four languages; see the spec page. Real data is the Kraken crypto venue only (lit); simulated venues are labelled.
- **Validation:** golden values written in the spec, blind re-derived (DR-H2); generated suite `sched_h`, passed by every build (observed, local, 2026-11-18). **Review:** 2026-11-18.
- **Tier:** 3.
- **Challenger:** hand cases and blind re-derivation.
- **Monitoring thresholds:** slices not summing to the order (HR-3).
- **Data lineage hash:** sha256 f08bdfdf4ef15ba7f454eb8078357da4856b34f09d3e7f26a44dbfc46ec2ea78 (`sched_h`, 13 cases) (2026-11-18).
- **Retirement trigger:** a superseding stage H ruling.
- **Validation report:** `specifications/10-execution/schedules.md`.

### MH-9 Implementation shortfall TCA (stage H wave 1)
- **Purpose:** Perold decomposition into delay, execution, opportunity and fees (`exec.tca.shortfall`).
- **Inputs:** as in the spec page.
- **Limitations:** spec confirmed 2026-11-18; implemented in all four languages; see the spec page. Real data is the Kraken crypto venue only (lit); simulated venues are labelled.
- **Validation:** golden values written in the spec, blind re-derived (DR-H2); generated suite `tca_h`, passed by every build (observed, local, 2026-11-18). **Review:** 2026-11-18.
- **Tier:** 3.
- **Challenger:** hand cases and blind re-derivation.
- **Monitoring thresholds:** decomposition not summing to the total to 1e-10.
- **Data lineage hash:** sha256 ab5c8ce760fe7beb843b6395cfe7430e25a063a3e36edb37d9f99ba929f0f7ea (`tca_h`, 6 cases) (2026-11-18).
- **Retirement trigger:** a superseding stage H ruling.
- **Validation report:** `specifications/10-execution/tca.md`.

### MH-10 Avellaneda-Stoikov quotes (stage H wave 1)
- **Purpose:** inventory-aware market-making quotes (`micro.mm.as_quotes`).
- **Inputs:** as in the spec page.
- **Limitations:** spec confirmed 2026-11-18; implemented in all four languages; see the spec page. Real data is the Kraken crypto venue only (lit); simulated venues are labelled.
- **Validation:** golden values written in the spec, blind re-derived (DR-H2); generated suite `as_h`, passed by every build (observed, local, 2026-11-18). **Review:** 2026-11-18.
- **Tier:** 3.
- **Challenger:** [AS08] printed tables and blind re-derivation.
- **Monitoring thresholds:** quotes off the closed form by more than 1e-10.
- **Data lineage hash:** sha256 c664b079cad0301165975dbb75373a7b40afcc43cc2c2d3b69289c15477b1196 (`as_h`, 7 cases) (2026-11-18).
- **Retirement trigger:** a superseding stage H ruling.
- **Validation report:** `specifications/09-microstructure/avellaneda-stoikov.md`.

### MH-11 Paper trading: ledger, book and pre-trade checks (stage H, H-21)
- **Purpose:** a simulated paper book with a hash-chained append-only ledger, positions, cash, financing, daily P&L explain and pre-trade risk checks (`specifications/10-execution/paper-trading.md`).
- **Inputs:** as in the spec page; decimal strings throughout (HR-44).
- **Limitations:** the book, explain and fill path are Python (`paper.py`, `paper_fills.py`); the `paper.*` CLI operations are in all four languages; simulated fills only, from the lit, dark and router simulators (HR-47), with a TCA record per order; labelled "crypto venue; simulated"; never live orders (HR-42); the dashboard is stage K.
- **Validation:** goldens `pt_h` (28) and `e1_hpt` (5), passed by the Python build; the blind lane matched values on some and checked only the shape of others (SHAPE-ONLY is not an outside check). **Review:** 2026-11-18.
- **Tier:** 3.
- **Challenger:** `sha256sum` on the canonical bytes of `pt_h-0020`; blind re-derivation (DR-H2).
- **Monitoring thresholds:** P&L explain residual not exactly zero (HR-53); a ledger record without the label fails `verify` (HR-43).
- **Data lineage hash:** sha256 ab5bf3bf7604b7695d3c524f794416a1b75de983302025e8eb55c81d81d9475f (`pt_h`, 34 cases); sha256 bdc23fa1f7fa045a770f3af19905e97b332cdab1152e5f08b9e50485c95ec49c (`e1_hpt`, 5 cases) (2026-11-18).
- **Retirement trigger:** a superseding stage H ruling.
- **Validation report:** `specifications/10-execution/paper-trading.md`.

### MH-12 Microstructure estimators (stage H round 3)
- **Purpose:** arrival, cancel, resilience, liquidity decay, adverse selection, regime impact and passive-versus-aggressive estimators (`micro.est.*`, H-4b), in all four languages.
- **Inputs:** as in the spec page.
- **Limitations:** spec confirmed 2026-11-18; see the spec page. Inputs are synthetic or simulated; no claim on real markets.
- **Validation:** generated suite `mest_h`, passed by every build (observed, local, 2026-11-18); blind re-derivation (DR-H2), counts in `oracle/OUTSIDE_SHARES.md`. **Review:** 2026-11-18.
- **Tier:** 3.
- **Challenger:** blind re-derivation, 7 of 7 value cases (`program/STAGE_H_BLIND_MICRO.md`); planted-truth simulations (HR-71).
- **Monitoring thresholds:** a planted parameter not recovered within 3 standard errors.
- **Data lineage hash:** sha256 f01d89526ee09b2dd55f7f72f5c7d4b53ca25839595515214c9e3f3a83c99b9a (`mest_h`, 18 cases) (2026-11-18).
- **Retirement trigger:** a superseding stage H ruling.
- **Validation report:** `specifications/09-microstructure/micro-estimators.md`.

### MH-13 Venue analytics (stage H round 3)
- **Purpose:** markouts, fill rates and toxicity per venue (`exec.venue.analytics`, H-16), in all four languages.
- **Inputs:** as in the spec page.
- **Limitations:** spec confirmed 2026-11-18; see the spec page. Inputs are synthetic or simulated; no claim on real markets.
- **Validation:** generated suite `venue_h`, passed by every build (observed, local, 2026-11-18); blind re-derivation (DR-H2), counts in `oracle/OUTSIDE_SHARES.md`. **Review:** 2026-11-18.
- **Tier:** 3.
- **Challenger:** second, fresh blind re-derivation, 5 of 5 value cases (`program/STAGE_H_BLIND_MICRO.md`).
- **Monitoring thresholds:** any golden differing from its exact value.
- **Data lineage hash:** sha256 cbbb2292c02937117f4e2362968c3a9be40c2781fb714522e9496b950230c1ce (`venue_h`, 10 cases) (2026-11-18).
- **Retirement trigger:** a superseding stage H ruling.
- **Validation report:** `specifications/10-execution/venue-analytics.md`.

### MH-14 Adaptive algorithms (stage H round 3)
- **Purpose:** arrival price, close, liquidity seeking, pairs and baskets (`exec.algo.*`, H-14), in all four languages.
- **Inputs:** as in the spec page.
- **Limitations:** spec confirmed 2026-11-18; see the spec page. Inputs are synthetic or simulated; no claim on real markets.
- **Validation:** generated suite `alg_h`, passed by every build (observed, local, 2026-11-18); blind re-derivation (DR-H2), counts in `oracle/OUTSIDE_SHARES.md`. **Review:** 2026-11-18.
- **Tier:** 3.
- **Challenger:** blind re-derivation; all value cases agree (`program/STAGE_H_BLIND_EXEC.md`).
- **Monitoring thresholds:** schedule identities broken by more than 1e-10.
- **Data lineage hash:** sha256 2f590f8eae3cc2834bb456cbb808fb9c9dd562f16ee4eed16134a91732efd3ed (`alg_h`, 25 cases) (2026-11-18).
- **Retirement trigger:** a superseding stage H ruling.
- **Validation report:** `specifications/10-execution/adaptive-algos.md`.

### MH-15 Pre-trade TCA and cost attribution (stage H round 3)
- **Purpose:** `exec.tca.pretrade` and `exec.tca.attribution` (H-17), in all four languages.
- **Inputs:** as in the spec page.
- **Limitations:** spec confirmed 2026-11-18; see the spec page. Inputs are synthetic or simulated; no claim on real markets.
- **Validation:** generated suite `tcx_h`, passed by every build (observed, local, 2026-11-18); blind re-derivation (DR-H2), counts in `oracle/OUTSIDE_SHARES.md`. **Review:** 2026-11-18.
- **Tier:** 3.
- **Challenger:** blind re-derivation; all value cases agree (`program/STAGE_H_BLIND_EXEC.md`).
- **Monitoring thresholds:** attribution not summing to the total within 1e-10.
- **Data lineage hash:** sha256 28665d1672d6ce6af70627a0b0fa97330756ea929aadc82d5b99532dcd0681ee (`tcx_h`, 11 cases) (2026-11-18).
- **Retirement trigger:** a superseding stage H ruling.
- **Validation report:** `specifications/10-execution/tca-pretrade.md`.

### MH-16 Library interfaces (R4) (stage H round 3)
- **Purpose:** typed execution and microstructure layer (Python `exec_api`, Java validated records) stating thread safety per public type (H-5).
- **Inputs:** as in the spec page.
- **Limitations:** spec confirmed 2026-11-18; see the spec page. Inputs are synthetic or simulated; no claim on real markets.
- **Validation:** unit tests in Python and Java; first local p50/p99 timing (Windows laptop), not the acceptance machine. **Review:** 2026-11-18.
- **Tier:** 3.
- **Challenger:** none outside the project.
- **Monitoring thresholds:** p99 above the target fixed before any timing.
- **Data lineage hash:** none (no golden suite; the interfaces are checked by unit tests).
- **Retirement trigger:** a superseding stage H ruling.
- **Validation report:** `specifications/10-execution/library-interfaces.md`.

### MH-17 Equity, FX and rates conventions (stage H round 4, H-22 to H-24)
- **Purpose:** tick rounding, fee cap, round lot, T+1 settlement (`micro.eq.*`); pip value and spot date (`micro.fx.*`); 32nds, tick value, bond and bill price and bond yield (`micro.rates.*`).
- **Inputs:** as in the spec page; decimal strings (HR-12); integers within +-(2^53-1) (HR-116).
- **Limitations:** calendars are inputs; on-coupon-date bond only (off-date pricing reuses `04-pricing`); third digit of 32nds: CME quarter digits 0, 2, 5, 7 only (source read 2026-11-19); eighth-tick contracts (2-year and 3-year notes) not supported (HR-118); outputs carry no label (HR-111). Rule dates are per rule (HR-120): tick table and fee cap default `compliance_date` 2027-11-01, round lot 2025-11-03; with no `as_of` the amended text applies, which for ticks and fees is not in force before 2027-11-01. USDCAD T+1 has no primary source read (HR-119).
- **Validation:** goldens `eqc_h`, `fxc_h`, `rtc_h` with E1 cases in `e1_h4`; blind re-derivation (DR-H2) per `oracle/OUTSIDE_SHARES.md`. **Review:** 2026-11-18.
- **Tier:** 3.
- **Challenger:** blind second lane (`stage_h_blind/multiasset/`, rates packet 2).
- **Monitoring thresholds:** acceptance A3 properties (rounding never more aggressive; parse(format(x)) = x on the 1/128 grid; spot a good day and at least T+1).
- **Data lineage hash:** goldens `datasets/golden/stage_h/eqc_h.json`, `fxc_h.json`, `rtc_h.json` (generator `oracle/python/gen_stage_h_ma.py`).
- **Retirement trigger:** a superseding stage H ruling or a rule change (HR-120 compliance dates: the SEC has the deferred tick and fee rules under review, so 2027-11-01 may move).
- **Validation report:** `specifications/09-microstructure/asset-conventions.md`.

### MH-18 Simulated equity auction (stage H round 4, H-22)
- **Purpose:** opening and closing call-auction uncrossing (`exec.sim.auction.uncross`) and session phases in the lit engine (HR-112).
- **Inputs:** as in the spec page.
- **Limitations:** simulated venue, labelled "simulated venue; not a real exchange"; tie-break rules fixed by ruling HR-84, not one exchange's rulebook (two steps of the default are the simulator's own, HR-119); no cross means no auction (HR-127); the continuous book does not join the closing cross.
- **Validation:** goldens `auc_h`, `ses_h`; blind share H-22 66.7 % (20 of 30, with blind packet 3 of 2026-11-19). **Review:** 2026-11-18.
- **Tier:** 3.
- **Challenger:** blind second lane; property: volume maximal over the candidate grid (A3).
- **Monitoring thresholds:** any golden difference across the four builds.
- **Data lineage hash:** `datasets/golden/stage_h/auc_h.json`, `ses_h.json`.
- **Retirement trigger:** a superseding stage H ruling.
- **Validation report:** `specifications/10-execution/auction.md`.

### MH-19 Simulated FX dealer venue with last look (stage H round 4, H-23)
- **Purpose:** streamed quotes and request handling with a price-move and a random last-look reject (`exec.sim.fx.stream`, `exec.sim.fx.request`).
- **Inputs:** as in the spec page; the draw from `core.rng` stream `request_index` (HR-97), `request_index` within 0..2^32-1 (HR-116).
- **Limitations:** a stated toy, not any dealer's practice; labelled "simulated venue; not a real exchange; no real FX data"; FX Global Code Principle 17 read 2026-11-19; the thresholds and the random reject are the spec's own, not from the Code (HR-119).
- **Validation:** goldens `fxv_h` (HR-116 boundary cases included); blind share H-23 71.4 %. **Review:** 2026-11-18.
- **Tier:** 3.
- **Challenger:** blind second lane.
- **Monitoring thresholds:** any golden difference across the four builds.
- **Data lineage hash:** `datasets/golden/stage_h/fxv_h.json`.
- **Retirement trigger:** a superseding stage H ruling.
- **Validation report:** `specifications/10-execution/fx-rfq-venue.md`.

### MH-20 Simulated Treasury futures venue (stage H round 4, H-24)
- **Purpose:** ZN and ZB futures on the lit engine in integer ticks, 32nds display, P&L and variation margin (`exec.sim.fut.*`).
- **Inputs:** as in the spec page; contract specs are parameters with [CME-ZN] and [CME-ZB] defaults.
- **Limitations:** simulated venue, labelled "simulated venue; not a real exchange; no real rates data"; quarter-tick price text only, eighth-tick contracts not supported (HR-118); no delivery or conversion-factor logic here.
- **Validation:** goldens `fut_h` (HR-116 integer boundary included); blind share H-24 94.7 % (18 of 19; two of the three `exec.sim.fut.run` value cases were re-derived blind in packet 3, 2026-11-19) after rates packet 2 (HR-114). **Review:** 2026-11-18.
- **Tier:** 3.
- **Challenger:** blind second lane.
- **Monitoring thresholds:** any golden difference across the four builds.
- **Data lineage hash:** `datasets/golden/stage_h/fut_h.json`.
- **Retirement trigger:** a superseding stage H ruling.
- **Validation report:** `specifications/10-execution/rates-futures-venue.md`.

### MK-1 Bitemporal store query (stage K wave 1, K-4a)
- **Purpose:** the value of a series as known at knowledge time K for valid time V, with corrections and withdrawals (`core.store.bitemporal_query`), in all four languages.
- **Inputs:** as in the spec page; instants are whole seconds (KR-16).
- **Limitations:** spec confirmed 2026-11-19 (`specifications/01-core/bitemporal-store.md`); the log is passed in the request, there is no persistent store.
- **Validation:** goldens `bt_k` plus `e2_k` two-error cases, passed by every build (observed, local, 2026-11-19); KR-4 correction property on 10,000 logs in each language (`program/stage_k_w1/`). **Review:** 2026-11-19.
- **Tier:** 3.
- **Challenger:** blind re-derivation (DR-H2), 6 of 8 value cases fully blind (`program/STAGE_K_BLIND_W1.md`).
- **Monitoring thresholds:** any KR-4 property failure; any golden difference across the four builds.
- **Data lineage hash:** sha256 15c685aa0eb348131b246aaa54e6d7df83d00545a1b0ecee71c79a660163cbce (`bt_k`, 10 cases) (2026-11-19).
- **Retirement trigger:** a superseding stage K ruling.
- **Validation report:** `specifications/01-core/bitemporal-store.md`.

### MK-2 Incremental curve update (stage K wave 1, K-4b)
- **Purpose:** sequential annual par bootstrap and its incremental update from the first changed quote (`curve.bootstrap.par_annual`, `curve.incremental.update`), in all four languages.
- **Inputs:** as in the spec page.
- **Limitations:** spec confirmed 2026-11-19; hand-sized instrument set; the stage B production bootstrap has no incremental entry point (only the premise that earlier pillars cannot move is checked on it).
- **Validation:** goldens `inc_k`; 10,000 random vectors bit-identical to a full rebuild in Python and Java; 45 quote moves on stage B bootstraps (`program/stage_k_w1/`). **Review:** 2026-11-19.
- **Tier:** 3.
- **Challenger:** blind re-derivation (DR-H2), 4 of 4 value cases.
- **Monitoring thresholds:** any recomputed pillar differing from a full rebuild by more than 1e-12 relative, or any copied pillar not bit-identical.
- **Data lineage hash:** sha256 746a7729fe42ed44d521621452503a014a01aa47f06546f8c08523ad70316eca (`inc_k`, 6 cases) (2026-11-19).
- **Retirement trigger:** a superseding stage K ruling.
- **Validation report:** `specifications/02-curves/incremental-update.md`.

### MK-3 Recalibration trigger (stage K wave 1, K-4c)
- **Purpose:** fires when a monitored input moves more than k sample sigmas times sqrt(days) since calibration (`calib.trigger.check`), in all four languages.
- **Inputs:** as in the spec page.
- **Limitations:** spec confirmed 2026-11-19; two-sided normal level only, which understates the false-alarm rate of a short window (the acceptance uses the Student-t predictive rate); CUSUM and EWMA are out of wave 1.
- **Validation:** goldens `trig_k`; simulation of 100,000 noise paths inside the 99% binomial interval and a planted 6-sigma move firing on every path, Python and Java (`program/stage_k_w1/`). **Review:** 2026-11-19.
- **Tier:** 3.
- **Challenger:** blind re-derivation (DR-H2), 4 of 5 value cases; SciPy `2*norm.sf(k)` on `false_alarm_rate` only (KR-11).
- **Monitoring thresholds:** observed noise fire rate outside the 99% binomial interval of its stated level.
- **Data lineage hash:** sha256 b3297f772ed002b9b369e10ef77c1d70b952dcff32604c2b9cf6b9105aafb5b3 (`trig_k`, 8 cases) (2026-11-19).
- **Retirement trigger:** a superseding stage K ruling.
- **Validation report:** `specifications/03-calibration/recalibration-triggers.md`.

### MK-4 Intraday delta-gamma risk with a Lagrange bound (stage K wave 1, K-5a)
- **Purpose:** delta-gamma P&L of a parallel yield move on zero-coupon positions with a bound on its error (`risk.intraday.delta_gamma_bound`), in all four languages.
- **Inputs:** as in the spec page.
- **Limitations:** spec confirmed 2026-11-19; zero-coupon positions only (other instruments have no `M3`, so no bound); latency-aware analytics on simulated data; the binary64 comparison is meaningful only for `T abs(h)` well above 1e-7 (KR-17).
- **Validation:** goldens `idr_k`; 1,000 seeded moves with zero violations in Python and Java, rechecked at 50 digits (`oracle/IDR_K_MOVES_CHECK_W1.json`). **Review:** 2026-11-19.
- **Tier:** 3.
- **Challenger:** none counted: the blind lane checked the bounds only to 6 decimals and idr_k-0005 was not blind, so the item has 0 of 5 value cases outside-checked (under the 60% per-item floor, `oracle/OUTSIDE_SHARES.md`); mpmath is our own oracle.
- **Monitoring thresholds:** any move with abs(estimate - revaluation) above the bound.
- **Data lineage hash:** sha256 7529524f6558dbdf27d65327bbe53396e1efaffdfa33159b6ce314afbbf7e153 (`idr_k`, 7 cases) (2026-11-19).
- **Retirement trigger:** a superseding stage K ruling.
- **Validation report:** `specifications/06-risk/intraday-risk-bounds.md`.

### MK-5 Second-order Bermudan scheme and its ladder (stage K, K-8)
- **Purpose:** `CN_RANNACHER_SMOOTHED`, an optional `method` on `rates.shortrate.bermudan_swaption` and `rates.shortrate.bermudan_ladder`: Crank-Nicolson with four implicit half steps after each exercise date, the curve term integrated exactly, and the exercise `max` smoothed to second order (KR-8 as revised by KR-18), so that the ladder at the default grid 201/100 is within 1% of the converged model derivative.
- **Inputs:** as in the spec page; `method` absent or `G18_IMPLICIT` keeps the G-18 scheme bit for bit.
- **Limitations:** spec 0.2.0 PROPOSED (`specifications/06-risk/bermudan-ladder-k8.md`); not the default method (the default stays `G18_IMPLICIT`, KR-8); the R6 use restriction of MG-6 was lifted for this method on 2026-11-19 (KR-110) after acceptance 1 to 3 passed in all four builds; the general use restriction at the top of this page still applies; the ladder row of a curve node the price does not depend on (0.4986 years in the judged cases) is exactly 0 and is not judged by any acceptance test (owner decision 2026-11-19); the end correction of the smoothing is derived in `program/K8_DIAGNOSIS.md`, not taken from a paper.
- **Validation:** acceptance 1 to 3 pass in Python, acceptance 3 in Java, C++ and Rust (`oracle/K8_ACCEPTANCE_W2.json`, `oracle/K8_ACCEPTANCE_PORTS.json`): worst judged entry at 201/100 0.40% from QuantLib, observed orders 1.84 to 2.15 on 24 entries; goldens `k8_k` in all four builds; ladder against its own Richardson bumps to 1e-8 in each language's unit tests. **Review:** 2026-11-19.
- **Tier:** 1.
- **Challenger:** QuantLib 1.44 `FdHullWhiteSwaptionEngine` central bump at tGrid 8,000, xGrid 3,201 (KR-19, `oracle/K8_REFERENCE_QL.json`), counted outside only on the judged ladder entries of k8_k-0001..0003; the goldens themselves are the Python build's output, not an independent oracle. Blind re-derivation (DR-H2) by a second model from the spec text alone: 7 of 7 value cases MATCH, counted (`program/STAGE_K_BLIND_K8.md`; the row-0 question it waited on is closed, `program/K8_ROW0_FINDING.md`).
- **Monitoring thresholds:** any judged ladder entry at 201/100 more than 1% from the reference; any observed order outside 1.5 to 2.5 or a `NON_MONOTONE` status on 201/401/801; AAD against bump beyond 1e-8 relative.
- **Data lineage hash:** sha256 e3f51c83d7eeeac3a7c4cb35e09eb89d7feca3bce4c8e73a2362fca0aefaac89 (`k8_k`, 14 cases; regenerated 2026-11-19 to record the blind MATCH, values unchanged) (2026-11-19).
- **Retirement trigger:** a superseding stage K ruling, or the method failing acceptance in any build.
- **Validation report:** `specifications/06-risk/bermudan-ladder-k8.md`.

### MK-6 SA-CCR exposure at default (stage K wave 1b, K-8d)
- **Purpose:** standardised approach for counterparty credit risk EAD of one netting set, margined or unmargined (`risk.saccr.ead`, CRE52), in all four languages.
- **Inputs:** as in the spec page; supervisory parameters in `specifications/06-risk/sa-ccr-parameters.json`, one copy for the four builds.
- **Limitations:** rulings KR-30 to KR-39 confirmed 2026-11-19; KR-39 scope limits (one margin agreement per netting set, no haircut computation, no CCP rules); closed form, no iteration.
- **Validation:** goldens `saccr_k` passed by every build through the neutral runner (observed, local laptop, 2026-11-19); CRE99 Examples 1 to 5 reproduce the printed EADs (KR-30). **Review:** 2026-11-19.
- **Tier:** 3.
- **Challenger:** 12 of 16 value cases (75%): 5 printed CRE99 examples and 7 blind re-derivations (DR-H2, `program/STAGE_K_BLIND_W1B.md`); 4 further blind matches excluded for a recorded process failure.
- **Monitoring thresholds:** any golden difference across the four builds; any CRE99 printed EAD not reproduced at its printed digits.
- **Data lineage hash:** sha256 e0fedebf674fc978431991dd6b16c67bf4eaa5e216682172c24c837d4a91561e (`saccr_k`, 39 cases) (2026-11-19).
- **Retirement trigger:** a superseding stage K ruling or a change of CRE52.
- **Validation report:** `specifications/06-risk/sa-ccr.md`.

### MK-7 FRTB IMA backtesting zones and desk limits (stage K wave 1b, K-8e)
- **Purpose:** bank-wide traffic-light zone from the larger of the actual and hypothetical exception counts, desk exception limits, and exception counting (`risk.frtb.backtest.zone`, `.desk`, `.count`, MAR32 and MAR99), in all four languages.
- **Inputs:** as in the spec page; tables in `specifications/06-risk/frtb-ima-backtest-tables.json`.
- **Limitations:** rulings KR-40 to KR-47 confirmed 2026-11-19; KR-44 (limits 12 and 30, "more than" covering both) is an inferred reading; backtesting only, no PLA test or capital (KR-47); `risk.frtb.backtest.zone` has no E1 golden (Integer inputs only, open point).
- **Validation:** goldens `btk_k` and `tlk_k` passed by every build (observed, local laptop, 2026-11-19); MAR99 Table 2 rows 0 to 10 reproduced. **Review:** 2026-11-19.
- **Tier:** 3.
- **Challenger:** 23 of 24 `btk_k` value cases (95.8%, floor 60%): MAR99 Table 2 printed figures on 12, and 11 blind re-derivations (DR-H2, `program/STAGE_K_BLIND_BTK.md`, 12 of 12 MATCH; btk_k-0017 matched but is not counted, the rules text states its answer). SciPy `binom.cdf` on 23 of 24 is not counted (D6 precedent: stage F `SCIPY.BINOM` is `reimplementation`, risk_f4-0082).
- **Monitoring thresholds:** any zone, limit or count difference across the four builds; any MAR99 Table 2 row not reproduced.
- **Data lineage hash:** sha256 a987ea2f465fd2d1d139da303d3edaa4addd78b0b989fd90656595ec6cd31160 (`btk_k`, 40 cases; after the blind-lane `verified_by` entries, outputs unchanged) (2026-11-19).
- **Retirement trigger:** a superseding stage K ruling or a change of MAR32.
- **Validation report:** `specifications/06-risk/frtb-ima-backtest.md`.

### MK-8 FRTB DRC and RRAO (stage K wave 2, K-8a, PROPOSED)
- **Purpose:** default risk charge for non-securitisations, securitisations and the correlation trading portfolio, and the residual risk add-on (MAR22, MAR23). Specified only.
- **Inputs:** as in the spec page.
- **Limitations:** spec and rulings (KR-50 to KR-69) PROPOSED; nothing implemented and no golden file written (2026-11-19). Not a model in use.
- **Validation:** hand cases in the spec, all reproduced by a blind second model (`program/STAGE_K_BLIND_W2.md`); no build exists yet. **Review:** 2026-11-19.
- **Tier:** 3.
- **Challenger:** blind re-derivation (DR-H2) of the spec's hand cases, `program/STAGE_K_BLIND_W2.md`; gate status `program/STAGE_K_W2_GATE.md`.
- **Monitoring thresholds:** none until built; then any golden difference across the four builds.
- **Data lineage hash:** sha256 5ddb8e136e2de83d001b165d0814f772f6e75b602650d60a8f45eefd57ad23e9 (spec page `frtb-drc-rrao.md`, no golden file yet) (2026-11-19).
- **Retirement trigger:** the wave-2 build replaces this entry's limitations, or the item is withdrawn.
- **Validation report:** `specifications/06-risk/frtb-drc-rrao.md`.

### MK-9 FRTB IMA: ES with liquidity horizons, NMRF and SES, RFET, PLA, capital (stage K wave 2, K-8f, PROPOSED)
- **Purpose:** liquidity-horizon-scaled expected shortfall, stressed ES for non-modellable factors, the risk factor eligibility test, the P&L attribution test and the IMA capital aggregation (MAR31 to MAR33). Specified only.
- **Inputs:** as in the spec page.
- **Limitations:** spec and rulings (KR-50 to KR-69) PROPOSED; nothing implemented and no golden file written (2026-11-19). Not a model in use.
- **Validation:** hand cases in the spec, all reproduced by a blind second model (`program/STAGE_K_BLIND_W2.md`); no build exists yet. **Review:** 2026-11-19.
- **Tier:** 3.
- **Challenger:** blind re-derivation (DR-H2) of the spec's hand cases, `program/STAGE_K_BLIND_W2.md`; gate status `program/STAGE_K_W2_GATE.md`.
- **Monitoring thresholds:** none until built; then any golden difference across the four builds.
- **Data lineage hash:** sha256 60ac9a23779398a0c7c44dba6099093b0943ef20ce5b1b6c159ed78ea9021166 (spec page `frtb-ima.md`, no golden file yet) (2026-11-19).
- **Retirement trigger:** the wave-2 build replaces this entry's limitations, or the item is withdrawn.
- **Validation report:** `specifications/06-risk/frtb-ima.md`.

### MK-10 CVA risk capital: BA-CVA and SA-CVA (stage K wave 2, K-8g, PROPOSED)
- **Purpose:** basic (reduced and full) and standardised CVA capital (MAR50). Specified only.
- **Inputs:** as in the spec page.
- **Limitations:** spec and rulings (KR-50 to KR-69) PROPOSED; nothing implemented and no golden file written (2026-11-19). Not a model in use.
- **Validation:** hand cases in the spec, all reproduced by a blind second model (`program/STAGE_K_BLIND_W2.md`); no build exists yet. **Review:** 2026-11-19.
- **Tier:** 3.
- **Challenger:** blind re-derivation (DR-H2) of the spec's hand cases, `program/STAGE_K_BLIND_W2.md`; gate status `program/STAGE_K_W2_GATE.md`.
- **Monitoring thresholds:** none until built; then any golden difference across the four builds.
- **Data lineage hash:** sha256 348a99ad113d40f349c9943a4ba3d49f1ff3faddcd10a49fbc76a5ac21b1b6ca (spec page `cva-capital.md`, no golden file yet) (2026-11-19).
- **Retirement trigger:** the wave-2 build replaces this entry's limitations, or the item is withdrawn.
- **Validation report:** `specifications/06-risk/cva-capital.md`.

### MK-11 Leverage ratio and large exposures, simplified (stage K wave 2, K-8i, PROPOSED)
- **Purpose:** leverage ratio and large-exposure limit checks (simplified). Specified only.
- **Inputs:** as in the spec page.
- **Limitations:** spec and rulings (KR-50 to KR-69) PROPOSED; nothing implemented and no golden file written (2026-11-19). Not a model in use.
- **Validation:** hand cases in the spec, all reproduced by a blind second model (`program/STAGE_K_BLIND_W2.md`); no build exists yet. **Review:** 2026-11-19.
- **Tier:** 3.
- **Challenger:** blind re-derivation (DR-H2) of the spec's hand cases, `program/STAGE_K_BLIND_W2.md`; gate status `program/STAGE_K_W2_GATE.md`.
- **Monitoring thresholds:** none until built; then any golden difference across the four builds.
- **Data lineage hash:** sha256 46b10b589b39c08b25c7d4e0f3641d9c39f9d7b03759446a19b6ea11dcc2d81c (spec page `leverage-large-exposures.md`, no golden file yet) (2026-11-19).
- **Retirement trigger:** the wave-2 build replaces this entry's limitations, or the item is withdrawn.
- **Validation report:** `specifications/06-risk/leverage-large-exposures.md`.
