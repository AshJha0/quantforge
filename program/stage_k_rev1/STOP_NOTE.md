# Lane k-v1-rev1: stop note (2026-11-20)

Branch `k-v1-rev1` off `k-v1` at 5f2a8dc8. K-9 different-model review findings 1, 7, 8, 12, 19, 21, 22
(`institutional-quant-engine-plan/STAGE_K_K9_REVIEW_PART1.md`). Rulings KR-340 to KR-343, all PROPOSED, in
`specifications/stage-k-rulings-rev1.md`. Evidence classes: *measured* unless stated.

## Per finding

| # | State | Evidence | Next step |
|---|---|---|---|
| 1 fuzz | done on the branch; workflow still red on `main` | The four red runs (2026-11-09, 11-13 twice, 11-16) had nine findings. All were fixed by code that landed after those runs (v0.8.2, v0.8.3, J-W3-18 to J-W3-21 on 2026-11-17). Probe of the nine inputs on this branch: Python, Java, C++ (ASan and UBSan build) and Rust give the same error codes; the mean-variance input gives the same weights to the last digits. Two inputs had no golden of the exact input: now `fuzzfix_k` (2). Local fuzz, seed 5: Java 150 s, 20,200 inputs, 0 findings; C++ and Rust see the WSL section below. Guard `tools/check_scheduled_runs.py` (KR-342) with self-test | after merge: run the fuzz workflow on `main` by hand and close K9-1 on green; wire the guard (KR-342) once rows exist for `daily-workflows.yml` and `mutation-stage.yml`, which are also red on `main` and unregistered |
| 7 SABR chi | done, four builds | Reproduced: relative error of `m = z/chi` 2.7e-9 at `z = 1.01e-7`, `rho = 0.3` (reviewer: 3.5e-9), and up to 1e-4 at `z = -3.7e6` (cancellation for large negative `z`). New form 3 ulp or less on about 18,000 points. Goldens `sabrz_c` (32, relative limit 1e-12, mpmath plus a scipy quad check of the integral form); 22 fail the old Python build | none |
| 8 implied vol | done, four builds | Reproduced in Python and Java: a 1e-12 absolute price check accepted 0.1234 (Python) and 0.1196 (Java) for a true 0.1 at price 1.48e-265. Cause: Newton on `V - price` stalls far out of the money and the final check is met by any vol. Fix (KR-341): Newton on `ln V - ln price`, acceptance on an estimated vol error, `E_NO_CONVERGENCE` when the price does not identify the vol. Goldens `ivdeep_c` (12; scipy log-space brentq check). Other solvers with the same shape, not changed: `credit.cdsoption.implied_vol` and `rates.bondfut.implied_vol` (Brent on the price, no final check) | follow-up: check those two on tiny premiums |
| 12 LEARN local vol | done | mpmath at 40 digits: `w_T = 0.033906` against `w/T = 0.063852` (term structure) and the curvature term (+0.21533 in `g`) lower local vol; the skew term (-0.010594) raises it | none |
| 19 FRTB scenarios | done (Python only; the other builds had no such import) | `python/quantforge_core/frtb_scenarios.py`; no behaviour change; mutation seeds of `var_risk.py`, `frtb.py` change | mutation sample not run |
| 21 tests | done | `test_goldens_stage_d.py` defaults to the repository root; `python/tests/conftest.py` fails on a skip not listed in `python/tests/expected_skips.txt` (KR-343) | none |
| 22 CVA note | done in LEARN.md | first-order bias, measured toy example | follow-up: the one-line note beside the formula in `specifications/06-risk/xva-framework.md` (the xVA lanes were editing it) |

## Verification

See the section "Results" below, filled at the stop.
