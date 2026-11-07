"""Stage D golden cases. Wave 1: D1 rates core.

All market data is synthetic. Each suite checks its results against QuantLib, SciPy or an exact-rational route, and stops
if a tolerance would let a named wrong convention through. Nothing here depends on maths-library rounding or on a solver's
path: compounding runs in exact rationals, fits have closed forms or convex objectives checked from several starts, and
guards stop the run when a discrete choice (outlier set, step bracket) sits near its threshold.
"""
import math
from datetime import date, timedelta
from fractions import Fraction as Fr

import mpmath as mp
import numpy as np
import QuantLib as ql
from scipy.optimize import brentq, least_squares

from qf_oracle import common
from qf_oracle.common import Suite, note
from qf_oracle.dates import is_business, yf
from qf_oracle import rates as RT
from qf_oracle.rates import Curve, add_bd, bootstrap, ois_legs, ois_par, ois_periods
import gen_stage_b as B

G = "oracle/python/gen_stage_d.py"
E, A, R, I = "date_and_convention", "simple_analytic", "root_finding", "interpolation"
SYN = "synthetic"
AS_OF = date(2026, 11, 6)
QLV = "quantlib-1.44"
MUTANTS = []
Q = lambda d: ql.Date(d.day, d.month, d.year)  # noqa: E731
RT.CONV["ESTR"] = dict(currency="EUR", day_count="ACT_360", calendar="EUTA", spot_lag=2, payment_lag=2, fixed_months=12, fixed_day_count="ACT_360")
DEN = {"SOFR": 360, "ESTR": 360, "SONIA": 365}
DFLIM = B.DFLIM
PVLIM = B.PVLIM
RATELIM = {"absolute": 1e-12, "relative": 0.0, "reason": "stage-d-targets: exact-rational compounding; only the final division rounds"}
ESTR_Q = [(t, r - .0145) for t, r in B.SONIA_Q]


def S(name, spec):
    return Suite(name, f"specifications/{spec}", G)


def write(s):
    keep = common.GOLDEN
    for c in s.cases:
        if SYN not in c["tags"]:
            c["tags"].append(SYN)
    common.GOLDEN = keep.parent / "stage_d"
    s.write()
    common.GOLDEN = keep


def caught(suite, name, gap, tol):
    assert gap > tol, f"{suite}: mutant '{name}' is not caught: gap {gap:.3e}, tolerance {tol:.3e}"
    MUTANTS.append((suite, name, gap))


def qindex(conv, h=None):
    h = h or ql.YieldTermStructureHandle()
    return {"SOFR": lambda: ql.Sofr(h), "ESTR": lambda: ql.Estr(h), "SONIA": lambda: ql.Sonia(h)}[conv]()


def ql_ois(conv, as_of, quotes, ip="LOG_LINEAR_DF", jumps=()):
    ql.Settings.instance().evaluationDate = Q(as_of)
    c = RT.CONV[conv]
    hs = [ql.OISRateHelper(c["spot_lag"], B.qper(t), ql.QuoteHandle(ql.SimpleQuote(r)), qindex(conv), ql.YieldTermStructureHandle(), True, c["payment_lag"]) for t, r in quotes]
    k = ql.PiecewiseLogLinearDiscount if ip == "LOG_LINEAR_DF" else ql.PiecewiseLinearZero
    jq = [ql.QuoteHandle(ql.SimpleQuote(f)) for _, f in jumps]
    q = k(Q(as_of), hs, ql.Actual365Fixed(), jq, [Q(d) for d, _ in jumps])
    q.enableExtrapolation()
    return q


class JCurve(Curve):
    """Curve with discount-factor jumps: D(t) = D_smooth(t) * prod(factor for jump date strictly before t)."""

    def __init__(self, as_of, dates, dfs, interp="LOG_LINEAR_DF", jumps=()):
        self.jumps = list(jumps)
        super().__init__(as_of, dates, [v / self.J(d) for d, v in zip(dates, dfs)], interp)

    def J(self, d):
        return math.prod(f for jd, f in self.jumps if jd < d)

    def df(self, d):
        return super().df(d) * self.J(d)


def bootstrap_ois_j(conv, as_of, quotes, interp="LOG_LINEAR_DF", jumps=()):
    per = [ois_periods(conv, as_of, t) for t, _ in quotes]
    pil = [p[-1][2] for p in per]
    dfs = []
    for i, d in enumerate(pil):
        def err(ln):
            return ois_par(conv, per[i], JCurve(as_of, pil[:i + 1], dfs + [math.exp(ln)], interp, jumps)) - quotes[i][1]
        p = math.log(dfs[-1]) if dfs else 0.0
        dfs.append(math.exp(brentq(err, p - 1, p + 1, xtol=1e-15, rtol=1e-15, maxiter=500)))
    return JCurve(as_of, pil, dfs, interp, jumps), dfs, per


def jcurve(cv, dates, dfs, jumps=()):
    out = {"as_of": str(cv.as_of), "interpolation": cv.interp, "pillars": [{"date": str(d), "discount_factor": v} for d, v in zip(dates, dfs)]}
    if jumps:
        out["jumps"] = [{"date": str(d), "factor": f} for d, f in jumps]
    return out


def pillars(dates, dfs):
    return [{"date": str(d), "discount_factor": v} for d, v in zip(dates, dfs)]


