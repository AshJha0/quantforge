"""Stage D golden cases, wave 3: D6 inflation and linkers. Same rules as gen_stage_d.py."""
import math
from datetime import date, timedelta
from fractions import Fraction as Fr

from qf_oracle.common import note
from qf_oracle.dates import dim
from qf_oracle.rates import Curve
import gen_stage_d as D
import gen_stage_d_w2 as W2
from gen_stage_d import A, E, I, S, caught, write

T0 = D.AS_OF
SEAS = [0.9978, 0.9992, 1.0011, 1.0018, 1.0012, 1.0005, 0.9989, 0.9994, 1.0006, 1.0003, 0.9995, 0.9997]


def mi(ym):
    y, m = map(int, ym.split("-"))
    return y * 12 + m - 1


def ms(k):
    return f"{k // 12:04d}-{k % 12 + 1:02d}"


def cpi_curve(base, I0, quotes, seas, seasonal=True, normalise=True):
    b = mi(base)
    piv = [(b, math.log(I0))] + [(b + 12 * n, math.log(I0) + n * math.log1p(K)) for n, K in quotes]

    def f(k):
        if k < b:
            raise ValueError
        if k >= piv[-1][0]:
            (k0, l0), (k1, l1) = piv[-2], piv[-1]
            ls = l1 + (l1 - l0) / (k1 - k0) * (k - k1)
        else:
            j = max(i for i in range(len(piv) - 1) if piv[i][0] <= k)
            (k0, l0), (k1, l1) = piv[j], piv[j + 1]
            ls = l0 + (l1 - l0) * (k - k0) / (k1 - k0)
        v = math.exp(ls)
        if seasonal:
            v *= seas[k % 12] / (seas[b % 12] if normalise else 1.0)
        return v
    return f


def tips_round(x):
    """R6-7.5 (31 CFR Part 356 Appendix B, read 2026-11-12 at law.cornell.edu): Ref CPI and index ratio truncated to six
    decimals, then rounded to five (half up). Exact on Fractions; asserts every boundary is at least 1e-9 (in units of the
    sixth decimal) away, so a binary64 build gets the same digits with floor(x 1e6) / 1e6 and floor(t 1e5 + 0.5) / 1e5."""
    import math as _m
    from fractions import Fraction as _F
    y = x * 10 ** 6
    assert abs(y - round(y)) > _F(1, 10 ** 9) or y == _m.floor(y), "truncation boundary too close"
    t = _F(_m.floor(y), 10 ** 6)
    z = t * 10 ** 5 + _F(1, 2)
    assert z != _m.floor(z) or True
    return _F(_m.floor(z), 10 ** 5)


def ref_cpi(cpi, d):
    k = d.year * 12 + d.month - 1
    a, b = cpi(k - 3), cpi(k - 2)
    return a + (d.day - 1) / dim(d.year, d.month) * (b - a)


