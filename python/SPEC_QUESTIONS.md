# Spec questions from the Python implementation

Each item is a place where the spec is unclear, or where a golden case disagrees with it. Nothing here
was tuned to fit. The code follows the spec text, and the choice made is stated.

## Resolved by the spec corrections on `stage-a` (363e5a8)

- Q1, `add_tenor` end of month: `calendars.md` now says on or after the last business day, with a calendar
  month-end rule for `UNADJUSTED`. The code changed to match.
- Q2, `start == end` on `THIRTY_E_360_ISDA`: `daycount.md` keeps 0 and the golden case changed. No code change.
- Q3, moments at a large offset: `statistics-and-time-series.md` now specifies the shift by the first value,
  which the code already did.

No golden case is known to disagree with the spec now.

All of the earlier open choices, Q4 to Q21, are now settled by `specifications/01-core/rulings.md`, or by the corrected
contract and `root-finders.md`. The code follows those rulings.

## Closed by `limits.md` and rulings A1 to A6

- Q22, `sequence < 1` or an empty `series_id`: closed by A1, `E_SCHEMA`.
- Q23, lone surrogate in a record: closed by A4, `E_SCHEMA`.
- Q24, an instant outside years 1 to 9999: closed by A5, now `E_DATE_RANGE`.

## Closed by `limits.md` B1 to B5

- Q25, text too deep: closed by B2. A lexical scan runs before parsing, limit 64 on `document_text` and 80 on a case.
- Q26, `document_text` over the byte limit: closed by B1, `E_LIMIT` without parsing.
- Q27, `E_SCHEMA` with an over-long array: closed by B3. Every `E_SCHEMA` check now runs before the limit stage.
- Q28, nesting of record keys: closed by B4, every key.
- Q29, A5 and `chain`: closed by B5, it applies.

No question is open.

## Stage B: closed by `stage-b-rulings.md`

Q30 by B1, Q31 by B2, Q32 by the corrected `projection-and-fra.md`, Q33 by B9 (now checked in every `fx.*`), Q34 by B7,
Q35 by B5 (now on `fx.*` too), Q36 by B12, Q37 by B11, Q38 by B12, Q39 by B3, Q40 by B4, Q41 by B17.

Q42 is closed by B19: `start_months` runs from 0 to 1200, else `E_INPUT`.

No question is open.

## Stage C: choices made where the spec is silent

No golden turns on these, so none blocked work. Each is this build's reading, not a ruling.

- Q43, `SPOT` with `scale: null`: closed by C15, `E_INPUT`.
- Q44, order of the scale, positivity and delta checks in `vol.delta.*`, unlisted: scale, then `forward`/`vol`/`expiry_years`, then strike or delta.
- Q45, `vol.sabr.arbfree` where a call price reaches `f0`: closed by C16, `null`.
- Q46, `vol.svi.evaluate` with empty `log_moneyness`: closed by C17, `E_INPUT`.
- Q47, `usecase.vol_surface` checks not listed: `as_of` differing from the curve's, empty `slices`, or expiries out of order `E_INPUT`; target `strike`, `quantity` not above 0 `E_DOMAIN`, after the expiry check.
- Q48, `vol.ssvi.calibrate` has no listed check of `thetas`: it applies those of `vol.ssvi.evaluate`.
- Q49, `gamma` at exactly 1 in `vol.ssvi.calibrate`: the fit keeps `gamma` below 1, so a true 1 is only approached.

## Stage D wave 1 (open)

- QD1, `stage_b/ois.json` case `ois-0023` sends `ESTR` to `rates.ois.bootstrap` and expects `E_SCHEMA`. Stage D
  (`ois-curves.md` 1.1.0, contract 1.5.0) makes `ESTR` valid, so the code returns `ok` and this one old golden fails.
  The golden needs retiring or changing; the code follows the stage D spec.
- QD2, curve object check order: pillar checks run before jump checks (`curve-framework.md` lists no order).
- QD3, `rates.csa.discount`: two forwards on one date is not covered; the code gives `E_INPUT`. Curve checks run
  before the `fx` checks.
- QD4, `rates.basis.ois_spread`: the three curves are checked as curves before the shared `as_of` check.
- QD5, `rates.curve.joint_bootstrap`: the empty-list check runs first, then all OIS checks, then all term checks.
  `GLOBAL` applies to the OIS block; the term block is always solved after it, which ruling D9 says is the same answer.