# ---------------------------------------------------------------- D1a: SOFR, ESTR OIS, jumps (turn of year)
def ois_d():
    s = S("ois_d", "02-curves/ois-curves.md")
    op = "rates.ois.bootstrap"
    for conv, quotes in (("ESTR", ESTR_Q), ("SOFR", B.SOFR_Q)):
        for as_of in (AS_OF, date(2026, 12, 31)):
            for ip in ("LOG_LINEAR_DF", "LINEAR_ZERO"):
                cv, dfs, per = bootstrap_ois_j(conv, as_of, quotes, ip)
                q = ql_ois(conv, as_of, quotes, ip)
                pil = [p[-1][2] for p in per]
                err = max(abs(q.discount(Q(d)) - v) for d, v in zip(pil, dfs))
                assert err < 5e-12, (conv, as_of, ip, err)
                s.add(op, {"convention": conv, "as_of": str(as_of), "quotes": B.jq(quotes), "interpolation": ip, "method": "GLOBAL" if ip == "LINEAR_ZERO" else "SEQUENTIAL"},
                      {"pillars": pillars(pil, dfs)}, cls=I, verified=["independent-replay", QLV], tags=[conv], limit=DFLIM)
    note("ois_d: ESTR and SOFR pillars match QuantLib OISRateHelper within 5e-12, both interpolations, two dates")
    # ESTR payment lag is 2 business days, as Strata 2.12.78 EUR-FIXED-1Y-ESTR-OIS: lag 1 is a wrong convention.
    cv, dfs, per = bootstrap_ois_j("ESTR", AS_OF, ESTR_Q)
    RT.CONV["ESTR"]["payment_lag"] = 1
    _, d2, _ = bootstrap_ois_j("ESTR", AS_OF, ESTR_Q)
    RT.CONV["ESTR"]["payment_lag"] = 2
    caught("ois_d", "ESTR payment lag 1 instead of 2", max(abs(a - b) for a, b in zip(dfs, d2)), 1e-9)
    # Turn of year: a discount-factor jump, applied to dates strictly after the jump date.
    jumps = [(date(2026, 12, 31), math.exp(-.0050 * 1 / 365))]
    for conv, quotes in (("SOFR", B.SOFR_Q), ("ESTR", ESTR_Q)):
        cv, dfs, per = bootstrap_ois_j(conv, AS_OF, quotes, "LOG_LINEAR_DF", jumps)
        q = ql_ois(conv, AS_OF, quotes, "LOG_LINEAR_DF", jumps)
        pil = [p[-1][2] for p in per]
        err = max(abs(q.discount(Q(d)) - v) for d, v in zip(pil, dfs))
        assert err < 5e-12, err
        s.add(op, {"convention": conv, "as_of": str(AS_OF), "quotes": B.jq(quotes), "interpolation": "LOG_LINEAR_DF", "method": "SEQUENTIAL", "jumps": [{"date": str(d), "factor": f} for d, f in jumps]},
              {"pillars": pillars(pil, dfs)}, cls=I, verified=["independent-replay", QLV], tags=[conv, "turn-of-year"], limit=DFLIM)
        jc = jcurve(cv, pil, dfs, jumps)
        qd = [date(2026, 12, 30), date(2026, 12, 31), date(2027, 1, 1), date(2027, 1, 4), date(2030, 6, 28)]
        dv = [cv.df(d) for d in qd]
        assert max(abs(q.discount(Q(d)) - v) for d, v in zip(qd, dv)) < 5e-12
        s.add("rates.curve.discount", {"curve": jc, "dates": [str(d) for d in qd]}, {"discount_factors": dv, "zero_rates": [-math.log(v) / ((d - AS_OF).days / 365) for d, v in zip(qd, dv)]},
              cls=I, verified=["independent-replay", QLV], tags=["turn-of-year"])
        _, dn, _ = bootstrap_ois_j(conv, AS_OF, quotes, "LOG_LINEAR_DF")
        caught("ois_d", f"{conv} turn of year ignored", max(abs(a - b) for a, b in zip(dfs, dn)), 1e-9)
        smooth = JCurve(AS_OF, pil, dfs, "LOG_LINEAR_DF", jumps)
        incl = math.prod(f for jd, f in jumps if jd <= date(2026, 12, 31)) * Curve.df(smooth, date(2026, 12, 31))
        caught("ois_d", "jump applied on its own date", abs(incl - cv.df(date(2026, 12, 31))), 1e-10)
    note("ois_d: turn-of-year jump curves match QuantLib's jump mechanism within 5e-12 at pillars and around the turn")
    bq = {"convention": "SOFR", "as_of": str(AS_OF), "quotes": B.jq(B.SOFR_Q[:4]), "interpolation": "LOG_LINEAR_DF", "method": "SEQUENTIAL"}
    s.add(op, {**bq, "jumps": [{"date": "2026-12-31", "factor": 0.0}]}, error="E_DOMAIN", cls=E, tags=["invalid"], description="factor must be > 0")
    s.add(op, {**bq, "jumps": [{"date": "2026-11-06", "factor": 0.99}]}, error="E_INPUT", cls=E, tags=["invalid"], description="jump date must be after as_of")
    s.add(op, {**bq, "jumps": [{"date": "2027-12-31", "factor": 0.99}, {"date": "2026-12-31", "factor": 0.99}]}, error="E_INPUT", cls=E, tags=["invalid"], description="jump dates strictly increasing")
    s.add(op, {**bq, "jumps": None}, error="E_SCHEMA", cls=E, tags=["invalid", "ruling"])
    # PVs: ESTR with lag 1, SOFR with lag 2, against QuantLib MakeOIS.
    pv = "rates.ois.pv"
    for conv, quotes in (("ESTR", ESTR_Q), ("SOFR", B.SOFR_Q)):
        cv, dfs, per = bootstrap_ois_j(conv, AS_OF, quotes)
        pil = [p[-1][2] for p in per]
        jc = jcurve(cv, pil, dfs)
        q = ql_ois(conv, AS_OF, quotes)
        h = ql.YieldTermStructureHandle(q)
        c = RT.CONV[conv]
        for tenor, k, side, N in (("2Y", .021, "RECEIVE", 2.5e7), ("10Y", .024, "PAY", 1e6), ("18M", .022, "PAY", 7.5e6), ("30Y", .025, "RECEIVE", 1e6)):
            if conv == "SOFR":
                k += .0145
            p = ois_periods(conv, AS_OF, tenor)
            a, fl = ois_legs(conv, p, cv)
            val = (1 if side == "PAY" else -1) * N * (fl - k * a)
            sw = ql.MakeOIS(B.qper(tenor), qindex(conv, h), k, settlementDays=c["spot_lag"], paymentLag=c["payment_lag"], nominal=N,
                            swapType=ql.Swap.Payer if side == "PAY" else ql.Swap.Receiver, pricingEngine=ql.DiscountingSwapEngine(h), telescopicValueDates=True)
            assert abs(sw.NPV() - val) < 1e-9 * N + 1e-6, (conv, tenor, sw.NPV(), val)
            s.add(pv, {"curve": jc, "trade": {"convention": conv, "tenor": tenor, "fixed_rate": k, "notional": N, "side": side}},
                  {"valuation": {"pv": val, "currency": c["currency"], "model": "OIS_DISCOUNTING", "data_version": None, "conventions": conv, "as_of": str(AS_OF)}, "par_rate": fl / a, "annuity": a},
                  cls=I, verified=["independent-replay", QLV], tags=[conv], limit={**PVLIM, "absolute": 1e-9 * N})
            tele = (cv.df(p[0][0]) - cv.df(p[-1][1]))
            caught("ois_d", f"{conv} {tenor} telescoped floating leg", abs(N * (fl - tele)), 1e-9 * N + 1e-9 * abs(val))
    note("ois_d: ESTR and SOFR swap PVs match QuantLib MakeOIS within 1e-9 per unit notional")
    write(s)


