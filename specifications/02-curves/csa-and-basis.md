# CSA discounting, index basis and joint calibration

Spec version 1.0.0. Status: Specified (stage D).

## `rates.csa.discount`

A collateralised trade discounts at the collateral rate. Inputs: `curve` (the collateral currency's OIS curve), `collateral_spread` `s` (continuous, added to the collateral rate), `fx` (`null`, or `{spot, forwards: [{date, forward}]}`), `dates`. Output: `discount_factors`. With `t = (d - as_of)/365`:

- `fx` `null`: `D(d) = Dc(d) exp(-s t)`.
- Trade in currency X, cash collateral in currency Y: `D(d) = Dc(d) * spot / F(d) * exp(-s t)`, where `Dc` is Y's OIS curve and `spot`, `F(d)` are units of X per unit of Y for delivery on `as_of` and on `d`. `fx` is a key that must be present (ruling C9).

Checks, in order: `spot <= 0` or a `forward <= 0`: `E_DOMAIN`. A date with no forward when `fx` is given: `E_INPUT`. A date before `as_of`: `E_OUT_OF_RANGE`.

## `rates.basis.ois_spread`

Two overnight indices in one currency, such as SOFR against a synthetic second index. Inputs: `convention`, `tenor`, `discount`, `projection_a`, `projection_b` (curves with one `as_of`, else `E_INPUT`). Periods `(s_i, e_i, p_i)` from `ois-curves.md`. Output:

`spread = (F_a - F_b) / A`, `F_x = sum (P_x(s_i)/P_x(e_i) - 1) D(p_i)`, `A = sum alpha_i D(p_i)`.

It is the amount added to leg B to match leg A. Both legs discount on `discount`.

## `rates.curve.joint_bootstrap`

Inputs: `convention` (overnight), `index` (`USD-TERM-3M`), `as_of`, `ois_quotes` (as `rates.ois.bootstrap`), `term_quotes` (as `rates.projection.bootstrap`), `interpolation`, `method` (`SEQUENTIAL`, `GLOBAL`). Outputs: `discount_pillars`, `projection_pillars`. Diagnostic: `max_repricing_error`, required.

One system: every OIS quote reprices on the discount curve, and every term quote on the projection curve discounted on it, each below 1e-13. The system is block triangular (OIS quotes do not see the projection curve), so `GLOBAL` (Newton on all pillars) and `SEQUENTIAL` (discount curve first) give one answer. Either list empty: `E_INPUT`; other checks as the two bootstraps.

## Acceptance

`csa.discount`: class `interpolation`, hand replay. `ois_spread`: 1e-10; equals the difference of QuantLib `MakeOIS` fair rates on the two projection curves within 1e-12. `joint_bootstrap`: pillars within 1e-9; QuantLib two-step build agrees within 1e-10. Suite `stage_d/csa_d`.

## Sources

Added in R1 (v0.4.1) to meet plan 11.2.4 and 11.5. These are references only: they do not change any rule above. "(not opened)" means the reference was checked from memory for this backfill, not re-read; section numbers are given only where known.

- [S1] Piterbarg, V., "Funding beyond discounting: collateral agreements and derivatives pricing", *Risk*, February 2010, 97-102 (not opened)
- [S2] Fujii, M., Shimada, Y. and Takahashi, A., "A note on construction of multiple swap curves with and without collateral", *FSA Research Review* 6, 2010 (not opened)
- [S3] ISDA, *2016 Credit Support Annex for Variation Margin* (collateral interest rate) (not opened)
