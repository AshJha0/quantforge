# Stage D numeric targets

Set before any stage D code, as plan section 8 requires. "Oracle measured" is the oracle's own replay against the outside source, from `oracle/python/gen_stage_d.py`. Self-assessment until the end-of-project human review.

Calibration is judged on repricing, and on parameters only where the minimum is unique (every stage D fit is). Iteration counts are never compared.

## Wave 1: D1 rates core

| Item | Target | Oracle | Oracle measured |
|---|---|---|---|
| ESTR, SOFR curve solve | Every quote reprices below 1e-13 | Own repricing | Solver tolerance 1e-15 |
| ESTR, SOFR pillars, with or without jumps | Within 1e-9 | QuantLib `OISRateHelper`, jumps | Within 5e-12 |
| OIS PV, any notional | 1e-9 per unit notional, plus 1e-9 relative | QuantLib `MakeOIS` | Within 1e-9 per unit |
| Floating leg | General form, never telescoped | Identity | Telescoped misses by 11 to 715 on the goldens' notionals |
| Dated compounding, fallback | 1e-12 absolute | Exact rationals; QuantLib `OvernightLeg` | QuantLib within 5e-14 |
| Step curve | `simple_analytic` | Exact integral; QuantLib `ForwardCurve` | Within 2e-15 |
| Step fit | Rates within 1e-10 of known truth | QuantLib par rates | Within 1e-12 |
| Futures convexity | `simple_analytic` | QuantLib `HullWhite::convexityBias` | Within 1e-15 plus 1e-12 relative |
| CSA discount | `interpolation` | Hand replay | No outside source |
| OIS index basis | 1e-10 | QuantLib fair-rate difference | Within 1e-12 |
| Joint bootstrap | Pillars within 1e-9 | QuantLib two-step build | Within 1e-10 |
| Smooth forward fit | 1e-10 plus 1e-8 relative | Exact rationals; NumPy | NumPy within 1e-9 |
| Huber Nelson-Siegel | 1e-9; outlier set exact | IRLS at 50 digits; SciPy from three starts | Within 1e-8 |

Every target is wide enough for libm and solver differences, and narrow enough to catch each of the 65 wrong conventions the generator lists (the smallest gap is 2.6e-6).
