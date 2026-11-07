"""Stage B golden cases. All market data here is synthetic. Checks each result against QuantLib or a hand calculation."""
import itertools
import math
from datetime import date, timedelta
from decimal import ROUND_HALF_EVEN, Decimal
from fractions import Fraction as Fr

import numpy as np
import QuantLib as ql
from scipy.optimize import least_squares

from qf_oracle import common
from qf_oracle.common import Suite, note
from qf_oracle.dates import is_business, yf
from qf_oracle.rates import (CONV, Curve, add_bd, add_months, adjust, bootstrap, bootstrap_ois, end_date, jac_fd, last_bd, ois_legs, ois_par,
                             ois_periods, schedule)

G = "oracle/python/gen_stage_b.py"
E = "date_and_convention"
I = "interpolation"
SYN = "synthetic"
AS_OF = date(2026, 11, 6)
SONIA_Q = [("1W", .0372), ("1M", .0371), ("3M", .0368), ("6M", .0362), ("1Y", .0350), ("2Y", .0335), ("3Y", .0330), ("5Y", .0335), ("7Y", .0345), ("10Y", .0360), ("15Y", .0375), ("20Y", .0380), ("30Y", .0370)]
SOFR_Q = [(t, r + .0015) for t, r in SONIA_Q]
TERM = dict(day_count="ACT_360", calendar="USGS", spot_lag=2, months=3, fixed_months=12, fixed_day_count="THIRTY_360_BOND")
Q = lambda d: ql.Date(d.day, d.month, d.year)  # noqa: E731
DFLIM = {"absolute": 1e-9, "relative": 0.0, "reason": "stage-b-targets: discount factors within 1e-9; curve solves stop at 1e-13 in rate"}
PVLIM = {"absolute": 1e-3, "relative": 1e-9, "reason": "1e-9 per unit of notional on 1e6: the curve solve's tolerance carried through"}


def S(name, spec):
    s = Suite(name, f"specifications/{spec}", G)
    return s


def write(s):
    keep = common.GOLDEN
    if s.name != "units":  # every other stage B input is constructed, not observed
        for c in s.cases:
            if SYN not in c["tags"]:
                c["tags"].append(SYN)
    common.GOLDEN = keep.parent / "stage_b"
    s.write()
    common.GOLDEN = keep


def qper(t):
    return ql.Period(int(t[:-1]), {"W": ql.Weeks, "M": ql.Months, "Y": ql.Years}[t[-1]])


def jq(quotes):
    return [{"tenor": t, "rate": r} for t, r in quotes]


def jcurve(c, dates, dfs):
    return {"as_of": str(c.as_of), "interpolation": c.interp, "pillars": [{"date": str(d), "discount_factor": v} for d, v in zip(dates, dfs)]}


def units():
    s = S("units", "01-core/units-and-money.md")
    cv = "core.units.convert"
    for v, a, b, r in ((5.0, "PERCENT", "DECIMAL", 0.05), (0.05, "DECIMAL", "BP", 500.0), (25.0, "BP", "PERCENT", 0.25), (-12.5, "BP", "DECIMAL", -0.00125), (0.0, "BP", "BP", 0.0)):
        s.add(cv, {"value": v, "from": a, "to": b}, {"value": r}, verified=["hand"])
    s.add(cv, {"value": 1.0, "from": "PIPS", "to": "BP"}, error="E_SCHEMA", cls=E, tags=["invalid"])
    rd, ad = "core.units.round_money", "core.units.add_money"
    for amt, ccy in (("2.675", "GBP"), ("2.665", "GBP"), ("-2.675", "USD"), ("1000.5", "JPY"), ("1001.5", "JPY"), ("0.005", "EUR"), ("0.015", "EUR"), ("123456789012345678.12345678", "USD")):
        places = 0 if ccy == "JPY" else 2
        r = Decimal(amt).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_EVEN)
        s.add(rd, {"amount": amt, "currency": ccy}, {"amount": format(r, "f"), "currency": ccy}, cls=E, verified=["python-decimal"])
    s.add(ad, {"a": {"amount": "0.1", "currency": "GBP"}, "b": {"amount": "0.2", "currency": "GBP"}}, {"amount": "0.3", "currency": "GBP"}, cls=E, verified=["hand"], description="decimal, so no binary rounding")
    s.add(ad, {"a": {"amount": "1.50", "currency": "GBP"}, "b": {"amount": "-1.5", "currency": "GBP"}}, {"amount": "0", "currency": "GBP"}, cls=E, verified=["hand"])
    s.add(ad, {"a": {"amount": "1", "currency": "GBP"}, "b": {"amount": "1", "currency": "USD"}}, error="E_CURRENCY_MISMATCH", cls=E, tags=["invalid"])
    s.add(rd, {"amount": "1.5", "currency": "XXX"}, error="E_SCHEMA", cls=E, tags=["invalid"])
    s.add(rd, {"amount": "1e3", "currency": "GBP"}, error="E_SCHEMA", cls=E, tags=["invalid"])
    s.add(rd, {"amount": "1234567890123456789.0", "currency": "GBP"}, error="E_LIMIT", cls=E, tags=["invalid"])
    lk = "core.conventions.lookup"
    for k, c in CONV.items():
        s.add(lk, {"id": k}, {"kind": "OVERNIGHT", **c, "business_day_convention": "MODIFIED_FOLLOWING"}, cls=E, verified=["strata-2.12.78-source"])
    s.add(lk, {"id": "USD-TERM-3M"}, {"kind": "TERM", "currency": "USD", **TERM, "business_day_convention": "MODIFIED_FOLLOWING"}, cls=E, verified=["hand"], tags=[SYN])
    s.add(lk, {"id": "GBPUSD"}, {"kind": "FX", "base": "GBP", "quote": "USD", "spot_lag": 2, "calendars": ["GBLO", "USGS"], "pip": 0.0001}, cls=E, verified=["hand"])
    s.add(lk, {"id": "EURUSD"}, {"kind": "FX", "base": "EUR", "quote": "USD", "spot_lag": 2, "calendars": ["EUTA", "USGS"], "pip": 0.0001}, cls=E, verified=["hand"])
    s.add(lk, {"id": "NOPE"}, error="E_SCHEMA", cls=E, tags=["invalid"])
    write(s)


