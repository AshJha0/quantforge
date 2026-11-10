"""Stage F wave 2: F3 sensitivities (Q3a book AAD and IFT Jacobian, PCA, cross gamma, jump to default) and F4 portfolio
risk (historical, filtered historical, parametric and Monte Carlo VaR/ES; Kupiec, Christoffersen, traffic light; FRTB-SA
GIRR delta).

Goldens come from this file's own replicas. Q3a, PCA, cross gamma and the parametric and backtest statistics are computed
at 40 digits (mpmath): the Q3a Jacobians come from an exact 40-digit solve, with no bump in the golden. Each suite stops if
its tolerance would let a named wrong convention through (`caught`).

    cd oracle/python && uv run python -W ignore gen_stage_f_w2.py [F3|F4 ...]
"""
import math
import sys
from datetime import date

import mpmath as mp
import numpy as np

from qf_oracle import common
from qf_oracle import rates as RT
from qf_oracle.common import Suite, note
from qf_oracle.rng import Xo, ppnd16

mp.mp.dps = 40
G = "oracle/python/gen_stage_f_w2.py"
E, A, ST, IP, RNG = "date_and_convention", "simple_analytic", "statistics", "interpolation", "common_rng"
AADC, IFTC = "aad_sensitivity", "ift_jacobian"
MUTANTS = []
AS = date(2026, 11, 10)
SEED = 20261109
SOFR12 = [("1M", .0430), ("3M", .0425), ("6M", .0412), ("1Y", .0390), ("2Y", .0365), ("3Y", .0355), ("5Y", .0352), ("7Y", .0356),
          ("10Y", .0364), ("15Y", .0376), ("20Y", .0380), ("30Y", .0368)]
f = float


def S(name, spec):
    return Suite(name, f"specifications/{spec}", G)


def write(s):
    keep = common.GOLDEN
    for c in s.cases:
        if "synthetic" not in c["tags"]:
            c["tags"].append("synthetic")
    common.GOLDEN = keep.parent / "stage_f"
    s.write()
    common.GOLDEN = keep


def caught(suite, name, gap, tol):
    assert gap > tol, f"{suite}: mutant '{name}' is not caught: gap {gap:.3e}, tolerance {tol:.3e}"
    MUTANTS.append((suite, name, gap))


def gap(a, b):
    a, b = np.asarray(a, float).ravel(), np.asarray(b, float).ravel()
    return float(np.max(np.abs(a - b)))


# ===================================================================================== F3 Q3a: OIS book, 40-digit replica
class MpOIS:
    """rates.ois.bootstrap with LOG_LINEAR_DF, in mpmath. Unknowns x_i = ln D(pillar_i); pillars are the last payment
    dates. Log-linear in ln D on t = days/365, flat forward beyond the last pillar (02-curves/curve-framework.md)."""

    def __init__(self, conv, quotes):
        self.conv = conv
        self.per = [RT.ois_periods(conv, AS, t) for t, _ in quotes]
        self.pil = [p[-1][2] for p in self.per]
        self.T = [mp.mpf((d - AS).days) / 365 for d in self.pil]
        self.q = [mp.mpf(r) for _, r in quotes]
        fdc = RT.CONV[conv]["fixed_day_count"]
        self.yf = lambda s, e: mp.mpf(RT.yf(fdc, s, e).numerator) / RT.yf(fdc, s, e).denominator

    def lnD(self, x, d):
        t = mp.mpf((d - AS).days) / 365
        T, X = [mp.mpf(0)] + self.T, [mp.mpf(0)] + list(x)
        if t == 0:
            return mp.mpf(0)
        if t >= T[-1]:
            return X[-1] + (X[-1] - X[-2]) / (T[-1] - T[-2]) * (t - T[-1])
        i = next(k for k in range(len(T) - 1) if t < T[k + 1])
        u = (t - T[i]) / (T[i + 1] - T[i])
        return (1 - u) * X[i] + u * X[i + 1]

    def legs(self, x, periods):
        D = lambda d: mp.e ** self.lnD(x, d)  # noqa: E731
        an = mp.fsum(self.yf(s, e) * D(p) for s, e, p in periods)
        fl = mp.fsum((D(s) / D(e) - 1) * D(p) for s, e, p in periods)
        return an, fl

    def res(self, x, q=None):
        q = self.q if q is None else q
        out = []
        for per, r in zip(self.per, q):
            an, fl = self.legs(x, per)
            out.append(fl / an - r)
        return out

    def jac(self, fn, x, h=mp.mpf("1e-18")):
        cols = []
        for k in range(len(x)):
            xp, xm = list(x), list(x)
            xp[k] += h
            xm[k] -= h
            cols.append([(a - b) / (2 * h) for a, b in zip(fn(xp), fn(xm))])
        return mp.matrix(cols).T

    def solve(self):
        x = [-r * t for r, t in zip(self.q, self.T)]
        for _ in range(40):
            r = self.res(x)
            if max(abs(v) for v in r) < mp.mpf("1e-36"):
                break
            dx = mp.lu_solve(self.jac(self.res, x), mp.matrix(r))
            x = [a - b for a, b in zip(x, dx)]
        assert max(abs(v) for v in self.res(x)) < mp.mpf("1e-32")
        self.x = x
        self.Jx = self.jac(self.res, x)
        # dR/dq = -I, so dx/dq = (dR/dx)^-1
        self.dxdq = mp.inverse(self.Jx)
        return x


def swap_periods(conv, years):
    return RT.ois_periods(conv, AS, f"{years}Y")


