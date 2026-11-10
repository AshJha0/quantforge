# Stage F cases without an outside oracle (rule 11.2.5, ruling F-23)

Written by the spec session on 2026-11-10, last updated after the R5 audit additions, when `outside_f.py` reported **225 of 438 = 51.4%** (floor 60%; the coordinator ruled that error cases stay in the denominator and the floor is recorded as failed). Each row is a group of cases in `datasets/golden/stage_f` that no free outside source reproduces, with the reason. The register of verified cases is `oracle/outside_register_f.json`; the library objects are in `oracle/CONVENTION_MAP_F.md`.

| Suite | Cases | Count | Reason |
|---|---|---|---|
| all value suites | error cases | 79 | An error code is this platform's own input rule; no library is an oracle for it. They stay in the denominator (coordinator ruling, 2026-11-10). |
| `cdsidx_f` | `credit.cdsindex.option_price` | 54 | R7: the reference worked example, Pedersen (2003), is not freely available. QuantLib has no CDS index option. Needs a human with the paper (README known issue). |
| `book_f` | lifecycle and marks | 23 | The platform's own book conventions (average cost, fallback order, IPV flag, ruling F-34). No library defines them. |
| `frtb_f` | `risk.frtb.girr_delta` | 13 | MAR21 and MAR23 print no worked example, and no free library implements the SBM with Basel parameters (checked 2026-11-10). |
| `risk_f3` | `risk.book.ois_sensitivity` | 5 | QuantLib's bootstrap stops at 1e-12, so a bump-and-rebuild through it misses the Q3a bound of 1e-8 relative (as with the monotonic log cubic Jacobian in Q4). The AAD reference is Rust's, which is a language lane, not an outside source. |
| `risk_f3` | `risk.credit.jtd` | 5 | A definition (value after default minus market value) with no library form. (Cross gamma is now checked through QuantLib `MakeOIS` revaluations.) |
| `risk_f4` | `risk.var.monte_carlo` | 4 | Driven by `core.rng` draws; no library reproduces those streams. |
| `curve_f` | `TENSION_SPLINE`, `HYBRID` | 12 | QuantLib has no tension spline or hybrid step-and-smooth curve; SciPy has no tension spline. |
| `curve_f` | inspect `LINEAR_ZERO` | 1 | QuantLib's `ZeroCurve` extrapolates the zero rate linearly; the spec holds the last discrete forward flat, so the dates beyond the last pillar differ. (Log-linear and log cubic with a jump are now checked.) |
| `joint_f` | four-curve, steps and log cubic systems; funding curve | 6 | Constant-notional xccy and `OIS_STEPS` with futures and solved turns have no QuantLib builder. QuantLib's monotonic log cubic bootstrap stops at 1e-12, which misses the Jacobian bound. The funding curve's piecewise-flat instantaneous spread is not QuantLib's `PiecewiseZeroSpreadedTermStructure` (linear zero spread). |
| `risk_f4` | `risk.var.historical` (`risk_f4-0107`) | 1 | Ties at the VaR scenario: where the spec's tail starts inside a tied block is the spec's own position rule (F-31); `numpy.quantile` gives the VaR but cannot place the tail. |
| `garch_f` | `vol.garch.estimate` (`garch_f-0009`) | 1 | `arch` reproduces it to 2.6e-8 relative in `omega`, short of the new 1e-8 limit (F-43); the verifier's finite-difference Newton needs a rerun under WSL, which timed out on 2026-11-10. |
| `vix_f` | `vol.vix.term_variance` | 5 | Only the Cboe sample strip has published numbers. |
| `lvc_f` | `vol.local.dupire` | 4 | The slice-expiry continuity rule is the spec's own. A QuantLib `LocalVolSurface` comparison was not attempted. |

## Notes

- `arch` cannot run on the Windows host: Windows Application Control blocks the pandas DLLs it imports (the same block as Clang, README known issues). `outside_garch_arch.py` runs under WSL with `uv run --no-project --with arch==7.2.0 --with pandas==2.2.3 --with "numpy<2.3" --with scipy`, writes `oracle/outside_arch_f.json`, and `outside_f.py` judges it. `arch` is not added to the oracle's locked environment.
- No free-source candidate is left. 60% of 438 is 263 cases, 38 more than now; the 134 value cases left have no free source, apart from the two `garch_f` and ties notes above.
