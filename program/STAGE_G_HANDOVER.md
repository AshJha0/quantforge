# Stage G handover

From the stage G spec and oracle session to the four language sessions and the lanes. Append-only. Each wave section says what a language session may read. Never read anything under `oracle/`: that is the oracle, and reading it breaks the clean room.

Stage G (v0.7): rates models and xVA (plan section 4, row G), plus Q3b, Q9, A5 (plan 12.3, parameters in 12.10) and R9 (plan 13.3). All stage G goldens are in `datasets/golden/stage_g/`, run through `conformance/runner/runner.py` (it finds them by suite name). Always read `specifications/cli-contract.md` (block "Stage G operations") and `specifications/stage-g-rulings.md` with any stage G slice. The stage F rules (F-1 to F-3 finite and negative-zero inputs, F-5 names, F-6 spec template) apply to every new operation.

## Wave plan

| Wave | Slices | Content | Main outside oracle |
|---|---|---|---|
| 1 | G1, R9 | Vasicek, CIR, Hull-White bond prices and bond options; discrete barrier monitoring (BGK) | QuantLib 1.44 model objects |
| 2 | G2, G3 | Jamshidian European swaption on Hull-White; Hull-White calibration to a swaption strip; G2++; Bermudan swaptions (tree and PDE); callable bonds | QuantLib `JamshidianSwaptionEngine`, `G2SwaptionEngine`, `TreeSwaptionEngine`, `FdHullWhiteSwaptionEngine`, `TreeCallableFixedRateBondEngine` |
| 3 | G4, Q3b, Q9 | LMM (caplet and swaption calibration, MC pricing); AAD core in four languages on the rates models (Q3b, ruling G-9); MC Greeks by pathwise, likelihood ratio and smoothed digitals, and the model-reserve dispersion report (Q9, ruling G-10) | QuantLib `LiborForwardModel`; closed forms for the Greeks tests |
| 4 | G5, G6 | CSA terms, netting sets, margin period of risk, collateral simulation; EE, PFE, EPE; CVA, DVA, FVA with the overlap defined, MVA, SIMM-style IM, wrong-way risk, KVA. Demo: exposure checked against ORE | ORE (Open Source Risk Engine, free) for exposure profiles; closed-form EE of a single swap under Hull-White |
| any | A5 | Heston and SABR calibration surrogate, Python research module only, challenger tier (ruling G-11) | the full pricers |

The parameters of Q3b, Q9 and A5 are fixed now (rulings G-9 to G-11), before any result is seen.

## WAVE 1 READY (2026-11-10): G1 short-rate models and R9 discrete barriers

Read with every slice: `specifications/cli-contract.md` (block "Stage G operations"), `specifications/stage-g-rulings.md` G-1 to G-8, `specifications/edge-case-register.md` (rows G1 to G5), `specifications/name-map.json` (regenerated: 228 operations).

### G1 (suite `shortrate_g`, 78 cases): `04-pricing/short-rate-models.md`
- New operations `rates.shortrate.zcb` and `rates.shortrate.zcb_option`, models `VASICEK`, `CIR`, `HULL_WHITE`.
- Build notes:
  - Small mean reversion (G-2): use `expm1` for `B` and a series for `(B - tau)/a^2` below `a tau = 1e-2`. The `a = 1e-4` golden fails a direct double evaluation by about 1e-9 relative.
  - Hull-White curve: log-linear discount factors with `(0, 1)` as the first node; the forward at a pillar time is the right-hand one (G-3); flat forward beyond the last pillar.
  - CIR options need a noncentral chi-square CDF to about 1e-15 relative. A Poisson-weighted sum of regularised lower incomplete gammas works (stop when past the Poisson mode and the term is below 1e-17 of the sum). Java and C++ need their own regularised incomplete gamma (series for `x < s + 1`, continued fraction otherwise). CIR option cases use class `root_finding` (1e-10).
  - `short_rate` is required by `zcb` for every model, required by `zcb_option` for `VASICEK` and `CIR`, and refused (`E_INPUT`) by `zcb_option` for `HULL_WHITE` (G-5).
- Property tests: put-call parity to 1e-12 per unit face; Hull-White `zcb` at `t = 0` equals the curve; `zero_rate -> short_rate` as `T - t -> 0`.

