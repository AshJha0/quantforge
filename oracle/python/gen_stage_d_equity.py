"""Stage D golden cases, wave 2, D5: equity dividend, borrow and financing curves, futures basis, index dividends,
dividend futures, index rebalancing, corporate actions, TRS. Analytic and exact-rational; forwards cross-checked with
QuantLib's dividend engine as in stage C. Same rules as gen_stage_d.py."""
import math
from datetime import date, timedelta
from fractions import Fraction as Fr

import QuantLib as ql
from scipy.optimize import brentq

from qf_oracle.common import note
from qf_oracle.rates import Curve
import gen_stage_d as D
from gen_stage_d import A, E, I, R, QLV, Q, S, caught, write

T0 = D.AS_OF
DISC = Curve(T0, [T0 + timedelta(d) for d in (182, 365, 730, 1826)], [math.exp(-r * d / 365) for r, d in ((.0405, 182), (.0400, 365), (.0385, 730), (.0375, 1826))])
JD = D.jcurve(DISC, [T0 + timedelta(d) for d in (182, 365, 730, 1826)], [DISC.df(T0 + timedelta(d)) for d in (182, 365, 730, 1826)])
SPOT = 5012.5
DIVS = [(date(2026, 12, 18), 18.0), (date(2027, 3, 19), 16.5), (date(2027, 6, 18), 21.0), (date(2027, 9, 17), 17.5), (date(2027, 12, 17), 19.0), (date(2028, 3, 17), 17.0)]


def t(d):
    return (d - T0).days / 365


def carry(d, b):
    return DISC.df(d) * math.exp(b * t(d))


def fwd(Tm, b, s=0.0, divs=DIVS):
    """F = [S - sum div C(t_i)] / C(T), C = D exp(b t) exp(-s t): funding curve D, borrow b, financing spread s."""
    C = lambda d: carry(d, b) * math.exp(-s * t(d))  # noqa: E731
    return (SPOT - sum(a * C(d) for d, a in divs if T0 < d <= Tm)) / C(Tm)


def ql_fwd(Tm, b):
    ql.Settings.instance().evaluationDate = Q(T0)
    dts = [T0 + timedelta(d) for d in (182, 365, 730, 1826)]
    dc = ql.DiscountCurve([Q(T0)] + [Q(d) for d in dts], [1.0] + [carry(d, b) for d in dts], ql.Actual365Fixed())
    dc.enableExtrapolation()
    h = ql.YieldTermStructureHandle(dc)
    pv = sum(a * dc.discount(Q(d)) for d, a in DIVS if T0 < d <= Tm)
    return (SPOT - pv) / dc.discount(Q(Tm))


EXP = [date(2026, 12, 18), date(2027, 3, 19), date(2027, 6, 18), date(2027, 12, 17)]


def equity_d():
    s = S("equity_d", "02-curves/equity-curves.md")
    b = .0030
    # Implied dividends from futures: X(T) = S - F(T) C(T), the carry-PV of dividends to T; yield q(T) = -ln(F C / S)/T.
    op = "eq.dividend.implied"
    fut = [(e, fwd(e, b)) for e in EXP]
    for e, F in fut:
        assert abs(ql_fwd(e, b) - F) < 1e-9
    X = [SPOT - F * carry(e, b) for e, F in fut]
    q = [-math.log(F * carry(e, b) / SPOT) / t(e) for e, F in fut]
    per = [X[0]] + [X[k] - X[k - 1] for k in range(1, len(X))]
    s.add(op, {"spot": SPOT, "funding": JD, "borrow_rate": b, "futures": [{"expiry": str(e), "price": F} for e, F in fut]},
          {"pv_dividends": X, "period_pv_dividends": per, "dividend_yields": q}, cls=A, verified=["analytic"], tags=["dividend-curve"])
    caught("equity_d", "implied dividends ignoring borrow", max(abs((SPOT - F * DISC.df(e)) - x) for (e, F), x in zip(fut, X)), 1e-8)
    s.add(op, {"spot": SPOT, "funding": JD, "borrow_rate": b, "futures": [{"expiry": str(e), "price": F} for e, F in fut[::-1]]}, error="E_INPUT", cls=E, tags=["invalid"], description="expiries strictly increasing")
    s.add(op, {"spot": -1.0, "funding": JD, "borrow_rate": b, "futures": [{"expiry": str(e), "price": F} for e, F in fut]}, error="E_DOMAIN", cls=E, tags=["invalid"])
    # Implied borrow from a forward and known dividends (monotone in b, unique).
    bop = "eq.borrow.implied"
    for e, bt in ((EXP[1], .0030), (EXP[3], .0125), (EXP[2], -.0010)):
        F = fwd(e, bt)
        got = brentq(lambda x: fwd(e, x) - F, -.5, .5, xtol=1e-16, rtol=1e-15)
        assert abs(got - bt) < 1e-12
        s.add(bop, {"spot": SPOT, "funding": JD, "dividends": [{"ex_date": str(d), "amount": a} for d, a in DIVS], "expiry": str(e), "forward": F}, {"borrow_rate": bt},
              cls=R, verified=["known-truth"], tags=["borrow-curve"])
    # Futures basis and implied financing spread.
    fop = "eq.futures.basis"
    for e, sp, mk in ((EXP[1], .0, 4980.0), (EXP[3], .0035, 4975.0), (EXP[2], .0, 4990.25)):
        fair = fwd(e, b, sp)
        imp = brentq(lambda x: fwd(e, b, x) - mk, -.5, .5, xtol=1e-16, rtol=1e-15)
        s.add(fop, {"spot": SPOT, "funding": JD, "borrow_rate": b, "financing_spread": sp, "dividends": [{"ex_date": str(d), "amount": a} for d, a in DIVS], "expiry": str(e), "futures_price": mk},
              {"fair_price": fair, "basis": mk - fair, "implied_financing_spread": imp}, cls=R, verified=["analytic", "known-truth"], tags=["futures-basis"])
        caught("equity_d", f"dividends carried on D, not C, {e}", abs((SPOT - sum(a * DISC.df(d) for d, a in DIVS if T0 < d <= e)) / carry(e, b) - fwd(e, b)), 1e-8)
    s.add(fop, {"spot": SPOT, "funding": JD, "borrow_rate": b, "financing_spread": 0.0, "dividends": [], "expiry": "2026-11-05", "futures_price": 5000.0}, error="E_DATE_ORDER", cls=E, tags=["invalid"], description="expiry before as_of")
    note("equity_d: forwards replayed through a QuantLib DiscountCurve within 1e-9 (interpolation only, not an outside model); implied borrow and financing spreads are known truth")
    write(s)