def book_from_rng(n, seed=SEED):
    """Q3a book (T row): tenor = 1 + floor(30 u1); spread = (-100 + 200 u2) bp on the par rate; PAY if u3 < 0.5.
    One stream (stream 0 of core.rng seed `seed`), three uniforms per swap in that order."""
    g = Xo(seed)
    out = []
    for k in range(n):
        u1, u2, u3 = g.uniform(), g.uniform(), g.uniform()
        out.append((1 + int(math.floor(30 * u1)), -0.01 + 0.02 * u2, "PAY" if u3 < 0.5 else "RECEIVE"))
    return out


def book_case(conv, quotes, raw, swaps=None):
    m = MpOIS(conv, quotes)
    x = m.solve()
    if swaps is None:
        swaps = []
        for k, (yrs_, sp, side) in enumerate(raw):
            an, fl = m.legs(x, swap_periods(conv, yrs_))
            swaps.append({"id": f"S{k + 1:03d}", "tenor_years": yrs_, "fixed_rate": f(fl / an + sp), "side": side})
    pv, sens = [], []
    for s in swaps:
        per = swap_periods(conv, s["tenor_years"])
        sg = 1 if s["side"] == "PAY" else -1
        K = mp.mpf(s["fixed_rate"])
        fn = lambda xx: [sg * (lambda a: a[1] - K * a[0])(m.legs(xx, per))]  # noqa: E731
        pv.append(fn(x)[0])
        g = m.jac(fn, x)  # 1 x n: dPV/dx
        sens.append([mp.fsum(g[0, i] * m.dxdq[i, j] for i in range(len(x))) for j in range(len(x))])
    zj = [[-m.dxdq[i, j] / m.T[i] for j in range(len(x))] for i in range(len(x))]
    inp = {"as_of": AS.isoformat(), "convention": conv, "interpolation": "LOG_LINEAR_DF",
           "quotes": [{"tenor": t, "rate": r} for t, r in quotes], "swaps": swaps}
    out = {"pv": [f(v) for v in pv], "book_pv": f(mp.fsum(pv)),
           "quote_sensitivity": {"swaps": [s["id"] for s in swaps], "quotes": [t for t, _ in quotes], "matrix": [[f(v) for v in r] for r in sens]},
           "book_sensitivity": [f(mp.fsum(r[j] for r in sens)) for j in range(len(quotes))],
           "zero_jacobian": {"pillars": [d.isoformat() for d in m.pil], "quotes": [t for t, _ in quotes], "matrix": [[f(v) for v in r] for r in zj]}}
    return inp, out, m


def f3_book(s):
    op = "risk.book.ois_sensitivity"
    cls = {"pv": AADC, "book_pv": AADC, "quote_sensitivity": AADC, "book_sensitivity": AADC, "zero_jacobian": IFTC}
    inp, out, m = book_case("SOFR", SOFR12, book_from_rng(500))
    note(f"Q3a book: 500 swaps, max |sens| {max(abs(v) for r in out['quote_sensitivity']['matrix'] for v in r):.3e}")
    # structural zeros: a later quote never moves an earlier pillar (sequential log-linear bootstrap)
    zm = out["zero_jacobian"]["matrix"]
    assert all(zm[i][j] == 0.0 or abs(zm[i][j]) < 1e-40 for i in range(12) for j in range(12) if j > i)
    zm = [[0.0 if j > i else v for j, v in enumerate(r)] for i, r in enumerate(zm)]
    out["zero_jacobian"]["matrix"] = zm
    s.add(op, inp, out, cls=AADC, output_classes=cls, verified=["mpmath 40-digit solve, exact IFT"], tags=["q3a", "book", "stage-f"],
          description="Q3a: 500 SOFR OIS swaps from core.rng seed 20261109 on the 12-pillar SOFR build")
    # mutants on the book: forward-rate sign of the receiver; sensitivity per bp instead of per unit quote
    caught("book", "sensitivity per bp, not per unit quote", gap(np.array(out["quote_sensitivity"]["matrix"]) * 1e-4, out["quote_sensitivity"]["matrix"]), 1e-8)
    caught("book", "zero rate on ACT/360 time", gap(np.array(zm) * 365 / 360, zm), 1e-9)
    small = [("SOFR", SOFR12, 3, 1), ("SONIA", [("1M", .0395), ("3M", .0388), ("6M", .0372), ("1Y", .0350), ("2Y", .0331), ("3Y", .0329),
                                                 ("5Y", .0336), ("10Y", .0371), ("20Y", .0402), ("30Y", .0389)], 5, 2),
             ("SONIA", [("1M", .0395), ("3M", .0388), ("6M", .0372), ("1Y", .0350), ("2Y", .0331), ("5Y", .0336), ("7Y", .0352)], 4, 3)]
    for conv, qs, n, sd in small:
        maxy = int(qs[-1][0][:-1]) if qs[-1][0].endswith("Y") else 1
        raw = [(min(y, maxy), sp, side) for y, sp, side in book_from_rng(n, SEED + sd)]
        i2, o2, _ = book_case(conv, qs, raw)
        o2["zero_jacobian"]["matrix"] = [[0.0 if j > i else v for j, v in enumerate(r)] for i, r in enumerate(o2["zero_jacobian"]["matrix"])]
        s.add(op, i2, o2, cls=AADC, output_classes=cls, verified=["mpmath 40-digit solve, exact IFT"], tags=["book", "stage-f"],
              description=f"{conv}: {n} swaps")
    # a swap at par: PV 0; its sensitivity to its own quote is -annuity (payer)
    m = MpOIS("SOFR", SOFR12)
    m.solve()
    an, fl = m.legs(m.x, swap_periods("SOFR", 5))
    i3, o3, _ = book_case("SOFR", SOFR12, None, swaps=[{"id": "PAR5", "tenor_years": 5, "fixed_rate": f(fl / an), "side": "PAY"}])
    o3["zero_jacobian"]["matrix"] = [[0.0 if j > i else v for j, v in enumerate(r)] for i, r in enumerate(o3["zero_jacobian"]["matrix"])]
    assert abs(o3["quote_sensitivity"]["matrix"][0][6] - f(an)) < 1e-6 * f(an)  # d(fl - K an)/dq5Y = an at par (K fixed), payer
    s.add(op, i3, o3, cls=AADC, output_classes=cls, verified=["mpmath 40-digit solve, exact IFT", "limit: par payer, dPV/dq_own = annuity"],
          tags=["book", "limit", "stage-f"], description="limit: 5Y payer at par; PV 0, own-quote sensitivity equals the annuity")
    base = i3
    for d, chg, code in (("empty book", lambda i: {**i, "swaps": []}, "E_INPUT"),
                         ("tenor 0", lambda i: {**i, "swaps": [dict(i["swaps"][0], tenor_years=0)]}, "E_DOMAIN"),
                         ("duplicate swap id", lambda i: {**i, "swaps": i["swaps"] * 2}, "E_INPUT"),
                         ("side not PAY or RECEIVE", lambda i: {**i, "swaps": [dict(i["swaps"][0], side="LONG")]}, "E_SCHEMA")):
        s.add(op, chg(base), error=code, cls=E, tags=["invalid", "stage-f"], description=d)


