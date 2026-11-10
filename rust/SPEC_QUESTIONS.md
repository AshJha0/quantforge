# Spec questions from the Rust implementation

Each entry is a place where the specs and the golden cases disagreed, or where the spec leaves a choice open.
Nothing here was tuned to fit: the code follows the spec text.

## Resolved at `stage-a` 363e5a8

- `add_tenor` with `end_of_month`: `calendars.md` now says "on or after the last business day", with a separate
  `UNADJUSTED` rule. The code follows the new text.
- `THIRTY_E_360_ISDA` with `start == end`: the spec keeps 0, and the golden case was corrected.
- `implementations.json` on Windows: the runner now resolves the path, and no config copy is needed.
- Shift by the first value: now required for `summary`, `covariance`, `ols`, `autocorrelation` and `ar1`.

- The `implementations.yaml` name in `cli-contract.md` is corrected to `.json`.
- The silent points listed here earlier are settled by `specifications/01-core/rulings.md`, and the code follows it.
  The one change of a stated choice was S2: `ols` on constant `y` now gives a `null` `r_squared`.

## Closed at `stage-a` 3737bb5

- `core.store.*` order of checks: ruling A2 replaced "before anything else", and the code follows it.
- `core.store.*`, `sequence` below 1 is `E_SCHEMA`: confirmed by A1.
- `core.store.replay`, `head` is the whole log: confirmed by A6.

## Closed at `stage-a` bb663d6

- `E_LIMIT` on `document_text`: B1 and B2 put size and a lexical depth scan before parsing, and the code follows them.
- `dimensions` of 65 with a large `count` is `E_LIMIT`: confirmed by B3.

## Stage B, closed at `stage-b` ddf2b18

`specifications/stage-b-rulings.md` settles the stage B readings listed here earlier, and the code follows it. The
changes of a stated choice were B0 (spot in OIS), B5, B7, B8, B9 and B10. B11 and B12 also reordered `calib.fit`.
`hedge.solve` now gives `E_NO_CONVERGENCE` if its result fails the first-order conditions (B13).

## Stage B, closed at `stage-b` 9615ef5

- `fx.curve.implied` limit on `points`: confirmed by B21.
- `newton` bracket with an exact zero at an end: confirmed by B23.

## Closed on `stage-c-rust`

- B24: every operation that works on an array now stops at the limit after its typed reads, before any work.

## Stage C, readings taken where the spec is silent

None of these is reached by a golden. Rulings C15 and C16 settled the readings on `scale` and on `vol.sabr.arbfree`; C17 settled empty lists.

- `vol.svi.calibrate`, `vol.sabr.calibrate`: a `weights` of another length is `E_INPUT`, and lengths are checked before order.
- `risk.vol.surface_vega`: a position with `forward`, `strike`, `discount_factor` or `expiry_years` not above 0 is `E_DOMAIN`.
- `usecase.vol_surface`: empty or out-of-order `slices` is `E_INPUT`; a slice expiry on or before `as_of`, or a target `strike` or `quantity` not above 0, is `E_DOMAIN`. The target check runs before any fit.

## Stage D wave 1, readings taken where the spec is silent

- **Conflict:** `stage_b/ois.json` case `ois-0023` still expects `ESTR` in `rates.ois.bootstrap` to be `E_SCHEMA`, but stage D (`ois-curves.md` 1.1.0, contract 1.5.0) accepts `ESTR`. Rust follows stage D, so this one old case fails. The oracle needs to retire or update it.
- `rates.ois.compound_dated`: an unknown `convention` id is `E_SCHEMA`; a known non-overnight id (such as `USD-TERM-3M`) is `E_INPUT`, as golden `compound_d-0030` shows.
- Jumps: date checks (`E_INPUT`) run before factor checks (`E_DOMAIN`). On a curve object they run after the pillar checks.
- `rates.ois.step_curve`: an empty `steps` is `E_INPUT` (ruling D12 exempts only `jumps`). An empty `dates` is `E_INPUT` and is the first rule check (as C17).
- `rates.csa.discount`: two forwards on one date are `E_INPUT`. The curve's own checks run before the CSA checks.
- `rates.curve.joint_bootstrap`: `GLOBAL` runs Newton on all OIS pillars, then the projection block on that curve (the system is block triangular, D9). Optional `jumps` are not read here, as the spec does not list them.
- `calib.curve.robust`: if the inlier set is too small to fix the betas, or the Newton active set does not settle, the result is `E_NO_CONVERGENCE`.
- Limits: `ois_quotes` and `term_quotes` take the 100-item quote-list limit, and `projection_a` and `projection_b` take the 100-pillar curve limit. `fixings`, `knots`, `maturities`, `dates` and `steps` take only the general array limit.