# ---------------------------------------------------------------- index dividends, dividend futures, rebalancing, corporate actions
CONS = [{"id": "A", "shares": 1200.0, "price": 185.25, "dividends": [{"ex_date": "2026-12-11", "amount": 0.82}, {"ex_date": "2027-03-12", "amount": 0.82}, {"ex_date": "2027-06-11", "amount": 0.86}]},
        {"id": "B", "shares": 800.0, "price": 412.10, "dividends": [{"ex_date": "2027-02-19", "amount": 3.10}, {"ex_date": "2027-08-20", "amount": 3.25}]},
        {"id": "C", "shares": 2500.0, "price": 61.40, "dividends": [{"ex_date": "2026-12-18", "amount": 0.45}, {"ex_date": "2027-12-17", "amount": 0.95}]}]
DIVISOR = 104.25


def index_d():
    s = S("index_d", "04-pricing/equity-index.md")
    op = "eq.index.dividends"
    pts = {}
    for c in CONS:
        for dv in c["dividends"]:
            pts[dv["ex_date"]] = pts.get(dv["ex_date"], Fr(0)) + Fr(c["shares"]) * Fr(dv["amount"]) / Fr(DIVISOR)
    dates = sorted(pts)
    periods = [("2026-12-01", "2027-12-31"), ("2027-01-01", "2027-06-30"), ("2027-07-01", "2027-12-31")]
    per = [sum((pts[d] for d in dates if a <= d <= b_), Fr(0)) for a, b_ in periods]
    lvl = sum(Fr(c["shares"]) * Fr(c["price"]) for c in CONS) / Fr(DIVISOR)
    implied = [float(x) * 1.02 for x in per]
    s.add(op, {"divisor": DIVISOR, "constituents": CONS, "periods": [{"start": a, "end": b_} for a, b_ in periods], "implied_period_points": implied},
          {"level": float(lvl), "ex_dates": dates, "points": [float(pts[d]) for d in dates], "period_points": [float(x) for x in per], "basis": [i - float(x) for i, x in zip(implied, per)]},
          cls=A, verified=["exact-rational"], tags=["index-dividends", "dividend-futures"], output_classes={"ex_dates": E})
    caught("index_d", "dividend points not divided by the divisor", float(per[0] * DIVISOR - per[0]), 1e-10)
    s.add(op, {"divisor": 0.0, "constituents": CONS, "periods": [], "implied_period_points": []}, error="E_DOMAIN", cls=E, tags=["invalid"])
    s.add(op, {"divisor": DIVISOR, "constituents": CONS, "periods": [{"start": "2027-06-30", "end": "2027-01-01"}], "implied_period_points": [1.0]}, error="E_DATE_ORDER", cls=E, tags=["invalid"])
    s.add(op, {"divisor": DIVISOR, "constituents": CONS, "periods": [{"start": "2027-01-01", "end": "2027-06-30"}], "implied_period_points": []}, error="E_INPUT", cls=E, tags=["invalid"], description="one implied value per period")
    # Rebalancing: the level is unchanged across the rebalance; the divisor absorbs it.
    rop = "eq.index.rebalance"
    new = [{"id": "A", "shares": 1100.0, "price": 185.25}, {"id": "B", "shares": 850.0, "price": 412.10}, {"id": "D", "shares": 600.0, "price": 97.80}]
    newcap = sum(Fr(c["shares"]) * Fr(c["price"]) for c in new)
    nd = newcap / lvl
    s.add(rop, {"divisor": DIVISOR, "constituents": [{k: c[k] for k in ("id", "shares", "price")} for c in CONS], "new_constituents": new},
          {"level": float(lvl), "new_divisor": float(nd), "weights": [float(Fr(c["shares"]) * Fr(c["price"]) / newcap) for c in new]}, cls=A, verified=["exact-rational"], tags=["rebalance"])
    caught("index_d", "divisor kept, level jumps", float(abs(newcap / Fr(DIVISOR) - lvl)), 1e-10)
    s.add(rop, {"divisor": DIVISOR, "constituents": [{k: c[k] for k in ("id", "shares", "price")} for c in CONS], "new_constituents": [new[0], new[0]]}, error="E_INPUT", cls=E, tags=["invalid"], description="duplicate id")
    # Corporate actions: price adjustment factor f; adjusted price = f * price, adjusted shares = shares / f.
    cop = "eq.corporate_action.adjust"
    for act, extra, f in (("SPLIT", {"ratio": 3.0}, Fr(1, 3)), ("RIGHTS", {"new_per_old": 0.25, "subscription_price": 150.0}, None), ("SPECIAL_DIVIDEND", {"amount": 12.5}, None), ("REVERSE_SPLIT", {"ratio": 0.1}, Fr(10))):
        P = Fr(185.25)
        if act == "RIGHTS":
            m, k = Fr(extra["new_per_old"]), Fr(extra["subscription_price"])
            terp = (P + m * k) / (1 + m)
            f = terp / P
        elif act == "SPECIAL_DIVIDEND":
            f = (P - Fr(extra["amount"])) / P
        elif act in ("SPLIT", "REVERSE_SPLIT"):
            f = 1 / Fr(extra["ratio"])
        s.add(cop, {"action": act, "cum_price": 185.25, "shares": 1200.0, "strike": 180.0, **extra},
              {"factor": float(f), "ex_price": float(P * f), "adjusted_shares": float(Fr(1200) / f), "adjusted_strike": float(Fr(180) * f)}, cls=A, verified=["exact-rational", "hand"], tags=["corporate-action"])
        if act == "RIGHTS":
            caught("index_d", "rights adjusted by subscription ratio only", float(abs(1 / (1 + m) - f)), 1e-10)
    s.add(cop, {"action": "SPLIT", "cum_price": 185.25, "shares": 1200.0, "strike": 180.0, "ratio": 0.0}, error="E_DOMAIN", cls=E, tags=["invalid"])
    s.add(cop, {"action": "SPECIAL_DIVIDEND", "cum_price": 185.25, "shares": 1200.0, "strike": 180.0, "amount": 200.0}, error="E_DOMAIN", cls=E, tags=["invalid"], description="amount at or above the price")
    write(s)


