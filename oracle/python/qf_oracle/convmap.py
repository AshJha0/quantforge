"""Convention mapping table for outside-oracle checks (plan rule 11.2.5).

This is the one place where a QuantForge spec convention is turned into an outside library's own convention
object. `outside_d.py` takes every library convention from here, never inline. Each row names the spec
section it maps and its review state. The human-readable copy is `oracle/CONVENTION_MAP.md`; the two must
agree, and `outside_d.py --check-map` fails if a row is missing from either.

Review state: "self-reviewed 2026-11-07" means the spec session read the spec text and the library's
documentation for the row and found them equal. It is not an outside review.
"""
import QuantLib as ql

LIBRARY = "QuantLib"
VERSION = ql.__version__
REVIEW = "self-reviewed 2026-11-07"

# id: (spec reference, library object factory, note)
ROWS = {
    # Overnight indices and OIS conventions (01-core/conventions.md rows; lags are the spec's, the index objects QuantLib's)
    "IDX.SOFR": ("01-core/conventions.md SOFR: USD, ACT/360, USGS", lambda h=None: ql.Sofr(h or ql.YieldTermStructureHandle()), ""),
    "IDX.ESTR": ("01-core/conventions.md ESTR: EUR, ACT/360, EUTA", lambda h=None: ql.Estr(h or ql.YieldTermStructureHandle()), ""),
    "IDX.SONIA": ("01-core/conventions.md SONIA: GBP, ACT/365F, GBLO", lambda h=None: ql.Sonia(h or ql.YieldTermStructureHandle()), ""),
    "OIS.LAGS": ("01-core/conventions.md spot_lag and payment_lag", lambda conv: {"SOFR": (2, 2), "ESTR": (2, 2), "SONIA": (0, 0)}[conv],
                 "QuantLib OISRateHelper and MakeOIS take these as arguments; telescopic value dates on"),
    "CMPD.METHOD": ("02-curves/overnight-compounding.md NONE, LOOKBACK, OBSERVATION_SHIFT, LOCKOUT",
                    lambda method, k: (k if method in ("LOOKBACK", "OBSERVATION_SHIFT") else 0, k - 1 if method == "LOCKOUT" else 0, method == "OBSERVATION_SHIFT"),
                    "QuantLib (lookbackDays, lockoutDays, applyObservationShift). QuantLib lockoutDays = k locks k+1 days; the ARRC rule in the spec is QuantLib k-1"),
    "ISDA.FALLBACK": ("02-curves/overnight-compounding.md fallbacks: ISDA 2020 IBOR Fallbacks Protocol, spreads fixed 2021-03-05 (Bloomberg ISDA fallback spread announcement)",
                      lambda ibor: {"USD-LIBOR-1M": ("SOFR", 0.0011448), "USD-LIBOR-3M": ("SOFR", 0.0026161), "USD-LIBOR-6M": ("SOFR", 0.0042826),
                                    "GBP-LIBOR-1M": ("SONIA", 0.000326), "GBP-LIBOR-3M": ("SONIA", 0.001193), "GBP-LIBOR-6M": ("SONIA", 0.002766)}[ibor],
                      "rate in arrears with a 2 business-day observation shift; the spread is a published constant, not a QuantLib value"),
    "HW.CONVEXITY": ("02-curves/futures-convexity.md Hull-White futures convexity", lambda: ql.HullWhite.convexityBias, "same closed form; QuantLib takes the quoted price"),
    "RATE.SIMPLE_ACT_360": ("04-pricing/bonds.md repo: simple interest on ACT/360", lambda r: ql.InterestRate(r, ql.Actual360(), ql.Simple, ql.Annual), ""),
    # Day counts
    "DC.ACT_360": ("01-core/daycount.md ACT_360", lambda: ql.Actual360(), ""),
    "DC.ACT_360_INCL_LAST": ("04-pricing/credit.md accrual on default, last day included", lambda: ql.Actual360(True), "ISDA CDS standard model"),
    "DC.ACT_365F": ("01-core/daycount.md ACT_365F; curve time in 02-curves/curve-framework.md", lambda: ql.Actual365Fixed(), ""),
    "DC.THIRTY_360_BOND": ("01-core/daycount.md THIRTY_360_BOND", lambda: ql.Thirty360(ql.Thirty360.BondBasis), ""),
    "DC.ACT_ACT_ICMA": ("04-pricing/bonds.md accrued and yield periods", lambda sch: ql.ActualActual(ql.ActualActual.ISMA, sch), "needs the bond's own schedule"),
    # Calendars
    "CAL.NONE": ("04-pricing/bonds.md unadjusted coupon dates", lambda: ql.NullCalendar(), ""),
    "CAL.USGS": ("01-core/calendars.md USGS", lambda: ql.UnitedStates(ql.UnitedStates.GovernmentBond), "coverage checked by compare_calendars.py"),
    "CAL.WEEKENDS": ("04-pricing/credit.md CDS dates roll on weekends only", lambda: ql.WeekendsOnly(), "ISDA CDS standard model"),
    # Business-day conventions
    "BDC.UNADJUSTED": ("01-core/calendars.md UNADJUSTED", lambda: ql.Unadjusted, ""),
    "BDC.FOLLOWING": ("01-core/calendars.md FOLLOWING", lambda: ql.Following, ""),
    "BDC.MODIFIED_FOLLOWING": ("01-core/calendars.md MODIFIED_FOLLOWING", lambda: ql.ModifiedFollowing, ""),
    # Schedule generation
    "GEN.BACKWARD": ("02-curves/schedules.md backward from the end, short stub first", lambda: ql.DateGeneration.Backward, ""),
    "GEN.CDS2015": ("04-pricing/credit.md IMM dates, 2015 roll", lambda: ql.DateGeneration.CDS2015, ""),
    # Frequencies
    "FREQ.1": ("04-pricing/bonds.md frequency 1", lambda: ql.Annual, ""),
    "FREQ.2": ("04-pricing/bonds.md frequency 2", lambda: ql.Semiannual, ""),
    "FREQ.4": ("04-pricing/bonds.md frequency 4", lambda: ql.Quarterly, ""),
    # Compounding
    "CMP.BOND_YIELD": ("04-pricing/bonds.md yield compounded at the coupon frequency", lambda: ql.Compounded, ""),
    "CMP.CONTINUOUS": ("04-pricing/bonds.md Z-spread continuous on curve time", lambda: ql.Continuous, ""),
    # Curves
    "CRV.LOG_LINEAR_DF": ("02-curves/curve-framework.md LOG_LINEAR_DF, D(as_of) = 1",
                          lambda dates, dfs: ql.DiscountCurve(dates, dfs, ql.Actual365Fixed()), "QuantLib DiscountCurve is log-linear in DF"),
    "CRV.LOG_LINEAR_DF_JUMPS": ("02-curves/curve-framework.md jumps: D = D_smooth x factors of jump dates strictly before t",
                                lambda dates, dfs, jq, jd: ql.DiscountCurve(dates, dfs, ql.Actual365Fixed(), ql.NullCalendar(), jq, jd),
                                "QuantLib applies a jump when jump time < t, as the spec does"),
    "CRV.LINEAR_ZERO": ("02-curves/curve-framework.md LINEAR_ZERO: continuous zero rate on ACT/365F, linear in t, flat before the first pillar",
                        lambda: ql.PiecewiseLinearZero, "bootstrap only; QuantLib sets the zero at t = 0 to the first pillar's"),
    "CRV.HAZARD_FLAT": ("04-pricing/credit.md piecewise-flat hazard between survival pillars",
                        lambda dates, hz: ql.HazardRateCurve(dates, hz, ql.Actual365Fixed()), ""),
    # Option formulas
    "OPT.BLACK_76": ("05-volatility/black-models.md BLACK_76, time ACT/365F from as_of", lambda: ql.BlackCapFloorEngine, ""),
    "OPT.BACHELIER": ("05-volatility/black-models.md BACHELIER, time ACT/365F from as_of", lambda: ql.BachelierCapFloorEngine, ""),
    # Credit engine
    "ENG.ISDA_CDS": ("04-pricing/credit.md ISDA CDS Standard Model", lambda: ql.IsdaCdsEngine, "Taylor, NoBias, Piecewise"),
}


def obj(row, *args):
    """The library object for a row. Raises KeyError for an unmapped row, so no mapping can be inline."""
    return ROWS[row][1](*args)


FREQ = {1: "FREQ.1", 2: "FREQ.2", 4: "FREQ.4"}
