# Spec questions from the C++ implementation

Written from the specs alone. Nothing here was changed to fit a golden file.

## Settled by the stage-a corrections

- `add_tenor` end of month: `calendars.md` now states QuantLib's rule, and this build follows it.
- `diff_linalg-0006`: the limit now follows the formula in the spec.
- Runner command on Windows: `runner.py` now resolves the path.
- `start == end` is tested first in `daycount.md`, which also settles `BUS_252` outside the calendar range: 0.

## Closed by rulings and limits

- Log checks against `E_SCHEMA`: ruling A2, the contract's order holds.
- `sequence < 1` and empty `series_id`: ruling A1, `E_SCHEMA`.
- `skip` with no upper limit: `limits.md`.
- `implementations.yaml` in the contract: corrected.
- Every other gap this file listed: settled by `specifications/01-core/rulings.md`.
- `document_text` breaking a limit and a parse rule together: rulings B1 and B2.

Array limit before work: closed by ruling B24. Each handler now reads its inputs, then calls `In::ready()`, then works.

## Stage B

Closed by `specifications/stage-b-rulings.md` and the corrected specs: `end_of_month` on swap schedules, `spot` from a
non-business `as_of` (my reading was wrong, B0), `months` ranges, `FRA` end, empty `pillars` (my reading was wrong, B3),
`day_count` in `forward`, `payment_lag`, empty `periods`, `compound`, `fx.*` tenors, curve `as_of` in `fx.*` and date
order of swap legs (I had no check, B8, B9), `calib.fit` checks, `hedge.solve` order, `hedge_tenors`, solve method,
19-digit sums, and shared bumped curves.

`start_months`: ruling B19, 0 to 1200, as built.


## Stage C

No golden depends on these. Each is how the build reads a point the spec leaves open; none is sent as a question yet.

- `vol.delta.*`, `vol.smile.rr_bf`: the spec lists no order among the scale, forward, vol and delta checks. Scale first is now ruling C15.
- `BACHELIER` with `shift: 0`: `E_SCHEMA`, by C8. C9 says `shift` at 0 may be absent, which does not settle whether it may be present.
- `eq.forward.parity` with no `discount_factor` key: `E_SCHEMA`, treated like `borrow_curve` under C9, though C9 does not name it.
- `vol.svi.calibrate`, `vol.sabr.calibrate`: the length rule is checked before the increasing rule, though the spec names increasing first.
- `vol.ssvi.calibrate`: no rule for `total_variance <= 0`. None added.
- `usecase.vol_surface`: no check order given, and no rule for `target.strike` or `quantity`. Built as `vol.equity.price`, `E_DOMAIN`.

Settled by rulings: `SPOT` with null `scale` (C15, my `E_DOMAIN` was wrong), a price at or above `f0` (C16, as built), empty lists (C17; my order was wrong in `vol.svi.evaluate`, `vol.sabr.*`).

## Stage D wave 1 (open)

Each is answered here with the most conservative reading; none changes a golden result.