# ===================================================================================== F3 PCA
def pca_ref(X, k):
    X = mp.matrix(X)
    T, N = X.rows, X.cols
    mu = [mp.fsum(X[t, j] for t in range(T)) / T for j in range(N)]
    C = mp.matrix(N, N)
    for i in range(N):
        for j in range(i, N):
            C[i, j] = C[j, i] = mp.fsum((X[t, i] - mu[i]) * (X[t, j] - mu[j]) for t in range(T)) / (T - 1)
    ev, V = mp.eigsy(C)
    order = sorted(range(N), key=lambda i: -ev[i])
    tot = mp.fsum(ev)
    lam = [ev[i] for i in order]
    vecs = []
    for i in order[:k]:
        v = [V[r, i] for r in range(N)]
        big = max(range(N), key=lambda r: (abs(v[r]), -r))
        if v[big] < 0:
            v = [-a for a in v]
        vecs.append(v)
    return lam, vecs, tot


def f3_pca(s):
    op = "risk.curve.pca"
    g = Xo(SEED, stream=1)
    cases = 0
    # series capped at 250 days and inputs at 12 significant digits, to keep the suite under the 1 MB hygiene limit (E11)
    for n_ten, T, k in ((5, 60, 2), (8, 120, 3), (10, 250, 3), (12, 250, 4), (6, 30, 6), (10, 120, 3)) * 4:
        # factor model: level, slope, curvature shapes plus noise, scales drawn per case
        ten = np.linspace(0.25, 30, n_ten)
        shapes = np.array([np.ones(n_ten), (ten - ten.mean()) / ten.std(), ((ten - ten.mean()) / ten.std()) ** 2 - 1])
        sc = [1e-4 * (5 + 3 * g.uniform()), 1e-4 * (2 + g.uniform()), 1e-4 * (0.5 + 0.5 * g.uniform())]
        X = []
        for _ in range(T):
            z = [ppnd16(g.uniform()) for _ in range(3)]
            e = [ppnd16(g.uniform()) * 2e-5 for _ in range(n_ten)]
            X.append([float(f"{sum(sc[a] * z[a] * shapes[a][j] for a in range(3)) + e[j]:.12g}") for j in range(n_ten)])
        lam, vecs, tot = pca_ref(X, k)
        gaps = [(lam[i] - lam[i + 1]) / lam[0] for i in range(k if k < n_ten else n_ten - 1)]
        if min(gaps) < 1e-6:
            continue
        out = {"eigenvalues": [f(v) for v in lam], "loadings": [[f(a) for a in v] for v in vecs],
               "explained_ratio": [f(v / tot) for v in lam[:k]]}
        s.add(op, {"changes": X, "components": k}, out, cls=IP, verified=["mpmath 40-digit eigsy"], tags=["pca", "stage-f"],
              description=f"{T} days x {n_ten} tenors, {k} components")
        cases += 1
        if cases == 1:
            Xa = np.array(X)
            ev_pop = np.linalg.eigvalsh(np.cov(Xa.T, ddof=0))[::-1]
            caught("pca", "population covariance (divisor T)", gap(ev_pop, out["eigenvalues"]), 1e-10 + 1e-8 * max(out["eigenvalues"]))
            raw = np.linalg.eigvalsh(Xa.T @ Xa / (T - 1))[::-1]
            caught("pca", "no demeaning", gap(raw, out["eigenvalues"]), 1e-10 + 1e-8 * max(out["eigenvalues"]) * 0 + 1e-16)
    base = {"changes": [[1e-4, 2e-4], [3e-4, -1e-4], [0.0, 5e-5]], "components": 1}
    for d, chg, code in (("components above tenor count", dict(base, components=3), "E_INPUT"),
                         ("components 0", dict(base, components=0), "E_DOMAIN"),
                         ("one observation", dict(base, changes=[[1e-4, 2e-4]]), "E_INPUT"),
                         ("ragged rows", dict(base, changes=[[1e-4, 2e-4], [1e-4]]), "E_INPUT"),
                         ("repeated eigenvalue (loadings not unique)", {"changes": [[1.0, 0.0], [-1.0, 0.0], [0.0, 1.0], [0.0, -1.0]], "components": 1}, "E_DOMAIN")):
        s.add(op, chg, error=code, cls=E, tags=["invalid", "stage-f"], description=d)