# ---------------------------------------------------------------- D1b: dated compounding, lookback, lockout, shift, fallbacks
CAL = {"SOFR": "USGS", "ESTR": "EUTA", "SONIA": "GBLO"}


def fix_rate(conv, d):
    base = {"SOFR": .0431, "ESTR": .0193, "SONIA": .0372}[conv]
    return base + [0, 3, -2, 5, -4, 1, 2, -1, 4, -3, 0][d.toordinal() % 11] * 1e-4


def fixings(conv, a, b):
    out, d = [], a
    while d <= b:
        if is_business(CAL[conv], d):
            out.append((d, fix_rate(conv, d)))
        d += timedelta(1)
    return out


def bds(cal, a, b):
    return [d for d in (a + timedelta(i) for i in range((b - a).days + 1)) if is_business(cal, d)]


def sub_bd(cal, d, k):
    while k > 0:
        d -= timedelta(1)
        k -= is_business(cal, d)
    return d


def compound(conv, S0, E0, method, k, fx, mutant=None):
    """Exact-rational compounded rate. fx: dict date -> rate. Returns (rate, growth, total days)."""
    cal, den = CAL[conv], DEN[conv]
    ds = bds(cal, S0, E0)
    n = len(ds) - 1
    g, tot = Fr(1), 0
    if method == "OBSERVATION_SHIFT":
        os_ = [sub_bd(cal, d, k) for d in ds]
        for i in range(n):
            w = (os_[i + 1] - os_[i]).days if mutant != "shift weights from interest period" else (ds[i + 1] - ds[i]).days
            g *= 1 + Fr(fx[os_[i]]) * w / den
            tot += w
    else:
        for i in range(n):
            w = (ds[i + 1] - ds[i]).days
            if method == "LOOKBACK":
                fd = sub_bd(cal, ds[i], k)
                if mutant == "lookback weights from observation period":
                    w = (sub_bd(cal, ds[i + 1], k) - fd).days
            elif method == "LOCKOUT":
                cut = n - k if mutant != "lockout one day early" else n - k - 1
                fd = ds[i] if i < cut else ds[cut]
            else:
                fd = ds[i]
            g *= 1 + Fr(fx[fd]) * w / den
            tot += w
    return (g - 1) * den / tot, g, tot


def ql_compound(conv, S0, E0, method, k, fx):
    ql.Settings.instance().evaluationDate = Q(E0 + timedelta(60))
    ix = qindex(conv)
    ix.clearFixings()
    for d, r in fx.items():
        ix.addFixing(Q(d), r)
    lb = k if method in ("LOOKBACK", "OBSERVATION_SHIFT") else 0
    # QuantLib's lockoutDays = k locks the last k days to the fixing k+1 days back; the ARRC rule (this spec) is QuantLib's k-1.
    lo = k - 1 if method == "LOCKOUT" else 0
    leg = ql.OvernightLeg([1.0], ql.Schedule([Q(S0), Q(E0)]), ix, ix.dayCounter(), ql.Following, [1.0], [0.0], False, ql.RateAveraging.Compound,
                          ql.NullCalendar(), 0, lb, lo, method == "OBSERVATION_SHIFT")
    r = ql.as_floating_rate_coupon(leg[0]).rate()
    ix.clearFixings()
    return r


