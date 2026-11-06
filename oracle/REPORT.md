# Oracle run report

Written by `oracle/python/run_all.py`. Every line comes from that run.

```
daycount difference strata ACT_ACT_ICMA: 13 of the tested pairs; first [('2024-01-01', '2024-01-31', 0.08152173913043478, 0.08241758241758242), ('2024-02-28', '2024-02-29', 0.002717391304347826, 0.0027472527472527475), ('2024-03-01', '2024-04-30', 0.16393442622950818, 0.16304347826086957)]
daycount difference strata ACT_ACT_AFB: 11 of the tested pairs; first [('2020-02-29', '2028-02-28', 8.0, 7.997267759562842), ('2024-01-01', '2025-02-28', 1.1616438356164382, 1.158904109589041), ('2024-02-29', '2028-02-28', 4.0, 3.9972677595628414)]
daycount difference strata ONE_ONE: 6 of the tested pairs; first [('2024-04-30', '2024-04-30', 0.0, 1.0), ('2024-01-01', '2024-01-01', 0.0, 1.0), ('2025-01-01', '2025-01-01', 0.0, 1.0)]
suite daycount: 1741 cases
suite calendar: 1154 cases
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
```
