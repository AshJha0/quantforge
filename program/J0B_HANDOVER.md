# Stage J lane J-0b hand-over (2026-11-13)

Branch `stage-j-fuzz` (worktree `C:/Work/Claude/qf-wt/j0b`), from `main` 3cca7da. Not pushed. Fuzz findings from `main` run 43390662426, seed 3.

| Fix | Ruling | Java | Python | Rust | C++ |
|---|---|---|---|---|---|
| `vol.garch.forecast` horizon 2^31 timeout | J-0b.1: horizon > 100,000 is `E_LIMIT` | already had it | added (`cli/limits.py`) | added (`cli/src/limits.rs`) | added (`cli/ops_vol.inc`) |
| `vol.garch.estimate` timeout on fuzzed `garch_f-0010` (return -2.68e297, its square overflows) | J-0b.2: `E_NON_FINITE` before any search (R6-8.1) | was `E_DOMAIN`, fixed (`GarchMle.java`) | was a 20 s all-inf search, fixed (`variance.py`) | already `E_NON_FINITE` | was `E_NO_CONVERGENCE`, fixed (`vol_stats.cpp`) |
| `exotic.basket.moment` ragged correlation crash (exit 70) | J-0b.3: every row length checked first, `E_INPUT` | fixed (`OpsExotics.java`) | already `E_INPUT` | already `E_INPUT` | already `E_INPUT` |

Rulings are in `specifications/stage-j-rulings.md` (new file); the limit row is in `specifications/01-core/limits.md`; the CHANGELOG entry is under "Unreleased (0.9.0)". The new golden suite is `datasets/golden/stage_j/fuzzfix_j.json` (6 error cases), written by `oracle/python/gen_stage_j_fuzz.py`.

## Results

- Conformance: each of the four languages passes all of fuzzfix_j 6/6, garch_e 29/29, garch_f 17/17, exotic_e 128/128, rulings_e_a 17/17 and e1_exotic 411/411. Rust and C++ ran in WSL from a `git archive` of 62577ce.
- Unit tests: Java `mvn -o test` green. Python `pytest -k "garch or limit or basket"` 70 passed. Rust `cargo test --release` all ok. C++ built with `-DQF_WERROR=ON`, and ctest passed.
- Fuzz with seed 3 for 60 s: Java (9,800 cases) and Python (3,600) gave 0 findings. Rust and C++ were not fuzzed locally.

## Left

- No unit tests were added. The goldens are the regression check.
- Not checked: the full Python suite, the docs gates (`check_case_total` or the case counts in README and site) and `check_error_cases.py` on stage_j.
- Other Java `anyMatrix` users may read ragged rows the same way. Not audited.