# ---------------------------------------------------------------- TRS
def trs_d():
    s = S("trs_d", "04-pricing/equity-index.md")
    op = "eq.trs.pv"
    b = .0030
    for start, end, cur, sp, n, side in ((date(2026, 9, 18), date(2027, 3, 19), .0402, .0045, 2000.0, "RECEIVE_EQUITY"), (date(2026, 11, 6), date(2027, 12, 17), None, .0060, 500.0, "PAY_EQUITY")):
        S0 = 4890.0 if start < T0 else SPOT
        F = fwd(end, b)
        divs = [(d, a) for d, a in DIVS if T0 < d <= end]
        eq_leg = n * (F * DISC.df(end) + sum(a * DISC.df(end) for _, a in divs) - S0 * DISC.df(end))
        al = (end - start).days / 360
        if cur is None:
            fl = (DISC.df(start) / DISC.df(end) - 1) / al
        else:
            fl = cur
        fund = n * S0 * (fl + sp) * al * DISC.df(end)
        sg = 1 if side == "RECEIVE_EQUITY" else -1
        s.add(op, {"spot": SPOT, "funding": JD, "borrow_rate": b, "dividends": [{"ex_date": str(d), "amount": a} for d, a in DIVS],
                   "trade": {"start": str(start), "end": str(end), "initial_price": S0, "shares": n, "spread": sp, "side": side}, "current_rate": cur},
              {"equity_leg": eq_leg, "funding_leg": fund, "pv": sg * (eq_leg - fund)}, cls=A, verified=["analytic"], tags=["trs"])
        caught("trs_d", f"TRS without dividends, {end}", abs(n * sum(a * DISC.df(end) for _, a in divs)), 1e-9 * n * S0)
    s.add(op, {"spot": SPOT, "funding": JD, "borrow_rate": b, "dividends": [], "trade": {"start": "2026-09-18", "end": "2027-03-19", "initial_price": 4890.0, "shares": 1.0, "spread": 0.0, "side": "RECEIVE_EQUITY"}, "current_rate": None},
          error="E_INPUT", cls=E, tags=["invalid", "ruling"], description="started period needs current_rate")
    write(s)


def main():
    D.estr()
    D.MUTANTS.clear()
    equity_d()
    index_d()
    trs_d()
    note(f"stage D D5: {len(D.MUTANTS)} wrong-convention checks, each caught")


if __name__ == "__main__":
    main()