1. **Closed by ruling D27.** Stage B golden `ois-0023` against ESTR. It expects `rates.ois.bootstrap` with `ESTR` to be `E_SCHEMA`. `ois-curves.md` 1.1.0 and contract 1.5.0 now list `ESTR`, so this build returns `ok` and that one stage B case fails. The spec wins; the case needs retiring or changing to `ok` by the oracle session.
2. **Closed by ruling D45.** **Unknown `convention` string in `rates.ois.compound_dated`, `rates.ois.fit_steps`, `rates.basis.ois_spread`.** The specs say "not `OVERNIGHT`: `E_INPUT`". A listed non-overnight record (`USD-TERM-3M`) gives `E_INPUT`; an unlisted string gives `E_SCHEMA`, as every other enum. `rates.curve.joint_bootstrap` keeps the bootstrap's rule (`E_SCHEMA` for anything not overnight).
3. **Empty `step_dates` in `rates.ois.fit_steps`.** Ruling D12 makes empty date lists `E_INPUT`; with `m = 0` the fit would otherwise be a one-quote flat rate. This build returns `E_INPUT`, checked before the quote count.
4. **Closed by ruling D31.** **Empty `dates` in `rates.ois.step_curve`, `rates.csa.discount`.** D12: `E_INPUT`, checked after the curve's own checks.
5. **Closed by ruling D42.** **Two forwards on one date in `rates.csa.discount`, two jumps on one date.** Forwards: `E_INPUT` (ambiguous data), after the `E_DOMAIN` checks. Jumps: already `E_INPUT` by the strictly increasing rule.
6. **Closed by ruling D62.** **`GLOBAL` in `rates.curve.joint_bootstrap`.** The system is block triangular, so Newton on all pillars equals the discount block's `GLOBAL` Newton followed by the projection block's solve. This build does exactly that; `max_repricing_error` is the larger of the two blocks.
7. **Closed by ruling D62.** **Order of `LOCKOUT` range check against business-day checks.** `n` is counted from the business days in `[start, end]` before `start`/`end` are checked, as the listed order puts `shift_days` first.
8. **Closed by ruling D43.** **`bond.yield.from_price` with a negative clean price** (`bonds_d-0048`: clean -1, dirty +1.06). `bonds.md` makes only `clean_price + accrued <= 0` an `E_DOMAIN`, yet the golden expects `E_DOMAIN`. This build also rejects `clean_price <= 0`, the stricter reading the golden implies.
9. **Closed by ruling D62.** **Asset swap floating dates on an end-of-month maturity.** `bonds.md` gives the end-of-month rule for the bond object only. The floating leg here steps back with plain month arithmetic (Feb 28 to Nov 28), which `bonds_d-0041` confirms.
10. **Closed by ruling D35.** **`bond.futures.conversion_factor` with delivery on or after maturity.** Not specified; `E_DATE_ORDER`, as the common bond check.
11. **Closed by ruling D37.** **Negative weight in `bond.fit.nelson_siegel`.** `E_DOMAIN`, checked after the positive-weight count and `tau`.
12. **Closed by ruling D36.** **CDS curves not as of the trade date.** `credit.md` measures time from `T` and gives curves their own `as_of`. This build requires both the discount and hazard `as_of` to equal `trade_date` (`E_INPUT` otherwise).
13. **Closed by ruling D37.** **Negative or all-zero weights in `credit.index.intrinsic` and `credit.curve.composite`.** Not specified; `E_DOMAIN`.
14. **Closed by ruling D32.** **`eq.futures.basis` implied financing spread with no root.** "Unique, as for borrow": this build searches the same `[-0.5, 0.5]` and returns `E_NOT_BRACKETED` outside it.
15. **Closed by ruling D41.** **`eq.trs.pv` with `end <= start`.** Not specified; `E_DATE_ORDER`.
16. **Closed by ruling D42.** **Two CPI fixings for one month in `infl.linker.price`, two FX forwards for one date.** `E_INPUT`, as two fixings on one date in `rates.ois.compound_dated`.
17. **Closed by ruling D45.** **`fx.xccy.bootstrap` with a convention other than SOFR/ESTR.** Ruling D17 allows only those; a listed other record gives `E_INPUT`, an unlisted string `E_SCHEMA`.
18. **Closed by ruling D44.** **`mbs.cashflows` with `wac <= 0` and `net_coupon > wac` together** (`mbs_d-0011`: wac 0, net 0.06). `mbs.md` lists the `E_INPUT` checks first, yet the golden expects `E_DOMAIN`. This build checks `wac <= 0` before `net_coupon > wac`, as the comparison presumes a valid WAC.
19. **Closed by ruling D56.** **Cap vol given as a list for one caplet, or `vol` neither number nor list.** A number is flat; any array is quoted (length must match, `E_INPUT`); anything else `E_SCHEMA`.
20. **Closed by ruling D40.** **Swaption and cap `tenor_months < 1`.** Not specified; `E_INPUT`, as `start_months`.

## R1.7 batch mode (silent choices)

