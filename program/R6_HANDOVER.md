# R6 handover (spec and oracle lane, branch `r6`)

From the R6 spec and oracle lane to the four language lanes, the evidence, docs and research lanes, and the coordinator. Append-only per wave. Rulings: `specifications/r6-rulings.md` (R6-n.x). Language lanes never read `oracle/`; everything needed to build is in this file, the rulings and the specs named per wave.

Contract **1.12.0** from wave 1 (R6-0.1): `conformance/runner/runner.py` and `stub_cli.py` expect it; every CLI must report it. While lanes move, `python tools/r6_judge.py --impl NAME FILES...` judges a build on chosen golden files without the contract stop.

Baseline before R6 goldens: 14,941 cases (7,419 value-checked) after the evidence lane's E9 golden `datasets/golden/core/mc_hash.json` (6 bit-exact cases), merged into `r6` at `5a80d7a`.

**Regeneration order (oracle only).** Any generator that rewrites a golden file drops the R6-10.2 `per_unit` classes; after regenerating, run `python conformance/tolerances/apply_r6_per_unit.py` and `python tools/check_tolerance_units.py` (must print 0 unexplained).

## Wave 1: R6-1, R6-3, R6-4, R6-8, R6-10 (and early rulings for the lanes' open questions)

### Rulings to implement (details in `r6-rulings.md`)

| Ruling | Operation | Exact behaviour change |
|---|---|---|
| R6-0.1 | `version` | `contract_version` `1.12.0` |
| R6-1.1 | `risk.curve.jacobian` | Remove any upper-triangle mask: every entry `(z_i(q + h e_j) - z_i(q - h e_j)) / (2h)` is computed and returned |
| R6-1.2 | `risk.curve.jacobian` | Optional `tension`, `step_end` inputs, required and checked exactly as `rates.ois.bootstrap` (`TENSION_SPLINE` without `tension`: `E_INPUT`; `tension <= 0` or `> 1000`: `E_DOMAIN`; `HYBRID` without `step_end`, or `step_end` not a pillar date: `E_INPUT`); every bumped curve built with them. Check order: after `bump_bp` (`E_DOMAIN`), as part of the bootstrap's own checks |
| R6-3.1 | `risk.var.historical`, `risk.var.filtered_historical`, `risk.var.monte_carlo` | `es`: `w = n - n*c` (binary64 product, then one subtraction), `m = floor(w)`; sort losses descending `L1 >= L2 >= ...`; `es = (L1 + ... + Lm + (w - m) * L(m+1)) / w`; if `w <= 0`, `es = L1`. `tail_count = ceil(w)` (1 if `w <= 0`). VaR unchanged (`k = ceil(n*c)`, `var = L_(k)` ascending) |
| R6-4.1 | `risk.frtb.sbm_total` (new) | Spec `06-risk/frtb-sa-girr.md` last section. Inputs `components` `[{risk_class, measure, scenarios: {high, medium, low}}]`; checks in order: `E_SCHEMA` (unknown `risk_class` not in `GIRR, CSR_NONSEC, EQ, COMM, FX`; `measure` not in `DELTA, VEGA, CURVATURE`; missing scenario key), finite rule F-2 (`E_DOMAIN`), empty list `E_INPUT`, a charge `< 0` `E_DOMAIN`, a duplicate (`risk_class`, `measure`) `E_INPUT`. Outputs `scenario_totals {high, medium, low}` (fsum or plain sum: within `simple_analytic`), `capital` (largest), `binding_scenario` (ties to the first of high, medium, low), `sum_of_component_capitals` |
| R6-8.1 | every operation | A non-finite result or intermediate from finite inputs is `E_NON_FINITE`, never a crash and never `E_DOMAIN`. **Java:** `Bonds.java:262` must return `E_NON_FINITE` (phase 0 returns `E_DOMAIN`). Python, Rust and C++ already return `E_NON_FINITE` on the fuzz input |
| R6-10.1, R6-10.2 | policy | New class `per_unit` (absolute 1e-10, relative 1e-8) in `conformance/tolerances/policy.yaml`; 238 existing cases now name it in `output_classes` for their per-unit outputs. Nothing to build: the v0.8.0 Python, Rust and C++ builds already pass it on every flagged output |