def compound_d():
    s = S("compound_d", "02-curves/overnight-compounding.md")
    op = "rates.ois.compound_dated"
    cases = [("SOFR", date(2026, 11, 10), date(2027, 2, 10)), ("ESTR", date(2026, 12, 15), date(2027, 3, 15)), ("SONIA", date(2026, 12, 21), date(2027, 1, 21))]
    for conv, S0, E0 in cases:
        fl = fixings(conv, S0 - timedelta(20), E0)
        fx = dict(fl)
        for method, k in (("NONE", 0), ("LOOKBACK", 2), ("LOOKBACK", 5), ("OBSERVATION_SHIFT", 2), ("OBSERVATION_SHIFT", 5), ("LOCKOUT", 2), ("LOCKOUT", 1)):
            r, g, tot = compound(conv, S0, E0, method, k, fx)
            qr = ql_compound(conv, S0, E0, method, k, fx)
            assert abs(qr - float(r)) < 5e-14, (conv, method, k, qr, float(r))
            acc = Fr((E0 - S0).days, DEN[conv])
            s.add(op, {"convention": conv, "start": str(S0), "end": str(E0), "method": method, "shift_days": k,
                       "fixings": [{"date": str(d), "rate": v} for d, v in fl]},
                  {"compounded_rate": float(r), "accrual": float(acc), "interest": float(r * acc)},
                  cls=A, verified=["exact-rational", QLV], tags=[conv, method.lower()], limit=RATELIM)
            for mut in ("lookback weights from observation period", "shift weights from interest period", "lockout one day early"):
                if (mut.startswith("lookback") and method == "LOOKBACK") or (mut.startswith("shift") and method == "OBSERVATION_SHIFT") or (mut.startswith("lockout") and method == "LOCKOUT"):
                    rm, _, _ = compound(conv, S0, E0, method, k, fx, mut)
                    caught("compound_d", f"{conv} {method} {k}: {mut}", abs(float(rm - r)), 1e-12)
    note("compound_d: lookback, observation shift and lockout match QuantLib OvernightIndexedCoupon within 5e-14 (lockout k as QuantLib k-1)")
    S0, E0 = date(2026, 11, 10), date(2027, 2, 10)
    fl = fixings("SOFR", S0 - timedelta(20), E0)
    b = {"convention": "SOFR", "start": str(S0), "end": str(E0), "method": "LOOKBACK", "shift_days": 2, "fixings": [{"date": str(d), "rate": v} for d, v in fl]}
    s.add(op, {**b, "fixings": b["fixings"][:-30]}, error="E_INPUT", cls=E, tags=["invalid"], description="a needed fixing is missing")
    s.add(op, {**b, "end": "2026-11-10"}, error="E_DATE_ORDER", cls=E, tags=["invalid"], description="end not after start")
    s.add(op, {**b, "start": "2026-11-11", "end": "2026-11-12"}, error="E_INPUT", cls=E, tags=["invalid", "ruling"], description="start on a holiday (Veterans Day)")
    s.add(op, {**b, "method": "NONE", "shift_days": 2}, error="E_INPUT", cls=E, tags=["invalid", "ruling"], description="NONE needs shift_days 0")
    s.add(op, {**b, "shift_days": -1}, error="E_INPUT", cls=E, tags=["invalid"])
    s.add(op, {**b, "method": "LOCKOUT", "shift_days": 0}, error="E_INPUT", cls=E, tags=["invalid", "ruling"], description="lockout needs shift_days >= 1")
    s.add(op, {**b, "method": "LOCKOUT", "shift_days": 63}, error="E_INPUT", cls=E, tags=["invalid", "ruling"], description="lockout must leave one unlocked day")
    s.add(op, {**b, "fixings": b["fixings"] + b["fixings"][-1:]}, error="E_INPUT", cls=E, tags=["invalid"], description="duplicate fixing date")
    s.add(op, {**b, "convention": "USD-TERM-3M"}, error="E_INPUT", cls=E, tags=["invalid"], description="not an overnight index")
    # IBOR fallbacks: ISDA 2020: compounded RFR over the IBOR period, observation shift 2 business days, plus fixed spread adjustment.
    fop = "rates.fallback.rate"
    for ibor, conv, S0, E0 in (("USD-LIBOR-3M", "SOFR", date(2026, 11, 10), date(2027, 2, 10)), ("USD-LIBOR-1M", "SOFR", date(2026, 12, 15), date(2027, 1, 15)),
                               ("GBP-LIBOR-3M", "SONIA", date(2026, 12, 21), date(2027, 3, 22)), ("GBP-LIBOR-6M", "SONIA", date(2026, 11, 9), date(2027, 5, 10))):
        fl = fixings(conv, S0 - timedelta(20), E0)
        fx = dict(fl)
        r, _, _ = compound(conv, S0, E0, "OBSERVATION_SHIFT", 2, fx)
        sa = FALLBACK[ibor]
        qr = ql_compound(conv, S0, E0, "OBSERVATION_SHIFT", 2, fx)
        assert abs(qr - float(r)) < 5e-14
        s.add(fop, {"ibor": ibor, "start": str(S0), "end": str(E0), "fixings": [{"date": str(d), "rate": v} for d, v in fl]},
              {"compounded_rate": float(r), "spread_adjustment": sa, "fallback_rate": float(r + Fr(sa))}, cls=A, verified=["exact-rational", QLV, "isda-2021-fixed-spreads"], tags=[conv, "fallback"], limit=RATELIM)
        rl, _, _ = compound(conv, S0, E0, "LOOKBACK", 2, fx)
        caught("compound_d", f"{ibor} fallback with lookback, no shift", abs(float(rl - r)), 1e-12)
        caught("compound_d", f"{ibor} fallback without spread adjustment", sa, 1e-12)
    s.add(fop, {"ibor": "EUR-LIBOR-3M", "start": "2026-11-10", "end": "2027-02-10", "fixings": []}, error="E_SCHEMA", cls=E, tags=["invalid"], description="not in the table")
    note("compound_d: IBOR fallback rates match QuantLib with 2-day observation shift; spreads are ISDA's fixed 2021-03-05 values")
    write(s)


FALLBACK = {"USD-LIBOR-1M": .0011448, "USD-LIBOR-3M": .0026161, "USD-LIBOR-6M": .0042826, "USD-LIBOR-12M": .0071513,
            "GBP-LIBOR-1M": .0003260, "GBP-LIBOR-3M": .0011930, "GBP-LIBOR-6M": .0027660, "GBP-LIBOR-12M": .0046440}


# ---------------------------------------------------------------- D1c: meeting-date step curve and its fit
def step_df(as_of, base, steps, jumps, d):
    t = lambda x: Fr((x - as_of).days, 365)  # noqa: E731
    knots = [(as_of, base)] + [(sd, r) for sd, r in steps]
    integ = Fr(0)
    for i, (sd, r) in enumerate(knots):
        if sd >= d:
            break
        nd = knots[i + 1][0] if i + 1 < len(knots) else None
        hi = d if nd is None or nd > d else nd
        integ += Fr(r) * (t(hi) - t(sd))
    j = math.prod(f for jd, f in jumps if jd < d)
    return integ, j


class StepCurve:
    def __init__(self, as_of, base, steps, jumps=()):
        self.as_of, self.base, self.steps, self.jumps = as_of, base, list(steps), list(jumps)

    def df(self, d):
        integ, j = step_df(self.as_of, self.base, self.steps, self.jumps, d)
        return math.exp(-float(integ)) * j


def ql_step(as_of, base, steps, jumps=()):
    ql.Settings.instance().evaluationDate = Q(as_of)
    dates = [Q(as_of)] + [Q(d) for d, _ in steps] + [Q(as_of) + ql.Period(60, ql.Years)]
    fwd = [base, base] + [r for _, r in steps]
    jq = [ql.QuoteHandle(ql.SimpleQuote(f)) for _, f in jumps]
    c = ql.ForwardCurve(dates, fwd, ql.Actual365Fixed(), ql.NullCalendar(), jq, [Q(d) for d, _ in jumps])
    c.enableExtrapolation()
    return c


MEET = [(date(2026, 12, 10), .0400), (date(2027, 1, 28), .0380), (date(2027, 3, 18), .0365), (date(2027, 5, 6), .0365), (date(2027, 6, 17), .0350)]


