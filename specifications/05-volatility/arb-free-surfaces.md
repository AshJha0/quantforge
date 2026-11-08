# Arbitrage-free SVI surfaces

Spec version 1.0.0. Status: Specified. Stage E, slice E1 (spec A). `stage-e-rulings.md` is normative and wins where it is more exact.

Builds on `smile-and-surface.md` (stage C): raw SVI, its domain, `g`, SSVI and the power law `phi` are defined there and are not repeated. Log-moneyness `k = ln(K/F(T))` at each expiry's own forward. Total variance `w = sigma^2 T`.

Sources:
- [GJ14] J. Gatheral, A. Jacquier, "Arbitrage-free SVI volatility surfaces", *Quantitative Finance* 14(1), 2014, pp. 59-71. Section 2.1 (calendar: `w(k, T)` non-decreasing in `T` at fixed `k`, Lemma 2.1), section 2.2 (butterfly: `g(k) >= 0` and `d_+(k) -> -inf`, Lemma 2.2), section 4 (SSVI, eq. 4.1; its slices are raw SVI), Example 3.1 (section 3.4, parameters eq. 3.8: the Vogt smile; revisited in Example 5.1). Section numbers as the arXiv version 1204.0646, checked by the R5 audit.
- [Lee04] R. Lee, "The moment formula for implied volatility at extreme strikes", *Mathematical Finance* 14(3), 2004, pp. 469-480. Theorem 3.2: `limsup w(k)/|k| <= 2` in both wings (not opened: paywalled; the bound is restated in [GJ14] section 2.2).

## Object `slices`

Array of `{expiry_years, svi}`, `svi` the stage C parameter object `{a, b, rho, m, sigma}`.

Checks, in this order: array empty, or `expiry_years` not strictly increasing: `E_INPUT`. An `expiry_years <= 0`: `E_DOMAIN`. An `svi` outside the stage C domain: `E_DOMAIN`. More than 100 slices: `E_LIMIT`, checked at the gate before every rule check (`01-core/limits.md` B3; ruling E-A34).

## `vol.svi.surface_check`

Inputs: `slices`, `log_moneyness` (the check grid, strictly increasing, at least 1 point, at most 10,000, else `E_INPUT` / `E_LIMIT`), `reject` (boolean).

Outputs:

| Output | Rule |
|---|---|
| `butterfly_violations` | `{expiry_index, k_index}` for every slice `j` and grid point `i` with `g_j(k_i) < 0` |
| `calendar_violations` | `{expiry_index, k_index}` for every `j >= 1` and `i` with `w_j(k_i) < w_{j-1}(k_i)` |
| `wing_violations` | `{expiry_index, side, kind}`; see below |
| `arbitrage_free` | all three lists empty |

Comparisons have no tolerance (ruling E-A1); each is strict as written, and the Lee test is `>= 2` (ruling E-A15). Lists are ordered by `expiry_index`, then `k_index`.

**Wings** (grid-free). For slice `P = (a, b, rho, m, sigma)` the asymptotes of `w` in `|k|` are

- left: slope `sL = b*(1-rho)`, constant `cL = a + b*(1-rho)*m`;
- right: slope `sR = b*(1+rho)`, constant `cR = a - b*(1+rho)*m`,

computed in binary64 exactly as written. Per slice, in this order:

1. `{j, "LEFT", "LEE"}` if `sL >= 2`; `{j, "RIGHT", "LEE"}` if `sR >= 2`. [Lee04] bounds the slope by 2; [GJ14] Lemma 2.2 also needs `d_+(k) -> -inf`, which fails at a slope of exactly 2 (`d_+` tends to 0), so 2 itself is flagged (ruling E-A15).
2. For `j >= 1`, per side (LEFT then RIGHT), with `s, c` this slice's and `s', c'` the previous slice's: `{j, side, "CALENDAR"}` if `s < s'`, or if `s == s'` and `c < c'`. A smaller slope means the later slice crosses below the earlier one far out in that wing, wherever the grid ends (ruling E-A2).

If `reject` is true and `arbitrage_free` is false: `E_ARBITRAGE`, no outputs.

This is a check on the given grid plus the asymptotes. It is not a proof of no arbitrage between grid points; a caller who needs that uses a finer grid. With `sL, sR < 2` (enforced above) raw SVI has `d_+ -> -inf`, the second condition of [GJ14] Lemma 2.2.

## `vol.ssvi.to_svi`

Inputs: `rho`, `eta`, `gamma`, `theta` (one slice). Domain as stage C SSVI (`|rho| >= 1`, `eta <= 0`, `gamma` outside `(0, 1]`, `theta <= 0`: `E_DOMAIN`).

With `phi = eta theta^-gamma (1+theta)^(gamma-1)`, output `svi`:

`a = theta (1 - rho^2)/2`, `b = theta phi/2`, `rho = rho`, `m = -rho/phi`, `sigma = sqrt(1 - rho^2)/phi`.

This SVI slice equals the SSVI slice at every `k` ([GJ14] section 4; check by substitution: `b (rho (k-m) + sqrt((k-m)^2 + sigma^2)) = theta/2 (rho phi k + rho^2 + sqrt((phi k + rho)^2 + 1 - rho^2))`).

## `vol.svi.fit_surface`

Inputs: `expiry_years` (strictly increasing, else `E_INPUT`), `log_moneyness` (one grid shared by all slices), `total_variance` (one row per expiry, each as long as the grid), `reject`.

Each row is fitted on its own by the stage C `vol.svi.calibrate` rule, unweighted (same errors: fewer than 5 points, ragged rows, `E_INPUT`; a `total_variance <= 0`, `E_DOMAIN`). Then `vol.svi.surface_check` runs on the fitted slices with the input grid.

Outputs: `slices` (fitted, with the input expiries), `rmse` (array, one per slice), and the four outputs of `vol.svi.surface_check`. `reject` true and not arbitrage-free: `E_ARBITRAGE`.

The fit does not repair arbitrage: it reports it. Constrained (arbitrage-free) fitting is not in stage E (ruling E-A3).

Goldens use exact quotes from known parameters, where the global minimum is unique; they are judged on parameters within 1e-6 and `rmse` within 1e-6 (`stage-e-targets-a.md`).

## Wrong conventions the goldens catch

- calendar compared on implied vol instead of total variance;
- a Lee bound of 4 (the bound on `w/|k|` misread);
- SSVI mapping with `m = +rho/phi`.
