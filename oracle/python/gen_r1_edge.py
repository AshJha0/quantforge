"""R1: edge-case register cases (plan 11.2.2). Suite stage_d/edge_d.

Each case pins one register row in specifications/edge-case-register.md. Values come from exact rationals, mpmath, or
the own bond and curve replays; zero-yield bonds, negative-rate curves and negative or zero fixings are also re-priced
by outside_d.py in QuantLib. Near-zero vol and time use inputs where the Black price is intrinsic value to far below the
tolerance, so no case depends on how a language's erfc rounds deep in the tail.
"""
import math
from datetime import date, timedelta
from fractions import Fraction as Fr

import mpmath as mp

from qf_oracle.common import note
from qf_oracle.rates import Curve
import gen_stage_d as D
import gen_stage_d_w2 as W2
import gen_stage_d_w3 as W3
from gen_stage_d import A, QLV, R, S, write

G = "oracle/python/gen_r1_edge.py"
mp.mp.dps = 50


def black(cp, F, K, v, t, df):
    F, K, v, t, df = (mp.mpf(x) for x in (F, K, v, t, df))
    if v * mp.sqrt(t) == 0:
        return float(df * max(F - K, 0) if cp else df * max(K - F, 0))
    sd = v * mp.sqrt(t)
    d1 = (mp.log(F / K) + sd * sd / 2) / sd
    d2 = d1 - sd
    N = lambda x: mp.ncdf(x)  # noqa: E731
    return float(df * (F * N(d1) - K * N(d2)) if cp else df * (K * N(-d2) - F * N(-d1)))


def main():
    D.estr()
    s = S("edge_d", "edge-case-register.md")
    s.generator = G
    # E1 zero and negative rates: bond at a zero yield.
    for b in (W2.BONDS[0], W2.BONDS[2]):
        r = W2.price_yield(b, W2.SET, 0.0)
        s.add("bond.price.from_yield", {"bond": b, "settlement": str(W2.SET), "yield": 0.0}, r, cls=A, verified=[QLV, "analytic"], tags=["edge-E1", "zero-rate"])
    # E1: compounding over negative fixings, and over zero fixings.
    for conv, S0, E0, shift, tag in (("ESTR", date(2026, 12, 15), date(2027, 3, 15), -.0240, "negative-rate"), ("SOFR", date(2026, 11, 10), date(2027, 2, 10), None, "zero-rate")):
        fl = [(d, 0.0 if shift is None else round(v + shift, 6)) for d, v in D.fixings(conv, S0 - timedelta(20), E0)]
        for method, k in (("NONE", 0), ("OBSERVATION_SHIFT", 2), ("LOCKOUT", 2)):
            rr, _, _ = D.compound(conv, S0, E0, method, k, dict(fl))
            acc = Fr((E0 - S0).days, D.DEN[conv])
            s.add("rates.ois.compound_dated", {"convention": conv, "start": str(S0), "end": str(E0), "method": method, "shift_days": k,
                                                "fixings": [{"date": str(d), "rate": v} for d, v in fl]},
                  {"compounded_rate": float(rr), "accrual": float(acc), "interest": float(rr * acc)}, cls=A, verified=["exact-rational", QLV],
                  tags=["edge-E1", tag, method.lower()], limit=D.RATELIM)
    # E1: a curve with negative zero rates (discount factors above 1).
    a = D.AS_OF
    pil = [date(2027, 11, 8), date(2028, 11, 6), date(2031, 11, 6), date(2036, 11, 6)]
    zs = [-.0060, -.0045, -.0020, .0010]
    dfs = [math.exp(-z * (d - a).days / 365) for z, d in zip(zs, pil)]
    cv = Curve(a, pil, dfs)
    jc = D.jcurve(cv, pil, dfs)
    qd = [date(2027, 2, 26), date(2027, 11, 8), date(2029, 6, 29), date(2034, 12, 29)]
    s.add("rates.curve.discount", {"curve": jc, "dates": [str(d) for d in qd]},
          {"discount_factors": [cv.df(d) for d in qd], "zero_rates": [-math.log(cv.df(d)) / ((d - a).days / 365) for d in qd]},
          cls="interpolation", verified=["independent-replay", QLV], tags=["edge-E1", "negative-rate"])
    # E12 near-zero vol and time: Black-76 price equals discounted intrinsic to far below tolerance.
    for cp, F, K, v, t, tag in ((True, 100.0, 95.0, 1e-6, 1.0, "near-zero-vol"), (False, 100.0, 105.0, 1e-6, 1.0, "near-zero-vol"),
                                (True, 100.0, 90.0, .20, 1 / 365, "near-zero-time"), (False, 100.0, 110.0, .20, 1 / 365, "near-zero-time"),
                                (True, 100.0, 100.0, 1e-6, 1.0, "near-zero-vol-atm")):
        df = .97
        p = black(cp, F, K, v, t, df)
        s.add("vol.option.price", {"model": "BLACK_76", "option_type": "CALL" if cp else "PUT", "strike": K, "expiry_years": t, "forward": F, "discount_factor": df, "vol": v},
              {"price": p, "forward": F}, cls=A, verified=["mpmath-50"], tags=["edge-E12", tag])
    # E7 CPI index lag at month boundaries: settlement on the first and on the last day of a month.
    fix = {"2026-05": 320.580, "2026-06": 321.465, "2026-07": 321.910, "2026-08": 322.150, "2026-09": 322.880, "2026-10": 323.410}
    for setl in (date(2026, 11, 30), date(2026, 12, 1), date(2026, 12, 31)):
        b, ry, base_ref = W2.BONDS[0], .0185, 300.12345
        r = W2.price_yield(b, setl, ry)
        k = setl.year * 12 + setl.month - 1
        m3, m2 = W3.ms(k - 3), W3.ms(k - 2)
        rc = Fr(fix[m3]) + Fr(setl.day - 1, W3.dim(setl.year, setl.month)) * (Fr(fix[m2]) - Fr(fix[m3]))
        ir = rc / Fr(base_ref)
        s.add("infl.linker.price", {"bond": b, "settlement": str(setl), "real_yield": ry, "base_ref_cpi": base_ref, "cpi_fixings": [{"month": m, "value": v} for m, v in fix.items()]},
              {"ref_cpi": float(rc), "index_ratio": float(ir), "real_clean": r["clean"], "real_accrued": r["accrued"], "nominal_clean": r["clean"] * float(ir),
               "nominal_accrued": r["accrued"] * float(ir)}, cls=A, verified=["analytic", "exact-rational"], tags=["edge-E7", "month-boundary"])
    write(s)
    note(f"edge_d: {len(s.cases)} edge-case register cases")


if __name__ == "__main__":
    main()
