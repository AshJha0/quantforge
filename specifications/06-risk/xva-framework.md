# xVA framework on given paths: collateral, netting, adjustments, SIMM-style margin, wrong-way risk

Spec version 1.0.0. Status: Specified (stage G, wave 4b). Rulings: `stage-g-rulings.md` G-40 to G-44. Suites `stage_g/collexp_g` (17), `xvaadj_g` (12), `simm_g` (8), `wwr_g` (6), written by `oracle/python/gen_stage_g_w4b.py`.

**Plain idea.** A bank's loss if a counterparty defaults depends on the whole relationship with that counterparty, not on one trade. Trades under one legal netting agreement offset each other. Under a credit support annex (CSA), collateral changes hands when the netted value moves past a threshold, but only in steps of at least the minimum transfer amount, and after a default it takes some days (the margin period of risk, MPoR) before the position can be closed out, so the collateral held lags the exposure. This page takes simulated values as **inputs**, so every formula can be checked exactly. It then turns exposure profiles into the valuation adjustments: CVA (counterparty default), DVA (own default), FVA (funding), MVA (funding initial margin), KVA (holding capital). It adds a SIMM-style initial margin for interest-rate delta and the Hull-White wrong-way-risk model. The simulation that produces the paths, and its check against ORE, is the separate wave 4c slice.

Sources (none opened in this session; pointers, as G-34):
- [G15] J. Gregory, *The xVA Challenge*, 3rd ed., Wiley, 2015: chapters on netting, collateral (thresholds, MTA, independent amount, MPoR), exposure metrics (EE, ENE, PFE, EPE), CVA, DVA, FVA, MVA, KVA.
- [GK14] A. Green, C. Kenyon, "MVA: initial margin valuation adjustment by replication and regression", *Risk*, 2015; and A. Green, C. Kenyon, C. Dennis, "KVA: capital valuation adjustment", *Risk*, December 2014.
- [BCBS] Basel Committee, *The Basel Framework*, CRE53 (internal model method: EE, effective EE, effective EPE over the first year).
- [SIMM] ISDA SIMM methodology (weighted sensitivity `WS = RW s CR`, concentration risk factor, aggregation `K = sqrt(sum WS^2 + sum rho WS WS)`). The weights and correlations here are **inputs**, not a SIMM calibration (G-43).
- [HW12] J. Hull, A. White, "CVA and wrong-way risk", *Financial Analysts Journal* 68(5), 2012: hazard `exp(a(t) + b V(t))`.
- [BM] D. Brigo, M. Morini, A. Pallavicini, *Counterparty Credit Risk, Collateral and Funding*, Wiley, 2013: first-to-default weighting and the DVA/FBA overlap.

## `xva.exposure.collateralised` (ruling G-40)

Inputs: `times` `t_0 < ... < t_n` (at least two, increasing, else `E_INPUT`); `trades`, at least one, each `{netting_set, values}` with `values` a list of paths, each of length `n + 1` (else `E_INPUT`); `csa`, optional, from netting-set name to `{threshold_receive, threshold_post, minimum_transfer_amount, mpor_steps, independent_amount (optional, default 0)}` (thresholds and MTA `>= 0`, `mpor_steps` an integer `>= 0`, else `E_DOMAIN`; a name with no trades is `E_INPUT`); `pfe_quantile` `q` in `(0, 1]` (else `E_DOMAIN`). All trades of a set have the same number of paths.

Formal statement. Per set, `V_p(t_i)` is the sum of its trades' values on path `p`. With a CSA: target collateral `T(V) = max(V - H_r, 0) - max(-V - H_p, 0) + IA`; calls `K_0 = T(V_0)`, `K_j = T(V_j)` if `|T(V_j) - K_(j-1)| >= MTA`, else `K_(j-1)`; collateral held `C_i = K_(max(i - l, 0))` with `l = mpor_steps`. Without a CSA, `C = 0`. Exposure `E = max(V - C, 0)`, negative exposure `N = min(V - C, 0)` [G15].

Outputs per set (in code-point order of names): `ee_i = mean_p E`, `ene_i = mean_p N`, `pfe_i` = the `ceil(q P)`-th smallest `E` (the inverted-CDF rule of stage F), `epe = sum_(i>=1) ee_i (t_i - t_(i-1)) / (t_n - t_0)`, `effective_epe`: with `eee_i = max(eee_(i-1), ee_i)` (`eee_0 = ee_0`), the same time average over the grid points within one year of `t_0` [BCBS CRE53]. `total_ee`: the sum over sets (no netting across sets).

Worked example (`collexp_g-0001` and `-0004`). Four paths, quarterly to one year, no CSA: `ee = (0, 1.125, 2.75, 3.375, 2.75)`, `epe = 2.5`, PFE at 75% at 0.75 years is 2.5 (exposures 2, 0, 9, 2.5 sorted, third). Add a CSA with thresholds 1, MTA 0.5, MPoR one step: `epe` falls to 1.71875; with no lag (`-0005`) it falls further, and with zero thresholds and no lag (`-0007`) the exposure is 0.