def schedules():
    s = S("schedule", "02-curves/schedules.md")
    op = "rates.schedule.generate"
    qcal = {"GBLO": ql.UnitedKingdom(ql.UnitedKingdom.Settlement), "EUTA": ql.TARGET()}
    for cal, st, en, m, eom, lag in (("GBLO", date(2026, 11, 6), date(2031, 11, 6), 12, False, 0), ("GBLO", date(2026, 11, 6), date(2029, 3, 6), 6, False, 0), ("GBLO", date(2026, 11, 6), date(2028, 1, 31), 3, False, 2),
                                     ("EUTA", date(2026, 11, 30), date(2029, 11, 30), 3, True, 0), ("EUTA", date(2027, 2, 26), date(2029, 2, 28), 6, True, 1)):
        sc = ql.Schedule(Q(st), Q(en), ql.Period(m, ql.Months), qcal[cal], ql.ModifiedFollowing, ql.ModifiedFollowing, ql.DateGeneration.Backward, eom)
        qd = [d.ISO() for d in sc]
        b = schedule(cal, st, en, m, eom)
        assert [str(x) for x in b] == qd, (qd, b)
        per = [{"start": str(x), "end": str(y), "payment": str(add_bd(cal, y, lag))} for x, y in zip(b, b[1:])]
        s.add(op, {"start": str(st), "end": str(en), "frequency_months": m, "calendar": cal, "end_of_month": eom, "payment_lag": lag}, {"periods": per}, cls=E, verified=["quantlib-1.44"])
    b = {"calendar": "GBLO", "end_of_month": False, "payment_lag": 0}
    s.add(op, {**b, "start": "2027-01-01", "end": "2026-01-01", "frequency_months": 3}, error="E_DATE_ORDER", cls=E, tags=["invalid"])
    s.add(op, {**b, "start": "2026-01-02", "end": "2027-01-04", "frequency_months": 5}, error="E_SCHEMA", cls=E, tags=["invalid"])
    write(s)


def curves():
    s = S("curve", "02-curves/curve-framework.md")
    dates = [date(2027, 11, 8), date(2031, 11, 6), date(2036, 11, 6)]
    dfs = [0.965, 0.84, 0.70]
    qd = [date(2026, 11, 6), date(2027, 5, 6), date(2027, 11, 8), date(2029, 6, 15), date(2036, 11, 6), date(2040, 1, 2)]
    for ip in ("LOG_LINEAR_DF", "LINEAR_ZERO"):
        c = Curve(AS_OF, dates, dfs, ip)
        ql.Settings.instance().evaluationDate = Q(AS_OF)
        if ip == "LOG_LINEAR_DF":
            qc = ql.DiscountCurve([Q(AS_OF)] + [Q(d) for d in dates], [1.0] + dfs, ql.Actual365Fixed())
            qc.enableExtrapolation()
            assert max(abs(qc.discount(Q(d)) - c.df(d)) for d in qd) < 1e-13
        v = [c.df(d) for d in qd]
        z = [None if d == AS_OF else -math.log(c.df(d)) / ((d - AS_OF).days / 365) for d in qd]
        s.add("rates.curve.discount", {"curve": jcurve(c, dates, dfs), "dates": [str(d) for d in qd]}, {"discount_factors": v, "zero_rates": z}, cls=I, verified=["hand", "quantlib-1.44"] if ip == "LOG_LINEAR_DF" else ["hand"])
        a, b = date(2027, 2, 8), date(2027, 5, 10)
        f = (c.df(a) / c.df(b) - 1) / float(yf("ACT_360", a, b))
        s.add("rates.curve.forward", {"curve": jcurve(c, dates, dfs), "start": str(a), "end": str(b), "day_count": "ACT_360"}, {"forward": f}, cls=I, verified=["hand"])
    c = jcurve(Curve(AS_OF, dates, dfs), dates, dfs)
    s.add("rates.curve.discount", {"curve": c, "dates": ["2026-11-05"]}, error="E_OUT_OF_RANGE", cls=E, tags=["invalid"])
    bad = {**c, "pillars": list(reversed(c["pillars"]))}
    s.add("rates.curve.discount", {"curve": bad, "dates": ["2027-01-01"]}, error="E_INPUT", cls=E, tags=["invalid"])
    neg = {**c, "pillars": [{"date": "2027-11-08", "discount_factor": -0.5}]}
    s.add("rates.curve.discount", {"curve": neg, "dates": ["2027-01-01"]}, error="E_DOMAIN", cls=E, tags=["invalid"])
    write(s)


def qindex(conv):
    if conv == "SONIA":
        return ql.OvernightIndex("S", 0, ql.GBPCurrency(), ql.UnitedKingdom(ql.UnitedKingdom.Settlement), ql.Actual365Fixed())
    return ql.OvernightIndex("F", 0, ql.USDCurrency(), ql.UnitedStates(ql.UnitedStates.GovernmentBond), ql.Actual360())


def ql_ois(conv, as_of, quotes, ip):
    ql.Settings.instance().evaluationDate = Q(as_of)
    c = CONV[conv]
    hs = [ql.OISRateHelper(c["spot_lag"], qper(t), ql.QuoteHandle(ql.SimpleQuote(r)), qindex(conv), ql.YieldTermStructureHandle(), True, c["payment_lag"]) for t, r in quotes]
    k = ql.PiecewiseLogLinearDiscount if ip == "LOG_LINEAR_DF" else ql.PiecewiseLinearZero
    q = k(Q(as_of), hs, ql.Actual365Fixed())
    q.enableExtrapolation()
    return q


