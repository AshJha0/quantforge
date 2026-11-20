# Stressed exposure: Effective EPE under current and stress calibrations

Spec version 0.1.0. Status: **PROPOSED** (stage K item K-8b; xVA spec lane 2026-11-19; nothing implemented, no golden file written). Rulings `stage-k-rulings-xva.md` KR-168, KR-173 to KR-176; stage G G-40, G-42. Gate: `program/STAGE_K_XVA_GATE.md`.

Every output carries `label`: "regulatory formula on caller inputs; not a regulatory return" (KR-176).

**Plain idea.** Exposure models calibrated to calm markets give small exposures, and capital set on them shrinks exactly when risk is quietly building. The Basel internal models method therefore asks for exposure twice: once with today's calibration and once with a calibration taken from a stress period, and the bank holds capital on whichever is larger. Two details matter. The larger one is chosen for the whole portfolio, not counterparty by counterparty, so a counterparty whose exposure happens to fall under stress still uses the stressed numbers if the portfolio does. And the exposure measure is Effective EPE: the average over the first year of an expected-exposure profile that is never allowed to fall.

## Sources

| Ref | Source | Evidence class | Used for |
|---|---|---|---|
| [CRE53] | Basel Framework CRE53.7 (p. 465: greater of capital on Effective EPE with current data and with a stress calibration, at total portfolio level), CRE53.11-53.13 (EAD = alpha x Effective EPE; Effective EE non-decreasing; Effective EPE the time-weighted average over the first year, or until all contracts mature), CRE53.14 (alpha 1.4), CRE53.16 (own alpha floor 1.2), PDF of 11/11/2026 | read 2026-11-19 | every rule |
| [ORE-E] | ORE examples: `xva.csv` columns `BaselEPE`, `BaselEEPE` | read 2026-11-19 (column names and one example's numbers) | the O route |
| G-40 | `effective_epe` | read (repo) | the averaging rule already in use |

## Formal statement

### `xva.exposure.stressed_eepe` (KR-168)

Inputs: `grid` `t_0 < t_1 < ... < t_m` (years, `t_0 = 0`); `netting_sets` [{`id`, `ee_current` (`m + 1` values `>= 0`), `ee_stressed` (same), `capital_weight` `w >= 0`, optional `maturity` (years)}]; `alpha` (default 1.4), `own_alpha` (default false).

Per netting set and calibration: horizon `T* = min(1, max maturity of the set)` if `maturity` is given and below 1, else 1; Effective EE `eee_0 = ee_0`, `eee_k = max(eee_(k-1), ee_k)`; `eepe = sum_(k: t_k <= T*) eee_k (t_k - t_(k-1)) / T*` (grid points strictly within the horizon plus the point at `T*`; `T*` must be a grid point, else `E_INPUT`); `ead = alpha x eepe`.

Portfolio: `K_cur = sum w ead_cur`, `K_str = sum w ead_str`; `calibration = "stressed"` if `K_str > K_cur` else `"current"`; every set reports both EADs and the one used.

Outputs: per set `eee_current`, `eee_stressed`, `eepe_current`, `eepe_stressed`, `ead_current`, `ead_stressed`, `ead_used`; `k_current`, `k_stressed`, `calibration`, `label`.

## Case inputs (kept for the blind packet)

Grid `(0, 0.25, 0.5, 0.75, 1)` unless stated.

| Case | Inputs |
|---|---|
| str_k-0001 | set A: current `(10, 14, 12, 15, 11)`, stressed `(10, 20, 24, 22, 18)`, `w 0.08`; set B: current `(20, 18, 22, 19, 16)`, stressed `(20, 16, 15, 14, 12)`, `w 0.04` |
| str_k-0002 | as 0001 with set A `w 0.004` (the portfolio choice flips) |
| str_k-0003 | one set, current = stressed `(5, 6, 7, 8, 9)`: tie, current used |
| str_k-0004 | one set, `maturity 0.5`, current `(10, 12, 9, 0, 0)`, stressed `(10, 15, 11, 0, 0)` |
| str_k-0005 | as 0001 with `alpha 1.25`, `own_alpha true` |
| str_k-0006 | monthly grid to one year, current `ee_k = 100 sqrt(t_k)`, stressed `ee_k = 150 sqrt(t_k)`, one set |
| str_k-0007, 0008 | ORE cases, see "Outside-check design" |

<!-- strip:begin -->
## Worked examples

**str_k-0001.** Set A current: Effective EE `(10, 14, 14, 15, 15)`, Effective EPE `(14 + 14 + 15 + 15) x 0.25 = 14.5`, EAD `20.3`; stressed `(10, 20, 24, 24, 24)`, EEPE 23, EAD 32.2. Set B current `(20, 20, 22, 22, 22)`, EEPE 21.5, EAD 30.1; stressed `(20, 20, 20, 20, 20)`, EEPE 20, EAD 28. Capital proxies: current `0.08 x 20.3 + 0.04 x 30.1 = 2.828`; stressed `0.08 x 32.2 + 0.04 x 28 = 3.696`. The portfolio uses the stressed calibration, so set B is carried at 28 even though its own stressed EEPE is lower than its current one: CRE53.7 says the choice is not made counterparty by counterparty.

**str_k-0002.** `w_A = 0.004`: current `0.004 x 20.3 + 0.04 x 30.1 = 0.0812 + 1.204 = 1.2852`, stressed `0.004 x 32.2 + 0.04 x 28 = 0.1288 + 1.12 = 1.2488`; the portfolio now uses the current calibration, and set A is carried at its current 20.3 although its own stressed EAD is 59% higher. The switch point: with B fixed, stressed wins when `w_A x 11.9 > 0.04 x 2.1`, that is `w_A > 0.0070588`.

## Golden cases (designed 2026-11-19; not yet frozen)

| Case | Expected | Outside check |
|---|---|---|
| str_k-0001 | eepe A 14.5 / 23; B 21.5 / 20; ead_used A 32.2, B 28; k_current 2.828; k_stressed 3.696; calibration stressed | B |
| str_k-0002 | k_current 1.2852; k_stressed 1.2488; calibration current; ead_used A 20.3, B 30.1 | B |
| str_k-0003 | calibration current (tie) | B |
| str_k-0004 | horizon 0.5: eepe current `(12 + 12) x 0.25 / 0.5 = 12`, stressed 15 | B |
| str_k-0005 | ead scaled by 1.25 | B |
| str_k-0006 | oracle | B |
| str_k-0007, 0008 | exact undiscounted EE by G-42 quadrature (current `sigma`, stressed `sigma`) | O |
<!-- strip:end -->

## Errors (order KR-175)

`E_SCHEMA`: missing field, wrong type. Structural `E_INPUT`: profile length not `m + 1`; duplicate set ids; `maturity` below 1 that is not a grid point; grid not starting at 0. `E_DOMAIN`: negative EE; `w < 0`; `alpha < 1.2`, or `alpha != 1.4` without `own_alpha`; `maturity <= 0`; grid not increasing; non-finite. Error goldens: str_ke-0001 `alpha 1.3` without `own_alpha` (`E_DOMAIN`); str_ke-0002 `ee_stressed` one value short (`E_INPUT`); str_ke-0003 `alpha "high"` and a negative EE at once (`E_SCHEMA`).

<!-- strip:begin -->
## Acceptance (fixed before any run; proposed, frozen on confirmation)

- A1 Value goldens to 1e-12 relative plus 1e-12 absolute.
- A2 Properties: Effective EE is non-decreasing; EEPE of a non-decreasing profile equals its time average; scaling every stressed profile up never switches the choice from stressed to current; the choice depends on the capital weights only through the two portfolio sums.
- A3 Gate: at least 5 of 8 value cases outside-checked (60% of 8 is 4.8).
<!-- strip:end -->

## Convergence and limit cases

| Method | Asserted order | Measured on | Limit case | Reference |
|---|---|---|---|---|
| Effective EPE on a grid | exact to rounding (a definition, not an approximation) | candidate oracle `str_k` (50 digits, 2026-11-20) | horizon below one year at a grid point (str_k-0004) | KR-168 |
| Undiscounted EE by G-42 quadrature (O cases) | quadrature to 1e-11 relative | not run | `sigma` current equal to stressed: a tie | G-42 |

## Accuracy envelope

Exact arithmetic. The stress calibration itself is the caller's, and it carries all the model risk; this operation only applies the CRE53 rule. The O cases check the place where the rule meets a model: Effective EPE of a simulated profile.

## Outside-check design (registered here before any run)

- **B (6):** str_k-0001 to 0006.
- **O (2), ORE `xva` analytic, `BaselEEPE` column, stage G route:** one G-42b payer swap run twice, `sigma = 0.01` (current) and `sigma = 0.02` (stressed), `a = 0.03`, seeds 20261341, 20261342, 5,000 samples, monthly grid over the first year. Golden: our EEPE from the exact EE. **Precondition, unverified by reading:** ORE's `BaselEEPE` definition (whether its EE is undiscounted, `EE / P(0, t)`, the one-year window and time weights) was not found in the parts of `xva.tex` read; the counting script must not be written until it is read in ORE's documentation or source at the tag, and if ORE's definition differs in a way we cannot match by inputs, the two cases become **none** and the gate is recounted. Check: `|golden - ORE| <= max(3, z_Bonf) SE`, SE from the cube.
- **None:** 0 now (2 if the precondition fails).

## Limits

- No stress-period selection and no stress calibration of `a` and `sigma`; both are the caller's.
- Capital weights are inputs (the credit risk framework is not implemented); the choice uses `sum w EAD`, which equals the capital ratio only when capital is linear in EAD for each counterparty, stated as a simplification.
- No specific wrong-way risk treatment (CRE53.48).