1. **`diagnostics` on error results.** `--timings` must add `diagnostics.elapsed_ns` to error results, which had no `diagnostics` member. `batch_check.py` strips only `elapsed_ns`, so a key present only with the flag fails timings_identity. The contract says `diagnostics` "may always be present", so every error result now carries `"diagnostics":{}`. The runner does not compare `diagnostics`, and no golden changes.
2. **`--timings` with `version` or `operations`.** Exit 64, empty stdout, as "any other argument".
3. **BT5 at end of file.** A final line of exactly 16,777,216 bytes plus a CR and no LF is parsed, not `E_LIMIT`: the CR is removed before the length is checked. The line buffer is the limit plus 2 bytes, and the rest of a longer line is read and dropped.
4. **Clock window.** `elapsed_ns` is measured with `steady_clock`, from just after the line is read to just before the result is written. For `run`, it starts after stdin reaches end of file.

## R2.1 par and key-rate risk (silent choices)

1. **Solve method.** `risk.curve.par` and `risk.curve.jacobian` take no `method`; the curve is built with `SEQUENTIAL`, no jumps.
2. **Check order inside the rule checks.** After `E_SCHEMA` and `E_LIMIT` (quote count, pillar count, key-date count): `bump_bp`, then BOND `notional` (`E_DOMAIN`), then the OIS convention match, `key_dates` rules (`E_INPUT`), then the bootstrap's own checks (crossed quotes, then `ois_bootstrap`).
3. **`TRIANGULAR` with `key_dates` null or empty.** `E_INPUT` ("at least 1").
4. **Jacobian above the diagonal.** Not computed: written as exactly 0, on the rule that pillar `i` is solved from quotes `0..i`. This assumes one pillar per quote, in quote order, as `rates.ois.bootstrap` gives.
5. **Bumped curves.** A `TRIANGULAR` or parallel bump multiplies `D(t)` by `exp(-s(t) t)` at every date, after interpolation and before jumps (jumps multiply, so the order does not matter). A `PILLAR` bump moves the stored jump-free log factor of pillar `i` by `-h t_i`, which is the same as moving `ln D(p_i)`.
6. **OIS product value.** `valuation.pv` with no `snapshot_id`.

## Stage E (silent choices)

E1 (`arb-free-surfaces.md`, `local-and-forward-vol.md`) and E7 (`garch.md`, `variance-swaps.md`, `vix-index.md`). Every golden passes, so none of these is pinned against a golden case.

