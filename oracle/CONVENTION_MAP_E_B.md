# Convention map for stage E spec B outside-oracle checks

Plan rule 11.2.5. Rows used by `oracle/python/outside_e_b.py`, from `oracle/python/qf_oracle/convmap_e_b.py`. Base rows are the stage D table (`oracle/CONVENTION_MAP.md`); only the new rows are listed here.

Library: QuantLib 1.44 (Python wheel). Version recorded per case in `oracle/outside_register_e_b.json`.

Review: self-reviewed 2026-11-08. Self-assessment, not an outside review.

| Row | Spec | QuantLib object | Note |
|---|---|---|---|
| `VS.DDKZ_SPOT` | 05-volatility/variance-swaps.md replication: DDKZ weights, reference S* = spot, puts walked down, calls up, one extension strike | `ql.ReplicatingVarianceSwapEngine(proc, dk, calls, puts` | QuantLib's drift term is 2/T (rT - (e^{rT} - 1)); it ignores the dividend yield, so only q = 0 cases are mapped (ruling E-B3) |
| `VS.INSTRUMENT` | 05-volatility/variance-swaps.md pv = N_var D (K_fair - K_var), long | `ql.VarianceSwap(ql.Position.Long, K, N, a, m), ""` |  |
| `PROC.BSM` | 05-volatility/variance-swaps.md flat continuous r and q on ACT/365F; Black vol per listed strike | `ql.BlackScholesMertonProcess(s, q, r, v), ""` |  |
| `CRV.FLAT_CONT_365F` | 05-volatility/variance-swaps.md flat continuously compounded rate, ACT/365F | `ql.YieldTermStructureHandle(ql.FlatForward(a, r, ql.Actual365Fixed(), ql.Continuous)), ""` |  |
| `VOL.STRIKE_TABLE` | 05-volatility/variance-swaps.md vols given at listed strikes only; the engine reads them only there | `ql.BlackVarianceSurface(a, ql.NullCalendar(), dates, ks, m, ql.Actual365Fixed(` | two identical maturity columns so the surface is defined; read only at listed strikes and the maturity |
| `SABR.SECTION` | 05-volatility/rates-vol-cube.md smile: sabr.md Hagan lognormal vol at the swaption's own forward and expiry time | `ql.SabrSmileSection(t, F, [a, b, n, r]), "QuantLib parameter order is alpha, beta, nu, rho"` | QuantLib parameter order is alpha, beta, nu, rho |
| `INTERP.BILINEAR` | 05-volatility/rates-vol-cube.md parameters bilinear in (expiry time ACT/365F, tenor years) | `ql.BilinearInterpolation(xs, ys, M), "QuantLib's matrix is indexed [y][x]"` | QuantLib's matrix is indexed [y][x] |
| `SWO.BLACK_ENGINE` | 05-volatility/caps-and-swaptions.md swaption, Black on the forward swap rate, time ACT/365F | `ql.BlackSwaptionEngine(h, ql.QuoteHandle(ql.SimpleQuote(v)), ql.Actual365Fixed()), ""` |  |
| `OPT.BLACK_FORMULA` | 05-volatility/black-models.md BLACK_76, discounted | `ql.blackFormula, "formula level"` | formula level |
| `OPT.BACHELIER_FORMULA` | 05-volatility/black-models.md BACHELIER, discounted | `ql.bachelierBlackFormula, "formula level"` | formula level |
| `OPT.BLACK_IMPLIED` | 05-volatility/rates-vol-cube.md implied Black vol from a premium | `ql.blackFormulaImpliedStdDev, "returns the standard deviation; divided by sqrt(t)"` | returns the standard deviation; divided by sqrt(t) |
| `CORR.EIGEN` | 06-risk/correlation.md validation: eigenvalues of the symmetric input | `ql.SymmetricSchurDecomposition(M), "Jacobi rotations"` | Jacobi rotations |
| `CORR.HIGHAM` | 06-risk/correlation.md nearest correlation, unweighted Frobenius norm (Higham 2002) | `ql.pseudoSqrt(M, ql.SalvagingAlgorithm.Higham), "returns a square root S; the repaired matrix is S S^T. Qua...` | returns a square root S; the repaired matrix is S S^T. QuantLib stops near 1e-6 in the iterate |
| `CDS.MIDPOINT` | 04-pricing/credit-options-and-copulas.md underlying legs: mid-point default, accrual on default ACT/360 to the mid date | `ql.MidPointCdsEngine(dp, R, h), "the CdsOption builds its own MidPointCdsEngine on the underlying"` | the CdsOption builds its own MidPointCdsEngine on the underlying |
| `CDSO.BLACK` | 04-pricing/credit-options-and-copulas.md Black on the forward spread with risky annuity; front-end protection for non-knock-out payers | `ql.BlackCdsOptionEngine(dp, R, h, ql.QuoteHandle(ql.SimpleQuote(v))), ""` |  |
| `CDS.SCHEDULE` | 04-pricing/credit-options-and-copulas.md quarterly from expiry, unadjusted, no calendar, forward generation | `ql.Schedule(a, b, ql.Period(3, ql.Months), ql.NullCalendar(), ql.Unadjusted, ql.Unadjusted, ql.DateGenerati...` |  |
| `CRV.FLAT_HAZARD_365F` | 04-pricing/credit-options-and-copulas.md flat hazard on ACT/365F | `ql.DefaultProbabilityTermStructureHandle(` |  |
| `NORM.BIVARIATE` | 04-pricing/credit-options-and-copulas.md bivariate normal CDF | `ql.BivariateCumulativeNormalDistributionWe04DP(rho), "West (2004) double precision"` | West (2004) double precision |
| `NORM.INVERSE` | 04-pricing/credit-options-and-copulas.md normal quantile | `(ql.InverseCumulativeNormal(), ql.CumulativeNormalDistribution(), ql.NormalDistribution(` | QuantLib's inverse is good to about 3e-9; one Newton step with QuantLib's own CDF and density brings it to rounding |