- QD6, limits: `ois_quotes` and `term_quotes` are taken as quote lists, capped at 100 like `quotes`.
- QD7, `rates.ois.fit_steps`: quotes out of tenor order are caught by the pillar rule as `E_INPUT`.

## Stage D waves 2 and 3 (open)

- QD8, `bond.yield.from_price`: golden `bonds_d-0048` gives `clean_price` -1 (dirty +1.06) and expects `E_DOMAIN`,
  but the spec's check is `clean_price + accrued <= 0`. The code gives `E_DOMAIN` for `clean_price <= 0` as well.
- QD9, `bond.spread.asset_swap`: the quarterly floating dates are stepped back from `maturity` with the day clipped
  to the month. The bond object's month-end rule is not applied to them (golden `bonds_d-0041` needs that reading).
- QD10, `bond.fit.nelson_siegel`: a negative weight gives `E_DOMAIN`, and a `weights` list of the wrong length
  gives `E_INPUT`. Neither is listed.
- QD11, `bond.futures.conversion_factor`: a maturity on or before the first day of the delivery month gives
  `E_DATE_ORDER`, which is not listed.
- QD12, `fx.xccy.pv` does not check that `start` is on or after the curves' `as_of`. Bootstrap curve checks run
  before the quote checks.
- QD13, credit: a hazard curve with no pillars, dates not increasing after `as_of` (`E_INPUT`) or a survival
  `<= 0` (`E_DOMAIN`) is not specified. Hazard time counts from `trade_date`, and the hazard `as_of` is only used
  to check pillar order. `credit.cds.price` and `credit.index.intrinsic` apply the bootstrap's recovery check.
  The trade date is rejected when it equals any adjusted accrual start or any payment date.
- QD14, `eq.futures.basis`: the implied financing spread is searched in `[-0.5, 0.5]` ("as for borrow"), and
  gives `E_NOT_BRACKETED` outside it.
- QD15, `eq.trs.pv`: `end <= start` gives `E_DATE_ORDER`, which is not listed.
- QD16, `infl.*`: `seasonality` is taken as a required key that may be `null` (ruling C9 style).

## Stage D wave 3 (open)

- QD17, `mbs.cashflows`: golden `mbs_d-0011` has `wac` 0 and `net_coupon` 0.06 and expects `E_DOMAIN`, but the
  listed order puts `net_coupon > wac` (`E_INPUT`) first. The code checks `wac <= 0` before `net_coupon > wac`.
- QD18, `cmdty.storage.carry`: a forward price `<= 0` gives `E_DOMAIN` (it is not listed, and the log needs it).
- QD19, `rates.swaption.price`: the vol check runs after the expiry check and before the curve-derived forward check.

QD1 is closed by ruling D27: stage B `ois-0023` now sends `TONA`, and the code needs no change.

## Closed by rulings D31 to D46

- QD2 by D46 (pillars, then jump dates, then jump factors). QD3 by D42. QD8 by D43. QD10 by D37. QD11 by D35.
  QD12 by D39 (now `E_OUT_OF_RANGE`). QD14 by D32. QD15 by D41. QD17 by D44.
- QD13 in part: D36 requires every CDS curve's `as_of` to equal `trade_date`, so hazard time and the hazard
  `as_of` agree. Still open: the hazard pillar checks, and the code also rejects a trade date on a payment date.
- Also applied, with no earlier question: D31 (empty `steps` is flat, empty `dates` is `E_INPUT`), D33 (`wam` above
  1200 is `E_INPUT`), D34 (`mbs.price` with `1 + y/12 <= 0` is `E_DOMAIN`), D38 (fewer than three distinct
  maturities in `calib.curve.robust` is `E_SINGULAR`), D40 (`tenor_months` 1 to 1200 in caps and swaptions), and
  D45 (a listed convention of the wrong kind is `E_INPUT` in the stage D operations).

Still open: QD4, QD5, QD6, QD7, QD9, QD13 (in part), QD16, QD18, QD19.

## Closed by rulings D47 to D63

- QD4 by D48. QD5 by D62. QD6 by D49. QD7 by D51. QD9 by D62 (plain month steps). QD13 by D52 and D62
  (survival must be in `(0, 1]`; a trade maturity on or before `trade_date` is `E_INPUT`). QD16 by D54. QD18 by
  D58. QD19 by D57.
