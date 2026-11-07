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

## Wave 2, D2: bonds and repo

| Item | Target | Oracle | Oracle measured |
|---|---|---|---|
| Price, accrued, durations, convexity from yield | `simple_analytic` | QuantLib `FixedRateBond`, `BondFunctions` | Within 1e-10; convexity 1e-8 |
| Yield from price | `root_finding` | Known truth; QuantLib | Exact round trip |
| Curve price, Z-spread | `interpolation`; Z-spread `root_finding` | QuantLib `zSpread` | Within 1e-10 |
| Asset swap, bond-OIS spread | `interpolation` | Hand replay | No outside source |
| FRN | `interpolation` | Replay; par identity | Par within 1e-11 |
| Repo forward, special repo, implied repo | `simple_analytic` | Analytic | |
| Conversion factor, CTD index | Exact | CBOT formula, hand | No outside library |
| Sovereign fit, RV residuals | Betas within 1e-8 | Known truth; SciPy from three starts | Within 1e-9 |

## Wave 2, D3: cross-currency and NDF

| Item | Target | Oracle | Oracle measured |
|---|---|---|---|
| Basis-adjusted foreign curve | Pillars within 1e-9 | Known truth | Replay within 1e-13 |
| Cross-currency swap PV | 1e-9 per unit notional | QuantLib `OvernightLeg` NPV for coupons | Within 1e-6 on 1e7 |
| NDF | `interpolation` | Analytic | |

## Wave 2, D4: credit

| Item | Target | Oracle | Oracle measured |
|---|---|---|---|
| ISDA CDS price, upfront, par spread | 1e-9 per unit notional | QuantLib `IsdaCdsEngine` | NPV within 7e-16 per unit |
| Hazard bootstrap | Survival within 1e-9 | QuantLib fair spreads on the result | Within 2e-10 |
| Index intrinsic, composite curves | 1e-9 | Through the above | |

## Wave 2, D5: equity

| Item | Target | Oracle | Oracle measured |
|---|---|---|---|
| Implied dividends, futures basis, TRS | `simple_analytic` | Analytic | No outside library |
| Implied borrow, financing spread | `root_finding` | Known truth | |
| Index dividends, dividend futures, rebalance, corporate actions | `simple_analytic` | Exact rationals | |

## Wave 3, D6: inflation

| Item | Target | Oracle | Oracle measured |
|---|---|---|---|
| CPI curve with seasonality | `simple_analytic`; pillars reprice exactly | Analytic | |
| ZCIS, linker from curve | `interpolation` | Analytic | |
| Linker from real yield | `simple_analytic` | Exact-rational reference CPI; bond formulas checked against QuantLib in D2 | |

Every target is wide enough for libm and solver differences, and narrow enough to catch each of the 65 wrong conventions the generator lists (the smallest gap is 2.6e-6).
