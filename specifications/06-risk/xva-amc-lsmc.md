# American Monte Carlo: Longstaff-Schwartz exercise and exposure of callable portfolios

Spec version 0.1.0. Status: **PROPOSED** (stage K item K-8b; xVA spec lane 2026-11-19; nothing implemented, no golden file written). Rulings `stage-k-rulings-xva.md` KR-171, KR-173 to KR-176; stage G G-18, G-42. Gate: `program/STAGE_K_XVA_GATE.md`.

Label on every Monte Carlo output: "simulated".

**Plain idea.** A callable trade is worth its value under the best exercise policy, and on a simulated path we cannot see the future to know whether calling today is best. Longstaff and Schwartz's answer is to look sideways instead: across all paths that are in the money at a date, regress what continuing actually paid on simple functions of today's state; the fitted curve estimates the value of waiting, and the holder exercises where the immediate payoff beats it. Working backwards date by date gives an exercise rule, and averaging the cash flows it produces gives the price. The same regression, applied at every exposure date, gives each path's trade value without a nested simulation, which is what an exposure engine needs for callable portfolios (American Monte Carlo, AMC).

## Sources

| Ref | Source | Evidence class | Used for |
|---|---|---|---|
| [LS01] | Longstaff and Schwartz, *RFS* 14(1), 2001: Section 1 (pp. 115-119, the eight-path example with every intermediate matrix and the value 0.1144), Section 2 (p. 122, weighted Laguerre basis eqs. 2-4), Section 3 (pp. 126-127, American put, constant plus three Laguerre terms, 100,000 paths with antithetics, 50 exercise dates a year, Table 1) | read 2026-11-19 | the algorithm; P and L cases |
| [ORE-S] | ORE User Guide `methods/simulation.tex`, "Exposures using American Monte Carlo" (parametric regression per trade, training and pricing phases, basis type and order, Bermudan swaption under LGM) | read 2026-11-19 | the O-approx route |
| [ORE-E] | ORE examples `AmericanMonteCarlo` (Bermudan agreement needs LGM mean reversion 0; basis order 6) | read 2026-11-19 | the O-approx configuration |
| [QL] | QuantLib 1.44 `FdBlackScholesVanillaEngine` with `BermudanExercise` | measured 2026-11-19 | L values |

## Formal statement

### `pricing.american.lsmc` (KR-171)

Inputs: `paths` (state at `t_0 .. t_m`, either given or generated: `model` GBM with `spot`, `rate`, `vol`, `n_paths`, `antithetic`, `seed`), `exercise_times` (subset of the grid), `payoff` (`PUT` or `CALL` with `strike`), `basis` (`MONOMIAL` order `n` or `LAGUERRE` order `n` on `x / strike`), optional `pricing_seed` (two-pass). Algorithm [LS01]: set cash flows to the payoff at `t_m`; for each earlier exercise time `t_k`, take the in-the-money paths, regress the realised cash flow discounted to `t_k` on the basis of the state at `t_k` (QR least squares), exercise where payoff `>` fitted continuation (strict), overwrite later cash flows on exercised paths; price = mean of cash flows discounted to `t_0`. Outputs `price`, `stderr` (over antithetic pair means when antithetic), `european` (same paths, final date only), `coefficients` per exercise time, `exercise_counts`.

### `xva.exposure.amc` (KR-171)

Inputs as `pricing.american.lsmc` for a callable netting set on given or generated paths, plus `exposure_times`. Each path's value at an exposure time is the fitted continuation value (or the exercise value where exercised); outputs EE, ENE and PFE as G-40 on these values. Specified, not given goldens in this spec except through the O-approx route; its value cases are added by the build lane once a deterministic reference (G-18 lattice exposure of a Bermudan swaption) is specified.

## Case inputs (kept for the blind packet)

| Case | Inputs |
|---|---|
| lsmc_k-0001 | the [LS01] Section 1 eight paths (given), strike 1.10, rate 0.06 per period, exercise at 1, 2, 3, `MONOMIAL` order 2 |
| lsmc_k-0002 | GBM `S 36`, `vol 0.20`, `T 1`, `r 0.06`, strike 40, put, 50 exercise dates a year, 100,000 paths (50,000 antithetic pairs), `LAGUERRE` order 3, seed 20261351 |
| lsmc_k-0003 | as 0002, `S 40` |
| lsmc_k-0004 | as 0002, `S 44` |
| lsmc_k-0005 | as 0002, `S 40`, `vol 0.40` |
| lsmc_k-0006 | as 0002, `S 36`, `T 2` |
| lsmc_k-0007 | as 0002, `S 44`, `vol 0.40` |
| amc_k-0001 .. 0003 | ORE cases, see "Outside-check design" |

<!-- strip:begin -->
## Worked examples

**lsmc_k-0001 (the printed example).** Discount factor per period `exp(-0.06) = 0.94176`. At time 2 the five in-the-money paths (1, 3, 4, 6, 7) regress `Y = (0, 0.07, 0.18, 0.20, 0.09) x 0.94176` on `(1, X, X^2)`, `X = (1.08, 1.07, 0.97, 0.77, 0.84)`: coefficients `(-1.06999, 2.98341, -1.81358)` (printed `-1.070, 2.983, -1.813`). Exercise at time 2 on paths 4, 6, 7. At time 1, paths 1, 4, 6, 7, 8: coefficients `(2.03751, -3.33544, 1.35646)` (printed `2.038, -3.335, 1.356`); exercise on 4, 6, 7, 8. Cash flows `0.07` at 3 on path 3, `0.17, 0.34, 0.18, 0.22` at 1 on paths 4, 6, 7, 8. Price `0.11443433004505696` (printed `.1144`); European `0.05638073927026089` (printed `.0564`). The printed continuation values at time 1 were evaluated with the rounded coefficients and differ from full precision by about 5e-4 (`STAGE_K_SOURCES_XVA.md` finding 1); the decisions do not change.

