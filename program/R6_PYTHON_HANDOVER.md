# R6 Python lane hand-over

Branch `r6-lang-python` (worktree `qf-wt/python`), from `e387d29`, with `r6-evidence` (`aa33e85`) and `r6` (`d51d30a`, waves 1A, 1B, 2, 3) merged. Not pushed.

## Findings reproduced first

| Finding | Result | Evidence |
|---|---|---|
| 3, Jacobian upper-triangle mask (`risk_curve.py:197`) | **reproduced**: against an independent central difference, MONOTONE_CONVEX and MONOTONIC_LOG_CUBIC failed at entry (0, 1); TENSION_SPLINE and HYBRID could not run at all (no `tension`/`step_end` input) | `python/tests/test_r6_jacobian.py` |
| 15, finite input that overflows | **not reproduced as a crash** in Python: in-process fuzz, every numeric input of one golden per operation (274 operations, 11,646 runs) set to 1e308, -1e308, 1e-308; no exception escaped `run_case`. Overflow gives `E_NON_FINITE`, which ruling R6-8.1 confirms | scratch script, not committed |
| 18, MBS PSA above about 1667% (`mbs.py:25`) | **reproduced**: complex numbers, CLI crash in `json.dumps` (exit 70) | `test_mbs_psa_above_cpr_one_is_domain_error` |
| 21, mixed units read as singular | **reproduced** by `r6/hedgescale_r6` (3 value cases were `E_SINGULAR`) | goldens |

## Items done

- Wave 1: contract 1.12.0 (R6-0.1); Jacobian without mask and with `tension`/`step_end` (R6-1.1, R6-1.2); ES with fractional tail weight (R6-3.1); `risk.frtb.sbm_total` (R6-4.1); complex results treated as non-finite (no crash path left).
- Wave 2: BGK envelope (R6-2.1); `deflated_pfe_*` keys (R6-5.1, R6-5.6); critical points from `g'` on 6,001 points over +-12 sd, bisection, cached per profile (R6-5.5); MBS PSA with any `CPR_k >= 1` is `E_DOMAIN` before any cash flow (R6-7.1); CDS trade date on an IMM date priced (R6-7.3); TIPS truncate-then-round (R6-7.5).
- Wave 3: Jacobi-scaled singularity tests in `hedge.qp.solve` (`ERROR` mode, solved in scaled variables) and scaled Cholesky in `hedge.minvar.ratio` (negative pivot `E_NOT_POSITIVE_DEFINITE`, pivot <= 1e-12 `E_SINGULAR`) (R6-6.2, R6-11.7); caps `10 n + 100` and 1,000,000 points (R6-6.1, property tests with a cap of 1); `max_instruments` out of range is `E_INPUT` before the subset `E_LIMIT` (R6-11.6); empty `eq_matrix` `E_INPUT` (R6-11.13); `usecase.option_hedge_lots` (R6-11.20). R6-11.12 and R6-11.18 already held.
- R6-16 G4: `cli/ops_stage_g2.py` renamed `cli/ops_lmm_xva_frtb.py` (operation names unchanged; `stages.json` never named it). G-9: the existing `<= 5` assertion also appends the measured ratio to `$QF_G9_OUT` when set.
- R6-25: `python/SPEC_QUESTIONS.md` headings name their rulings; unruled items listed under "R6 status".
- R6-26: see coverage below; `tests/test_r6_version.py` covers both branches of `__init__.py` (60% to 100%), with the expected value read from `pyproject.toml`.

## Timing (local laptop, not evidence)

`r6/hedgeqp_large_r6`: 5 of 5 pass in 412.6 s for the suite (n = 50 three cases, n = 200 two), well above T6's 20 s per case for Python. `stage_g/expsim_g` takes 300 s with the 6,001-point scan (passes).

## Results

See the "Final run" section at the end.

## Questions for the spec lane

1. R6-6.2 for `MIN_NORM`: Python applies scaling only to the `ERROR` decision; in `MIN_NORM` the rank and the minimum-norm answer stay unscaled (minimum norm in scaled variables is a different answer). Confirm.
2. R6-6.1 kink tolerance: Python's sign-state search still tests `x_j != 0` exactly at the kink; no golden distinguishes it. Wave 3 goldens pass.
3. R6-11.9, R6-11.16 (negative bumped hazard, spread-vol floor) have no goldens; not built here.
4. G4: do `tests/test_stage_*.py` file names count for the R6-16 `git grep`? Renaming touches mutation configs and the stage E quality register.
5. Unruled from earlier stages: E-Q7, E-Q11, F-Q1, F-Q4, G-Q2.
6. Large-hedge speed: T6 is missed by about 8x in Python.

## Session 2026-11-12 evening: five pytest failures fixed, r6 wave 4 merged

| Test | Verdict | Change |
|---|---|---|
| `test_stage_g2.py::test_portfolio_single_swap_reproduces_wave_4a_and_pfe_order`, `::test_portfolio_offsetting_swaps_have_no_exposure` | stale test (R6-5.1 renamed `pfe_*` to `deflated_pfe_*`) | keys updated, assertions unchanged |
| `test_stage_d2.py::test_cds_dates` | stale test (R6-7.3: trade date on an IMM date is priced, not `E_INPUT`) | now asserts periods are returned |
| `test_hedge_solvers.py::test_property_qp_kkt_bounds_and_equalities` | **code bugs** (three) plus test-helper gaps | (a) `_Qp.multipliers`: with every position on a bound and an equality, lambda was never fitted, so a degenerate state cycled to `E_NO_CONVERGENCE`; lambda is now chosen from the admissible interval (one row) or least squares (more rows). (b) Multiplier signs judged against `max(1, max|g|)` (R6-11.4); a gradient near 1e-140 made a 1e-141 rounding sign drop a bound forever. (c) `ERROR` scaled solve: column norms 1e63 apart lost the scaled null space and `x = D x~` missed the equality by 1.2; if the unscaled equality residual exceeds 1e-9 relative, the unique minimiser is re-solved in caller units. Helper `kkt_residual` gets the same all-at-bound lambda rule; the sum check is relative to `max|x|` (rounding), not absolute 1e-12. 3,000 extra Hypothesis examples clean |
| `test_hedge_solvers.py::test_property_min_norm_equals_the_unique_solution` | stale test (R6-6.2 / R6-6.2a: `ERROR` decides on scaled columns, `MIN_NORM` ranks unscaled; a 1e-50 column differs) | `assume(cond(A) < 1e5)` with that reason |

Merged `r6` at `c7c6bd7` (wave 4). Final run on the merge: conformance **15,077 / 15,077**; pytest **1946 passed, 2 skipped, 0 failed** (775.9 s); coverage TOTAL **98%**.

Files below 90% line coverage: **none** (lowest: `book_risk.py` 91%, `roots.py` 92%, `fitting.py`, `calibration.py`, `cli/ops_book.py`, `risk_tools.py` 93%). No tests needed for the 90% bar.

Timing (local laptop, not evidence): `r6/hedgeqp_large_r6` 5/5 in **122.9 s** for the suite (n = 50 three cases, n = 200 two), about 25 s per case, still above T6's 20 s; `stage_g/expsim_g` 102/102 in 184.3 s.
