"""Stage E spec B, E8: CDS options (Black on the forward spread, front-end protection), Gaussian and Student-t copula
joint default, large-pool Vasicek (LHP) loss distribution and tranche expected loss.

CDS legs: mid-point default timing on a quarterly unadjusted schedule, ACT/360 premium and accrual on default, flat
continuous rate and hazard on ACT/365F (ruling E-B22). Copula and LHP values are closed forms in the bivariate normal or
bivariate t distribution, evaluated by mpmath quadrature at 50 digits; a fixed Gauss-Legendre integral over the factor
cross-checks every LHP value (ruling E-B25)."""
from datetime import date, timedelta

import mpmath as mp

from qf_oracle.common import note
from gen_stage_e_b import A, E, Q, R, MUTANTS, S, caught, f, write

mp.mp.dps = 50
D_ = date.fromisoformat


def add_m(d, m):
    y, mo = divmod(d.month - 1 + m, 12)
    return date(d.year + y, mo + 1, d.day)


def cds_legs(i, mutant=None):
    t0, ex, mat = D_(i["as_of"]), D_(i["expiry"]), D_(i["maturity"])
    r, h, Rr = mp.mpf(i["rate"]), mp.mpf(i["hazard_rate"]), mp.mpf(i["recovery"])
    tt = lambda d: mp.mpf((d - t0).days) / 365  # noqa: E731
    Sv = lambda d: mp.exp(-h * tt(d))  # noqa: E731
    Dv = lambda d: mp.exp(-r * tt(d))  # noqa: E731
    dates, k = [ex], 1
    while dates[-1] < mat:
        dates.append(min(add_m(ex, 3 * k), mat))
        k += 1
    prot, ann = 0, 0
    for a, b in zip(dates, dates[1:]):
        m = a + timedelta((b - a).days // 2)
        al = mp.mpf((b - a).days) / (360 if mutant != "act365" else 365)
        acc = mp.mpf((m - a).days) / 360
        prot += (1 - Rr) * Dv(m) * (Sv(a) - Sv(b))
        ann += al * Dv(b) * Sv(b) + (0 if mutant == "no-accrual" else acc * Dv(m) * (Sv(a) - Sv(b)))
    T = tt(ex) if mutant != "time-to-maturity" else tt(mat)
    fep = (1 - Rr) * (1 - Sv(ex)) * Dv(ex)
    return prot / ann, ann, T, fep


def black(call, F, K, sd):
    d1 = (mp.log(F / K) + sd * sd / 2) / sd
    d2 = d1 - sd
    return F * mp.ncdf(d1) - K * mp.ncdf(d2) if call else K * mp.ncdf(-d2) - F * mp.ncdf(-d1)


def cds_option(i, mutant=None):
    F, Aa, T, fep = cds_legs(i, mutant)
    N, K, v = mp.mpf(i["notional"]), mp.mpf(i["strike"]), mp.mpf(i["vol"])
    payer = i["type"] == "PAYER"
    p = N * Aa * black(payer, F, K, v * mp.sqrt(T))
    add = N * fep if (payer and (not i["knock_out"] or mutant == "fep-on-knockout")) else 0
    return {"price": f(p + add), "forward_spread": f(F), "risky_annuity": f(Aa), "front_end_protection": f(N * fep)}


# ---- copulas
def Phi2(a, b, rho):
    a, b, rho = mp.mpf(a), mp.mpf(b), mp.mpf(rho)
    s = mp.sqrt(1 - rho * rho)
    return mp.quad(lambda x: mp.npdf(x) * mp.ncdf((b - rho * x) / s), [-mp.inf, min(a, 0), a] if a > 0 else [-mp.inf, a])


def tcdf(x, nu):
    x, nu = mp.mpf(x), mp.mpf(nu)
    return 1 - mp.betainc(nu / 2, mp.mpf(1) / 2, 0, nu / (nu + x * x), regularized=True) / 2 if x > 0 else mp.betainc(nu / 2, mp.mpf(1) / 2, 0, nu / (nu + x * x), regularized=True) / 2


def tpdf(x, nu):
    x, nu = mp.mpf(x), mp.mpf(nu)
    return mp.gamma((nu + 1) / 2) / (mp.sqrt(nu * mp.pi) * mp.gamma(nu / 2)) * (1 + x * x / nu) ** (-(nu + 1) / 2)


def tinv(p, nu):
    return mp.findroot(lambda x: tcdf(x, nu) - p, mp.sqrt(nu) * mp.erfinv(2 * mp.mpf(p) - 1) * 0 + mp.npdf(0) * 0 + (mp.erfinv(2 * mp.mpf(p) - 1) * mp.sqrt(2)))


def T2(a, b, rho, nu):
    """Bivariate Student t CDF: Y | X = x is t_{nu+1} with location rho x and scale sqrt((nu + x^2)(1 - rho^2)/(nu + 1))."""
    a, b, rho, nu = map(mp.mpf, (a, b, rho, nu))
    g = lambda x: tpdf(x, nu) * tcdf((b - rho * x) / mp.sqrt((nu + x * x) * (1 - rho * rho) / (nu + 1)), nu + 1)  # noqa: E731
    return mp.quad(g, [-mp.inf, min(a, 0), a] if a > 0 else [-mp.inf, a])


def lhp_el_min(p, rho, k):
    """E[min(P(M), k)] for the Vasicek conditional default probability P(M), k in (0, 1]."""
    p, rho, k = map(mp.mpf, (p, rho, k))
    if k >= 1:
        return p
    c = mp.sqrt(2) * mp.erfinv(2 * p - 1)
    mstar = (c - mp.sqrt(1 - rho) * mp.sqrt(2) * mp.erfinv(2 * k - 1)) / mp.sqrt(rho)
    return p - (Phi2(c, mstar, mp.sqrt(rho)) - k * mp.ncdf(mstar))


def lhp_el_quad(p, rho, k, n=200):
    """Cross-check: fixed Gauss-Legendre (numpy nodes) on M in [-12, m*] and [m*, 12], split at the kink of min(P, k)."""
    import numpy as np
    p, rho, k = map(mp.mpf, (p, rho, k))
    c = mp.sqrt(2) * mp.erfinv(2 * p - 1)
    P = lambda M: mp.ncdf((c - mp.sqrt(rho) * M) / mp.sqrt(1 - rho))  # noqa: E731
    cuts = [mp.mpf(-12), mp.mpf(12)]
    if k < 1:
        ms = (c - mp.sqrt(1 - rho) * mp.sqrt(2) * mp.erfinv(2 * k - 1)) / mp.sqrt(rho)
        if -12 < ms < 12:
            cuts = [mp.mpf(-12), ms, mp.mpf(12)]
    xs, ws = np.polynomial.legendre.leggauss(n)
    tot = 0
    for lo, hi in zip(cuts, cuts[1:]):
        for x, w in zip(xs, ws):
            M = (hi - lo) / 2 * mp.mpf(x) + (hi + lo) / 2
            tot += (hi - lo) / 2 * mp.mpf(w) * mp.npdf(M) * min(P(M), k)
    return tot


def tranche(p, rho, Rr, a, d, mutant=None):
    lgd = 1 - mp.mpf(Rr)
    if mutant == "no-recovery-scaling":
        lgd = 1
    ka, kd = min(mp.mpf(a) / lgd, 1), min(mp.mpf(d) / lgd, 1)
    r_ = rho if mutant != "rho-as-sqrt" else mp.mpf(rho) ** 2
    return lgd * (lhp_el_min(p, r_, kd) - (lhp_el_min(p, r_, ka) if a > 0 else 0)) / (mp.mpf(d) - mp.mpf(a))


def credit_e():
    s = S("creditopt_e", "04-pricing/credit-options-and-copulas.md")
    op, iop = "credit.cdsoption.price", "credit.cdsoption.implied_vol"
    LIM = {"absolute": 1e-9 * 1e7, "relative": 1e-9, "reason": "1e-9 per unit notional, as stage D credit"}
    combos = []
    for (exm, tenor) in ((3, 60), (6, 60), (12, 48), (6, 36)):
        for (h, r) in ((.02, .035), (.01, .03), (.045, -.002)):
            for typ, K, v, ko in (("PAYER", None, .5, True), ("RECEIVER", None, .4, True), ("PAYER", None, .6, False)):
                combos.append((exm, tenor, h, r, typ, K, v, ko))
    for n, (exm, tenor, h, r, typ, K, v, ko) in enumerate(combos):
        ex = add_m(date(2026, 12, 20), exm)
        mat = add_m(ex, tenor)
        Kx = round(h * .6 * [1.0, .8, 1.25][n % 3], 4)
        i = {"as_of": "2026-11-06", "expiry": ex.isoformat(), "maturity": mat.isoformat(), "rate": r, "hazard_rate": h, "recovery": .4, "type": typ,
             "strike": Kx, "notional": 1e7, "vol": v, "knock_out": ko}
        out = cds_option(i)
        s.add(op, i, out, cls=R, verified=["independent-replay", "mpmath-50"], tags=["cdsoption", typ.lower(), "knock-out" if ko else "front-end-protection"],
              output_classes={"forward_spread": A, "risky_annuity": A}, limit=LIM)
        for m in ("no-accrual", "act365", "time-to-maturity") + (("fep-on-knockout",) if ko and typ == "PAYER" else ()):
            caught("creditopt_e", f"cdsoption {n}: {m}", abs(cds_option(i, m)["price"] - out["price"]), 1e-2 + 1e-9 * out["price"])
        if ko and n % 2 == 0:
            j = {k: v_ for k, v_ in i.items() if k != "vol"} | {"premium": out["price"]}
            s.add(iop, j, {"vol": v}, cls=R, verified=["independent-replay", "mpmath-50 root"], tags=["cdsoption", "implied"])
    b = {"as_of": "2026-11-06", "expiry": "2027-03-20", "maturity": "2032-03-20", "rate": .035, "hazard_rate": .02, "recovery": .4, "type": "PAYER", "strike": .012,
         "notional": 1e7, "vol": .5, "knock_out": True}
    for d, bad, code in (("expiry not after as_of", {"expiry": "2026-11-06"}, "E_INPUT"), ("maturity not after expiry", {"maturity": "2027-03-20"}, "E_INPUT"),
                         ("recovery outside [0, 1)", {"recovery": 1.0}, "E_DOMAIN"), ("hazard negative", {"hazard_rate": -.01}, "E_DOMAIN"),
                         ("strike not positive", {"strike": 0.0}, "E_DOMAIN"), ("vol negative", {"vol": -.1}, "E_DOMAIN")):
        s.add(op, {**b, **bad}, error=code, cls=E, tags=["invalid"], description=d)
    s.add(iop, {k: v_ for k, v_ in b.items() if k != "vol"} | {"premium": 1.0}, error="E_DOMAIN", cls=E, tags=["invalid"], description="premium below the zero-vol value: no implied vol")
    s.add(iop, {k: v_ for k, v_ in b.items() if k != "vol"} | {"premium": 5e4, "knock_out": False}, error="E_INPUT", cls=E, tags=["invalid", "ruling"],
          description="implied vol only for knock-out options (ruling E-B23)")
    # Gaussian and Student-t copula joint default
    jop = "credit.copula.joint_default"
    PL = {"absolute": 1e-12, "relative": 1e-9, "reason": "probabilities; quantiles carry about 1e-12 relative"}
    for p1, p2, rho, cop, nu in ((.02, .03, .3, "GAUSSIAN", None), (.05, .05, .6, "GAUSSIAN", None), (.01, .2, -.2, "GAUSSIAN", None), (.1, .15, .9, "GAUSSIAN", None),
                                 (.02, .03, .3, "STUDENT_T", 4), (.05, .05, .6, "STUDENT_T", 3), (.01, .2, -.2, "STUDENT_T", 10), (.1, .15, 0.0, "STUDENT_T", 5),
                                 (.02, .03, 0.0, "GAUSSIAN", None)):
        if cop == "GAUSSIAN":
            jp = Phi2(mp.sqrt(2) * mp.erfinv(2 * mp.mpf(p1) - 1), mp.sqrt(2) * mp.erfinv(2 * mp.mpf(p2) - 1), rho)
        else:
            jp = T2(tinv(p1, nu), tinv(p2, nu), rho, nu)
        i = {"copula": cop, "default_probabilities": [p1, p2], "correlation": rho} | ({"degrees_of_freedom": nu} if nu else {})
        s.add(jop, i, {"joint_default_probability": f(jp), "default_correlation": f((jp - mp.mpf(p1) * p2) / mp.sqrt(mp.mpf(p1) * (1 - mp.mpf(p1)) * p2 * (1 - mp.mpf(p2))))},
              cls=Q, verified=["mpmath-50 quad"], tags=["copula", cop.lower()], limit=PL)
        if rho:
            g2 = Phi2(mp.sqrt(2) * mp.erfinv(2 * mp.mpf(p1) - 1), mp.sqrt(2) * mp.erfinv(2 * mp.mpf(p2) - 1), rho)
            alt = g2 if cop == "STUDENT_T" else Phi2(mp.sqrt(2) * mp.erfinv(2 * mp.mpf(p1) - 1), mp.sqrt(2) * mp.erfinv(2 * mp.mpf(p2) - 1), mp.sqrt(abs(rho)) * mp.sign(rho))
            caught("creditopt_e", f"copula {cop} rho={rho}: {'Gaussian in place of t' if cop == 'STUDENT_T' else 'sqrt(rho) as pair correlation'}", abs(f(alt - jp)), 1e-12 + 1e-9 * f(jp))
        elif cop == "STUDENT_T":
            caught("creditopt_e", "copula t at rho 0 is not independence", abs(f(jp) - p1 * p2), 1e-12 + 1e-9 * f(jp))
    for d, bad, code in (("probability outside (0, 1)", {"copula": "GAUSSIAN", "default_probabilities": [0.0, .1], "correlation": .3}, "E_DOMAIN"),
                         ("correlation outside (-1, 1)", {"copula": "GAUSSIAN", "default_probabilities": [.1, .1], "correlation": 1.0}, "E_DOMAIN"),
                         ("t without degrees of freedom", {"copula": "STUDENT_T", "default_probabilities": [.1, .1], "correlation": .3}, "E_INPUT"),
                         ("degrees of freedom not above 0", {"copula": "STUDENT_T", "default_probabilities": [.1, .1], "correlation": .3, "degrees_of_freedom": 0}, "E_DOMAIN"),
                         ("unknown copula", {"copula": "CLAYTON", "default_probabilities": [.1, .1], "correlation": .3}, "E_SCHEMA")):
        s.add(jop, bad, error=code, cls=E, tags=["invalid"], description=d)
    # Large homogeneous pool (Vasicek)
    top, cop_ = "credit.lhp.tranche_loss", "credit.lhp.loss_cdf"
    TL = {"absolute": 1e-12, "relative": 1e-9, "reason": "1e-12 per unit tranche notional (1e-5 on 10m); quantiles carry about 1e-12 relative"}
    for p, rho, Rr in ((.05, .3, .4), (.02, .15, .4), (.1, .5, .35)):
        tr = [(0, .03), (.03, .07), (.07, .1), (.1, .15), (.15, .3), (.3, 1.0)]
        els = []
        for a, d in tr:
            el = tranche(p, rho, Rr, a, d)
            q_ = (1 - mp.mpf(Rr)) * (lhp_el_quad(p, rho, min(d / (1 - Rr), 1)) - (lhp_el_quad(p, rho, min(a / (1 - Rr), 1)) if a else 0)) / (d - a)
            assert abs(q_ - el) < 1e-11, f"LHP quadrature cross-check {abs(q_ - el)}"
            els.append(el * (d - a))
            s.add(top, {"default_probability": p, "correlation": rho, "recovery": Rr, "attachment": a, "detachment": d}, {"expected_loss_fraction": f(el)},
                  cls=Q, verified=["mpmath-50 closed form", "Gauss-Legendre 2x200 split at the kink"], tags=["lhp", "tranche"] + (["equity"] if a == 0 else []), limit=TL)
            for m in ("no-recovery-scaling", "rho-as-sqrt"):
                caught("creditopt_e", f"lhp p={p} {a}-{d}: {m}", abs(f(tranche(p, rho, Rr, a, d, m) - el)), 1e-12 + 1e-9 * f(el))
        assert abs(sum(els) - (1 - mp.mpf(Rr)) * p) < 1e-18, "tranches do not add up to the pool"
        xs = [.005, .01, .02, .05, .1, .2]
        c = mp.sqrt(2) * mp.erfinv(2 * mp.mpf(p) - 1)
        cdf = [mp.ncdf((mp.sqrt(1 - mp.mpf(rho)) * mp.sqrt(2) * mp.erfinv(2 * mp.mpf(x) / (1 - mp.mpf(Rr)) - 1) - c) / mp.sqrt(rho)) for x in xs]
        s.add(cop_, {"default_probability": p, "correlation": rho, "recovery": Rr, "losses": xs}, {"cdf": [f(v) for v in cdf]}, cls=Q, verified=["mpmath-50 closed form"],
              tags=["lhp", "cdf"], limit=PL)
    for d, bad, code in (("detachment not above attachment", {"attachment": .07, "detachment": .03}, "E_INPUT"), ("detachment above 1", {"attachment": .03, "detachment": 1.2}, "E_INPUT"),
                         ("correlation 0 (degenerate pool)", {"correlation": 0.0}, "E_DOMAIN"), ("probability 1", {"default_probability": 1.0}, "E_DOMAIN")):
        s.add(top, {"default_probability": .05, "correlation": .3, "recovery": .4, "attachment": .03, "detachment": .07, **bad}, error=code, cls=E, tags=["invalid"], description=d)
    s.add(cop_, {"default_probability": .05, "correlation": .3, "recovery": .4, "losses": [.7]}, error="E_DOMAIN", cls=E, tags=["invalid"], description="loss at or above 1 - recovery")
    note("creditopt_e: CDS options on mid-point legs; copulas and LHP by mpmath quadrature; LHP cross-checked by fixed Gauss-Legendre")
    write(s)


def e8():
    MUTANTS.clear()
    credit_e()
    note(f"stage E E8: {len(MUTANTS)} wrong-convention checks, each caught")


if __name__ == "__main__":
    e8()
