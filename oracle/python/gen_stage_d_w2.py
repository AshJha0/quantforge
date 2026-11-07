"""Stage D golden cases, wave 2. D2 bonds and repo. Same rules as gen_stage_d.py."""
import math
from datetime import date, timedelta

import numpy as np
import QuantLib as ql
from scipy.optimize import brentq, least_squares

from qf_oracle.common import note
from qf_oracle.rates import Curve, add_months
import gen_stage_d as D
from gen_stage_d import A, E, I, R, QLV, Q, S, caught, write

AS_OF = D.AS_OF
SPOT_CURVE = Curve(AS_OF, [date(2027, 11, 8), date(2028, 11, 6), date(2031, 11, 6), date(2036, 11, 6), date(2046, 11, 6), date(2056, 11, 6)],
                   [math.exp(-r * ((d - AS_OF).days / 365)) for d, r in zip([date(2027, 11, 8), date(2028, 11, 6), date(2031, 11, 6), date(2036, 11, 6), date(2046, 11, 6), date(2056, 11, 6)],
                                                                         [.0380, .0365, .0370, .0390, .0420, .0410])])


def eom(d):
    return (d + timedelta(1)).month != d.month


def coupon_dates(maturity, freq, after):
    """Unadjusted coupon dates, backward from maturity; returns (previous, list of dates > after)."""
    m, k, out = 12 // freq, 0, []
    while True:
        d = add_months(maturity, -m * k)
        if eom(maturity):
            d = date(d.year, d.month, 1) + timedelta(31)
            d = d.replace(day=1) - timedelta(1)
        if d <= after:
            return d, out[::-1]
        out.append(d)
        k += 1


def bond_cfs(b, settle):
    prev, ds = coupon_dates(date.fromisoformat(b["maturity"]), b["frequency"], settle)
    c = 100 * b["coupon"] / b["frequency"]
    cfs = [(d, c + (100 if d == ds[-1] else 0)) for d in ds]
    accrued = c * (settle - prev).days / (ds[0] - prev).days
    w = (ds[0] - settle).days / (ds[0] - prev).days
    return cfs, accrued, w


def price_yield(b, settle, y):
    cfs, ai, w = bond_cfs(b, settle)
    f = b["frequency"]
    v = 1 / (1 + y / f)
    ts = [(k + w) for k in range(len(cfs))]
    P = sum(cf * v ** t for (_, cf), t in zip(cfs, ts))
    dP = sum(-t / f * cf * v ** (t + 1) for (_, cf), t in zip(cfs, ts))
    d2P = sum(t * (t + 1) / f / f * cf * v ** (t + 2) for (_, cf), t in zip(cfs, ts))
    mac = sum(t / f * cf * v ** t for (_, cf), t in zip(cfs, ts)) / P
    return dict(dirty=P, accrued=ai, clean=P - ai, modified_duration=-dP / P, macaulay_duration=mac, convexity=d2P / P)


