# Stage E rulings, spec A (slices E1, E2, E3, E5)

Spec version 1.0.0. Normative: this page is part of every spec A stage E spec, and wins where it is more exact. Spec B's rulings (E4, E6, E7, E8) use the prefix E-B in their own file.

## Oracle rules for stage E, spec A

- Outside oracle: QuantLib 1.44 under plan rule 11.2.5. Every QuantLib convention object comes from `oracle/python/qf_oracle/convmap_e_a.py`; the reviewed table and per-suite coverage are in `oracle/OUTSIDE_E_A.md`; one register row per counted case, with the version, in `oracle/outside_register_e_a.json`. These are separate from the stage D files so the two spec sessions never edit one generated file.
- Where QuantLib has no route, a second independent route is used (40-digit mpmath replay of a different formula, or a published counterexample) and the case does not count as outside.
- No golden depends on libm last-digit rounding, unseeded Monte Carlo or an iteration path. Booleans and violation lists are guarded by the generator, which stops when a compared quantity sits near its threshold.

## Rulings

| # | Point | Ruling |
|---|---|---|
| E-A1 | Comparisons in `vol.svi.surface_check` | Strict, no tolerance: `g < 0`, `w_j < w_{j-1}`, slope `> 2`. Goldens keep every compared quantity at least 1e-6 (`g`, slopes, constants) or 1e-9 (calendar gaps) from its threshold, so rounding cannot flip a flag |
| E-A2 | Wing calendar rule | Asymptotic slope and constant of each wing, computed in binary64 as written (`b*(1-rho)`, `a + b*(1-rho)*m`, ...). Equal slopes compare exactly; the tie case uses dyadic parameters so every language computes the same bits. Catches crossings beyond the grid, which [GJ14] Lemma 2.1 forbids for all `k` |
| E-A3 | Fitting | `vol.svi.fit_surface` fits each slice by the stage C rule and reports arbitrage; it does not constrain the fit. Arbitrage-free constrained fitting (for example [GJ14] section 5's SSVI-based repair) is out of scope for stage E |
| E-A4 | Surface between SVI slices | Total variance linear in `T` at fixed forward log-moneyness; flat implied vol before the first and after the last slice; at a node, `w_T` is the right-hand difference. Same as the stage C grid surface in `T` |
| E-A5 | Forward vol of zero | A zero forward variance is not arbitrage and returns 0. Only a negative one is `E_ARBITRAGE` |
| E-A6 | Sticky delta | At fixed expiry, sticky (forward, unadjusted) delta equals sticky forward moneyness: Black forward delta `N(d1)` with `d1 = (-k + w(k)/2)/sqrt(w(k))` is a function of `k` alone. Premium-adjusted and spot deltas are E3 conventions and do not enter E1 |
| E-A7 | Vol of vol | Sample standard deviation (divisor `n - 1`) of daily changes, annualised by `sqrt(periods_per_year)`. `LOG` changes are the default reading of "vol of vol"; `ABSOLUTE` is given for normal-vol series. It is a historical measure on an input series, not a model parameter |
| E-A8 | Local vol inputs | `vol.local.dupire` takes SVI slices, not the stage C grid surface: the grid surface is piecewise linear in `k`, so `w_kk` is zero between nodes and undefined at them, and its local vol would be meaningless |
| E-A9 | FX pair conventions | The caller picks `delta_type` and `atm_type`; no table of which pair uses PA deltas or DNS. Rates are flat continuous; spot lag, premium date and the delivery-date discount ([RW12] section 1) are not modelled: `T` runs to delivery and expiry together |
| E-A10 | PA call delta root | Two strikes give one PA call delta below its maximum; the result is the root above `K*` (the strike of maximum delta), as market quoting uses. A delta at or above the maximum is `E_DOMAIN` |
| E-A11 | Strangle | `bf` is the smile strangle (`call_vol + put_vol = 2(atm + bf)`). The broker strangle, which prices a single-vol strangle against a fitted smile, is out of scope for stage E (register row EA8) |
| E-A12 | Heston at `xi = 0` | `E_DOMAIN`: the characteristic function divides by `xi^2`. The small-`xi` limit is tested at `xi = 1e-3` and `1e-2` (near zero, not at it, plan section 8), against Black-Scholes at the average variance |
| E-A13 | Heston and Bates quadrature | Targets are on the price (1e-8 per unit at spot 100, plus 1e-9 relative), not on a method. The reference recipe (Lewis integral, Gauss-Legendre 256 nodes on `[0, 200]`) meets them on every golden. The original Heston (1993) form of the characteristic function has a branch cut at long maturity; the [Alb07] form is required in effect, since the goldens include a 5-year, `xi = 1` case |
| E-A14 | SLV reference scheme | `vol.slv.leverage` is specified as a recipe, so four builds can agree to `numerical_scheme` tolerance: upwind face fluxes for drift, central diffusion, no-flux `v` boundaries, Dirichlet `x` ends, an explicit mixed term, a positivity floor after each step, a start density at least two cells wide, and a smooth conditional-variance estimate (no branch). It is a first-order scheme. It is not a converged leverage function and does not match QuantLib's `HestonSLVFDMModel` grid; accuracy is checked only by grid refinement (within 2% at the spot) and the flat-vol limit |
| E-A19 | Barrier already touched | Spot on or beyond the barrier is `E_DOMAIN`. The option's state (knocked in or out) is trade data, not a pricing input; a knocked-out option is worth its rebate and a knocked-in one a vanilla, which the caller prices directly |
| E-A20 | Lookback at zero carry | `b = 0` is `E_DOMAIN`: the Goldman-Sosin-Gatto closed form divides by `b`. The `b -> 0` limit exists but is not specified in stage E |
| E-A21 | Basket weights | `exotic.basket.moment` takes non-negative weights only; lognormal moment matching is poor for spreads, which go to `exotic.spread.kirk` |
| E-A22 | BAW | `r = 0` is `E_DOMAIN` (division by `1 - e^{-rT}`). Prices are judged to 1e-5 per unit at spot 100 (1 currency unit on 100,000 units): QuantLib solves the critical price only to about 1e-6, and BAW is itself an approximation with errors near 1e-2. The critical price is not an output |
| E-A23 | American tree and FD | CRR uses Hull's probability `(e^{(r-q)dt} - d)/(u - d)`, not QuantLib's `1/2 + drift dt/(2dx)` tree. FD is a reference recipe (backward Euler, projection), judged as a recipe to `numerical_scheme` tolerance; accuracy is checked only against a 2000-step tree (within 2e-2). Neither is outside-checked |

### Rulings on the R5 audit of E1 (2026-11-08)

| # | Point | Ruling |
|---|---|---|
| E-A15 | Lee boundary | A wing slope of exactly 2 is flagged: `LEE` when `sL >= 2` or `sR >= 2`. [GJ14] Lemma 2.2 needs `d_+ -> -inf`, which fails at slope 2. New golden `surf_e-0029` (`b = 2`, `rho = 0`: both slopes exactly 2 in binary64). No earlier golden changes |
| E-A16 | Citations | [GJ14] references corrected to the arXiv numbering: calendar section 2.1, butterfly section 2.2, SSVI section 4, Vogt smile Example 3.1 (eq. 3.8). Hull is the 10th edition (2018), by chapter title, as every stage B to E spec. Sources not opened are marked "not opened" |
| E-A17 | Outside count (rule 11.2.5) | A case counts only if every output is a QuantLib value or plain arithmetic on QuantLib values. Where QuantLib matches but an output is the spec's own algebra (SVI wing lists and the flag built on them; the sticky-delta smile term `vega dv/dS`), the case is listed in `oracle/outside_register_e_a.json` under `partly_outside_not_counted` and not counted. E1 falls from 31 to 16 counted; spec A from 75.5% to 60.2% (148 of 246) across E1 to E3 and E2. The convention map remains self-reviewed, and the register says so; that is not an outside review |
| E-A18 | Error codes without goldens | Added: `E_LIMIT` for 101 slices (`surf_e-0030`), 10,001 check points (`surf_e-0031`) and 10,001 Dupire points (`lv_e-0040`); `E_SCHEMA` for a missing `reject` (`surf_e-0032`), an unlisted `rule` (`lv_e-0041`) and `method` (`lv_e-0042`); `E_INPUT` for an empty forward-vol term structure (`lv_e-0043`) |

### Rulings on build questions

| # | Point | Ruling |
|---|---|---|
| E-A24 | `vol.slv.leverage` grid position (C++ question on `slv_e-0006`) | The rule stays as written: `x_min < ln(spot) < x_max`, else `E_INPUT`; no cell margin. The golden was wrong: `ln(100) = 4.6052` lies inside `[4.6, 4.7]`, so the spec accepts it. `slv_e-0006` now uses `x_min = 4.61`, which puts `ln(spot)` below the grid, and still expects `E_INPUT`. No other case changes |

### Rulings on the second R5 audit (E2, E3, E5; 2026-11-08)

| # | Point | Ruling |
|---|---|---|
| E-A25 | Stage floor | The 60% floor is judged on the whole stage after E-A17 is applied to both specs, and is reported with its margin in cases. Spec A reports its own share in `oracle/OUTSIDE_E_A.md`; the stage figure is the coordinator's, combining both registers. If the stage is below 60%, either more independent QuantLib-object cases are added or the owner records an accepted deviation |
| E-A26 | Heston and Bates recipe at short expiry | The 256-node rule on `[0, 200]` missed the target at `T = 0.02` (2.6e-7). The recipe is now 1024 nodes on `[0, 200/sqrt(min(T, 1))]`, within 2e-9 of the 30-digit value from 2 days to 10 years. New goldens at 7 and 2 days (tag `short-expiry`). The target is unchanged |
| E-A27 | Heston and Bates golden values | Goldens are the 30-digit values, not the binary64 recipe; they moved by about 1e-10, far inside the 1e-8 target. `vol.heston.cf` keeps class `fourier` |
| E-A28 | Lookback near zero carry | `E_DOMAIN` when `|b| <= 1e-8 v^2`, not only at `b = 0`. A golden at `b = 1e-5` (40-digit value, limit 1e-8) and an `E_DOMAIN` golden at `b = 1e-12` |
| E-A29 | SLV tolerance | `vol.slv.leverage` goldens are judged to 1e-7 absolute and relative. The recipe is first order, and an independent re-implementation agreed to 1.6e-9, 16% of the old 1e-8 limit |
| E-A30 | BAW at negative rates | `r <= 0` is `E_DOMAIN`: `1 - e^{-rT} <= 0`, and the put critical-price equation has no root. A golden at `r = -1%` |
| E-A31 | SLV citation | The leverage identity is Gyongy (1986) and Dupire (2004), not Henry-Labordere 2009, which is the particle method. The grid scheme is this spec's own recipe |
| E-A32 | Reiswich-Wystup citation | The working paper (CPQF No. 20): delta types section 1.3, ATM section 1.4, strike conversion section 1.5 |
| E-A33 | Small vol-of-vol claim | The targets table now says within 3 `xi` in price (measured 2.2 `xi`), not 0.05 `xi`. The goldens and their wrong-convention checks are unchanged |

Also added after the audit: one `E_SCHEMA` golden for a missing `cash` on an asset-or-nothing digital; six barrier goldens with rebates, including up-and-out and up-and-in. Up-barrier rebate cases already existed (`exotic_e` cases tagged `up_out`, `up_in` and `rebate`). All new cases are appended, so no case id moved.
