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
