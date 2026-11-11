# FRTB standardised approach: vega and curvature (stage F carry-over)

Spec version 1.0.0. Status: Specified (stage F carry-over wave 2b, landed in stage G). Ruling `stage-g-rulings.md` G-51 (closes the owner item of G-49). Suite `stage_f/frtb_f2c` (19 cases), written by `oracle/python/gen_stage_f_frtb3.py`. Read with `frtb-sa-girr.md` and `frtb-sa-fx-equity.md`: bucket definitions, delta correlations and the MAR21.6 scenarios carry over.

**Plain idea.** Delta measures the first-order move of a book; an options book also loses when implied volatility moves (vega) and when the underlying makes a large move that the delta does not capture (curvature). FRTB charges vega like delta, with weighted vega sensitivities and correlations that also depend on option maturity. Curvature takes the loss under a large up and a large down shock, after removing the part delta already counts, keeps the worse direction per bucket, and aggregates with squared delta correlations, ignoring pairs where both positions gain.

Source: Basel Committee, *The Basel Framework* (version in force 2023-01-01), owner-supplied PDF `basel-framework-full.pdf`, MAR21 read page by page on 2026-11-11: MAR21.4 (pp. 570-571), MAR21.5 (pp. 571-573), MAR21.6 (p. 573), MAR21.56 and 21.57 Table 5 (p. 599), MAR21.79 (p. 609), MAR21.92 Table 13 (p. 614), MAR21.93 to 21.95 (pp. 614-616), MAR21.98 to 21.101 (pp. 616-618).

## `risk.frtb.vega`

Inputs: `risk_class` (`GIRR`, `CSR_NONSEC`, `EQUITY`, `COMMODITY`, `FX`; others `E_INPUT`); `sensitivities`, each `{bucket, name (not for GIRR or FX), option_maturity (> 0, else E_DOMAIN), underlying_maturity (GIRR only, required there, else E_INPUT), vega}`. `vega` is the vega sensitivity `VR_k` of MAR21.25, computed by the caller.

Recipe:
- Risk weights (MAR21.92 Table 13): 100% for every class, except equity large cap and indices (buckets 1 to 8, 12, 13, per the Table 13 FAQ): 77.78%. Footnote 295's formula `min(55% x sqrt(LH/10), 100%)` gives these values with the Table 13 liquidity horizons; the table values are used. `WS_k = RW x VR_k`.
- Within a bucket, GIRR (MAR21.93): `rho = min(exp(-a |T_k - T_l| / min(T_k, T_l)) x exp(-a |U_k - U_l| / min(U_k, U_l)), 1)`, `a = 1%`, `T` the option maturities, `U` the underlying residual maturities. Other classes (MAR21.94): `rho = min(rho_delta x exp(-a |T_k - T_l| / min(T_k, T_l)), 1)`, `rho_delta` the delta correlation along the name dimension only (MAR21.94 FAQ1): CSR 35% (80% in buckets 17, 18); equity as MAR21.78 spot against spot; commodity Table 12; FX 1.
- Other-sector buckets (equity 11, CSR 16): simple sum of absolute net weighted sensitivities (MAR21.56(1), 21.79(1)).
- Across buckets: the delta `gamma` of each class (MAR21.95). Aggregation MAR21.4; scenarios MAR21.6.

Outputs as `risk.frtb.girr_delta`, with `vega` in place of `delta`.

Worked example (`frtb_f2c-0006`): one FX vega of 1,000,000 gives capital 1,000,000 (100% weight). (`-0001`) GIRR, EUR 1y-into-5y +1,000,000 and 5y-into-10y -600,000: correlation `exp(-0.01 x 4) x exp(-0.01 x 1) = 0.951`, `K_EUR = 467,466` in the medium scenario.

## `risk.frtb.curvature`

Inputs: `risk_class` (as above); `factors`, each `{bucket, name (not for GIRR or FX), cvr_up, cvr_down}`: the bank's `CVR_k^+`, `CVR_k^-` of MAR21.5(2), already summed over instruments; `fx_scalar` (FX only, else `E_INPUT`): divide every CVR by 1.5 (MAR21.98). The same (`bucket`, `name`) twice is `E_INPUT`.

Formal statement:
- Per instrument (MAR21.5(2)): `CVR^+ = -(V(x up) - V(x) - RW s)`, `CVR^- = -(V(x down) - V(x) + RW s)`. Shocks are the delta risk weight as a relative shift (FX and equity, MAR21.98) or the largest bucket delta weight as a parallel shift (GIRR, CSR, commodity, MAR21.99). Example: a long option at 100 moving to 118 and 85 under a 30% shock, with `s = 50`: `CVR^+ = -3`, `CVR^- = 0`, so no charge (`frtb_f2c-0010`).
- Within a bucket (MAR21.5(3)): `K^+ = sqrt(max(0, sum max(CVR_k^+, 0)^2 + sum_(k != l) rho_kl CVR_k^+ CVR_l^+ psi(CVR_k^+, CVR_l^+)))`, likewise `K^-`; `K_b = max(K^+, K^-)`. Upward is selected if `K^+ > K^-`, or on a tie if `sum CVR^+ > sum CVR^-`; otherwise downward. `psi = 0` when both arguments are negative, else 1. `rho_kl` is the square of the delta correlation (MAR21.100); for CSR and commodity only the name dimension counts.
- Other-sector buckets (MAR21.56(2), 21.79(2)): `K_b = max(sum max(CVR^+, 0), sum max(CVR^-, 0))`.
- Across buckets (MAR21.5(4)): `S_b = sum CVR^+` if upward was selected, else `sum CVR^-`; `curvature = sqrt(max(0, sum K_b^2 + sum_(b != c) gamma_bc S_b S_c psi(S_b, S_c)))`, `gamma_bc` the square of the delta value (MAR21.101; GIRR 25%). The MAR21.6 scenarios apply to the squared correlations, and selection is made per scenario (MAR21.5(3)(a)).

Outputs: `scenarios` (per `high`, `medium`, `low`: `buckets` `[{bucket, k, s, selected}]`, `curvature`), `capital`, `binding_scenario`.

Worked example (`frtb_f2c-0014`): Brent and WTI with equal up and down CVRs: `K^+ = K^-` and `sum CVR^+ = sum CVR^-`, so downward is selected.

## MAR21.57 Table 5

Checked against the PDF (p. 599): it prints the upper triangle only; every value matches `frtb-sa-fx-equity.md`, which takes the table as symmetric. No change.

## Outside share

None (MAR21 has no worked example).

## Convergence and limit cases

| Method | Asserted order | Measured on | Limit case | Reference |
|---|---|---|---|---|
| Vega aggregation | exact | `frtb_f2c` | one factor: `capital = RW x VR` (`-0006`, asserted) | MAR21.4 |
| Curvature aggregation | exact | `frtb_f2c` | long gamma only: capital 0 (`-0010`) | MAR21.5 |
