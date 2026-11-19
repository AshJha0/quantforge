# Netting sets with margin period of risk, variation margin and initial margin

Spec version 0.1.0. Status: **PROPOSED** (stage K item K-8b; xVA spec lane 2026-11-19; nothing implemented, no golden file written). Rulings `stage-k-rulings-xva.md` KR-169, KR-170, KR-173 to KR-176; stage G G-40, G-42b. Gate: `program/STAGE_K_XVA_GATE.md`.

**Plain idea.** Under a CSA the counterparty posts variation margin (VM) as the trades move, so the bank's exposure should be small. It is not zero, because after the last margin call is met the counterparty can stop paying and the bank needs some days (the margin period of risk, MPoR) to notice the default, argue, and close out. Over those days the trades keep moving and the collateral does not. Initial margin (IM) is a second buffer, posted up front and held apart, sized to cover most of that move. This page gives (1) the supervisory minimum length of the MPoR from the Basel text, (2) the exposure on given paths with VM, IM and the MPoR lag, and (3) a closed form for one normal factor, which shows how large the residual exposure is and how much IM removes.

## Sources

| Ref | Source | Evidence class | Used for |
|---|---|---|---|
| [CRE53] | Basel Framework CRE53.22-53.26, PDF pp. 468-469 (PDF of 11/11/2026) | read 2026-11-19 | MPoR floors 5, 10, 20 business days; doubling after disputes; `F + N - 1` |
| [ORE-X] | ORE User Guide `methods/xva.tex`, collateral (VM) model: CSA amount with thresholds and IA, MTA on the delivery, collateral at default `CSA(t_d - tau)`, close-out grid | read 2026-11-19 | the ORE convention the O cases compare with |
| [ORE-E] | ORE examples `ExposureWithCollateral` (MPoR grid, close-out grid, first-MPoR adjustment) | read 2026-11-19 | which configuration flags exist |
| [APS16] | Andersen, Pykhtin, Sokol (2016) | **not read** (SSRN 403) | nothing taken |
| G-40 | `xva.exposure.collateralised` | read (repo) | VM mechanics, lag in grid steps |

## Formal statement

### `xva.mpor.days` (KR-169)

Inputs: `repo_only` (bool), `max_trades_last_quarter` (integer `>= 0`), `illiquid` (bool: illiquid collateral or a hard-to-replace OTC derivative, as CRE53.24(2)), `long_disputes_last_two_quarters` (integer `>= 0`), `remargin_days` `N` (integer `>= 1`), optional `model_mpor_days`. Steps: `F = 5` if `repo_only` else 10; `F = 20` if `max_trades_last_quarter > 5000` or `illiquid`; `F = 2F` if `long_disputes_last_two_quarters > 2`; `floor = F + N - 1`. Outputs `floor_days`, and with `model_mpor_days`: `mpor_days = max(model_mpor_days, floor_days)`, `binding` (true when the floor is used).

### `xva.exposure.closeout` (KR-170)