## Stage D wave 2, readings taken where the spec is silent

- `bond.yield.from_price`: a `clean_price <= 0` is `E_DOMAIN` as well as `clean_price + accrued <= 0`. Golden `bonds_d-0048` (clean -1, dirty above 0) expects `E_DOMAIN`.
- `bond.spread.asset_swap`: floating dates step back by plain month arithmetic, with no month-end rule even for a month-end maturity. Golden `bonds_d-0041` needs this. The spec says only "unadjusted".
- `bond.fit.nelson_siegel`: a `weights` of another length is `E_INPUT`, and a negative weight is `E_DOMAIN`. The `tau` check runs first.
- `bond.futures.conversion_factor`: whole months from the first of the delivery month, less one if the maturity day is earlier (it never is). A maturity before delivery is `E_INPUT`. `bond.futures.basis` with no bonds is `E_INPUT`.
- `fx.xccy.bootstrap`: a known convention id other than `SOFR` (domestic) or `ESTR` (foreign) is `E_INPUT`, and an unknown id is `E_SCHEMA`. A `start` before `as_of` is `E_OUT_OF_RANGE`. `months` above 1200 is `E_INPUT`. `fx.xccy.pv` uses the USGS and EUTA joint calendar without convention inputs.
- Credit: hazard pillars that do not increase or do not follow `as_of` are `E_INPUT`. A survival outside `(0, 1]` is `E_DOMAIN`. A maturity on or before the trade date is `E_INPUT`. In `credit.curve.composite`, `scale <= 0`, a negative weight, or a weight sum `<= 0` is `E_DOMAIN`. Discount nodes for the integration are the discount curve's pillar dates.
- Equity D5: `eq.futures.basis` solves the financing spread on `[-1, 1]` and gives `E_NOT_BRACKETED` outside it. In `eq.dividend.implied` an empty `futures` list is `E_INPUT`. `eq.borrow.implied` with `expiry <= as_of` is `E_DATE_ORDER`. In `eq.index.rebalance`, the duplicate check runs before `divisor <= 0` (`E_DOMAIN`). In `eq.trs.pv`, `end <= start` is `E_DATE_ORDER`, and the side values are `RECEIVE_EQUITY` and `PAY_EQUITY`.
- Inflation D6: `index_ratio` divides by the input `base_cpi`, not by `exp(ln base_cpi)`, and the fixed leg uses `powf`. Golden `inflation_d-0009` (pv near 0) needs this to 1 ulp. `seasonality` is a required key that may be `null`. `years` above 100 is `E_INPUT`. `base_cpi <= 0` or `base_ref_cpi <= 0` is `E_DOMAIN`. Two fixings for one month are `E_INPUT`.

## Stage D wave 3, readings taken where the spec is silent

- D27: no code change was needed. `TONA` is unlisted, so it is already `E_SCHEMA`. The earlier `ois-0023` conflict is closed.
- `mbs.cashflows`: `wac <= 0` (`E_DOMAIN`) is checked before `net_coupon > wac` (`E_INPUT`). Golden `mbs_d-0011` (wac 0, net coupon 0.06) expects `E_DOMAIN`, while the spec lists the `E_INPUT` checks first. `wam` above 1200 is `E_INPUT`.
- `mbs.price`: `1 + y/12 <= 0` is `E_DOMAIN`.
- `rates.cap.price` and `rates.swaption.price`: `tenor_months` outside 1 to 1200 is `E_INPUT`. A swaption `vol < 0` is `E_DOMAIN`. Under `BACHELIER`, any strike and forward are accepted.
- `cmdty.curve.forward`: `seasonality` is a required key that may be `null`, and an empty `quotes` list is `E_INPUT`. In `cmdty.storage.carry`, a forward price `<= 0` is `E_DOMAIN`.