## Golden cases (designed 2026-11-19; not yet frozen)

| Case | Expected | Outside value | Outside check |
|---|---|---|---|
| lsmc_k-0001 | price 0.11443433004505696; european 0.05638073927026089; coefficients above; exercise paths {4, 6, 7, 8} at 1, none at 2 after time-1 overwrite, {3} at 3 | [LS01] p. 119: .1144, .0564; p. 117-118 coefficients to 3 decimals | **P** |
| lsmc_k-0002 | our estimator's value and stderr (oracle, project generator) | QuantLib FD Bermudan 4.477778571078294; [LS01] Table 1 FD 4.478 | **L** |
| lsmc_k-0003 | oracle | QuantLib 2.3140404396108387; [LS01] 2.314 | **L** |
| lsmc_k-0004 | oracle | QuantLib 1.1098508330990724; [LS01] 1.110 | **L** |
| lsmc_k-0005 | oracle | QuantLib 5.311929283959786; [LS01] 5.312 | **L** |
| lsmc_k-0006 | oracle | QuantLib 4.840181064177312; [LS01] 4.840 | **L** |
| lsmc_k-0007 | oracle | QuantLib 3.9476585393935406; [LS01] 3.948 | **L** |
| amc_k-0001 .. 0003 | see below | ORE AMC | O-approx |
<!-- strip:end -->

QuantLib values measured 2026-11-19: `FdBlackScholesVanillaEngine(process, 2000, 800)`, flat 6% continuous rate, no dividend, `BermudanExercise` on `round(365 T k / (50 T))` days, `k = 1 .. 50 T`; a 4000 x 1600 grid changes each value by less than 2e-5. These reproduce [LS01]'s printed finite-difference column to its three decimals (the continuously exercisable American values do not: 4.486 at the first row), which shows the printed column is the 50-dates Bermudan.

## Errors (order KR-175)

`E_SCHEMA`: missing field, unknown basis or payoff. Structural `E_INPUT`: exercise time not on the grid; given paths of unequal length; `pricing_seed` with given paths. `E_DOMAIN`: `strike <= 0`, `vol <= 0`, `n_paths < 2`, odd `n_paths` with antithetic, order outside `0..8`, non-positive state on a GBM path; non-finite. Error goldens: lsmc_ke-0001 `n_paths 9` with antithetic (`E_DOMAIN`); lsmc_ke-0002 exercise time 0.5 on an integer grid (`E_INPUT`); lsmc_ke-0003 basis `"SPLINE"` and `strike 0` at once (`E_SCHEMA`).

<!-- strip:begin -->
## Acceptance (fixed before any run; proposed, frozen on confirmation)

- A1 lsmc_k-0001 in all four builds to 1e-12 relative (deterministic); against print: price within 5e-5 of 0.1144, European within 5e-5 of 0.0564, coefficients within 5e-4 of the printed three decimals, the same exercise decisions.
- A2 lsmc_k-0002 to 0007: each build reproduces the oracle's estimate to 1e-10 relative (same generator, same seed); against QuantLib: `|estimate - QL| <= 3 stderr` with no further allowance. [LS01] reports differences up to 0.025 in its own Table 1 at `T = 2`, `vol 0.40`; the rows chosen here are the ones where its printed differences are at most 0.019 against standard errors of 0.007 to 0.012, so a miss would be informative. A miss is recorded as a miss, never re-seeded.
- A3 Gate: at least 6 of 10 value cases outside-checked strictly (P 1, L 6 planned; 7 of 10 if every L case passes).
- A4 Properties: price `>=` European on the same paths; price `<=` the QuantLib value plus `3 stderr` (low bias of an in-sample exercise rule is expected, high bias is a bug flag); with all exercise dates removed but the last, price equals European exactly.
<!-- strip:end -->

## Accuracy envelope (plan 14.10 rule 4)

LSMC has three errors: Monte Carlo noise (reported `stderr`), the regression's misfit of the continuation value (a low bias of the exercise rule), and in-sample foresight (a high bias when the same paths fit and price; two-pass removes it). The L cases cover the envelope's edges in moneyness (36, 40, 44) and in volatility and maturity (`vol 0.40`, `T 2`), the two directions in which [LS01] Table 1 shows the largest differences.

## Outside-check design (registered here before any run)

- **P (1):** lsmc_k-0001 against [LS01] pp. 117-119.
- **L (6):** lsmc_k-0002 to 0007 against QuantLib's finite-difference Bermudan (a different method: PDE, not simulation) under A2.
- **O-approx (3), ORE AMC, local heavy run (one WSL job, minutes a case):** three Bermudan swaptions (10 into 10 physical, annual exercise; LGM with mean reversion 0 as ORE's example requires, `sigma` 0.005, 0.01, 0.015), ORE `amc` engine, 10,000 training and 10,000 pricing paths, basis order 6; compare the time-0 price with our G-18 lattice price at a converged grid within `max(3, z) SE + 0.5%` of the price, and report EE profiles. Not counted strictly (KR-173: ORE's regression is an approximation, as ours is). Needs the wheel to run AMC: unverified (`STAGE_K_XVA_GATE.md` section 4).
- **None:** 0.

## Limits

- One-dimensional state in the goldens; multi-factor bases are allowed by the contract but not tested here.
- No duality upper bound (Andersen-Broadie); the high side is checked only against QuantLib.
- AMC exposure of callable portfolios has no strictly counted outside check yet; until a deterministic lattice exposure reference is specified, its EE outputs are reported as "simulated; checked against ORE AMC within an approximation tolerance".