def ois():
    s = S("ois", "02-curves/ois-curves.md")
    op = "rates.ois.bootstrap"
    for conv, quotes in (("SONIA", SONIA_Q), ("SOFR", SOFR_Q)):
        for as_of in (AS_OF, date(2026, 11, 30)):
            for ip in ("LOG_LINEAR_DF", "LINEAR_ZERO"):
                cv, dfs, per = bootstrap_ois(conv, as_of, quotes, ip)
                q = ql_ois(conv, as_of, quotes, ip)
                pil = [p[-1][2] for p in per]
                assert max(abs(q.discount(Q(d)) - v) for d, v in zip(pil, dfs)) < 5e-12
                for meth in ("SEQUENTIAL", "GLOBAL"):
                    s.add(op, {"convention": conv, "as_of": str(as_of), "quotes": jq(quotes), "interpolation": ip, "method": meth},
                          {"pillars": [{"date": str(d), "discount_factor": v} for d, v in zip(pil, dfs)]}, cls=I, verified=["independent-replay", "quantlib-1.44"], tags=[SYN], limit=DFLIM)
    note("ois: replay matches QuantLib to 5e-12 at every pillar, SONIA and SOFR, both interpolations")
    neg = [(t, r - .05) for t, r in SONIA_Q[:6]]
    cv, dfs, per = bootstrap_ois("SONIA", AS_OF, neg)
    q = ql_ois("SONIA", AS_OF, neg, "LOG_LINEAR_DF")
    pil = [p[-1][2] for p in per]
    assert max(abs(q.discount(Q(d)) - v) for d, v in zip(pil, dfs)) < 5e-12 and dfs[-1] > 1
    s.add(op, {"convention": "SONIA", "as_of": str(AS_OF), "quotes": jq(neg), "interpolation": "LOG_LINEAR_DF", "method": "GLOBAL"}, {"pillars": [{"date": str(d), "discount_factor": v} for d, v in zip(pil, dfs)]},
          cls=I, verified=["independent-replay", "quantlib-1.44"], tags=[SYN, "negative-rates"], limit=DFLIM)
    bid = [{"tenor": t, "bid": r - .0001, "ask": r + .0001} for t, r in SONIA_Q[:5]]
    cv, dfs, per = bootstrap_ois("SONIA", AS_OF, SONIA_Q[:5])
    s.add(op, {"convention": "SONIA", "as_of": str(AS_OF), "quotes": bid, "interpolation": "LOG_LINEAR_DF", "method": "SEQUENTIAL"}, {"pillars": [{"date": str(p[-1][2]), "discount_factor": v} for p, v in zip(per, dfs)]},
          cls=I, verified=["independent-replay"], tags=[SYN], limit=DFLIM, description="mid of bid and ask, so the same as the mid quotes")
    bq = {"convention": "SONIA", "as_of": str(AS_OF), "interpolation": "LOG_LINEAR_DF", "method": "GLOBAL"}
    s.add(op, {**bq, "quotes": jq([("2Y", .03), ("1Y", .03)])}, error="E_INPUT", cls=E, tags=["invalid"])
    s.add(op, {**bq, "quotes": jq([("1Y", .03), ("12M", .03)])}, error="E_INPUT", cls=E, tags=["invalid"], description="same pillar date twice")
    s.add(op, {**bq, "quotes": []}, error="E_INPUT", cls=E, tags=["invalid"])
    s.add(op, {**bq, "quotes": [{"tenor": "1Y", "bid": .03, "ask": .02}]}, error="E_INPUT", cls=E, tags=["invalid"], description="crossed")
    s.add(op, {**bq, "convention": "TONA", "quotes": jq(SONIA_Q[:1])}, error="E_SCHEMA", cls=E, tags=["invalid"])

    cp = "rates.ois.compound"
    r, n = [.05, .0502, .0504], [1, 1, 3]
    v = Fr(1)
    for a, b in zip(r, n):
        v *= 1 + Fr(a) * b / 365
    s.add(cp, {"rates": r, "days": n, "denominator": 365}, {"compounded_rate": float((v - 1) * 365 / 5)}, verified=["exact-rational"])
    s.add(cp, {"rates": r, "days": n[:2], "denominator": 365}, error="E_INPUT", cls=E, tags=["invalid"])
    s.add(cp, {"rates": [.05], "days": [0], "denominator": 365}, error="E_INPUT", cls=E, tags=["invalid"])

    pv = "rates.ois.pv"
    for conv, quotes in (("SONIA", SONIA_Q), ("SOFR", SOFR_Q)):
        cv, dfs, per = bootstrap_ois(conv, AS_OF, quotes)
        pil = [p[-1][2] for p in per]
        jc = jcurve(cv, pil, dfs)
        q = ql_ois(conv, AS_OF, quotes, "LOG_LINEAR_DF")
        for tenor, k, side in (("5Y", .034, "PAY"), ("10Y", .036, "RECEIVE"), ("7Y", .03, "PAY")):
            p = ois_periods(conv, AS_OF, tenor)
            a, fl = ois_legs(conv, p, cv)
            N = 1e6
            val = (1 if side == "PAY" else -1) * N * (fl - k * a)
            c = CONV[conv]
            h = ql.YieldTermStructureHandle(q)
            ix = ql.OvernightIndex(qindex(conv).name(), 0, qindex(conv).currency(), qindex(conv).fixingCalendar(), qindex(conv).dayCounter(), h)
            sw = ql.MakeOIS(qper(tenor), ix, k, settlementDays=c["spot_lag"], paymentLag=c["payment_lag"], nominal=N, swapType=ql.Swap.Payer if side == "PAY" else ql.Swap.Receiver,
                            pricingEngine=ql.DiscountingSwapEngine(h), telescopicValueDates=True)
            assert abs(sw.NPV() - val) < 1e-5, (conv, tenor, sw.NPV(), val)
            s.add(pv, {"curve": jc, "trade": {"convention": conv, "tenor": tenor, "fixed_rate": k, "notional": N, "side": side}, "snapshot_id": "sha256:" + "ab" * 32},
                  {"valuation": {"pv": val, "currency": c["currency"], "model": "OIS_DISCOUNTING", "data_version": "sha256:" + "ab" * 32, "conventions": conv, "as_of": str(AS_OF)}, "par_rate": fl / a, "annuity": a},
                  cls=I, verified=["independent-replay", "quantlib-1.44"], tags=[SYN], limit=PVLIM)
    note("ois: swap PVs match QuantLib OvernightIndexedSwap within 1e-5 on 1e6, with and without payment lag")
    # Payment lag: telescoping fails, and the spec's formula is what matches.
    cv, dfs, per = bootstrap_ois("SOFR", AS_OF, SOFR_Q)
    p = ois_periods("SOFR", AS_OF, "10Y")
    tele = cv.df(p[0][0]) - cv.df(p[-1][1])
    gap = abs(ois_legs("SOFR", p, cv)[1] - tele)
    assert gap > 1e-5
    note(f"ois: with payment lag the telescoped form misses the leg by {gap:.2e} per unit notional on 10Y")
    write(s)
    return


def term_periods(as_of, tenor_m, months):
    cal = TERM["calendar"]
    spot = add_bd(cal, as_of, TERM["spot_lag"])
    return spot, schedule(cal, spot, add_months(spot, tenor_m), months)


def swap_legs(disc, proj, as_of, tenor_m):
    _, fx = term_periods(as_of, tenor_m, TERM["fixed_months"])
    _, fl = term_periods(as_of, tenor_m, TERM["months"])
    ann = sum(float(yf(TERM["fixed_day_count"], a, b)) * disc.df(b) for a, b in zip(fx, fx[1:]))
    flt = sum((proj.df(a) / proj.df(b) - 1) * disc.df(b) for a, b in zip(fl, fl[1:]))
    return ann, flt


def proj_quotes():
    return [{"type": "DEPOSIT", "months": 3, "rate": .0395}, {"type": "FRA", "start_months": 3, "rate": .0385}, {"type": "FRA", "start_months": 6, "rate": .0375}, {"type": "FRA", "start_months": 9, "rate": .037},
            {"type": "SWAP", "months": 24, "rate": .0355}, {"type": "SWAP", "months": 36, "rate": .035}, {"type": "SWAP", "months": 60, "rate": .0355}, {"type": "SWAP", "months": 120, "rate": .038}]


def bootstrap_proj(disc, as_of, quotes, ip):
    cal = TERM["calendar"]
    spot = add_bd(cal, as_of, TERM["spot_lag"])
    pil, rep = [], []
    for q in quotes:
        if q["type"] == "SWAP":
            m = q["months"]
            pil.append(term_periods(as_of, m, 12)[1][-1])
            rep.append(lambda c, m=m, r=q["rate"]: (lambda af: af[1] / af[0] - r)(swap_legs(disc, c, as_of, m)))
        else:
            s0 = spot if q["type"] == "DEPOSIT" else adjust(cal, add_months(spot, q["start_months"]))
            e = adjust(cal, add_months(s0, 3))
            pil.append(e)
            rep.append(lambda c, a=s0, b=e, r=q["rate"]: (c.df(a) / c.df(b) - 1) / float(yf("ACT_360", a, b)) - r)
    c, dfs = bootstrap(as_of, pil, rep, ip)
    return c, dfs, pil