## Stage D, closed by rulings D31 to D46 (merged from `stage-d` 2836b6b)

- Closed, and the code changed:
  - D31: an empty `steps` is now a flat curve.
  - D32: `eq.futures.basis` now searches `[-0.5, 0.5]`.
  - D35: a conversion-factor maturity before delivery is now `E_DATE_ORDER`.
  - D36: CDS curves must have `as_of = trade_date`, else `E_INPUT`.
  - D37: in `credit.index.intrinsic` and `bond.fit.nelson_siegel`, a negative weight or a zero sum is `E_DOMAIN`.
- Closed, confirming the reading already taken: D33 (`wam` above 1200), D34 (`mbs.price` domain), D38 (robust singular), D39 (xccy `start`), D40 (`tenor_months`), D41 (TRS dates), D42 (duplicate forwards and fixings), D43 (`bonds_d-0048`), D44 (`mbs_d-0011`), D45 (convention ids), D46 (jump check order), D12 (empty `dates`).
- All of the entries above that were still open are now answered by rulings D47 to D63 (merged from `stage-d` b566056). Each one confirms the reading already taken, with no code change:
  - D62: asset-swap dates (`bonds_d-0041`), the joint `GLOBAL` path, robust non-convergence and the CDS integration nodes.
  - D63: `jumps` in `joint_bootstrap`.
  - D49: the quote-list limit.
  - D52: the credit checks.
  - D53: the equity checks.
  - D54: `seasonality` and `years`.
  - D55: `BACHELIER` strikes.
  - D59: `months` in xccy.
  - D60: the `inflation_d-0009` tolerance is widened, so the `powf` and `base_cpi` choice no longer matters.

No stage D question is open.

## R1.7 batch mode (silent choices, 2026-11-07)

