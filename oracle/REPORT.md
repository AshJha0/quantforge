# Oracle run report

Written by `oracle/python/run_all.py`. Every line comes from that run.

```
daycount QuantLib THIRTY_E_360_ISDA: 1 difference, start = end = termination on 29 February, QuantLib gives -1/360; the spec gives 0
daycount Strata ACT_ACT_AFB: 11 differences, all with end on 28 February, all reproduced by Strata's documented rule
daycount Strata ONE_ONE: 6 differences, all start = end; Strata documents 1/1 as always 1
daycount Strata THIRTY_E_360_ISDA: 1 difference, same case as QuantLib, -1/360; the spec gives 0
daycount: no other difference from QuantLib or Strata, ACT_ACT_ICMA included
suite daycount: 1756 cases
add_tenor: text of calendars.md matches QuantLib on every day 2021 to 2026, two calendars, all conventions
suite calendar: 1169 cases
suite compounding: 846 cases
rng: xoshiro256** and SplitMix64 match the published reference vectors
rng: PPND16 worst relative error against 50-digit erfinv over 17 points: 3.40e-16
suite rng: 28 cases
sobol: own code, QuantLib JoeKuoD6 and SciPy agree bit for bit on all stored cases
suite sobol: 10 cases
mc CALL PLAIN N=100000 m=1: price 9.293666 true 9.227006 err 6.67e-02 stderr 0.04393
mc PUT PLAIN N=50000 m=1: price 6.291901 true 6.330081 err 3.82e-02 stderr 0.04092
mc CALL PLAIN N=20000 m=4: price 9.365804 true 9.227006 err 1.39e-01 stderr 0.09867
mc CALL PLAIN N=50000 m=1: price 9.145860 true 9.227006 err 8.11e-02 stderr 0.06144
mc CALL ANTITHETIC N=50000 m=1: price 9.238425 true 9.227006 err 1.14e-02 stderr 0.03257
mc CALL CONTROL_VARIATE N=50000 m=1: price 9.232647 true 9.227006 err 5.64e-03 stderr 0.02542
mc PUT CONTROL_VARIATE N=50000 m=2: price 6.326961 true 6.330081 err 3.12e-03 stderr 0.02540
mc CALL SOBOL N=65536 m=1: price 9.225903 true 9.227006 err 1.10e-03 stderr 0.05401
mc CALL SOBOL N=16384 m=4: price 9.219085 true 9.227006 err 7.92e-03 stderr 0.10792
mc CALL PLAIN N=50000 m=1: price 5.881570 true 5.800638 err 8.09e-02 stderr 0.07682
suite monte_carlo: 13 cases
suite root: 28 cases
suite integrate: 95 cases
tension: limits to natural cubic (p=0.011) and to linear (p=400) hold; s' continuous at every knot
monotone convex: every g integrates to 0, matches node forwards, closed-form G matches quadrature; all inputs reprice
suite interp: 52 cases
suite diff_linalg: 17 cases
suite stats: 31 cases
pde J=100 M=50: price err 1.448e-03 delta err 1.843e-04 gamma err 1.171e-06
pde J=200 M=100: price err 3.644e-04 delta err 4.603e-05 gamma err 2.754e-07
pde J=400 M=200: price err 9.124e-05 delta err 1.151e-05 gamma err 6.777e-08
pde J=800 M=400: price err 2.282e-05 delta err 2.877e-06 gamma err 1.688e-08
pde convergence ratios on halving h and dt: [3.974, 3.994, 3.998]
suite pde: 11 cases
cos BS CALL K=100.0 sig=0.2 t=1.0: err 3.89e-24
cos BS PUT K=100.0 sig=0.2 t=1.0: err 3.89e-24
cos BS CALL K=80.0 sig=0.3 t=0.25: err 4.92e-24
cos BS PUT K=130.0 sig=0.15 t=2.0: err 3.57e-24
cos BS CALL K=120.0 sig=0.5 t=5.0: err 1.14e-27
cos Heston CALL K=100.0 t=1.0: against QuantLib err 6.78e-11
cos Heston PUT K=90.0 t=1.0: against QuantLib err 6.78e-11
cos Heston CALL K=120.0 t=2.0: against QuantLib err 8.90e-12
cos Heston PUT K=100.0 t=0.5: against QuantLib err 5.59e-09
cos Heston near zero vol-of-vol against BS at average variance: err 2.11e-06
suite cos: 14 cases
snapshot: hand-written canonical form matches; hashlib matches NIST abc and system sha256sum
suite snapshot: 21 cases
suite data_checks: 27 cases
time: rule table matches zoneinfo at 2717520 half-hour instants, 2007 to 2037, five zones
suite time: 123 cases
suite rulings: 39 cases
suite store: 21 cases
store: expected rows hand-written; hashes from the oracle canonical form, one source by nature
limits: mc at limit, price 9.24164, stderr 0.01384
suite limits: 61 cases
suite store_a4: 6 cases
suite limit_order: 15 cases
suite store_rulings: 11 cases
suite units: 26 cases
suite schedule: 7 cases
suite curve: 7 cases
ois: replay matches QuantLib to 5e-12 at every pillar, SONIA and SOFR, both interpolations
ois: swap PVs match QuantLib OvernightIndexedSwap within 1e-5 on 1e6, with and without payment lag
ois: with payment lag the telescoped form misses the leg by 1.13e-04 per unit notional on 10Y
suite ois: 32 cases
projection: replay against QuantLib, max pillar difference 1.09e-14
projection: vanilla swap PVs match QuantLib within 1e-5 on 1e6
suite projection: 6 cases
suite fx: 14 cases
risk: key-rate sums match the parallel DV01 to under 1e-5 relative at a 1 bp bump
suite risk: 6 cases
suite hedge: 10 cases
calibration: Nelson-Siegel objective LM 7.2e-35, BFGS 4.3e-15; Gauss-Newton and BFGS reach the exponential minima
suite calibration: 25 cases
use case 1: book PV 59903.6465 and delta 2054546.4912, QuantLib FxForward gap 9.90e-10 and 7.59e-04
use case 2: DV01 5359.88 on 1e7, residual key-rate norm 0.02 against 3847.77 unhedged
suite usecases: 2 cases
schedule_deep: 48 cases against QuantLib, 48 also equal to Strata PeriodicSchedule
suite schedule_deep: 48 cases
suite curve_deep: 8 cases
ois_deep: 20 swap PVs against Strata's pricer on 1e6, worst difference 4.075e-10
suite ois_deep: 36 cases
projection_deep: pillars, swaps and FRAs match QuantLib, including month-end spot, a holiday in the spot lag and negative rates
suite projection_deep: 19 cases
risk_deep: DV01 and every key rate against bumped QuantLib quotes, worst difference 3.339e-06 on 1e6
suite risk_deep: 6 cases
fx_deep: implied ratios against QuantLib FxSwapRateHelper, worst difference 1.887e-15
suite fx_deep: 33 cases
hedge_deep: exact enumeration against SciPy L-BFGS-B, worst difference 6.04e-10
suite hedge_deep: 12 cases
suite rulings_b: 46 cases
mutants: 23 deliberate errors, all caught
suite equity_forward: 26 cases
equity_forward: 26 cases
suite black: 61 cases
black: 61 cases
suite black_deep: 156 cases
black_deep: 156 cases
equity_forward_deep: 6 QuantLib checks, 3 with a borrow on the shipped engine; the wrong forward misses by up to 4.234e-02
suite equity_forward_deep: 15 cases
equity_forward_deep: 15 cases
suite greeks: 45 cases
greeks: 45 cases
suite smile: 57 cases
smile: 57 cases
suite surface: 14 cases
surface: 14 cases
suite sabr: 25 cases
sabr: 25 cases
sabr_deep: arbitrage-free recipe against QuantLib CEV at nu=0: worst call error 1.51e-05
sabr_deep: against QuantLib NoArbSabr (Doust, another method): worst vol gap 1.79e-02
suite sabr_deep: 13 cases
sabr_deep: 13 cases
strata_vol: Black, Greeks, Bachelier, Hagan against Strata, worst gap 2.04e-14
suite strata_vol: 32 cases
strata_vol: 32 cases
suite usecases_c: 2 cases
usecases_c: 2 cases
stage C mutants: 30 caught; arbitrage-free against CEV [1.5084564432291114e-05], Hagan [0.005817758552876473], Doust [0.017899914994640886]
ois_d: ESTR and SOFR pillars match QuantLib OISRateHelper within 5e-12, both interpolations, two dates
ois_d: turn-of-year jump curves match QuantLib's jump mechanism within 5e-12 at pillars and around the turn
ois_d: ESTR and SOFR swap PVs match QuantLib MakeOIS within 1e-9 per unit notional
suite ois_d: 25 cases
compound_d: lookback, observation shift and lockout match QuantLib OvernightIndexedCoupon within 5e-14 (lockout k as QuantLib k-1)
compound_d: IBOR fallback rates match QuantLib with 2-day observation shift; spreads are ISDA's fixed 2021-03-05 values
suite compound_d: 35 cases
steps_d: step curves match QuantLib ForwardCurve (backward flat) with jumps within 2e-15
steps_d: fit recovers the step rates behind QuantLib MakeOIS par rates within 1e-12
suite steps_d: 11 cases
futures_d: Hull-White convexity matches QuantLib HullWhite.convexityBias, including a = 0 by limit
suite futures_d: 10 cases
csa_d: OIS index basis equals the difference of QuantLib par rates on the two projection curves within 1e-12
csa_d: joint bootstrap agrees with QuantLib's two-step build within 1e-10
suite csa_d: 13 cases
fits_d: smoothness-regularised forward fits solved in exact rationals; NumPy agrees within 1e-9
fits_d: Huber Nelson-Siegel fits (fixed tau) agree with SciPy least_squares loss='huber' from three starts within 1e-8
suite fits_d: 16 cases
stage D: 65 wrong-convention checks, each caught
  mutant ois_d: ESTR payment lag 1 instead of 2: gap 1.873e-04
  mutant ois_d: SOFR turn of year ignored: gap 4.675e-07
  mutant ois_d: jump applied on its own date: gap 1.362e-05
  mutant ois_d: ESTR turn of year ignored: gap 4.695e-07
  mutant ois_d: jump applied on its own date: gap 1.365e-05
  mutant ois_d: ESTR 2Y telescoped floating leg: gap 1.359e+02
  mutant ois_d: ESTR 10Y telescoped floating leg: gap 3.054e+01
  mutant ois_d: ESTR 18M telescoped floating leg: gap 2.245e+01
  mutant ois_d: ESTR 30Y telescoped floating leg: gap 8.002e+01
  mutant ois_d: SOFR 2Y telescoped floating leg: gap 7.147e+02
  mutant ois_d: SOFR 10Y telescoped floating leg: gap 1.135e+02
  mutant ois_d: SOFR 18M telescoped floating leg: gap 7.348e+01
  mutant ois_d: SOFR 30Y telescoped floating leg: gap 2.518e+02
  mutant compound_d: SOFR LOOKBACK 2: lookback weights from observation period: gap 2.753e-05
  mutant compound_d: SOFR LOOKBACK 5: lookback weights from observation period: gap 7.030e-05
  mutant compound_d: SOFR OBSERVATION_SHIFT 2: shift weights from interest period: gap 2.753e-05
  mutant compound_d: SOFR OBSERVATION_SHIFT 5: shift weights from interest period: gap 7.030e-05
  mutant compound_d: SOFR LOCKOUT 2: lockout one day early: gap 6.593e-06
  mutant compound_d: SOFR LOCKOUT 1: lockout one day early: gap 3.297e-06
  mutant compound_d: ESTR LOOKBACK 2: lookback weights from observation period: gap 1.451e-05
  mutant compound_d: ESTR LOOKBACK 5: lookback weights from observation period: gap 5.023e-05
  mutant compound_d: ESTR OBSERVATION_SHIFT 2: shift weights from interest period: gap 1.451e-05
  mutant compound_d: ESTR OBSERVATION_SHIFT 5: shift weights from interest period: gap 5.023e-05
  mutant compound_d: ESTR LOCKOUT 2: lockout one day early: gap 4.019e-05
  mutant compound_d: ESTR LOCKOUT 1: lockout one day early: gap 1.674e-05
  mutant compound_d: SONIA LOOKBACK 2: lookback weights from observation period: gap 8.843e-06
  mutant compound_d: SONIA LOOKBACK 5: lookback weights from observation period: gap 1.035e-04
  mutant compound_d: SONIA OBSERVATION_SHIFT 2: shift weights from interest period: gap 8.843e-06
  mutant compound_d: SONIA OBSERVATION_SHIFT 5: shift weights from interest period: gap 1.035e-04
  mutant compound_d: SONIA LOCKOUT 2: lockout one day early: gap 3.236e-05
  mutant compound_d: SONIA LOCKOUT 1: lockout one day early: gap 2.265e-05
  mutant compound_d: USD-LIBOR-3M fallback with lookback, no shift: gap 2.753e-05
  mutant compound_d: USD-LIBOR-3M fallback without spread adjustment: gap 2.616e-03
  mutant compound_d: USD-LIBOR-1M fallback with lookback, no shift: gap 2.622e-06
  mutant compound_d: USD-LIBOR-1M fallback without spread adjustment: gap 1.145e-03
  mutant compound_d: GBP-LIBOR-3M fallback with lookback, no shift: gap 1.219e-05
  mutant compound_d: GBP-LIBOR-3M fallback without spread adjustment: gap 1.193e-03
  mutant compound_d: GBP-LIBOR-6M fallback with lookback, no shift: gap 7.272e-06
  mutant compound_d: GBP-LIBOR-6M fallback without spread adjustment: gap 2.766e-03
  mutant steps_d: step effective one day late: gap 1.912e-05
  mutant steps_d: step effective one day late: gap 1.912e-05
  mutant steps_d: step effective one day late: gap 4.133e-06
  mutant futures_d: convexity added, not subtracted, t=0.25: gap 1.868e-05
  mutant futures_d: Ho-Lee sigma^2 t T / 2 at t=2.0: gap 2.453e-06
  mutant futures_d: convexity added, not subtracted, t=2.0: gap 6.529e-04
  mutant futures_d: convexity added, not subtracted, t=5.0: gap 2.243e-03
  mutant futures_d: Ho-Lee sigma^2 t T / 2 at t=1.0: gap 2.657e-06
  mutant futures_d: convexity added, not subtracted, t=1.0: gap 8.531e-05
  mutant futures_d: Ho-Lee sigma^2 t T / 2 at t=9.75: gap 8.673e-04
  mutant futures_d: convexity added, not subtracted, t=9.75: gap 1.006e-02
  mutant futures_d: Ho-Lee sigma^2 t T / 2 at t=1.0: gap 2.555e-06
  mutant futures_d: convexity added, not subtracted, t=1.0: gap 1.134e-04
  mutant csa_d: collateral spread sign flipped (0.0025): gap 3.435e-02
  mutant csa_d: collateral spread sign flipped (-0.001): gap 1.374e-02
  mutant csa_d: forward ratio inverted: gap 2.764e-01
  mutant csa_d: forward ratio inverted: gap 2.798e-01
  mutant csa_d: basis 2Y projected and discounted on leg B's curve: gap 4.283e-05
  mutant csa_d: basis 5Y projected and discounted on leg B's curve: gap 8.460e-05
  mutant csa_d: basis 10Y projected and discounted on leg B's curve: gap 1.656e-04
  mutant csa_d: projection discounted on itself (single curve): gap 1.071e-05
  mutant fits_d: smooth fit penalising levels, lambda 0.0001: gap 3.437e-05
  mutant fits_d: smooth fit penalising levels, lambda 0.01: gap 3.023e-03
  mutant fits_d: plain least squares instead of Huber ([4]): gap 2.846e-03
  mutant fits_d: plain least squares instead of Huber ([2, 9]): gap 1.086e-03
  mutant fits_d: plain least squares instead of Huber ([6]): gap 1.340e-03
bonds_d: clean price, accrued, modified duration and convexity match QuantLib FixedRateBond (ACT/ACT ICMA, compounded) within 1e-10
bonds_d: curve prices and Z-spreads match QuantLib BondFunctions.zSpread (continuous, ACT/365F) within 1e-10
suite bonds_d: 49 cases
repo_d: FRN at zero margins on its own curve, settled on a coupon date, prices at 100 within 1e-11
repo_d: CTD is bond 2; implied repo gap to next 1.04e-01
suite repo_d: 19 cases
suite bondfit_d: 4 cases
stage D wave 2: 26 wrong-convention checks, each caught
  mutant bonds_d: accrued on ACT/365 for 2029-11-15: gap 1.690e-02
  mutant bonds_d: accrued on ACT/365 for 2031-02-28: gap 5.960e-03
  mutant bonds_d: accrued on ACT/365 for 2036-08-15: gap 8.644e-03
  mutant bonds_d: accrued on ACT/365 for 2055-05-15: gap 1.888e-02
  mutant bonds_d: accrued on ACT/365 for 2027-12-15: gap 6.210e-04
  mutant bonds_d: curve price not forwarded to settlement 2029-11-15: gap 3.234e-02
  mutant bonds_d: curve price not forwarded to settlement 2031-02-28: gap 3.148e-02
  mutant bonds_d: curve price not forwarded to settlement 2036-08-15: gap 3.303e-02
  mutant bonds_d: curve price not forwarded to settlement 2034-03-31: gap 3.003e-02
  mutant bonds_d: curve price not forwarded to settlement 2055-05-15: gap 3.519e-02
  mutant bonds_d: asset swap over the bond's own annuity 2029-11-15: gap 3.813e-04
  mutant bonds_d: asset swap over the bond's own annuity 2031-02-28: gap 6.050e-05
  mutant bonds_d: asset swap over the bond's own annuity 2036-08-15: gap 9.260e-06
  mutant bonds_d: asset swap over the bond's own annuity 2034-03-31: gap 7.888e-05
  mutant bonds_d: asset swap over the bond's own annuity 2055-05-15: gap 4.482e-06
  mutant repo_d: FRN discount margin ignored: gap 5.911e-01
  mutant repo_d: FRN discount margin ignored: gap 2.280e-01
  mutant repo_d: coupon in repo term not reinvested 2029-11-15: gap 5.454e-03
  mutant repo_d: repo on clean, not dirty 2029-11-15: gap 6.595e-03
  mutant repo_d: coupon in repo term not reinvested 2036-08-15: gap 1.356e-03
  mutant repo_d: repo on clean, not dirty 2036-08-15: gap 9.508e-03
  mutant repo_d: coupon in repo term not reinvested 2034-03-31: gap 2.962e-03
  mutant repo_d: repo on clean, not dirty 2034-03-31: gap 3.037e-02
  mutant repo_d: coupon in repo term not reinvested 2031-02-28: gap 1.828e-03
  mutant repo_d: repo on clean, not dirty 2031-02-28: gap 9.427e-03
  mutant bondfit_d: zero-weight (rich) bond fitted as normal: gap 7.101e-03
xccy_d: bootstrap recovers the basis-adjusted curve within 1e-13; foreign legs match QuantLib OvernightLeg NPVs within 1e-6 on 1e7
suite xccy_d: 13 cases
stage D D3: 12 wrong-convention checks, each caught
credit_d: ISDA bootstrap replay reprices with QuantLib IsdaCdsEngine fair spreads within 1.9e-10
credit_d: CDS NPV and upfront match QuantLib IsdaCdsEngine within 6.9e-16 per unit
credit_d: on the SOFR curve, QuantLib's IsdaCdsEngine fair spreads agree with the replay within 1.2e-11
suite credit_d: 19 cases
stage D D4: 13 wrong-convention checks, each caught
equity_d: forwards replayed through a QuantLib DiscountCurve within 1e-9 (interpolation only, not an outside model); implied borrow and financing spreads are known truth
suite equity_d: 10 cases
suite index_d: 12 cases
suite trs_d: 3 cases
stage D D5: 9 wrong-convention checks, each caught
inflation_d: CPI pillars reprice every ZCIS quote with and without seasonality
suite inflation_d: 13 cases
stage D D6: 5 wrong-convention checks, each caught
capswaption_d: option values from QuantLib blackFormula and bachelierBlackFormula; schedules and curves as stage B
suite capswaption_d: 14 cases
stage D D7: 9 wrong-convention checks, each caught
commodity_d: seasonal curves reprice every quote; carry values kept at least 1e-6 from zero
suite commodity_d: 10 cases
stage D D8: 3 wrong-convention checks, each caught
mbs_d: PSA ramp, SMM, level-pay amortisation by the standard formulas; the last month retires the balance within 1e-6
suite mbs_d: 12 cases
stage D D9: 10 wrong-convention checks, each caught
suite rulings_d: 18 cases
rulings_d: 18 cases
suite rulings2_d: 25 cases
rulings2_d: 25 cases
suite outside_d: 284 cases
outside_d: all 284 cases re-priced in QuantLib 1.44 through the convention map
suite edge_d: 24 cases
edge_d: 24 edge-case register cases
suite rulings_r1: 15 cases
rulings_r1: 15 cases (R1-3 conversion factor, R1-4 CDS discount interpolation)
suite risk_r2: 41 cases
risk_r2: QuantLib worst gaps per unit notional: par 1.8e-12, key-rate 3.7e-16; Jacobian 1.7e-08; par-from-zero identity worst 5.0e-06 of par DV01
suite pnl_r2: 44 cases
pnl_r2: 44 cases, 4 not explained (large moves on long products); largest |unexplained|/threshold 3.24; no case within 0.9-1.1
invariants: 256620 day-count evaluations, none negative, all equal-date results 0
invariants: 4394 golden cases checked, none breaks a stated invariant
invariants: 343 stage B cases checked, none breaks one
invariants:   FX delta sign follows side: 11
invariants:   OIS PV equals notional x (par - fixed) x annuity: 26
invariants:   discount factors positive: 10
invariants:   hedge cuts key-rate risk: 1
invariants:   hedge offsets delta: 1
invariants:   key rates sum to DV01; payers gain: 9
invariants:   objective not negative: 19
invariants:   periods contiguous, ends on business days: 54
invariants:   pillars increase, discount factors positive: 40
invariants:   points equal forward minus spot: 11
invariants:   residual, objective and first-order conditions: 17
invariants:   spot after trade date: 20
invariants:   valuation carries its snapshot: 57
invariants: 446 stage C cases checked, none breaks one
invariants:   SABR density flag matches minimum: 3
invariants:   SSVI ATM total variance equals theta: 3
invariants:   SVI variance positive, flag matches min g: 2
invariants:   arbitrage-free SABR: mass 1, mean f, density not negative, calls bounded and decreasing: 6
invariants:   forward positive, factors positive, dividends not negative: 4
invariants:   gamma and vega not negative for a long option: 59
invariants:   implied vol not negative: 97
invariants:   option price within no-arbitrage bounds: 115
invariants:   parity residual not negative, breaches ascending: 3
invariants:   surface flag matches violation lists: 4
invariants:   surface variance positive: 1
invariants:   use case 3 vol and forwards positive: 1
invariants: 654 stage D cases checked, none breaks one
invariants:   CDS legs positive: 25
invariants:   CDS survival in (0, 1] and strictly falling: 7
invariants:   CPI positive: 2
invariants:   CSA discount factors positive: 5
invariants:   CTD has the highest implied repo: 1
invariants:   MBS balance falls to zero; principal not negative: 3
invariants:   NDF forward positive, equal to the fixing once known: 3
invariants:   OIS pillars strictly increasing, discount factors positive: 10
invariants:   TRS pv = sign (equity - funding): 2
invariants:   bond: dirty = clean + accrued; modified = Macaulay / (1 + y/f); duration and convexity positive: 110
invariants:   cap = sum of non-negative caplets: 12
invariants:   compounded rate within the fixings' range (plus compounding); interest = rate x accrual: 71
invariants:   convexity not negative; forward = futures rate - convexity: 6
invariants:   corporate action keeps shares x price: 4
invariants:   fallback = compounded + positive fixed spread: 4
invariants:   futures basis = market - fair: 3
invariants:   implied dividends: period amounts sum to the cumulative: 1
invariants:   index basis = quoted - intrinsic: 1
invariants:   joint bootstrap pillars strictly increasing: 2
invariants:   linker nominal = real x index ratio: 5
invariants:   repo: special outputs null exactly when gc_rate is null: 4
invariants:   robust fit: outliers are exactly the residuals beyond delta: 4
invariants:   smooth fit: objective not negative and at least the weighted residual sum: 4
invariants:   step curve positive; decreasing when all forwards are positive: 4
invariants:   storage arbitrage flag = positive carry value: 2
invariants:   swaption at least intrinsic on the annuity: 10
invariants:   xccy pv = sign (spot foreign - domestic): 3
fragility: 18 adaptive cases keep their outcome under noise of up to 8 ulps
fragility: integrate-0095 error estimate 1.52e-01 against tol 1e-13
fragility: root-0025 needs 7 Brent steps against max_iter 2; root-0026 has width 0.125 after 3 bisections against x_tol 1e-12
```

