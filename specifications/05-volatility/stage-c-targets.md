# Stage C numeric targets

Set before any stage C code, as plan section 8 requires. "Oracle measured" comes from a run of `oracle/python/gen_stage_c.py`, which stops if a limit is broken. No implementation has run yet. Passing will be self-assessment, not validation.

Calibration is judged on repricing. Parameters are compared only where several starts reach one minimum, which the generator checks. Iteration counts are never compared.

**No golden depends on libm rounding or a solver path.** Guards in the generator stop the run when:

- an implied vol has `vega < 1e-3 max(price, 1)`;
- a boolean sits near its threshold: density within 1e-3 of 0 where negative, SSVI margins within 1e-6, surface slopes within 1e-9 of a tolerance, parity quotes within 1e-3 of a spread edge;
- a fit is not unique across starts;
- a bumped second derivative could move by the limit from four ulps of rounding (this is why `hv` is `1e-3 v`);
- arbitrage-free prices move more than 1e-9 when `alpha` moves by 2e-15.

| Item | Target | Oracle | Oracle measured |
|---|---|---|---|
| Equity forward, flat and curve forms | `simple_analytic`: 1e-12 plus 1e-10 relative | Rolled route, step by step between dividends; plan check case | Rolled route within 1e-10; 97.0149584 against wrong 97.0640923 |
| Option on dividend stock, PV | 1e-12 plus 1e-10 relative | QuantLib `AnalyticDividendEuropeanEngine`, two routes with a borrow | Within 1e-9 |
| Same, delta, gamma, vega | As PV | Same | Within 1e-9, vega 1e-8 |
| Parity forward | 1e-9 plus 1e-10 relative with exact quotes; class `interpolation` with noise | NumPy, known truth | Exact |
| Black-76, Bachelier price | 1e-12 plus 1e-10 relative | QuantLib, Strata, parity | QuantLib within 1e-9; Strata within 2.1e-14 |
| Black-Scholes price | As above | Analytic through Black-76; QuantLib engine in `greeks` | Within 1e-8 |
| Implied vol | `root_finding`: 1e-10 plus 1e-10 relative; Bachelier 1e-9 | Known truth, QuantLib, Strata | QuantLib to its stated 1e-6 on the solve |
| Analytic Greeks | 1e-12 plus 1e-10 relative | QuantLib (delta, gamma, vega, theta, rho); Strata (delta, gamma, vega, vanna, volga) | QuantLib within 1e-8 relative; Strata 2.1e-14 |
| Analytic against bump | Absolute 2e-4 plus 1e-4 relative | Bump in the oracle, every model and grid point | Holds |
| Bump Greeks, between builds | 1e-4 plus 1e-6 relative | Replay | Rounding guard holds |
| Delta to strike and back | `interpolation`; back 1e-10 | Round trip | 1e-12 |
| SVI evaluate | `interpolation`: 1e-10 plus 1e-8 relative | QuantLib `SviSmileSection`, Vogt counterexample | QuantLib within 1e-12 |
| SVI fit, exact quotes | Parameters, rmse within 1e-6 | Known truth, SciPy | Within 1e-6 |
| SVI fit, noise 1e-4 | rmse within 1e-8; parameters 2e-4 | SciPy, four starts | Starts agree within 1e-5 |
| SSVI evaluate | `interpolation`; flags exact | Analytic; ATM equals theta | 1e-15 at ATM |
| SSVI fit | Within 1e-6 | Known truth, SciPy | Within 1e-6 |
| Surface query | `interpolation` | QuantLib `BlackVarianceSurface`, on 81 points in and beyond the grid | Within 1e-12 |
| Surface check | Exact lists | Constructed cases | Exact |
| Bucket vega | 1e-7 plus 1e-8 relative; sum within 5% of parallel | Replay | Holds |
| Hagan SABR, shifted too | `interpolation` | QuantLib, Strata | Within 1e-10 |
| SABR density | 1e-5 plus 1e-6 relative; flag and `E_ARBITRAGE` exact | Replay; negative at about -1e-3 or worse | Shifted case equal to unshifted within 1e-6 |
| SABR fit, exact quotes | Within 1e-6 | Known truth, SciPy | Within 1e-6 |
| SABR fit, noise 2e-4 | rmse within 1e-8; parameters 1e-4 | SciPy, four starts | Starts agree within 1e-5 |
| Arbitrage-free SABR, between builds | `numerical_scheme`: 1e-8 plus 1e-8 relative | Replay of the same grid | Mass within 1e-11, mean within 1e-10 relative |
| Arbitrage-free SABR, method error | Calls within 5e-4 of CEV truth at `nu = 0`; vols within 7e-3 of Hagan where Hagan is safe | QuantLib `AnalyticCEVEngine` | CEV 1.5e-5; Hagan 5.8e-3 |
| Arbitrage-free SABR against another method | Vols within 2e-2 | QuantLib `NoArbSabrSmileSection` (Doust) | 1.8e-2. Different model of the floor, so a coarse check only |
| Use case 3 | 2e-3 plus 1e-7 relative | Known truth through parts checked above | Holds |

Time steps are first order, so the 5e-4 and 7e-3 lines bound method error, not rounding. Only the `numerical_scheme` line is the gate between builds.
