# MVA from projected initial margin

Spec version 0.1.0. Status: **PROPOSED** (stage K item K-8b; xVA spec lane 2026-11-19; nothing implemented, no golden file written). Rulings `stage-k-rulings-xva.md` KR-160, KR-164 to KR-166, KR-173 to KR-176; stage G G-41. Gate: `program/STAGE_K_XVA_GATE.md`. Plan 15.2 change log (owner 2026-11-19): MVA is computed from caller-supplied or project-defined initial margin, not from any ISDA model.

**Plain idea.** Initial margin a bank posts is locked away: it must be funded at the bank's borrowing spread and earns only what the custodian pays on it. Over the life of the netting set that difference, times the margin expected to be posted in each period, is a cost: MVA. The hard part is not the sum but the margin profile: how much IM will be posted in five years, on each simulated path? This page fixes the sum (as ORE writes it) and three ways to get the profile: the caller gives it; it comes from a normal MPoR move (a quantile of a normal increment); or it is regressed on simulated paths, the method ORE calls regression DIM. A fourth way, the project's placeholder initial margin model applied on each path, is reserved until that model's operation id is fixed.

## Sources

| Ref | Source | Evidence class | Used for |
|---|---|---|---|
| [GK14] | Green and Kenyon, arXiv:1405.0508v2, p. 7 eq. 37 (MVA as an integral over the expected IM profile of `(1 - R_B) lambda_B - s_I`, discounted at `r + lambda_B + lambda_C`); Section 3.2 (IM by regression on simulated states) | read 2026-11-19 | the quantity; the regression idea |
| [ORE-X] | ORE User Guide `methods/xva.tex`, "Dynamic Initial Margin and MVA": `MVA = sum (f_b - s_I) delta_i S_C(t_i) S_B(t_i) E^N[DIM(t_i) D(t_i)]`; regression DIM `alpha sqrt(E_t[X^2] - E_t^2[X])`, `X` the netted value change over the MPoR, `E_t[X]` replaced by the across-path mean, polynomial regression on a market variable; "it needs benchmarking/validation" | read 2026-11-19 | the discrete formula and the regression method, as written |
| [ORE-P] | `ore.tex`: `dimModel` (`Regression` or `Flat`), `dimQuantile`, `dimHorizonCalendarDays`, `dimRegressionOrder`, `dimRegressors` | read 2026-11-19 | the ORE inputs |
| the project's placeholder initial margin model | branch `k-simm-spec`, being renamed | not used | **TODO: final operation id (KR-160)** |

## Formal statement

### `xva.mva.value` (KR-165)

Inputs: `times` `t_1 < ... < t_n` (from `t_0 = 0`); `discount_factors`; `expected_im` `IM_i >= 0` (from `xva.im.project` or the caller); `borrow_curve` (KR-164) or `borrow_spread` (flat); `im_spread` `s_I`; `counterparty`, `own` hazards. `MVA = sum_i (f_b,i - s_I) delta_i S_C(t_i) S_B(t_i) D_i IM_i`. Outputs `mva`, `terms`.

### `xva.im.project` (KR-166)

