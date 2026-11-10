# Stage F convention map (rule 11.2.5)

QuantLib 1.44. self-reviewed 2026-11-09 (spec session); second review by the R5 audit. Written by `oracle/python/outside_f.py`.

| Row | Spec | Library objects |
|---|---|---|
| `CRV.MONOTONE_CONVEX` | 02-curves/curve-framework.md MONOTONE_CONVEX = QuantLib ConvexMonotone(quadraticity 0, monotonicity 1, forcePositive false), ruling F-19 | PiecewiseConvexMonotoneForward(ref, helpers, Actual365Fixed, [], [], ConvexMonotone(0, 1, False)); ConvexMonotoneInterpolation on discrete forwards |
| `CRV.MONOTONIC_LOG_CUBIC` | 02-curves/curve-framework.md MONOTONIC_LOG_CUBIC = QuantLib MonotonicLogCubic | MonotonicLogCubicDiscountCurve(dates, dfs, Actual365Fixed) for D; MonotonicCubicNaturalSpline(t, ln D).derivative for f; PiecewiseLogCubicDiscount(ref, helpers, Actual365Fixed[, jumps]) |
| `OIS.HELPER` | 02-curves/ois-curves.md periods and lags | OISRateHelper(settlementDays, tenor, quote, index, discount=None, telescopic=True, paymentLag) |
| `IDX` | 01-core/conventions.md SOFR, SONIA, ESTR | ql.Sofr(), ql.Sonia(), ql.Estr() |
| `TERM.HELPERS` | 02-curves/projection-and-fra.md USD-TERM-3M deposits, FRAs, swaps | IborIndex TERM 3M (2 days, US GovernmentBond, ModifiedFollowing, Actual360); DepositRateHelper, FraRateHelper, SwapRateHelper(Annual, ModifiedFollowing, Thirty360 BondBasis, exogenous discount) |
| `CRV.LOG_LINEAR_DF` | 02-curves/curve-framework.md LOG_LINEAR_DF | PiecewiseLogLinearDiscount(ref, helpers, Actual365Fixed) |
| `CBOE.SAMPLE` | 05-volatility/vix-index.md Cboe sample | Cboe Volatility Index Methodology v6.0, Appendix 3 printed values (F, K0, sigma^2, VIX) |
