# Exposure profiles of swap portfolios under Hull-White, checked against ORE (wave 4c)

Spec version 1.0.0. Status: Specified (stage G, wave 4c). Rulings: `stage-g-rulings.md` G-12, G-16, G-23, G-42. Suite `stage_g/expsim_g`, written by `oracle/python/gen_stage_g_w4c.py`; ORE inputs, runner and check under `oracle/ore/`.

**Plain idea.** The exposure of a netting set is the positive part of the sum of its trades' values. For one swap at a reset date, its expected discounted positive part is a swaption price (wave 4a). For a portfolio it is not, but under a one-factor model the whole netting set's value at a date is a function of one Gaussian number, so its expected positive part, its negative part and its quantiles are one-dimensional integrals that can be computed exactly. This page fixes those numbers as goldens and checks them against an independent production-grade engine, ORE (Open Source Risk Engine), which simulates paths and revalues the trades on each one.

Sources (pointers): [LSG] R. Lichters, R. Stamm, D. Gallagher, *Modern Derivatives Pricing and Credit Exposure Analysis*, Palgrave Macmillan, 2015, chapter 11 (the LGM model, its numeraire and bond formula) (not opened); [Ham] P. Hagan, "Evaluating and hedging exotic swap instruments via LGM", 2002 (not opened); [G15] J. Gregory, *The xVA Challenge*, 3rd ed., Wiley, 2015 (EE, ENE, PFE, EPE) (not opened); ORE 1.8.17.0, `open-source-risk-engine` Python wheel, Acadia/Quaternion, Apache licence 2.0, run under WSL Ubuntu (G-23).

## Model (LGM form of Hull-White)

With constant mean reversion `a` and volatility `sigma`: `H(t) = (1 - e^(-a t))/a`, `zeta(t) = sigma^2 (e^(2 a t) - 1)/(2 a)`. Under the LGM measure `x(t) ~ N(0, zeta(t))`, the numeraire is `N(t, x) = exp(H(t) x + H(t)^2 zeta(t)/2) / P(0, t)` and `P(t, T, x) = P(0, T)/P(0, t) exp(-(H(T) - H(t)) x - (H(T)^2 - H(t)^2) zeta(t)/2)` [LSG ch. 11]. This is the same model as Hull-White with the curve fitted (wave 1), written in the coordinates ORE simulates.

## `xva.exposure.portfolio_hw`

Inputs: `curve`, `mean_reversion`, `sigma` (Hull-White rules); `trades`: at least one (else `E_INPUT`), each a swap `{notional, fixed_rate, side (PAY or RECEIVE), start_years, payment_times}` with the G-12 conventions, all with the same reset dates (else `E_INPUT`); `exposure_times`: reset dates of the set before its last payment (else `E_INPUT`); `pfe_quantiles` in `(0, 1)` (else `E_DOMAIN`); `hazard_rate` (`>= 0`) and `recovery` (`[0, 1)`) for the CVA.

Formal statement. At an exposure time `t`, the deflated netting-set value is `f(x) = sum_trades sgn N_tr (1 - P(t, T_n, x) - K sum tau_i P(t, T_i, x)) / N(t, x)` (a payer is floater minus fixed; at a reset date the floater is worth par). Then:
- `discounted_ee(t) = E[max(f, 0)]`, `discounted_ene(t) = E[min(f, 0)]` (Gaussian integrals split at the zeros of `f`);
- `deflated_pfe_q(t)` (outputs `deflated_pfe_95`, `deflated_pfe_99`; named `pfe_95`, `pfe_99` until v0.8.0, renamed by ruling R6-5.1 because the quantity is not PFE as a desk reads it) = the smallest `y >= 0` with `P(max(f, 0) <= y) >= q` (0 if the exposure is 0 with probability at least `q`); it is a quantile of the **discounted** exposure under the LGM measure, the quantity ORE's cube holds. It is **not** a potential future exposure in the usual sense (a quantile of the undeflated exposure in currency at `t`, under the real-world or `t`-forward measure); dividing by the numeraire changes both the units and the measure, so the two can differ by much more than discounting at the risk-free rate. An undeflated PFE is not built (R6-5.1);
- `epe = sum_i discounted_ee(t_i)(t_i - t_(i-1)) / t_n` (`t_0 = 0`);
- `cva = (1 - R) sum_i discounted_ee(t_i)(e^(-h t_(i-1)) - e^(-h t_i))` (G-16 buckets).

