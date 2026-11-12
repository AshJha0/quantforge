# R6 Python lane hand-over

Branch `r6-lang-python` (worktree `qf-wt/python`), from `e387d29`, with `r6-evidence` (`aa33e85`) merged. Not pushed.

## Findings reproduced first

| Finding | Result | Evidence |
|---|---|---|
| 3, Jacobian upper-triangle mask (`risk_curve.py:197`) | **reproduced**: against an independent central difference, MONOTONE_CONVEX and MONOTONIC_LOG_CUBIC fail at entry (0, 1); LOG_LINEAR_DF and LINEAR_ZERO pass | `python/tests/test_r6_jacobian.py` |
| 15, finite input that overflows | **not reproduced as a crash** in Python: in-process fuzz, every numeric input of one golden per operation (274 operations, 11,646 runs) set to 1e308, -1e308 and 1e-308; no exception escaped `run_case` and every result serialised. Overflow results come back `E_NON_FINITE` (1,834 runs) per `cli-contract.md`, not `E_DOMAIN` (see question 1) | scratch script, not committed |
| 18, MBS PSA above about 1667% (`mbs.py:25`) | **reproduced**: `mbs.cashflows` with PSA 5000 made complex numbers and the CLI crashed in `json.dumps` (TypeError, exit 70) | `test_mbs_psa_above_cpr_one_is_domain_error` |

## Items done

- Finding 3 / R6 Jacobian: mask removed; for local interpolations the upper triangle is still exactly zero. Conformance unchanged.
- Finding 18 / R6-8: a monthly CPR above 1 is `E_DOMAIN` on `pool`. The CLI result check also treats a complex value as non-finite, so no operation can crash that way.
- R6-16 G4: `cli/ops_stage_g2.py` renamed `cli/ops_lmm_xva_frtb.py` (public operation names unchanged; `stages.json` never named it). Test files named `test_stage_*.py` are kept: they are named in `pyproject.toml`, `python_sampled_mutants.py` and the stage E quality register (see question 3).
- R6-16 G-9: the existing assertion (ratio at most 5) now also appends the measured ratio to `$QF_G9_OUT` when set, for the Actions runner to keep. Local value not recorded as evidence (laptop timing).
- R6-25: stale "(open)" headings in `python/SPEC_QUESTIONS.md` now name their rulings; questions with no ruling listed in an "R6 status" section.
- R6-26: per-file line coverage before: every `quantforge_core` file at or above 90% except `__init__.py` (60%, 5 statements: the installed-version branch). Added `tests/test_r6_version.py` (both branches, expected value read from `pyproject.toml`): `__init__.py` 100% after. Whole package 98% (13,494 statements, 295 missed), floor 0.96. No allow-list candidate.

## Results

- Conformance before the merge: 14,935 of 14,935 (the `edge_d` suite rerun alone after a rename race). After the merge: see the final line below.
- Unit tests: 1,918 passed, 2 skipped (env-gated), 28 min under coverage; plus 7 new R6 tests pass. ruff clean; mypy clean (156 files).

## Questions for the spec lane

1. R6-8 says `E_DOMAIN` when a finite input overflows, but `cli-contract.md` maps a non-finite result to `E_NON_FINITE`, and Python returns that at the output check. Which code is the ruling? If `E_DOMAIN`, the contract and every golden expecting `E_NON_FINITE` change with it.
2. `risk.curve.jacobian` (and the other `risk.curve.*` operations) accept all of `curves.INTERPOLATIONS`, but have no `tension` or `step_end` input, so TENSION_SPLINE and HYBRID always give `E_INPUT`. Add the inputs, or narrow the enum?
3. G4: do `tests/test_stage_*.py` file names count as stage-letter module names for the R6-16 `git grep`? Renaming them touches the mutation config and the stage E quality register.
4. Still unruled from earlier stages: E-Q7, E-Q11, F-Q1, F-Q4, G-Q2 (`python/SPEC_QUESTIONS.md`).

## Waves

No `WAVE n READY` in `r6:program/R6_HANDOVER.md` at hand-over (the file does not exist yet on `r6`).
