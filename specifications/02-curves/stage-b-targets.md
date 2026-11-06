# Stage B numeric targets

Set before any stage B code, as plan section 8 requires. "Oracle measured" is from `oracle/REPORT.md`, and is the oracle's own replay against the outside source. No implementation has run against these.

Calibration is judged on repricing and objective, never on fitted parameters, unless the minimum is unique. Iteration counts are never compared.

| Item | Target | Oracle | Oracle measured |
|---|---|---|---|
| SONIA, SOFR curve solve | Every quote reprices below 1e-13 in rate | Own repricing | Solver tolerance 1e-15 in log discount factor |
| SONIA, SOFR pillars | Within 1e-9 of golden | QuantLib | Within 2e-11 |
| OIS floating leg | General form always; telescoped form only at zero lag and unit notional | Identity | On SOFR 10Y the telescoped form misses by 1.1e-4 per unit |
| OIS PV | 1e-3 plus 1e-9 relative, on 1e6 | QuantLib, Strata pricer | QuantLib within 1e-3; Strata within 4.1e-10 |
| Projection pillars | Within 1e-9 | QuantLib | Within 1e-10 |
| Vanilla swap PV | 1e-3 plus 1e-9 relative, on 1e6 | QuantLib | Within 1e-2 in the oracle assertion |
| FRA PV | As above | QuantLib | Within 1e-2 |
| Tenor basis | 1e-9 in rate | Hand replay | No outside source |
| DV01, key-rate | 1e-3 plus 1e-8 relative, on 1e6 | QuantLib with bumped quotes; sum identity | Within 3.4e-6; sum within 1e-5 relative of parallel |
| FX forward, delta | 1e-3 plus 1e-9 relative, on 1e6 | Analytic; central bump | Delta bump within 1e-8 relative |
| FX implied ratio, basis | 1e-7 bp | Analytic; QuantLib `FxSwapRateHelper` | Ratios within 1.9e-15 |
| Hedge solve | `x` within 1e-8; first-order conditions within 1e-9 | Sign enumeration; SciPy | Within 6e-10 of SciPy |
| Gauss-Newton, LM, BFGS | Unique minima: parameters within 1e-6. Known truth: objective within 1e-6 | Closed form, SciPy | Reached by plain methods |
| Nelson-Siegel fit | Objective at most 1e-10; parameters not compared | Known truth | See report |
| Regularised fit | Parameters within 1e-6 of closed form | Closed form | |
| Bid/ask | Exact breach list | Hand | |
| Calibration Jacobian | 1e-5 plus 1e-4 relative | Central bump | |
| Use case 1 | 1e-3 plus 1e-9 relative | Hand | |
| Use case 2 | 1e-2 plus 1e-6 relative, on 1e7; residual key-rate norm under 20% of unhedged | Replay | Holds |

Strata checks schedules, and OIS swap PVs through its own pricer on the same curve, but not curve building: its calibrator has not been run. See `stage-b-rulings.md` for each suite's sources.