def steps_d():
    s = S("steps_d", "02-curves/meeting-steps.md")
    op = "rates.ois.step_curve"
    jumps = [(date(2026, 12, 31), math.exp(-.0040 / 365))]
    qd = [date(2026, 11, 6), date(2026, 12, 9), date(2026, 12, 10), date(2026, 12, 11), date(2026, 12, 31), date(2027, 1, 1), date(2027, 6, 17), date(2028, 11, 6)]
    for base, steps, jp in ((.0425, MEET, ()), (.0425, MEET, jumps), (-.0040, [(date(2027, 1, 20), -.0050), (date(2027, 3, 3), -.0025)], ())):
        sc = StepCurve(AS_OF, base, steps, jp)
        qc = ql_step(AS_OF, base, steps, jp)
        dv = [sc.df(d) for d in qd]
        err = max(abs(qc.discount(Q(d)) - v) for d, v in zip(qd, dv))
        assert err < 2e-15, err
        inp = {"as_of": str(AS_OF), "base_rate": base, "steps": [{"date": str(d), "rate": r} for d, r in steps], "jumps": [{"date": str(d), "factor": f} for d, f in jp], "dates": [str(d) for d in qd]}
        fwd = [base if d < steps[0][0] else [r for sd, r in steps if sd <= d][-1] for d in qd]
        s.add(op, inp, {"discount_factors": dv, "overnight_forwards": fwd}, cls=A, verified=["exact-rational", QLV], tags=["meeting-steps"] + (["turn-of-year"] if jp else []))
        # Mutant: a step taking effect the day after its date.
        late = StepCurve(AS_OF, base, [(d + timedelta(1), r) for d, r in steps], jp)
        caught("steps_d", "step effective one day late", max(abs(late.df(d) - v) for d, v in zip(qd, dv)), 1e-12)
    note("steps_d: step curves match QuantLib ForwardCurve (backward flat) with jumps within 2e-15")
    b = {"as_of": str(AS_OF), "base_rate": .0425, "steps": [{"date": str(d), "rate": r} for d, r in MEET], "jumps": [], "dates": ["2027-01-01"]}
    s.add(op, {**b, "steps": b["steps"][::-1]}, error="E_INPUT", cls=E, tags=["invalid"], description="step dates strictly increasing")
    s.add(op, {**b, "dates": ["2026-11-05"]}, error="E_OUT_OF_RANGE", cls=E, tags=["invalid"])
    s.add(op, {**b, "steps": [{"date": "2026-11-06", "rate": .04}]}, error="E_INPUT", cls=E, tags=["invalid"], description="step on as_of")
    # Fit: base and one rate per step from OIS quotes, quote j's pillar in (step_j, step_{j+1}].
    fop = "rates.ois.fit_steps"
    for conv, base, steps, tenors, jp in (("SOFR", .0425, MEET, ["3W", "2M", "3M", "5M", "6M", "1Y"], ()), ("ESTR", .0190, [(date(2026, 12, 17), .0175), (date(2027, 2, 4), .0160)], ["1M", "2M", "6M"], jumps)):
        qc = ql_step(AS_OF, base, steps, jp)
        h = ql.YieldTermStructureHandle(qc)
        c = RT.CONV[conv]
        quotes = []
        for t in tenors:
            sw = ql.MakeOIS(B.qper(t), qindex(conv, h), 0.0, settlementDays=c["spot_lag"], paymentLag=c["payment_lag"], pricingEngine=ql.DiscountingSwapEngine(h), telescopicValueDates=True)
            quotes.append((t, sw.fairRate()))
        per = [ois_periods(conv, AS_OF, t) for t, _ in quotes]
        pil = [p[-1][2] for p in per]
        bounds = [AS_OF] + [d for d, _ in steps] + [date(2200, 1, 1)]
        assert all(bounds[j] < pil[j] <= bounds[j + 1] for j in range(len(pil))), (pil, bounds)
        # Replay: sequential, each quote fixes the newest rate.
        got = []
        for j in range(len(quotes)):
            def err(x):
                g = got + [x]
                return ois_par(conv, per[j], StepCurve(AS_OF, g[0], [(d, r) for (d, _), r in zip(steps, g[1:])], jp)) - quotes[j][1]
            got.append(brentq(err, -.5, .5, xtol=1e-16, rtol=1e-15, maxiter=500))
        truth = [base] + [r for _, r in steps]
        assert max(abs(a - b) for a, b in zip(got, truth)) < 1e-12, (got, truth)
        s.add(fop, {"convention": conv, "as_of": str(AS_OF), "step_dates": [str(d) for d, _ in steps], "quotes": B.jq(quotes), "jumps": [{"date": str(d), "factor": f} for d, f in jp]},
              {"base_rate": base, "step_rates": [r for _, r in steps]}, cls=R, verified=[QLV, "known-truth", "independent-replay"], tags=[conv, "meeting-steps"],
              limit={"absolute": 1e-10, "relative": 0.0, "reason": "known truth; QuantLib quotes carry about 1e-16 of rounding, amplified by short accruals"})
    note("steps_d: fit recovers the step rates behind QuantLib MakeOIS par rates within 1e-12")
    b = {"convention": "SOFR", "as_of": str(AS_OF), "step_dates": [str(d) for d, _ in MEET[:2]], "quotes": B.jq([("3W", .0425), ("2M", .042), ("3M", .041)]), "jumps": []}
    s.add(fop, {**b, "quotes": b["quotes"][:2]}, error="E_INPUT", cls=E, tags=["invalid"], description="quotes must number steps + 1")
    s.add(fop, {**b, "quotes": B.jq([("3W", .0425), ("3M", .042), ("4M", .041)])}, error="E_INPUT", cls=E, tags=["invalid", "ruling"], description="quote 1's pillar is past step 2")
    s.add(fop, {**b, "quotes": B.jq([("2W", .0425), ("3W", .042), ("3M", .041)])}, error="E_INPUT", cls=E, tags=["invalid", "ruling"], description="quote 1's pillar is not after step 1")
    write(s)


# ---------------------------------------------------------------- D1d: futures convexity
def hw_bias(price, t, T, sigma, a):
    d = T - t
    if a == 0:
        tdt, lam_f, tt = d, 2 * t, t
    else:
        tdt, lam_f, tt = (1 - math.exp(-a * d)) / a, (1 - math.exp(-2 * a * t)) / a, (1 - math.exp(-a * t)) / a
    h = sigma * sigma / 2
    z = h * lam_f * tdt * tdt + h * tdt * tt * tt
    F = (100 - price) / 100
    return -math.expm1(-z) * (F + 1 / d)


