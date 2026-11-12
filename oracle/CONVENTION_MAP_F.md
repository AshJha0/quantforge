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
| `SCIPY.CHI2` | 06-risk/var-es-and-backtests.md Kupiec, Christoffersen p-values | scipy.stats.chi2.sf(lr, dof); likelihood ratios from scipy.stats.binom.logpmf and scipy.special.xlogy |
| `SCIPY.MLE` | 06-risk/var-es-and-backtests.md Kupiec, Christoffersen (R6-13) | Bernoulli and first-order Markov likelihoods maximised numerically by scipy.optimize.minimize_scalar (bounded Brent, xatol 1e-15), not the closed-form MLE; transitions by numpy; p-values scipy.stats.chi2.sf; oracle/python/outside_f_r6.py |
| `SCIPY.BINOM` | 06-risk/var-es-and-backtests.md traffic light | scipy.stats.binom.cdf(x, n, 1 - c); zones at 0.95 and 0.9999; plus factor Basel 1996 Table 2 |
| `SCIPY.NORM` | 06-risk/var-es-and-backtests.md parametric VaR and ES | scipy.stats.norm.ppf; ES by scipy.integrate.quad of the normal tail (not the closed form) |
| `NUMPY.QUANTILE` | 06-risk/var-es-and-backtests.md historical VaR | numpy.quantile(losses, c, method='inverted_cdf') (Hyndman and Fan type 1); ES as the mean of the sorted losses from the first position holding that quantile (agrees with the spec without ties; a tie at the VaR scenario, risk_f4-0107, is not outside-checked) |
| `SCIPY.EIGH` | 06-risk/book-sensitivities.md PCA | numpy.cov(ddof=1); scipy.linalg.eigh (LAPACK syevr); sign rule of the spec |
| `SCIPY.LSTSQ` | 04-pricing/use-cases.md use case 4 factor attribution | scipy.linalg.lstsq on [1, F] (LAPACK gelsd); R^2, residual vol and standard errors from its residuals and numpy.linalg.inv of X'X |
| `SCIPY.QUAD` | 02-curves/curve-framework.md discount factors of MONOTONE_CONVEX from its forward | scipy.integrate.quad (QUADPACK qags) of QuantLib ConvexMonotoneInterpolation, per section, epsrel 1e-13 |
| `ARCH.GARCH` | 05-volatility/garch.md loglik, estimate; 06-risk/var-es-and-backtests.md FHS | arch 7.2.0 (run under WSL): GARCH(1,0,1).compute_variance with backcast = (v0 - omega)/(alpha + beta) so that sigma2_1 = v0; Normal / StudentsT (standardised) loglikelihood; EWMAVariance(lam) with backcast = mean square; fits maximise that objective (scipy Nelder-Mead, Newton on a finite-difference Hessian); oracle/python/outside_garch_arch.py |
| `CBOE.SAMPLE` | 05-volatility/vix-index.md Cboe sample | Cboe Volatility Index Methodology v6.0, Appendix 3 printed values (F, K0, sigma^2, VIX) |