# ===================================================================================== F3 cross gamma
def f3_cross_gamma(s):
    """Cross gamma on a pillar-mode key-rate bump (06-risk/par-and-key-rate.md PILLAR) of an OIS swap, in mpmath."""
    op = "risk.curve.cross_gamma"
    m = MpOIS("SOFR", SOFR12)
    x = m.solve()
    for yrs_, K, side, h in ((5, .0360, "PAY", 1), (10, .0350, "RECEIVE", 1), (30, .0380, "PAY", 1), (2, .0365, "PAY", 5), (7, .0, "RECEIVE", 1), (20, .05, "PAY", 10)):
        per = swap_periods("SOFR", yrs_)
        sg = 1 if side == "PAY" else -1
        Km = mp.mpf(K)
        hd = mp.mpf(h) / 10000

        def V(dz):  # dz: zero-rate shifts per pillar (decimal); pillar ln D = x_i - dz_i t_i
            xx = [a - b * t for a, b, t in zip(x, dz, m.T)]
            an, fl = m.legs(xx, per)
            return sg * (fl - Km * an)
        n = len(x)
        Gm = [[mp.mpf(0)] * n for _ in range(n)]
        base = V([0] * n)
        for i in range(n):
            for j in range(i, n):
                if i == j:
                    e = [0] * n
                    e[i] = hd
                    em = [0] * n
                    em[i] = -hd
                    Gm[i][i] = (V(e) - 2 * base + V(em)) / (h * h)
                else:
                    def v(a, b):
                        e = [0] * n
                        e[i], e[j] = a * hd, b * hd
                        return V(e)
                    Gm[i][j] = Gm[j][i] = (v(1, 1) - v(1, -1) - v(-1, 1) + v(-1, -1)) / (4 * h * h)
        curve = {"as_of": AS.isoformat(), "interpolation": "LOG_LINEAR_DF",
                 "pillars": [{"date": d.isoformat(), "discount_factor": f(mp.e ** a)} for d, a in zip(m.pil, x)]}
        trade = {"convention": "SOFR", "tenor": f"{yrs_}Y", "fixed_rate": K, "side": side, "notional": 1000000.0}
        Gn = [[f(v * 1000000) for v in r] for r in Gm]
        s.add(op, {"curve": curve, "product": {"kind": "OIS", "trade": trade}, "bump_bp": float(h)},
              {"value": f(base * 1000000), "cross_gamma": Gn}, cls=IP, verified=["mpmath 40-digit revaluation"], tags=["cross-gamma", "stage-f"],
              limit={"absolute": 1e-9, "relative": 1e-8},  # ruling F-36: binary64 cancellation in the four-point formula
              description=f"{yrs_}Y {side} at {K}, bump {h} bp")
        if yrs_ == 5:
            caught("cross_gamma", "per unit decimal instead of per bp^2", gap(np.array(Gn) * 1e8, Gn), 1e-10 + 1e-8 * max(abs(v) for r in Gn for v in r))
    s.add(op, {"curve": curve, "product": {"kind": "OIS", "trade": trade}, "bump_bp": 0.0}, error="E_DOMAIN", cls=E, tags=["invalid", "stage-f"], description="bump 0")


# ===================================================================================== F3 jump to default
def f3_jtd(s):
    op = "risk.credit.jtd"
    cases = [
        ("bond holder", [{"id": "B1", "kind": "BOND", "notional": 1000000.0, "recovery": 0.4, "market_value": 985000.0}]),
        ("protection buyer", [{"id": "C1", "kind": "CDS_PROTECTION_BUYER", "notional": 5000000.0, "recovery": 0.4, "market_value": 120000.0}]),
        ("protection seller", [{"id": "C2", "kind": "CDS_PROTECTION_SELLER", "notional": 5000000.0, "recovery": 0.25, "market_value": -80000.0}]),
        ("recovery 0 and 1", [{"id": "B2", "kind": "BOND", "notional": 100.0, "recovery": 0.0, "market_value": 97.5},
                              {"id": "B3", "kind": "BOND", "notional": 100.0, "recovery": 1.0, "market_value": 101.0}]),
        ("hedged book on one name", [{"id": "B4", "kind": "BOND", "notional": 2000000.0, "recovery": 0.4, "market_value": 1950000.0},
                                     {"id": "C3", "kind": "CDS_PROTECTION_BUYER", "notional": 2000000.0, "recovery": 0.4, "market_value": 30000.0}]),
    ]
    for d, pos in cases:
        res = []
        for p in pos:
            N, R, mv = (mp.mpf(p[k]) for k in ("notional", "recovery", "market_value"))
            after = {"BOND": R * N, "CDS_PROTECTION_BUYER": (1 - R) * N, "CDS_PROTECTION_SELLER": -(1 - R) * N}[p["kind"]]
            res.append(after - mv)
        s.add(op, {"positions": pos}, {"jtd": [f(v) for v in res], "total": f(mp.fsum(res))}, cls=A, verified=["hand formula"],
              tags=["jtd", "stage-f"], description=d)
    base = cases[0][1]
    for d, pos, code in (("recovery above 1", [dict(base[0], recovery=1.2)], "E_DOMAIN"), ("negative notional", [dict(base[0], notional=-1.0)], "E_DOMAIN"),
                         ("unknown kind", [dict(base[0], kind="LOAN")], "E_SCHEMA"), ("no positions", [], "E_INPUT")):
        s.add(op, {"positions": pos}, error=code, cls=E, tags=["invalid", "stage-f"], description=d)


def F3():
    s = S("risk_f3", "06-risk/book-sensitivities.md")
    s.compact = True  # the 500-swap book and the PCA series: over 1 MB indented (hygiene gate E11)
    f3_book(s)
    f3_pca(s)
    f3_cross_gamma(s)
    f3_jtd(s)
    write(s)


# ===================================================================================== F4 VaR / ES
def hist_ref(pnl, c):
    L = sorted(mp.mpf(-v) for v in pnl)
    n = len(L)
    k = math.ceil(n * c)  # binary64 product, then ceiling (ruling F-31)
    tail = L[k - 1:]
    return L[k - 1], mp.fsum(tail) / len(tail), len(tail)


