# Stage B numeric targets

Set before any stage B code, as plan section 8 requires. "Oracle measured" is from `oracle/REPORT.md`, and is the oracle's own replay against the outside source. No implementation has run against these.

Calibration is judged on repricing and objective, never on fitted parameters, unless the minimum is unique. Iteration counts are never compared.

| Item | Target | Oracle | Oracle measured |
|---|---|---|---|
| SONIA, SOFR curve solve | Every quote reprices below 1e-13 in rate | Own repricing | Solver tolerance 1e-15 in log discount factor |
| SONIA, SOFR pillars | Within 1e-9 of golden | QuantLib | Within 5e-12 |
| OIS floating leg | General form always; telescoped form only at zero lag and unit notional | Identity | On SOFR 10Y the telescoped form misses by 1.1e-4 per unit |
| OIS PV | 1e-3 plus 1e-9 relative, on 1e6 | QuantLib | Within 1e-3 |
| Projection pillars | Within 1e-9 | QuantLib | Within 1.1e-14 |
| Vanilla swap PV | 1e-3 plus 1e-9 relative, on 1e6 | QuantLib | Within 1e-2 in the oracle assertion |
| FRA PV, tenor basis | As above; 1e-9 in rate | Hand replay | No outside source |
| DV01, key-rate | 1e-3 plus 1e-8 relative, on 1e6 | Replay; key-rate sum identity | Sum within 1e-5 relative of parallel |
| FX forward, delta | 1e-3 plus 1e-9 relative, on 1e6 | Analytic; central bump | Delta bump within 1e-8 relative |
| FX basis | 1e-7 bp | Analytic | |
| Hedge solve | `x` within 1e-8; first-order conditions within 1e-9 | Sign enumeration | Conditions hold |
| Gauss-Newton, LM, BFGS | Unique minima: parameters within 1e-6. Known truth: objective within 1e-6 | Closed form, SciPy | Reached by plain methods |
| Nelson-Siegel fit | Objective at most 1e-10; parameters not compared | Known truth | See report |
| Regularised fit | Parameters within 1e-6 of closed form | Closed form | |
| Bid/ask | Exact breach list | Hand | |
| Calibration Jacobian | 1e-5 plus 1e-4 relative | Central bump | |
| Use case 1 | 1e-3 plus 1e-9 relative | Hand | |
| Use case 2 | 1e-2 plus 1e-6 relative, on 1e7; residual key-rate norm under 20% of unhedged | Replay | Holds |

Not done: Strata as a second curve source. It was used only for conventions, which the first version of this page did not make plain. A second build through Strata's calibrator is a candidate before the stage B exit.