- `GIVEN`: returns the input profile.
- `NORMAL_MPOR`: inputs `stdev` `sigma_i > 0` (annualised), `mpor_days`, `days_per_year` (default 250), `quantile` `q` (default 0.99). `IM_i = Phi^-1(q) sigma_i sqrt(mpor_days / days_per_year)`.
- `REGRESSION`: inputs per date `regressor` `x_p` and `increment` `X_p` (the caller's netted value change over the MPoR on path `p`; the values are "simulated"), `order` `n >= 0`, `quantile` `q`. Least squares of `X_p^2` on `(1, x_p, ..., x_p^n)` (QR); `IM_p = Phi^-1(q) sqrt(max(fit_p - mean_p(X)^2, 0))`; outputs per-path `im` and `expected_im` = path mean. Order 0 gives one IM for all paths, `Phi^-1(q) sqrt(mean(X^2) - mean(X)^2)` (population variance).
- `PLACEHOLDER_MODEL`: `E_INPUT` "the project's placeholder initial margin model is not wired yet" until KR-160's TODO is closed.

## Case inputs (kept for the blind packet)

Common for MVA cases: `times (0.5, 1, 1.5, 2)`, `discount_factors (0.985, 0.97, 0.955, 0.94)`, `h_C 0.02`, `h_B 0.01`, `borrow_spread 0.008`, `im_spread 0.001`.

| Case | Inputs |
|---|---|
| mva_k-0001 | `GIVEN` `(100, 90, 70, 40)` |
| mva_k-0002 | `NORMAL_MPOR`, `sigma (1000, 1200, 900, 500)`, 10 days, `q 0.99` |
| mva_k-0003 | `REGRESSION` at one date: `x (-1, -0.5, 0, 0.5, 1, 1.5)`, `X (3, -2, 1, -1, 2, -4)`, order 1, `q 0.99` (IM output only) |
| mva_k-0004 | as 0003 with order 0 |
| mva_k-0005 | `GIVEN` as 0001, `borrow_curve` of `fva_k-0004` instead of the flat spread |
| mva_k-0006, 0007 | ORE `dimModel Flat`, see "Outside-check design" |
| mva_k-0008 .. 0010 | ORE `dimModel Regression`, see "Outside-check design" |

<!-- strip:begin -->
## Worked examples

**mva_k-0001.** `(f_b - s_I) = 0.007`, `delta = 0.5`, survival at bucket ends `exp(-0.03 t_i)`: terms `0.007 x 0.5 x 0.98511 x 0.985 x 100 = 0.33961`, `... x 0.97045 x 0.97 x 90 = 0.29652`, `... x 0.95600 x 0.955 x 70 = 0.22367`, `... x 0.94176 x 0.94 x 40 = 0.12394`; `mva = 0.9837526973854892`.

**mva_k-0002.** `sqrt(10/250) = 0.2`, `Phi^-1(0.99) = 2.3263478740408408`: IM `(465.2695748081682, 558.3234897698018, 418.74261732735135, 232.6347874040841)`; `mva = 5.478479731127988`.

**mva_k-0003.** Regress `X^2 = (9, 4, 1, 1, 4, 16)` on `(1, x)`: intercept `5.333333`, slope `2.0`; fitted `(3.3333, 4.3333, 5.3333, 6.3333, 7.3333, 8.3333)`; `mean(X) = -1/6`, `mean(X)^2 = 0.0277778`; `im_p = 2.3263479 sqrt(fit_p - 0.0277778)`: `(4.22957654, 4.82713291, 5.35846121, 5.84166081, 6.28783710, 6.70438587)`; `expected_im 5.541509073311709`. The regression lets IM rise with the regressor, where the larger moves are.

## Golden cases (designed 2026-11-19; not yet frozen)

| Case | Expected | Outside check |
|---|---|---|
| mva_k-0001 | mva 0.9837526973854892 | B |
| mva_k-0002 | im as above; mva 5.478479731127988 | B |
| mva_k-0003 | im as above; expected_im 5.541509073311709 | B |
| mva_k-0004 | expected_im `2.3263479 x sqrt(35/6 - 1/36)` (oracle digits) | B |
| mva_k-0005 | oracle | B |
| mva_k-0006, 0007 | `IM_0 (f_b - s_I) sum delta_i S_C S_B P(0, t_i)` | O |
| mva_k-0008 .. 0010 | exact conditional-variance DIM by two-dimensional quadrature | O-approx (not counted strictly) |
<!-- strip:end -->

## Errors (order KR-175)

`E_SCHEMA`: missing field, wrong type, unknown method. Structural `E_INPUT`: lengths differ; `regressor` and `increment` of different lengths; fewer paths than `order + 1`; `PLACEHOLDER_MODEL` (not wired). `E_DOMAIN`: `IM_i < 0`; `sigma_i <= 0`; `q` outside `(0.5, 1)`; `order > 6`; hazards `< 0`; non-finite. Error goldens: mva_ke-0001 `expected_im` with a negative entry (`E_DOMAIN`); mva_ke-0002 `REGRESSION` with 2 paths and order 2 (`E_INPUT`); mva_ke-0003 method `"SIMM"` and `q 1.5` at once (`E_SCHEMA`; no such method exists and none will).

<!-- strip:begin -->
## Acceptance (fixed before any run; proposed, frozen on confirmation)

- A1 Value goldens to 1e-12 relative plus 1e-12 absolute; regression cases to 1e-10 relative (least squares conditioning).
- A2 Properties: `f_b = s_I` gives 0; MVA linear in the IM profile; `REGRESSION` with order 0 equals `NORMAL_MPOR` when the increments' population variance equals `sigma^2 mpor_years`; with all regressors equal the regression of any order equals order 0.
- A3 Gate: at least 6 of 10 value cases outside-checked in the strict sense; 0008 to 0010 are reported but not counted (KR-173).
- A4 AAD of `mva` with respect to spreads, hazards, IM entries; of `im` (`REGRESSION`) with respect to the increments, away from a floored `max(., 0)`.
<!-- strip:end -->

## Accuracy envelope (plan 14.10 rule 4)

`GIVEN` and `NORMAL_MPOR` are exact. `REGRESSION` is an approximation of the conditional standard deviation: its error is the polynomial's misfit plus sampling noise, and ORE itself says it needs benchmarking. Envelope check registered now: on one G-42 payer swap (`a = 0.03`, `sigma = 0.01`) at 1, 5 and 10 years, the order-1 and order-2 regression IM averaged over 5,000 paths must be within 3% of the exact `E[Phi^-1(q) sd(X | x(t))]` (two-dimensional quadrature); a miss is recorded and the regression method carries the measured gap in its docs. This is the edge where the swap's value is most convex in `x` (long maturity, short time).

## Outside-check design (registered here before any run)

- **B (5):** 0001 to 0005.
- **O (2), ORE `xva` with `dim = Y`, `mva = Y`, `dimModel Flat`:** two G-42b netting sets, IM today given through the collateral balances file (`InitialMargin` 1,000,000), `dimScaling` 1, `f_b` a flat 80 bp borrowing curve, `s_I = 0`; with `Flat` ORE uses today's IM on every path ([ORE-P]), so its MVA is `IM_0 (f_b - s_I) sum delta_i S_C(t_i) S_B(t_i) E^N[D(t_i)]` and `E^N[D(t_i)]` is a Monte Carlo estimate of `P(0, t_i)`. Golden: the same sum with `P(0, t_i)` exact. Check: `|golden - ORE| <= max(3, z_Bonf) SE`, SE of `sum w_i D_p(t_i)` from the cube. This checks ORE's MVA aggregation (spreads, survival at bucket ends, discounting), not IM projection.
- **O-approx (3), `dimModel Regression`, order 1, `dimQuantile 0.99`, `dimHorizonCalendarDays 14`:** three G-42b single swaps. Golden: exact `E^N[Phi^-1(q) sd(V(t + 14/365) - V(t) | x(t)) D(t)]` by quadrature. Tolerance registered now: `max(3, z_Bonf) SE + 3%` of the golden MVA. Reported, **not counted** in the strict share (KR-173: ORE's regression is an approximation of our quantity, not the same computation). Values from ORE's `dim_evolution` output are compared date by date and reported.
- **None:** 0.

## Limits

- No IM from the project's placeholder initial margin model until KR-160's TODO is closed; when it is, a separate golden block is added and the gate recounted.
- IM is not reduced by the counterparty's default (no IM close-out interaction with CVA here; `xva-mpor-closeout.md` uses IM in exposure).
- Single currency; no IM on cleared trades (CCP IM) or haircuts on non-cash IM.