- Also applied: D54 `years` at most 100, and D59 `months` at most 1200 in `fx.xccy.*`. Both are now `E_INPUT`.

No stage D question is open.

## R1.7 batch mode (silent choices, no question open)

- R1-P1. Error results now always carry `"diagnostics": {}` (allowed: "`diagnostics` is an object and may always
  be present"). Without it, `--timings` would add a whole `diagnostics` object to error results, not one key, and
  `batch_check.py` timings_identity would fail. Applies to `run` and `batch` alike.
- R1-P2. BT5 reads each line with a cap of limit + 2 bytes (content, CR, LF); a capped read with no LF is over
  the limit and the rest of the line is drained in 1 MiB pieces, so at most limit + 2 bytes are held.
- R1-P3. `elapsed_ns` uses `time.monotonic_ns()`, from after the line (or for `run`, all of stdin) is read to
  just before the result is serialised.
- R1-P4. `--batch` is accepted only as the first argument and is rewritten to `batch`; so `--batch batch` and
  `batch --batch` are exit 64.
- R1-P5. R1-6 SOFR: the "USGS plus every Good Friday" calendar is used only inside `overnight.compound_dated`
  (business days, start/end check, `back`). Other SOFR uses (swap schedules, curves) keep plain `USGS`.

## Stage E (open)

Choices made where a stage E spec was silent or two rules pull apart. No golden depends on any of them.

- E-Q1 (E1, `slices` count). `arb-free-surfaces.md` lists "more than 100 slices: `E_LIMIT`" last, after the
  `E_INPUT` and `E_DOMAIN` slice checks, but `01-core/limits.md` B3 puts `E_LIMIT` before every rule check.
  Python follows B3: the slice cap (100), the grid cap (`log_moneyness`, 10,000) and the point cap (`points`,
  10,000) are checked at the gate, before any rule check. `vol.svi.fit_surface` caps `expiry_years` at 100 the
  same way.
- E-Q2 (E1, other arrays). The stage C cap of 100 (ruling C10, every `vol.` operation) would cap the E1 grid
  at 100, against the 10,000 stated in E1. Python lifts the stage C cap for the three E1 operations with a
  stated grid (`vol.svi.surface_check`, `vol.svi.fit_surface`, `vol.local.dupire`) and keeps it for the other
  E1 operations (`vol.forward.vol` expiries, `vol.smile.dynamics` strikes, `vol.volofvol.measure` vols), whose
  pages name no limit. A 100-long cap on a vol-of-vol series is tight; a ruling is asked for.
- E-Q3 (E7, arrays). `returns`, `prices` and `strip` "count towards limits.md like any array" (cli-contract,
  spec B): read as the 100,000 cap only, so the stage C cap of 100 does not apply to `vol.garch.*`,
  `vol.varswap.*` and `vol.vix.*`.
- E-Q4 (E7, `vol.varswap.fair_strike`). A replicated `fair_variance` below 0 (possible on a coarse strip with
  a large carry) has no `sqrt`. The page lists no check for it; Python returns `E_DOMAIN` on field `vols`
  rather than crash.
- E-Q5 (E7, `vol.vix.index`). The bracket rule (`N1 < N2`, `N1 <= 43200 <= N2`) is the only listed check;
  its order against the two term inputs' own checks is not stated. Python checks both terms first (near, then
  next), then the bracket, then a negative bracket under the root (`E_DOMAIN`).
- E-Q6 (E1, `vol.forward.vol`). No check on `expiry_years <= 0` is listed; Python takes them as given (a
  first expiry of 0 then divides by `T_1 - 0` only from the second point on).
- E-Q7 (E4, `rates.swaption.price_cube`). The domain checks (`alpha <= 0`, `beta` outside `[0, 1]`,
  `|rho| >= 1`, `nu < 0`) are applied to every node of the cube, not only to the interpolated parameters:
  `ratesvol_e-0017` puts a bad `rho` at a node the trade does not touch and expects `E_DOMAIN`. A bilinear mix
  of valid nodes is then valid too.
