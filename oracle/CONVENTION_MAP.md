# Convention map for outside-oracle checks

Plan rule 11.2.5: a stage D case counts as "outside oracle" only if the QuantLib call uses QuantLib's own convention objects, and the mapping from a QuantForge spec convention to those objects lives in a separate, reviewed table. This is that table, written from `oracle/python/qf_oracle/convmap.py` by `outside_d.py --write-map`; `outside_d.py` takes every library convention from it and fails if a row here is missing.

Library: QuantLib 1.44 (Python wheel, pinned in `oracle/python/uv.lock`). The version is recorded on every counted case in `oracle/outside_register.json`.

Review: self-reviewed 2026-11-07. The spec session read each spec section and the QuantLib documentation or source for the object and found them equal. That is self-assessment, not an outside review. A row's review must be redone when its spec section or the QuantLib version changes.

| Row | Spec | QuantLib object | Note |
|---|---|---|---|
| `IDX.SOFR` | 01-core/conventions.md SOFR: USD, ACT/360, USGS | `ql.Sofr(h or ql.YieldTermStructureHandle()), ""` |  |
| `IDX.ESTR` | 01-core/conventions.md ESTR: EUR, ACT/360, EUTA | `ql.Estr(h or ql.YieldTermStructureHandle()), ""` |  |
| `IDX.SONIA` | 01-core/conventions.md SONIA: GBP, ACT/365F, GBLO | `ql.Sonia(h or ql.YieldTermStructureHandle()), ""` |  |
| `OIS.LAGS` | 01-core/conventions.md spot_lag and payment_lag | `{"SOFR": (2, 2), "ESTR": (2, 2), "SONIA": (0, 0)}[conv]` | QuantLib OISRateHelper and MakeOIS take these as arguments; telescopic value dates on |
| `CMPD.METHOD` | 02-curves/overnight-compounding.md NONE, LOOKBACK, OBSERVATION_SHIFT, LOCKOUT | `(k if method in ("LOOKBACK", "OBSERVATION_SHIFT") else 0, k - 1 if method == "LOCKOUT" else 0, method == "O...` | QuantLib (lookbackDays, lockoutDays, applyObservationShift). QuantLib lockoutDays = k locks k+1 days; the ARRC rule in the spec is QuantLib k-1 |
| `ISDA.FALLBACK` | 02-curves/overnight-compounding.md fallbacks: ISDA 2020 IBOR Fallbacks Protocol, spreads fixed 2021-03-05 (Bloomberg ISDA fallback spread announcement) | `{"USD-LIBOR-1M": ("SOFR", 0.0011448), "USD-LIBOR-3M": ("SOFR", 0.0026161), "USD-LIBOR-6M": ("SOFR", 0.0042826` | rate in arrears with a 2 business-day observation shift; the spread is a published constant, not a QuantLib value |
| `HW.CONVEXITY` | 02-curves/futures-convexity.md Hull-White futures convexity | `ql.HullWhite.convexityBias, "same closed form; QuantLib takes the quoted price"` | same closed form; QuantLib takes the quoted price |
| `RATE.SIMPLE_ACT_360` | 04-pricing/bonds.md repo: simple interest on ACT/360 | `ql.InterestRate(r, ql.Actual360(), ql.Simple, ql.Annual), ""` |  |
| `DC.ACT_360` | 01-core/daycount.md ACT_360 | `ql.Actual360(), ""` |  |
| `DC.ACT_360_INCL_LAST` | 04-pricing/credit.md accrual on default, last day included | `ql.Actual360(True), "ISDA CDS standard model"` | ISDA CDS standard model |
| `DC.ACT_365F` | 01-core/daycount.md ACT_365F; curve time in 02-curves/curve-framework.md | `ql.Actual365Fixed(), ""` |  |
| `DC.THIRTY_360_BOND` | 01-core/daycount.md THIRTY_360_BOND | `ql.Thirty360(ql.Thirty360.BondBasis), ""` |  |
| `DC.ACT_ACT_ICMA` | 04-pricing/bonds.md accrued and yield periods | `ql.ActualActual(ql.ActualActual.ISMA, sch), "needs the bond's own schedule"` | needs the bond's own schedule |
| `CAL.NONE` | 04-pricing/bonds.md unadjusted coupon dates | `ql.NullCalendar(), ""` |  |
| `CAL.USGS` | 01-core/calendars.md USGS | `ql.UnitedStates(ql.UnitedStates.GovernmentBond), "coverage checked by compare_calendars.py"` | coverage checked by compare_calendars.py |
| `CAL.WEEKENDS` | 04-pricing/credit.md CDS dates roll on weekends only | `ql.WeekendsOnly(), "ISDA CDS standard model"` | ISDA CDS standard model |
| `BDC.UNADJUSTED` | 01-core/calendars.md UNADJUSTED | `ql.Unadjusted, ""` |  |
| `BDC.FOLLOWING` | 01-core/calendars.md FOLLOWING | `ql.Following, ""` |  |
| `BDC.MODIFIED_FOLLOWING` | 01-core/calendars.md MODIFIED_FOLLOWING | `ql.ModifiedFollowing, ""` |  |
| `GEN.BACKWARD` | 02-curves/schedules.md backward from the end, short stub first | `ql.DateGeneration.Backward, ""` |  |
| `GEN.CDS2015` | 04-pricing/credit.md IMM dates, 2015 roll | `ql.DateGeneration.CDS2015, ""` |  |
| `FREQ.1` | 04-pricing/bonds.md frequency 1 | `ql.Annual, ""` |  |
| `FREQ.2` | 04-pricing/bonds.md frequency 2 | `ql.Semiannual, ""` |  |
| `FREQ.4` | 04-pricing/bonds.md frequency 4 | `ql.Quarterly, ""` |  |
| `CMP.BOND_YIELD` | 04-pricing/bonds.md yield compounded at the coupon frequency | `ql.Compounded, ""` |  |
| `CMP.CONTINUOUS` | 04-pricing/bonds.md Z-spread continuous on curve time | `ql.Continuous, ""` |  |
| `CRV.LOG_LINEAR_DF` | 02-curves/curve-framework.md LOG_LINEAR_DF, D(as_of) = 1 | `ql.DiscountCurve(dates, dfs, ql.Actual365Fixed()), "QuantLib DiscountCurve is log-linear in DF"` | QuantLib DiscountCurve is log-linear in DF |
| `CRV.LOG_LINEAR_DF_JUMPS` | 02-curves/curve-framework.md jumps: D = D_smooth x factors of jump dates strictly before t | `ql.DiscountCurve(dates, dfs, ql.Actual365Fixed(), ql.NullCalendar(), jq, jd` | QuantLib applies a jump when jump time < t, as the spec does |
| `CRV.LINEAR_ZERO` | 02-curves/curve-framework.md LINEAR_ZERO: continuous zero rate on ACT/365F, linear in t, flat before the first pillar | `ql.PiecewiseLinearZero, "bootstrap only; QuantLib sets the zero at t = 0 to the first pillar's"` | bootstrap only; QuantLib sets the zero at t = 0 to the first pillar's |
| `CRV.HAZARD_FLAT` | 04-pricing/credit.md piecewise-flat hazard between survival pillars | `ql.HazardRateCurve(dates, hz, ql.Actual365Fixed()), ""` |  |
| `OPT.BLACK_76` | 05-volatility/black-models.md BLACK_76, time ACT/365F from as_of | `ql.BlackCapFloorEngine, ""` |  |
| `OPT.BACHELIER` | 05-volatility/black-models.md BACHELIER, time ACT/365F from as_of | `ql.BachelierCapFloorEngine, ""` |  |
| `ENG.ISDA_CDS` | 04-pricing/credit.md ISDA CDS Standard Model | `ql.IsdaCdsEngine, "Taylor, NoBias, Piecewise"` | Taylor, NoBias, Piecewise |

## Known mapping points

- `CMPD.METHOD`: QuantLib's `lockoutDays = k` locks the last k+1 rates; the ARRC lockout in `02-curves/overnight-compounding.md` locks k, so the map passes k-1.
- `ISDA.FALLBACK`: the spread adjustments are published constants (fixed 2021-03-05), not QuantLib values. A fallback case counts because its compounded rate comes from QuantLib.
- `credit.cds.bootstrap` is counted by a reprice check: QuantLib's `cdsMaturity` gives the pillar dates, and the golden survivals priced in QuantLib's ISDA engine return each quoted spread within 1e-10.
- `rates.ois.pv`: the strings in `valuation` are identities of the inputs and the spec's fixed strings; only the numbers come from QuantLib.
- `repo.*`: QuantLib gives the bond's cash flows, accrued and the simple ACT/360 growth factors; the forward-price identity is the spec's own algebra on those objects.
- Strata and the ISDA C library are not used for stage D counting yet.
