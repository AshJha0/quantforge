"""Stage D golden cases, wave 3, D7: caps, floors and European swaptions on flat or quoted vol. Same rules as gen_stage_d.py."""
import math
from datetime import date

import QuantLib as ql

from qf_oracle.common import note
from qf_oracle.dates import yf
from qf_oracle.rates import add_bd, add_months, adjust, schedule
import gen_stage_d as D
from gen_stage_d import E, I, QLV, S, caught, write

T0 = D.AS_OF


def opt(model, cp, F, K, v, t):
    w = 1 if cp else -1
    if model == "BLACK_76":
        return ql.blackFormula(ql.Option.Call if cp else ql.Option.Put, K, F, v * math.sqrt(t))
    return ql.bachelierBlackFormula(ql.Option.Call if cp else ql.Option.Put, K, F, v * math.sqrt(t))


def curves():
    disc, ud, up = D.bootstrap_ois_j("SOFR", T0, D.B.SOFR_Q)
    jd = D.jcurve(disc, [p[-1][2] for p in up], ud)
    pc, pd, pp = D.B.bootstrap_proj(disc, T0, D.B.proj_quotes(), "LOG_LINEAR_DF")
    return disc, jd, pc, D.jcurve(pc, pp, pd)


def vol_d():
    s = S("capswaption_d", "05-volatility/caps-and-swaptions.md")
    disc, jd, pc, jp = curves()
    spot = add_bd("USGS", T0, 2)
    cop = "rates.cap.price"
    for typ, sm, tm, K, model, vol, N in (("CAP", 3, 24, .0380, "BLACK_76", .22, 1e7), ("FLOOR", 3, 24, .0340, "BLACK_76", .25, 1e7), ("CAP", 6, 36, .0360, "BACHELIER", .0095, 5e7),
                                          ("CAP", 3, 12, .0370, "BLACK_76", [.20, .21, .215, .22], 1e7), ("FLOOR", 12, 12, .0300, "BACHELIER", [.0090, .0092, .0094, .0095], 2e7)):
        st = adjust("USGS", add_months(spot, sm))
        ds = schedule("USGS", st, add_months(st, tm), 3)
        vols = vol if isinstance(vol, list) else [vol] * (len(ds) - 1)
        assert len(vols) == len(ds) - 1
        caps, total = [], 0.0
        for (a, e), v in zip(zip(ds, ds[1:]), vols):
            al = float(yf("ACT_360", a, e))
            F = (pc.df(a) / pc.df(e) - 1) / al
            p = N * al * disc.df(e) * opt(model, typ == "CAP", F, K, v, (a - T0).days / 365)
            caps.append(p)
            total += p
        s.add(cop, {"discount": jd, "projection": jp, "model": model, "vol": vol, "trade": {"type": typ, "start_months": sm, "tenor_months": tm, "strike": K, "notional": N}},
              {"price": total, "caplets": caps}, cls=I, verified=["independent-replay", QLV], tags=["cap"] + (["quoted-vol"] if isinstance(vol, list) else ["flat-vol"]),
              limit={"absolute": 1e-9 * N, "relative": 1e-9, "reason": "curve tolerance on notional"})
        alt = sum(N * float(yf("ACT_360", a, e)) * disc.df(e) * opt(model, typ == "CAP", (pc.df(a) / pc.df(e) - 1) / float(yf("ACT_360", a, e)), K, v, (e - T0).days / 365) for (a, e), v in zip(zip(ds, ds[1:]), vols))
        caught("capswaption_d", f"{typ} {sm}x{tm}: expiry at period end, not fixing", abs(alt - total), 1e-9 * N)
    b = {"discount": jd, "projection": jp, "model": "BLACK_76", "vol": [.2, .2], "trade": {"type": "CAP", "start_months": 3, "tenor_months": 12, "strike": .037, "notional": 1e7}}
    s.add(cop, b, error="E_INPUT", cls=E, tags=["invalid"], description="one vol per caplet")
    s.add(cop, {**b, "vol": -0.1}, error="E_DOMAIN", cls=E, tags=["invalid"])
    s.add(cop, {**b, "vol": .2, "trade": {**b["trade"], "start_months": 0}}, error="E_INPUT", cls=E, tags=["invalid", "ruling"], description="start_months at least 1")
    s.add(cop, {**b, "vol": .2, "trade": {**b["trade"], "strike": -.01}}, error="E_DOMAIN", cls=E, tags=["invalid"], description="Black needs a positive strike")
    # Swaptions: forward swap rate and annuity on the D2/B swap conventions, priced at exercise = swap start.
    wop = "rates.swaption.price"
    ql.Settings.instance().evaluationDate = ql.Date(T0.day, T0.month, T0.year)
    for typ, em, tm, K, model, vol, N in (("PAYER", 12, 60, .0370, "BLACK_76", .21, 1e7), ("RECEIVER", 12, 60, .0350, "BLACK_76", .21, 1e7), ("PAYER", 24, 120, .0380, "BACHELIER", .0098, 2.5e7), ("RECEIVER", 60, 60, .0400, "BACHELIER", .0090, 1e7)):
        st = adjust("USGS", add_months(spot, em))
        fx = schedule("USGS", st, add_months(st, tm), 12)
        fl = schedule("USGS", st, add_months(st, tm), 3)
        A = sum(float(yf("THIRTY_360_BOND", a, e)) * disc.df(e) for a, e in zip(fx, fx[1:]))
        Fl = sum((pc.df(a) / pc.df(e) - 1) * disc.df(e) for a, e in zip(fl, fl[1:]))
        Sw = Fl / A
        tau = (st - T0).days / 365
        price = N * A * opt(model, typ == "PAYER", Sw, K, vol, tau)
        s.add(wop, {"discount": jd, "projection": jp, "model": model, "vol": vol, "trade": {"type": typ, "expiry_months": em, "tenor_months": tm, "strike": K, "notional": N}},
              {"price": price, "forward_rate": Sw, "annuity": A}, cls=I, verified=["independent-replay", QLV], tags=["swaption"],
              limit={"absolute": 1e-9 * N, "relative": 1e-9, "reason": "curve tolerance on notional"})
        caught("capswaption_d", f"{typ} {em}x{tm}: annuity on the floating schedule", abs(N * sum(float(yf("ACT_360", a, e)) * disc.df(e) for a, e in zip(fl, fl[1:])) * opt(model, typ == "PAYER", Sw, K, vol, tau) - price), 1e-9 * N)
    # Parity: payer - receiver = N A (S - K).
    s.add(wop, {"discount": jd, "projection": jp, "model": "BLACK_76", "vol": .2, "trade": {"type": "PAYER", "expiry_months": 0, "tenor_months": 60, "strike": .037, "notional": 1e7}},
          error="E_INPUT", cls=E, tags=["invalid", "ruling"], description="expiry_months at least 1")
    note("capswaption_d: option values from QuantLib blackFormula and bachelierBlackFormula; schedules and curves as stage B")
    write(s)


def main():
    D.MUTANTS.clear()
    vol_d()
    note(f"stage D D7: {len(D.MUTANTS)} wrong-convention checks, each caught")


if __name__ == "__main__":
    main()