def futures_d():
    s = S("futures_d", "02-curves/futures-convexity.md")
    op = "rates.futures.convexity"
    for price, t, T, sg, a in ((96.0, .25, .5, .01, .03), (96.5, 2.0, 2.25, .012, .05), (97.2, 5.0, 5.25, .009, 0.0), (101.0, 1.0, 1.25, .008, .1), (95.5, 9.75, 10.0, .011, .02), (96.0, 1.0, 1.0833333333333333, .01, .03)):
        bq = ql.HullWhite.convexityBias(price, t, T, sg, a)
        bm = hw_bias(price, t, T, sg, a)
        assert abs(bq - bm) < 1e-15 + 1e-12 * abs(bq), (bq, bm)
        F = (100 - price) / 100
        s.add(op, {"price": price, "start_years": t, "end_years": T, "sigma": sg, "mean_reversion": a},
              {"futures_rate": F, "convexity": bq, "forward_rate": F - bq}, cls=A, verified=[QLV, "analytic"], tags=["hull-white"])
        hl = sg * sg * t * T / 2
        if a > 0 and t >= 1:
            caught("futures_d", f"Ho-Lee sigma^2 t T / 2 at t={t}", abs(hl - bq), 1e-12 + 1e-10 * abs(bq))
        caught("futures_d", f"convexity added, not subtracted, t={t}", 2 * abs(bq), 1e-12 + 1e-10 * abs(F))
    note("futures_d: Hull-White convexity matches QuantLib HullWhite.convexityBias, including a = 0 by limit")
    b = {"price": 96.0, "start_years": 1.0, "end_years": 1.25, "sigma": .01, "mean_reversion": .03}
    s.add(op, {**b, "end_years": 1.0}, error="E_INPUT", cls=E, tags=["invalid"], description="end must be after start")
    s.add(op, {**b, "start_years": -0.1}, error="E_DOMAIN", cls=E, tags=["invalid"])
    s.add(op, {**b, "sigma": -0.01}, error="E_DOMAIN", cls=E, tags=["invalid"])
    s.add(op, {**b, "mean_reversion": -0.01}, error="E_DOMAIN", cls=E, tags=["invalid"])
    write(s)


# ---------------------------------------------------------------- D1e: CSA discounting, index basis, joint calibration
def csa_d():
    s = S("csa_d", "02-curves/csa-and-basis.md")
    cv, dfs, per = bootstrap_ois_j("SOFR", AS_OF, B.SOFR_Q)
    pil = [p[-1][2] for p in per]
    jc = jcurve(cv, pil, dfs)
    ev, edf, eper = bootstrap_ois_j("ESTR", AS_OF, ESTR_Q)
    epil = [p[-1][2] for p in eper]
    je = jcurve(ev, epil, edf)
    op = "rates.csa.discount"
    qd = [date(2027, 5, 6), date(2028, 11, 6), date(2031, 11, 6), date(2036, 11, 6)]
    for spr in (0.0, .0025, -.0010):
        dv = [cv.df(d) * math.exp(-spr * (d - AS_OF).days / 365) for d in qd]
        s.add(op, {"curve": jc, "collateral_spread": spr, "fx": None, "dates": [str(d) for d in qd]}, {"discount_factors": dv}, cls=I, verified=["independent-replay"], tags=["csa"])
        if spr:
            caught("csa_d", f"collateral spread sign flipped ({spr})", max(abs(v - cv.df(d) * math.exp(spr * (d - AS_OF).days / 365)) for d, v in zip(qd, dv)), 1e-10)
    # USD trade, EUR cash collateral at ESTR: D(t) = D_EUR(t) * S / F(t), F in USD per EUR.
    Sx = 1.0850
    fw = [(d, Sx * ev.df(d) / cv.df(d) * math.exp(.0012 * (d - AS_OF).days / 365)) for d in qd]
    for spr in (0.0, .0005):
        dv = [ev.df(d) * Sx / F * math.exp(-spr * (d - AS_OF).days / 365) for d, F in fw]
        s.add(op, {"curve": je, "collateral_spread": spr, "fx": {"spot": Sx, "forwards": [{"date": str(d), "forward": F} for d, F in fw]}, "dates": [str(d) for d in qd]},
              {"discount_factors": dv}, cls=I, verified=["independent-replay", "analytic"], tags=["csa", "cross-currency-collateral"])
        caught("csa_d", "forward ratio inverted", max(abs(v - ev.df(d) * F / Sx) for (d, F), v in zip(fw, dv)), 1e-10)
    s.add(op, {"curve": je, "collateral_spread": 0.0, "fx": {"spot": Sx, "forwards": [{"date": str(qd[0]), "forward": fw[0][1]}]}, "dates": [str(qd[1])]}, error="E_INPUT", cls=E, tags=["invalid"], description="a date with no forward")
    s.add(op, {"curve": je, "collateral_spread": 0.0, "fx": {"spot": 0.0, "forwards": [{"date": str(qd[0]), "forward": fw[0][1]}]}, "dates": [str(qd[0])]}, error="E_DOMAIN", cls=E, tags=["invalid"])
    # Index basis: spread on leg B so the two overnight legs match, same periods and discounting.
    bop = "rates.basis.ois_spread"
    proj_b = Curve(AS_OF, pil, [v * math.exp(-.0008 * (d - AS_OF).days / 365) for d, v in zip(pil, dfs)])
    jb = jcurve(proj_b, pil, [proj_b.df(d) for d in pil])
    h = ql.YieldTermStructureHandle(ql_ois("SOFR", AS_OF, B.SOFR_Q))
    qb = ql.DiscountCurve([Q(AS_OF)] + [Q(d) for d in pil], [1.0] + [proj_b.df(d) for d in pil], ql.Actual365Fixed())
    qb.enableExtrapolation()
    hb = ql.YieldTermStructureHandle(qb)
    c = RT.CONV["SOFR"]
    for tenor in ("2Y", "5Y", "10Y"):
        p = ois_periods("SOFR", AS_OF, tenor)
        a, fa = ois_legs("SOFR", p, cv)
        fb = sum((proj_b.df(x) / proj_b.df(y) - 1) * cv.df(z) for x, y, z in p)
        spread = (fa - fb) / a
        ra = ql.MakeOIS(B.qper(tenor), qindex("SOFR", h), 0.0, settlementDays=2, paymentLag=2, pricingEngine=ql.DiscountingSwapEngine(h), telescopicValueDates=True).fairRate()
        rb = ql.MakeOIS(B.qper(tenor), qindex("SOFR", hb), 0.0, settlementDays=2, paymentLag=2, pricingEngine=ql.DiscountingSwapEngine(h), telescopicValueDates=True).fairRate()
        assert abs((ra - rb) - spread) < 1e-12, (ra - rb, spread)
        s.add(bop, {"convention": "SOFR", "tenor": tenor, "discount": jc, "projection_a": jc, "projection_b": jb}, {"spread": spread}, cls=I, verified=["independent-replay", QLV], tags=["index-basis"],
              limit={"absolute": 1e-10, "relative": 0.0, "reason": "curve tolerance"})
        caught("csa_d", f"basis {tenor} projected and discounted on leg B's curve", abs(spread - (fa - sum((proj_b.df(x) / proj_b.df(y) - 1) * proj_b.df(z) for x, y, z in p)) / a), 1e-10)
    note("csa_d: OIS index basis equals the difference of QuantLib par rates on the two projection curves within 1e-12")
    # Joint calibration: discount from OIS quotes and projection from term quotes in one solve; agrees with the two-step build.
    jop = "rates.curve.joint_bootstrap"
    qd2 = ql_ois("SOFR", AS_OF, B.SOFR_Q)
    dh = ql.YieldTermStructureHandle(qd2)
    idx = B.ql_term()
    hs = []
    for q in B.proj_quotes():
        qq = ql.QuoteHandle(ql.SimpleQuote(q["rate"]))
        if q["type"] == "DEPOSIT":
            hs.append(ql.DepositRateHelper(qq, idx))
        elif q["type"] == "FRA":
            hs.append(ql.FraRateHelper(qq, q["start_months"], idx))
        else:
            hs.append(ql.SwapRateHelper(qq, ql.Period(q["months"], ql.Months), idx.fixingCalendar(), ql.Annual, ql.ModifiedFollowing, ql.Thirty360(ql.Thirty360.BondBasis), idx, ql.QuoteHandle(), ql.Period(0, ql.Days), dh))
    qp = ql.PiecewiseLogLinearDiscount(Q(AS_OF), hs, ql.Actual365Fixed())
    qp.enableExtrapolation()
    pc, pd, pp = B.bootstrap_proj(cv, AS_OF, B.proj_quotes(), "LOG_LINEAR_DF")
    assert max(abs(qp.discount(Q(d)) - v) for d, v in zip(pp, pd)) < 1e-10
    for meth in ("SEQUENTIAL", "GLOBAL"):
        s.add(jop, {"convention": "SOFR", "index": "USD-TERM-3M", "as_of": str(AS_OF), "ois_quotes": B.jq(B.SOFR_Q), "term_quotes": B.proj_quotes(), "interpolation": "LOG_LINEAR_DF", "method": meth},
              {"discount_pillars": pillars(pil, dfs), "projection_pillars": pillars(pp, pd)}, cls=I, verified=["independent-replay", QLV], tags=["joint"], limit=DFLIM)
    single = B.bootstrap_proj(Curve(AS_OF, pp, pd), AS_OF, B.proj_quotes(), "LOG_LINEAR_DF")[1]
    caught("csa_d", "projection discounted on itself (single curve)", max(abs(a - b) for a, b in zip(single, pd)), 1e-9)
    s.add(jop, {"convention": "SOFR", "index": "USD-TERM-3M", "as_of": str(AS_OF), "ois_quotes": [], "term_quotes": B.proj_quotes(), "interpolation": "LOG_LINEAR_DF", "method": "GLOBAL"}, error="E_INPUT", cls=E, tags=["invalid"])
    note("csa_d: joint bootstrap agrees with QuantLib's two-step build within 1e-10")
    write(s)


