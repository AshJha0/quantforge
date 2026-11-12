"""Stage D golden cases, wave 2, D4: ISDA CDS, index CDS, composite curves, digital CDS. Same rules as gen_stage_d.py.

The ISDA standard model is replayed here and checked against QuantLib's IsdaCdsEngine (Taylor fix, no bias, piecewise
forwards). The ISDA C library itself is not run; QuantLib's engine is the outside source.
"""
import math
from datetime import date, timedelta

import QuantLib as ql
from scipy.optimize import brentq

from qf_oracle.common import note
import gen_stage_d as D
from gen_stage_d import E, I, QLV, Q, S, caught, write

CALQ = ql.WeekendsOnly()
NODISC = False
WORST = [0.0, 0.0]
QLE = "quantlib-1.44-isda-cds-engine"


def wk(d):
    while d.weekday() >= 5:
        d += timedelta(1)
    return d


def add_bd_w(d, n):
    while n:
        d += timedelta(1)
        n -= d.weekday() < 5
    return d


def roll(T):
    if (T.month, T.day) >= (9, 20):
        return date(T.year, 12, 20)
    if (T.month, T.day) >= (3, 20):
        return date(T.year, 6, 20)
    return date(T.year - 1, 12, 20)


def maturity(T, tenor):
    r = roll(T)
    n = int(tenor[:-1])
    m = n * 12 if tenor[-1] == "Y" else n
    y, mo = divmod(r.year * 12 + r.month - 1 + m, 12)
    return date(y, mo + 1, 20)


def periods(T, mat):
    """(accrual start, accrual end, payment) with unadjusted ends shifted per ISDA below. Starts at the last IMM date <= T."""
    imm = [date(y, m, 20) for y in range(T.year - 1, mat.year + 1) for m in (3, 6, 9, 12)]
    prev = max(d for d in imm if d <= T)
    ds = [d for d in imm if prev <= d <= mat]
    out = []
    for j, (a, b) in enumerate(zip(ds, ds[1:])):
        last = j == len(ds) - 2
        out.append((wk(a), b if last else wk(b), wk(b), last))
    return out


class Hz:
    def __init__(self, T, dates, hz):
        self.T, self.dates, self.hz = T, list(dates), list(hz)
        self.t = [(d - T).days / 365 for d in dates]

    def logq(self, t):
        s, p = 0.0, 0.0
        for e, h in zip(self.t, self.hz):
            if t <= e:
                return s + h * (t - p)
            s += h * (e - p)
            p = e
        return s + self.hz[-1] * (t - p)

    def lam(self, t):
        for e, h in zip(self.t, self.hz):
            if t <= e:
                return h
        return self.hz[-1]


def legs(T, disc, hz, mat, R, digital=False):
    """Returns (protection, rpv01 per unit coupon incl. accrual on default, accrual fraction, P(cash settle))."""
    tt = lambda d: (d - T).days / 365  # noqa: E731
    nodes = sorted(set(hz.t + ([] if NODISC else [(d - T).days / 365 for d in disc_dates(disc)])))

    def lnP(t):
        # discount is log-linear in curve time between pillars: piecewise-constant forward
        ts, ls = disc_tl(disc)
        if t >= ts[-1]:
            f = (ls[-1] - ls[-2]) / (ts[-1] - ts[-2])
            return ls[-1] + f * (t - ts[-1])
        i = max(k for k in range(len(ts) - 1) if ts[k] <= t)
        u = (t - ts[i]) / (ts[i + 1] - ts[i])
        return (1 - u) * ls[i] + u * ls[i + 1]

    def fwd(a, b):
        return (lnP(b) - lnP(a)) / (b - a)

    def pieces(a, b):
        pts = [a] + [x for x in nodes if a < x < b] + [b]
        return list(zip(pts, pts[1:]))

    def qp(t):
        return math.exp(-hz.logq(t) - lnP(t))
    prot = 0.0
    for a, b in pieces(0.0, tt(mat)):
        h, f = hz.lam((a + b) / 2), fwd(a, b)
        prot += h / (f + h) * (qp(a) - qp(b))
    prot *= 1.0 if digital else 1 - R
    rp = 0.0
    per = periods(T, mat)
    for a, e, p, last in per:
        a1, e1 = a - timedelta(1), p - timedelta(1)
        alpha = ((e + timedelta(1) if last else e) - a).days / 360
        rp += alpha * math.exp(-hz.logq(tt(e1))) * math.exp(-lnP(tt(p)))
        ta = tt(a1)
        for x, y in pieces(max(ta, 0.0), tt(e1)):
            h, f = hz.lam((x + y) / 2), fwd(x, y)
            k, Dl = f + h, y - x
            Ex = math.exp(-k * Dl)
            rp += 365 / 360 * h * qp(x) * ((x - ta) * (1 - Ex) / k + (1 - Ex * (1 + k * Dl)) / k ** 2)
    acc = (T + timedelta(1) - per[0][0]).days / 360
    cs = add_bd_w(T, 3)
    return prot, rp, acc, math.exp(-lnP(tt(cs)))