def ql_term():
    return ql.IborIndex("TERM", ql.Period(3, ql.Months), 2, ql.USDCurrency(), ql.UnitedStates(ql.UnitedStates.GovernmentBond), ql.ModifiedFollowing, False, ql.Actual360())


def projection():
    s = S("projection", "02-curves/projection-and-fra.md")
    ql.Settings.instance().evaluationDate = Q(AS_OF)
    cv, dfs, per = bootstrap_ois("SOFR", AS_OF, SOFR_Q)
    pil = [p[-1][2] for p in per]
    jc = jcurve(cv, pil, dfs)
    qd = ql_ois("SOFR", AS_OF, SOFR_Q, "LOG_LINEAR_DF")
    dh = ql.YieldTermStructureHandle(qd)
    idx = ql_term()
    hs = []
    for q in proj_quotes():
        qq = ql.QuoteHandle(ql.SimpleQuote(q["rate"]))
        if q["type"] == "DEPOSIT":
            hs.append(ql.DepositRateHelper(qq, idx))
        elif q["type"] == "FRA":
            hs.append(ql.FraRateHelper(qq, q["start_months"], idx))
        else:
            hs.append(ql.SwapRateHelper(qq, ql.Period(q["months"], ql.Months), idx.fixingCalendar(), ql.Annual, ql.ModifiedFollowing, ql.Thirty360(ql.Thirty360.BondBasis), idx, ql.QuoteHandle(), ql.Period(0, ql.Days), dh))
    qp = ql.PiecewiseLogLinearDiscount(Q(AS_OF), hs, ql.Actual365Fixed())
    qp.enableExtrapolation()
    pc, pd, pp = bootstrap_proj(cv, AS_OF, proj_quotes(), "LOG_LINEAR_DF")
    err = max(abs(qp.discount(Q(d)) - v) for d, v in zip(pp, pd))
    note(f"projection: replay against QuantLib, max pillar difference {err:.2e}")
    assert err < 1e-10
    s.add("rates.projection.bootstrap", {"discount": jc, "index": "USD-TERM-3M", "as_of": str(AS_OF), "quotes": proj_quotes(), "interpolation": "LOG_LINEAR_DF"},
          {"pillars": [{"date": str(d), "discount_factor": v} for d, v in zip(pp, pd)]}, cls=I, verified=["independent-replay", "quantlib-1.44"], tags=[SYN], limit=DFLIM)
    jp = jcurve(pc, pp, pd)
    N = 1e6
    spot = add_bd("USGS", AS_OF, 2)
    for sm, k, side in ((3, .0385, "PAY"), (6, .036, "RECEIVE")):
        a = adjust("USGS", add_months(spot, sm))
        e = adjust("USGS", add_months(a, 3))
        al = float(yf("ACT_360", a, e))
        F = (pc.df(a) / pc.df(e) - 1) / al
        v = (1 if side == "PAY" else -1) * N * al * (F - k) / (1 + al * F) * cv.df(a)
        s.add("rates.fra.pv", {"discount": jc, "projection": jp, "trade": {"index": "USD-TERM-3M", "start": str(a), "fixed_rate": k, "notional": N, "side": side}},
              {"valuation": {"pv": v, "currency": "USD", "model": "FRA_DISCOUNTING", "data_version": None, "conventions": "USD-TERM-3M", "as_of": str(AS_OF)}, "forward_rate": F}, cls=I, verified=["independent-replay"], tags=[SYN], limit=PVLIM)
    pj = ql.YieldTermStructureHandle(qp)
    idx2 = idx.clone(pj)
    for yrs, k, side in ((5, .036, "PAY"), (10, .037, "RECEIVE")):
        ann, flt = swap_legs(cv, pc, AS_OF, yrs * 12)
        v = (1 if side == "PAY" else -1) * N * (flt - k * ann)
        sw = ql.MakeVanillaSwap(ql.Period(yrs, ql.Years), idx2, k, ql.Period(0, ql.Days), nominal=N, fixedLegTenor=ql.Period(1, ql.Years), fixedLegDayCount=ql.Thirty360(ql.Thirty360.BondBasis),
                                swapType=ql.Swap.Payer if side == "PAY" else ql.Swap.Receiver, pricingEngine=ql.DiscountingSwapEngine(dh))
        assert abs(sw.NPV() - v) < 1e-5, (sw.NPV(), v)
        s.add("rates.swap.pv", {"discount": jc, "projection": jp, "trade": {"index": "USD-TERM-3M", "tenor_months": yrs * 12, "fixed_rate": k, "notional": N, "side": side}},
              {"valuation": {"pv": v, "currency": "USD", "model": "SWAP_DISCOUNTING", "data_version": None, "conventions": "USD-TERM-3M", "as_of": str(AS_OF)}, "par_rate": flt / ann}, cls=I, verified=["independent-replay", "quantlib-1.44"], tags=[SYN], limit=PVLIM)
    note("projection: vanilla swap PVs match QuantLib within 1e-5 on 1e6")
    _, fl = term_periods(AS_OF, 60, 3)
    ann3 = sum(float(yf("ACT_360", a, b)) * cv.df(b) for a, b in zip(fl, fl[1:]))
    tp = sum((pc.df(a) / pc.df(b) - cv.df(a) / cv.df(b)) * cv.df(b) for a, b in zip(fl, fl[1:]))
    s.add("rates.basis.spread", {"discount": jc, "projection": jp, "index": "USD-TERM-3M", "tenor_months": 60}, {"spread": tp / ann3}, cls=I, verified=["independent-replay"], tags=[SYN], limit={"absolute": 1e-9, "relative": 0.0, "reason": "curve tolerance"})
    write(s)
    return cv, jc