## `xva.adjustments.value` (ruling G-41)

Inputs: `times` `t_1 < ... < t_n` (buckets from 0), `discount_factors`, `ee` (`>= 0`), `ene` (`<= 0`) (all length `n`, else `E_INPUT`; signs else `E_DOMAIN`); `counterparty` and `own` `{hazard_rate >= 0, recovery in [0, 1)}` (else `E_DOMAIN`); `funding` `{borrow_spread, lend_spread, exclude_dva_overlap}`; optional `im` with `im_spread`, optional `capital` with `hurdle_rate` (each pair together, else `E_INPUT`).

Formal statement, buckets `(t_(i-1), t_i]`, exposure at the bucket end, `S_c`, `S_b` the survival curves `e^(-h t)`, both names alive at the bucket start for the first-to-default weight [BM]:
- `CVA = (1 - R_c) sum D_i ee_i (S_c(t_(i-1)) - S_c(t_i)) S_b(t_(i-1))`; `DVA = (1 - R_b) sum D_i |ene_i| (S_b(t_(i-1)) - S_b(t_i)) S_c(t_(i-1))`;
- `FCA = s_b sum D_i ee_i S_c S_b(t_(i-1)) dt_i`, `FBA = s_l sum D_i |ene_i| S_c S_b(t_(i-1)) dt_i`, `FVA = FCA - FBA`. **Overlap (G-41):** with `exclude_dva_overlap`, `s_l` is replaced by `max(s_l - h_b (1 - R_b), 0)`, removing the part of the lending benefit that is the bank's own credit spread and is already in DVA;
- `MVA = s_IM sum D_i IM_i S_c S_b dt_i`; `KVA = hurdle sum D_i capital_i S_c S_b dt_i` [GK14].

Worked example (`xvaadj_g-0001`): CVA 2.7099, DVA 0.8998, FCA 1.8156, FBA 1.2027, FVA 0.6129. Excluding the overlap (`-0002`, `h_b = 1%`, `R_b = 40%`, `s_l = 0.8%`) leaves a lending spread of 0.2%, and FBA falls to 0.3007.

## `xva.simm.ir_delta` (ruling G-43)

Inputs: `sensitivities` `s_k`, `risk_weights` `RW_k >= 0`, `correlations` `rho_kl` in `[-1, 1]` (square, same length; else `E_INPUT` / `E_DOMAIN`), `concentration_threshold` `T > 0`.

Formal statement [SIMM]: `CR = max(1, sqrt(|sum s_k| / T))`, `WS_k = RW_k s_k CR`, `margin = sqrt(max(0, sum_k sum_l rho_kl WS_k WS_l))` (`rho_kk = 1`). Outputs `weighted_sensitivities`, `concentration_factor`, `margin`.

Worked example: `simm_g-0002`, one bucket, `s = 10,000`, `RW = 90`: margin 900,000. `simm_g-0001` (mixed signs, tenor correlation `exp(-0.3 |ln(T_k/T_l)|)`): 452,205.34.

## `xva.wwr.cva_hw` (ruling G-44)

Inputs: `times` `t_1 < ... < t_n`, `values` (paths of length `n`, the exposure at bucket ends), `discount_factors`, `hazard_rate` `h > 0` (else `E_DOMAIN`), `recovery`, `wwr_b`.

Formal statement [HW12]: on path `p` the hazard in bucket `i` is `exp(a_i + b V_p(t_i))`; `a_i` solves `mean_p S_p(t_i) = e^(-h t_i)` given the path survivals `S_p(t_(i-1))` (one root per bucket, strictly monotone in `a`); `CVA = (1 - R) sum D_i mean_p[max(V_p(t_i), 0) (S_p(t_(i-1)) - S_p(t_i))]`. Outputs `cva` and `a`.

Worked example: CVA 0.04363 with `b = 0` (equal to the independent bucket CVA on the path-mean EE, asserted), 0.06115 at `b = 0.1`, 0.08649 at `b = 0.3` (wrong way), 0.01557 at `b = -0.2` (right way).

## Tolerances and outside share

1e-9 absolute plus 1e-12 relative (`root_finding` class for `wwr_g`). Outside: none (formulas on given inputs; G-40). The simulated slice (wave 4c) carries the ORE comparison.

## Convergence and limit cases

| Method | Asserted order | Measured on | Limit case | Reference |
|---|---|---|---|---|
| Exposure statistics | exact | `collexp_g` | zero thresholds, MTA 0, no lag: exposure 0 (asserted) | definition |
| Adjustments | exact | `xvaadj_g` | own hazard 0: DVA 0 (asserted) | definition |
| WWR `a(t)` root | 1e-40 in the oracle; builds to 1e-14 relative | `wwr_g` | `b = 0`: independent CVA (asserted) | [HW12] |