def disc_dates(c):
    return [c.as_of + timedelta(round(t * 365)) for t in c.t[1:]]


def disc_tl(c):
    return c.t, [-math.log(x) for x in c.d]


def price(T, disc, hz, mat, R, cpn, digital=False):
    prot, rp, acc, pcs = legs(T, disc, hz, mat, R, digital)
    clean = rp - acc * pcs
    return {"protection_leg": prot, "rpv01": rp, "accrued": cpn * acc, "par_spread": prot / clean,
            "upfront": (prot - cpn * rp) / pcs + cpn * acc, "pv_unit": prot - cpn * rp + cpn * acc * pcs}


def bootstrap(T, disc, R, quotes):
    mats = [maturity(T, t) for t, _ in quotes]
    hz = []
    for j, (t, s) in enumerate(quotes):
        def err(h):
            return price(T, disc, Hz(T, mats[:j + 1], hz + [h]), mats[j], R, s)["par_spread"] - s
        hz.append(brentq(err, 1e-8, 3.0, xtol=1e-16, rtol=1e-15, maxiter=500))
    H = Hz(T, mats, hz)
    return H, mats, [math.exp(-H.logq((m - T).days / 365)) for m in mats]


def ql_setup(T, disc, H, R):
    ql.Settings.instance().evaluationDate = Q(T)
    dts = disc_dates(disc)
    dc = ql.DiscountCurve([Q(T)] + [Q(d) for d in dts], [1.0] + [disc.df(d) for d in dts], ql.Actual365Fixed())
    dc.enableExtrapolation()
    hc = ql.HazardRateCurve([Q(T)] + [Q(d) for d in H.dates], [H.hz[0]] + H.hz, ql.Actual365Fixed())
    hc.enableExtrapolation()
    return ql.YieldTermStructureHandle(dc), ql.DefaultProbabilityTermStructureHandle(hc)


def ql_cds(T, mat, cpn, R, dh, ph, digital=False):
    sch = ql.Schedule(Q(T), Q(mat), ql.Period(3, ql.Months), CALQ, ql.Following, ql.Unadjusted, ql.DateGeneration.CDS2015, False)
    c = ql.CreditDefaultSwap(ql.Protection.Buyer, 1.0, 0.0, cpn, sch, ql.Following, ql.Actual360(), True, True, Q(T) + 1, CALQ.advance(Q(T), 3, ql.Days), ql.FaceValueClaim(), ql.Actual360(True), True, Q(T), 3)
    c.setPricingEngine(ql.IsdaCdsEngine(ph, 0.0 if digital else R, dh, False, ql.IsdaCdsEngine.Taylor, ql.IsdaCdsEngine.NoBias, ql.IsdaCdsEngine.Piecewise))
    return c


QUOTES = [("6M", .0045), ("1Y", .0060), ("3Y", .0090), ("5Y", .0120), ("7Y", .0135), ("10Y", .0150)]


def jhz(T, mats, surv):
    return {"as_of": str(T), "pillars": [{"date": str(d), "survival": v} for d, v in zip(mats, surv)]}