def fx():
    s = S("fx", "02-curves/fx.md")
    gc, gd, gp = bootstrap_ois("SONIA", AS_OF, SONIA_Q)
    uc, ud, up = bootstrap_ois("SOFR", AS_OF, SOFR_Q)
    gpil, upil = [p[-1][2] for p in gp], [p[-1][2] for p in up]
    jg, ju = jcurve(gc, gpil, gd), jcurve(uc, upil, ud)

    def joint(d):
        return is_business("GBLO", d) and is_business("USGS", d)

    def spot_date(d):
        n = 0
        while n < 2:
            d += timedelta(1)
            n += joint(d)
        return d
    jc = ql.JointCalendar(ql.UnitedKingdom(ql.UnitedKingdom.Settlement), ql.UnitedStates(ql.UnitedStates.GovernmentBond), ql.JoinHolidays)
    for d in (date(2026, 11, 6), date(2026, 12, 23), date(2027, 3, 24), date(2026, 11, 25)):
        sd = spot_date(d)
        assert jc.advance(Q(d), 2, ql.Days).ISO() == str(sd)
        s.add("fx.spot_date", {"pair": "GBPUSD", "trade_date": str(d)}, {"spot_date": str(sd)}, cls=E, verified=["quantlib-1.44"])
    sp = spot_date(AS_OF)
    S0 = 1.2800
    base = {"pair": "GBPUSD", "spot": S0, "as_of": str(AS_OF), "base_curve": jg, "quote_curve": ju}

    def fwd(d, S1=S0):
        return S1 * (gc.df(d) / gc.df(sp)) / (uc.df(d) / uc.df(sp))
    for T in (date(2027, 2, 10), date(2027, 11, 10), date(2031, 11, 10)):
        F = fwd(T)
        s.add("fx.forward.outright", {**base, "value_date": str(T)}, {"forward": F, "points": (F - S0) / 1e-4}, cls=I, verified=["hand"], tags=[SYN])
    N = 1e6
    T = date(2027, 11, 10)
    for K, side in ((1.29, "BUY"), (1.27, "SELL")):
        sg = 1 if side == "BUY" else -1
        pv = sg * N * (fwd(T) - K) * uc.df(T)
        delta = sg * N * (fwd(T) / S0) * uc.df(T)
        h = 1e-6
        num = sg * N * ((fwd(T, S0 + h) - fwd(T, S0 - h)) / (2 * h)) * uc.df(T)
        assert abs(num - delta) / abs(delta) < 1e-8
        s.add("fx.forward.pv", {**base, "trade": {"notional_base": N, "strike": K, "value_date": str(T), "side": side}},
              {"valuation": {"pv": pv, "currency": "USD", "model": "FX_FORWARD_DISCOUNTING", "data_version": None, "conventions": "GBPUSD", "as_of": str(AS_OF)}, "fx_delta": delta}, cls=I, verified=["hand"], tags=[SYN], limit=PVLIM)
    n, f = date(2027, 2, 10), date(2027, 11, 10)
    kn, kf = 1.28, 1.2775
    pv = N * (fwd(n) - kn) * uc.df(n) * -1 + N * (fwd(f) - kf) * uc.df(f)
    dl = N * (-(fwd(n) / S0) * uc.df(n) + (fwd(f) / S0) * uc.df(f))
    s.add("fx.swap.pv", {**base, "trade": {"notional_base": N, "near_date": str(n), "near_rate": kn, "far_date": str(f), "far_rate": kf, "far_side": "BUY"}},
          {"valuation": {"pv": pv, "currency": "USD", "model": "FX_SWAP_DISCOUNTING", "data_version": None, "conventions": "GBPUSD", "as_of": str(AS_OF)}, "fx_delta": dl}, cls=I, verified=["hand"], tags=[SYN], limit=PVLIM)
    pts = [("3M", -18.5), ("6M", -36.0), ("1Y", -71.0), ("2Y", -140.0)]
    out = []
    for t, p in pts:
        T = end_date("USGS", sp, t) if False else adjust("GBLO", add_months(sp, int(t[:-1]) * (12 if t[-1] == "Y" else 1)))
        while not joint(T):
            T += timedelta(1)
        F = S0 + p * 1e-4
        ratio = (F / S0) * (uc.df(T) / uc.df(sp))
        tau = (T - sp).days / 365
        zi = -math.log(ratio) / tau
        zo = -math.log(gc.df(T) / gc.df(sp)) / tau
        out.append({"value_date": str(T), "implied_ratio": ratio, "basis_bp": (zi - zo) * 1e4})
    s.add("fx.curve.implied", {**base, "points": [{"tenor": t, "points": p} for t, p in pts]}, {"nodes": out}, cls=I, verified=["hand"], tags=[SYN], limit={"absolute": 1e-7, "relative": 0.0, "reason": "basis in bp"})
    s.add("fx.spot_date", {"pair": "XXXYYY", "trade_date": "2026-11-06"}, error="E_SCHEMA", cls=E, tags=["invalid"])
    s.add("fx.forward.outright", {**base, "spot": -1.0, "value_date": "2027-02-10"}, error="E_DOMAIN", cls=E, tags=["invalid"])
    s.add("fx.forward.outright", {**base, "value_date": "2026-11-09"}, error="E_DATE_ORDER", cls=E, tags=["invalid"], description="before the spot date")
    write(s)


def dv01_replay(conv, quotes, ip, trade, as_of=AS_OF):
    p = ois_periods(conv, as_of, trade["tenor"])

    def price(rates):
        cv = bootstrap_ois(conv, as_of, [(t, r) for (t, _), r in zip(quotes, rates)], ip)[0]
        a, fl = ois_legs(conv, p, cv)
        return (1 if trade["side"] == "PAY" else -1) * trade["notional"] * (fl - trade["fixed_rate"] * a)
    r0 = [r for _, r in quotes]
    bp = 1e-4
    par = (price([r + bp for r in r0]) - price([r - bp for r in r0])) / 2
    keys = []
    for i in range(len(r0)):
        u, d = list(r0), list(r0)
        u[i] += bp
        d[i] -= bp
        keys.append((price(u) - price(d)) / 2)
    return par, keys


def risk():
    s = S("risk", "06-risk/rates-sensitivities.md")
    RL = {"absolute": 1e-3, "relative": 1e-8, "reason": "difference of two curve solves on 1e6, each good to 1e-13 in rate"}
    for conv, q, tr in (("SONIA", SONIA_Q, {"convention": "SONIA", "tenor": "5Y", "fixed_rate": .034, "notional": 1e6, "side": "PAY"}), ("SONIA", SONIA_Q, {"convention": "SONIA", "tenor": "10Y", "fixed_rate": .036, "notional": 1e6, "side": "RECEIVE"}),
                        ("SOFR", SOFR_Q, {"convention": "SOFR", "tenor": "7Y", "fixed_rate": .036, "notional": 1e6, "side": "PAY"})):
        par, keys = dv01_replay(conv, q, "LOG_LINEAR_DF", tr)
        rel = abs(sum(keys) - par) / abs(par)
        assert rel < 1e-5, rel
        s.add("risk.ois.dv01", {"as_of": str(AS_OF), "quotes": jq(q), "interpolation": "LOG_LINEAR_DF", "trade": tr}, {"dv01": par, "key_rate": keys}, cls=I, verified=["independent-replay", "identity-sum"], tags=[SYN], limit=RL)
    note("risk: key-rate sums match the parallel DV01 to under 1e-5 relative at a 1 bp bump")
    y, cf = 0.04, [(0.5, 2.0), (1.0, 2.0), (1.5, 2.0), (2.0, 102.0)]
    pv = sum(c * math.exp(-y * t) for t, c in cf)
    dur = sum(t * c * math.exp(-y * t) for t, c in cf) / pv
    cvx = sum(t * t * c * math.exp(-y * t) for t, c in cf) / pv
    s.add("risk.cashflows", {"cashflows": [{"t": t, "amount": c} for t, c in cf], "yield": y}, {"pv": pv, "duration": dur, "convexity": cvx}, verified=["hand"])
    s.add("risk.cashflows", {"cashflows": [], "yield": y}, error="E_INPUT", cls=E, tags=["invalid"])
    s.add("risk.cashflows", {"cashflows": [{"t": -1.0, "amount": 1.0}], "yield": y}, error="E_DOMAIN", cls=E, tags=["invalid"])
    write(s)


