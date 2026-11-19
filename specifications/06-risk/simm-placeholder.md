# SIMM-structure initial margin on placeholder weights (K-8h)

Spec version 0.1.0. Status: **PROPOSED** (stage K item K-8h, round 2 work started early; spec lane 2026-11-19; nothing implemented, no golden file written). Operation `risk.simm.placeholder`. Rulings KR-130 to KR-141 (`specifications/stage-k-rulings-simm.md`). Parameters `specifications/tables/stage_k/simm-placeholder.json`, written by `tools/gen_simm_placeholder.py` and guarded by `tools/test_simm_placeholder.py`. Blind-lane record and gate note: `program/STAGE_K_BLIND_SIMM.md`.

**Label rule (KR-130, owner decision K-QE).** Every output carries `label`: "placeholder weights; SIMM aggregation structure only; not ISDA SIMM initial margin". Every doc, table, golden, packet and figure that shows a number from this operation says "placeholder weights" next to it. No ISDA parameter value (risk weight, correlation, threshold, scaling constant or quantile) appears anywhere in the repository; the placeholder table holds round numbers chosen by us by a stated rule, and its header says so.

**Plain idea.** Two banks that trade uncleared derivatives post initial margin to each other: collateral sized to cover what the portfolio could lose over the few days it takes to close it out after a default. The industry's standard recipe (ISDA SIMM) does not simulate anything. It takes the portfolio's sensitivities (how much it gains or loses per small move of each rate, price or volatility), multiplies each by a risk weight, and adds them up with correlations, in a fixed order of levels: risk factors into buckets, buckets into a risk class, risk classes into a product class, product classes into one number. Large one-way positions get a concentration add-on. Option books add a vega charge and a curvature charge for the part of the risk that sensitivities miss. This page states that aggregation algebra precisely for a small, complete scope. The weights and correlations are ours and artificial, so the output is a check of the algebra, never a margin number.

## Sources

| Ref | Source | Evidence class | Used for |
|---|---|---|---|
| [SIMM-M] | ISDA SIMM Methodology, a public PDF described in the stage K plan as free. The landing page https://www.isda.org/isda-simm/ returned HTTP 403 to an automated fetch on 2026-11-19; no other isda.org page was tried (the host refuses automated fetches); no click-through, licence or registration screen was seen and none was accepted | **not read** | nothing is quoted; every structural statement about SIMM on this page is **recalled, not read** (see the per-formula table below) |
| [RDS] | ISDA Risk Data Standards (the CRIF file format) | **not read** (same host) | nothing; the input schema below is our own, CRIF-like in shape only |
| [G43] | `specifications/06-risk/xva-framework.md` section `xva.simm.ir_delta` and ruling G-43 (`stage-g-rulings.md`), stage G | read 2026-11-19 | the repository's earlier SIMM-style single-bucket IR delta: `CR = max(1, sqrt(abs(sum s) / T))`, `WS = RW s CR`, `margin = sqrt(max(0, sum sum rho WS WS))`; weights are inputs there |
| [GATE] | `program/STAGE_K_W2_GATE.md`, section "SIMM (K-8h) on placeholder weights" | read 2026-11-19 | outside-check route: blind lane only; no published numbers usable on placeholder weights |
| [ORE-S] | `program/STAGE_K_ORE_SURVEY.md` section 5 and `oracle/LICENCES.md` | read 2026-11-19 | licence position; ORE's SIMM calibration files are not opened or used (owner) |
| [MAR50] | `specifications/06-risk/cva-capital.md` `risk.cva.sa` (Basel MAR50.53, read by the wave 2 lane) | read 2026-11-19 (repository spec) | the clipped-sum pattern `S_b = max(-K_b, min(sum WS, K_b))` and the radicand floor ruling KR-62, reused here as rulings, not as SIMM text |

Per-formula evidence. "Recalled" means the statement is from memory of the public SIMM methodology and was not checked against the document in this lane. A blind match on placeholder weights cannot turn "recalled" into "read" (`program/STAGE_K_BLIND_SIMM.md`, gate note).

