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
| `fits_d` | SciPy `least_squares` (Huber) | Exact rationals; NumPy |

The generator stops if a tolerance would let one of its 65 wrong conventions through. All stage D data is synthetic.