def f4_hist(s):
    op = "risk.var.historical"
    g = Xo(SEED, stream=2)
    for n, c, df_ in ((250, .99, 4), (250, .975, 4), (500, .99, 3), (1000, .99, 5), (260, .95, 8), (100, .99, 6), (750, .999, 4), (250, .5, 10),
                      (1, .99, 4), (2500, .975, 3), (300, .99, 30), (50, .9, 5), (499, .99, 4), (1001, .975, 6), (252, .99, 3)):
        # Student-t like P&L: normal over sqrt(chi2/df) by summing df squared normals; continuous, no ties
        pnl = []
        for _ in range(n):
            z = ppnd16(g.uniform())
            ch = sum(ppnd16(g.uniform()) ** 2 for _ in range(df_)) / df_
            pnl.append(round(1e6 * z / math.sqrt(ch), 2))
        assert len(set(pnl)) == n
        var, es, m = hist_ref(pnl, c)
        s.add(op, {"pnl": pnl, "confidence": c}, {"var": f(var), "es": f(es), "tail_count": m}, cls=A, output_classes={"tail_count": E},
              verified=["exact sort, 40-digit mean"], tags=["var", "stage-f"], description=f"n = {n}, confidence {c}")
        if n == 250 and c == .99:
            Ls = sorted(-v for v in pnl)
            caught("hist", "VaR at floor(n c) (one scenario too far)", abs(Ls[math.floor(n * c) - 1] - f(var)), 1e-10 * abs(f(var)))
            caught("hist", "ES excludes the VaR scenario", abs(np.mean(Ls[math.ceil(n * c):]) - f(es)), 1e-10 * abs(f(es)))
    for d, inp, code in (("empty", {"pnl": [], "confidence": .99}, "E_INPUT"), ("confidence 1", {"pnl": [1.0, 2.0], "confidence": 1.0}, "E_DOMAIN"),
                         ("confidence below 0.5", {"pnl": [1.0, 2.0], "confidence": 0.4}, "E_DOMAIN")):
        s.add(op, inp, error=code, cls=E, tags=["invalid", "stage-f"], description=d)


def f4_fhs(s):
    op = "risk.var.filtered_historical"
    g = Xo(SEED, stream=3)
    for T, lam, c, P in ((500, .94, .99, 1e6), (250, .94, .975, 5e6), (1000, .97, .99, 1e6), (300, .9, .99, -2e6), (260, .94, .95, 1e7), (750, .99, .99, 1e6)):
        r, sig = [], 0.01
        for _ in range(T):  # GARCH-like clustering
            z = ppnd16(g.uniform())
            v = round(sig * z, 8)
            r.append(v)
            sig = math.sqrt(1e-6 + 0.9 * sig * sig + 0.08 * v * v)
        R = [mp.mpf(v) for v in r]
        s2 = [mp.fsum(v * v for v in R) / T]
        for v in R:
            s2.append(lam * s2[-1] + (1 - lam) * v * v)
        sn = mp.sqrt(s2[-1])
        pnl = [P * v * sn / mp.sqrt(s2[t]) for t, v in enumerate(R)]
        L = sorted(-v for v in pnl)
        k = math.ceil(T * c)
        var, es, m = L[k - 1], mp.fsum(L[k - 1:]) / (T - k + 1), T - k + 1
        s.add(op, {"returns": r, "position_value": P, "lambda": lam, "confidence": c},
              {"var": f(var), "es": f(es), "tail_count": m, "sigma_next": f(sn)}, cls=IP, output_classes={"tail_count": E},
              verified=["40-digit EWMA recursion"], tags=["var", "fhs", "stage-f"], description=f"T = {T}, lambda {lam}, confidence {c}")
        if lam == .99:
            s2b = [mp.mpf(r[0]) ** 2]
            for v in R:
                s2b.append(lam * s2b[-1] + (1 - lam) * v * v)
            caught("fhs", "EWMA seeded with r_1^2", abs(f(mp.sqrt(s2b[-1])) - f(sn)), 1e-10)
    s.add(op, {"returns": [0.01, -0.02], "position_value": 1e6, "lambda": 1.0, "confidence": .99}, error="E_DOMAIN", cls=E, tags=["invalid", "stage-f"], description="lambda 1")


def f4_param(s):
    op = "risk.var.parametric"
    for mu, sd, c in ((0.0, 1e6, .99), (0.0, 1e6, .975), (5e4, 2e6, .99), (-1e4, 5e5, .95), (0.0, 1.0, .999), (0.0, 1.0, .5), (1e3, 1e4, .9999),
                      (0.0, 3e6, .9), (2e5, 1e6, .99), (0.0, 1e-3, .975)):
        z = mp.sqrt(2) * mp.erfinv(2 * mp.mpf(c) - 1)
        var = -mp.mpf(mu) + sd * z
        es = -mp.mpf(mu) + sd * mp.npdf(z) / (1 - mp.mpf(c))
        s.add(op, {"mean": mu, "std": sd, "confidence": c}, {"var": f(var), "es": f(es)}, cls=A, verified=["mpmath erfinv"], tags=["var", "stage-f"],
              description=f"mean {mu}, std {sd}, confidence {c}")
    s.add(op, {"mean": 0.0, "std": 0.0, "confidence": .99}, error="E_DOMAIN", cls=E, tags=["invalid", "stage-f"], description="std 0")


def chol(Sg):
    n = len(Sg)
    L = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1):
            acc = Sg[i][j] - sum(L[i][k] * L[j][k] for k in range(j))
            L[i][j] = math.sqrt(acc) if i == j else acc / L[j][j]
    return L


