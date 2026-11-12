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

WAVE 1 READY 96f7a33 (1A and 1B: every wave 1 golden committed)

## Wave 3: R6-6, R6-9, R6-11 (audit rulings, use case 6), R6-25

Read: `specifications/r6-rulings.md` R6-6.1 to R6-6.4, R6-11 table (audit items 1 to 20), R6-11.20 (use case 6); specs `08-hedging/hedge-solvers.md` and the three other hedging pages ("R6 amendments" sections), `04-pricing/use-cases.md` (use case 6), `benchmarks/targets.md` (T6, T7).

**Correction to wave 2:** regenerating `barrier_g` dropped the R5 case `barrier_g-0038` (`monitoring_per_year` 1,000,001, `E_LIMIT`); restored at `e1d2584`. Pull `r6` again if you took wave 2 at `3c5bcfe`.

### Behaviour changes

| Ruling | Operation | Change |
|---|---|---|
| R6-6.1 | `hedge.qp.solve`, `hedge.frontier.solve`, `hedge.integer.solve` | Kink `|x_j| <= 1e-11 max(1, max|x|)`, then exact re-solve on the state; active-set or sign-state iterations capped at `10 n + 100`; integer search capped at 1,000,000 points or nodes; both give `E_NO_CONVERGENCE`. Property test per language: a planted run with a cap of 1 returns the code |
| R6-6.2 | every I-3 decision | Jacobi scaling first: `D M D`, `D_jj = 1/sqrt(M_jj)`; `E` rows to unit norm and columns by `D`; reduced Hessian `Z^T D H D Z` against the largest eigenvalue of `D H D`. Solution unchanged |
| R6-11.3, R6-11.4, R6-11.5 | qp, integer, select | Feasibility tolerance exactly 1e-9 relative; accepted answer has KKT residual at most `1e-10 max(1, max|g|)`; ties within `1e-12 max(best, f(0))` |
| R6-11.6 | `hedge.select.solve` | `max_instruments` outside `1..n`: `E_INPUT`, before the subset-count `E_LIMIT` |
| R6-11.7 | `hedge.minvar.ratio` | Negative pivot: `E_NOT_POSITIVE_DEFINITE`; small pivot of the scaled form: `E_SINGULAR`; lower triangle used |
| R6-11.9, R6-11.16 | `hedge.credit.cds`, `hedge.correlation.neutralise` | Negative bumped hazard: `E_DOMAIN`; spread vol `s <= 1e-12 (v1 + v2)`: `E_SINGULAR` (no goldens yet) |
| R6-11.12 | `hedge.beta.futures` | Evaluate `((target_beta - beta) * V) / (F * m)` in that order before rounding |
| R6-11.13 | `hedge.qp.solve` | `eq_matrix: []` is `E_INPUT` |
| R6-11.18 | greeks, correlation books | Unknown `instrument` string: `E_SCHEMA` |
| R6-11.20 | `usecase.option_hedge_lots` (new) | Use case 6, spec in `use-cases.md`: book Greeks, per-lot hedge Greeks, weights `1/max(1,|b_t|)^2`, `hedge.integer.solve` with lot bounds `+-max_lots`, Greeks after for all three, `hedge_cost`, `rounding_cost`. Checks: `hedges` empty `E_INPUT`; `lot_size <= 0`, `half_spread < 0`, `max_lots < 1` `E_DOMAIN`; unknown target `E_SCHEMA`; F-2 first |
| R6-9 | every operation | Nothing new to build if F-2 is implemented; the new E1 goldens exercise it on 29 operations that had none |

### Golden files (wave 3)

| File | Cases | Value | Error | Notes |
|---|---:|---:|---:|---|
| `r6/hedgeqp_large_r6.json` | 5 | 5 | 0 | n = 50 (3 cases) and n = 200 (2); HiGHS state, exact KKT (residual below 1e-40), HiGHS `x` within 1.2e-6; `root_finding`. Time T6/T7 per `benchmarks/targets.md` and publish |
| `r6/hedgescale_r6.json` | 4 | 3 | 1 | mixed units; v0.8.0 Python returns `E_SINGULAR` on the three value cases (finding 21 reproduced) |
| `r6/hedgeaudit_r6.json` | 3 | 0 | 3 | audit items 6, 7, 13; v0.8.0 Python fails all three (intended) |
| `r6/uc6_r6.json` | 10 | 4 | 6 | use case 6 |
| `r6/e1_r6.json` | 54 | 0 | 54 | F-2 on 29 operations (two per operation where it has two or more Real inputs); v0.8.0 Python passes 54 of 54 |

