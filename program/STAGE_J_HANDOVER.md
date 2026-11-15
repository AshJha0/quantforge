# Stage J handover

From the stage J spec and oracle session to the four language sessions and the lanes. Append-only. Each wave section says what a language session may read. Never read anything under `oracle/`: that is the oracle, and reading it breaks the clean room.

Stage J (v0.9): research and backtesting (plan section 4, row J; 11.3; 12.5 Q7, A1, A4; 14.6 J-1 to J-11). All stage J goldens are in `datasets/golden/stage_j/`, run through `conformance/runner/runner.py` (it finds them by suite name). Always read `specifications/cli-contract.md` (block "Stage J operations", contract 1.13.0) and `specifications/stage-j-rulings-w1.md` with any stage J slice; the J-0b fuzz rulings are in `specifications/stage-j-rulings.md` on branch `stage-j-fuzz`. Stage F rules F-1 to F-3, F-5, F-6 and R6-8.1 apply to every new operation.

## Wave plan

| Wave | Content | Main outside check |
|---|---|---|
| 1 | Backtester (event and vectorised), purged k-fold and CPCV counts, Viterbi regime labels, PSR, DSR, PBO by CSCV, power | Hand and textbook examples (J-19) |
| 2 | Drift (A3), Baum-Welch and Markov-switching AR (A4), Reality Check or SPA (J-4), mean-variance and risk parity (J-5), shrinkage and Black-Litterman (J-6) | scipy QP, scikit-learn Ledoit-Wolf (oracle only) |
| 3 | 14.5 items (shock library, ES backtest, Euler contributions, held-out-strike backtest) | Treasury par-yield history, named dates only |

## WAVE 1 READY (2026-11-13): backtester, CV, regimes, research statistics

Read with every slice: the four spec pages below; `specifications/stage-j-rulings-w1.md` J-1 to J-19; `specifications/cli-contract.md` (block "Stage J operations"); `specifications/name-map.json` (regenerated: 284 operations).

### Suites (99 cases)

| Suite | Spec | Operations | Cases (value, error) |
|---|---|---|---|
| `backtest_j` | `11-research/backtester.md` | `research.backtest.run` | 23 (14, 9) |
| `purgedcv_j` | `11-research/purged-cv.md` | `research.cv.purged_kfold`, `research.cv.cpcv_paths` | 23 (15, 8) |
| `regime_j` | `11-research/regimes.md` | `research.regime.viterbi` | 16 (10, 6) |
| `rstats_j` | `11-research/research-statistics.md` | `research.stats.dsr`, `.psr`, `.power`, `.pbo` | 37 (24, 13) |