- E-Q8 (E4, `infl.cap.zc_price`). `(1 + K)^T` with `1 + K <= 0` has no real value for a non-integer `T`; the
  page lists no check. Python returns `E_DOMAIN` on `strike`, after the `BLACK_76` forward check and before
  the `years` check. The page's "strike <= 0" check is read as YoY only, so a negative ZC strike with
  `1 + K > 0` is priced under both models.
- E-Q9 (E4, `rates.cap.strip`). The page lists the strip's own checks but not their order against D7's
  (`start_months`, tenor range, `BLACK_76` strike and forwards). Python runs the strip checks (tenors, count,
  flat vols), then D7's.
- E-Q10 (E2, `vol.slv.leverage`, golden `slv_e-0006`). The spec's check is `x_min < ln(spot) < x_max`, else
  `E_INPUT`. The golden has `spot = 100`, `x_min = 4.6`, `x_max = 4.7`; `ln 100 = 4.60517` lies inside, and
  also inside the node interior (`x_1 = 4.60167`), so by the page the case is valid, but the golden expects
  `E_INPUT` ("spot outside the x grid interior"). Python follows the page and fails this one golden; a
  ruling or a corrected golden (for example `x_min = 4.61`) is asked for. No other check is added to fit it.
- E-Q11 (E2, array caps). `strikes` and `u` fall under the stage C cap of 100 (every `vol.` operation, as
  E-Q2); the E2 page names no limit except the SLV grid (`nx`, `nv` 1000, `nt` 10,000), checked at the gate.
- E-Q12 (E8, `credit.cdsoption.implied_vol`, golden `creditopt_e-0055`). The page says `E_DOMAIN` for a
  premium "at or below the zero-vol value, or at or above the upper bound". The golden is an out-of-the-money
  knock-out payer (forward 1.18877% against a 1.20% strike), so the zero-vol value is 0, with `premium = 1.0`
  on 10m notional. By the page that premium has an implied vol: Python finds 0.5397%, which reprices to
  1.0 within 1e-12. The golden expects `E_DOMAIN` ("premium below the zero-vol value"). Python follows the
  page and fails this one golden. Either the golden needs a premium at or below 0, or the page needs a stated
  lower vol bound (as E-B10 gives for the cap strip), which Python would then apply.
- E-Q13 (E8, `credit.copula.joint_default`). `default_probabilities` must hold exactly two values
  (`E_INPUT` otherwise); the page does not say, and this check runs first.

Closed by rulings (2026-11-08): E-Q1 by E-A34 (`E_LIMIT` at the gate, as built); E-Q2 by E-A35 (stage C cap
kept, vol-of-vol series raised to 10,000, now built); E-Q6 by E-A36 (first `expiry_years <= 0` is `E_DOMAIN`,
now built); E-Q10 by E-A24 (golden corrected); E-Q12 by E-B27 (golden corrected).
Closed by spec B rulings (2026-11-08): E-Q3 by E-B35 (as built); E-Q4 by E-B36 (as built); E-Q5 by E-B34
(bracket now checked first); E-Q8 by E-B37 (as built); E-Q9 by E-B40 (as built); E-Q13 by E-B40 (as built).
Still open: E-Q7 (cube domain checks on every node, as the golden needs) and E-Q11 (E2 array caps), both
upheld in effect by goldens and E-A35.

## Stage F

- F-Q1 (E1, NaN and infinity at public inputs). Until the shared golden lands, Python applies the rule in the
  library, at the outermost public call, before any other check: a NaN, +inf or -inf anywhere in an argument
  (floats, lists, tuples, dicts, dataclasses, NumPy float arrays) is `E_DOMAIN`, and -0.0 is accepted as 0.0.
  The field is the innermost dataclass field or dict key holding the value, else the parameter name. Calls
  between core functions are not checked again, so an intermediate infinity is still `E_NON_FINITE` at the
  output. Over the CLI no input can be NaN or infinite (cli-contract, JSON), so conformance results do not
  change. Asked: whether E1 runs before the E_SCHEMA and E_INPUT checks (Python: first), and which field a
  value inside a structured input names.
- F-Q2 (G4). Core modules are named by domain; `stage_d3` was split into `caps_swaptions`, `commodity` and
  `mbs`; `vol_e1` is `arb_surface`, `vol_e7` is `variance`, `credit_e8` is `credit_options`, `equity_d` is
  `equity_curves`. CLI handlers live in `cli/ops_<domain>.py` by verb prefix; the verb table is the registry.
