# Stage D rulings and oracle coverage

Spec version 1.0.0. Normative: this page is part of every stage D spec, and wins where it is more exact.

## Rulings

| # | Point | Ruling |
|---|---|---|
| D1 | ESTR convention | Spot lag 2, payment lag 2, as Strata 2.12.78 `EUR-FIXED-1Y-ESTR-OIS`, read from its bytecode. Lag 1 is a wrong-convention check |
| D2 | Jump date | A jump multiplies discount factors for dates strictly after its date, as QuantLib. On its own date it does not apply |
| D3 | Lockout `k` | ARRC rule: the fixing of `d_{n-k}` applies from `d_{n-k}` to the end. QuantLib's `lockoutDays` is this `k` minus 1 |
| D4 | `shift_days` | `NONE`: must be 0. `LOCKOUT`: 1 to `n-1`. Others: 0 or more. Else `E_INPUT` |
| D5 | `start`, `end` of dated compounding | Business days of the index calendar, else `E_INPUT`. No adjustment is made for the caller |
| D6 | Step date | A step takes effect on its date. A step on `as_of` is `E_INPUT`: use `base_rate` |
| D7 | Step fit | `b_j < p_j <= b_{j+1}` makes the fit triangular and unique; anything else is `E_INPUT`, not a least-squares fit |
| D8 | Fallback spreads | ISDA's fixed values of 2021-03-05, as `overnight-compounding.md`. Only those eight IBORs |
| D9 | Joint bootstrap | Block triangular, so the joint and two-step solves agree to solver tolerance. Goldens use QuantLib's two-step build |
| D10 | Optional `jumps`, `weights` | May be absent. `null` is `E_SCHEMA`, as C9. `jumps` is required (may be empty) in `rates.ois.step_curve` and `rates.ois.fit_steps`; `fx` is required (may be `null`) in `rates.csa.discount` |
| D11 | Time | Curve time `(date - as_of)/365` throughout, as stage B. Operations with `*_years` take them as given |
| D12 | Empty arrays | `E_INPUT` for quote, fixing, date, maturity and knot lists. `jumps` may be empty |

| D13 | Bond dates | Coupon dates unadjusted, no calendar, no odd first coupon, face 100. Business-day rolls on bond payments are not in stage D |
| D14 | Bond time | Yield exponents count whole periods plus `w`; curve and Z-spread time is `(d - as_of)/365`; the fit uses `(d - settlement)/365` |
| D15 | Repo | ACT/360 simple; coupons inside the term reinvested at the repo rate. `gc_rate` key required, may be `null` |
| D16 | CTD | Highest implied repo. Conversion factors are inputs to `bond.futures.basis`, so a factor error does not move the basis case |

| D17 | Cross-currency schedule | Quarterly, `MODIFIED_FOLLOWING` on the joint calendar, ACT/360, constant notional with exchanges. `start` must be a joint business day. Domestic USD, foreign EUR only |
| D18 | NDF forward | At the payment date, from the two curves; no spot lag and no convexity. A fixing on or before `as_of` must be given |

| D19 | CDS trade date | Not on an adjusted coupon date (`E_INPUT`); that edge moves accrual start and has no outside check here |
| D20 | Hazard pillars | At each quote's maturity (ISDA). QuantLib's `SpreadCdsHelper` puts them a day after the last payment; that is a wrong-convention check here |
| D21 | Observation day | Coupon survival and accrual-on-default end at payment date minus 1 day, as QuantLib's `IsdaCdsEngine` source. Read from QuantLib 1.44 `isdacdsengine.cpp` |

| D22 | Borrow and financing | Flat continuous rates on top of the funding curve, in `C`. Term structures of borrow are later work |
| D23 | Dividend futures | Fair price is the sum of known index dividend points in the period, ex-dates inclusive at both ends; no discounting (futures, deterministic dividends) |
| D24 | TRS | One period, paid at `end`, dividends paid at `end`. `current_rate` key required |

| D25 | CPI lag | `base_month` carries the swap lag; linkers use the three-month TIPS reference rule. Integer-year ZCIS only |
| D26 | Seasonality | Multiplicative, normalised to the base month's calendar month, so pillars are untouched |

| D27 | Stage B case `ois-0023` | It expected `ESTR` to be `E_SCHEMA`; D1 lists `ESTR`, so that expectation is retired. The case now sends `TONA`, still unlisted, and keeps `E_SCHEMA`. Changed in `gen_stage_b.py` and `stage_b/ois.json`; nothing else in stage B moves |

| D28 | Cap and swaption timing | Caplets fix at accrual start, swaptions exercise at swap start: no fixing or notice lag in stage D |

