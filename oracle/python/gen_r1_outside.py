"""R1: stage D cases with an outside oracle under rule 11.2.5. Suite stage_d/outside_d.

Expected values come from the same own-code replays as the stage D generators (exact-rational compounding,
bond cash-flow sums, the ISDA replay, Black and Bachelier on own schedules). Every case is then re-priced by
outside_d.py in QuantLib from the case inputs alone, through the reviewed convention map, and the run stops
if any case fails that check. Inputs avoid solver-path and libm sensitivity: yields and spreads are inverted
only where the root is simple and bracketed, and no case sits near a discrete threshold.
"""
import math
from datetime import date, timedelta

from qf_oracle.common import note
from qf_oracle.rates import add_bd, add_months, adjust, schedule
from qf_oracle.dates import yf
import gen_stage_d as D
import gen_stage_d_w2 as W2
import gen_stage_d_credit as CR
import gen_stage_d_vol as V
from gen_stage_d import A, E, I, R, QLV, S, write
from fractions import Fraction as Fr

G = "oracle/python/gen_r1_outside.py"
TAG = "outside-r1"

BONDS = [
    {"maturity": "2028-02-29", "coupon": .0200, "frequency": 2},   # leap-day, end-of-month
    {"maturity": "2030-04-30", "coupon": .0350, "frequency": 2},   # end-of-month, 30-day month
    {"maturity": "2032-08-31", "coupon": .0410, "frequency": 2},   # end-of-month, 31-day month
    {"maturity": "2035-05-15", "coupon": .0000, "frequency": 1},   # zero coupon
    {"maturity": "2029-06-15", "coupon": .0575, "frequency": 4},
    {"maturity": "2040-01-15", "coupon": .0125, "frequency": 1},
    {"maturity": "2053-11-15", "coupon": .0500, "frequency": 2},   # long
    {"maturity": "2027-05-17", "coupon": .0300, "frequency": 2},   # short, one coupon left
    {"maturity": "2033-11-09", "coupon": .0275, "frequency": 2},   # settlement on a coupon date
    {"maturity": "2045-02-28", "coupon": .0450, "frequency": 2},   # February end, not leap
]
SETTLES = [date(2026, 11, 9), date(2027, 2, 26), date(2027, 5, 14)]
YIELDS = [.0425, -.0050, .0001]


def bonds(s):
    cv = W2.SPOT_CURVE
    jcv = D.jcurve(cv, W2._dates(cv), [cv.df(d) for d in W2._dates(cv)])
    for b in BONDS:
        mat = date.fromisoformat(b["maturity"])
        for st in SETTLES:
            if st >= mat:
                continue
            for y in YIELDS:
                r = W2.price_yield(b, st, y)
                s.add("bond.price.from_yield", {"bond": b, "settlement": str(st), "yield": y}, r, cls=A, verified=[QLV, "analytic"], tags=[TAG, "fixed-bond"])
            r = W2.price_yield(b, st, .0425)
            s.add("bond.yield.from_price", {"bond": b, "settlement": str(st), "clean_price": r["clean"]}, {"yield": .0425, "dirty": r["dirty"], "accrued": r["accrued"]},
                  cls=R, verified=[QLV, "known-truth"], tags=[TAG, "fixed-bond"])
            dp, ai = W2.curve_dirty(b, st, cv)
            s.add("bond.price.from_curve", {"bond": b, "settlement": str(st), "curve": jcv}, {"dirty": dp, "accrued": ai, "clean": dp - ai},
                  cls=I, verified=["independent-replay", QLV], tags=[TAG, "fixed-bond"])
            for z in (.0060, -.0025):
                dz, ai = W2.curve_dirty(b, st, cv, z)
                s.add("bond.spread.z", {"bond": b, "settlement": str(st), "curve": jcv, "clean_price": dz - ai}, {"z_spread": z}, cls=R, verified=[QLV, "known-truth"],
                      tags=[TAG, "z-spread"])


WINDOWS = [("SOFR", date(2026, 11, 20), date(2026, 12, 21)),   # US Thanksgiving
           ("SOFR", date(2026, 12, 15), date(2027, 3, 15)),    # year end, MLK, Presidents Day
           ("ESTR", date(2027, 3, 22), date(2027, 4, 22)),     # TARGET Easter
           ("ESTR", date(2026, 12, 28), date(2027, 6, 28)),    # year end, six months
           ("SONIA", date(2027, 3, 24), date(2027, 6, 24)),    # UK Easter and May bank holidays
           ("SONIA", date(2027, 8, 25), date(2027, 9, 27))]    # UK summer bank holiday


def compounding(s):
    for conv, S0, E0 in WINDOWS:
        fl = D.fixings(conv, S0 - timedelta(20), E0)
        fx = dict(fl)
        for method, k in (("NONE", 0), ("LOOKBACK", 2), ("LOOKBACK", 5), ("OBSERVATION_SHIFT", 2), ("OBSERVATION_SHIFT", 5), ("LOCKOUT", 2), ("LOCKOUT", 1)):
            r, _, _ = D.compound(conv, S0, E0, method, k, fx)
            acc = Fr((E0 - S0).days, D.DEN[conv])
            s.add("rates.ois.compound_dated", {"convention": conv, "start": str(S0), "end": str(E0), "method": method, "shift_days": k,
                                                "fixings": [{"date": str(d), "rate": v} for d, v in fl]},
                  {"compounded_rate": float(r), "accrual": float(acc), "interest": float(r * acc)}, cls=A, verified=["exact-rational", QLV],
                  tags=[TAG, conv, method.lower()], limit=D.RATELIM)


