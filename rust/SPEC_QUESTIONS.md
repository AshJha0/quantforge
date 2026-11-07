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