| D29 | Commodity curve | Additive log seasonality by calendar month, linear in month index between quotes, no extrapolation |

| D30 | MBS | PSA age is `age + k` for month `k`; net coupon at most WAC; delay measured in 30-day months; no servicing strip or guarantee fee beyond the WAC-net gap |

| D31 | Empty `steps`, `dates` in `rates.ois.step_curve` | `steps: []` is a flat curve at `base_rate`. `dates: []` is `E_INPUT`. Cases `rulings_d-0001`, `-0002` |
| D32 | No root for an implied rate in `eq.futures.basis`, `eq.borrow.implied` | Search `[-0.5, 0.5]` only; otherwise `E_NOT_BRACKETED`. Case `rulings_d-0003` (root near -0.65) |
| D33 | `wam` above 1200 | `E_INPUT`, not `E_LIMIT`: `01-core/limits.md` lists no MBS limit. Case `rulings_d-0004` |
| D34 | `mbs.price` with `1 + y/12 <= 0` | `E_DOMAIN`. Case `rulings_d-0005` |
| D35 | `bond.futures.conversion_factor` with maturity before the delivery month | `E_DATE_ORDER`. Case `rulings_d-0006` |
| D36 | CDS curves' `as_of` | Both `discount` and `hazard` (and every hazard in `credit.index.intrinsic`) must have `as_of = trade_date`, else `E_INPUT`. Cases `rulings_d-0007`, `-0008` |
| D37 | Weights in `credit.index.intrinsic`, `credit.curve.composite`, `bond.fit.nelson_siegel` | A negative weight, or weights summing to 0: `E_DOMAIN`. Wrong length: `E_INPUT`. Cases `rulings_d-0009` to `-0012` |
| D38 | `calib.curve.robust` when the maturities cannot fix three betas | `E_SINGULAR`. Case `rulings_d-0013` |
| D39 | `fx.xccy.bootstrap`, `fx.xccy.pv` with `start` before `as_of` | `E_OUT_OF_RANGE`. Case `rulings_d-0014` |
| D40 | `tenor_months` in caps and swaptions | 1 to 1200, else `E_INPUT`. Cases `rulings_d-0015`, `-0016` |
| D41 | `eq.trs.pv` with `end <= start` | `E_DATE_ORDER`. Case `rulings_d-0017` |
| D42 | Two forwards on one date in `rates.csa.discount`; two fixings for one month in `infl.linker.price` | `E_INPUT`. Case `rulings_d-0018` |
| D43 | `bond.yield.from_price` with `clean_price <= 0` | `E_DOMAIN`, as well as `clean_price + accrued <= 0`. `bonds.md` corrected; case `bonds_d-0048` |
| D44 | `mbs.*` check order | `wac <= 0` (`E_DOMAIN`) comes before `net_coupon > wac` (`E_INPUT`); `wam`, `age` first. `mbs.md` corrected; case `mbs_d-0011` |
| D45 | Convention ids | An unlisted id is `E_SCHEMA`; a listed id of the wrong kind (`USD-TERM-3M` where an overnight index is needed, or not `SOFR`/`ESTR` in `fx.xccy.*`) is `E_INPUT`. Case `compound_d-0030` |
| D46 | Check order for curves with `jumps` | The curve's pillar checks first, then jump dates (`E_INPUT`), then jump factors (`E_DOMAIN`). In `rates.ois.bootstrap` its own list stands (jumps first) |