def solve_l1(A, b, w, c, lam):
    """Exact, by enumerating sign patterns of x. Convex with full column rank, so the minimiser is unique."""
    A, b, w, c = map(lambda v: np.array(v, float), (A, b, w, c))
    n = A.shape[1]
    W = np.diag(w)
    H = 2 * A.T @ W @ A
    g = 2 * A.T @ W @ b
    best = None
    for sg in itertools.product((-1, 0, 1), repeat=n):
        act = [i for i in range(n) if sg[i]]
        x = np.zeros(n)
        if act:
            rhs = -(g[act] + lam * c[act] * np.array([sg[i] for i in act]))
            x[act] = np.linalg.solve(H[np.ix_(act, act)], rhs)
            if any(x[i] * sg[i] <= 0 for i in act):
                continue
        r = A @ x + b
        o = r @ W @ r + lam * c @ np.abs(x)
        if best is None or o < best[0]:
            best = (o, x, r)
    o, x, r = best
    gr = H @ x + g  # first-order conditions
    for i in range(n):
        assert (abs(gr[i] + lam * c[i] * np.sign(x[i])) < 1e-9) if x[i] else (abs(gr[i]) <= lam * c[i] + 1e-9)
    return x, r, o


def hedge():
    s = S("hedge", "08-hedging/stage-b-hedges.md")
    op = "hedge.solve"
    A = [[1.0, 0.2, 0.0], [0.3, 1.0, 0.4], [0.0, 0.3, 1.0], [0.1, 0.1, 0.2]]
    b = [10.0, -4.0, 6.0, 1.0]
    w = [1.0, 2.0, 1.0, 0.5]
    for lam, c in ((0.0, [0.0, 0.0, 0.0]), (1.0, [0.5, 0.5, 0.5]), (8.0, [1.0, 2.0, 0.5]), (500.0, [1.0, 1.0, 1.0])):
        x, r, o = solve_l1(A, b, w, c, lam)
        s.add(op, {"a": A, "b": b, "weights": w, "costs": c, "lambda": lam}, {"x": [float(v) for v in x], "residual": [float(v) for v in r], "objective": float(o)}, cls=I, verified=["sign-enumeration", "first-order-conditions"], limit={"absolute": 1e-8, "relative": 0.0, "reason": "any solver; the minimiser is unique"})
    s.add(op, {"a": [[1.0]], "b": [5.0], "weights": [1.0], "costs": [0.0], "lambda": 0.0}, {"x": [-5.0], "residual": [0.0], "objective": 0.0}, cls=I, verified=["hand"], description="one instrument, exact hedge")
    s.add(op, {"a": [[1.0, 1.0], [1.0, 1.0]], "b": [1.0, 2.0], "weights": [1.0, 1.0], "costs": [0.0, 0.0], "lambda": 0.0}, error="E_SINGULAR", cls=E, tags=["invalid"])
    s.add(op, {"a": A, "b": b[:2], "weights": w, "costs": [0.0] * 3, "lambda": 0.0}, error="E_INPUT", cls=E, tags=["invalid"])
    s.add(op, {"a": A, "b": b, "weights": w, "costs": [-1.0] * 3, "lambda": 1.0}, error="E_DOMAIN", cls=E, tags=["invalid"])
    s.add("hedge.spread_cost", {"quantities": [100.0, -50.0], "half_spreads": [0.25, 0.5]}, {"cost": 50.0}, verified=["hand"])
    s.add("hedge.spread_cost", {"quantities": [1.0], "half_spreads": [-0.1]}, error="E_DOMAIN", cls=E, tags=["invalid"])
    write(s)


def gauss_newton(r, x, iters=200):
    """calib.fit's Gauss-Newton: full step, halved until the objective falls."""
    x = np.array(x, float)
    for _ in range(iters):
        v = r(x)
        J = jac_fd(r, x, 1e-7)
        st = np.linalg.lstsq(J, -v, rcond=None)[0]
        a = 1.0
        while (r(x + a * st) ** 2).sum() > (v ** 2).sum() and a > 1e-10:
            a /= 2
        x = x + a * st
        if np.linalg.norm(a * st) <= 1e-12 * (1 + np.linalg.norm(x)):
            break
    return x


def check_solvers(X, noise):
    """The golden minima must be reachable by the plain methods the spec names, whatever their path."""
    from scipy.optimize import minimize
    Xa = np.array(X)
    ye = 3.0 * np.exp(-0.4 * Xa)
    for y in (ye, ye + np.array(noise)):
        r = lambda q, y=y: q[0] * np.exp(-q[1] * Xa) - y  # noqa: E731
        g = gauss_newton(r, [2.0, 0.3])
        b = minimize(lambda q: (r(q) ** 2).sum(), [2.0, 0.3], method="BFGS", options={"gtol": 1e-8}).x
        best = least_squares(r, [2.0, 0.3], xtol=1e-14, ftol=1e-14, gtol=1e-14).x
        assert np.abs(g - best).max() < 1e-7 and np.abs(b - best).max() < 1e-5, (g, b, best)

    def ns(q):
        e = (1 - np.exp(-Xa / q[3])) / (Xa / q[3])
        return q[0] + q[1] * e + q[2] * (e - np.exp(-Xa / q[3]))
    y = ns([.04, -.015, .01, 1.5])
    lm = least_squares(lambda q: ns(q) - y, [.035, -.01, .005, 1.2], method="lm", xtol=1e-14, ftol=1e-14)
    bf = minimize(lambda q: ((ns(q) - y) ** 2).sum(), [.035, -.01, .005, 1.2], method="BFGS", options={"gtol": 1e-8})
    note(f"calibration: Nelson-Siegel objective LM {(lm.fun ** 2).sum():.1e}, BFGS {bf.fun:.1e}; Gauss-Newton and BFGS reach the exponential minima")
    assert (lm.fun ** 2).sum() < 1e-10 and bf.fun < 1e-10