## Stage D outside-oracle coverage (rule 11.2.5)

Written by `oracle/python/outside_d.py`. A case counts only if QuantLib 1.44, built from its own convention objects through `qf_oracle/convmap.py` (reviewed copy: `oracle/CONVENTION_MAP.md`), reproduces every output of the case within the case's own tolerance. One row per counted case, with the library version and the convention rows used, is in `oracle/outside_register.json`. Error cases are in the denominator and never count. Older `verified_by` tags that name QuantLib are not counted here unless this check passes.

| Suite | Outside-oracle cases | Cases | Share | Why not more |
|---|---|---|---|---|
| `bondfit_d` | 0 | 4 | 0% | Nelson-Siegel fit judged on repricing; QuantLib's FittedBondDiscountCurve fits by its own optimiser path, so it cannot reproduce a golden independently of iteration path |
| `bonds_d` | 39 | 49 | 80% |  |
| `capswaption_d` | 9 | 14 | 64% |  |
| `commodity_d` | 0 | 10 | 0% | no QuantLib object for monthly log-linear commodity forwards with additive seasonality or for storage carry |
| `compound_d` | 25 | 35 | 71% |  |
| `credit_d` | 9 | 19 | 47% |  |
| `csa_d` | 3 | 13 | 23% | cases without FX count via QuantLib ZeroSpreadedTermStructure; CSA with FX forwards has no QuantLib object; spread and basis cases are internal |
| `edge_d` | 11 | 24 | 46% |  |
| `equity_d` | 0 | 10 | 0% | QuantLib has no implied-dividend, implied-borrow or equity futures-basis object; its dividend handling uses other conventions |
| `fits_d` | 0 | 16 | 0% | smooth and robust curve fits are internal estimators (penalised and Huber); no QuantLib equivalent |
| `futures_d` | 6 | 10 | 60% |  |
| `index_d` | 0 | 12 | 0% | index dividends, rebalancing and corporate actions have no QuantLib object |
| `inflation_d` | 0 | 13 | 0% | QuantLib's inflation curves use other lag and interpolation conventions (spec 02-curves/inflation.md); ZCIS and linkers would need the spec's own CPI curve |
| `mbs_d` | 0 | 12 | 0% | QuantLib has no agency MBS pool cash-flow model |
| `ois_d` | 20 | 25 | 80% |  |
| `outside_d` | 284 | 284 | 100% |  |
| `repo_d` | 8 | 19 | 42% |  |
| `rulings2_d` | 1 | 25 | 4% | internal: spec rulings, mostly error and order cases |
| `rulings_d` | 0 | 18 | 0% | internal: spec rulings, mostly error and order cases |
| `rulings_r1` | 0 | 15 | 0% | internal: spec rulings; CME conversion factors have no QuantLib object |
| `steps_d` | 0 | 11 | 0% | meeting-date step fits are internal; QuantLib ForwardCurve could replay a step curve but not the fit |
| `trs_d` | 0 | 3 | 0% | QuantLib has no equity total return swap with these legs |
| `xccy_d` | 4 | 13 | 31% | PV and bootstrap count via QuantLib OvernightLeg; NDF has no QuantLib object; the rest are error cases |
| **stage D** | **419** | **654** | **64.1%** | |

Caveat: most counted cases are fixed-rate bonds (suite `outside_d`), so the stage-wide share leans on one product family.