### Early rulings for open language questions (so lanes can start; full text in `r6-rulings.md` waves 2 and 3)

| Question | Ruling |
|---|---|
| Java G-J6 (`portfolio_hw` zeros and level crossings) | R6-5.5: a build must find every zero of `f` and every crossing of `f = y` used by the PFE quantile. Required method (or one proven equivalent): bracket the critical points of `f` from the analytic `f'` on a scan of at least 6,001 points over `x` in `[-12, 12]` standard deviations, refine each by bisection to `1e-14` relative in `x`; `f` is then monotone between consecutive critical points, so each piece has at most one root, found by bisection. Java's method is the reference. A fixed 601-point scan is not enough (it understated `pfe_99`; those goldens were corrected by `fix_w4c_pfe.py` in stage G) |
| Java G-J7 (PFE key naming) | R6-5.1: keys are `deflated_pfe_` followed by `100 q` written with trailing zeros removed (`0.95` gives `deflated_pfe_95`, `0.975` gives `deflated_pfe_97.5`). Goldens use `[0.95, 0.99]` only |
| Java J-I6 (kink tolerance, iteration cap; review finding 7) | R6-6.1: one value for every build. Kink: a position is at its kink when `|x_j| <= 1e-11 * max(1, max_k |x_k|)`; after the sign state is found, the smooth problem on that state is re-solved exactly (I-54). Iteration cap for any active-set or sign-state loop of `hedge.qp.solve`: `10 n + 100` iterations (`n` instruments), then `E_NO_CONVERGENCE`. `hedge.integer.solve`: at most 1,000,000 enumerated lattice points or branch-and-bound nodes, then `E_NO_CONVERGENCE`. Wave 3 adds goldens |

### Golden files (wave 1)

| File | Cases | Value | Error | Notes |
|---|---:|---:|---:|---|
| `r6/jacobian_r6.json` (new) | 12 | 8 | 4 | **pending: generator running; see "WAVE 1B" below** |
| `r6/sbm_total_r6.json` (new) | 12 | 5 | 7 | one case built from `frtb_f-0003` (GIRR, binds high) and `frtb_f2b-0002` (FX, binds low); one NaN case (E1) |
| `r6/nonfinite_r6.json` (new) | 2 | 0 | 2 | coupon `-1e308` and `1e308` in `bond.futures.conversion_factor`: `E_NON_FINITE` |
| `stage_f/risk_f4.json` (changed) | 108 | same | same | 26 cases change `es`, 16 of them also `tail_count` |
| 19 files with `per_unit` (changed; includes 8 cds_imm_r6 cases of wave 2) | 238 cases | | | tolerance only (`output_classes`) |

### Expected conformance totals after wave 1A (everything except `jacobian_r6`)

14,941 + 14 = **14,955**: value-checked 7,419 + 5 = **7,424**; error 5,008 + 9 = **5,017**; invariance (`any` + `same_as`) **2,514** unchanged. With `jacobian_r6` (wave 1B): **14,967**, value 7,432, error 5,021.

### Python oracle agreement

Every wave 1 golden comes from the oracle (`oracle/python/gen_r6_w1.py`; ES from `gen_stage_f_w2.py F4`). Independent checks run before writing: ES against a numpy Acerbi-Tasche written from the paper's form (20 of 20 historical cases within 1e-9); SBM total against a brute-force recomputation; tolerance re-judging on three builds (`conformance/tolerances/R6_REJUDGE_*.json`).

WAVE 1A READY (sbm_total_r6, nonfinite_r6, risk_f4, per_unit classes, all rulings above) at the commit that adds this line; see `git log -1 -- program/R6_HANDOVER.md`.
