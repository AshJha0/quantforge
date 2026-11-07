"""Stage D golden cases, wave 2, D3: cross-currency basis and NDF. Same rules as gen_stage_d.py."""
import math
from datetime import date, timedelta

import QuantLib as ql
from scipy.optimize import brentq

from qf_oracle.common import note
from qf_oracle.dates import is_business
from qf_oracle.rates import Curve, add_months
import gen_stage_d as D
from gen_stage_d import E, I, QLV, Q, S, caught, write

AS_OF = D.AS_OF


def joint_bd(d):
    return is_business("USGS", d) and is_business("EUTA", d)


def joint_adjust(d):
    r = d
    while not joint_bd(r):
        r += timedelta(1)
    if r.month == d.month:
        return r
    r = d
    while not joint_bd(r):
        r -= timedelta(1)
    return r


def xccy_dates(start, months):
    return [start] + [joint_adjust(add_months(start, 3 * k)) for k in range(1, months // 3 + 1)]


def float_leg(ds, proj, disc, spread, N, exchange=True):
    v = sum(N * ((proj.df(a) / proj.df(e) - 1) + spread * (e - a).days / 360) * disc.df(e) for a, e in zip(ds, ds[1:]))
    if exchange:
        v += N * (disc.df(ds[-1]) - disc.df(ds[0]))
    return v


def xccy_pv(dd, df_, pf, S0, start, months, Nf, spread, side):
    ds = xccy_dates(start, months)
    lf = float_leg(ds, pf, df_, spread, Nf)
    ld = float_leg(ds, dd, dd, 0.0, Nf * S0)
    sg = 1 if side == "RECEIVE_FOREIGN" else -1
    return sg * (S0 * lf - ld), lf, ld


def qcurve(ds, vs):
    c = ql.DiscountCurve([Q(AS_OF)] + [Q(d) for d in ds], [1.0] + list(vs), ql.Actual365Fixed())
    c.enableExtrapolation()
    return c


def ql_leg_npv(ds, proj_curve, disc_curve, conv, N, spread):
    ix = D.qindex(conv, ql.YieldTermStructureHandle(proj_curve))
    leg = ql.OvernightLeg([N], ql.Schedule([Q(d) for d in ds]), ix, ql.Actual360(), ql.Unadjusted, [1.0], [spread], True, ql.RateAveraging.Compound)
    return ql.CashFlows.npv(leg, ql.YieldTermStructureHandle(disc_curve), False, Q(AS_OF), Q(AS_OF))


def pillars(ds, vs):
    return [{"date": str(d), "discount_factor": v} for d, v in zip(ds, vs)]


def xccy_d():
    s = S("xccy_d", "02-curves/cross-currency.md")
    usd, ud, up = D.bootstrap_ois_j("SOFR", AS_OF, D.B.SOFR_Q)
    eur, ed, ep = D.bootstrap_ois_j("ESTR", AS_OF, D.ESTR_Q)
    upil, epil = [p[-1][2] for p in up], [p[-1][2] for p in ep]
    ju, je = D.jcurve(usd, upil, ud), D.jcurve(eur, epil, ed)
    S0, start = 1.0850, joint_adjust(date(2026, 11, 10))
    mats = [12, 24, 36, 60, 84, 120]
    xd = [xccy_dates(start, m)[-1] for m in mats]
    bt = [-.0010, -.0014, -.0017, -.0021, -.0023, -.0025]
    truth = Curve(AS_OF, xd, [eur.df(d) * math.exp(b * (d - AS_OF).days / 365) for d, b in zip(xd, bt)])
    tdf = [truth.df(d) for d in xd]
    # The USD leg (SOFR flat, projected and discounted on one curve, with exchanges) is worth 0, so par makes the EUR leg 0.
    quotes = []
    for m in mats:
        ds = xccy_dates(start, m)
        assert abs(float_leg(ds, usd, usd, 0.0, 1.0)) < 1e-15
        ann = sum((e - a).days / 360 * truth.df(e) for a, e in zip(ds, ds[1:]))
        q = -float_leg(ds, eur, truth, 0.0, 1.0) / ann
        assert abs(float_leg(ds, eur, truth, q, 1.0)) < 1e-15
        quotes.append((q, m))
    got = []
    for j, (q, m) in enumerate(quotes):
        ds = xccy_dates(start, m)

        def err(ln):
            return float_leg(ds, eur, Curve(AS_OF, xd[:j + 1], got + [math.exp(ln)]), q, 1.0)
        p0 = math.log(got[-1]) if got else 0.0
        got.append(math.exp(brentq(err, p0 - 1, p0 + 1, xtol=1e-16, rtol=1e-15, maxiter=500)))
    assert max(abs(a - b) for a, b in zip(got, tdf)) < 1e-13
    jq = [{"months": m, "spread": q} for q, m in quotes]
    base = {"domestic": ju, "foreign_projection": je, "domestic_convention": "SOFR", "foreign_convention": "ESTR", "start": str(start), "quotes": jq, "interpolation": "LOG_LINEAR_DF"}
    s.add("fx.xccy.bootstrap", base, {"pillars": pillars(xd, tdf)}, cls=I, verified=["known-truth", "independent-replay"], tags=["xccy"], limit=D.DFLIM)
    caught("xccy_d", "basis ignored: foreign discount = foreign OIS", max(abs(eur.df(d) - v) for d, v in zip(xd, tdf)), 1e-9)
    jt = D.jcurve(truth, xd, tdf)
    qe, qt = qcurve(epil, ed), qcurve(xd, tdf)
    for m, sp, side, Nf in ((24, -.0012, "RECEIVE_FOREIGN", 1e7), (60, -.0030, "PAY_FOREIGN", 5e7), (120, -.0020, "RECEIVE_FOREIGN", 2.5e7)):
        pv, lf, ld = xccy_pv(usd, truth, eur, S0, start, m, Nf, sp, side)
        ds = xccy_dates(start, m)
        qlf = ql_leg_npv(ds, qe, qt, "ESTR", Nf, sp) + Nf * (truth.df(ds[-1]) - truth.df(ds[0]))
        assert abs(qlf - lf) < 1e-6, (qlf, lf)
        s.add("fx.xccy.pv", {"domestic": ju, "foreign_projection": je, "foreign_discount": jt, "spot": S0, "trade": {"start": str(start), "months": m, "foreign_notional": Nf, "spread": sp, "side": side}},
              {"pv": pv, "foreign_leg": lf, "domestic_leg": ld}, cls=I, verified=["independent-replay", QLV], tags=["xccy"],
              limit={"absolute": 1e-9 * Nf, "relative": 1e-9, "reason": "curve tolerance on notional"})
        caught("xccy_d", f"no notional exchange, {m}M", abs(S0 * Nf * (truth.df(ds[-1]) - truth.df(ds[0]))), 1e-9 * Nf)
        caught("xccy_d", f"foreign leg discounted on foreign OIS, {m}M", abs(S0 * (float_leg(ds, eur, eur, sp, Nf) - lf)), 1e-9 * Nf)
    note("xccy_d: bootstrap recovers the basis-adjusted curve within 1e-13; foreign legs match QuantLib OvernightLeg NPVs within 1e-6 on 1e7")
    s.add("fx.xccy.bootstrap", {**base, "quotes": jq[::-1]}, error="E_INPUT", cls=E, tags=["invalid"], description="months strictly increasing")
    s.add("fx.xccy.bootstrap", {**base, "quotes": [{"months": 10, "spread": -.001}]}, error="E_INPUT", cls=E, tags=["invalid"], description="months a multiple of 3")
    s.add("fx.xccy.bootstrap", {**base, "start": "2026-11-11"}, error="E_INPUT", cls=E, tags=["invalid", "ruling"], description="start not a joint business day (USGS Veterans Day)")
    # NDF.
    nop = "fx.ndf.pv"
    ccy = Curve(AS_OF, xd, [usd.df(d) * math.exp(-.0310 * (d - AS_OF).days / 365) for d in xd])
    jc_ = D.jcurve(ccy, xd, [ccy.df(d) for d in xd])
    Sx = 88.45
    for fixd, pay, K, N, side, fixing in ((date(2027, 5, 6), date(2027, 5, 10), 90.10, 1e7, "BUY", None), (date(2027, 11, 8), date(2027, 11, 10), 91.00, 5e6, "SELL", None),
                                          (date(2026, 11, 5), date(2026, 11, 9), 88.00, 1e7, "BUY", 88.62)):
        F = fixing if fixing is not None else Sx * usd.df(pay) / ccy.df(pay)
        sg = 1 if side == "BUY" else -1
        pv = sg * N * (1 - K / F) * usd.df(pay)
        s.add(nop, {"usd_curve": ju, "offshore_curve": jc_, "spot": Sx, "trade": {"fixing_date": str(fixd), "payment_date": str(pay), "strike": K, "usd_notional": N, "side": side}, "fixing": fixing},
              {"pv": pv, "forward": F}, cls=I, verified=["analytic"], tags=["ndf"])
        caught("xccy_d", f"NDF as N (F - K), not divided by F, {fixd}", abs(sg * N * (F - K) * usd.df(pay) - pv), 1e-9 * N)
        if fixing is None:
            Fi = Sx * ccy.df(pay) / usd.df(pay)
            caught("xccy_d", f"NDF forward ratio inverted, {fixd}", abs(sg * N * (1 - K / Fi) * usd.df(pay) - pv), 1e-9 * N)
    nb = {"usd_curve": ju, "offshore_curve": jc_, "spot": Sx, "trade": {"fixing_date": "2026-11-05", "payment_date": "2026-11-09", "strike": 88.0, "usd_notional": 1e7, "side": "BUY"}, "fixing": None}
    s.add(nop, nb, error="E_INPUT", cls=E, tags=["invalid", "ruling"], description="fixing date on or before as_of needs a fixing")
    s.add(nop, {**nb, "trade": {**nb["trade"], "fixing_date": "2027-05-10", "payment_date": "2027-05-06"}}, error="E_DATE_ORDER", cls=E, tags=["invalid"])
    s.add(nop, {**nb, "fixing": -1.0}, error="E_DOMAIN", cls=E, tags=["invalid"])
    write(s)


def main():
    D.estr()
    D.MUTANTS.clear()
    xccy_d()
    note(f"stage D D3: {len(D.MUTANTS)} wrong-convention checks, each caught")


if __name__ == "__main__":
    main()