# ---------------------------------------------------------------- D1f: regularised and outlier-robust curve fits
def smooth_matrix(knots, mats):
    Bm = []
    for m in mats:
        row, prev = [], Fr(0)
        for k in knots:
            row.append((min(Fr(m), Fr(k)) - prev if Fr(m) > prev else Fr(0)) / Fr(m))
            prev = Fr(k)
        Bm.append(row)
    return Bm


def solve_exact(Mx, v):
    n = len(v)
    M = [row[:] + [v[i]] for i, row in enumerate(Mx)]
    for c in range(n):
        p = next(r for r in range(c, n) if M[r][c] != 0)
        M[c], M[p] = M[p], M[c]
        for r in range(n):
            if r != c and M[r][c] != 0:
                f = M[r][c] / M[c][c]
                M[r] = [a - f * b for a, b in zip(M[r], M[c])]
    return [M[i][n] / M[i][i] for i in range(n)]


def smooth_fit(knots, mats, ys, lam, w=None, penalise_levels=False):
    Bm = smooth_matrix(knots, mats)
    n, w = len(knots), w or [1] * len(mats)
    W = [Fr(x) for x in w]
    Mx = [[sum(W[j] * Bm[j][a] * Bm[j][b] for j in range(len(mats))) for b in range(n)] for a in range(n)]
    v = [sum(W[j] * Bm[j][a] * Fr(ys[j]) for j in range(len(mats))) for a in range(n)]
    L = Fr(lam)
    for k in range(n - 1 if not penalise_levels else n):
        if penalise_levels:
            Mx[k][k] += L
        else:
            Mx[k][k] += L
            Mx[k + 1][k + 1] += L
            Mx[k][k + 1] -= L
            Mx[k + 1][k] -= L
    f = solve_exact(Mx, v)
    fit = [sum(Bm[j][a] * f[a] for a in range(n)) for j in range(len(mats))]
    obj = sum(W[j] * (fit[j] - Fr(ys[j])) ** 2 for j in range(len(mats))) + L * sum((f[k + 1] - f[k]) ** 2 for k in range(n - 1))
    return f, fit, obj


def ns_load(m, tau):
    x = mp.mpf(m) / mp.mpf(tau)
    e = (1 - mp.e ** (-x)) / x
    return [mp.mpf(1), e, e - mp.e ** (-x)]


def huber_irls(mats, ys, tau, delta):
    X = [ns_load(m, tau) for m in mats]
    y = [mp.mpf(v) for v in ys]
    b = [mp.mpf(0)] * 3
    for _ in range(400):
        r = [sum(X[j][k] * b[k] for k in range(3)) - y[j] for j in range(len(y))]
        w = [1 if abs(rj) <= delta else delta / abs(rj) for rj in r]
        M = mp.matrix(3, 3)
        v = mp.matrix(3, 1)
        for j in range(len(y)):
            for a in range(3):
                v[a] += w[j] * X[j][a] * y[j]
                for c in range(3):
                    M[a, c] += w[j] * X[j][a] * X[j][c]
        nb = mp.lu_solve(M, v)
        nb = [nb[k] for k in range(3)]
        if max(abs(nb[k] - b[k]) for k in range(3)) < mp.mpf(10) ** -40:
            b = nb
            break
        b = nb
    r = [sum(X[j][k] * b[k] for k in range(3)) - y[j] for j in range(len(y))]
    return b, r


