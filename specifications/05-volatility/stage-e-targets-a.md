# Stage E numeric targets, spec A

Set before any stage E code (plan section 8). "Oracle measured" is from `oracle/python/gen_stage_e_a.py`, which stops if a limit is broken, and `oracle/python/outside_e_a.py`. No implementation has run yet; passing will be self-assessment.

**Money reading.** Prices here are per unit of underlying at spot 100. On a 10m notional (100,000 units) the `interpolation` class (1e-10 absolute) is 1e-5 currency units; on vols, 1e-10 is far below a hundredth of a vol point. `conformance/tolerances/money.md` gives the class table.

## E1 arbitrage-free surfaces, local and forward vol

| Item | Target | Oracle | Oracle measured |
|---|---|---|---|
| `vol.svi.surface_check` lists, flag | Exact | QuantLib `SviSmileSection` total variance (calendar) and the sign of its numerical density (butterfly); wing algebra on inputs; Vogt counterexample [GJ14 section 5] | 9 of 9 value cases reproduced by QuantLib |
| `vol.ssvi.to_svi` | `simple_analytic` | Closed form; replay through stage C SSVI evaluate | Within 1e-15 at five `k` per case |
| `vol.svi.fit_surface` | Parameters and `rmse` within 1e-6 absolute; lists exact | Known truth, SciPy, four starts | Truth within 1e-7, starts agree within 1e-7 |
| `vol.local.dupire` | `interpolation` | Closed form; 40-digit price-based Dupire `2 C_T/(K^2 C_KK)` from Black prices | Within 1e-9 relative at every point |
| `vol.forward.vol` | `simple_analytic` | QuantLib `BlackVarianceCurve.blackForwardVol` | Within 1e-15 |
| `vol.smile.dynamics` | `interpolation` | QuantLib `SviSmileSection`, `blackFormula`, `BlackCalculator`; deltas also by 40-digit bump of the full price | Bump within 1e-12 |
| `vol.volofvol.measure` | `statistics` | QuantLib `IncrementalStatistics`; mpmath | Within 1e-14 |

Guards: `|g| > 1e-6` and calendar gaps above 1e-9 on every check-grid point; `|g| > 1e-4` and `w_T > 1e-6` at every Dupire point of a value case; Lee slopes and wing slope gaps 1e-6 from their thresholds.

Outside-oracle share (E1): 31 of 67 cases (46%); error cases are in the denominator. The stage floor of 60% applies to the stage as a whole; E2, E3 and E5 are mostly QuantLib engines and carry the share. The running total is in `oracle/OUTSIDE_E_A.md`.

## E3 FX smile

| Item | Target | Oracle | Oracle measured |
|---|---|---|---|
| `fx.option.price` | `simple_analytic`; price limit 1e-6 currency units on 1m foreign notional plus 1e-10 relative | QuantLib `BlackScholesMertonProcess` (foreign curve as dividend curve) with `AnalyticEuropeanEngine` | All outputs reproduced |
| `fx.delta.from_strike`, `fx.atm.strike` | `simple_analytic` | QuantLib `BlackDeltaCalculator` (`deltaFromStrike`, `atmStrike`) | All reproduced |
| `fx.delta.to_strike`, `fx.smile.from_quotes` | 1e-10 absolute plus 1e-9 relative on strikes (far below a pip) | QuantLib `strikeFromDelta`; oracle solve to 1e-15 with a conditioning guard | QuantLib agrees within 2e-10 relative |

Outside-oracle share (E3): 114 of 125 (91%); spec A running total in `oracle/OUTSIDE_E_A.md` (145 of 192, 75.5%).

## E2 Heston, Bates, Merton, SLV

| Item | Target | Oracle | Oracle measured |
|---|---|---|---|
| `vol.heston.price`, `vol.bates.price` | 1e-8 absolute plus 1e-9 relative per unit at spot 100 (1e-3 currency units on 100,000 units) | QuantLib `AnalyticHestonEngine`, `BatesEngine` at relative 1e-13; 30-digit mpmath Lewis integral | QuantLib within 1e-9; reference recipe within 2.4e-11 |
| Small vol of variance (`xi` 1e-3, 1e-2) | As above | 30-digit mpmath; QuantLib within 1e-12; Black-Scholes at average variance within 0.05 `xi` | The binary64 recipe is about 1e-9 off at `xi = 1e-3` (cancellation), inside the target |
| `vol.heston.cf` | `fourier` | 30-digit mpmath | Within 1e-13 |
| `vol.merton.price` | As Heston | Poisson series, Lewis at 256 nodes, 30-digit mpmath (no QuantLib engine in the Python wheel) | Within 1e-9 |
| `vol.slv.leverage` | `numerical_scheme` (1e-8) | Reference scheme; 1e-12 input perturbation moves leverage under 1e-8; grid refinement within 2% at the spot; flat-vol, zero-correlation limit within 3% of 1 near the money | Holds; mass at `T` 0.988 to 1.000 |

Outside-oracle share (E2): 18 of 46 (Heston and Bates value cases); spec A running total in `oracle/OUTSIDE_E_A.md`.
