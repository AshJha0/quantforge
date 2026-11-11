# Model-reserve dispersion report (Q9 part 2)

Spec version 1.0.0. Status: Specified (stage G, wave 3e). Ruling: `stage-g-rulings.md` G-36. Suite `stage_g/reserve_g` (9 cases), written by `oracle/python/gen_stage_g_q9b.py`.

**Plain idea.** Two models can match the same vanilla option prices and still disagree on an exotic, because the exotic depends on how the smile moves, which vanillas do not pin down. A desk books the exotic with one model and holds a reserve against the chance that another reasonable model is right. A simple, widely used measure is the spread of the prices from a set of models that all fit the vanillas [Cont 2006]. Regulators ask for the same idea under prudent valuation: a model-risk adjustment from the range of plausible models [EU 2016/101, Article 11]. This page fixes the statistic (with goldens) and registers, before any run, the report that applies it to every single-asset exotic under Heston, local vol and stochastic-local vol (SLV).

Sources:
- [Cont06] R. Cont, "Model uncertainty and its impact on the pricing of derivative instruments", *Mathematical Finance* 16(3), 2006, pp. 519-547: the worst-case range over a set of calibrated models as a coherent measure of model uncertainty (not opened in this session).
- [EU 2016/101] Commission Delegated Regulation (EU) 2016/101, regulatory technical standards for prudent valuation, Article 11 (model-risk additional valuation adjustment from a range of plausible models) (not opened).
- [Gyo86] and the SLV leverage of `05-volatility/heston-family.md`; local vol of `05-volatility/local-and-forward-vol.md`.

## `risk.model_reserve.dispersion`

Inputs: `prices`, an object from model name to price (at least two entries, else `E_INPUT`; every price finite, F-2); `reference_model`, the booked model (must be a key of `prices`, else `E_INPUT`).

Formal statement. With `p_m` the prices and `p_ref` the booked price:
- `mean = (1/M) sum p_m`; `range = max p_m - min p_m` [Cont06]; `half_range = range/2`;
- `reserve = max_m |p_m - p_ref|` (how far the booked price can be from the furthest model);
- `worst_model`: the model attaining `reserve`; on a tie, the first name in Unicode code-point order;
- `relative_reserve = reserve/|p_ref|`, or `null` when `p_ref = 0` (`null` is legal only here).

Worked example (`reserve_g-0001`). A down-and-out call: Heston 4.1832, local vol 4.6021, SLV 4.3907, booked on SLV. `range = 0.4189`, `reserve = |4.6021 - 4.3907| = 0.2114` (local vol is furthest), `relative_reserve = 4.81%`.

Tolerance: 1e-12 absolute plus 1e-15 relative (one rounding of exact arithmetic). Outside: none (arithmetic on the inputs).

## The report (registered 2026-11-11, before any run; ruling G-36)

Run by the Python research lane; every language implements `risk.model_reserve.dispersion` only.

- Market: `S = 100`, `r = 0.03`, `q = 0`. The "true" smile is Heston `{v0 0.04, kappa 1.5, theta 0.04, xi 0.5, rho -0.7}` priced by Lewis's integral on expiries 0.25, 0.5, 1, 2 and strikes 60 to 150 step 5.
- Models: `HESTON` (those parameters); `LOCAL_VOL` (`vol.local.dupire` on that surface); `SLV` (Heston with `xi` scaled by 0.5 and leverage from `vol.slv.leverage`, so it also fits the surface). Booked model: `SLV`.
- Simulation: full-truncation Euler for the variance, log-Euler for the spot, 250 steps a year, 200,000 paths, numpy PCG64 seed 20261111, the same normals for all three models.
- Products, `T = 1`, `K = 100` unless stated: digital call; barrier down-and-out call `H = 85` and up-and-out call `H = 130`, daily monitoring; arithmetic Asian call (daily); floating lookback call; chooser at 0.5. Multi-asset exotics (quanto, spread, basket) are out of scope: they need a correlation model the three single-asset models do not define.
- Sanity gate (pass or fail): each model reprices the 1-year calls at strikes 80, 100, 120 within 3 SE of the Lewis prices. If it fails, the report is marked invalid, not tuned.
- Output: one row per product with the three prices, their SE and the `risk.model_reserve.dispersion` outputs. There is no pass or fail on the size of the reserve; the plan's acceptance is that the report runs on every exotic.

Status: registered, not run in this session.

## Convergence and limit cases

| Method | Asserted order | Measured on | Limit case | Reference |
|---|---|---|---|---|
| Dispersion statistic | exact (one rounding) | `reserve_g` | all models equal: every spread output 0 (`reserve_g-0003`) | exact rationals |
| Report simulation | Monte Carlo `N^-1/2` | sanity gate on vanillas | `xi -> 0`: the three models coincide with Black-Scholes | Lewis prices |
