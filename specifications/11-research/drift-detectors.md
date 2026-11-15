# Drift detectors: CUSUM, Page-Hinkley, PSI, two-sample KS (A3)

Spec version 1.0.0. Status: specified (stage J, wave 3); Python reference first. Target CLI contract 1.15.0 (J-W3-1). Rulings: `stage-j-rulings-w3.md` J-W3-10 to J-W3-15. Suite: `datasets/golden/stage_j/drift_j`, written by `oracle/python/gen_stage_j_w3.py`. Plan 12.10 A3; study prereg `research/preregs/A3-drift.md` (unsigned draft at this commit).

**Plain idea.** A model is fitted on data that looked one way. Drift detectors watch new data and raise a flag when it stops looking that way: CUSUM and Page-Hinkley watch the mean step by step; PSI and the KS test compare a recent window with a reference window.

Sources: [PAGE54] E. S. Page, "Continuous inspection schemes", *Biometrika* 41, 1954. [SIEG85] D. Siegmund, *Sequential Analysis*, Springer 1985 (ARL approximation). [GAMA14] J. Gama et al., "A survey on concept drift adaptation", *ACM Computing Surveys* 46(4), 2014 (Page-Hinkley running-mean form). [MASSEY51] F. J. Massey, "The Kolmogorov-Smirnov test for goodness of fit", *JASA* 46, 1951. PSI: industry convention (credit scoring), no single primary source; the conventions are fixed by J-W3-12. All recalled, not opened in this session.

## `research.drift.cusum`

Inputs `x`, `k > 0`, `h > 0`, optional `mu0` (0), `sigma > 0` (1), `reset` (true). Outputs `alarms` (0-based indices), `directions` (`+1`/`-1` per alarm), `s_plus`, `s_minus` (final values). J-W3-10. Hand case: `x = (0, 3, 3)`, `k = 0.5`, `h = 4`: `S+ = 0, 2.5, 5`, alarm at 2, direction `+1`.

## `research.drift.page_hinkley`

Inputs `x`, `delta >= 0`, `lambda > 0`, optional `direction` (`both`), `reset` (true). Outputs `alarms`, `directions`. J-W3-11.

## `research.drift.psi`

Inputs `reference`, `test` (each at least `bins` values), optional `bins` (10, at least 2), `threshold` (0.25). Outputs `psi`, `reference_shares`, `test_shares` (after the floor), `alarm`. J-W3-12.

## `research.drift.ks`

Inputs `a`, `b` (non-empty), optional `level` (0.05, in `(0, 1)`). Outputs `statistic`, `p_value`, `reject`. J-W3-13. With ties the p-value is the continuous-null value and is conservative for the size of the test only approximately; goldens with ties say so.

Errors for all four: empty or too short inputs, `bins < 2`: `E_INPUT`; parameters out of range: `E_DOMAIN`; sizes over J-W3-14: `E_LIMIT`.

## Property tests

- CUSUM and Page-Hinkley give no alarm on a constant series at `mu0` (CUSUM) or any constant series (Page-Hinkley with `delta > 0`); PSI of a sample against itself is 0; KS of a sample against itself has statistic 0 and p-value 1; KS is symmetric in `a` and `b`.

## Limitations

Univariate; i.i.d. reference assumed for the stated ARL and size figures. The study that measures size, ARL and delay is `research/preregs/A3-drift.md`; operating characteristics are not outputs.
