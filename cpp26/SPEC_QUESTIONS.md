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

1. **Stage B golden `ois-0023` against ESTR.** It expects `rates.ois.bootstrap` with `ESTR` to be `E_SCHEMA`. `ois-curves.md` 1.1.0 and contract 1.5.0 now list `ESTR`, so this build returns `ok` and that one stage B case fails. The spec wins; the case needs retiring or changing to `ok` by the oracle session.
2. **Unknown `convention` string in `rates.ois.compound_dated`, `rates.ois.fit_steps`, `rates.basis.ois_spread`.** The specs say "not `OVERNIGHT`: `E_INPUT`". A listed non-overnight record (`USD-TERM-3M`) gives `E_INPUT`; an unlisted string gives `E_SCHEMA`, as every other enum. `rates.curve.joint_bootstrap` keeps the bootstrap's rule (`E_SCHEMA` for anything not overnight).
3. **Empty `step_dates` in `rates.ois.fit_steps`.** Ruling D12 makes empty date lists `E_INPUT`; with `m = 0` the fit would otherwise be a one-quote flat rate. This build returns `E_INPUT`, checked before the quote count.
4. **Empty `dates` in `rates.ois.step_curve`, `rates.csa.discount`.** D12: `E_INPUT`, checked after the curve's own checks.
5. **Two forwards on one date in `rates.csa.discount`, two jumps on one date.** Forwards: `E_INPUT` (ambiguous data), after the `E_DOMAIN` checks. Jumps: already `E_INPUT` by the strictly increasing rule.
6. **`GLOBAL` in `rates.curve.joint_bootstrap`.** The system is block triangular, so Newton on all pillars equals the discount block's `GLOBAL` Newton followed by the projection block's solve. This build does exactly that; `max_repricing_error` is the larger of the two blocks.
7. **Order of `LOCKOUT` range check against business-day checks.** `n` is counted from the business days in `[start, end]` before `start`/`end` are checked, as the listed order puts `shift_days` first.
8. **`bond.yield.from_price` with a negative clean price** (`bonds_d-0048`: clean -1, dirty +1.06). `bonds.md` makes only `clean_price + accrued <= 0` an `E_DOMAIN`, yet the golden expects `E_DOMAIN`. This build also rejects `clean_price <= 0`, the stricter reading the golden implies.
9. **Asset swap floating dates on an end-of-month maturity.** `bonds.md` gives the end-of-month rule for the bond object only. The floating leg here steps back with plain month arithmetic (Feb 28 to Nov 28), which `bonds_d-0041` confirms.
10. **`bond.futures.conversion_factor` with delivery on or after maturity.** Not specified; `E_DATE_ORDER`, as the common bond check.
11. **Negative weight in `bond.fit.nelson_siegel`.** `E_DOMAIN`, checked after the positive-weight count and `tau`.
