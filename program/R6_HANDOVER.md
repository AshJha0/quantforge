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

WAVE 1A READY 2826732 (sbm_total_r6, nonfinite_r6, risk_f4, per_unit classes, all rulings above; jacobian_r6 follows as WAVE 1B)

## Wave 2: R6-2, R6-5, R6-7 (and R6-3's ES spec already in wave 1)

Read: `specifications/r6-rulings.md` R6-2.1, R6-2.2, R6-5.1 to R6-5.6, R6-7.1 to R6-7.6; specs `04-pricing/exotics.md` (stage G section), `06-risk/xva-exposure-portfolio.md`, `04-pricing/mbs.md`, `04-pricing/credit.md` (Dates), `04-pricing/bonds.md` (basis), `02-curves/inflation.md` (`infl.linker.price`).

### Behaviour changes

| Ruling | Operation | Change |
|---|---|---|
| R6-2.1 | `exotic.barrier.price`, `DISCRETE` | `E_DOMAIN` outside the envelope: allowed only for `DOWN_OUT` `CALL` with `barrier <= strike` or `UP_OUT` `PUT` with `barrier >= strike`, `rebate == 0`, and `abs(ln(spot/barrier)) >= 1.25 * vol * sqrt(T/n)` with `n = floor(m T + 0.5)`. Checked after the existing domain checks (E-A19, `n = 0`); compute in binary64, the goldens keep every decision away from 1.25 (closest inside 1.32, closest outside 0.91) |
| R6-5.1 | `xva.exposure.portfolio_hw` | Output keys `pfe_95`, `pfe_99` renamed `deflated_pfe_95`, `deflated_pfe_99` (general rule R6-5.6). Values unchanged |
| R6-5.5 | `xva.exposure.portfolio_hw` | Find every zero and level crossing as stated (critical points from `f'`, at least 6,001 scan points over +-12 sd, bisection). No golden value changes (stage G goldens were corrected by `fix_w4c_pfe.py`); builds that scan coarsely may fail `pfe_99` |
| R6-7.1 | `mbs.cashflows`, `mbs.price` | PSA with any monthly `CPR_k >= 1` (k = 1..wam): `E_DOMAIN`, after the existing checks. Python v0.8.0 crashes here (`complex` not serialisable: reproduced) |
| R6-7.3 | `credit.cds.*` | Trade date on an adjusted coupon date is priced: the last IMM date on or before `T` is `T`'s own unadjusted date, the first period starts at `T` (adjusted), one day accrued at step-in. Remove the D19 `E_INPUT` |
| R6-7.5 | `infl.linker.price` | `ref_cpi = round5(trunc6(raw))`, `index_ratio = round5(trunc6(ref_cpi / base_ref_cpi))`, nominal figures times that rounded ratio; `trunc6(x) = floor(x * 1e6) / 1e6`, `round5(t) = floor(t * 1e5 + 0.5) / 1e5` in binary64 |
| R6-7.2, R6-7.4, R6-7.6 | basis, ESTR, MBS delay | No behaviour change (new golden; ESTR lag 2 confirmed; `delay_days` documented) |

### Golden files (wave 2)

| File | Cases | Value | Error | Notes |
|---|---:|---:|---:|---|
| `r6/barrier_r6.json` (new) | 14 | 6 | 8 | edge of the envelope; every value case MC-checked |
| `stage_g/barrier_g.json` (changed) | 37 | 9 (was 31) | 28 (was 6) | 22 value cases now `E_DOMAIN`, same ids |
| `r6/mbs_r6.json` (new) | 10 | 2 | 8 | |
| `r6/cds_imm_r6.json` (new) | 8 | 8 | 0 | QuantLib `IsdaCdsEngine` within 1.3e-11 |
| `stage_d/credit_d.json` (changed) | 19 | 14 (was 13) | 5 (was 6) | `credit_d-0017` now a value case |
| `r6/basis_r6.json` (new) | 1 | 1 | 0 | |
| `stage_d/inflation_d.json` (changed) | 13 | 8 | 5 | `-0010`, `-0011` rounded |
| `stage_g/expsim_g.json` (changed) | 102 | 96 | 6 | keys renamed |

### Expected totals after wave 2 (with wave 1B)

**15,000** cases: value-checked **7,428**, error **5,058**, invariance **2,514**.

### Python v0.8.0 against wave 2 (`tools/r6_judge.py`): every failure is an intended change

`barrier_g` 22 fail (now `E_DOMAIN`), `barrier_r6` 8 fail, `mbs_r6` crash (complex), `cds_imm_r6` 8 fail and `credit_d-0017` (`E_INPUT`), `inflation_d` 2 fail (rounding), `expsim_g` 96 fail (keys); `basis_r6` passes.

### Oracle agreement

Goldens from `oracle/python/gen_r6_w2.py`, `gen_stage_g_w1.py R9`, `gen_stage_d_credit.py`, `gen_stage_d_w3.py`; MC acceptance 13 of 13 (`oracle/R6_BARRIER_ACCEPTANCE.json`); QuantLib CDS within 1.3e-11; basis implied repo re-solved by brentq within 1e-12.

WAVE 2 READY 3c5bcfe

## Wave 1B: `r6/jacobian_r6`

12 cases (8 value, 4 error): SOFR under `MONOTONE_CONVEX`, `MONOTONIC_LOG_CUBIC`, `TENSION_SPLINE` (`tension` 0.5), `HYBRID` (`step_end` the third pillar), `LOG_LINEAR_DF`, `LINEAR_ZERO`; SONIA and ESTR under `MONOTONE_CONVEX`; errors: `TENSION_SPLINE` without `tension`, `HYBRID` without `step_end` (`E_INPUT`), `tension` 0 (`E_DOMAIN`), `step_end` not a pillar (`E_INPUT`). Tolerance 1e-8 absolute plus 1e-6 relative. Largest entry above the diagonal: 0.039 (SOFR monotone convex). Ruling R6-1.3 records that the plan's Richardson test cannot hold for a 1 bp quotient (gap 5e-6 even for log-linear) and what is asserted instead.

**Which builds had the mask (finding 3, for the release notes):** Python (`risk_curve.py:197`, reproduced: code and v0.8.0 build), Rust (`risk_curve.rs:404`; the v0.8.0 binary returns 0.0 above the diagonal on 6 of 8 value cases: reproduced), C++ (`core/risk.cpp`, loop from `i = j`; the v0.8.0 binary returns 0 on the same entries and also lacked `tension`/`step_end`: reproduced). Java: no mask (Java lane, phase 0; largest upper entry 0.038): not reproduced in Java.

Totals with wave 1B: as stated under wave 2 (15,000 after waves 1 and 2).