| D47 | Overnight conventions in `rates.basis.ois_spread`, `rates.curve.joint_bootstrap` | Any `OVERNIGHT` record, `ESTR` included. Case `rulings2_d-0001` |
| D48 | `rates.basis.ois_spread` check order | Each curve's own checks first, then the shared `as_of`. Case `rulings2_d-0002` |
| D49 | `ois_quotes`, `term_quotes` | Quote lists: 100 at most, else `E_LIMIT`. Case `rulings2_d-0003` |
| D50 | A lookback or shift reaching outside the calendar range | `E_DATE_RANGE`. Case `rulings2_d-0004` |
| D51 | `rates.ois.fit_steps` quotes out of tenor order | `E_INPUT`, by the pillar rule. Case `rulings2_d-0005` |
| D52 | Hazard curve checks | Survival outside `(0, 1]`: `E_DOMAIN`. Pillars not strictly increasing after `as_of`: `E_INPUT`. A trade maturity on or before `trade_date`: `E_INPUT`. Cases `rulings2_d-0006` to `-0008` |
| D53 | Equity checks | Empty `futures`: `E_INPUT`. `eq.borrow.implied` with `expiry <= as_of`: `E_DATE_ORDER`. `eq.index.rebalance`: duplicate ids (`E_INPUT`) before `divisor <= 0` (`E_DOMAIN`). Cases `rulings2_d-0009` to `-0011` |
| D54 | `seasonality`; `years` | `seasonality` is a required key that may be `null` (in `infl.*` and `cmdty.curve.forward`); absent is `E_SCHEMA`. `years` at most 100, else `E_INPUT`. Cases `rulings2_d-0012` to `-0014` |
| D55 | `BACHELIER` caps and floors | Any strike and forward, negative included. Case `rulings2_d-0015` |
| D56 | Cap and swaption `model`, `vol` type | Only `BLACK_76`, `BACHELIER`; anything else `E_SCHEMA`. `vol` a number (flat) or an array (quoted, any length checked); any other JSON type `E_SCHEMA`. Cases `rulings2_d-0016`, `-0017` |
| D57 | Swaption check order | `expiry_months` and `tenor_months` (`E_INPUT`) before `vol` (`E_DOMAIN`), before curve-derived checks. Case `rulings2_d-0018` |
| D58 | `cmdty.storage.carry` price `<= 0` | `E_DOMAIN`. Case `rulings2_d-0019` |
| D59 | `fx.xccy.*` | `months` above 1200: `E_INPUT`. `fx.xccy.pv` with `start` before `as_of`: `E_OUT_OF_RANGE` (as D39). Cases `rulings2_d-0020`, `-0021` |
| D60 | ZCIS pv tolerance | 1e-9 per unit notional plus 1e-9 relative: a par swap's pv is rounding noise (`inflation_d-0009`). Widened in `inflation_d-0007` to `-0009`; values unchanged |
| D61 | `bond.futures.basis` | `delivery <= settlement`: `E_DATE_ORDER`. `delivery` after a bond's maturity: `E_INPUT`. Empty `bonds`: `E_INPUT`. Cases `rulings2_d-0022` to `-0024` |
| D62 | Need no golden | Asset-swap dates by plain month steps (pinned by `bonds_d-0041`). `joint_bootstrap` `GLOBAL` as block solve: same answer to solver tolerance (D9). Lockout `n` counted before business-day checks, and joint-bootstrap list order: every branch gives `E_INPUT`, so no output differs. Robust fit: at full rank the Huber minimum exists and is unique, so `E_NO_CONVERGENCE` cannot be a golden outcome (C12); rank deficiency is `E_SINGULAR` (D38). Discount pillars as CDS integration nodes: pinned by the multi-node case in `credit_d`. TRS side names: listed in the spec |
| D63 | `jumps` in `rates.curve.joint_bootstrap` | Not an input, so ignored like any key the operation does not read (`01-core/limits.md` B3 counts such keys only for the array limit) |

| D64 | Empty `step_dates` in `rates.ois.fit_steps` | `E_INPUT` (D12), the first rule check, before the quote count, even with one quote. Case `rulings2_d-0025` |

Cases for rulings carry the `ruling` tag.

## Oracle coverage

| Suite | Outside oracle | Analytic, hand or replay only |
|---|---|---|
| `ois_d` | QuantLib `OISRateHelper` with jumps, `MakeOIS` | Telescoping check |
| `compound_d` | QuantLib `OvernightLeg` (lookback, lockout, observation shift) | Exact rationals; ISDA spread table |
| `steps_d` | QuantLib `ForwardCurve` with jumps; `MakeOIS` par rates for the fit | Exact integral |
| `futures_d` | QuantLib `HullWhite::convexityBias` | Limit at `a = 0` |
| `csa_d` | QuantLib for basis and joint build | CSA discount is hand replay only |
| `bonds_d` | QuantLib `FixedRateBond`, `BondFunctions` (price, yield, duration, convexity, Z-spread) | Asset swap is replay only |
| `repo_d` | None | FRN replay and par identity; repo analytic; CBOT formula by hand |
| `bondfit_d` | SciPy `least_squares` | Known truth |
| `xccy_d` | QuantLib `OvernightLeg` NPV of foreign coupons | Bootstrap is known truth; NDF analytic |
| `credit_d` | QuantLib `IsdaCdsEngine` (the ISDA model as QuantLib implements it) | Index and composite curves are sums of checked parts |
| `equity_d`, `index_d`, `trs_d` | None: analytic and exact rationals only | All |
| `inflation_d` | None | Analytic, exact-rational reference CPI |
| `capswaption_d` | QuantLib `blackFormula`, `bachelierBlackFormula` | Composition on stage B curves |
| `commodity_d` | None | Analytic |
| `mbs_d` | None | Analytic |
| `fits_d` | SciPy `least_squares` (Huber) | Exact rationals; NumPy |

The generator stops if a tolerance would let one of its 65 wrong conventions through. All stage D data is synthetic.