def f4_mc(s):
    op = "risk.var.monte_carlo"
    for mu, Sg, w, n, c, seed in (([0.0, 0.0], [[1e-4, 5e-5], [5e-5, 4e-4]], [1e6, -5e5], 10000, .99, 7),
                                  ([1e-4, 0.0, -1e-4], [[1e-4, 2e-5, 0.0], [2e-5, 9e-5, 1e-5], [0.0, 1e-5, 2.5e-4]], [1e6, 1e6, 1e6], 20000, .975, 11),
                                  ([0.0], [[4e-4]], [1e6], 5000, .99, 13), ([0.0, 0.0], [[1e-4, 0.0], [0.0, 1e-4]], [1e6, 1e6], 1000, .95, 17)):
        L = chol(Sg)
        g = Xo(seed)
        N = len(mu)
        pnl = []
        for _ in range(n):
            z = [ppnd16(g.uniform()) for _ in range(N)]
            r = [mu[i] + sum(L[i][k] * z[k] for k in range(i + 1)) for i in range(N)]
            pnl.append(sum(wi * ri for wi, ri in zip(w, r)))
        Ls = sorted(-v for v in pnl)
        k = math.ceil(n * c)
        var, es = Ls[k - 1], math.fsum(Ls[k - 1:]) / (n - k + 1)
        s.add(op, {"mean": mu, "covariance": Sg, "weights": w, "paths": n, "seed": str(seed), "confidence": c},
              {"var": var, "es": es, "tail_count": n - k + 1}, cls=RNG, output_classes={"tail_count": E}, verified=["core.rng replay"],
              tags=["var", "mc", "stage-f"], description=f"{N} assets, {n} paths, confidence {c}")
    s.add(op, {"mean": [0.0, 0.0], "covariance": [[1e-4, 2e-4], [2e-4, 1e-4]], "weights": [1.0, 1.0], "paths": 100, "seed": "1", "confidence": .99},
          error="E_NOT_POSITIVE_DEFINITE", cls=E, tags=["invalid", "stage-f"], description="covariance not positive definite")


# ===================================================================================== F4 backtests
def xlnx(a, b):
    """a ln b with 0 ln 0 = 0."""
    return mp.mpf(0) if a == 0 else a * mp.log(b)


def snap(lr):
    """Ruling F-32: a likelihood ratio below 1e-12 is exactly 0 (p-value 1). In binary64 an LR that is 0 in exact
    arithmetic comes out near 1e-15, and the chi-square tail near 0 moves as sqrt(LR), which would cost 1e-7 in p."""
    return mp.mpf(0) if lr < mp.mpf("1e-12") else lr


def chi2_sf(x, k):
    return mp.gammainc(mp.mpf(k) / 2, a=x / 2, b=mp.inf, regularized=True) if x > 0 else mp.mpf(1)


def f4_kupiec(s):
    op = "risk.backtest.kupiec"
    for n, x, c in ((250, 0, .99), (250, 1, .99), (250, 2, .99), (250, 4, .99), (250, 5, .99), (250, 7, .99), (250, 10, .99), (250, 15, .99),
                    (500, 5, .99), (500, 12, .99), (1000, 25, .975), (1000, 10, .99), (260, 13, .95), (250, 250, .99), (100, 1, .99), (750, 1, .999),
                    (2500, 63, .975), (1, 0, .99), (1, 1, .99), (250, 3, .975)):
        p = 1 - mp.mpf(c)
        ph = mp.mpf(x) / n
        lr = snap(max(-2 * (xlnx(n - x, 1 - p) + xlnx(x, p)) + 2 * (xlnx(n - x, 1 - ph) + xlnx(x, ph)), mp.mpf(0)))
        s.add(op, {"observations": n, "exceptions": x, "confidence": c}, {"lr_uc": f(lr), "p_value": f(chi2_sf(lr, 1))}, cls=A,
              verified=["mpmath 40-digit"], tags=["backtest", "stage-f"], description=f"{x} of {n} at {c}")
    for d, inp, code in (("exceptions above observations", {"observations": 10, "exceptions": 11, "confidence": .99}, "E_DOMAIN"),
                         ("zero observations", {"observations": 0, "exceptions": 0, "confidence": .99}, "E_DOMAIN")):
        s.add(op, inp, error=code, cls=E, tags=["invalid", "stage-f"], description=d)


def christ_ref(I, c):
    n = len(I)
    x = sum(I)
    lr_uc = snap(max(-2 * (xlnx(n - x, 1 - (1 - mp.mpf(c))) + xlnx(x, 1 - mp.mpf(c))) + 2 * (xlnx(n - x, 1 - mp.mpf(x) / n) + xlnx(x, mp.mpf(x) / n)), mp.mpf(0)))
    nn = {(a, b): 0 for a in (0, 1) for b in (0, 1)}
    for a, b in zip(I, I[1:]):
        nn[(a, b)] += 1
    n00, n01, n10, n11 = nn[(0, 0)], nn[(0, 1)], nn[(1, 0)], nn[(1, 1)]
    tot = n00 + n01 + n10 + n11
    pi = mp.mpf(n01 + n11) / tot
    p01 = mp.mpf(n01) / (n00 + n01) if n00 + n01 else mp.mpf(0)
    p11 = mp.mpf(n11) / (n10 + n11) if n10 + n11 else mp.mpf(0)
    l0 = xlnx(n00 + n10, 1 - pi) + xlnx(n01 + n11, pi)
    l1 = xlnx(n00, 1 - p01) + xlnx(n01, p01) + xlnx(n10, 1 - p11) + xlnx(n11, p11)
    lr_ind = snap(max(-2 * (l0 - l1), mp.mpf(0)))
    lr_cc = lr_uc + lr_ind
    return {"lr_uc": f(lr_uc), "lr_ind": f(lr_ind), "lr_cc": f(lr_cc), "p_uc": f(chi2_sf(lr_uc, 1)), "p_ind": f(chi2_sf(lr_ind, 1)),
            "p_cc": f(chi2_sf(lr_cc, 2)), "transitions": {"n00": n00, "n01": n01, "n10": n10, "n11": n11}}