1. **VIX selection.** Settled by ruling E-B15: no selected out-of-the-money put, or no selected out-of-the-money call, is `E_INPUT` (puts are checked first).
2. **VIX zero-bid count.** The count of consecutive zero bids starts afresh on each side, from the first strike beyond `K0`. `K0`'s own bids never count.
3. **`vol.vix.index` check order.** After schema, the `N1 < N2`, `N1 <= 43200 <= N2` rule is checked before either term's own checks (near first, then next).
4. **`vol.varswap.fair_strike` `K_min`.** `K_min - dk <= 0` uses the lowest put strike (the put walk's extension).
5. **`vol.garch.fit` convergence.** Nelder-Mead in unconstrained coordinates (`omega = e^u`, `alpha` and `beta` as softmax shares with a slack term, so `alpha + beta < 1`), from five starts, then restarted from the best point until a restart gains under 1e-12 relative. `E_NO_CONVERGENCE` if the last restart's simplex has not collapsed. Fitted parameters are written to diagnostics, not to values.
6. **`slices` above 100.** Settled by ruling E-A34: every E_LIMIT comes right after E_SCHEMA.
7. **Dupire at a point.** `w_T <= 0` is tested before `g <= 0`. Both give `E_ARBITRAGE`, so only the message differs.
8. **E3 common checks, order.** The common checks run in input order: `spot`, `strike`, `expiry_years`, `vol`, `notional`. `fx.delta.to_strike` then checks the sign of `delta`, then its reachable range. `fx.smile.from_quotes` checks `atm_vol`, then `delta` in `(0, 0.5)`, then `call_vol` and `put_vol`, then each strike solve (so a PA call delta above its maximum is `E_DOMAIN` from that solve).
9. **E3 PA solves.** Both PA solves bisect in `ln K` to the last representable step. For the PA call, the solve first finds `K*` from `sd N(d2) = n(d2)`, then takes the root between `K*` and `ln F + 40 sd + 2`.
10. **E4 cube domain.** Every node's SABR parameters are checked (`E_DOMAIN`), not only the four that are interpolated. This runs after the grid checks (`E_INPUT`). It matches the goldens.
11. **E4 smaller checks.** A negative `vol` is `E_DOMAIN` in the bond-futures, YoY and ZC options; zero is allowed. `ctd_yield` and `ctd_modified_duration` must be above 0 (`E_DOMAIN`), checked after the premium bounds. In `rates.cap.strip`, `start_months` is range-checked after the flat-vol checks.
12. **E2 `slv_e-0006`.** Settled by ruling E-A24: the spec rule stands and the golden input was corrected (`x_min` 4.61).
13. **E2 check order.** `strikes` empty (`E_INPUT`) first, then `spot`, `expiry_years`, strikes above 0, `heston`, then `jumps` (or `vol`, then `jumps`, for Merton). SLV: `spot`, `expiry_years`, `heston`, `slices`, then the grid rules in the spec's order.
14. **E8 implied-vol error case.** Settled by ruling E-B27: the golden (now `creditopt_e-0145`) is a receiver.
15. **E8 output names and checks.** `credit.copula.joint_default` writes `joint_default_probability` and `default_correlation`; the goldens accept them. `default_probabilities` must have exactly 2 entries (`E_INPUT`). `credit.lhp.loss_cdf` with an empty `losses` is `E_INPUT`. `credit.cdsoption.implied_vol` checks `knock_out` before the date checks.
16. **Second audit (E-B29 to E-B33).** Nearest correlation stops when the largest absolute change in `Y` is below 1e-14, which is stricter than the 1e-12 relative test of E-B31. In `risk.corr.implied`, a negative weight is `E_DOMAIN`, then the vols, then fewer than two positive weights (`E_DOMAIN`). The cap strip searches `[1e-10, 5]` (Black) or `[1e-10, 0.5]` (Bachelier).
17. **Spec A second audit (E-A26, E-A28, E-A30).** Heston and Bates use Gauss-Legendre 1024 on `[0, 200/sqrt(min(T, 1))]`. In the lookback, `|b| <= 1e-8 v^2` is `E_DOMAIN`, checked after `running_extreme`. In BAW, `r <= 0` is `E_DOMAIN`, checked after the common checks.
18. **Cross-language rulings (E-A34 to E-A40).** The C10 cap of 100 applies to the forward-vol lists, smile-dynamics strikes, Heston, Bates and Merton strikes, Heston `u`, Asian fixings, basket lists, and the fit-surface expiries and grid. The vol-of-vol series is capped at 10,000. SLV runs its E_LIMIT checks, then the slice and grid E_INPUT rules, then E_DOMAIN. An SLV spot of 0 or below fails the `ln(spot)` grid rule (E_INPUT) first.
19. **Spec B cross-language rulings (E-B34 to E-B40).** All applied. Replicated variance below 0 is `E_DOMAIN` (E-B36). The three malformed goldens (`rulings_e_b-0008`, `-0009`, `-0015`) were rebuilt upstream and pass.

## Stage F

- F-2 order in the CLI: a non-finite Real is recorded when read and raised as `E_DOMAIN` in `In::ready()`, after
  `E_SCHEMA` and `E_LIMIT`. A few older handlers run a rule check before `ready()`; for a non-finite input there the
  code is still `E_DOMAIN` (their own domain check), only the message differs.
- F-1 and a field that is any JSON value (`core.store.*` record `value`): a top-level `"NaN"`, `"Infinity"` or
  `"-Infinity"` string is read as a Real and rejected by F-2; other strings stay record values. Not stated for this field.
- Golden defects reported to the spec session on 2026-11-09: `e1_core-0033`, `0038`, `0275`, `0280`, `0305` (a `same_as`
  case keeps its base case's `extra_checks`), and `e1_core-0129` to `0131` (`"NaN"` in the Integer `n` expects
  `E_DOMAIN`; F-1 says `E_SCHEMA`). This build follows F-1.
- R7 `credit.cdsindex.option_price`: domain checks in the spec order (recovery, hazard, strike, coupon, vol), notional last; `F_adj <= 0` names field `hazard_rate`, `K_adj <= 0` names `strike`; `h_K` bisection to the floating-point limit; vol = 0 is the intrinsic value; notional scales outputs only.
- Q1 tension spline: settled by ruling F-35; the small-z branch uses `alpha = h/6 (1 - 7 z^2/60)` and `R(u)` with its `z^2` term.
- Q1 `step_end` must be a pillar of every curve it is applied to (in `rates.curve.joint_bootstrap` both curves). `rates.projection.bootstrap` has no `tension`/`step_end` keys, so TENSION_SPLINE and HYBRID are `E_INPUT` there. `rates.curve.inspect` forwards are of the smooth curve (no jumps, no zero shift); LINEAR_ZERO forward before the first pillar is the first zero rate.
- R8 `vol.garch.loglik`: STUDENT_T checks (missing nu `E_INPUT`, nu <= 2 `E_DOMAIN`) run after the existing checks; a non-finite `degrees_of_freedom` is `E_DOMAIN` even under NORMAL. `vol.garch.estimate` interior test for nu: `nu - 2 >= 2e-6` and `500 - nu >= 5e-4`.
- R10 VIX: a missing quote key stays `E_SCHEMA`; only an explicit `null` is a null quote. A present negative quote is `E_DOMAIN` even if the other side of that series is null.
- Q4 XCCY quote column: `dR/dq = sum alpha_i D_f(e_i)` (the true derivative of `L_foreign` in `spread`); `joint_f-0001` covers it and passes.
- Q4 turns (F-26 amended): the solve holds `ln S` internally; `dR/dx` is re-expressed at fixed `ln D` (turn column minus
  the columns of pillars after the turn) before the IFT solve. Exact zeros off the turn only on `OIS_STEPS` curves.
- Q4 IFT `dR/dx`: central differences Richardson-combined over `h = 1e-5` and `5e-6`. With `h = 1e-7` the
  monotonic log cubic system (`joint_f-0003`) misses the `jacobian` class by roundoff (1.6e-9 against 1e-9).
- Q4 `rates.funding.curve`: `1 + rate tau <= 0` (`E_DOMAIN`) is checked after all `end` order checks (`E_INPUT`).
- F3 `risk.curve.cross_gamma`: settled by ruling F-36 (`PAY`/`RECEIVE`, 1e-9 absolute). The build still sums `V(bump) - V(0)` per cash flow with `expm1`.
- F3 `risk.book.ois_sensitivity`: exact derivatives for LOG_LINEAR_DF and LINEAR_ZERO; the stage F interpolations are
  `E_DOMAIN` here (no golden). `tenor_years` above 100 is `E_DOMAIN` (calendar range). E_LIMIT sizes (100000 swaps or rows,
  100 PCA columns) are this build's choice.
- F4 `risk.var.monte_carlo`: settled by ruling F-39 (`seed` a decimal u64 string; `E_NOT_POSITIVE_DEFINITE`).
- F4 FHS with all returns 0 and traffic light with exceptions above observations: `E_DOMAIN`, accepted by F-39.
- F5 book and UC4 choices (duplicate opening position, zero quantity, optional `ipv`, later quotes, shape checks first): accepted by F-39.

## Stage G

- `capfloor_g-0040` (golden defect, reported 2026-11-11): HULL_WHITE cap with `period_times` [1, 2, 3] and `strike` -0.5
  expects `E_DOMAIN` with description "1 + K tau <= 0", but `1 + K tau = 0.5 > 0` for every period, so the spec rule
  does not apply and this build prices it. The other 40 `capfloor_g` cases pass.
- `expsim_g` wave 4c, 8 cases (`-0039`, `-0045`, `-0055`, `-0061`, `-0071`, `-0077`, `-0087`, `-0093`), reported
  2026-11-11: each fails one `pfe_99` point at a late date of a long payer, by 3e-5 to 1e-4 relative, where the 99%
  quantile sits on the flat top of the deflated value `f(x)`. An independent 40-digit mpmath check of `-0039` at
  t = 17 (critical point of `f` by `findroot`, both crossings of `f = y` by bisection) gives `P(f > y) = 0.01000000000008`
  at this build's 291,331.928, and `0.01234` at the golden 291,322.038 (fmax 291,350.886). So this build looks right
  and the golden quantile root looks like it misses part of the region above `y` near the top. Everything else in
  these cases, and the other 94 cases, pass.
