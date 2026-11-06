# Stage B numeric targets

Written before any stage B code, as plan section 8 requires. These are proposed limits, and nothing has been run against them. Stage B specs may tighten them; loosening one needs a recorded reason.

| Item | Target | Oracle |
|---|---|---|
| SONIA OIS curve, global solve | Every input quote reprices within 1e-10 in rate (1e-6 bp) | Own repricing |
| SONIA and minimal SOFR curves | Discount factors within 1e-9 of QuantLib on the same quotes, conventions and interpolation, out to 30 years | QuantLib; Strata second |
| OIS floating leg | Uses `sum (D(s_i)/D(e_i)-1) D(p_i)`; equals `D(T0)-D(Tn)` within 1e-12 at zero payment lag and unit notional | Analytic |
| FRA and swap PV | Par instrument PV within 1e-8 per 1 notional | QuantLib |
| DV01 | Central 1 bp bump within 1e-6 relative of QuantLib on the same bump | QuantLib |
| Key-rate risk | Sum within 1e-8 relative of parallel risk when bump shapes sum to one, to first order at 0.01 bp | Identity |
| FX forward | Covered-parity value within 1e-10 relative | Analytic |
| FX swap points and basis | Quotes reprice within 1e-10 | Own repricing |
| Hedge solve | Residual meets first-order conditions within 1e-9 | Optimality conditions |
| Gauss-Newton, BFGS | Known-truth problems: parameters within 1e-6, objective within 1e-10 of the known minimum | Known truth; SciPy |
| Regularised fit | Objective within 1e-8 of oracle; repricing error is reported, not forced to zero | SciPy |
| Bid/ask fit | Fitted quote inside bid/ask, or the breach is listed | Own check |
| Spread cost model | Exact on hand cases, class `simple_analytic` | Hand |

Calibration is judged on repricing and objective value, never on parameters.
