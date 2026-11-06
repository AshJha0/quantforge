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
fragility: 18 adaptive cases keep their outcome under noise of up to 8 ulps
fragility: integrate-0095 error estimate 1.52e-01 against tol 1e-13
fragility: root-0025 needs 7 Brent steps against max_iter 2; root-0026 has width 0.125 after 3 bisections against x_tol 1e-12
```
