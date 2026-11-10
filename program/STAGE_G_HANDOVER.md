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