Inputs: G-40 inputs (`times`, `trades` with path values, `csa` per netting set with `mpor_steps`), plus per netting set optional `im_received` and `im_posted`: either a profile (one value per date, applied on every path) or per-path values. Collateral at `t_i`: `VM_p(t_(i-l))` from G-40, `IM_p(t_(i-l))` likewise lagged. Exposure `E = max(V - VM - IM_received, 0)`; negative exposure `N = min(V - VM + IM_posted, 0)` (posted IM is returned on our default only after the counterparty's claim; it enters ENE, a stated choice). Outputs per set as G-40 (`ee`, `ene`, `pfe`, `epe`, `effective_epe`) plus `ee_no_im` for comparison.

### `xva.exposure.closeout_normal` (KR-170)

Inputs: `v0` (netted value at the last good margin call), `sigma` (`> 0`, annualised standard deviation of the netted value), `mpor_days` (business days, `> 0`), `days_per_year` (default 250), `threshold_receive` `H >= 0`, `im` `>= 0` or `im_quantile` `q in (0.5, 1)` (then `IM = Phi^-1(q) s`). `s = sigma sqrt(mpor_days / days_per_year)`; `VM = max(v0 - H, 0)`; `m = v0 - VM - IM`; `ee = m Phi(m/s) + s phi(m/s)`. Outputs `s`, `vm`, `im`, `ee`. With `v0 <= 0` the bank holds no VM (it may have posted; that is ENE) and `m = v0 - IM`.

## Case inputs (kept for the blind packet)

| Case | Operation | Inputs |
|---|---|---|
| mpor_k-0001 | days | repo_only, 10 trades, liquid, 0 disputes, N 1 |
| mpor_k-0002 | days | not repo, 10 trades, liquid, 0 disputes, N 1 |
| mpor_k-0003 | days | not repo, 10 trades, liquid, 0 disputes, N 5 |
| mpor_k-0004 | days | not repo, 6,000 trades, liquid, 0 disputes, N 1 |
| mpor_k-0005 | days | not repo, 10 trades, liquid, 3 disputes, N 1 |
| mpor_k-0006 | days | not repo, 10 trades, illiquid, 3 disputes, N 3, model_mpor_days 15 |
| cln_k-0001 | normal | `v0 5e6`, `sigma 1e6`, 10 days, `H 0`, `im 0` |
| cln_k-0002 | normal | `v0 5e6`, `sigma 1e6`, 10 days, `H 1e6`, `im 0` |
| cln_k-0003 | normal | `v0 5e5`, `sigma 1e6`, 10 days, `H 1e6`, `im 0` |
| cln_k-0004 | normal | `v0 5e6`, `sigma 1e6`, 10 days, `H 0`, `im_quantile 0.99` |
| cln_k-0005 | normal | `v0 5e6`, `sigma 1e6`, 10 days, `H 1e6`, `im_quantile 0.99` |
| clp_k-0001 | paths | `collexp_g-0004` paths and CSA, `im_received` profile `(0, 0.5, 0.5, 0.5, 0.5)` |
| clp_k-0002, 0003 | paths | ORE cases, see "Outside-check design" |

<!-- strip:begin -->
## Worked examples

**MPoR floors.** Daily margining of an OTC set: `F = 10`, `N = 1`, floor 10 (mpor_k-0002). Weekly margining (`N = 5`): 14 (mpor_k-0003). More than two long disputes: the floor doubles before `N - 1` is added: 20 (mpor_k-0005). Illiquid collateral and disputes with margining every 3 days: `F = 20`, doubled 40, plus 2: 42 (mpor_k-0006); the model's 15 days are below the floor, so `binding: true`, `mpor_days 42`.

**cln_k-0001.** `s = 1e6 sqrt(10/250) = 200,000`. Zero threshold: VM = v0, so `m = 0` and `ee = s phi(0) = s / sqrt(2 pi) = 79,788.45608028655`. Even with perfect daily VM, ten days of unmargined moves leave an expected exposure of 8% of one year's standard deviation.

**cln_k-0004.** `IM = Phi^-1(0.99) x 200,000 = 465,269.5748081682`; `m = -465,269.57`; `ee = m Phi(m/s) + s phi(m/s) = 677.732692609934`: a 99% IM removes 99.15% of the residual expected exposure.

**cln_k-0002.** Threshold 1e6: VM `4e6`, `m = 1e6 = 5 s`, `ee = 1,000,000.010692331` (the threshold is almost all exposure; the MPoR move adds 0.01).

## Golden cases (designed 2026-11-19; not yet frozen)

| Case | Expected | Outside check |
|---|---|---|
| mpor_k-0001 | floor 5 | B |
| mpor_k-0002 | floor 10 | B |
| mpor_k-0003 | floor 14 | B |
| mpor_k-0004 | floor 20 | B |
| mpor_k-0005 | floor 20 | B |
| mpor_k-0006 | floor 42; mpor_days 42; binding true | B |
| cln_k-0001 | ee 79788.45608028655 | **L** (SciPy `quad` of `E[max(m + s Z, 0)]`: 79788.45608028653) |
| cln_k-0002 | ee 1000000.010692331 | **L** (1000000.0106923312) |
| cln_k-0003 | vm 0; m 5e5; ee 500400.8274358256 | **L** (500400.8274358257) |
| cln_k-0004 | im 465269.5748081682; ee 677.732692609934 | **L** (677.7326926099279) |
| cln_k-0005 | ee 534961.4566317102 | **L** (534961.4566317102) |
| clp_k-0001 | oracle, exact arithmetic on the paths | B |
| clp_k-0002, 0003 | two-dimensional Gaussian quadrature (below) | O |
<!-- strip:end -->

L values measured 2026-11-19 with SciPy `integrate.quad` of the defining integral `int max(m + s z, 0) phi(z) dz` from `-m/s` to 12 (a different formulation from the closed form; relative agreement 1e-14 or better).

## Errors (order KR-175)

`E_SCHEMA`: missing field, wrong type (a boolean given as a number). Structural `E_INPUT`: `im_received` profile length not equal to the grid; per-path IM with a path count differing from the trades'; both `im` and `im_quantile`. `E_DOMAIN`: `sigma <= 0`; `mpor_days <= 0`; `N < 1`; negative trade or dispute counts; `H < 0`; `im < 0`; `q` outside `(0.5, 1)`; non-finite. Error goldens: mpor_ke-0001 `remargin_days 0` (`E_DOMAIN`); cln_ke-0001 both `im` and `im_quantile` (`E_INPUT`); cln_ke-0002 `sigma "high"` and `mpor_days -1` at once (`E_SCHEMA`).

<!-- strip:begin -->
## Acceptance (fixed before any run; proposed, frozen on confirmation)

- A1 Value goldens to 1e-12 relative plus 1e-9 absolute (`simple_analytic`; the normal CDF to 1e-15 as the house `Phi`).
- A2 Properties: `ee` is non-increasing in `im`, non-decreasing in `H`, non-decreasing in `mpor_days`; `im = 0`, `H = 0` gives `s / sqrt(2 pi)`; the path form with `im_received = 0` equals G-40.
- A3 Gate: at least 8 of 13 value cases outside-checked (60% of 13 is 7.8).
- A4 AAD of `ee` with respect to `sigma`, `im`, `H`, `v0` (`d ee / d im = -Phi(m/s)`) to KR-161.
<!-- strip:end -->

## Accuracy envelope (plan 14.10 rule 4)

The closed form assumes the netted value moves as one normal increment over the MPoR with no cash flow inside the window. It is exact under that assumption. At the edges: `m/s` large negative (deep IM cover, cln_k-0004) the result is a tail of size 1e-3 of `s`, where cancellation in `m Phi + s phi` would lose digits; builds evaluate `s (phi(k) + k Phi(k))` with `k = m/s` through `erfcx` for `k < -5` (stated; a golden at `k = -6` is added by the oracle lane). `m/s` large positive: `ee -> m`, cln_k-0002. The O cases check the path form at the realistic edge, a swap with VM and an MPoR of two weeks.

## Outside-check design (registered here before any run)

- **B (7):** mpor_k-0001 to 0006 (rules from CRE53), clp_k-0001.
- **L (5, measured):** cln_k-0001 to 0005.
- **O (2), ORE `xva` with VM, stage G route:** two G-42b single payer swaps (`a = 0.03`, `sigma = 0.01`), CSA threshold 0, MTA 0, `MarginPeriodOfRisk 2W`, close-out grid with `CloseOutLag 2W`, `MporMode StickyDate`, `calculationType NoLag`, `mporCashFlowMode NonePay`; exposure dates chosen so no swap cash flow falls in any close-out window. Golden: `E^N[max(V(t) - V(t - 14/365), 0) / N(t)]` in the LGM coordinates, a two-dimensional Gaussian integral (`x(t - mpor)` and the increment), quadrature to 1e-9 relative. Seeds 20261331, 20261332, 5,000 samples. Count: EE at every exposure date within `max(3, z_Bonf) SE`. Sticky-date versus actual-date valuation changes the value at the close-out date by the model's drift over two weeks only through the numeraire; the debug run on a demo case (KR-174) decides which of the two golden forms (sticky: `V(t; x(t))` with market date frozen at `t - mpor`; actual: market date `t`) matches ORE's documented definition, and the choice is recorded before the counted runs.
- **None:** 0.

## Limits

- No dispute modelling beyond the CRE53.25 count; no settlement risk on margin flows; no wrong-way collateral.
- IM is given or projected (`xva-mva-im.md`); the project's placeholder initial margin model is not called here.
- "Business days" are counted by the caller; no holiday calendar.
