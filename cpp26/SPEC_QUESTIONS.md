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
6. **`slices` above 100.** `E_LIMIT` comes after the `E_INPUT` and `E_DOMAIN` slice checks, as the spec lists them. This is unlike the general limits rule, where `E_LIMIT` comes right after schema.
7. **Dupire at a point.** `w_T <= 0` is tested before `g <= 0`. Both give `E_ARBITRAGE`, so only the message differs.
8. **E3 common checks, order.** The common checks run in input order: `spot`, `strike`, `expiry_years`, `vol`, `notional`. `fx.delta.to_strike` then checks the sign of `delta`, then its reachable range. `fx.smile.from_quotes` checks `atm_vol`, then `delta` in `(0, 0.5)`, then `call_vol` and `put_vol`, then each strike solve (so a PA call delta above its maximum is `E_DOMAIN` from that solve).
9. **E3 PA solves.** Both PA solves bisect in `ln K` to the last representable step. For the PA call, the solve first finds `K*` from `sd N(d2) = n(d2)`, then takes the root between `K*` and `ln F + 40 sd + 2`.
10. **E4 cube domain.** Every node's SABR parameters are checked (`E_DOMAIN`), not only the four that are interpolated. This runs after the grid checks (`E_INPUT`). It matches the goldens.
11. **E4 smaller checks.** A negative `vol` is `E_DOMAIN` in the bond-futures, YoY and ZC options; zero is allowed. `ctd_yield` and `ctd_modified_duration` must be above 0 (`E_DOMAIN`), checked after the premium bounds. In `rates.cap.strip`, `start_months` is range-checked after the flat-vol checks.
12. **E2 `slv_e-0006` (open, sent to the coordinator).** The golden expects `E_INPUT` for `spot` 100, `x_min` 4.6, `x_max` 4.7. Here `ln(spot) = 4.6052` is strictly inside, and the spec's only rule is `x_min < ln(spot) < x_max`. The build follows the spec, so this one case fails until the spec or the golden is settled.
13. **E2 check order.** `strikes` empty (`E_INPUT`) first, then `spot`, `expiry_years`, strikes above 0, `heston`, then `jumps` (or `vol`, then `jumps`, for Merton). SLV: `spot`, `expiry_years`, `heston`, `slices`, then the grid rules in the spec's order.