- **Error results always carry `diagnostics: {}`.** `batch_check.py` timings_identity strips only `elapsed_ns`, so an error result that gained `diagnostics` under `--timings` left an empty object behind and failed. The contract allows `diagnostics` on every result ("may always be present"), so the Rust build now writes it on every error result, with or without the flag. Suggest the spec state this, or have the checker drop an empty `diagnostics`.
- **BT1 CR removal:** exactly one CR before the LF is removed (v0.4 removed every trailing CR/LF). A last line without LF keeps a trailing CR removed too, as before.
- **BT5 memory:** the reader keeps at most 16,777,217 bytes (room for the CRLF's CR) and drops the rest of the line; the `E_LIMIT` message is "the line is longer than 16 MiB". Under `--timings` it carries `elapsed_ns` like any other result.

## R2.1 par and key-rate risk (silent choices, 2026-11-07)

- **Optional keys:** `bump_bp` (default 1) and `scheme` (default `CENTRAL`) may be absent. `key_dates` may be absent, which counts as `null`. A `key_dates` that is neither `null` nor an array of dates is `E_SCHEMA`.
- **Mode against key_dates:** `TRIANGULAR` with `null` key_dates is `E_INPUT`, the same as an empty list. `PILLAR` with an array is `E_INPUT`, as specified. Both come after the `bump_bp` and `notional` checks (`E_DOMAIN`).
- **Jacobian above the diagonal** is set to exactly 0 rather than computed. The sequential bootstrap already gives 0 there; setting it makes "exactly 0" hold by construction.
- **Convention check** applies to `risk.curve.par` only. `risk.curve.key_rate` takes a curve object that carries no convention, so an `OIS` product is priced on it whatever its convention.
- **Bond value** uses the bond pricer's `dirty`, scaled by `notional / 100`, on the bumped discount function with the curve's `as_of` as time origin. Settlement before `as_of` is `E_OUT_OF_RANGE`, as `bond.price.from_curve`.

## Stage E (silent choices, 2026-11-08)

E1 and E7 pass every golden (surf_e 28, lv_e 39, garch_e 27, varswap_e 31, vix_e 14). Readings taken where the spec is silent:

- **E1 `reject`** is required (`E_SCHEMA` when missing), as ruling E-A18 settled.
- **E1 `vol.svi.fit_surface` row count:** a `total_variance` with a different number of rows from `expiry_years` is `E_INPUT` (the stage C "ragged rows" rule), checked after the expiry order.
- **E1 `vol.forward.vol` expiry sign:** no `expiry_years <= 0` check is specified, so none is made; strict increase is the only expiry rule. Suggest the spec say whether `T_0 <= 0` is `E_DOMAIN`.
- **E1 enums:** an unknown `rule`, `option_type` or `method` is `E_SCHEMA`, as for enums elsewhere in the contract.
- **E1 `vol.smile.dynamics` order:** empty `strikes` (`E_INPUT`), then the SVI domain, then the positivity of `expiry_years`, `spot`, `spot_shifted` and strikes (`E_DOMAIN`).
- **E7 `vol.vix.term_variance` with no OTM put or call selected:** settled by ruling E-B15, `E_INPUT` (implemented).
- **E7 strip order:** the strip may come in any order; the build sorts it by strike. Duplicates are found after sorting.
- **E7 `vol.vix.index` order:** after schema reads of both terms, the `N1 < N2`, `N1 <= 43200 <= N2` bracket is checked before either term's rule checks.
- **E7 zero-bid counter:** "consecutive" resets on any quote with a non-zero bid; `K0` itself does not count towards either side's run.
- **E3 check order:** the common checks (`spot`, `expiry_years`, `vol` above 0) come first, then `strike` and `notional`; in `fx.delta.to_strike` the sign of the delta comes before its reach; in `fx.smile.from_quotes` the `delta` interval comes before the wing vols.
- **E3 PA call maximum:** a delta exactly equal to the maximum is `E_DOMAIN` (ruling E-A10 "at or above"). The peak is found by bisection on `d2`, so a delta within a few ulps of the maximum may land on either side.
- **E4 cube domain** is checked on every node (not only the interpolated point), after the shape, node-order and grid checks; then strike and forward. A one-node axis needs the trade exactly on that node.
- **E4 cube `expiry_months < 1`** is `E_INPUT`, as D7's swaption.
- **E4 strip schedule:** every cap uses the prefix of the longest cap's quarterly schedule (cap `k` holds the first `M_k/3` caplets). `start_months < 1` is `E_INPUT`, as D7, checked after the flat-vol checks. A bracket that cannot reach a cap price below vol 1e6 is `E_NO_CONVERGENCE` (unspecified; cannot occur for a finite price below the bound).
- **E4 bond futures:** a negative `vol` is `E_DOMAIN`; `ctd_yield` and `ctd_modified_duration` are not checked (the spec lists no rule), so a zero gives an infinite `yield_vol`. Suggest the spec require both above 0.
- **E2 `slv_e-0006`:** settled by ruling E-A24 (the written rule stands, the golden was corrected); passes with no code change.
- **E2 Heston small `xi`:** `b - d` is computed as `-xi^2 (iu + u^2)/(b + d)` and `ln((1 - g e)/(1 - g))` by a complex `log1p`, which is algebraically the [Alb07] form with no cancellation; the plain form was 8e-8 off at `xi = 1e-3` (`heston_e-0011`), outside the 1e-8 target.
- **E2 SLV check order:** slices, then grid sizes (`E_INPUT`), then spot and expiry (`E_DOMAIN`), then the `ln(spot)` interior rule (`E_INPUT`), then `v_max` (`E_DOMAIN`), then the Heston domain.
- **E6 `risk.corr.nearest` stop:** Dykstra iterations stop when no entry of `Y` moves by more than 1e-13 (cap 100,000 iterations, then `E_NO_CONVERGENCE`). Eigenvectors by cyclic Jacobi.
- **E6 `risk.corr.implied` index vol:** `index_vol <= 0` is `E_DOMAIN` with the member vols (the spec names only member vols).
- **E8 `creditopt_e-0055`:** settled by ruling E-B27 (golden corrected to a receiver below its zero-vol value); passes with no code change.
- **E8 copula inputs:** `default_probabilities` must hold exactly two values (`E_INPUT`); `degrees_of_freedom` is read for `STUDENT_T` only and ignored for `GAUSSIAN`. `credit.lhp.loss_cdf` with an empty `losses` is `E_INPUT`.
- **E8 numerics:** bivariate normal by the Drezner-Wesolowsky `sin` substitution (16 panels of 20-point Gauss-Legendre); Student t CDF and bivariate t as normal mixtures over `ln(W/nu)` (120 panels, normalised by the same rule); t quantile by bisection; normal quantile AS241 plus one Newton step.
- **E5 readings:** `CONTINUOUS` averaging with a non-empty `fixing_years` is `E_INPUT`; fixings are checked before the common `E_DOMAIN` checks. Kirk needs vols above 0 and correlation in `[-1, 1]` (`E_DOMAIN`), unstated in the spec. Basket length mismatches are `E_INPUT` with the correlation checks. CRR `steps` above 20,000 is `E_LIMIT`; FD `nx` above 1,001 or `nt` above 10,000 is `E_LIMIT`, `nt < 1` `E_INPUT`, `width <= 0` `E_DOMAIN`.
- **E-B31/E-B32/E-B33 (second audit):** the nearest-matrix stop (no entry moves more than 1e-13) is tighter than the relative 1e-12 of E-B31 and passes every golden, including the 20 by 20; the strip searches `[1e-10, 5]` (Black) or `[1e-10, 0.5]` (Bachelier), refusing below with `E_ARBITRAGE` and above with `E_DOMAIN`; implied correlation refuses a negative weight or fewer than two positive weights with `E_DOMAIN`, and a zero weight drops its name.
- **Spec A second audit (E-A26, E-A28, E-A30):** Lewis integral now 1024 Gauss-Legendre nodes on `[0, 200/sqrt(min(T, 1))]` (short-expiry goldens at 7 and 2 days pass); lookback refuses `|b| <= 1e-8 v^2`; BAW refuses `r <= 0`. No stage E question is open: the two spec/golden conflicts Rust raised (`slv_e-0006`, `creditopt_e-0055`) were settled by E-A24 and E-B27.
- **Cross-language rulings E-A34 to E-A40:** applied. `E_LIMIT` stays at the gate (E-A34). The C10 cap of 100 now also covers `exotic.*` lists, `expiry_years`, `u`, `fixing_years`, `forwards` and `correlation`, while the stated limits win: check grid and Dupire points 10,000, vol-of-vol series 10,000 (E-A35). A forward-vol first expiry at or below 0 is `E_DOMAIN` (E-A36). SLV puts every `E_INPUT` rule before `E_DOMAIN` (E-A37). Asian checks follow input order, common checks first (E-A38). Kirk and basket checks upheld (E-A39); FD codes upheld (E-A40). The earlier readings for these points are superseded.
- **Cross-language rulings E-B34 to E-B40:** applied. VIX bracket first (E-B34, already so); no C10 cap on E7 lists (E-B35, already so); replicated variance below 0 is `E_DOMAIN` (E-B36); ZC order forward, `1 + K`, years, with negative `K` priced (E-B37); E4 option vols `>= 0` and CTD inputs above 0 after the premium bounds (E-B38); implied-correlation `E_DOMAIN` order (E-B39); CDS implied-vol knock-out rule before the dates (E-B40).
- **`rulings_e_b-0008`, `-0009`, `-0015`:** settled; spec B rebuilt them from the proper bases (5b58e2d) and they pass with no code change. No stage E question is open.

## Stage F, closed by `stage-f` 968952b (F-1 to F-4)

- E1 order: F-2 puts the finite rule after `E_SCHEMA` and `E_LIMIT` and before every own check;
  the CLI follows it. Library functions check finiteness first as well.
- E1 encoding: F-1 tokens are read at the CLI boundary. A string field whose value is literally
  `"NaN"` would also be read as a number and be `E_SCHEMA`; no spec field takes free text where
  that could occur, so it is noted here, not asked.
- `-0.0`: F-3, same result as `+0.0`; the `negative_zero` cases pass with no change.
- Library `field` for a non-finite value inside a struct is the argument name (`self` for a
  receiver); F-4 does not fix the field, so this stays a Rust choice.

## Stage F wave 1a (F6, Q1), choices made where the spec is silent

- Q1 `TENSION_SPLINE` and `HYBRID` read `tension` and `step_end` from the same object as
  `interpolation` (the curve object, or the top level of a bootstrap). The order of checks is
  `tension` missing `E_INPUT`, out of `(0, 1000]` `E_DOMAIN`, then the pillar checks; a
  `step_end` that is not a pillar date is `E_INPUT` after the pillar order checks.
- Q1 bootstrap: for the four stage F methods `SEQUENTIAL` runs the same global Newton solve as
  `GLOBAL` (ruling F-21 allows either route to the unique solution).
- R8 `vol.garch.estimate`: the search is the stage E multi-start Nelder-Mead (27 starts for
  Student-t, over `nu` in 5, 10 and 30), then Newton on the exact gradient with a central-difference
  Hessian (relative step 1e-5). The Student-t golden series take about 10 s each in a release
  build; a faster start would come from the Gaussian estimate.
- R7: `h_K` is bisected until the bracket cannot shrink, which is within 1e-15 relative.

## Stage F wave 1b (Q4 joint solve), choices and findings

- `rates.curve.joint_solve` is solved block by block (F-25): Newton on each curve's own
  unknowns with a central-difference block Jacobian and backtracking, to 1e-16 where reachable.
  Starting point as the spec, except `XCCY`, which starts from its foreign projection curve's
  discount factors at its pillars (the "first quote" of an xccy curve is a spread, not a rate).
- IFT Jacobian: `dR/dx` by a five-point stencil per unknown, with a step that starts at 1e-5 and
  shrinks by 4 until two steps agree within residual roundoff (4e-9 times 1e-5/h, plus 1e-6
  relative). Then block forward substitution, so cross-curve zeros are exact (F-25).
- Finding for the held-back four-curve case: the 2e-3 mismatch has two causes, neither in the
  spec. (1) The h = 1e-4 Richardson reference crosses a monotone-convex branch boundary for the
  `SOFR-3M` and `SOFR-2Y` columns (one-sided derivatives of the turn factor in `SOFR-3M` are
  0.18997 for |h| up to 1e-5, but 0.17804 at +1e-4). (2) A fixed 1e-5 five-point `dR/dx`
  stencil also crosses a boundary in one SOFR pillar column, which put `turn` / `SOFR-1M` off by
  7.5e-4 (0.11714 against 0.11790 on both sides). With the adaptive stencil the Rust IFT
  matches small-step bump-and-rebuild (h = 1e-6 central, or 1e-5 / 5e-6 Richardson) to about
  2e-8 above the `jacobian` limit, and that remainder is the spread between the references.
- `XCCY` `dR/dq` is `sum alpha_i D_f(e_i)` on the solved foreign curve, not `-1`. The text says
  "-1 on the diagonal for rate and spread quotes", but the xccy residual is the leg value with the
  spread inside it, so its exact derivative is the annuity.
- F-26 with `ln D` pillar unknowns: on a pillar curve, holding the full `ln D` at pillars while
  the turn's `ln factor` moves changes `S = D/J` at pillars after the turn, so an instrument whose
  dates all sit before the turn but inside the section that ends at the first pillar after it
  (or anywhere, for a non-local method) does move. Rust reports the honest `d model / d ln factor`
  (it is the `dR/dx` column), so those zeros are not forced. On `OIS_STEPS` curves the zeros are
  exact. The goldens only have steps-curve turns, so nothing fails today.

## Stage F wave 2 (F3), choices and findings

- `risk.book.ois_sensitivity`: reverse-mode AAD on a tape (`aad.rs`), one sweep per residual
  for `dR/dx` and one per swap for `x_bar`, then `(dR/dx)^T lambda = x_bar` (F-29). The zero
  Jacobian solves `dR/dx` by forward substitution when it is exactly lower triangular, so the
  F-30 zeros are exact. The tape mirrors `LOG_LINEAR_DF` and `LINEAR_ZERO`; other methods are
  `E_INPUT` for now (the spec allows any `rates.ois.bootstrap` method; the goldens use log-linear).
- `risk.curve.cross_gamma` goldens spell the OIS `side` as `PAYER` / `RECEIVER`, but
  `ois-curves.md` and every older OIS trade golden use `PAY` / `RECEIVE`. Rust reads both
  spellings for this operation only. Spec: please pick one.
- Cross gamma at 1 bp on a 1e6 notional loses about 1.5e-10 to binary64 cancellation if the
  formula is summed directly, which is over the `interpolation` 1e-10 limit. On log-linear and
  linear-zero curves Rust evaluates the same formula in closed form per exponential term
  (`4 sinh^2(g h/2)` and `sinh(g_i h) sinh(g_j h)`), which matches the 40-digit goldens. Other
  products and interpolations use the direct formula.