| Formula on this page | SIMM methodology | Repository |
|---|---|---|
| F1 netting of identical risk factors | recalled, not read | |
| F2 concentration factor `CR = max(1, sqrt(abs(sum s) / T))` | recalled, not read | read [G43] |
| F3 weighted sensitivity `WS = RW s CR` | recalled, not read | read [G43] |
| F4 intra-bucket `K_b` with `f_kl = min(CR)/max(CR)` | recalled, not read (the `f_kl` factor) | read [G43] for the form without `f_kl` |
| F5 clipped bucket sum `S_b` and inter-bucket aggregation with `g_bc` for IR | recalled, not read | read [MAR50] for the clipping pattern in Basel text (a different framework) |
| F6 residual bucket added outside the root | recalled, not read | |
| F7 vega: `WS = VRW VR VCR`, same aggregation as delta | recalled, not read | |
| F8 curvature: `CVR = SF(t) VR`, `SF(t) = a min(1, d / t)`, squared correlations, `theta`, `lambda = (z^2 - 1)(1 + theta) - theta`, floor at 0 | recalled, not read (the form); the constants `a`, `d`, `z` are placeholders | |
| F9 risk class margin = delta + vega + curvature | recalled, not read | |
| F10 product class `sqrt(sum IM_r^2 + sum psi IM_r IM_s)` | recalled, not read | |
| F11 total = sum over product classes (no diversification across product classes) | recalled, not read | |
| Ruling-only choices (KR-133 to KR-140): radicand floors, `theta` at 0/0, empty input, reporting of absent levels | not a SIMM statement | ours |

## Scope (KR-131)

In scope, completely specified:

| Level | In |
|---|---|
| Product classes | `RatesFX`, `Credit`, `Equity`, `Commodity` as grouping labels; any in-scope risk class may appear under any of them |
| Risk classes | `IR` (interest rate, one curve per currency), `FX`, `EQ` (equity) |
| Margin kinds | IR: delta, vega, curvature. EQ: delta, vega, curvature. FX: delta only |
| Buckets | IR: one bucket per currency. FX: one bucket, key `FX`. EQ: buckets `1`, `2`, `3` and `RESIDUAL` |
| Concentration | delta and vega concentration factors; curvature has none |
| Correlations | within a bucket (tenor matrix for IR, one number per bucket for EQ, one number for FX), across buckets (IR with the `g_bc` concentration ratio, EQ without), across risk classes (`psi`) |

Left out (KR-131), each a deliberate cut to keep the scope completely specified: the Credit Qualifying, Credit Non-Qualifying and Commodity risk classes (so base correlation, which belongs to credit, is out); FX vega and FX curvature; IR sub-curves, inflation and cross-currency basis risk factors; IR and FX currency volatility groups; the historical volatility ratio and any curvature scale factor beyond `SF`; the add-on and product-class multipliers of the SIMM governance framework; posting versus collecting directions and two-way regulatory schedules; FX conversion (every amount is already in the calculation currency); any calibration or risk weight that depends on currency or issuer beyond the placeholder rules.

## Formal statement

Notation: `rc` a risk class, `b` a bucket, `k`, `l` risk factors, `s_k` a net delta amount, `VR_k` a net vega amount, `RW`, `VRW` risk weights, `T`, `VT` thresholds, `rho`, `gamma`, `psi` correlations, all from the placeholder table. `sqrt+(x)` means `sqrt(max(0, x))` (KR-134). `clip(x, K) = max(-K, min(x, K))`.

### Inputs (CRIF-like, our own schema)