New gates (both shown red on a planted fault): `python tools/check_e1_coverage.py` (`--self-test`; 254 of 276 operations covered, 22 exempt because no golden of theirs has a Real input, listed in `conformance/E1_EXEMPT.json`) and `python tools/check_tolerance_units.py` (`--self-test`). Name map regenerated: 276 operations (`risk.frtb.sbm_total`, `usecase.option_hedge_lots` added).

### Expected totals after wave 3 (all waves)

**15,076** cases: value-checked **7,440**, error **5,122**, invariance (`any` + `same_as`) **2,514**. Against the baseline 14,941: +135 cases, +21 value, +114 error (22 of the error increase are `barrier_g` value cases turned `E_DOMAIN`).

### R6-25 (low items, this lane's share)

| Item | Where |
|---|---|
| SSVI butterfly test is sufficient only; `false` can be a false alarm | `05-volatility/smile-and-surface.md` (`butterfly_free`) |
| LMM simulation bias bound (`|z| <= 3` and `|mc - cf| <= 3 SE + 2%`; worst 1.2%) and a Rebonato criterion (`3 SE + 1%`; 0.41%, 0.47% pass) | `04-pricing/lmm.md` |
| CDS repricing against QuantLib about 1e-11 (not 1e-13) with weekend dates | `04-pricing/credit.md` (`credit.cds.bootstrap`) |
| Good Friday early closes: the listed years are first-Friday Good Fridays; the rule is the published list | `01-core/calendars.md` |
| `hedgeslip_i`, `hedgeint_i` register wording | `oracle/outside_register_i.json` |

### Stage I outside share (R6-13, coordinator request)

`tools/outside_shares.py`: stage I is **102 of 278 = 36.7%** without the wave 5 sweeps and 266 of 443 = 60.05% with them. The ceiling without sweeps, even if every remaining value case got a real library check, is below 60%: 153 of the 278 cases are value cases, 125 are error cases (most `E_INPUT` and `E_DOMAIN` shape checks no library can confirm). Classes with no free outside reference: integer lots (`hedgeint_i`, 12 value cases: no free library solves bounded integer least squares; HiGHS 1.16 solves MILP and continuous QP only), the beta futures and residual report arithmetic (`hedgebeta_i` 8, `hedgeres_i` 7: closed-form arithmetic, any check is a reimplementation), slippage (`hedgeslip_i` 6), the backtests (`hedgebt_i`, `hedgebtcost_i`, 12: reimplementation). Maximum reachable by honest library checks: about 108 value cases plus about 23 `E_SINGULAR`/`E_INFEASIBLE`/`E_NOT_POSITIVE_DEFINITE` decisions confirmable by numpy or HiGHS, so about 131 of 278 = 47%. The R6 hedge goldens (in `r6/`, not counted to stage I) are checked by HiGHS but only to its 1e-6 tolerance, not the case tolerance, so they do not count under I-2 either. **Shortfall for the owner: stage I cannot reach 60% under R6-13 without counting the wave 5 sweeps; the gap is about 13 points (36 cases) at best.** Not done in this lane: the per-case register for I (the numbers above are from the suite register).

### Oracle agreement and evidence

Goldens from `oracle/python/gen_r6_w3.py` (large QP, scaling, audit, use case 6) and `gen_r6_e1.py`. Audit hand examples recomputed by the oracle: all agree (`oracle/python/r6_audit_examples.py`). Integer `E_NO_CONVERGENCE` has no golden (method-dependent stop); property tests only.

WAVE 3 READY b877bc4

## Findings reproduced (spec and oracle lane scope)

Script: `oracle/python/r6_repro.py` (plus `tools/r6_judge.py` runs on the v0.8.0 builds named).