### R9 (suite `barrier_g`, 32 cases): `04-pricing/exotics.md`, section "Stage G addition"
- `exotic.barrier.price` gains `monitoring` (`CONTINUOUS` default, `DISCRETE`) and `monitoring_per_year`. Shift the barrier away from spot by `exp(0.5826 v sqrt(1/m))`, then use the stage E formula. `beta = 0.5826` exactly (G-7); the domain check uses the unshifted barrier (G-8).
- Property test (the R9 acceptance): daily down-and-out call and put against your own exact-date MC, 40,000 paths, `core.rng` seed 20261109, within 3 SE (parameters in the spec).

### Outside-oracle status (rule 11.2.5, ruling G-4)
`shortrate_g` 61 of 78 counted (QuantLib 1.44 `Vasicek`, `CoxIngersollRoss`, `HullWhite` on a `DiscountCurve`; every output a QuantLib value or `zero_rate` arithmetic on one). Not counted: the 15 error cases, the small-`a` case (QuantLib's cancellation) and the pillar-time case (QuantLib's centred forward). `barrier_g` 2 of 32 (the continuous rows, `AnalyticBarrierEngine`); the 25 BGK rows rest on the MC acceptance, and 5 are error cases. Wave 1: 63 of 110 = 57.3%, below the 60% floor on its own; with wave 2a (below) the stage stands at 96 of 150 = 64.0%. The floor is measured over the stage at release (G-4), error cases in the denominator.

### Model inventory
Rows MG-1 (short-rate models) and MG-2 (discrete barrier correction) added to `docs/model-inventory.md` with golden hashes.

## WAVE 2a READY (2026-11-10): Jamshidian swaption on Hull-White

Read: `specifications/04-pricing/short-rate-models.md`, section "`rates.shortrate.swaption`"; rulings G-12, G-13; cli-contract block "Stage G operations"; `specifications/name-map.json` (229 operations).