def calib():
    s = S("calibration", "03-calibration/least-squares.md")
    op = "calib.fit"
    X = [0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 7.0, 10.0]
    noise = [.002, -.001, .0015, -.002, .001, -.0005, .0012, -.0008]
    check_solvers(X, noise)
    for meth in ("GAUSS_NEWTON", "LEVENBERG_MARQUARDT", "BFGS"):
        yl = [1.0 + 2.0 * x + e for x, e in zip(X, noise)]
        Am = np.c_[np.ones(8), X]
        p = np.linalg.lstsq(Am, yl, rcond=None)[0]
        o = float(((Am @ p - yl) ** 2).sum())
        lim = {"absolute": 1e-6, "relative": 0.0, "reason": "solver stops by its own test; judged on objective and a unique minimiser"}
        s.add(op, {"model": "LINEAR", "x": X, "y": yl, "start": [0.0, 0.0], "method": meth}, {"parameters": [float(v) for v in p], "objective": o}, cls=I, verified=["numpy"], tags=[SYN], limit=lim)
        ye = [3.0 * math.exp(-0.4 * x) for x in X]
        s.add(op, {"model": "EXPONENTIAL", "x": X, "y": ye, "start": [2.0, 0.3], "method": meth}, {"parameters": [3.0, 0.4], "objective": 0.0}, cls=I, verified=["known-truth"], tags=[SYN], limit=lim)
        yn = [v + e for v, e in zip(ye, noise)]
        r = least_squares(lambda q: q[0] * np.exp(-q[1] * np.array(X)) - yn, [2.0, 0.3], xtol=1e-14, ftol=1e-14, gtol=1e-14)
        s.add(op, {"model": "EXPONENTIAL", "x": X, "y": yn, "start": [2.0, 0.3], "method": meth}, {"parameters": [float(v) for v in r.x], "objective": float((r.fun ** 2).sum())}, cls=I, verified=["scipy-1.18.1"], tags=[SYN], limit=lim)
        tp = [.04, -.015, .01, 1.5]

        def ns(q, x):
            x = np.array(x)
            e = (1 - np.exp(-x / q[3])) / (x / q[3])
            return q[0] + q[1] * e + q[2] * (e - np.exp(-x / q[3]))
        s.add(op, {"model": "NELSON_SIEGEL", "x": X, "y": [float(v) for v in ns(tp, X)], "start": [.035, -.01, .005, 1.2], "method": meth, "report_parameters": False}, {"objective": 0.0}, cls=I, verified=["known-truth"], tags=[SYN], limit={"absolute": 1e-10, "relative": 0.0, "reason": "repricing, not parameters: Nelson-Siegel is poorly identified"}) if meth != "GAUSS_NEWTON" else None
    Am = np.c_[np.ones(8), X]
    yl = [1.0 + 2.0 * x + e for x, e in zip(X, noise)]
    for lam, prior in ((0.5, [0.0, 0.0]), (10.0, [1.0, 1.0])):
        p = np.linalg.solve(Am.T @ Am + lam * np.eye(2), Am.T @ np.array(yl) + lam * np.array(prior))
        o = float(((Am @ p - yl) ** 2).sum() + lam * ((p - prior) ** 2).sum())
        s.add(op, {"model": "LINEAR", "x": X, "y": yl, "start": [0.0, 0.0], "method": "LEVENBERG_MARQUARDT", "regularisation": lam, "prior": prior}, {"parameters": [float(v) for v in p], "objective": o}, cls=I, verified=["closed-form"], tags=[SYN], limit={"absolute": 1e-6, "relative": 0.0, "reason": "closed form; solver tolerance"})
    w = [1, 1, 1, 1, 4, 4, 4, 4.0]
    Wm = np.diag(w)
    p = np.linalg.solve(Am.T @ Wm @ Am, Am.T @ Wm @ np.array(yl))
    o = float((w * (Am @ p - yl) ** 2).sum())
    s.add(op, {"model": "LINEAR", "x": X, "y": yl, "weights": w, "start": [0.0, 0.0], "method": "GAUSS_NEWTON"}, {"parameters": [float(v) for v in p], "objective": o}, cls=I, verified=["closed-form"], tags=[SYN], limit={"absolute": 1e-6, "relative": 0.0, "reason": "closed form"})
    # A bound that binds: slope held at 1.5, intercept then the mean residual.
    b = 1.5
    a = float(np.mean(np.array(yl) - b * np.array(X)))
    o = float(((a + b * np.array(X) - yl) ** 2).sum())
    s.add(op, {"model": "LINEAR", "x": X, "y": yl, "start": [0.0, 0.0], "method": "LEVENBERG_MARQUARDT", "upper": [100.0, 1.5], "lower": [-100.0, -100.0]}, {"parameters": [a, b], "objective": o}, cls=I, verified=["closed-form"], tags=[SYN], limit={"absolute": 1e-6, "relative": 0.0, "reason": "closed form"})
    rb = {"model": "ROSENBROCK", "x": [], "y": [], "start": [-1.2, 1.0]}
    s.add(op, {**rb, "method": "BFGS"}, {"parameters": [1.0, 1.0], "objective": 0.0}, cls=I, verified=["analytic"], limit={"absolute": 1e-5, "relative": 0.0, "reason": "gradient test at 1e-8"})
    s.add(op, {"model": "LINEAR", "x": X, "y": yl[:3], "start": [0.0, 0.0], "method": "BFGS"}, error="E_INPUT", cls=E, tags=["invalid"])
    s.add(op, {"model": "LINEAR", "x": X, "y": yl, "start": [0.0], "method": "BFGS"}, error="E_INPUT", cls=E, tags=["invalid"])
    s.add(op, {"model": "LINEAR", "x": X, "y": yl, "start": [0.0, 0.0], "method": "NEWTON"}, error="E_SCHEMA", cls=E, tags=["invalid"])
    s.add(op, {"model": "LINEAR", "x": X, "y": yl, "start": [0.0, 0.0], "method": "BFGS", "regularisation": -1.0}, error="E_DOMAIN", cls=E, tags=["invalid"])
    s.add(op, {"model": "LINEAR", "x": [1.0, 1.0, 1.0], "y": [1.0, 2.0, 3.0], "start": [0.0, 0.0], "method": "GAUSS_NEWTON"}, error="E_SINGULAR", cls=E, tags=["invalid"])
    s.add(op, {"model": "EXPONENTIAL", "x": X, "y": [3.0 * math.exp(-0.4 * x) for x in X], "start": [2.0, 0.3], "method": "LEVENBERG_MARQUARDT", "max_iter": 1}, error="E_NO_CONVERGENCE", cls=E, tags=["invalid"])
    ba = "calib.check_bid_ask"
    s.add(ba, {"fitted": [1.0, 2.0, 3.0], "bid": [0.9, 2.1, 3.0], "ask": [1.1, 2.2, 3.1]}, {"breaches": [{"index": 1, "side": "BID", "distance": 2.1 - 2.0}]}, cls=I, verified=["hand"])
    s.add(ba, {"fitted": [1.0], "bid": [2.0], "ask": [1.0]}, error="E_INPUT", cls=E, tags=["invalid"])
    rp = "calib.curve_report"
    q = SONIA_Q[:8]

    def zs(r):
        cv, dfs, per = bootstrap_ois("SONIA", AS_OF, [(t, v) for (t, _), v in zip(q, r)])
        return [-math.log(v) / t for v, t in zip(dfs, cv.t[1:])]
    J = jac_fd(zs, [r for _, r in q], 1e-5)
    s.add(rp, {"convention": "SONIA", "as_of": str(AS_OF), "quotes": jq(q), "interpolation": "LOG_LINEAR_DF"}, {"jacobian": [[float(v) for v in row] for row in J], "condition_number": float(np.linalg.cond(J))}, cls=I,
          verified=["central-bump"], tags=[SYN], limit={"absolute": 1e-5, "relative": 1e-4, "reason": "analytic or bumped Jacobians both pass; bump error is about 1e-7"})
    write(s)