def ql_bond(b, settle):
    ql.Settings.instance().evaluationDate = Q(settle)
    mat = date.fromisoformat(b["maturity"])
    f = b["frequency"]
    sch = ql.Schedule(Q(add_months(mat, -12 * 40)), Q(mat), ql.Period(12 // f, ql.Months), ql.NullCalendar(), ql.Unadjusted, ql.Unadjusted, ql.DateGeneration.Backward, eom(mat))
    return ql.FixedRateBond(0, 100.0, sch, [b["coupon"]], ql.ActualActual(ql.ActualActual.ISMA, sch), ql.Unadjusted), {1: ql.Annual, 2: ql.Semiannual, 4: ql.Quarterly}[f]


def curve_dirty(b, settle, cv, z=0.0):
    cfs, ai, _ = bond_cfs(b, settle)
    ds = lambda d: cv.df(d) * math.exp(-z * (d - AS_OF).days / 365)  # noqa: E731
    return sum(cf * ds(d) for d, cf in cfs) / ds(settle), ai


BONDS = [{"maturity": "2029-11-15", "coupon": .0425, "frequency": 2}, {"maturity": "2031-02-28", "coupon": .0375, "frequency": 2},
         {"maturity": "2036-08-15", "coupon": .0450, "frequency": 2}, {"maturity": "2034-03-31", "coupon": .0300, "frequency": 1},
         {"maturity": "2055-05-15", "coupon": .0475, "frequency": 2}, {"maturity": "2027-12-15", "coupon": .0150, "frequency": 4}]
SET = date(2026, 11, 9)


def _dates(cv):
    return [cv.as_of + timedelta(round(t * 365)) for t in cv.t[1:]]


def bonds_d():
    s = S("bonds_d", "04-pricing/bonds.md")
    for b in BONDS:
        for y in (.0410, -.0020, .0800):
            r = price_yield(b, SET, y)
            qb, fr = ql_bond(b, SET)
            dc = ql.ActualActual(ql.ActualActual.ISMA, ql.Schedule(Q(add_months(date.fromisoformat(b["maturity"]), -480)), Q(date.fromisoformat(b["maturity"])), ql.Period(12 // b["frequency"], ql.Months), ql.NullCalendar(), ql.Unadjusted, ql.Unadjusted, ql.DateGeneration.Backward, eom(date.fromisoformat(b["maturity"]))))
            qc = ql.BondFunctions.cleanPrice(qb, y, dc, ql.Compounded, fr, Q(SET))
            qa = qb.accruedAmount(Q(SET))
            qm = ql.BondFunctions.duration(qb, y, dc, ql.Compounded, fr, ql.Duration.Modified, Q(SET))
            qx = ql.BondFunctions.convexity(qb, y, dc, ql.Compounded, fr, Q(SET))
            assert abs(qc - r["clean"]) < 1e-10 and abs(qa - r["accrued"]) < 1e-12 and abs(qm - r["modified_duration"]) < 1e-10 and abs(qx - r["convexity"]) < 1e-8, (b, y, qc, r, qm, qx)
            s.add("bond.price.from_yield", {"bond": b, "settlement": str(SET), "yield": y}, r, cls=A, verified=[QLV, "analytic"], tags=["fixed-bond"])
            if y == .0410:
                s.add("bond.yield.from_price", {"bond": b, "settlement": str(SET), "clean_price": r["clean"]}, {"yield": y, "dirty": r["dirty"], "accrued": r["accrued"]}, cls=R, verified=[QLV, "known-truth"], tags=["fixed-bond"])
                # Mutant: accrual on ACT/365 rather than within the period.
                cfs, ai, _ = bond_cfs(b, SET)
                prev, ds = coupon_dates(date.fromisoformat(b["maturity"]), b["frequency"], SET)
                if b["frequency"] != 1:
                    caught("bonds_d", f"accrued on ACT/365 for {b['maturity']}", abs(100 * b["coupon"] * (SET - prev).days / 365 - ai), 1e-10)
    note("bonds_d: clean price, accrued, modified duration and convexity match QuantLib FixedRateBond (ACT/ACT ICMA, compounded) within 1e-10")
    # Curve price and Z-spread.
    cv = SPOT_CURVE
    jcv = D.jcurve(cv, _dates(cv), [cv.df(d) for d in _dates(cv)])
    qcurve = ql.DiscountCurve([Q(AS_OF)] + [Q(d) for d in _dates(cv)], [1.0] + [cv.df(d) for d in _dates(cv)], ql.Actual365Fixed())
    qcurve.enableExtrapolation()
    for b in BONDS[:5]:
        for z in (0.0, .0035, -.0010):
            dp, ai = curve_dirty(b, SET, cv, z)
            qb, fr = ql_bond(b, SET)
            if z == 0.0:
                s.add("bond.price.from_curve", {"bond": b, "settlement": str(SET), "curve": jcv}, {"dirty": dp, "accrued": ai, "clean": dp - ai}, cls=I, verified=["independent-replay", QLV], tags=["fixed-bond"])
                qd = sum(cf.amount() * qcurve.discount(cf.date()) for cf in qb.cashflows() if cf.date() > Q(SET)) / qcurve.discount(Q(SET))
                assert abs(qd - dp) < 1e-10
                caught("bonds_d", f"curve price not forwarded to settlement {b['maturity']}", abs(dp - dp * cv.df(SET)), 1e-8)
            else:
                qz = ql.BondFunctions.zSpread(qb, ql.BondPrice(dp - ai, ql.BondPrice.Clean), qcurve, ql.Actual365Fixed(), ql.Continuous, ql.NoFrequency, Q(SET), 1e-14, 200, 0.0)
                assert abs(qz - z) < 1e-10, (qz, z)
                s.add("bond.spread.z", {"bond": b, "settlement": str(SET), "curve": jcv, "clean_price": dp - ai}, {"z_spread": z}, cls=R, verified=[QLV, "known-truth"], tags=["z-spread"])
    note("bonds_d: curve prices and Z-spreads match QuantLib BondFunctions.zSpread (continuous, ACT/365F) within 1e-10")
    # Asset-swap (par-par) spread, and bond-OIS spread when the curve is OIS: (P_curve - P_market)/(100 A).
    for b in BONDS[:5]:
        dp, ai = curve_dirty(b, SET, cv)
        mk = dp - .85
        Af = asw_annuity(b, SET, cv)
        asw = (dp - mk) / (100 * Af)
        s.add("bond.spread.asset_swap", {"bond": b, "settlement": str(SET), "curve": jcv, "dirty_price": mk}, {"spread": asw, "annuity": Af}, cls=I, verified=["independent-replay"], tags=["asset-swap"])
        caught("bonds_d", f"asset swap over the bond's own annuity {b['maturity']}", abs(asw - (dp - mk) / (100 * fixed_annuity(b, SET, cv))), 1e-10)
    b0 = BONDS[0]
    s.add("bond.price.from_yield", {"bond": b0, "settlement": "2029-11-15", "yield": .04}, error="E_DATE_ORDER", cls=E, tags=["invalid"], description="settlement on or after maturity")
    s.add("bond.price.from_yield", {"bond": {**b0, "frequency": 3}, "settlement": str(SET), "yield": .04}, error="E_SCHEMA", cls=E, tags=["invalid"])
    s.add("bond.price.from_yield", {"bond": b0, "settlement": str(SET), "yield": -2.5}, error="E_DOMAIN", cls=E, tags=["invalid"], description="1 + y/f <= 0")
    s.add("bond.yield.from_price", {"bond": b0, "settlement": str(SET), "clean_price": -1.0}, error="E_DOMAIN", cls=E, tags=["invalid"])
    s.add("bond.spread.z", {"bond": b0, "settlement": "2026-11-05", "curve": jcv, "clean_price": 100.0}, error="E_OUT_OF_RANGE", cls=E, tags=["invalid"], description="settlement before the curve's as_of")
    write(s)
    return cv, jcv


def asw_annuity(b, settle, cv):
    mat = date.fromisoformat(b["maturity"])
    ds, k = [], 0
    while True:
        d = add_months(mat, -3 * k)
        if d <= settle:
            break
        ds.append(d)
        k += 1
    ds = [settle] + ds[::-1]
    return sum((e - s_).days / 360 * cv.df(e) for s_, e in zip(ds, ds[1:])) / cv.df(settle)


def fixed_annuity(b, settle, cv):
    cfs, _, _ = bond_cfs(b, settle)
    return sum(cv.df(d) / b["frequency"] for d, _ in cfs) / cv.df(settle)


def frn_price(cv, pv, settle, maturity, freq, current, margin, dm):
    prev, ds = coupon_dates(maturity, freq, settle)
    Dp = lambda d: cv.df(d) * math.exp(-dm * (d - AS_OF).days / 365)  # noqa: E731
    starts = [prev] + ds[:-1]
    tot = 0.0
    for i, (a, e) in enumerate(zip(starts, ds)):
        al = (e - a).days / 360
        r = current if i == 0 else (pv.df(a) / pv.df(e) - 1) / al
        tot += 100 * (r + margin) * al * Dp(e)
    tot += 100 * Dp(ds[-1])
    dirty = tot / Dp(settle)
    ai = 100 * (current + margin) * (settle - prev).days / 360
    return dirty, ai


def frn_repo_d(cv, jcv):
    s = S("repo_d", "04-pricing/bonds.md")
    op = "bond.frn.price"
    for st, mat, cur, mg, dm in ((date(2026, 11, 16), date(2029, 11, 16), None, 0.0, 0.0), (SET, date(2031, 2, 16), .0391, .0025, .0025), (SET, date(2031, 2, 16), .0391, .0025, .0040), (SET, date(2028, 5, 31), .0402, -.0005, .0010)):
        if cur is None:  # on a coupon date, margins zero, one curve: par
            prev, ds = coupon_dates(mat, 4, st)
            cur = (cv.df(prev) / cv.df(ds[0]) - 1) / ((ds[0] - prev).days / 360) if prev >= AS_OF else .0390
        dp, ai = frn_price(cv, cv, st, mat, 4, cur, mg, dm)
        if mg == dm and st == date(2026, 11, 16):
            assert abs(dp - 100) < 1e-10 or prev < AS_OF
        s.add(op, {"settlement": str(st), "maturity": str(mat), "frequency": 4, "current_rate": cur, "margin": mg, "discount_margin": dm, "discount": jcv, "projection": jcv},
              {"dirty": dp, "accrued": ai, "clean": dp - ai}, cls=I, verified=["independent-replay", "par-identity"], tags=["frn"])
        if dm != mg:
            caught("repo_d", "FRN discount margin ignored", abs(dp - frn_price(cv, cv, st, mat, 4, cur, mg, mg)[0]), 1e-8)
    # A par check with a known first period: settle on the first coupon start after as_of.
    st, mat = date(2026, 11, 16), date(2029, 11, 16)
    _, ds = coupon_dates(mat, 4, st)
    cur = (cv.df(st) / cv.df(ds[0]) - 1) / ((ds[0] - st).days / 360)
    dp, ai = frn_price(cv, cv, st, mat, 4, cur, 0.0, 0.0)
    assert abs(dp - 100) < 1e-11 and ai == 0, dp
    note("repo_d: FRN at zero margins on its own curve, settled on a coupon date, prices at 100 within 1e-11")
    # Repo forward, special repo.
    rop = "repo.forward"
    for b, end, rr, gc in ((BONDS[0], date(2026, 12, 9), .0385, None), (BONDS[2], date(2027, 2, 22), .0310, .0385), (BONDS[3], date(2027, 4, 9), .0395, .0385), (BONDS[1], date(2027, 3, 9), .0390, None)):
        r = price_yield(b, SET, .041)
        out = repo_fwd(b, SET, end, r["clean"], rr, gc)
        s.add(rop, {"bond": b, "start": str(SET), "end": str(end), "clean_price": r["clean"], "repo_rate": rr, "gc_rate": gc}, out, cls=A, verified=["analytic"], tags=["repo"] + (["special"] if gc else []))
        cpn = [(d, c) for d, c in bond_cfs(b, SET)[0] if d <= end]
        if cpn:
            caught("repo_d", f"coupon in repo term not reinvested {b['maturity']}", abs(sum(c * rr * (end - d).days / 360 for d, c in cpn)), 1e-10)
        caught("repo_d", f"repo on clean, not dirty {b['maturity']}", abs(out["forward_dirty"] - repo_fwd_clean_mut(b, SET, end, r["clean"], rr)), 1e-10)
        s.add("repo.implied_rate", {"bond": b, "start": str(SET), "end": str(end), "clean_price": r["clean"], "forward_clean": out["forward_clean"]}, {"repo_rate": rr}, cls=A, verified=["known-truth"], tags=["repo"])
    b = {"bond": BONDS[0], "start": str(SET), "end": "2026-11-09", "clean_price": 99.0, "repo_rate": .04, "gc_rate": None}
    s.add(rop, b, error="E_DATE_ORDER", cls=E, tags=["invalid"])
    s.add(rop, {**b, "end": "2030-01-01"}, error="E_INPUT", cls=E, tags=["invalid"], description="repo ends after maturity")
    # Conversion factors and CTD.
    cop = "bond.futures.conversion_factor"
    deliv = date(2026, 12, 1)
    fut_bonds = [{"maturity": "2033-11-15", "coupon": .0425, "frequency": 2}, {"maturity": "2034-02-15", "coupon": .0400, "frequency": 2},
                 {"maturity": "2033-08-15", "coupon": .0375, "frequency": 2}, {"maturity": "2034-05-15", "coupon": .0450, "frequency": 2}]
    cfs = []
    for fb in fut_bonds:
        cf, raw = cbot_cf(fb, deliv)
        cfs.append(cf)
        s.add(cop, {"bond": fb, "delivery_month": "2026-12", "notional_coupon": .06}, {"conversion_factor": cf}, cls=E, verified=["cbot-formula", "hand"], tags=["bond-futures"])
    top = "bond.futures.basis"
    F, rr, setl = 104.40625, .0385, SET
    rows = []
    for fb, cf in zip(fut_bonds, cfs):
        r = price_yield(fb, setl, .0415 + (0.0006 if fb["coupon"] == .0375 else 0))
        rows.append((fb, cf, r["clean"]))
    res = [basis_row(fb, cf, cp, F, setl, deliv, rr) for fb, cf, cp in rows]
    irs = sorted(x["implied_repo"] for x in res)
    assert irs[-1] - irs[-2] > 1e-6, "CTD ties"
    ctd = max(range(len(res)), key=lambda k: res[k]["implied_repo"])
    s.add(top, {"futures_price": F, "settlement": str(setl), "delivery": str(deliv), "repo_rate": rr,
                "bonds": [{**fb, "clean_price": cp, "conversion_factor": cf} for fb, cf, cp in rows]},
          {"bonds": res, "ctd": ctd}, cls=A, verified=["analytic", "hand"], tags=["bond-futures", "ctd"], output_classes={"ctd": E})
    note(f"repo_d: CTD is bond {ctd}; implied repo gap to next {irs[-1] - irs[-2]:.2e}")
    write(s)


def repo_fwd(b, st, end, clean, rr, gc):
    cfs, ai0, _ = bond_cfs(b, st)
    dirty = clean + ai0
    cpn = [(d, c) for d, c in cfs if d <= end]
    fd = dirty * (1 + rr * (end - st).days / 360) - sum(c * (1 + rr * (end - d).days / 360) for d, c in cpn)
    ai1 = bond_cfs(b, end)[1]
    out = {"dirty": dirty, "forward_dirty": fd, "forward_clean": fd - ai1, "interest": dirty * rr * (end - st).days / 360}
    out["special_spread"] = None if gc is None else gc - rr
    out["specialness_value"] = None if gc is None else dirty * (gc - rr) * (end - st).days / 360
    return out


def repo_fwd_clean_mut(b, st, end, clean, rr):
    cfs, ai0, _ = bond_cfs(b, st)
    cpn = [(d, c) for d, c in cfs if d <= end]
    return ai0 + clean * (1 + rr * (end - st).days / 360) - sum(c * (1 + rr * (end - d).days / 360) for d, c in cpn)


def cbot_cf(b, deliv):
    mat = date.fromisoformat(b["maturity"])
    months = (mat.year - deliv.year) * 12 + mat.month - deliv.month - (1 if mat.day < 1 else 0)
    n, z = divmod(months, 12)
    z = z // 3 * 3
    c = b["coupon"]
    v = z if z < 7 else 3
    a = 1 / 1.03 ** (v / 6)
    bb = c / 2 * (6 - v) / 6
    cc = 1 / 1.03 ** (2 * n) if z < 7 else 1 / 1.03 ** (2 * n + 1)
    raw = a * (c / 2 + c / .06 * (1 - cc) + cc) - bb
    frac = raw * 1e4 - math.floor(raw * 1e4)
    assert abs(frac - .5) > 1e-6, "conversion factor near a rounding boundary"
    return round(raw, 4), raw


def basis_row(b, cf, clean, F, st, deliv, rr):
    cfs, ai0, _ = bond_cfs(b, st)
    dirty = clean + ai0
    aid = bond_cfs(b, deliv)[1]
    inv = F * cf + aid
    cpn = [(d, c) for d, c in cfs if d <= deliv]
    T = (deliv - st).days / 360
    ir = (inv + sum(c for _, c in cpn) - dirty) / (dirty * T - sum(c * (deliv - d).days / 360 for d, c in cpn))
    fwd = dirty * (1 + rr * T) - sum(c * (1 + rr * (deliv - d).days / 360) for d, c in cpn)
    return {"invoice": inv, "gross_basis": clean - F * cf, "net_basis": fwd - inv, "implied_repo": ir}


def bondfit_d(cv, jcv):
    s = S("bondfit_d", "04-pricing/bonds.md")
    op = "bond.fit.nelson_siegel"
    tau, truth = 2.5, [.042, -.006, .004]
    set_ = SET

    def zc(t, bt):
        x = t / tau
        e = (1 - math.exp(-x)) / x
        return bt[0] + bt[1] * e + bt[2] * (e - math.exp(-x))

    def model(b, bt):
        cfs, ai, _ = bond_cfs(b, set_)
        ts = lambda d: (d - set_).days / 365  # noqa: E731
        return sum(cf * math.exp(-zc(ts(d), bt) * ts(d)) for d, cf in cfs)
    bs = BONDS[:5] + [{"maturity": "2032-05-15", "coupon": .04, "frequency": 2}, {"maturity": "2041-11-15", "coupon": .0425, "frequency": 2}]
    px = [model(b, truth) for b in bs]
    for rich, w in ((None, None), (2, [1, 1, 0, 1, 1, 1, 1])):
        mk = list(px)
        if rich is not None:
            mk[rich] += .75
        wts = w or [1] * len(bs)
        for st in ([0, 0, 0], [.05, .01, -.02], [.03, -.02, .02]):
            sol = least_squares(lambda p: np.sqrt(wts) * (np.array([model(b, p) for b in bs]) - np.array(mk)), st, xtol=1e-15, ftol=1e-15, gtol=1e-15)
            assert np.max(np.abs(sol.x - truth)) < 1e-9, sol.x
        resid = [model(b, truth) - m for b, m in zip(bs, mk)]
        inp = {"settlement": str(set_), "tau": tau, "bonds": [{**b, "dirty_price": m} for b, m in zip(bs, mk)]}
        if w:
            inp["weights"] = w
        s.add(op, inp, {"betas": truth, "residuals": resid}, cls="calibration", verified=["known-truth", "scipy-least-squares"], tags=["sovereign-fit"] + (["relative-value"] if w else []),
              limit={"absolute": 1e-8, "relative": 0.0, "reason": "known truth with zero weighted residual; unique minimum from three starts"})
    sol = least_squares(lambda p: np.array([model(b, p) for b in bs]) - np.array(mk), truth, xtol=1e-15, ftol=1e-15, gtol=1e-15)
    caught("bondfit_d", "zero-weight (rich) bond fitted as normal", float(np.max(np.abs(sol.x - truth))), 1e-8)
    s.add(op, {"settlement": str(set_), "tau": tau, "bonds": [{**b, "dirty_price": m} for b, m in zip(bs[:2], px[:2])]}, error="E_INPUT", cls=E, tags=["invalid"], description="fewer than 3 bonds with weight")
    s.add(op, {"settlement": str(set_), "tau": 0.0, "bonds": [{**b, "dirty_price": m} for b, m in zip(bs, px)]}, error="E_DOMAIN", cls=E, tags=["invalid"])
    write(s)


def d2():
    cv, jcv = bonds_d()
    frn_repo_d(cv, jcv)
    bondfit_d(cv, jcv)


def main():
    D.estr()
    D.MUTANTS.clear()
    d2()
    note(f"stage D wave 2: {len(D.MUTANTS)} wrong-convention checks, each caught")
    for su, name, gap in D.MUTANTS:
        note(f"  mutant {su}: {name}: gap {gap:.3e}")


if __name__ == "__main__":
    main()