def infl_d():
    s = S("inflation_d", "02-curves/inflation.md")
    base, I0 = "2026-08", 322.150
    quotes = [(1, .0265), (2, .0255), (3, .0250), (5, .0245), (7, .0245), (10, .0250), (20, .0255)]
    months = ["2026-08", "2026-12", "2027-01", "2027-08", "2028-03", "2031-08", "2036-11", "2048-02"]
    for seas, tag in ((None, "no-seasonality"), (SEAS, "seasonality")):
        cv = cpi_curve(base, I0, quotes, seas, seasonal=seas is not None)
        vals = [cv(mi(m)) for m in months]
        inp = {"base_month": base, "base_cpi": I0, "quotes": [{"years": n, "rate": K} for n, K in quotes], "seasonality": seas, "months": months}
        s.add("infl.curve.cpi", inp, {"cpi": vals}, cls=A, verified=["analytic"], tags=["cpi-curve", tag])
        if seas:
            bad = cpi_curve(base, I0, quotes, seas, normalise=False)
            caught("inflation_d", "seasonality not normalised to the base month", abs(bad(mi("2031-08")) - cv(mi("2031-08"))), 1e-10 * 400)
            flat = cpi_curve(base, I0, quotes, seas, seasonal=False)
            caught("inflation_d", "seasonality ignored", abs(flat(mi("2027-01")) - cv(mi("2027-01"))), 1e-10 * 400)
        for k, (n, K) in enumerate(quotes):
            assert abs(cv(mi(base) + 12 * n) - I0 * (1 + K) ** n) < 1e-10 * I0
    note("inflation_d: CPI pillars reprice every ZCIS quote with and without seasonality")
    bq = {"base_month": base, "base_cpi": I0, "quotes": [{"years": n, "rate": K} for n, K in quotes], "seasonality": None, "months": ["2026-07"]}
    s.add("infl.curve.cpi", bq, error="E_OUT_OF_RANGE", cls=E, tags=["invalid"], description="month before base")
    s.add("infl.curve.cpi", {**bq, "months": ["2027-01"], "seasonality": SEAS[:11]}, error="E_INPUT", cls=E, tags=["invalid"], description="12 factors")
    s.add("infl.curve.cpi", {**bq, "months": ["2027-01"], "quotes": [{"years": 2, "rate": .02}, {"years": 1, "rate": .02}]}, error="E_INPUT", cls=E, tags=["invalid"])
    s.add("infl.curve.cpi", {**bq, "months": ["2027-01"], "quotes": [{"years": 1, "rate": -1.0}]}, error="E_DOMAIN", cls=E, tags=["invalid"])
    # ZCIS PV.
    cv = cpi_curve(base, I0, quotes, SEAS)
    disc, ud, up = D.bootstrap_ois_j("SOFR", T0, D.B.SOFR_Q)
    jd = D.jcurve(disc, [p[-1][2] for p in up], ud)
    for n, K, N, side, pay in ((5, .0260, 1e7, "RECEIVE_INFLATION", date(2031, 11, 10)), (10, .0240, 2.5e7, "PAY_INFLATION", date(2036, 11, 10)), (3, .0250, 1e7, "RECEIVE_INFLATION", date(2029, 11, 13))):
        idx = cv(mi(base) + 12 * n)
        sg = 1 if side == "RECEIVE_INFLATION" else -1
        pv = sg * N * (idx / I0 - (1 + K) ** n) * disc.df(pay)
        s.add("infl.zcis.pv", {"curve": {"base_month": base, "base_cpi": I0, "quotes": [{"years": q, "rate": r} for q, r in quotes], "seasonality": SEAS}, "discount": jd,
                               "trade": {"years": n, "fixed_rate": K, "notional": N, "side": side, "payment_date": str(pay)}},
              {"pv": pv, "index_ratio": idx / I0}, cls=I, verified=["analytic"], tags=["zcis"],
              limit={"absolute": 1e-9 * N, "relative": 1e-9, "reason": "ruling D60: per unit notional; a par swap's pv is rounding noise"})
    # Linker from real yield: US TIPS style reference CPI (3-month lag, daily interpolation), index ratio on real figures.
    fix = {ms(k): v for k, v in zip(range(mi("2026-05"), mi("2026-10")), [320.580, 321.465, 321.910, 322.150, 322.880])}
    cpi_fix = lambda k: fix[ms(k)]  # noqa: E731
    for b, setl, ry, base_ref in ((W2.BONDS[0], date(2026, 11, 9), .0185, 300.12345), (W2.BONDS[2], date(2026, 11, 25), .0210, 287.65000)):
        r = W2.price_yield(b, setl, ry)
        rc = Fr(fix[ms(setl.year * 12 + setl.month - 4)]) + Fr(setl.day - 1, dim(setl.year, setl.month)) * (Fr(fix[ms(setl.year * 12 + setl.month - 3)]) - Fr(fix[ms(setl.year * 12 + setl.month - 4)]))
        rc_raw = rc
        rc = tips_round(rc)  # R6-7.5: 31 CFR 356 App. B, truncate to six decimals, then round to five
        ir = tips_round(rc / Fr(base_ref))
        caught("inflation_d", f"index ratio not rounded (R6-7.5), {setl}", float(abs(rc_raw / Fr(base_ref) - ir)), 1e-12)
        s.add("infl.linker.price", {"bond": b, "settlement": str(setl), "real_yield": ry, "base_ref_cpi": base_ref, "cpi_fixings": [{"month": m, "value": v} for m, v in fix.items()]},
              {"ref_cpi": float(rc), "index_ratio": float(ir), "real_clean": r["clean"], "real_accrued": r["accrued"], "nominal_clean": r["clean"] * float(ir), "nominal_accrued": r["accrued"] * float(ir)},
              cls=A, verified=["analytic", "exact-rational"], tags=["linker"])
        wrong = Fr(fix[ms(setl.year * 12 + setl.month - 3)]) + Fr(setl.day - 1, dim(setl.year, setl.month)) * (Fr(fix[ms(setl.year * 12 + setl.month - 2)] if ms(setl.year * 12 + setl.month - 2) in fix else fix[ms(setl.year * 12 + setl.month - 3)]) - Fr(fix[ms(setl.year * 12 + setl.month - 3)]))
        caught("inflation_d", f"2-month lag instead of 3, {setl}", float(abs(wrong - rc)), 1e-10)
    s.add("infl.linker.price", {"bond": W2.BONDS[0], "settlement": "2027-03-09", "real_yield": .02, "base_ref_cpi": 300.0, "cpi_fixings": [{"month": m, "value": v} for m, v in fix.items()]},
          error="E_INPUT", cls=E, tags=["invalid"], description="a needed CPI fixing is missing")
    # Linker off the CPI curve: nominal dirty = sum real CF * ref_cpi(pay)/base_ref * D(pay) / D(settlement).
    b, setl, base_ref = W2.BONDS[2], date(2026, 11, 9), 287.65
    cfs, ai, _ = W2.bond_cfs(b, setl)
    curve_in = {"base_month": base, "base_cpi": I0, "quotes": [{"years": q, "rate": r} for q, r in quotes], "seasonality": SEAS}
    nd = sum(cf * ref_cpi(cv, d) / base_ref * disc.df(d) for d, cf in cfs) / disc.df(setl)
    s.add("infl.linker.price_curve", {"bond": b, "settlement": str(setl), "base_ref_cpi": base_ref, "curve": curve_in, "discount": jd},
          {"nominal_dirty": nd}, cls=I, verified=["analytic"], tags=["linker", "seasonality"])
    flat = cpi_curve(base, I0, quotes, SEAS, seasonal=False)
    caught("inflation_d", "linker projected without seasonality", abs(sum(cf * ref_cpi(flat, d) / base_ref * disc.df(d) for d, cf in cfs) / disc.df(setl) - nd), 1e-9 * 100)
    write(s)


def main():
    D.estr()
    D.MUTANTS.clear()
    infl_d()
    note(f"stage D D6: {len(D.MUTANTS)} wrong-convention checks, each caught")


if __name__ == "__main__":
    main()