Expected totals after wave 1 on top of main `3cca7da` (before the J-0b fuzz goldens): `TOTALS: 15176 value 7504 error 5158 invariance 2514`. `tools/check_case_total.py` reads the last `TOTALS:` line of `program/R6_HANDOVER.md`; this branch does not edit that file because branch `stage-j-fuzz` appends to it. **Coordinator, at merge:** append one combined line (this wave's +99 / +63 / +36 / +0 on top of whatever `stage-j-fuzz` states) to `program/R6_HANDOVER.md`, then run the gate.

Gates run on this branch: `oracle/python/check_error_cases.py` (0 schema mismatches), `tools/gen_name_map.py --check` (clean), `tools/check_golden_copies.py` (0 stale), `tools/check_tolerance_units.py` (0 unexplained); `tools/check_case_total.py` counts 15176 / 7504 / 5158 / 2514 with 0 duplicate ids (fails only on the missing handover line above).

### Build notes

- Backtester: build the `EVENT` loop from the definition; `VECTOR` is shift, diff, multiply, cumsum. Both must give every golden. Holding P&L uses the position **before** the bar's trade (J-2). `trade_count` is an Integer; `max_drawdown` starts the peak at 0 (J-6). Default costs are 0, `lag` 1, `multiplier` 1, `engine` `EVENT`.
- Purged CV: fold sizes in `array_split` order; closed-interval overlap; embargo `floor(pct * n)` indices after the block only (J-8). Indices are 0-based and ascending. `purgedcv_j-0001` is worked in the spec.
- Viterbi: work in logs; `log 0 = -inf` must be handled (the alternation case has zero transitions). Ties: smallest index (J-11). An all-`-inf` end is `E_DOMAIN`.
- DSR: `N = 1` gives `SR0 = 0` (J-13). Normal quantile to full double precision; the goldens use class `per_unit`. Euler-Mascheroni `0.5772156649015329`.
- PBO: combinations in lexicographic order of the train block set; logits in that order; average OOS rank, 1 = worst (J-16). Sample std divisor `n - 1`.
- Check order everywhere: `E_PARSE`, `E_SCHEMA` (unknown enum), `E_LIMIT`, F-2, then each page's list.

### Property tests (each language, own data)

- `EVENT` equals `VECTOR` to 1e-10; attribution identity; zero costs give net = gross; look-ahead canary detected at `lag = 0` and absent at `lag = 1` (Q7).
- No train label overlaps a test span; `t1 = t0` with no embargo equals plain k-fold.
- Viterbi path equals brute force on random `K <= 3`, `T <= 6` models.
- `dsr` is decreasing in `n_trials` and `sr_variance`; `psr` with `sr_benchmark = sr` is 0.5.
- PBO lies in `[0, 1]`; with one strategy dominating every row it is 0.

### Outside-check status (J-19)

Hand or textbook value cases: `backtest_j-0001`, `-0002` (ten-trade hand table), `purgedcv_j-0001` (hand), `purgedcv_j` CPCV `N = 6, k = 2` (15 splits, 5 paths), `regime_j-0001` (textbook example, 0.01512), `rstats_j-0001`, `-0036`, `-0037` (DSR numerical example, paper read: printed 0.1132, 0.9004, 0.9505, 0.9505), `rstats_j-0017` to `-0020` (prereg MDS table), `rstats_j-0025` (PBO hand). Brute-force (independent method) on four further Viterbi cases. Outside **library** oracle added 2026-11-14 (`oracle/python/outside_j.py`, per case in `oracle/OUTSIDE_J.json`): 41 of the 63 value-checked cases (65.1 %; 41 of 99 = 41.4 % with error cases): `regime_j` 10/10 hmmlearn 0.3.3, `purgedcv_j` 12/15 timeseriescv 0.2 + scikit-learn 1.9.1 + skfolio 1.12.12, `rstats_j` 5/24 statsmodels 0.15.0 (power only; DSR, PSR, PBO have no free library), `backtest_j` 14/14 vectorbt 1.2.1. 14 library-object, 27 library-primitive. No golden disagreement; a timeseriescv end-of-data purge defect and the J-19 amendment text are in `program/WAVE1_ORACLE_NOTES.md`. Stage J is not yet wired into `tools/outside_shares.py`. J-1 source check closed 2026-11-13: both papers read; DSR digits match; [BBLdPZ17] prints no fully specified example, so PBO keeps the hand golden `rstats_j-0025`.

### Model inventory

Rows to add at the stage J docs pass: MI-J1 backtester, MI-J2 purged CV, MI-J3 Viterbi labels, MI-J4 DSR/PBO/power, with golden hashes.

### Not in wave 1

Walk-forward and the trial registry stay in the Python research package (`quantforge_research`), not CLI operations. A6 feature store and A8 template section belong to the research lane.

## WAVE 3 SPEC + PYTHON READY (2026-11-15): scenario stress (G18), interpolation backtests, drift detectors (A3)

Owner decision 2026-11-15: Option C, all in v0.9.0. Branch `j2-wave3` (from main a148d0e), not pushed. Read: `specifications/stage-j-rulings-w3.md` J-W3-1 to J-W3-16; spec pages `06-risk/scenario-stress.md`, `11-research/interp-backtest.md`, `11-research/drift-detectors.md`; `specifications/cli-contract.md` (wave 3 rows); `specifications/name-map.json` (regenerated: 299 operations).

### Suites (83 cases, generator `oracle/python/gen_stage_j_w3.py`)

| Suite | Operations | Cases (value, error) |
|---|---|---|
| `scen_j` | `risk.scenario.historical_shock`, `risk.scenario.replay` | 23 (13, 10) |
| `interpbt_j` | `research.backtest.interp_loo`, `research.backtest.surface_holdout` | 25 (16, 9) |
| `drift_j` | `research.drift.cusum`, `.page_hinkley`, `.psi`, `.ks` | 35 (26, 9) |

`program/R6_HANDOVER.md` ends `TOTALS: 15398 value 7626 error 5258 invariance 2514`. Python passes 83/83 through the runner. Contract: target 1.15.0 (J-W3-1); **not bumped yet** (runner, stub and four CLIs still 1.14.0) so Rust, Java and C++ conformance stays green on this branch; bump in one commit when the three language lanes land.

### Build notes (for the Rust, Java and C++ lanes)

- Scenarios: `shift_bp = 100 (end - start)` in binary64; a missing date is `E_DOMAIN`, order errors `E_DATE_ORDER`. Replay interpolates linearly in tenor, flat outside; `pnl` only when `dv01` is given.
- LOO: rebuild the interpolant without knot `i` using the `core.interp.evaluate` code path; end knots are never left out. Surface: interpolate `w = sigma^2 T` in `k`, back to vol.
- CUSUM: strict `> h`, restart both sums after an alarm. Page-Hinkley: running mean at each step (J-W3-11 as corrected), restart counters after an alarm. PSI: edges `r[ceil(j n / B) - 1]` (0-based), bins right-closed, floor 1e-4 without renormalising. KS: `D n m` as an integer, exact lattice count in big integers (or 128-bit plus a checked fallback); p-value is one final division.

### Outside-check status (R6-13 floor NOT met)

Library-checked value cases: `interpbt_j` 13 of 16 (scipy `CubicSpline` natural, `PchipInterpolator`, numpy `interp`; log-linear by mpmath and the hand case do not count), `drift_j` 6 of 26 (scipy `ks_2samp(method="exact")`, max gap 1.1e-16; CUSUM, Page-Hinkley, PSI are Fraction re-implementations, no free library with these conventions), `scen_j` 0 of 13 (exact Fraction arithmetic; the four real-data rows are checked against Fed H.15, an outside check of the data, not of a library). Wave 3: **19 of 55 value cases = 35 %**, below the 60 % floor. Options for the coordinator: river `PageHinkley`/`ADWIN` or `ruptures` for drift if conventions can be matched, independent re-derivation class where no library exists; or report the shortfall to the owner.

### Research results

- Interpolation backtests (pass rules committed in c41f629 before any run): **B1 FAIL** (cubic natural, leave-one-strike-out 0.370 vol pts > 0.25 at the ATM strike, T = 0.25; design b 0.355 <= 0.50); **B2 PASS** (pchip on Treasury par, pooled 3M-10Y median 2.62 bp <= 3, 95th 14.19 bp <= 15). `research/interp_backtest/RESULTS.md`.
- A3: prereg `research/preregs/A3-drift.md` is an **unsigned draft**; runner `research/a3/a3_drift_study.py` refuses until signed. The prereg predicts Page-Hinkley fails the delay rule with the plan's `lambda = 50` (about 100 steps): an owner decision before signing.
- J-8 scenario acceptance: H.15 match on all 88 start/end values (worst gap 0.0000 pp); goldens recompute the shifts and the replay.

### Wave 3 language lanes (2026-11-15, same branch)

- Ports: Rust `quantforge-core/src/research_w3.rs` + `quantforge-cli/src/ops/w3.rs`; Java `research/StressDrift.java` + `cli/OpsResearchW3.java`; C++ `src/core/research_w3.cpp` + `src/cli/ops_research_w3.inc` (+ `tests/test_research_w3.cpp`). Each carries its own Shewchuk `fsum` to match Python's `math.fsum`; KS counts in 128 bits (Rust, C++; probability-walk fallback, unit-tested against the count) or BigInteger (Java). Limits J-W3-14 in each CLI.
- Conformance: 83/83 wave 3 in each language; contract **1.15.0** (J-W3-1) in runner, stub and the four CLIs; full runs Rust 15,398/15,398 and C++ 15,398/15,398 (WSL), Java 15,398/15,398 (Windows). Rust and C++ binaries are blocked by Windows Application Control on this machine, so they were built and run in WSL from a file copy of the worktree.
- Outside share (R6-13): wave 3 now 42 of 55 value cases (76 %) in `oracle/OUTSIDE_J.json`; 5 of these (historical shock: pandas lookup plus arithmetic) are weak, 37 of 55 (67 %) without them. CUSUM and Page-Hinkley: no library with the conventions (river's PageHinkley differs), not counted; independent re-derivation is not counted for them because REDERIVE_OPS (owner decision 2026-11-12) does not list them.
- A3: DR-A3-1 sets Page-Hinkley `lambda = 5` (was 50) from the Siegmund calibration; prereg still unsigned.
- Docs: tutorial 33 (renumbered from 27; docs lane owns 27-32), LEARN and COOKBOOK wave 3 sections, glossary rows, model inventory MJ-9 to MJ-11.

### Not done in this lane

Different-model audit; Rust/C++ property tests beyond the unit tests added; CI on the pushed branch.

## WAVE 2 READY (2026-11-14): optimisation, estimation, ES backtest, Baum-Welch

Read with every slice: the spec pages below; `specifications/stage-j-rulings-w2.md` J-W2-1 to J-W2-15; `specifications/cli-contract.md` (block "Stage J operations", wave 2 rows); `specifications/name-map.json` (regenerated: 291 operations). Gap analysis and what stays out of wave 2: `program/STAGE_J_GAP.md`.

### Suites (96 cases)

| Suite | Spec | Operations | Cases (value, error) |
|---|---|---|---|
| `optim_j` | `07-portfolio/optimisation.md` | `research.portfolio.mean_variance`, `research.portfolio.risk_parity`, `risk.contrib.euler` | 49 (35, 14) |
| `estim_j` | `07-portfolio/estimation.md` | `research.estimate.ledoit_wolf`, `research.estimate.black_litterman` | 21 (15, 6) |
| `esbt_j` | `06-risk/es-backtest.md` | `risk.backtest.es_z2` | 12 (7, 5) |
| `baumwelch_j` | `11-research/baum-welch.md` | `research.regime.baum_welch` | 14 (6, 8) |

`program/R6_HANDOVER.md` now ends `TOTALS: 15315 value 7571 error 5230 invariance 2514` (wave 1 plus these 96 and four interior-shrinkage Ledoit-Wolf goldens, J-W2-23). Gates run on this branch: `tools/check_case_total.py` (matches, 0 duplicate ids), `tools/gen_name_map.py --check` (clean), `tools/check_golden_copies.py` (0 stale), `tools/check_tolerance_units.py` (0 unexplained), `oracle/python/check_error_cases.py stage_j` (0 mismatches), `tools/governance_gate.py` (clean; the two numerical pages carry Convergence sections). Contract: all four builds and the runner now use 1.14.0 (J-W2-1).

### Build notes

- Mean-variance: any exact QP method; a primal active set from a feasible start is the suggested one. Set bound weights to the bound exactly (`at_bound` is compared exactly). Check order: shapes, then `gamma`, bounds, feasibility, symmetry, Cholesky.
- Risk parity: Newton on `Sigma y = b / y`, step halving to keep `y > 0`, normalise `w = y / sum y`. Budgets are used as `b / sum b`.
- Euler: covariance need not be definite; only `w' Sigma w <= 0` fails.
- Ledoit-Wolf: divisor `T`, demeaned columns, `delta = 0` when `b^2 = 0`. Use the direct sum for `bbar^2`.
- Black-Litterman: Cholesky solve with `P tau Sigma P' + Omega`; never invert `Sigma`.
- Z2: losses positive, exception strict (`L > VaR`), `exceptions` an Integer.
- Baum-Welch: follow the page's iteration order exactly (E-step at start; then M-step, E-step, gain test). Output the parameters of the **last E-step**, not one more M-step. Sum over ascending indices. Each golden's `tolerance` is an input chosen with a `1e-11` margin (J-W2-12), so no build-specific stop handling is needed. Parameters compare at `1e-12` absolute plus `1e-9` relative.

### Property tests (each language, own data)

- Mean-variance KKT residual below `1e-9`; wide bounds equal the closed form; loosening a binding bound never lowers the objective.
- Risk-parity shares equal `b / sum b` to `1e-10` (J-5); Euler contributions sum to volatility to `1e-10` (J-8).
- Ledoit-Wolf `0 <= delta <= 1`; Black-Litterman update form equals precision form to `1e-10` (J-6); large `Omega` returns the prior.
- Z2 = 1 with no exceptions; scale invariance.
- Baum-Welch: log-likelihood non-decreasing (to `1e-9` relative); `K = 1` stops at iteration 2 with sample mean and population sd; two runs give identical bytes (12.10 A4); state permutation equivariance.

### Outside-check status

Hand cases: `optim_j-0001` (w1 = 17/26), `optim_j-0029` (risk parity 0.6 / 0.4), `optim_j-0041` (Euler), `estim_j-0001` (Ledoit-Wolf), `estim_j-0012` (Black-Litterman 0.075), `esbt_j-0001` (Z2 = -1.8), `baumwelch_j-0001` (one state). Independent methods: exact KKT certificate for all 21 mean-variance cases, plus bound-pattern enumeration for `N <= 4`; two algebraic forms for every Ledoit-Wolf and Black-Litterman case; log-space forward pass for every Baum-Welch log-likelihood. scipy SLSQP agrees with the exact mean-variance weights within 1.82e-8 (the generator prints the figure); this falls just short of the J-5 target of 1e-8 because SLSQP's precision is limited, not because the goldens are wrong (they are exact KKT points). **Open for the oracle lane** (J-W2-15): an outside QP at tight tolerance (cvxopt or OSQP) on the 20 J-5 problems, scikit-learn `ledoit_wolf` on `estim_j` (J-6, oracle only), hmmlearn on `baumwelch_j`. None of these libraries is in the oracle environment as of 2026-11-14.

### Done here in the research package (no other language)

`python/quantforge_research/`: `cv.walk_forward` (A1), `trials.trial_count` and `trials.register` (Q7, J-13), `snooping.reality_check` (J-4, stationary bootstrap). Tests in `python/tests/test_quantforge_research.py` (8 tests; the size test runs 200 simulated null sets and takes about 80 s). `pyproject.toml` now packages `quantforge_research*`.

### Not in wave 2

A3 drift detectors (the prereg `research/prereg/A3-drift.md` must be frozen before any code, 12.10), Markov-switching AR(1), the A4 T = 5,000 recovery run, the ES size study, the Ken French study, section 12 methods, the feature store, the A8 gate and wave 3 (shock library, held-out-strike backtest): research and docs lanes, listed with reasons in `program/STAGE_J_GAP.md`.