- F-Q3 (F-1 tokens). Python converts `"NaN"`, `"Infinity"` and `"-Infinity"` anywhere in the inputs before the
  handlers read them, so the field types decide: a Real takes the value, any other type is `E_SCHEMA`. A
  free-text field (an id, a store record's `value`) holding exactly one of the three strings is therefore
  read as a number. Asked: whether such fields keep the string (Python would then convert per Real field).
- F-Q4 (R8). The estimate starts from Nelder-Mead on an unconstrained map, then Newton on the analytic score
  with the Hessian from central differences of the score (relative step 1e-5), until the largest relative
  step (omega scaled by the sample variance) is below 1e-12. Interior means 1e-6 from every bound.
- F-Q5 (Q4, XCCY `dR/dq`). The page says `dR/dq` is `-1` for rate and spread quotes. For an `XCCY`
  instrument the residual is `L_foreign` itself and the spread enters the model, so Python uses the true
  derivative, the spread annuity `sum (e - s)/360 D_f(e)` at the solution; `-1` would not match a
  bump-and-rebuild. Asked: confirm.
- F-Q6 (Q4, ruling F-26 on pillar curves). On `OIS_STEPS` a turn factor leaves every instrument on one side
  of its date unchanged, and Python sets those entries to exact zeros. On a pillar curve the unknowns are
  `ln D` (full `D`), so a turn moves `S = D/J` at every later pillar; with a non-local interpolation that
  moves sections on both sides of the turn, and the derivative is genuinely nonzero. Python reports the
  computed value there. Asked: whether F-26 is meant for step curves only.
- F-Q7 (Q4, IFT `dR/dx` stencil). `dR/dx` for the Jacobian is Richardson on central differences, starting
  at `h = 1e-4` and quartering until two estimates agree (to `1e-14/h + 1e-7` relative), because the
  monotone-convex curve is piecewise in its data and a fixed `1e-4` stencil can straddle a branch
  boundary. Newton itself uses one central difference at `1e-7`.

Ruled (2026-11-10): F-Q3 by F-38 (tokens become numbers only in Real fields and at the top level of an
any-JSON field; Python changed to match: the conversion moved from a pass over all inputs into the Real
readers, and `core.store.*` record `value`). F-Q5 by the amended `dR/dq` line of `joint-solve-and-funding.md`
(as built). F-Q6 by F-26 as amended (as built). F-Q7 by F-28 (as built). Also applied: F-35 (tension
spline small-`z` series with its `z^2` terms), F-36 (`side` is `PAY` / `RECEIVE` in `risk_f3`), F-39
(Monte Carlo `seed` a u64 string; `E_NOT_POSITIVE_DEFINITE`; duplicate opening position `E_INPUT`).
F-Q1, F-Q2 and F-Q4 have no ruling yet.

## Stage G (2026-11-11)

- G-Q1 (G2e, `capfloor_g-0040`). The case is described as "1 + K tau <= 0" and expects `E_DOMAIN`, but its
  inputs (`period_times` [1, 2, 3], `strike` -0.5) give `1 + K tau = 0.5 > 0` in both periods. The spec rule
  (`1 + K tau_i > 0`, else `E_DOMAIN`) therefore prices it (0.9793 on unit notional). Python follows the
  spec and fails this one case; asked: regenerate the case (for example `strike` -1.5) or amend the rule.
- G-Q2 (G2c). `E_NO_CONVERGENCE` also covers an objective that is flat at the low end in rounding noise
  (an in-the-money strip with zero targets): an interior minimum must lie below both ends by more than
  1e-12 relative and bracket a sign change of `F'`. Not exercised by the goldens.
- G-Q1 answered by G-38 (golden fixed to `strike = -1.0`); Python unchanged and passes it.
- G-Q3 (G-31 `E_LIMIT` goldens). `shortrate_g-0082` has no `short_rate` (required by `zcb` for
  every model) and `mcgreeks_g-0022` has an integer `seed` (a u64 string is required, E_SCHEMA),
  yet both expect `E_LIMIT`, which G-31 checks *after* `E_SCHEMA`. Python passes them by checking
  the stage G sizes on the raw document before the typed reads (`registry.EARLY_LIMITS`). Asked:
  either fix the two inputs, or amend G-31 to say the stage G sizes come first.