def credit_d():
    s = S("credit_d", "04-pricing/credit.md")
    T = D.AS_OF
    sofr, ud, up = D.bootstrap_ois_j("SOFR", T, D.B.SOFR_Q)
    jsofr = D.jcurve(sofr, [p[-1][2] for p in up], ud)
    disc = D.Curve(T, [T + timedelta(7305)], [math.exp(-.039 * 7305 / 365)])
    jd = D.jcurve(disc, disc_dates(disc), [disc.df(d) for d in disc_dates(disc)])
    curves = {}
    for name, R, qs in (("IG", .40, QUOTES), ("HY", .25, [(t, 4 * q) for t, q in QUOTES]), ("SNR", .40, [(t, q * .7) for t, q in QUOTES[1:]])):
        H, mats, surv = bootstrap(T, disc, R, qs)
        curves[name] = (H, mats, surv, R)
        dh, ph = ql_setup(T, disc, H, R)
        for (t, q), m in zip(qs, mats):
            fs = ql_cds(T, m, q, R, dh, ph).fairSpread()
            assert abs(fs - q) < 1e-9, (name, t, fs, q)
            WORST[0] = max(WORST[0], abs(fs - q))
        s.add("credit.cds.bootstrap", {"trade_date": str(T), "discount": jd, "recovery": R, "quotes": [{"tenor": t, "spread": q} for t, q in qs]},
              {"pillars": [{"date": str(d), "survival": v} for d, v in zip(mats, surv)]}, cls=I, verified=["independent-replay", QLE], tags=["isda-cds"],
              limit={"absolute": 1e-9, "relative": 0.0, "reason": "curve solve; spreads reprice below 1e-13"})
        # Mutant: pillars one day after maturity (QuantLib helper's default), moves later pillars.
        mats1 = [m + timedelta(1) for m in mats]
        hz1 = []
        for j, (t, q) in enumerate(qs):
            hz1.append(brentq(lambda h: price(T, disc, Hz(T, mats1[:j + 1], hz1 + [h]), mats[j], R, q)["par_spread"] - q, 1e-8, 3.0, xtol=1e-16))
        H1 = Hz(T, mats1, hz1)
        caught("credit_d", f"{name}: hazard nodes at maturity + 1 day", max(abs(math.exp(-H1.logq((m - T).days / 365)) - v) for m, v in zip(mats, surv)), 1e-9)
    note(f"credit_d: ISDA bootstrap replay reprices with QuantLib IsdaCdsEngine fair spreads within {WORST[0]:.1e}")
    # Pricing: standard coupons 100 and 500, digital payout.
    pop = "credit.cds.price"
    for name, mat, cpn, side, N, dig in (("IG", date(2031, 12, 20), .01, "BUY_PROTECTION", 1e7, False), ("HY", date(2031, 12, 20), .05, "SELL_PROTECTION", 5e6, False),
                                         ("IG", date(2029, 6, 20), .01, "BUY_PROTECTION", 1e7, False), ("IG", date(2036, 12, 20), .01, "SELL_PROTECTION", 1e7, False),
                                         ("IG", date(2031, 12, 20), .01, "BUY_PROTECTION", 1e7, True)):
        H, mats, surv, R = curves[name]
        r = price(T, disc, H, mat, R, cpn, dig)
        dh, ph = ql_setup(T, disc, H, R)
        c = ql_cds(T, mat, cpn, R, dh, ph, dig)
        assert abs(c.NPV() - r["pv_unit"]) < 1e-9 and abs(c.fairSpread() - r["par_spread"]) < 1e-9 and abs(c.fairUpfront() - r["upfront"]) < 1e-9, (name, c.NPV(), r)
        WORST[1] = max(WORST[1], abs(c.NPV() - r["pv_unit"]), abs(c.fairUpfront() - r["upfront"]))
        sg = 1 if side == "BUY_PROTECTION" else -1
        out = {"pv": sg * N * r["pv_unit"], "upfront": r["upfront"], "accrued": r["accrued"], "par_spread": r["par_spread"], "protection_leg": r["protection_leg"], "rpv01": r["rpv01"]}
        s.add(pop, {"trade_date": str(T), "discount": jd, "hazard": jhz(T, mats, surv), "recovery": R, "trade": {"maturity": str(mat), "coupon": cpn, "notional": N, "side": side}, "payout": "DIGITAL" if dig else "STANDARD"},
              out, cls=I, verified=["independent-replay", QLE], tags=["isda-cds"] + (["digital"] if dig else []),
              limit={"absolute": 1e-9 * N, "relative": 1e-9, "reason": "ISDA replay against QuantLib within 2e-10 per unit"}, output_classes=None)
        if not dig:
            # Mutants: protection from step-in, no accrual on default, par spread on the dirty annuity.
            p2 = legs_mut_stepin(T, disc, H, mat, R)
            caught("credit_d", f"{name} {mat}: protection from step-in, not trade date", abs(p2 - r["protection_leg"]), 1e-10)
            caught("credit_d", f"{name} {mat}: par spread on dirty annuity", abs(r["protection_leg"] / r["rpv01"] - r["par_spread"]), 1e-10)
        else:
            caught("credit_d", "digital paid as (1 - R)", abs(price(T, disc, H, mat, R, cpn)["protection_leg"] - r["protection_leg"]), 1e-10)
    note(f"credit_d: CDS NPV and upfront match QuantLib IsdaCdsEngine within {WORST[1]:.1e} per unit")
    # Index CDS intrinsic value and basis.
    iop = "credit.index.intrinsic"
    names = [("IG", 1.0), ("SNR", 1.0), ("HY", 0.5)]
    mat = date(2031, 12, 20)
    ws = sum(w for _, w in names)
    ups = [price(T, disc, curves[n][0], mat, curves[n][3], .01)["upfront"] for n, _ in names]
    intr = sum(w * u for (_, w), u in zip(names, ups)) / ws
    quoted = intr + .0015
    s.add(iop, {"trade_date": str(T), "discount": jd, "names": [{"hazard": jhz(T, curves[n][1], curves[n][2]), "recovery": curves[n][3], "weight": w} for n, w in names],
                "trade": {"maturity": str(mat), "coupon": .01}, "quoted_upfront": quoted},
          {"intrinsic_upfront": intr, "basis": quoted - intr, "name_upfronts": ups}, cls=I, verified=["independent-replay", QLE], tags=["index-cds"],
          limit={"absolute": 1e-9, "relative": 0.0, "reason": "sum of ISDA prices"})
    caught("credit_d", "index intrinsic unweighted", abs(sum(ups) / len(ups) - intr), 1e-9)
    s.add(iop, {"trade_date": str(T), "discount": jd, "names": [], "trade": {"maturity": str(mat), "coupon": .01}, "quoted_upfront": 0.0}, error="E_INPUT", cls=E, tags=["invalid"])
    # Composite (sector, rating) curve: weighted mean spread per tenor, times a scale, then bootstrapped.
    cop = "credit.curve.composite"
    cons = [(QUOTES, 2.0), ([(t, q * 1.3) for t, q in QUOTES], 1.0), ([(t, q * .8) for t, q in QUOTES], 1.0)]
    for scale in (1.0, 1.75):
        comp = [(t, scale * sum(w * qs[k][1] for qs, w in cons) / sum(w for _, w in cons)) for k, (t, _) in enumerate(QUOTES)]
        H, mats, surv = bootstrap(T, disc, .40, comp)
        s.add(cop, {"trade_date": str(T), "discount": jd, "recovery": .40, "constituents": [{"quotes": [{"tenor": t, "spread": q} for t, q in qs], "weight": w} for qs, w in cons], "scale": scale},
              {"spreads": [q for _, q in comp], "pillars": [{"date": str(d), "survival": v} for d, v in zip(mats, surv)]}, cls=I, verified=["independent-replay", QLE], tags=["sector-curve"] + (["rating"] if scale != 1 else []),
              limit={"absolute": 1e-9, "relative": 0.0, "reason": "curve solve"})
    s.add(cop, {"trade_date": str(T), "discount": jd, "recovery": .40, "constituents": [{"quotes": [{"tenor": t, "spread": q} for t, q in QUOTES], "weight": 1.0}, {"quotes": [{"tenor": "1Y", "spread": .01}], "weight": 1.0}], "scale": 1.0},
          error="E_INPUT", cls=E, tags=["invalid"], description="constituents on different tenors")
    b = {"trade_date": str(T), "discount": jd, "recovery": .40, "quotes": [{"tenor": t, "spread": q} for t, q in QUOTES]}
    s.add("credit.cds.bootstrap", {**b, "recovery": 1.0}, error="E_DOMAIN", cls=E, tags=["invalid"])
    s.add("credit.cds.bootstrap", {**b, "quotes": b["quotes"][::-1]}, error="E_INPUT", cls=E, tags=["invalid"])
    s.add("credit.cds.bootstrap", {**b, "quotes": [{"tenor": "5Y", "spread": -.001}]}, error="E_DOMAIN", cls=E, tags=["invalid"])
    # R6-7.3 (replaces D19): a trade date on an adjusted coupon date is priced; same case id, now a value case on a curve set at that date
    T3 = date(2026, 12, 21)
    disc3 = D.Curve(T3, [T3 + timedelta(7305)], [math.exp(-.039 * 7305 / 365)])
    H3, mats3, surv3 = bootstrap(T3, disc3, .40, QUOTES)
    dh3, ph3 = ql_setup(T3, disc3, H3, .40)
    for (t, q), m in zip(QUOTES, mats3):
        assert abs(ql_cds(T3, m, q, .40, dh3, ph3).fairSpread() - q) < 1e-9
    s.add("credit.cds.bootstrap", {**b, "trade_date": str(T3), "discount": D.jcurve(disc3, disc_dates(disc3), [disc3.df(d) for d in disc_dates(disc3)])},
          {"pillars": [{"date": str(d), "survival": v} for d, v in zip(mats3, surv3)]}, cls=I, verified=["independent-replay", QLE], tags=["ruling", "r6"],
          limit={"absolute": 1e-9, "relative": 0.0, "reason": "curve solve; spreads reprice below 1e-13"},
          description="trade date on an adjusted coupon date: priced, accrual from T (R6-7.3; was E_INPUT under D19)")
    # A trade date in February: roll date is the previous 20 December.
    T2 = date(2027, 2, 10)
    disc2 = D.Curve(T2, [T2 + timedelta(365 * k) for k in (1, 3, 5, 10, 15)], [math.exp(-.038 * k) for k in (1, 3, 5, 10, 15)])
    jd2 = D.jcurve(disc2, disc_dates(disc2), [disc2.df(d) for d in disc_dates(disc2)])
    H, mats, surv = bootstrap(T2, disc2, .40, QUOTES)
    assert mats[2] == date(2029, 12, 20)
    dh, ph = ql_setup(T2, disc2, H, .40)
    for (t, q), m in zip(QUOTES, mats):
        assert abs(ql_cds(T2, m, q, .40, dh, ph).fairSpread() - q) < 1e-9
    s.add("credit.cds.bootstrap", {"trade_date": str(T2), "discount": jd2, "recovery": .40, "quotes": [{"tenor": t, "spread": q} for t, q in QUOTES]},
          {"pillars": [{"date": str(d), "survival": v} for d, v in zip(mats, surv)]}, cls=I, verified=["independent-replay", QLE], tags=["isda-cds", "roll-date"],
          limit={"absolute": 1e-9, "relative": 0.0, "reason": "curve solve"})
    # Multi-node discount curve: discount pillars are integration nodes too.
    H, mats, surv = bootstrap(T, sofr, .40, QUOTES)
    dh, ph = ql_setup(T, sofr, H, .40)
    gap = max(abs(ql_cds(T, m, q, .40, dh, ph).fairSpread() - q) for (t, q), m in zip(QUOTES, mats))
    assert gap < 1e-8
    note(f"credit_d: on the SOFR curve, QuantLib's IsdaCdsEngine fair spreads agree with the replay within {gap:.1e}")
    s.add("credit.cds.bootstrap", {"trade_date": str(T), "discount": jsofr, "recovery": .40, "quotes": [{"tenor": t, "spread": q} for t, q in QUOTES]},
          {"pillars": [{"date": str(d), "survival": v} for d, v in zip(mats, surv)]}, cls=I, verified=["independent-replay", QLE], tags=["isda-cds", "multi-node-discount"],
          limit={"absolute": 1e-9, "relative": 0.0, "reason": "curve solve"})
    write(s)


def legs_mut_stepin(T, disc, H, mat, R):
    # protection from T + 1: shift the start of integration by one day
    full = legs(T, disc, H, mat, R)[0]
    first = legs_window(T, disc, H, R)
    return full - first


def legs_window(T, disc, H, R):
    t1 = 1 / 365
    ts, ls = disc_tl(disc)
    f = (ls[1] - ls[0]) / (ts[1] - ts[0])
    h = H.lam(t1 / 2)
    return (1 - R) * h / (f + h) * (1 - math.exp(-(f + h) * t1))


def main():
    D.estr()
    D.MUTANTS.clear()
    credit_d()
    note(f"stage D D4: {len(D.MUTANTS)} wrong-convention checks, each caught")


if __name__ == "__main__":
    main()