### G2a (suite `swaption_g`, 40 cases)
- New operation `rates.shortrate.swaption` (Hull-White only in this wave).
- Build notes:
  - Reuse the wave 1 Hull-White bond and bond-option code. The critical rate `r*` solves `sum c_i P(T0, Ti; r*) = 1`; the sum is strictly decreasing in `r`, so Newton from 0 with a bracket fallback converges. Solve until the sum is within 1e-15 relative of 1; a looser solve (QuantLib's engine stops near 1e-8) misses the goldens by about 3e-7 relative.
  - Fixed accruals are time differences, first one from expiry (G-12). `payment_times` must start after `expiry_years`.
  - `short_rate` is refused (`E_INPUT`), as for the Hull-White bond option.
- Property test: payer minus receiver equals `annuity (forward_swap_rate - K)` to 1e-8 per unit notional.

### Outside-oracle status
`swaption_g` 33 of 40 (every value case; the 7 error cases are not counted). Stage G so far: 96 of 150 = 64.0% (`oracle/outside_register_g.json`).

## WAVE 2b READY (2026-11-10): G2++ bond prices and bond options

Read: `specifications/04-pricing/short-rate-models.md`, section "G2++"; ruling G-14; cli-contract block "Stage G operations"; `specifications/name-map.json` (231 operations).

### G2b (suite `g2pp_g`, 38 cases)
- New operations `rates.g2pp.zcb` (with factor states `x`, `y`) and `rates.g2pp.zcb_option` (states start at 0; `x` or `y` present is `E_INPUT`).
- Build notes: the curve and its rules are the Hull-White ones (log-linear, `(0, 1)` first node); `P(0,t)` ratios only, no instantaneous forward, so no pillar rule is needed. Apply the G-2 small-`a` series to each factor. `rho` strictly inside `(-1, 1)`.
- Property tests: put-call parity; `eta -> 0` gives the Hull-White price (golden `g2pp_g-0031`); `x = y = 0`, `t = 0` gives the curve.

### Outside-oracle status
`g2pp_g` 30 of 38 (every value case except the one-factor limit; QuantLib 1.44 `G2`). Stage G so far: 126 of 188 = 67.0%.

## WAVE 3a READY (2026-11-10): Q9 part 1, Monte Carlo Greeks

Read: `specifications/06-risk/mc-greeks.md`; rulings G-10, G-15; cli-contract block "Stage G operations"; `specifications/name-map.json` (232 operations); `specifications/01-core/rng.md`.

### Q9 part 1 (suite `mcgreeks_g`, 21 cases)
- New operation `risk.mc.greeks`: price, delta and vega with standard errors, for `CALL`, `PUT`, `DIGITAL_CALL` by `PATHWISE` (digital smoothed by a call spread of half-width `smoothing_width`), `LIKELIHOOD_RATIO` and `BUMP` (central, common draws).
- Build notes: draws are `core.rng` stream 0, one AS 241 normal per path, in path order. Standard errors use divisor `n - 1`. `price` is always the unsmoothed payoff. Class `common_rng`; the goldens keep paths away from kinks, so indicator flips cannot happen.
- Property test (G-10 acceptance): the digital-call check in the spec at 100,000 paths, seed 20261109.

### Open item for the coordinator and owner
G-10's variance condition (smoothed pathwise below bump) passes by a ratio of 0.9985 only: at `h S = eps` the two estimators are nearly the same call spread, so the test has little power. Its parameters were fixed before the run and are not changed here; a stronger setting needs an owner ruling.

### Outside-oracle status
`mcgreeks_g` 0 of 21: no library reproduces the `core.rng` stream (as `risk.var.monte_carlo` in stage F). Stage G so far: 126 of 209 = 60.3%, just above the 60% floor.

## WAVE 4a READY (2026-11-10): closed-form swap exposure and CVA under Hull-White

Read: `specifications/06-risk/xva-exposure.md`; ruling G-16 (and G-12, G-13); cli-contract block "Stage G operations"; `specifications/name-map.json` (233 operations).

### G5a (suite `exposure_g`, 15 cases)
- New operation `xva.exposure.swap_ee_hw`: discounted EE at reset dates (each point is the wave 2a swaption on the remaining swap; payer for `PAY`, receiver for `RECEIVE`) and an optional bucketed CVA.
- Build notes: call your `rates.shortrate.swaption` code per date. Exposure times are compared to the reset dates exactly as binary64 numbers. `cva` is present only when both credit inputs are given.
- Property test: `PAY` minus `RECEIVE` EE equals the forward value of the remaining swap.

### Outside-oracle status
`exposure_g` 7 of 15 (every value case). Stage G so far: 133 of 224 = 59.4%, just below the 60% floor (the 21 `mcgreeks_g` cases have no outside source by construction).

## Status at the end of the 2026-11-10 spec session (hard stop 23:15)

All work is committed locally on `stage-g` (not pushed). Nothing in the language worktrees was touched.

**Specified, with goldens and oracle evidence (224 cases, 6 suites in `datasets/golden/stage_g/`):**

| Wave | Suite | Cases | Outside (QuantLib 1.44) | Spec |
|---|---|---|---|---|
| 1 | `shortrate_g` (Vasicek, CIR, Hull-White bonds and bond options) | 78 | 61 | `04-pricing/short-rate-models.md` |
| 1 | `barrier_g` (R9, BGK discrete monitoring) | 32 | 2 | `04-pricing/exotics.md`, "Stage G addition" |
| 2a | `swaption_g` (Jamshidian on Hull-White) | 40 | 33 | `short-rate-models.md` |
| 2b | `g2pp_g` (G2++ bonds and bond options) | 38 | 30 | `short-rate-models.md`, "G2++" |
| 3a | `mcgreeks_g` (Q9 part 1) | 21 | 0 (core.rng stream) | `06-risk/mc-greeks.md` |
| 4a | `exposure_g` (swap EE and CVA, closed form) | 15 | 7 | `06-risk/xva-exposure.md` |
| | **Stage G so far** | **224** | **133 = 59.4%** | |

Rulings G-1 to G-16 (`specifications/stage-g-rulings.md`); G-9 to G-11 fix the Q3b, Q9 and A5 parameters before any result. Acceptance runs: R9 passes (`oracle/R9_ACCEPTANCE.json`); Q9 part 1 passes (`oracle/Q9_ACCEPTANCE.json`), with the weak-power open item above. Inventory rows MG-1 to MG-4; edge-case rows G1 to G5; name map 233 operations; `quality_gate --check-specs` and `--check-register` show no new gaps. Generators: `oracle/python/gen_stage_g_w1.py` (slices G1, R9, G2A, G2B, G5A) and `gen_stage_g_q9.py`; a clean rerun reproduces every golden byte for byte.

**Left for stage G:**
- Wave 2 rest: Hull-White calibration to a swaption strip; Bermudan swaptions (tree and PDE, with a pinned reference scheme, as `exotic.american.fd`); callable bonds; G2++ swaptions.
- Wave 3 rest: LMM; Q3b AAD core in four languages (ruling G-9 ladder benchmark); Q9 part 2, the model-reserve dispersion report (Heston, SLV, local vol) on every exotic.
- Wave 4 rest: CSA terms, netting sets, margin period of risk, collateral simulation; simulated EE, PFE, EPE (must reproduce `exposure_g` within 3 SE); DVA, FVA with the overlap defined, MVA, SIMM-style IM, wrong-way risk, KVA; the ORE exposure demo.
- A5 surrogate (Python research module, challenger, ruling G-11).
- The R5 audit of the stage G specs (different model).
- Outside share: 59.4%, 0.6 points below the floor. The QuantLib-checkable wave 2 items (calibration, Bermudans, callable bonds) should lift it.
- Open owner decision: G-10's variance test has little power at its fixed parameters (ratio 0.9985).

**Carry-over 3 (stage F outside share 51.4%): not advanced.** `oracle/OUTSIDE_GAPS_F.md` already concludes no free source is left for the 134 value cases. The only runnable item, the `garch_f-0009` arch check under WSL, adds one case and was not attempted tonight.

**Next step:** the coordinator relays waves 1, 2a, 2b, 3a and 4a to the four language sessions. The spec session then continues with wave 2 (Hull-White calibration, then Bermudans with a pinned tree or PDE reference scheme and the QuantLib `TreeSwaptionEngine` and `FdHullWhiteSwaptionEngine` as convergence evidence).

## WAVE 2c READY (2026-11-10): Hull-White sigma calibration

Read: `specifications/04-pricing/short-rate-models.md`, section "`rates.shortrate.hw_calibrate`"; ruling G-17; cli-contract block "Stage G operations"; `specifications/name-map.json` (235 operations).

### G2c (suite `hwcal_g`, 6 cases)
- New operation `rates.shortrate.hw_calibrate`: `sigma` with `a` fixed, least squares on prices per unit notional over `[1e-4, 1]`; outputs `sigma`, `fitted_prices`, `rmse`.
- Build notes: reuse the wave 2a swaption code. The objective is smooth and has one interior minimum on the goldens; bracket it by a scan, then Newton or Brent on `F'` until the relative step is below 1e-12. `sigma` is judged at 1e-9 relative. The exact-fit case (`a = 0.01`) has `rmse` near 1e-18: judged at 1e-12 absolute.

## WAVE 2d READY (2026-11-10): Bermudan swaption, pinned reference scheme

Read: `specifications/04-pricing/short-rate-models.md`, sections "`rates.shortrate.bermudan_swaption`" and "Convergence and limit cases (Bermudan scheme)"; ruling G-18.

### G2d (suite `bermudan_g`, 15 cases)
- New operation `rates.shortrate.bermudan_swaption`. Implement the seven-step scheme exactly: fully implicit, coefficients at the earlier time, linear-extrapolation boundaries substituted into the tridiagonal rows, exercise applied on arrival at each exercise time except at 0. Golden generator runs in about 11 seconds.
- Property tests: one exercise date converges to your `rates.shortrate.swaption` price as the grid is refined (order about 1); a Bermudan price is at least the scheme's own single-date price for its first exercise date on the same grid (amended by R5 M1 / G-28: not the Jamshidian price).

### Outside-oracle status after waves 2c and 2d
Neither suite counts (G-17, G-18): the calibration objective and the pinned scheme are this platform's own, and QuantLib values are recorded as evidence only (`oracle/BERMUDAN_EVIDENCE_G.json`: QuantLib FD and tree within about 0.2% of the scheme at the default grid). **Stage G now stands at 133 of 245 = 54.3%, below the 60% floor.** The expectation that wave 2 would lift the share was wrong for these two slices. Candidates that would count: QuantLib-checkable closed forms still to be specified (Hull-White caps and floors as bond-option portfolios, G2++ European swaptions by `G2SwaptionEngine` if its integration can be set tight enough, CIR swaptions by Jamshidian), and ORE exposure profiles in wave 4.

## Status update (2026-11-10, after waves 2c and 2d)

Supersedes the counts in the status section above; everything else there still holds.

| Wave | Suite | Cases | Outside |
|---|---|---|---|
| 1 | `shortrate_g`, `barrier_g` | 110 | 63 |
| 2a, 2b | `swaption_g`, `g2pp_g` | 78 | 63 |
| 2c, 2d | `hwcal_g`, `bermudan_g` | 21 | 0 |
| 3a | `mcgreeks_g` | 21 | 0 |
| 4a | `exposure_g` | 15 | 7 |
| | **Stage G** | **245** | **133 = 54.3%** |

Rulings now G-1 to G-18. G-10 stays open for the owner (Q9 variance test with low power). Left for stage G: callable bonds (the same scheme with a call schedule), G2++ swaptions, two-parameter or time-dependent Hull-White calibration, LMM, Q3b, Q9 part 2, the rest of xVA, A5, the R5 audit, and the outside share. **Next step:** relay waves 2c and 2d; the spec session continues with the QuantLib-countable closed forms listed above (Hull-White caps and floors first), then callable bonds on the G-18 scheme.

## WAVE 2e READY (2026-11-10): caps and floors under the short-rate models

Read: `specifications/04-pricing/short-rate-models.md`, section "`rates.shortrate.capfloor`"; ruling G-19; `specifications/name-map.json` (236 operations).

### G2e (suite `capfloor_g`, 41 cases)
- New operation `rates.shortrate.capfloor` for `VASICEK`, `CIR`, `HULL_WHITE`: a portfolio of wave 1 bond options (put for a cap, call for a floor, strike `1/(1 + K tau)`, scaled by `1 + K tau`).
- Property test: cap minus floor equals the swaplet sum on the model's bond prices.

### Status update (after wave 2e)
`capfloor_g` 36 of 41 count (QuantLib model objects). **Stage G: 169 of 286 = 59.1%**, still 0.9 points below the 60% floor. Counted per suite: shortrate 61/78, barrier 2/32, swaption 33/40, g2pp 30/38, capfloor 36/41, exposure 7/15; hwcal 0/6, bermudan 0/15, mcgreeks 0/21. Rulings G-1 to G-19; G-10 open for the owner. Next step: relay wave 2e; then callable bonds on the G-18 scheme, and the remaining QuantLib-countable items (CIR Jamshidian swaption, G2++ swaption if `G2SwaptionEngine` can be set tight enough).

## WAVE 2f READY (2026-11-10): Jamshidian swaptions for Vasicek and CIR

Read: `specifications/04-pricing/short-rate-models.md`, section "Stage G wave 2f"; ruling G-20.

### G2f (suite `swaption_affine_g`, 39 cases)
- `rates.shortrate.swaption` gains optional `model`; absent means `HULL_WHITE` (wave 2a goldens unchanged).
- Build notes: the critical-rate solve uses the model's own bond formula; for CIR check `sum c_i P(T0, Ti; 0) >= 1` first, else `E_DOMAIN`. CIR cases use the noncentral chi-square of wave 1.

### Status update (after wave 2f)
`swaption_affine_g` 36 of 39 count. **Stage G: 205 of 325 = 63.1%, above the 60% floor** (error cases in the denominator). Per suite: shortrate 61/78, barrier 2/32, swaption 33/40, swaption_affine 36/39, g2pp 30/38, capfloor 36/41, exposure 7/15; hwcal 0/6, bermudan 0/15, mcgreeks 0/21. Rulings G-1 to G-20; G-10 open for the owner. Left: callable bonds (G-18 scheme), G2++ swaptions, LMM, Q3b, Q9 part 2, the rest of xVA, A5, the R5 audit; stage F carry-over 3 unchanged at 51.4%. Next step: relay waves 2c to 2f; then callable bonds.

## WAVE 2g READY (2026-11-10): callable bonds on the Bermudan scheme

Read: `specifications/04-pricing/short-rate-models.md`, sections "`rates.shortrate.callable_bond`" and its convergence table; ruling G-21; `specifications/name-map.json` (237 operations).

### G3 (suite `callable_g`, 12 cases)
- New operation `rates.shortrate.callable_bond`: reuse your wave 2d stepper; at each coupon date cap by the call price (if callable) and then add the coupon.
- Property tests: no call times converges to the straight bond at order about 1; a callable bond is never above the scheme's own no-call bond on the same grid (amended by R5 M1 / G-28: not the exact straight bond).

## Final status, 2026-11-10 (supersedes the earlier status counts)

All work committed locally on `stage-g`, not pushed. Waves READY: 1, 2a to 2g, 3a, 4a (12 suites, 337 cases). Rulings G-1 to G-21.

| Suite | Cases | Outside |
|---|---|---|
| shortrate_g | 78 | 61 |
| barrier_g | 32 | 2 |
| swaption_g | 40 | 33 |
| swaption_affine_g | 39 | 36 |
| g2pp_g | 38 | 30 |
| capfloor_g | 41 | 36 |
| hwcal_g | 6 | 0 |
| bermudan_g | 15 | 0 |
| callable_g | 12 | 0 |
| mcgreeks_g | 21 | 0 |
| exposure_g | 15 | 7 |
| **Stage G** | **337** | **205 = 60.8%** |

**Left for stage G:** G2++ swaptions; two-parameter or time-dependent Hull-White calibration; LMM; Q3b AAD core (G-9); Q9 part 2 model-reserve report; the rest of xVA (CSA, netting, MPoR, collateral simulation, PFE and EPE, DVA, FVA, MVA, SIMM-style IM, wrong-way risk, KVA, ORE demo); A5 surrogate (G-11); the R5 audit; QuantLib comparison for callable bonds. **Open for the owner:** G-10 (Q9 variance test, low power). **Carry-over 3** (stage F 51.4%): not advanced.

**Next step:** relay waves 2c to 2g to the language sessions; the spec session continues with G2++ swaptions and then the xVA simulation wave, keeping the outside share above 60% (it is 60.8% now, with little margin).

## Owner decision on G-10, and G-10b (2026-11-10)

G-10 is kept as registered and recorded as **inconclusive, low power** (rulings, CHANGELOG known issues). G-10b was registered with a closed-form power calculation (33,541 paths per estimator for 80% power at a variance ratio of 0.8; 60,000 registered) and committed (`ea11299`) before it ran. It then **passed**: ratio 0.1015 [0.0888, 0.1161], `Z = 33.35`. Language sessions: the Q9 property test now has two parts, G-10 as in the spec (report only, not gating) and G-10b (gating, same seed, streams and path count). F-33 stays open for the owner.

Final status otherwise unchanged from "Final status, 2026-11-10" above: 12 suites, 337 cases, outside 205 of 337 = 60.8%, rulings G-1 to G-21 plus G-10b; nothing pushed.

## WAVE 3b READY (2026-11-11): LIBOR market model, closed-form layer

Read: `specifications/04-pricing/lmm.md`; ruling G-22; cli-contract block "Stage G operations"; `specifications/name-map.json` (239 operations).

### G4a (suites `lmmcap_g`, 26 cases; `lmmswn_g`, 42 cases)
- New operation `rates.lmm.capfloor`: Black caplets on the integrated abcd variance to each fixing date. Outputs `price`, `caplet_prices`, `forward_rates`, `black_vols`.
- New operation `rates.lmm.swaption_rebonato`: Rebonato's frozen-weight swaption volatility with exponential correlation. Outputs `price`, `swap_rate`, `annuity`, `black_vol`.
- Build notes: integrate `sigma_i sigma_j` in closed form (the abcd product integrates to exponentials times polynomials) or by Gauss-Legendre to 1e-14 relative. Reuse the wave 1 Hull-White curve code for `P(t)`. Check `E_DOMAIN` on every forward before pricing.
- Property tests: cap minus floor equals the swap value; payer minus receiver equals `notional A (S - K)`; flat abcd gives `black_vols = d`.

### Status update (after wave 3b)
`lmmcap_g` 17 of 26 and `lmmswn_g` 36 of 42 count (QuantLib 1.44 `AbcdFunction`, `DiscountCurve`, `blackFormula`; every value case). **Stage G: 258 of 405 = 63.7%** (error cases and the 21 `mcgreeks_g` cases in the denominator). Generator `oracle/python/gen_stage_g_lmm.py`; a rerun reproduces the goldens byte for byte. `quality_gate --check-specs --check-register`: no new gaps. Rulings G-1 to G-22 plus G-10b.

**Not done in this session, still left for stage G:** simulated LMM; Q3b AAD core (G-9); Q9 part 2 reserve dispersion; wave 4 rest (CSA, netting, MPoR, collateral, simulated EE/PFE/EPE, DVA/FVA/MVA, SIMM-style IM, WWR, KVA, ORE demo); A5 surrogate (G-11, challenger only, so no goldens by ruling); stage F carry-over wave 2b. Most wave 4 items have no free outside library short of ORE; each such suite lowers the share, so the 3.7-point margin above 60% buys about 25 uncounted cases at the current total.

## WAVE 3c READY (2026-11-11): simulated LMM, acceptance only

Read: `specifications/04-pricing/lmm.md`, section "Simulated LMM"; rulings G-25, G-26. No new operation and no goldens: each language implements the terminal-measure simulation as a library function and adds the caplet acceptance (6 caplets within 3 SE of `lmmcap_g`) as a property test. Python reference run passes (`oracle/LMM_ACCEPTANCE.json`). Rebonato error versus simulation 0.4-0.5% (evidence only). Outside share unchanged: 258 of 405 = 63.7%.

## R5 audit fixes (2026-11-11)

### H1, outside count (ruling G-27)
Recounted against QuantLib's own `JamshidianSwaptionEngine` at 3e-7 relative: `swaption_g` 26/40 (was 33), `swaption_affine_g` 36/39, `exposure_g` 6/15 (was 7); the semi-annual cases cannot be written as whole-day QuantLib dates. **Honest stage G share: 250 of 405 = 61.7%.** Under the strictest reading (Rebonato `lmmswn_g` not counted): 214 of 405 = 52.8%; that reading is open for the owner (G-27).

### M1, property tests (ruling G-28)
Both tests restated against the scheme's own bounding value on the same grid (`short-rate-models.md`, "Property tests on the pinned scheme"). The failures were the first-order scheme bias: `callable_g-0007` +0.0093 over the exact straight bond, `bermudan_g-0007` 0.17% under Jamshidian. Language sessions: change these two property tests.

### M2, negative-strike Jamshidian (ruling G-29)
`1 + K tau_n <= 0` is `E_DOMAIN`; root bracket `[-1, 1]`. `swaption_g` gains 3 cases (0041, 0042 values at K = -0.2%, both QuantLib-engine counted; 0043 error): 43 cases, 28 counted. Stage G: 252 of 408 = 61.8%.

### M3, discrete barrier (ruling G-30)
`n = floor(m T + 0.5)`, `n >= 1` else `E_DOMAIN`, BGK step `dt = T/n`; rebates not BGK-corrected. `barrier_g` gains 5 cases (0033 to 0037: T = 0.3 with m = 252, the tie T = 0.5 with m = 3, UP_OUT and UP_IN with rebates, n = 0 error); original 32 unchanged byte for byte. Stage G: 252 of 413 = 61.0%.

### M4 to M6 and LOW items (rulings G-31 to G-34)
- M4 (G-31): full `E_LIMIT` table with the combined bound `nx x total steps <= 5e8`; 9 `E_LIMIT` goldens appended (tag `r5`) to shortrate, swaption, exposure, bermudan (2), callable, mcgreeks, barrier.
- M5 (G-32): Poisson sum from the mode with log weights; CDF 0 for a non-positive argument. 3 CIR goldens appended to `shortrate_g` (0079 to 0081). QuantLib 1.44 itself underflows at `sigma = 0.005` (returns 0 for a call worth 16,898.80 per 1,000,000), so those two do not count; this is the bug the guard prevents.
- M6 (G-33): `expm1` factors and the cross-term series; 6 G2++ goldens appended (a = 1e-4, a = b = 0.1), 5 count (QuantLib's small-a bond loses digits).
- LOW (G-34): L1 to L10 and the citation note recorded; R9 power and the strict-count reading added to CHANGELOG known issues; `mc-greeks.md` check order fixed (seed first); Bermudan step count in binary64 as written.
- Language sessions: new property and error cases only; no existing golden value changed (the appended cases keep every earlier case id).

**Honest stage G outside share after the R5 fixes: 258 of 435 = 59.3%, below the 60% floor.** The drop comes from the H1 strict recount (-8), the new error and limit cases, and the 5 `aadladder_g` cases. ORE under WSL (G-23) is the route back above the floor in wave 4.

## WAVE 3d READY (2026-11-11): Q3b AAD core

Read: `specifications/06-risk/aad-core.md`; rulings G-9, G-35. New operation `rates.shortrate.bermudan_ladder` (suite `aadladder_g`, 5 cases: 3 values, 2 errors). Build notes: tape your wave 2d scheme (or hand-write its adjoint: Thomas solve backwards, `max` through its active branch); report the G-9 cost ratio. Property test: AAD equals your own Richardson bump within G-9. Outside: none (G-18).

## WAVE 3e READY (2026-11-11): Q9 part 2, model-reserve dispersion

Read: `specifications/06-risk/model-reserve.md`; ruling G-36. New operation `risk.model_reserve.dispersion` (suite `reserve_g`, 9 cases: 6 values, 3 errors; outside none). The report over every single-asset exotic is registered with fixed parameters and belongs to the Python research lane; it has not been run. Stage G share: 258 of 444 = 58.1%.

## Answers to G-J1 to G-J3 and a golden fix (ruling G-38)
`capfloor_g-0040` fixed (strike -1.0, so `1 + K tau = 0`, `E_DOMAIN`): all builds rerun that case. G-J1: negative `start_years` is `E_DOMAIN` after `side`, before `payment_times`. G-J2: the Java method is acceptable. `aadladder_g` (wave 3d) is READY (section above).

## A5 READY (2026-11-11): surrogate spec and acceptance harness

Read (research lane only; language sessions have nothing to build): `specifications/11-research/a5-surrogate.md`; rulings G-11, G-37. Harness `oracle/python/a5_acceptance.py`; self-test passes and is non-vacuous (`oracle/A5_HARNESS_SELFTEST.json`). No surrogate trained yet; never in goldens.

## Stage F carry-over wave 2b, part 1 READY (2026-11-11): E1 for the stage F operations

`gen_stage_f_e1.py` now skips only the `e1_*` files (and `stage_g`, whose operations get E1 in a later pass). E1 grows from 5,247 to 5,535 cases (+288) over 226 operations in 24 files; new file `e1_book.json`; **case ids in the `e1_*` files renumber**, so every build reruns the whole E1 set. Not done: F3 (inflation01, dividend and borrow, correlation sensitivities), F4 (reverse stress, limits, concentration, liquidity-adjusted risk, vol by horizon, model-risk reserve), FRTB vega, curvature and the other risk classes; E1 for the stage G operations.

## WAVE 4b READY (2026-11-11): deterministic xVA layer

Read: `specifications/06-risk/xva-framework.md`; rulings G-40, G-41, G-43, G-44. New operations `xva.exposure.collateralised` (`collexp_g`, 17), `xva.adjustments.value` (`xvaadj_g`, 12), `xva.simm.ir_delta` (`simm_g`, 8), `xva.wwr.cva_hw` (`wwr_g`, 6). Build notes: everything is exact arithmetic on the inputs except the WWR root (monotone in `a`; Newton from `ln h`). Property tests: total EE equals the sum over sets; zero thresholds with no lag give zero exposure; `b = 0` WWR equals the independent CVA. Outside: none. **Stage G share: 258 of 487 = 53.0%** (below 60%; ORE-checked wave 4c is the planned recovery, G-39).