def caps_swaptions(s):
    disc, jd, pc, jp = V.curves()
    T0 = V.T0
    spot = add_bd("USGS", T0, 2)
    for typ, sm, tm, K, model, vol, N in (("CAP", 1, 12, .0350, "BLACK_76", .30, 1e7), ("FLOOR", 6, 60, .0320, "BLACK_76", .27, 1e7), ("CAP", 12, 120, .0420, "BLACK_76", .19, 2.5e7),
                                          ("FLOOR", 3, 36, .0360, "BACHELIER", .0105, 1e7), ("CAP", 24, 60, .0300, "BACHELIER", .0088, 5e6), ("CAP", 3, 24, .0010, "BACHELIER", .0100, 1e7)):
        st = adjust("USGS", add_months(spot, sm))
        ds = schedule("USGS", st, add_months(st, tm), 3)
        caps = []
        for a, e in zip(ds, ds[1:]):
            al = float(yf("ACT_360", a, e))
            F = (pc.df(a) / pc.df(e) - 1) / al
            caps.append(N * al * disc.df(e) * V.opt(model, typ == "CAP", F, K, vol, (a - T0).days / 365))
        s.add("rates.cap.price", {"discount": jd, "projection": jp, "model": model, "vol": vol, "trade": {"type": typ, "start_months": sm, "tenor_months": tm, "strike": K, "notional": N}},
              {"price": sum(caps), "caplets": caps}, cls=I, verified=["independent-replay", QLV], tags=[TAG, "cap"],
              limit={"absolute": 1e-9 * N, "relative": 1e-9, "reason": "curve tolerance on notional"})
    for typ, em, tm, K, model, vol, N in (("PAYER", 3, 24, .0360, "BLACK_76", .25, 1e7), ("RECEIVER", 6, 120, .0380, "BLACK_76", .20, 1e7), ("PAYER", 36, 60, .0300, "BLACK_76", .23, 1e7),
                                          ("RECEIVER", 12, 240, .0410, "BACHELIER", .0092, 1e7), ("PAYER", 120, 120, .0400, "BACHELIER", .0085, 1e7), ("RECEIVER", 24, 36, .0330, "BACHELIER", .0101, 2e7)):
        st = adjust("USGS", add_months(spot, em))
        fx = schedule("USGS", st, add_months(st, tm), 12)
        fl = schedule("USGS", st, add_months(st, tm), 3)
        Aa = sum(float(yf("THIRTY_360_BOND", a, e)) * disc.df(e) for a, e in zip(fx, fx[1:]))
        Fl = sum((pc.df(a) / pc.df(e) - 1) * disc.df(e) for a, e in zip(fl, fl[1:]))
        Sw = Fl / Aa
        price = N * Aa * V.opt(model, typ == "PAYER", Sw, K, vol, (st - T0).days / 365)
        s.add("rates.swaption.price", {"discount": jd, "projection": jp, "model": model, "vol": vol, "trade": {"type": typ, "expiry_months": em, "tenor_months": tm, "strike": K, "notional": N}},
              {"price": price, "forward_rate": Sw, "annuity": Aa}, cls=I, verified=["independent-replay", QLV], tags=[TAG, "swaption"],
              limit={"absolute": 1e-9 * N, "relative": 1e-9, "reason": "curve tolerance on notional"})


def cds(s):
    T = D.AS_OF
    disc = D.Curve(T, [T + timedelta(7305)], [math.exp(-.039 * 7305 / 365)])
    jd = D.jcurve(disc, CR.disc_dates(disc), [disc.df(d) for d in CR.disc_dates(disc)])
    for name, Rr, qs in (("IG", .40, CR.QUOTES), ("HY", .25, [(t, 4 * q) for t, q in CR.QUOTES])):
        H, mats, surv = CR.bootstrap(T, disc, Rr, qs)
        jh = CR.jhz(T, mats, surv)
        for mat in (date(2027, 12, 20), date(2028, 6, 20), date(2030, 12, 20), date(2031, 6, 20), date(2034, 12, 20), date(2036, 12, 20)):
            for cpn, side, payout in ((.01, "BUY_PROTECTION", "STANDARD"), (.05, "SELL_PROTECTION", "STANDARD"))[: 2 if name == "IG" else 1] + (((.01, "BUY_PROTECTION", "DIGITAL"),) if mat.year == 2030 else ()):
                N = 1e7
                p = CR.price(T, disc, H, mat, Rr, cpn, payout == "DIGITAL")
                sign = 1 if side == "BUY_PROTECTION" else -1
                out = {"pv": sign * N * p["pv_unit"], "upfront": p["upfront"], "accrued": p["accrued"], "par_spread": p["par_spread"],
                       "protection_leg": p["protection_leg"], "rpv01": p["rpv01"]}
                s.add("credit.cds.price", {"trade_date": str(T), "discount": jd, "hazard": jh, "recovery": Rr, "trade": {"maturity": str(mat), "coupon": cpn, "notional": N, "side": side},
                                           "payout": payout}, out, cls=I, verified=["independent-replay", "quantlib-1.44-isda-cds-engine"], tags=[TAG, "isda-cds"],
                      limit={"absolute": 0.01, "relative": 1e-9, "reason": "ISDA replay against QuantLib within 2e-10 per unit"})


def main():
    D.estr()
    s = S("outside_d", "02-curves/stage-d-targets.md")
    s.generator = G
    bonds(s)
    compounding(s)
    caps_swaptions(s)
    cds(s)
    write(s)
    import outside_d as O
    got = {suite: (k, n) for suite, k, n in O.verify_all(show=True)[1]}
    k, n = got["outside_d"]
    assert k == n, f"outside_d: {n - k} of {n} cases fail the QuantLib check"
    note(f"outside_d: all {n} cases re-priced in QuantLib {O.CM.VERSION} through the convention map")


if __name__ == "__main__":
    main()