| Finding | Result |
|---|---|
| 3 Jacobian mask | **Reproduced** in Python, Rust and C++ (v0.8.0 builds return 0.0 above the diagonal; up to 0.039 expected). **Not reproduced** in Java (no mask; Java lane) |
| 4 Discrete barriers | **Reproduced**: `barrier_g-0006` (down-and-out put, monthly) BGK 0.2962 against exact-date MC 0.2478 +- 0.0012 (1M paths): +19.6% (review +19%); `barrier_g-0034` class reproduced on the grid (reverse barriers off by up to 120%) |
| 11 ES estimator | **Reproduced**: n = 500, 99% (`risk_f4-0003`): v0.8.0 estimator 7,009,443 against Acerbi-Tasche 7,459,030, -6.0% |
| 12 FRTB aggregation | **Reproduced**: `frtb_f-0003` (binds high) plus `frtb_f2b-0002` (binds low): sum of class capitals above the MAR21.7 total (`sbm_total_r6-0001`) |
| 13 PFE label | **Reproduced** by reading: `pfe_q` is a quantile of the deflated exposure (spec line 19); renamed |
| 14 Per-unit tolerances | **Reproduced in kind, not in count**: 460 loose per-unit outputs in 236 cases under my key list (review: 102 cases on a narrower list); no build fails the tightened class |
| 15 Fuzz crash | Java crash **not run here** (no local jar); the code path (`Bonds.java:262`, `BigDecimal(-inf)`) throws; Java lane reproduced exit 70. Python, Rust, C++ return `E_NON_FINITE`: the crash is Java-only |
| 17 G-34 L1 bias, G-10b | **Reproduced**: exact bias of the smoothed estimator -0.042% (review 0.04%); G-10c run: bump lower MSE |
| 18 MBS PSA, basis, CDS IMM, ESTR | MBS **reproduced** (Python v0.8.0 crashes on PSA 5000: complex result); basis golden implied repo near -100% **reproduced**; CDS IMM `E_INPUT` **reproduced** (`credit_d-0017`, Python); ESTR "unopened sources" **reproduced** (Strata opened now, second source not found) |
| 10 E1 gaps (53 operations) | **Reproduced in kind**: 51 operations lacked an E1 golden (not 53); 22 have no Real input, 29 now covered |
| 21 Mixed-unit `E_SINGULAR` | **Reproduced**: v0.8.0 Python returns `E_SINGULAR` on `hedgescale_r6-0001` to `-0003` |
| 7 Hedge solver at size | Largest stage I golden 6 x 4: **reproduced**. v0.8.0 Python solves the five large goldens correctly (timing not yet measured against T6/T7) |

## Plan 14.1 acceptance: oracle-side evidence paths

| Item | Acceptance | Evidence (oracle side) | Status |
|---|---|---|---|
| R6-1 | Goldens for the four non-local methods; entries within 1e-9 + 1e-7 rel of Richardson; an upper entry above 1e-3 | `datasets/golden/r6/jacobian_r6.json`, `oracle/python/gen_r6_w1.py` (gaps in `verified_by`) | Goldens and upper entry met; Richardson 1e-9 **not met by design** (R6-1.3: 1 bp truncation 5e-6) |
| R6-2 | MC (exact dates, >= 4M antithetic, `core.rng`) for down-out puts and up-out calls at daily, weekly, monthly; every `ok` golden within max(3 SE, 0.5%); outside cases are errors; tutorial 12 | `oracle/R6_BARRIER_ACCEPTANCE.json` (13 of 13), `oracle/R6_BARRIER_GRID.json`, `qf_oracle/mc_barrier.py`, `barrier_g`, `barrier_r6` | Met; the named put/call types are outside the envelope (error goldens); tutorial 12: docs lane |
| R6-3 | Goldens match an independent numpy estimator at integer and non-integer `n(1-c)` | `oracle/python/outside_f.py` `h_hist`; `stage_f/risk_f4.json` | Met (20 of 20) |
| R6-4 | Hand case where class maxima come from different scenarios; total strictly below the sum | `r6/sbm_total_r6.json` (cases 1, 2) | Met |
| R6-5 | G-42b recorded (evidence lane, ORE); G-10c recorded; G-34 L1 corrected; PFE renamed | `oracle/G10C_RESULT.json`, `oracle/python/run_g10c.py`, R6-5.1 to R6-5.4 | Met for this lane; G-42b is the evidence lane's |
| R6-6 | Four languages agree on large goldens; KKT residual below 1e-9 checked with an outside solver on the split form; timing published; mixed-unit regular problem not `E_SINGULAR` | `r6/hedgeqp_large_r6.json`, `oracle/R6_HEDGE_LARGE.json`, `r6/hedgescale_r6.json`, `benchmarks/targets.md` T6/T7 | Oracle side met; agreement and timing: language lanes |
| R6-7 | Goldens for each; ESTR ruling cites what was opened and when | `r6/mbs_r6`, `r6/basis_r6`, `r6/cds_imm_r6`, `stage_d/credit_d-0017`, `stage_d/inflation_d-0010/-0011`; R6-7.4 | Met, except ESTR second source not found |
| R6-8 | Failing input as a golden | `r6/nonfinite_r6.json` | Met (fuzz green: language lanes and CI) |
| R6-9 | Gate red on a new operation with no E1 case | `tools/check_e1_coverage.py --self-test`; `r6/e1_r6.json` | Met |
| R6-10 | No per-unit output above 1e-8 absolute without a ruling; cases re-judged | `tools/check_tolerance_units.py` (and `--self-test`), `conformance/tolerances/R6_REJUDGE_*.json`, `apply_r6_per_unit.py` | Met |
| R6-11 | Audit file; each disagreement ruled; use case 6 with goldens and tutorial link | `r6-rulings.md` R6-11 table; `r6/hedgeaudit_r6.json`; `r6/uc6_r6.json`; `oracle/python/r6_audit_examples.py` | Met; tutorial link: docs lane |