| Key | Type | Meaning |
|---|---|---|
| `calculation_currency` | string, three upper-case letters | currency of every amount |
| `records` | array of objects, 0 to 100,000 | sensitivities |
| `records[].trade_id` | string, optional | carried only; never used in a formula |
| `records[].product_class` | `RatesFX` `Credit` `Equity` `Commodity` | |
| `records[].risk_type` | `IR_DELTA` `IR_VEGA` `FX_DELTA` `EQ_DELTA` `EQ_VEGA` | risk class and kind |
| `records[].qualifier` | string; for IR and FX three upper-case letters | IR: curve currency; FX: the currency whose rate moves against the calculation currency; EQ: issuer |
| `records[].bucket` | `1` `2` `3` `RESIDUAL`; required on `EQ_*`, absent on `IR_*` and `FX_*` | equity bucket |
| `records[].label1` | `1W` `1Y` `5Y` `10Y`; required on `IR_DELTA` (tenor), `IR_VEGA` and `EQ_VEGA` (option expiry); absent on `FX_DELTA` and `EQ_DELTA` | |
| `records[].amount` | Real (finite) | `IR_DELTA`, `FX_DELTA`, `EQ_DELTA`: delta amount `s` (change in value for the unit move the caller uses; the algebra is unit-free). `IR_VEGA`, `EQ_VEGA`: vega risk amount `VR`, already the volatility times the derivative of value with respect to it (the caller's) |

The tenor days are those of the placeholder table: `1W` 7, `1Y` 365, `5Y` 1825, `10Y` 3650.

### Step 1: risk factors and netting (F1, KR-132)

Records are grouped by product class first; nothing nets across product classes. Within one product class, a record belongs to the risk factor:

| Risk type | Risk factor key | Bucket | Concentration group |
|---|---|---|---|
| `IR_DELTA` | `qualifier + "|" + label1`, for example `USD|5Y` | `qualifier` (the currency) | the currency |
| `IR_VEGA` | `qualifier + "|" + label1` (currency and expiry) | the currency | the currency |
| `FX_DELTA` | `qualifier` | `FX` | the currency |
| `EQ_DELTA` | `qualifier` (issuer) | `bucket` | the issuer |
| `EQ_VEGA` | `qualifier` (issuer; all expiries of one issuer are one factor) | `bucket` | the issuer |

Delta and vega are kept apart (a delta factor and a vega factor never net). The net amount of a factor is the sum of its records' amounts: `s_k` for delta, `VR_k` for vega.

### Step 2: concentration (F2)

For each concentration group `g` of a risk class and kind, with `T` the delta threshold (IR 100, FX 1000, EQ 100) or `VT` the vega threshold (IR 1000, EQ 1000) of the table:

`CR_g = max(1, sqrt(abs(sum over the factors k of group g of s_k) / T))` (vega: `VR_k` and `VT`).

The sum is signed before the absolute value: offsetting factors of one group reduce concentration. For IR the group is the whole currency, so every factor of one IR bucket has the same `CR`; that common value is also the bucket's `CR_b` used in step 5. `CR_g = 1` exactly when the absolute sum is at most the threshold.

### Step 3: weighted sensitivity (F3, F7)

Delta: `WS_k = RW_k s_k CR_g(k)`, with `RW_k` the IR weight of the factor's tenor `label1`, the FX weight (one number), or the EQ weight of the factor's bucket (the `RESIDUAL` weight for residual factors).
Vega: `WS_k = VRW_rc VR_k CR_g(k)` with the vega weight of the risk class (IR 2, EQ 3) and the vega concentration factor.

### Step 4: within a bucket (F4)

For each non-residual bucket `b`, and separately for the `RESIDUAL` bucket of EQ:

`K_b = sqrt+( sum_k WS_k^2 + sum_{k != l} rho_kl f_kl WS_k WS_l )`, the double sum over ordered pairs (each unordered pair counted twice), with
- `rho_kl`: IR the tenor matrix entry for the two factors' `label1` (vega uses the same matrix on the two expiries); FX the single FX correlation; EQ the within-bucket correlation of bucket `b` (`RESIDUAL` has its own);
- `f_kl = min(CR_g(k), CR_g(l)) / max(CR_g(k), CR_g(l))` with the delta or vega concentration factors of step 2 as the kind requires (equal to 1 for IR, where the two factors share one group).

`sum_ws_b = sum_{k in b} WS_k`; `S_b = clip(sum_ws_b, K_b)` (KR-133).

### Step 5: across buckets, and the residual bucket (F5, F6)

Over the non-residual buckets of one risk class and kind:

`M = sqrt+( sum_b K_b^2 + sum_{b != c} gamma_bc g_bc S_b S_c )` (ordered pairs), with
- `gamma_bc`: IR the single inter-currency correlation; EQ the single inter-bucket correlation; FX has one bucket and no pair;
- `g_bc = min(CR_b, CR_c) / max(CR_b, CR_c)` for IR (with `CR_b` the bucket's common concentration factor of step 2: the delta factor for delta, the vega factor for vega); `g_bc = 1` for EQ.

The margin of the kind is `margin = M + K_residual`, where `K_residual` is the `K_b` of step 4 for the EQ `RESIDUAL` bucket (0 when there is none). The residual bucket takes part in no inter-bucket sum. When the kind has only residual factors, `M = 0`.

### Step 6: curvature (F8)

Curvature is computed from the vega records of IR and EQ, with no risk weight and no concentration factor.

- Scaling: for a vega record with expiry `label1` of `t` days, `SF(t) = a min(1, d / t)` with `a` = `sf_scale` (0.25) and `d` = `sf_days` (20) of the table.
- `CVR_k = sum over the vega records of factor k of SF(t) x amount`. Factors are the vega factors of step 1 (IR: currency and expiry; EQ: issuer, summed over its expiries).
- Within a bucket: `K_b = sqrt+( sum_k CVR_k^2 + sum_{k != l} rho_kl^2 CVR_k CVR_l )` with the vega `rho_kl` of step 4 squared and no `f_kl`. `sum_cvr_b = sum_{k in b} CVR_k`, `S_b = clip(sum_cvr_b, K_b)`.
- Across non-residual buckets: `M_c = sqrt+( sum_b K_b^2 + sum_{b != c} gamma_bc^2 S_b S_c )` with no `g_bc`.
- Non-residual: `sum_cvr = sum of CVR_k over the non-residual factors`; `theta = min(sum_cvr / sum of abs(CVR_k), 0)`, and `theta = 0` when that denominator is 0 (KR-135); `lambda = (z^2 - 1)(1 + theta) - theta` with `z` = 2 from the table (so `lambda = 3 + 2 theta`); `C_non = max(sum_cvr + lambda M_c, 0)`.
- Residual (EQ only), computed the same way on the residual factors alone, with their own `sum_cvr_res`, `theta_res`, `lambda_res`, `K_res` (the residual bucket's `K_b`): `C_res = max(sum_cvr_res + lambda_res K_res, 0)`.
- Curvature margin `= C_non + C_res` (a part with no factors is 0).

### Step 7: risk class (F9)

`IM_rc = delta margin + vega margin + curvature margin`, a kind with no records contributing 0.

### Step 8: product class (F10)

`IM_pc = sqrt+( sum_rc IM_rc^2 + sum_{r != s} psi IM_r IM_s )` over the risk classes present in the product class (ordered pairs), `psi` = 0.2 for every pair.

### Step 9: total (F11)

`total = sum over product classes of IM_pc`. With no records, `total = 0` and `product_classes` is empty (KR-136).

### Outputs

All Reals are binary64 JSON numbers; no rounding.

| Path | Meaning |
|---|---|
| `label` | the KR-130 string |
| `total` | step 9 |
| `product_classes[<pc>].im` | step 8; only product classes with at least one record |
| `product_classes[<pc>].risk_classes[<rc>].im` | step 7; only risk classes with at least one record in that product class |
| `...risk_classes[<rc>].delta`, `.vega` | present only when the kind has records: `margin` (step 5), `buckets[<b>]` {`k_b`, `s_b`, `sum_ws`} for each non-residual bucket with factors, `residual_k` (only when the EQ `RESIDUAL` bucket has factors), `cr[<group>]` (step 2, every group), `ws[<factor key>]` (step 3, every factor) |
| `...risk_classes[<rc>].curvature` | present when `vega` is: `margin` (step 6 total), `cvr[<vega factor key>]`, `buckets[<b>]` {`k_b`, `s_b`, `sum_cvr`} for each non-residual bucket, `sum_cvr`, `theta`, `lambda` (only when non-residual factors exist), `residual` {`k`, `sum_cvr`, `theta`, `lambda`, `margin`} (only when residual factors exist) |

Keys: product classes and risk classes by their enum names; IR buckets by currency, the FX bucket `FX`, EQ buckets `1`, `2`, `3`; factor keys as in step 1; concentration groups by currency (IR, FX) or issuer (EQ). Output order of keys is free.

## Worked example (simm_k-0008)

USD 5Y delta 400 and EUR 5Y delta 900, both under `RatesFX`. Concentration: USD `sqrt(400/100) = 2`, EUR `sqrt(900/100) = 3`. Weighted: USD `30 x 400 x 2 = 24,000`, EUR `30 x 900 x 3 = 81,000`. Each bucket has one factor, so `K_b = abs(WS)` and `S_b = WS`. Across currencies: `gamma g = 0.25 x 2/3 = 1/6`, so `M^2 = 24,000^2 + 81,000^2 + 2 x (1/6) x 24,000 x 81,000 = 576e6 + 6,561e6 + 648e6 = 7,785e6`, `M = 88,232.64701911646`. One risk class, so the product class and the total are the same number (placeholder weights).

## Hand cases (value cases; arithmetic written out)

Placeholder weights throughout. Calculation currency USD unless stated; product class `RatesFX` for IR and FX, `Equity` for EQ, unless stated. Notation: `D` delta amount, `V` vega amount; `ccy tenor amount`. Every case reports all fields of the Outputs table; the line gives the arithmetic and the headline values; full expected values are in the hidden file of the blind packet.

| Case | Input | Arithmetic | Headline values |
|---|---|---|---|
| simm_k-0001 | IR D USD 5Y 2 | CR 1 (2 <= 100); WS 30 x 2 = 60; one factor, K_b = S_b = 60 | margin = im = total 60 |
| simm_k-0002 | IR D USD 1Y 3, USD 10Y -1 | WS 60, -40; rho(1Y,10Y) = 0.8; K^2 = 3,600 + 1,600 + 2 x 0.8 x 60 x (-40) = 1,360; sum_ws 20, S_b 20 (not clipped) | K_b = margin = 36.87817782917155 |
| simm_k-0003 | IR D USD 5Y +5 (T1) and USD 5Y -3 (T2) | one factor, net 2; as 0001 | total 60 |
| simm_k-0004 | IR D USD 5Y 2, EUR 1Y 4 | WS 60, 80; g 1; M^2 = 3,600 + 6,400 + 2 x 0.25 x 60 x 80 = 12,400 | 111.35528725660043 |
| simm_k-0005 | IR D USD 1Y 1, USD 10Y 1, EUR 5Y 2 | USD: WS 20, 40; K^2 = 400 + 1,600 + 2 x 0.8 x 800 = 3,280, K = 57.271284253105414; sum_ws 60 > K so S = K (clipped); EUR K = S = 60; M^2 = 3,280 + 3,600 + 2 x 0.25 x 57.2713 x 60 = 6,880 + 30 sqrt(3,280) | 92.72614802521004 |
| simm_k-0006 | IR D USD 1Y -1, USD 10Y -1, EUR 5Y 2 | as 0005 with USD signs reversed: sum_ws -60, S = -57.271284253105414; M^2 = 6,880 - 30 sqrt(3,280) | 71.84609573530658 |
| simm_k-0007 | IR D USD 1Y 300, USD 5Y 100 | bucket CR = sqrt(400/100) = 2 for both factors; WS 20 x 300 x 2 = 12,000, 30 x 100 x 2 = 6,000; f = 1; rho(1Y,5Y) 0.9; K^2 = 144e6 + 36e6 + 2 x 0.9 x 72e6 = 309.6e6; sum_ws 18,000 > K, clipped | 17,595.453958338217 |
| simm_k-0008 | IR D USD 5Y 400, EUR 5Y 900 | worked example; CR 2 and 3, g_bc 2/3 | 88,232.64701911646 |
| simm_k-0009 | FX D EUR 200, JPY -100 | CR 1 both (<= 1000); WS 1,000, -500; K^2 = 1e6 + 0.25e6 + 2 x 0.5 x 1,000 x (-500) = 0.75e6 | 866.0254037844386; sum_ws 500 |
| simm_k-0010 | FX D EUR 4000, JPY 9000 | CR 2 and 3; WS 5 x 4,000 x 2 = 40,000, 5 x 9,000 x 3 = 135,000; f = 2/3; K^2 = 1.6e9 + 18.225e9 + 2 x 0.5 x (2/3) x 5.4e9 = 23.425e9; sum_ws 175,000 clipped | 153,052.27865013966 |
| simm_k-0011 | IR D USD 5Y 2; FX D EUR 200 | IM_IR 60, IM_FX 1,000; IM^2 = 3,600 + 1e6 + 2 x 0.2 x 60 x 1,000 = 1,027,600 | 1,013.7060717979349 |
| simm_k-0012 | EQ D A bucket 1 3, B bucket 1 -2 | WS 30, -20; rho 0.5; K^2 = 900 + 400 - 600 = 700; sum_ws 10 | 26.457513110645905 |
| simm_k-0013 | EQ D A bucket 2 400, B bucket 2 100 | CR_A 2, CR_B 1 (exactly at the threshold); WS 20 x 400 x 2 = 16,000, 20 x 100 = 2,000; f = 1/2; K^2 = 256e6 + 4e6 + 2 x 0.5 x 0.5 x 32e6 = 276e6; sum_ws 18,000 clipped | 16,613.24772583615 |
| simm_k-0014 | EQ D A bucket 2 300 (T1), A bucket 2 -100 (T2) | net 200; CR sqrt(2) = 1.4142135623730951; WS 20 x 200 x sqrt 2 | 5,656.85424949238 |
| simm_k-0015 | EQ D A bucket 1 5, C bucket 3 -2 | WS 50, -60; M^2 = 2,500 + 3,600 + 2 x 0.25 x 50 x (-60) = 4,600 | 67.82329983125268 |
| simm_k-0016 | EQ D A bucket 1 5; R1 RESIDUAL 2, R2 RESIDUAL -1 | M = 50; residual WS 80, -40, rho_res 0.25; K_res^2 = 6,400 + 1,600 - 2 x 0.25 x 3,200 = 6,400, K_res 80; margin 50 + 80 | 130 |
| simm_k-0017 | EQ D R1 RESIDUAL 3 | residual only: M = 0; K_res = 40 x 3 = 120; no `buckets` entry | 120 |
| simm_k-0018 | IR V USD 1Y 50 | vega: VCR 1, WS 2 x 50 = 100. Curvature: SF(365) = 0.25 x 20/365 = 1/73; CVR = 50/73 = 0.684931506849315; theta 0, lambda 3; C = 4 x 50/73 | vega 100; curvature 2.73972602739726; im 102.73972602739725 |
| simm_k-0019 | IR V USD 1W 20, USD 1Y -730 | vega: sum VR -710, VCR 1; WS 40, -1,460; rho 0.9; K^2 = 1,600 + 2,131,600 - 2 x 0.9 x 58,400 = 2,028,080. Curvature: SF(7) = 0.25 (20/7 > 1, capped at 1); CVR 5, -10; K^2 = 25 + 100 + 2 x 0.81 x (-50) = 44; sum_cvr -5; theta = -5/15 = -1/3; lambda = 3 x 2/3 + 1/3 = 7/3; C = -5 + (7/3) sqrt(44) | vega 1,424.1067375727143; curvature 10.477582354991865; im 1,434.5843199277062 |
| simm_k-0020 | IR V USD 1W -40 | vega WS -80, margin 80. Curvature CVR -10; theta -1; lambda 1; C = max(-10 + 10, 0) = 0 (the floor) | curvature 0; im 80 |
| simm_k-0021 | IR V EUR 5Y 4000 | VCR = sqrt(4,000/1,000) = 2; WS 2 x 4,000 x 2 = 16,000. Curvature SF(1825) = 0.25 x 20/1,825; CVR = 4,000 x 5/1,825 = 10.95890410958904 (no concentration); C = 4 CVR | vega 16,000; curvature 43.83561643835616; im 16,043.835616438357 |
| simm_k-0022 | EQ V A bucket 1 1W 40, A bucket 1 1Y 365; R RESIDUAL 1W 20 | vega: VR_A = 405, WS 3 x 405 = 1,215; residual WS 60; margin 1,215 + 60. Curvature: CVR_A = 0.25 x 40 + (1/73) x 365 = 15, C_non = 4 x 15 = 60; CVR_R = 5, C_res = 4 x 5 = 20 | vega 1,275; curvature 80; im 1,355 |
| simm_k-0023 | IR D USD 5Y 2; IR V USD 1Y 50 | delta 60 (0001) + vega 100 + curvature 1,000/365 (0018) | im 162.73972602739727 |
| simm_k-0024 | IR D USD 5Y 2 (RatesFX); EQ D A bucket 1 5 (Equity) | product classes 60 and 50, summed | total 110 |
| simm_k-0025 | IR D USD 5Y 2 (RatesFX); IR D USD 5Y -2 (Equity) | no netting across product classes: 60 + 60 | total 120 |
| simm_k-0026 | all under Equity: EQ D A bucket 1 5; FX D EUR 200; IR D USD 5Y 2 | IM 50, 1,000, 60; IM^2 = 2,500 + 1e6 + 3,600 + 2 x 0.2 x (60,000 + 3,000 + 50,000) = 1,051,300 | 1,025.3292154230269 |
| simm_k-0027 | IR D USD 5Y +2 (T1), USD 5Y -2 (T2) | net 0; CR 1; WS 0; K_b 0 | total 0 |
| simm_k-0028 | no records | KR-136 | total 0 |
| simm_k-0029 | calculation currency EUR; FX D USD 500 | CR 1; WS 2,500 | 2,500 |

Error cases (not value cases; for the goldens, not for the blind packet): simm_ke-0001 `risk_type` `CR_DELTA` (`E_SCHEMA`); simm_ke-0002 `EQ_DELTA` without `bucket` (`E_INPUT`); simm_ke-0003 `FX_DELTA` qualifier equal to the calculation currency (`E_INPUT`); simm_ke-0004 amount NaN (`E_DOMAIN`, finite rule); simm_ke-0005 `label1` `3Y` and amount Infinity in one input (two errors at once: `E_SCHEMA` first); simm_ke-0006 issuer A in bucket 1 and bucket 2 within one product class (`E_INPUT`).

Value cases 29. Branches exercised: single factor (0001); two factors in a bucket (0002, 0012); netting with signs (0003, 0014, 0027); two buckets (0004, 0015); clipping positive and negative (0005, 0006, 0007, 0010, 0013); concentration below, at and above the threshold (0001, 0013, 0007, 0014); `f_kl` (0010, 0013); `g_bc` (0008); residual with and without other buckets (0016, 0017, 0022); vega with and without concentration (0018, 0021); curvature with `SF` capped and uncapped, negative `theta`, the zero floor (0019, 0020); two risk classes and three (0011, 0026); two product classes (0024, 0025); zero and empty (0027, 0028); another calculation currency (0029).

## Errors (order KR-139 = KR-67 = HR-122)

`E_SCHEMA`: missing `calculation_currency` or `records`; a record that is not an object; a missing or mistyped key; `product_class`, `risk_type`, `bucket` or `label1` outside its enum; a currency that is not three upper-case letters; an unknown key in a record. `E_LIMIT`: more than 100,000 records. Finite rule: a non-finite `amount` is `E_DOMAIN`. Structural `E_INPUT`: `label1` missing where required or present where it must be absent; `bucket` missing on an `EQ_*` record or present on an `IR_*` or `FX_*` record; an `FX_DELTA` qualifier equal to the calculation currency; one issuer in two buckets within one product class (delta and vega together). `E_DOMAIN`: none beyond the finite rule (every finite amount is valid, of either sign).

## Acceptance (fixed before any run; proposed, frozen on confirmation)

- A1 Every value golden in all four builds to 1e-12 relative (1e-15 absolute at 0), KR-67.
- A2 Properties: scaling every amount by `c > 0` with all thresholds scaled by `c` scales every margin by `c`; with every `CR = 1`, scaling by any `c` scales every delta and vega margin by `abs(c)`; `abs(S_b) <= K_b`; curvature margin >= 0; `IM_pc <= sum_rc IM_rc` (as `psi <= 1`); total equals the sum of product classes.
- A3 Gate: 60% of the 29 value cases outside-checked. No published or library check exists on placeholder weights ([GATE]); the only route is the blind lane of `program/STAGE_K_BLIND_SIMM.md` (eligible 28, matches needed 18). Below that, K-8h moves to a point release (owner).

## Limits

- Placeholder weights only (KR-130). The output is not ISDA SIMM initial margin and must not be used to call or post margin.
- The aggregation algebra is recalled, not read (Sources). A blind match shows our statement is unambiguous and our arithmetic consistent, not that the algebra equals ISDA's methodology.
- Sensitivities are inputs; no pricing or bump engine is attached. Units are the caller's: the formulas are unit-free given consistent amounts and thresholds.
- The scope cuts of KR-131 apply: no credit, commodity, FX vega or curvature, sub-curves, inflation, basis, volatility groups, historical volatility ratio, add-ons, multipliers or regulatory schedules.
- The radicand floors (KR-134) are rulings; no case reaches a negative radicand.