Builds may use any one-dimensional quadrature that resolves the kinks (split at the zeros of `f`) to 1e-10 relative. Every zero of `f` and every crossing `f = y` must be found (ruling R6-5.5): bracket the critical points of `f` from the analytic `f'` on at least 6,001 points over `x` in `[-12, 12]` standard deviations, refine by bisection to 1e-14 relative, then find the at most one root on each monotone piece by bisection. Output keys for a quantile `q`: `deflated_pfe_` + `100 q` with trailing zeros removed (R6-5.6). Outputs in the order of `exposure_times`.

Worked example (the ORE demo, `oracle/ore/ORE_DEMO.json`). The `exposure_g-0001` swap (5-year payer at 3% on 10 million, `a = 0.05`, `sigma = 0.01`): this operation gives `discounted_ee = 352,680.98, 285,620.69, 204,079.27, 107,026.77`, equal to the Jamshidian values of wave 4a to every printed digit, and `deflated_pfe_95` at one year 824,786.37. ORE prices the swap today at 419,429.419545 against the closed-form 419,429.419545, and with 8,000 paths its EE lies within 1.0 standard error at every date.

## The ORE check (ruling G-42)

- Inputs written by `oracle/ore/build_case.py`: the curve as ACT/365 continuously compounded zero quotes at whole-day pillars with log-linear discount interpolation (it reproduces the curve's discount factors exactly), swaps on explicit whole-day schedules, the floating index `EUR-QFPAR-1Y` defined by an `IborIndex` convention (zero fixing days, NullCalendar, A365, unadjusted) so that ORE's par coupons are the single-curve par floater of G-12, LGM with constant `a` and `sigma` and no calibration, a simulation market with pillars every 30 days.
- Six ORE runs, one per (`a`, `sigma`) in {0.03, 0.10} x {0.005, 0.01, 0.015}, 5,000 samples, seeds 20261111 to 20261116, annual grid to 20 years, 16 netting sets per run.
- A case counts when every check lies within `max(3, z_Bonf)` Monte Carlo standard errors (EE and ENE means, PFE through the empirical CDF at the golden quantile, per-sample EPE and CVA), `z_Bonf` for the case's checks at a family-wise 1%. The rule was registered before the six runs were read (commit `c9a956a`); one debug run on the demo case was read first, and it fixed two input conventions (the index day count and the simulation pillars), recorded here.

## Outside share

Result of the registered rule (`oracle/ore/ORE_CHECK_4C.json`): **80 of the 96 value cases count** (40 single swaps, 40 portfolios), 0 of the 6 error cases. The 16 that do not count fail on one check each, all where the rule is ill-conditioned rather than where the values disagree: 15 on `pfe_99` of long payer exposures (`S20P` in all six runs, `P5` in five, `S10P` and `P2` at the highest volatility), and 1 on a degenerate standard error. For a payer the deflated value `f(x)` has an interior maximum, so the 99% quantile sits on the flat top of `f`, where a 0.1% value difference (for example 291,322 golden against 291,670 ORE at 17 years) moves the empirical CDF by many standard errors; the EE, ENE, EPE and CVA checks of those cases pass. The degenerate case is `P5` at `sigma = 0.005`, `a = 0.10`: the golden EE at one year is 0.0007 (a far tail no sample of 5,000 reaches), ORE's is 0 with a zero standard error, and the rule counted a zero-SE mismatch as a failure. The rule is kept as registered; an amendment (a value-space PFE tolerance, and a zero-SE allowance of one sample's weight) is left to the owner (G-42 note).

## Convergence and limit cases

| Method | Asserted order | Measured on | Limit case | Reference |
|---|---|---|---|---|
| One-factor quadrature | exact to 1e-10 | `expsim_g` | a single swap at a reset date: the Jamshidian swaption (demo case, every digit) | wave 4a |
| ORE simulation (evidence) | `N^-1/2` | 5,000 and 8,000 paths | the demo case within 1 SE at 8,000 paths | ORE 1.8.17 |