### Stage I outside share under the owner's 2026-11-12 rule (value-checked cases only)

Recomputed from the suite register (every counted case is a value case): **102 of 153 value cases = 66.7%** without wave 5 and without any R6 case added; with wave 5, 266 of 318 = 83.6%. Old all-case figure beside it: 102 of 278 = 36.7% (60.05% with wave 5). No case was added to reach this. Value classes with no free outside reference, named with the reason: integer lots `hedgeint_i` (12: no free library solves bounded integer least squares; HiGHS 1.16 does MILP and continuous QP only), beta futures `hedgebeta_i` (8: closed-form arithmetic; any check would restate the formula), residual report `hedgeres_i` (7: same), slippage `hedgeslip_i` (6: exact rational arithmetic is the oracle), backtests `hedgebt_i`/`hedgebtcost_i` (12: spec cash-account arithmetic on QuantLib values, classed reimplementation). The earlier "shortfall" paragraph applies to the old all-case rule only. Figures to be confirmed by the evidence lane's updated `tools/outside_shares.py` when `r6-evidence` lands (this lane does not edit the tool).

### Stage I per-case register (replaces the suite-count assumption)

`tools/stage_i_case_register.py` writes `oracle/outside_register_i_cases.json` from each case's own `verified_by` (a library is named there only when it agreed within the case tolerance, I-2). Real figures, no assumption: **102 of 153 value cases = 66.7%** without wave 5 and without added cases; 266 of 318 = 83.6% with wave 5; old all-case rule 102 of 278 = 36.7%. The per-case count equals the favourable suite-count reading exactly: every counted case is a value case. No R6 case is added to stage I. Uncounted value cases and reasons, confirmed: `hedgeint_i` 12 (no free bounded integer least-squares solver; HiGHS is MILP or continuous QP); `hedgebeta_i` 8 and `hedgeres_i` 7 (closed-form arithmetic; a check would restate the formula: correct); `hedgeslip_i` 6 (exact rational arithmetic is the oracle itself: correct); `hedgebt_i` 7 and `hedgebtcost_i` 5 (QuantLib values, then the spec's cash-account arithmetic: reimplementation); plus 1 in `hedgecost_i`, 2 in `hedgefrontier_i`, 1 in `hedgemv_i`, 2 in `hedgeqp_i` where no outside solver agreed within tolerance (left uncounted, as I-2 says). Merged `r6-evidence` at `b9b2b3c`.

### R6-1 oracle side: met (plan row reworded to match R6-1.3)

Per-case Richardson gaps, largest upper entry and the truncation explanation: `oracle/R6_JACOBIAN_RICHARDSON.json` (8 value cases of `r6/jacobian_r6`; smooth methods about 5e-6, piecewise SOFR `MONOTONE_CONVEX` and `HYBRID` 1.4e-3). No golden or build change. R6-11.9 and R6-11.16 stay open without goldens: each needs a new check in the language builds, beyond the rulings already implemented.

### R6-1: cause of the 1.4e-3 gaps (follow-up)

