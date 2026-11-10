# Stage F cases without an outside oracle (rule 11.2.5, ruling F-23)

Written by the spec session on 2026-11-10, after `outside_f.py` reported **212 of 403 = 52.6%** (floor 60%). Each row is a group of cases in `datasets/golden/stage_f` that no free outside source reproduces, with the reason. The register of verified cases is `oracle/outside_register_f.json`; the library objects are in `oracle/CONVENTION_MAP_F.md`.

| Suite | Cases | Count | Reason |
|---|---|---|---|
| all value suites | error cases | 72 | An error code is this platform's own input rule; no library is an oracle for it (the same reasoning that leaves E1 out of the denominator, ruling F-23). They stay in the denominator as F-23 is written: changing that is the owner's call, not a spec ruling made after the results were seen. Without them the share would be 212 of 331 = 64.0%. |
| `cdsidx_f` | `credit.cdsindex.option_price` | 34 | R7: the reference worked example, Pedersen (2003), is not freely available. QuantLib has no CDS index option. Needs a human with the paper (README known issue). |
| `book_f` | lifecycle and marks | 23 | The platform's own book conventions (average cost, fallback order, IPV flag, ruling F-34). No library defines them. |
| `frtb_f` | `risk.frtb.girr_delta` | 13 | MAR21 and MAR23 print no worked example, and no free library implements the SBM with Basel parameters (checked 2026-11-10). |
| `risk_f3` | `risk.book.ois_sensitivity` | 5 | QuantLib's bootstrap stops at 1e-12, so a bump-and-rebuild through it misses the Q3a bound of 1e-8 relative (as with the monotonic log cubic Jacobian in Q4). The AAD reference is Rust's, which is a language lane, not an outside source. |
| `risk_f3` | `risk.curve.cross_gamma`, `risk.credit.jtd` | 11 | Cross gamma: needs QuantLib OIS swap objects with the spec's payment-lag schedule on a bumped pillar curve; not attempted yet (candidate, about a day). JTD: a definition with no library form. |
| `risk_f4` | `risk.var.monte_carlo` | 4 | Driven by `core.rng` draws; no library reproduces those streams. |
| `curve_f` | `TENSION_SPLINE`, `HYBRID` | 10 | QuantLib has no tension spline or hybrid step-and-smooth curve; SciPy has no tension spline. |
| `curve_f` | inspect `LOG_LINEAR_DF`, `LINEAR_ZERO`, `MONOTONIC_LOG_CUBIC` with a jump | 3 | Not attempted: QuantLib `DiscountCurve` and `ZeroCurve` would give the discount factors, but the forward at a pillar needs the spec's one-sided rule, which needs checking first. Candidate. |
| `joint_f` | four-curve, steps and log cubic systems; funding curve | 6 | Constant-notional xccy and `OIS_STEPS` with futures and solved turns have no QuantLib builder. QuantLib's monotonic log cubic bootstrap stops at 1e-12, which misses the Jacobian bound. The funding curve's piecewise-flat instantaneous spread is not QuantLib's `PiecewiseZeroSpreadedTermStructure` (linear zero spread). |
| `garch_f` | `vol.garch.estimate` 0009, 0012 | 2 | `arch` 7.2.0 (run under WSL) reproduces the parameters and log-likelihood, but its standard errors were 1.6e-5 relative off against a 1e-5 limit, from the finite-difference Hessian used on the arch objective. A scaled-coordinate Hessian is in `outside_garch_arch.py` but not yet run: WSL stopped starting on 2026-11-10 (`HCS_E_TERMINATED`, then `CreateVm` timeout). Rerun when WSL is back. |
| `vix_f` | `vol.vix.term_variance` | 5 | Only the Cboe sample strip has published numbers. |
| `lvc_f` | `vol.local.dupire` | 3 | The slice-expiry continuity rule is the spec's own. A QuantLib `LocalVolSurface` comparison was not attempted. |

## Notes

- `arch` cannot run on the Windows host: Windows Application Control blocks the pandas DLLs it imports (the same block as Clang, README known issues). `outside_garch_arch.py` runs under WSL with `uv run --no-project --with arch==7.2.0 --with pandas==2.2.3 --with "numpy<2.3" --with scipy`, writes `oracle/outside_arch_f.json`, and `outside_f.py` judges it. `arch` is not added to the oracle's locked environment.
- The two candidates marked above (cross gamma and the three curve inspect cases) would add 9 cases, giving 221 of 403 = 54.8%. Even with every candidate, the 60% floor is out of reach while error cases stay in the denominator.