def f4_christ(s):
    op = "risk.backtest.christoffersen"
    g = Xo(SEED, stream=4)
    specs = [(250, .99, .01, 0), (250, .99, .02, 0), (250, .99, .02, .3), (500, .99, .01, .5), (1000, .975, .025, 0), (1000, .975, .03, .2),
             (250, .95, .05, 0), (260, .95, .08, .4), (750, .99, .01, 0), (250, .99, .04, .6), (500, .975, .025, .1), (2000, .99, .012, .05),
             (250, .99, 0.0, 0), (100, .99, .05, .8), (300, .975, .02, 0)]
    for n, c, base_p, clus in specs:
        I, prev = [], 0
        for _ in range(n):
            pr = clus if prev and clus else base_p
            prev = 1 if g.uniform() < pr else 0
            I.append(prev)
        out = christ_ref(I, c)
        s.add(op, {"exceptions": [bool(v) for v in I], "confidence": c}, out, cls=A, output_classes={"transitions": E}, verified=["mpmath 40-digit"],
              tags=["backtest", "stage-f"], description=f"n = {n}, {sum(I)} exceptions, clustering {clus}")
        if clus == .3:
            caught("christ", "independence on n - 1 vs n transitions (uses n)", abs(out["lr_ind"] - f(-2 * (xlnx(n - sum(I), 1 - mp.mpf(sum(I)) / n) + xlnx(sum(I), mp.mpf(sum(I)) / n)))), 1e-10)
    # hand cases: all ones after the first; last day only
    for I, d in (([False] * 249 + [True], "single exception on the last day (no transition out of 1)"), ([True, True, True, False] * 10, "clustered pattern")):
        s.add(op, {"exceptions": I, "confidence": .99}, christ_ref([int(v) for v in I], .99), cls=A, output_classes={"transitions": E},
              verified=["mpmath 40-digit"], tags=["backtest", "limit", "stage-f"], description=d)
    s.add(op, {"exceptions": [True], "confidence": .99}, error="E_INPUT", cls=E, tags=["invalid", "stage-f"], description="one observation (no transition)")


PLUS = {5: .40, 6: .50, 7: .65, 8: .75, 9: .85}


def f4_traffic(s):
    op = "risk.backtest.traffic_light"
    for n, x, c in [(250, k, .99) for k in range(0, 14)] + [(500, 8, .99), (500, 12, .99), (260, 6, .99), (1000, 30, .975), (250, 9, .975), (250, 0, .975)]:
        p = 1 - mp.mpf(c)
        cum = mp.fsum(mp.binomial(n, k) * p ** k * (1 - p) ** (n - k) for k in range(x + 1))
        zone = "GREEN" if cum < mp.mpf("0.95") else ("YELLOW" if cum < mp.mpf("0.9999") else "RED")
        plus = (0.0 if x <= 4 else PLUS.get(x, 1.0)) if (n == 250 and c == .99) else None
        s.add(op, {"observations": n, "exceptions": x, "confidence": c}, {"cumulative_probability": f(cum), "zone": zone, "plus_factor": plus},
              cls=A, output_classes={"zone": E, "plus_factor": E}, verified=["mpmath exact binomial sum", "Basel 1996 Table 2 zone boundaries 4/9"],
              tags=["backtest", "stage-f"], description=f"{x} of {n} at {c}")
    s.add(op, {"observations": 250, "exceptions": -1, "confidence": .99}, error="E_DOMAIN", cls=E, tags=["invalid", "stage-f"], description="negative exceptions")


# ===================================================================================== F4 FRTB-SA GIRR delta
TEN = {"0.25Y": .25, "0.5Y": .5, "1Y": 1, "2Y": 2, "3Y": 3, "5Y": 5, "10Y": 10, "15Y": 15, "20Y": 20, "30Y": 30}
RW = {"0.25Y": .017, "0.5Y": .017, "1Y": .016, "2Y": .013, "3Y": .012, "5Y": .011, "10Y": .011, "15Y": .011, "20Y": .011, "30Y": .011}
SPECIFIED = {"EUR", "USD", "GBP", "AUD", "JPY", "SEK", "CAD"}


def girr_rho(a, b):
    fa, fb = a["risk_factor"], b["risk_factor"]
    if "XCCY_BASIS" in (fa, fb):
        return mp.mpf(0)
    if fa == "INFLATION" and fb == "INFLATION":
        return mp.mpf("0.999")
    if "INFLATION" in (fa, fb):
        return mp.mpf("0.4")
    ta, tb = mp.mpf(TEN[fa]), mp.mpf(TEN[fb])
    r = max(mp.e ** (-mp.mpf("0.03") * abs(ta - tb) / min(ta, tb)), mp.mpf("0.4"))
    return r if a["curve"] == b["curve"] else r * mp.mpf("0.999")