def ql_fx_forward(base, quote, S0, N, K, T, side):
    """QuantLib FxForward on the same curves, as (pv in quote currency, delta by central bump)."""
    ql.Settings.instance().evaluationDate = Q(AS_OF)
    bc = ql.YieldTermStructureHandle(base)
    qc = ql.YieldTermStructureHandle(quote)
    cal = ql.JointCalendar(ql.UnitedKingdom(ql.UnitedKingdom.Settlement), ql.UnitedStates(ql.UnitedStates.GovernmentBond), ql.JoinHolidays)
    fwd = ql.FxForward(N, ql.GBPCurrency(), ql.USDCurrency(), K, Q(T), side != "BUY", 2, cal)
    sq = ql.SimpleQuote(S0)
    fwd.setPricingEngine(ql.DiscountingFxForwardEngine(bc, qc, ql.QuoteHandle(sq)))
    pv = fwd.npvTargetCurrency()
    h = 1e-6
    sq.setValue(S0 + h)
    up = fwd.npvTargetCurrency()
    sq.setValue(S0 - h)
    dn = fwd.npvTargetCurrency()
    return pv, (up - dn) / (2 * h)


def ql_curve(c):
    q = ql.DiscountCurve([Q(c.as_of + timedelta(round(t * 365))) for t in c.t], c.d, ql.Actual365Fixed())
    q.enableExtrapolation()
    return q


def usecases():
    s = S("usecases", "04-pricing/use-cases.md")
    # Use case 1: FX, spot to hedge.
    gc, gd, gp = bootstrap_ois("SONIA", AS_OF, SONIA_Q)
    uc, ud, up = bootstrap_ois("SOFR", AS_OF, SOFR_Q)
    jg, ju = jcurve(gc, [p[-1][2] for p in gp], gd), jcurve(uc, [p[-1][2] for p in up], ud)
    sp, S0 = date(2026, 11, 10), 1.28
    book = [{"notional_base": 5e6, "strike": 1.27, "value_date": "2027-02-10", "side": "BUY"}, {"notional_base": 3e6, "strike": 1.285, "value_date": "2027-11-10", "side": "SELL"}]
    pv = dl = qpv = qdl = 0.0
    for t in book:
        T = date.fromisoformat(t["value_date"])
        sg = 1 if t["side"] == "BUY" else -1
        F = S0 * (gc.df(T) / gc.df(sp)) / (uc.df(T) / uc.df(sp))
        pv += sg * t["notional_base"] * (F - t["strike"]) * uc.df(T)
        dl += sg * t["notional_base"] * (F / S0) * uc.df(T)
        qpv += ql_fx_forward(ql_curve(gc), ql_curve(uc), S0, t["notional_base"], t["strike"], T, t["side"])[0]
        qdl += ql_fx_forward(ql_curve(gc), ql_curve(uc), S0, t["notional_base"], t["strike"], T, t["side"])[1]
    note(f"use case 1: book PV {pv:.4f} and delta {dl:.4f}, QuantLib FxForward gap {abs(pv - qpv):.2e} and {abs(dl - qdl):.2e}")
    assert abs(pv - qpv) < 1e-6 and abs(dl - qdl) < 1e-2
    hs = 0.00005
    hedge_n = -dl
    s.add("usecase.fx_hedge", {"pair": "GBPUSD", "spot": S0, "as_of": str(AS_OF), "base_curve": jg, "quote_curve": ju, "book": book, "half_spread": hs},
          {"pv": pv, "fx_delta": dl, "hedge_spot_base": hedge_n, "residual_delta": 0.0, "hedge_cost": abs(hedge_n) * hs}, cls=I, verified=["hand", "quantlib-1.44"], tags=[SYN], limit=PVLIM)
    # Use case 2: SONIA, curve to key-rate hedge.
    q = SONIA_Q
    trade = {"convention": "SONIA", "tenor": "6Y", "fixed_rate": .034, "notional": 1e7, "side": "PAY"}
    cv = bootstrap_ois("SONIA", AS_OF, q)[0]
    p = ois_periods("SONIA", AS_OF, "6Y")
    a, fl = ois_legs("SONIA", p, cv)
    pv = 1e7 * (fl - .034 * a)
    par, keys = dv01_replay("SONIA", q, "LOG_LINEAR_DF", trade)
    hedges = ["5Y", "7Y"]
    cols = []
    for h in hedges:
        pr = ois_par("SONIA", ois_periods("SONIA", AS_OF, h), cv)
        cols.append(dv01_replay("SONIA", q, "LOG_LINEAR_DF", {"tenor": h, "fixed_rate": pr, "notional": 1e6, "side": "PAY"})[1])
    Am = np.array(cols).T
    b = np.array(keys)
    x = np.linalg.solve(Am.T @ Am, -Am.T @ b)
    res = Am @ x + b
    cost = float(sum(abs(v) * abs(sum(cc)) * 0.25 for v, cc in zip(x, cols)))
    assert np.linalg.norm(res) < 0.2 * np.linalg.norm(b)
    s.add("usecase.rates_hedge", {"as_of": str(AS_OF), "quotes": jq(q), "interpolation": "LOG_LINEAR_DF", "trade": trade, "hedge_tenors": hedges, "hedge_unit_notional": 1e6, "half_spread_bp": 0.25},
          {"pv": pv, "dv01": par, "key_rate": keys, "hedge_units": [float(v) for v in x], "residual_key_rate": [float(v) for v in res], "hedge_cost": cost}, cls=I, verified=["independent-replay"], tags=[SYN],
          limit={"absolute": 1e-2, "relative": 1e-6, "reason": "bumped solves on 1e7 notional"})
    note(f"use case 2: DV01 {par:.2f} on 1e7, residual key-rate norm {float(np.linalg.norm(res)):.2f} against {float(np.linalg.norm(b)):.2f} unhedged")
    write(s)


def main():
    units()
    schedules()
    curves()
    ois()
    projection()
    fx()
    risk()
    hedge()
    calib()
    usecases()
    assert last_bd and ois_par


if __name__ == "__main__":
    main()