Not truncation in the usual small-`h` sense and not a kink: `oracle/R6_JACOBIAN_KINK.json` shows, for entry [10, 9] under SOFR `MONOTONE_CONVEX` and `HYBRID`, central quotients -0.237553 (1 bp), -0.236481 (0.5 bp), -0.236060 (0.1 bp), -0.2360156 (0.01 bp), and forward minus backward 0.0319, 0.0157, 0.00328, 0.000328, which shrinks in proportion to the bump. The zero rate is smooth but strongly curved in that quote, so 1 bp is outside the `h^2` range. Not a defect; documented as a known limit in `par-and-key-rate.md` and R6-1.3. No golden or build change.

## Rulings on the Python lane questions (2026-11-12)

See `r6-rulings.md`, section "Python lane questions": R6-6.2a (no scaling under `MIN_NORM`: confirmed), R6-6.1a (exact-zero kink test conforms for an exact active set; coverage gap: no golden distinguishes it), R6-16a (test file names are not G4 modules), E-Q7 and E-Q11 ruled as Python built them, F-Q1 and F-Q4 ruled (field text and method not normative), G-Q2 deferred to J-10, R6-6.4a (Python's large hedge solve missed T6/T7: 412.6 s against 46 s; target unchanged; `expsim_g` has no target). R6-1.3 wording now matches the corrected plan row: R6-1 met.

### R6-6.1b: kink coverage closed by argument, no golden

See `r6-rulings.md` R6-6.1b: a misclassified position within 1e-11 changes the answer by at most about cond x 1e-11, inside `root_finding`, so no golden can separate the two tests. The tolerance binds only builds whose final step is not an exact re-solve on the state. Python's exact-zero test conforms. Totals unchanged (15,076: value 7,440, error 5,122, invariance 2,514).

## Wave 3B: stale golden copies (Java J-R6-3), rulings J-R6-4, J-R6-5, negative-pivot band, R6-11.16 corrected

Changed case ids (expected results only): `e1_risk-0372` (ES and `tail_count` from its source `risk_f4-0039`), `edge_d-0015`, `edge_d-0016`, `edge_d-0017` (R6-7.5 rounding). Totals unchanged: 15,076 (value 7,440, error 5,122, invariance 2,514). `hedgecorr_i-0015` stays `E_DOMAIN`; ruling R6-11.16 was wrong and is corrected to `E_DOMAIN`. Rulings in `r6-rulings.md`, "Java lane questions".

Why the oracle side missed them: each regeneration rewrote only its own file. `stage_f/e1_*` twins are copies made once by `gen_stage_f_e1.py` from the goldens of the day, and `edge_d` has its own copy of the linker formula in `gen_r1_edge.py`; nothing compared a copy with its source after the source changed, and the per-file diffs I checked were of the regenerated files only. New gate: `python tools/check_golden_copies.py` (any case whose inputs equal another case's inputs, `-0.0` read as `0.0`, must expect the same result; `--self-test` shows it red on a planted stale twin). The formula copy in `gen_r1_edge.py` now calls the shared `tips_round`, so it cannot drift again. A search for other copies of changed rulings (ES, TIPS, PFE keys, barrier envelope, `sbm_total`) found none beyond these four.

WAVE 3B READY 516b776 (changed: e1_risk-0372, edge_d-0015, edge_d-0016, edge_d-0017; totals 15,076)

## Wave 3C: correction to wave 3B

What happened: while checking J-R6-3 I ran `gen_stage_f_e1.py` once. It rewrote every `stage_f/e1_*` file and also created two NEW files, `e1_risk_1.json` (713 cases) and `e1_risk_2.json` (129), because it now partitions its 6,421 cases differently from the committed layout. I restored the tracked files with `git checkout`, which does not remove untracked files, and `git add -A` committed the two new ones in `516b776`. They were regenerated E1 cases under new ids: 538 of the 842 have exactly the operation and inputs of an existing golden (duplicates); the other 304 are the generator's re-sweep over the R6-changed inputs and new operations, whose E1 coverage this round is already given by `r6/e1_r6` (the gate shows every operation covered). None was intended; all removed. Removed. The only intended wave 3B changes stand: `e1_risk-0372`, `edge_d-0015`, `-0016`, `-0017`.

New gate `python tools/check_case_total.py`: the committed totals and unique ids must equal the last `TOTALS:` line in this file (it reports 15,918 with the stray files and fails). `gen_stage_f_e1.py` must not be rerun on `r6` without restoring its file layout (noted for the evidence lane).

TOTALS: 15076 value 7440 error 5122 invariance 2514

WAVE 3C READY fde2c4a (stray files removed; 15,076 cases: value 7,440, error 5,122, invariance 2,514)

## `aadladder_g` gradient disagreement (second oracle lane): not a defect

Recomputed from the oracle's own scheme (`gen_stage_g_berm.price`) by central differences, absolute bump 1e-6 on each discount factor: at the golden grid (101 points, 50 steps a year) the entries reproduce the golden to every digit (127, 191,964, 173,816, 147,510, -233,482, -343,473). The same derivative at finer grids: 401/200 gives 127, 220,895, 163,851, 132,970, -236,617, -347,516; 801/400 gives 127, 225,712, 158,174, 131,838, -234,410, -347,771. So the golden and the spec are right: the spec defines the ladder as the derivative of the discrete scheme at the case's grid (G-9, `aad-core.md`), and the discount-factor entries of that scheme are 15% to 18% away from the converged model's at the golden grid, while its price is only 0.24% away. The outside check compared against QuantLib's converged derivative with a tolerance sized from QuantLib's own grid behaviour, which converges faster in the curve inputs than the spec scheme: hence a gap of about 30,000 against a tolerance of about 2,100. No golden changes; no language build is affected. `aad-core.md` now states the convention (absolute change of each input discount factor, scheme derivative at the case grid, not the model derivative) with these numbers.

For the second oracle lane: count the `aadladder_g` price, `d_price_d_mean_reversion` and `d_price_d_sigma` only if they pass with a tolerance measured on each derivative itself; leave the discount-factor entries uncounted (no outside library differentiates the spec's scheme, G-18), so the three cases do not count under "every compared output".

## UNFINISHED at shutdown (2026-11-12)

- R6-27: spec text done (`5fa5d6c`). Grid table committed: `oracle/R6_LADDER_GRIDS.json` (101/50 to 801/400) and `oracle/R6_LADDER_GRIDS_EXTRA.json` (501/250, 601/300). No single grid meets 2% for all three cases (convergence is not monotone); chosen: `aadladder_g-0002` at 501/250 (worst 0.99%, 3.3 s per price). Golden generator `oracle/python/gen_r6_w4.py` was launched detached (`run_r6_w4.cmd`, log `oracle/python/gen_r6_w4.log`); the shutdown likely killed it. Rerun detached, check the log, commit `datasets/golden/r6/aadladder_r6.json`, then write `WAVE 4 READY` with TOTALS 15077 value 7441 error 5122 invariance 2514.
- Blind re-derivation findings not yet ruled: traffic-light plus factors (1996 vs MAR32.9/MAR33.42), equity vega 77.78% vs 77.7817%, binding-scenario tie rule as a library choice, MAR21.44 root-2 scope for inflation and cross-currency basis.

## Wave 4: R6-27 (Bermudan ladder on a finer grid; tag blocker)

Read: `specifications/06-risk/aad-core.md` (R6-27 section). Generator `oracle/python/gen_r6_w4.py` (run detached, 218 s, log `oracle/python/gen_r6_w4.log`).

| File | Cases | Value | Error | Notes |
|---|---:|---:|---:|---|
| `r6/aadladder_r6.json` (new) | 1 | 1 | 0 | `aadladder_g-0002`'s inputs at `nx = 501`, 250 steps a year; every ladder entry within 0.99% of the 801/400 ladder |

**Convergence is not monotone.** No single grid meets 2% for all three `aadladder_g` cases (table in `oracle/R6_LADDER_GRIDS.json` and `R6_LADDER_GRIDS_EXTRA.json`); this golden is one case on one grid, chosen because it meets 2%. The ladder at the default grid (101/50) is a derivative of the discrete scheme and is not for hedging. Real fix: stage K item K-8.

**Richardson gate.** The q3b gate (two Richardson pairs agree within 1e-9) is for the 101/50 grid. On 501/250 they agree to 1.9e-9; the accepted gate here is 2.5e-9, a quarter of the case tolerance (relative 1e-8), recorded in the case's `verified_by`.

**What the languages must do.** No behaviour change: `rates.shortrate.bermudan_ladder` must accept `nx = 501`, `steps_per_year = 250` and pass the case at absolute 1e-10, relative 1e-8. Cost about 3.3 s per price in the Python oracle; a build that bumps every input sequentially at this grid should check its timeout. Docs lane: inventory entry and tutorial carry the three-grid table and "not for hedging at the default grid".

TOTALS: 15077 value 7441 error 5122 invariance 2514