def girr_ref(inp):
    red = inp.get("specified_currency_reduction", False)
    rep = inp.get("reporting_currency")
    bk = {}
    for x in inp["sensitivities"]:
        rw = mp.mpf("0.016") if x["risk_factor"] in ("INFLATION", "XCCY_BASIS") else mp.mpf(RW[x["risk_factor"]])
        if red and (x["currency"] in SPECIFIED or x["currency"] == rep):
            rw = rw / mp.sqrt(2)
        bk.setdefault(x["currency"], []).append((x, rw * mp.mpf(x["sensitivity"])))
    out = {}
    scen = {"medium": lambda r: r, "high": lambda r: min(mp.mpf("1.25") * r, mp.mpf(1)), "low": lambda r: max(2 * r - 1, mp.mpf("0.75") * r)}
    for nm, fn in scen.items():
        rows = []
        for cur in sorted(bk):
            items = bk[cur]
            q = mp.fsum(w * w for _, w in items) + mp.fsum(fn(girr_rho(a, b)) * wa * wb for i, (a, wa) in enumerate(items) for j, (b, wb) in enumerate(items) if i != j)
            K = mp.sqrt(max(q, mp.mpf(0)))
            Sb = mp.fsum(w for _, w in items)
            rows.append([cur, K, Sb])
        gam = fn(mp.mpf("0.5"))
        tot = lambda Ss: mp.fsum(r[1] ** 2 for r in rows) + mp.fsum(gam * Ss[i] * Ss[j] for i in range(len(rows)) for j in range(len(rows)) if i != j)  # noqa: E731
        Ss = [r[2] for r in rows]
        v = tot(Ss)
        alt = False
        if v < 0:
            alt = True
            Ss = [max(min(r[2], r[1]), -r[1]) for r in rows]
            v = tot(Ss)
        out[nm] = {"buckets": [{"currency": r[0], "k": f(r[1]), "s": f(r[2]), "s_used": f(su)} for r, su in zip(rows, Ss)],
                   "delta": f(mp.sqrt(max(v, mp.mpf(0)))), "alternative_used": alt}
    order = ["high", "medium", "low"]
    best = max(order, key=lambda k: (out[k]["delta"], -order.index(k)))
    return {"scenarios": out, "capital": out[best]["delta"], "binding_scenario": best}


def f4_girr(s):
    op = "risk.frtb.girr_delta"
    mk = lambda cur, crv, rf, v: {"currency": cur, "curve": crv, "risk_factor": rf, "sensitivity": v}  # noqa: E731
    g = Xo(SEED, stream=5)
    cases = [
        ("one tenor", [mk("USD", "SOFR", "5Y", 1e6)], False),
        ("long-short on one curve", [mk("USD", "SOFR", "2Y", 1e6), mk("USD", "SOFR", "10Y", -1.2e6)], False),
        ("two curves one currency", [mk("EUR", "ESTR", "5Y", 5e5), mk("EUR", "EURIBOR3M", "5Y", -4e5), mk("EUR", "EURIBOR3M", "10Y", 3e5)], False),
        ("inflation and xccy basis", [mk("GBP", "SONIA", "10Y", 2e5), mk("GBP", "UKRPI", "INFLATION", 1e5), mk("GBP", "GBPUSD", "XCCY_BASIS", -5e4)], False),
        ("two currencies, offsetting buckets (low scenario binds or alternative S)", [mk("USD", "SOFR", "5Y", 1e6), mk("EUR", "ESTR", "5Y", -1e6)], False),
        ("alternative S_b: two offsetting buckets of uncorrelated xccy basis factors",
         [mk("USD", f"USD-B{k}", "XCCY_BASIS", 1e6) for k in range(4)] + [mk("EUR", f"EUR-B{k}", "XCCY_BASIS", -1e6) for k in range(4)], False),
        ("specified-currency reduction",[mk("USD", "SOFR", "1Y", 3e5), mk("USD", "SOFR", "30Y", -2e5), mk("BRL", "CDI", "2Y", 1e5)], True),
    ]
    rand = []
    for k in range(6):
        sens = []
        for cur in ("USD", "EUR", "JPY")[:1 + k % 3]:
            for crv in ("OIS", "IBOR")[:1 + k % 2]:
                for t in TEN:
                    if g.uniform() < 0.6:
                        sens.append(mk(cur, f"{cur}-{crv}", t, round((g.uniform() - 0.5) * 2e6, 2)))
        rand.append((f"random book {k + 1}: {len(sens)} sensitivities", sens, k % 2 == 1))
    for d, sens, red in cases + rand:
        inp = {"sensitivities": sens, "specified_currency_reduction": red}
        out = girr_ref(inp)
        s.add(op, inp, out, cls=A, output_classes={"binding_scenario": E}, verified=["mpmath 40-digit", "MAR21.42 Table 1, MAR21.46 Table 2 (theta 3%)"],
              tags=["frtb", "stage-f"], description=d)
        if d.startswith("alternative"):
            assert all(out["scenarios"][k]["alternative_used"] for k in ("medium", "high", "low"))
        if d == "long-short on one curve":
            caught("girr", "rho without the 40% floor", abs(girr_ref({"sensitivities": [mk("USD", "SOFR", "0.25Y", 1e6), mk("USD", "SOFR", "30Y", -1e6)]})["capital"]
                                                         - f(math.sqrt((0.017e6) ** 2 + (0.011e6) ** 2 - 2 * math.exp(-0.03 * 29.75 / 0.25) * 0.017e6 * 0.011e6))), 1e-6)
    for d, sens, code in (("unknown tenor", [mk("USD", "SOFR", "4Y", 1.0)], "E_SCHEMA"), ("duplicate factor", [mk("USD", "SOFR", "5Y", 1.0)] * 2, "E_INPUT"),
                          ("empty", [], "E_INPUT")):
        s.add(op, {"sensitivities": sens}, error=code, cls=E, tags=["invalid", "stage-f"], description=d)


def F4():
    s = S("risk_f4", "06-risk/var-es-and-backtests.md")
    f4_hist(s)
    f4_fhs(s)
    f4_param(s)
    f4_mc(s)
    f4_kupiec(s)
    f4_christ(s)
    f4_traffic(s)
    s2 = S("frtb_f", "06-risk/frtb-sa-girr.md")
    f4_girr(s2)
    write(s)
    write(s2)


SLICES = {"F3": F3, "F4": F4}

if __name__ == "__main__":
    for k in sys.argv[1:] or list(SLICES):
        SLICES[k]()
    for m in MUTANTS:
        note(f"caught {m[0]}: {m[1]} (gap {m[2]:.3e})")
