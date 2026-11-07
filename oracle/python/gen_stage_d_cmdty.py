"""Stage D golden cases, wave 3, D8: commodity forward curves with seasonality, storage carry. Analytic. Same rules as gen_stage_d.py."""
import math
from datetime import date

from qf_oracle.common import note
from qf_oracle.rates import Curve
import gen_stage_d as D
from gen_stage_d import A, E, S, caught, write
from gen_stage_d_w3 import mi

T0 = D.AS_OF
SEAS = [.060, .045, .010, -.030, -.045, -.040, -.020, -.015, -.020, .000, .025, .030]


def fcurve(quotes, seas, use=True):
    ks = [mi(m) for m, _ in quotes]
    L = [math.log(p) - (seas[k % 12] if use and seas else 0.0) for k, (_, p) in zip(ks, quotes)]

    def f(k):
        if k < ks[0] or k > ks[-1]:
            raise ValueError
        j = max(i for i in range(len(ks)) if ks[i] <= k)
        l = L[j] if j == len(ks) - 1 else L[j] + (L[j + 1] - L[j]) * (k - ks[j]) / (ks[j + 1] - ks[j])
        return math.exp(l + (seas[k % 12] if seas else 0.0))
    return f


def cmdty_d():
    s = S("commodity_d", "02-curves/commodity.md")
    op = "cmdty.curve.forward"
    quotes = [("2026-12", 3.420), ("2027-03", 3.105), ("2027-06", 2.880), ("2027-12", 3.560), ("2028-12", 3.640), ("2030-12", 3.700)]
    months = ["2026-12", "2027-01", "2027-02", "2027-05", "2027-08", "2027-11", "2028-07", "2029-01", "2030-12"]
    for seas in (SEAS, None):
        cv = fcurve(quotes, seas)
        out = [cv(mi(m)) for m in months]
        for m, p in quotes:
            assert abs(cv(mi(m)) - p) < 1e-13
        s.add(op, {"quotes": [{"month": m, "price": p} for m, p in quotes], "seasonality": seas, "months": months}, {"forwards": out}, cls=A, verified=["analytic"], tags=["commodity-curve"] + (["seasonality"] if seas else []))
        if seas:
            raw = fcurve(quotes, None)
            caught("commodity_d", "interpolated without removing seasonality", max(abs(raw(mi(m)) - v) for m, v in zip(months, out)), 1e-12 + 1e-10 * 4)
    b = {"quotes": [{"month": m, "price": p} for m, p in quotes], "seasonality": SEAS, "months": ["2031-01"]}
    s.add(op, b, error="E_OUT_OF_RANGE", cls=E, tags=["invalid", "ruling"], description="no extrapolation past the last quote")
    s.add(op, {**b, "months": ["2027-01"], "quotes": b["quotes"][::-1]}, error="E_INPUT", cls=E, tags=["invalid"])
    s.add(op, {**b, "months": ["2027-01"], "quotes": [{"month": "2026-12", "price": 0.0}, {"month": "2027-03", "price": 3.0}]}, error="E_DOMAIN", cls=E, tags=["invalid"])
    s.add(op, {**b, "months": ["2027-01"], "seasonality": SEAS[:6]}, error="E_INPUT", cls=E, tags=["invalid"])
    # Storage carry.
    cop = "cmdty.storage.carry"
    disc = Curve(T0, [date(2027, 5, 6), date(2027, 11, 8), date(2028, 11, 6), date(2031, 11, 6)], [math.exp(-r * ((d - T0).days / 365)) for d, r in zip([date(2027, 5, 6), date(2027, 11, 8), date(2028, 11, 6), date(2031, 11, 6)], [.040, .039, .038, .037])])
    jd = D.jcurve(disc, [date(2027, 5, 6), date(2027, 11, 8), date(2028, 11, 6), date(2031, 11, 6)], [disc.df(d) for d in [date(2027, 5, 6), date(2027, 11, 8), date(2028, 11, 6), date(2031, 11, 6)]])
    fw = [(date(2026, 12, 15), 75.20), (date(2027, 3, 15), 74.10), (date(2027, 6, 15), 75.90), (date(2027, 12, 15), 78.40), (date(2028, 12, 15), 76.00)]
    for u in (.020, .060):
        ys, vs, arb = [], [], []
        for (d0, f0), (d1, f1) in zip(fw, fw[1:]):
            dt = (d1 - d0).days / 365
            r = math.log(disc.df(d0) / disc.df(d1)) / dt
            y = r + u - math.log(f1 / f0) / dt
            v = disc.df(d1) * f1 - disc.df(d0) * f0 * math.exp(u * dt)
            assert abs(v) > 1e-6
            ys.append(y)
            vs.append(v)
            arb.append(v > 0)
        s.add(cop, {"funding": jd, "forwards": [{"date": str(d), "price": p} for d, p in fw], "storage_cost": u}, {"convenience_yields": ys, "carry_values": vs, "arbitrage": arb},
              cls=A, verified=["analytic"], tags=["storage"], output_classes={"arbitrage": E})
        caught("commodity_d", f"storage cost ignored, u={u}", max(abs((math.log(disc.df(a) / disc.df(b)) / ((b - a).days / 365) - math.log(q / p) / ((b - a).days / 365)) - y) for ((a, p), (b, q)), y in zip(zip(fw, fw[1:]), ys)), 1e-10)
    s.add(cop, {"funding": jd, "forwards": [{"date": "2026-12-15", "price": 75.2}], "storage_cost": .02}, error="E_INPUT", cls=E, tags=["invalid"], description="at least two forwards")
    s.add(cop, {"funding": jd, "forwards": [{"date": str(d), "price": p} for d, p in fw], "storage_cost": -.01}, error="E_DOMAIN", cls=E, tags=["invalid"])
    note("commodity_d: seasonal curves reprice every quote; carry values kept at least 1e-6 from zero")
    write(s)


def main():
    D.MUTANTS.clear()
    cmdty_d()
    note(f"stage D D8: {len(D.MUTANTS)} wrong-convention checks, each caught")


if __name__ == "__main__":
    main()