def fits_d():
    s = S("fits_d", "03-calibration/curve-fits.md")
    op = "calib.curve.smooth"
    knots = [.5, 1, 2, 3, 5, 7, 10]
    mats = [.25, .5, 1, 1.5, 2, 3, 4, 5, 7, 10]
    ys = [.0420, .0415, .0398, .0385, .0376, .0365, .0362, .0364, .0371, .0380]
    for lam in (0.0, 1e-4, 1e-2):
        f, fit, obj = smooth_fit(knots, mats, ys, lam)
        Bn = np.array([[float(x) for x in r] for r in smooth_matrix(knots, mats)])
        Dm = np.diff(np.eye(len(knots)), axis=0)
        fn = np.linalg.solve(Bn.T @ Bn + lam * Dm.T @ Dm, Bn.T @ np.array(ys))
        assert np.max(np.abs(fn - np.array([float(x) for x in f]))) < 1e-9
        s.add(op, {"knots": knots, "maturities": mats, "zero_rates": ys, "lambda": lam}, {"forwards": [float(x) for x in f], "fitted": [float(x) for x in fit], "objective": float(obj)},
              cls=A, verified=["exact-rational", "numpy"], tags=["regularised"], limit={"absolute": 1e-10, "relative": 1e-8, "reason": "linear solve; condition number up to about 1e3"})
        if lam:
            fl, _, _ = smooth_fit(knots, mats, ys, lam, penalise_levels=True)
            caught("fits_d", f"smooth fit penalising levels, lambda {lam}", float(max(abs(a - b) for a, b in zip(f, fl))), 1e-10 + 1e-8 * .05)
    w = [1, 1, 2, 2, 1, 1, 1, 1, .5, .5]
    f, fit, obj = smooth_fit(knots, mats, ys, 1e-3, w)
    s.add(op, {"knots": knots, "maturities": mats, "zero_rates": ys, "lambda": 1e-3, "weights": w}, {"forwards": [float(x) for x in f], "fitted": [float(x) for x in fit], "objective": float(obj)},
          cls=A, verified=["exact-rational"], tags=["regularised"], limit={"absolute": 1e-10, "relative": 1e-8, "reason": "linear solve"})
    s.add(op, {"knots": knots, "maturities": mats + [12], "zero_rates": ys + [.038], "lambda": 0.0}, error="E_INPUT", cls=E, tags=["invalid"], description="maturity past the last knot")
    s.add(op, {"knots": knots, "maturities": mats[:3], "zero_rates": ys[:3], "lambda": 0.0}, error="E_SINGULAR", cls=E, tags=["invalid"], description="fewer maturities than knots, no penalty")
    s.add(op, {"knots": knots, "maturities": mats, "zero_rates": ys, "lambda": -1.0}, error="E_DOMAIN", cls=E, tags=["invalid"])
    s.add(op, {"knots": [1, .5], "maturities": [.25], "zero_rates": [.04], "lambda": 1.0}, error="E_INPUT", cls=E, tags=["invalid"])
    note("fits_d: smoothness-regularised forward fits solved in exact rationals; NumPy agrees within 1e-9")
    rop = "calib.curve.robust"
    mats = [.25, .5, 1, 2, 3, 4, 5, 7, 10, 15, 20, 30]
    base = [ns_load(m, 2.0) for m in mats]
    tb = [.040, -.004, .006]
    ys = [float(sum(a * b for a, b in zip(x, tb))) for x in base]
    for outl, delta, tau in (({4: .0030}, .0005, 2.0), ({2: -.0025, 9: .0020}, .0004, 2.0), ({}, .0005, 1.5), ({6: .0015}, .0003, 3.0)):
        yy = [y + outl.get(j, 0) + (j % 3 - 1) * 1e-5 for j, y in enumerate(ys)]
        b, r = huber_irls(mats, yy, tau, mp.mpf(delta))
        rf = [float(x) for x in r]
        assert all(abs(abs(x) - delta) > 1e-6 for x in rf), "a residual sits near the Huber threshold"
        Xn = np.array([[float(v) for v in ns_load(m, tau)] for m in mats])
        for st in ([0, 0, 0], [.05, .02, -.03], [.02, -.01, .01]):
            sol = least_squares(lambda p: Xn @ p - np.array(yy), st, loss="huber", f_scale=delta, xtol=1e-15, ftol=1e-15, gtol=1e-15)
            assert np.max(np.abs(sol.x - np.array([float(x) for x in b]))) < 1e-8, (sol.x, b)
        out = [j for j, x in enumerate(rf) if abs(x) > delta]
        obj = sum((x * x / 2 if abs(x) <= delta else delta * abs(x) - delta * delta / 2) for x in r)
        s.add(rop, {"maturities": mats, "zero_rates": yy, "tau": tau, "delta": delta}, {"betas": [float(x) for x in b], "residuals": rf, "outliers": out, "objective": float(obj)},
              cls="calibration", verified=["independent-replay", "scipy-least-squares-huber"], tags=["outlier-robust"],
              output_classes={"outliers": E}, limit={"absolute": 1e-9, "relative": 0.0, "reason": "convex objective, unique minimum; reached by IRLS and SciPy from three starts"})
        ls = np.linalg.lstsq(Xn, np.array(yy), rcond=None)[0]
        if outl:
            caught("fits_d", f"plain least squares instead of Huber ({sorted(outl)})", float(np.max(np.abs(ls - np.array([float(x) for x in b])))), 1e-9)
    note("fits_d: Huber Nelson-Siegel fits (fixed tau) agree with SciPy least_squares loss='huber' from three starts within 1e-8")
    s.add(rop, {"maturities": mats, "zero_rates": ys, "tau": 2.0, "delta": 0.0}, error="E_DOMAIN", cls=E, tags=["invalid"])
    s.add(rop, {"maturities": mats, "zero_rates": ys, "tau": -1.0, "delta": .0005}, error="E_DOMAIN", cls=E, tags=["invalid"])
    s.add(rop, {"maturities": mats[:2], "zero_rates": ys[:2], "tau": 2.0, "delta": .0005}, error="E_INPUT", cls=E, tags=["invalid"], description="fewer than 3 points")
    s.add(rop, {"maturities": [0.0] + mats[1:], "zero_rates": ys, "tau": 2.0, "delta": .0005}, error="E_DOMAIN", cls=E, tags=["invalid"], description="maturity must be > 0")
    write(s)


def wave1():
    ois_d()
    compound_d()
    steps_d()
    futures_d()
    csa_d()
    fits_d()


def main():
    MUTANTS.clear()
    wave1()
    note(f"stage D: {len(MUTANTS)} wrong-convention checks, each caught")
    for su, name, gap in MUTANTS:
        note(f"  mutant {su}: {name}: gap {gap:.3e}")


if __name__ == "__main__":
    main()
