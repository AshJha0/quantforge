"""Stage J wave 2: portfolio optimisation, estimation, Euler contributions, ES backtest, Baum-Welch.

Specs: specifications/07-portfolio/optimisation.md, 07-portfolio/estimation.md, 06-risk/es-backtest.md,
11-research/baum-welch.md; rulings specifications/stage-j-rulings-w2.md (J-W2-1 onwards).

Independent oracle: exact rational arithmetic (fractions) on the binary64 inputs for every operation that is linear
algebra only (mean-variance KKT solve, Ledoit-Wolf, Black-Litterman, ES Z2); mpmath at 50 digits for square roots,
risk parity (Newton on the Spinu system) and Baum-Welch.

Outside and independent checks (no golden is taken from an implementation under test):
- Mean-variance: the active set is located with scipy SLSQP, then the KKT system is solved exactly and every KKT
  condition (feasibility, multiplier signs, strict complementarity margin 1e-6) is verified in Fractions; PD covariance
  makes the KKT point the unique optimum. scipy agreement to 1e-8 is the J-5 outside check (recorded per case).
  For N <= 4 the active set is also found by enumerating all 3^N bound patterns. Hand case: two assets (w1 = 17/26).
- Risk parity: two assets with equal budgets give w_i proportional to 1/sigma_i for any correlation (hand).
- Euler: hand case; contributions sum to volatility exactly in the oracle.
- Ledoit-Wolf: two algebraic forms (paper [LW04] and the scikit-learn expression) equal in Fractions.
- Black-Litterman: two closed forms (update form and precision form) equal in Fractions; one-asset hand case.
- ES Z2: hand case.
- Baum-Welch: K = 1 converges to the sample mean and population sd (closed form); log-likelihood re-checked by a
  log-space forward pass.

    cd oracle/python && uv run python -W ignore gen_stage_j_w2.py
"""
import itertools
import math
from fractions import Fraction as Fr

import mpmath as mp

from qf_oracle import common
from qf_oracle.common import Suite, note

mp.mp.dps = 50
G = "oracle/python/gen_stage_j_w2.py"
FOLDER = "stage_j"
SA, EX, RF = "simple_analytic", "date_and_convention", "root_finding"
SPEC_OPT = "specifications/07-portfolio/optimisation.md"
SPEC_EST = "specifications/07-portfolio/estimation.md"
SPEC_ES = "specifications/06-risk/es-backtest.md"
SPEC_BW = "specifications/11-research/baum-welch.md"
LIM = {"assets": 500, "views": 500, "rows": 1_000_000, "cells": 10_000_000, "states": 16, "iterations": 10_000,
       "bw_cells": 10_000_000}
SYM_TOL = 1e-12
BW_LIMIT = {"absolute": 1e-12, "relative": 1e-9, "reason": "plan 12.10 A4: fitted parameters within 1e-9 relative across languages (ruling J-W2-9)"}


class QfErr(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def F(x):
    return Fr(x)


# ---------------------------------------------------------------- exact linear algebra

def solve(A, b):
    """Gauss-Jordan in Fractions; raises ZeroDivisionError if singular."""
    n = len(A)
    M = [list(map(F, A[i])) + [F(b[i])] for i in range(n)]
    for c in range(n):
        p = next(r for r in range(c, n) if M[r][c] != 0)
        M[c], M[p] = M[p], M[c]
        for r in range(n):
            if r != c and M[r][c] != 0:
                f = M[r][c] / M[c][c]
                M[r] = [x - f * y for x, y in zip(M[r], M[c])]
    return [M[i][n] / M[i][i] for i in range(n)]


def inv(A):
    n = len(A)
    cols = [solve(A, [1 if i == j else 0 for i in range(n)]) for j in range(n)]
    return [[cols[j][i] for j in range(n)] for i in range(n)]


def matmul(A, B):
    return [[sum(A[i][k] * B[k][j] for k in range(len(B))) for j in range(len(B[0]))] for i in range(len(A))]


def matvec(A, x):
    return [sum(a * b for a, b in zip(r, x)) for r in A]


def tr(A):
    return [list(r) for r in zip(*A)]


def pd(A):
    """Exact LDL' pivots all positive."""
    n = len(A)
    M = [list(map(F, r)) for r in A]
    for c in range(n):
        if M[c][c] <= 0:
            return False
        for r in range(c + 1, n):
            f = M[r][c] / M[c][c]
            M[r] = [x - f * y for x, y in zip(M[r], M[c])]
    return True


def check_square_sym(S, n, need_pd=True):
    if not isinstance(S, list) or len(S) != n or any(not isinstance(r, list) or len(r) != n for r in S):
        raise QfErr("E_INPUT")
    scale = max(abs(x) for r in S for x in r) or 1.0
    if any(abs(S[i][j] - S[j][i]) > SYM_TOL * scale for i in range(n) for j in range(n)):
        raise QfErr("E_DOMAIN")
    if need_pd and not pd(S):
        raise QfErr("E_DOMAIN")


def fin(*xs):
    for x in xs:
        if isinstance(x, list):
            fin(*x)
        elif isinstance(x, float) and not math.isfinite(x):
            raise QfErr("E_DOMAIN")


# ---------------------------------------------------------------- mean-variance (J-W2-2 .. J-W2-4)

def mv_inputs(inp):
    mu, S = inp["expected_returns"], inp["covariance"]
    n = len(mu)
    if n > LIM["assets"]:
        raise QfErr("E_LIMIT")
    fin(mu, S)
    lo = inp.get("lower", [0.0] * n); up = inp.get("upper", [1.0] * n)
    if n < 1 or len(lo) != n or len(up) != n:
        raise QfErr("E_INPUT")
    check_square_sym(S, n)
    g = inp["risk_aversion"]
    if g <= 0 or any(l > u for l, u in zip(lo, up)) or sum(map(F, lo)) > 1 or sum(map(F, up)) < 1:
        raise QfErr("E_DOMAIN")
    return mu, S, F(g), lo, up, n


def kkt(mu, S, g, lo, up, state):
    """state[i] in (-1, 0, 1). Returns (w, nu, grad) exactly or None."""
    n = len(mu)
    free = [i for i in range(n) if state[i] == 0]
    if not free:
        return None
    wB = {i: F(lo[i]) if state[i] < 0 else F(up[i]) for i in range(n) if state[i]}
    A = [[g * F(S[i][j]) for j in free] + [F(1)] for i in free] + [[F(1)] * len(free) + [F(0)]]
    rhs = [F(mu[i]) - g * sum(F(S[i][j]) * v for j, v in wB.items()) for i in free] + [1 - sum(wB.values())]
    try:
        x = solve(A, rhs)
    except StopIteration:
        return None
    w = [wB.get(i) for i in range(n)]
    for k, i in enumerate(free):
        w[i] = x[k]
    nu = x[-1]
    Sw = matvec([[F(v) for v in r] for r in S], w)
    grad = [F(mu[i]) - g * Sw[i] - nu for i in range(n)]
    return w, nu, grad


def kkt_ok(res, lo, up, state, margin=Fr(1, 10 ** 6)):
    w, nu, gr = res
    for i, s in enumerate(state):
        if s == 0 and not (F(lo[i]) + margin <= w[i] <= F(up[i]) - margin):
            return False
        if s < 0 and gr[i] > -margin:
            return False
        if s > 0 and gr[i] < margin:
            return False
    return True


def mv_scipy(mu, S, g, lo, up):
    import numpy as np
    from scipy.optimize import minimize
    mu_, S_ = np.array(mu), np.array(S)
    n = len(mu)
    x0 = np.clip(np.full(n, 1.0 / n), lo, up)
    r = minimize(lambda w: -(mu_ @ w - float(g) / 2 * w @ S_ @ w), x0, jac=lambda w: -(mu_ - float(g) * S_ @ w),
                 bounds=list(zip(lo, up)), constraints=[{"type": "eq", "fun": lambda w: w.sum() - 1, "jac": lambda w: np.ones(n)}],
                 method="SLSQP", options={"ftol": 1e-16, "maxiter": 2000})
    return list(r.x)


OUTSIDE_MV = []


def mv_ref(inp):
    mu, S, g, lo, up, n = mv_inputs(inp)
    ws = mv_scipy(mu, S, g, lo, up)
    state = [-1 if abs(ws[i] - lo[i]) < 1e-7 else 1 if abs(ws[i] - up[i]) < 1e-7 else 0 for i in range(n)]
    res = kkt(mu, S, g, lo, up, state)
    for _ in range(50):  # repair the located set exactly (one primal active-set flip at a time) before certifying
        if res is not None and kkt_ok(res, lo, up, state, margin=Fr(0)):
            break
        if res is None:
            raise AssertionError("no free asset")
        w, _, gr = res
        bad = [i for i in range(n) if (state[i] == 0 and not F(lo[i]) <= w[i] <= F(up[i])) or (state[i] < 0 and gr[i] > 0) or (state[i] > 0 and gr[i] < 0)]
        i = bad[0]
        state[i] = (-1 if w[i] < F(lo[i]) else 1) if state[i] == 0 else 0
        res = kkt(mu, S, g, lo, up, state)
    assert res is not None and kkt_ok(res, lo, up, state), "KKT certificate failed (margin)"
    if n <= 4:
        found = [st for st in itertools.product((-1, 0, 1), repeat=n)
                 if (r := kkt(mu, S, g, lo, up, st)) is not None and kkt_ok(r, lo, up, st, margin=Fr(0))]
        assert found == [tuple(state)], (found, state)
    w, nu, _ = res
    OUTSIDE_MV.append(max(abs(float(a) - b) for a, b in zip(w, ws)))
    Sf = [[F(v) for v in r] for r in S]
    var = sum(a * b for a, b in zip(w, matvec(Sf, w)))
    ret = sum(F(m) * a for m, a in zip(mu, w))
    return {"weights": [float(x) for x in w], "expected_return": float(ret), "volatility": float(mp.sqrt(mp.mpf(var.numerator) / var.denominator)),
            "objective": float(ret - g / 2 * var), "at_bound": state}


# ---------------------------------------------------------------- risk parity (J-W2-5)

def rp_ref(inp):
    S = inp["covariance"]
    n = len(S)
    if n > LIM["assets"]:
        raise QfErr("E_LIMIT")
    fin(S)
    b = inp.get("budgets", [1.0 / n] * n) if n else []
    if n < 1 or len(b) != n:
        raise QfErr("E_INPUT")
    check_square_sym(S, n)
    if any(x <= 0 for x in b) or abs(sum(b) - 1) > 1e-12:
        raise QfErr("E_DOMAIN")
    Sm = mp.matrix([[mp.mpf(x) for x in r] for r in S]); bm = [mp.mpf(x) for x in b]
    y = mp.matrix([mp.sqrt(bm[i] / Sm[i, i]) for i in range(n)])
    for _ in range(200):
        Fv = Sm * y - mp.matrix([bm[i] / y[i] for i in range(n)])
        if mp.norm(Fv) < mp.mpf(10) ** -45:
            break
        J = Sm + mp.diag([bm[i] / y[i] ** 2 for i in range(n)])
        d = mp.lu_solve(J, -Fv); t = mp.mpf(1)
        while any(y[i] + t * d[i] <= 0 for i in range(n)):
            t /= 2
        y = y + t * d
    else:
        raise AssertionError("risk parity Newton did not converge")
    w = y / sum(y)
    Sw = Sm * w; vol = mp.sqrt(sum(w[i] * Sw[i] for i in range(n)))
    rc = [w[i] * Sw[i] / vol for i in range(n)]
    assert all(abs(rc[i] / vol - bm[i] / sum(bm)) < mp.mpf(10) ** -40 for i in range(n))
    return {"weights": [float(x) for x in w], "volatility": float(vol), "contributions": [float(x) for x in rc]}


# ---------------------------------------------------------------- Euler contributions (J-W2-6)

def euler_ref(inp):
    w, S = inp["weights"], inp["covariance"]
    n = len(w)
    if n > LIM["assets"]:
        raise QfErr("E_LIMIT")
    fin(w, S)
    if n < 1:
        raise QfErr("E_INPUT")
    check_square_sym(S, n, need_pd=False)
    Sw = matvec([[F(v) for v in r] for r in S], list(map(F, w)))
    var = sum(F(a) * b for a, b in zip(w, Sw))
    if var <= 0:
        raise QfErr("E_DOMAIN")
    vol = mp.sqrt(mp.mpf(var.numerator) / var.denominator)
    marg = [mp.mpf(x.numerator) / x.denominator / vol for x in Sw]
    con = [mp.mpf(a) * m for a, m in zip(w, marg)]
    assert abs(sum(con) - vol) < mp.mpf(10) ** -45
    return {"volatility": float(vol), "marginal": [float(x) for x in marg], "contributions": [float(x) for x in con],
            "shares": [float(c / vol) for c in con]}


# ---------------------------------------------------------------- Ledoit-Wolf (J-W2-7)

def lw_ref(inp):
    X = inp["returns"]
    T = len(X)
    if T > LIM["rows"] or (T and T * len(X[0]) > LIM["cells"]):
        raise QfErr("E_LIMIT")
    fin(X)
    if T < 2 or any(not isinstance(r, list) or len(r) != len(X[0]) for r in X) or len(X[0]) < 1:
        raise QfErr("E_INPUT")
    p = len(X[0])
    Xf = [[F(v) for v in r] for r in X]
    mean = [sum(r[j] for r in Xf) / T for j in range(p)]
    Z = [[r[j] - mean[j] for j in range(p)] for r in Xf]
    S = [[sum(z[i] * z[j] for z in Z) / T for j in range(p)] for i in range(p)]
    m = sum(S[i][i] for i in range(p)) / p
    d2 = sum((S[i][j] - (m if i == j else 0)) ** 2 for i in range(p) for j in range(p)) / p
    bbar = sum(sum((z[i] * z[j] - S[i][j]) ** 2 for i in range(p) for j in range(p)) / p for z in Z) / T ** 2
    b2 = min(bbar, d2)
    delta = Fr(0) if b2 == 0 else b2 / d2
    # second form: the scikit-learn expression (sklearn.covariance.ledoit_wolf_shrinkage), written from its algebra
    X2 = [[z ** 2 for z in r] for r in Z]
    beta_ = sum(sum(X2[t][i] * X2[t][j] for t in range(T)) for i in range(p) for j in range(p))
    delta_ = sum(sum(Z[t][i] * Z[t][j] for t in range(T)) ** 2 for i in range(p) for j in range(p)) / T ** 2
    beta = Fr(1, p * T) * (beta_ / T - delta_)
    dl = (delta_ - 2 * m * sum(sum(X2[t][j] for t in range(T)) / T for j in range(p)) + p * m ** 2) / p
    beta = min(beta, dl)
    assert (Fr(0) if beta == 0 else beta / dl) == delta
    cov = [[float(delta * m * (1 if i == j else 0) + (1 - delta) * S[i][j]) for j in range(p)] for i in range(p)]
    return {"covariance": cov, "shrinkage": float(delta), "mu": float(m)}


# ---------------------------------------------------------------- Black-Litterman (J-W2-8)

def bl_ref(inp):
    S, pi, P, q, Om, tau = inp["covariance"], inp["prior_returns"], inp["pick"], inp["views"], inp["view_covariance"], inp["tau"]
    n, k = len(pi), len(q)
    if n > LIM["assets"] or k > LIM["views"]:
        raise QfErr("E_LIMIT")
    fin(S, pi, P, q, Om)
    if n < 1 or k < 1 or len(P) != k or any(not isinstance(r, list) or len(r) != n for r in P):
        raise QfErr("E_INPUT")
    check_square_sym(S, n)
    check_square_sym(Om, k)
    if tau <= 0:
        raise QfErr("E_DOMAIN")
    t = F(tau)
    tS = [[t * F(v) for v in r] for r in S]
    Pf = [[F(v) for v in r] for r in P]; Pt = tr(Pf)
    Of = [[F(v) for v in r] for r in Om]
    pif, qf = list(map(F, pi)), list(map(F, q))
    mid = inv([[a + b for a, b in zip(r1, r2)] for r1, r2 in zip(matmul(matmul(Pf, tS), Pt), Of)])
    K = matmul(matmul(tS, Pt), mid)
    resid = [a - b for a, b in zip(qf, matvec(Pf, pif))]
    post = [a + b for a, b in zip(pif, matvec(K, resid))]
    M = [[a - b for a, b in zip(r1, r2)] for r1, r2 in zip(tS, matmul(matmul(K, Pf), tS))]
    # precision form
    tSi, Oi = inv(tS), inv(Of)
    H = [[a + b for a, b in zip(r1, r2)] for r1, r2 in zip(tSi, matmul(matmul(Pt, Oi), Pf))]
    M2 = inv(H)
    post2 = matvec(M2, [a + b for a, b in zip(matvec(tSi, pif), matvec(matmul(Pt, Oi), qf))])
    assert post2 == post and M2 == M
    pred = [[float(F(S[i][j]) + M[i][j]) for j in range(n)] for i in range(n)]
    return {"posterior_returns": [float(x) for x in post], "posterior_covariance": [[float(x) for x in r] for r in M],
            "predictive_covariance": pred}


# ---------------------------------------------------------------- ES backtest Z2 (J-W2-10)

def z2_ref(inp):
    L, V, E, a = inp["losses"], inp["var"], inp["es"], inp["alpha"]
    T = len(L)
    if T > LIM["rows"]:
        raise QfErr("E_LIMIT")
    fin(L, V, E)
    if T < 1 or len(V) != T or len(E) != T:
        raise QfErr("E_INPUT")
    if not 0 < a < 1 or any(e <= 0 for e in E):
        raise QfErr("E_DOMAIN")
    s = sum(F(l) / F(e) for l, v, e in zip(L, V, E) if l > v)
    z2 = 1 - s / (T * F(a))
    return {"z2": float(z2), "exceptions": sum(1 for l, v in zip(L, V) if l > v), "expected_exceptions": float(T * F(a))}


# ---------------------------------------------------------------- Baum-Welch (J-W2-9, J-W2-11 .. J-W2-13)

def bw_estep(y, pi, A, mu, sd):
    T, K = len(y), len(pi)
    b = [[mp.npdf(y[t], mu[j], sd[j]) for j in range(K)] for t in range(T)]
    al, c = [], []
    for t in range(T):
        h = [pi[j] * b[0][j] for j in range(K)] if t == 0 else [sum(al[-1][i] * A[i][j] for i in range(K)) * b[t][j] for j in range(K)]
        ct = sum(h)
        if ct == 0:
            raise QfErr("E_DOMAIN")
        c.append(ct); al.append([x / ct for x in h])
    be = [[mp.mpf(1)] * K for _ in range(T)]
    for t in range(T - 2, -1, -1):
        be[t] = [sum(A[i][j] * b[t + 1][j] * be[t + 1][j] for j in range(K)) / c[t + 1] for i in range(K)]
    ll = sum(mp.log(x) for x in c)
    # independent check: log-space forward pass
    la = [mp.log(pi[j]) + mp.log(b[0][j]) if pi[j] > 0 else mp.ninf for j in range(K)]
    for t in range(1, T):
        la = [mp.log(sum(mp.exp(la[i]) * A[i][j] for i in range(K))) + mp.log(b[t][j]) for j in range(K)]
    assert abs(mp.log(sum(mp.exp(x) for x in la)) - ll) < mp.mpf(10) ** -35
    return b, al, be, c, ll


def bw_mstep(y, A, b, al, be, c):
    T, K = len(y), len(A)
    g = [[al[t][i] * be[t][i] for i in range(K)] for t in range(T)]
    pi = list(g[0])
    An = []
    for i in range(K):
        den = sum(g[t][i] for t in range(T - 1))
        if den == 0:
            raise QfErr("E_DOMAIN")
        An.append([sum(al[t][i] * A[i][j] * b[t + 1][j] * be[t + 1][j] / c[t + 1] for t in range(T - 1)) / den for j in range(K)])
    mu, sd = [], []
    for i in range(K):
        w = sum(g[t][i] for t in range(T))
        m = sum(g[t][i] * y[t] for t in range(T)) / w
        v = sum(g[t][i] * (y[t] - m) ** 2 for t in range(T)) / w
        if v <= 0:
            raise QfErr("E_DOMAIN")
        mu.append(m); sd.append(mp.sqrt(v))
    return pi, An, mu, sd


def bw_check(inp):
    y = inp["observations"]; pi = inp["initial"]; A = inp["transition"]; mu = inp["means"]; sd = inp["sds"]
    K, T = len(pi), len(y)
    tol, mx = inp.get("tolerance", 1e-10), inp.get("max_iterations", 1000)
    if K > LIM["states"] or mx > LIM["iterations"] or T > LIM["rows"] or T * K > LIM["bw_cells"]:
        raise QfErr("E_LIMIT")
    fin(y, pi, A, mu, sd, tol)
    if T < 2 or K < 1 or len(A) != K or any(not isinstance(r, list) or len(r) != K for r in A) or len(mu) != K or len(sd) != K or mx < 1:
        raise QfErr("E_INPUT")
    if (any(x < 0 for x in pi) or any(x < 0 for r in A for x in r) or abs(sum(pi) - 1) > 1e-9
            or any(abs(sum(r) - 1) > 1e-9 for r in A) or any(s <= 0 for s in sd) or tol <= 0):
        raise QfErr("E_DOMAIN")
    return y, pi, A, mu, sd, tol, mx


def bw_run(inp):
    y, pi, A, mu, sd, tol, mx = bw_check(inp)
    y = [mp.mpf(v) for v in y]
    th = ([mp.mpf(v) for v in pi], [[mp.mpf(v) for v in r] for r in A], [mp.mpf(v) for v in mu], [mp.mpf(v) for v in sd])
    b, al, be, c, ll = bw_estep(y, *th)
    gains, it, conv = [], 0, False
    while it < mx:
        th = bw_mstep(y, th[1], b, al, be, c)
        it += 1
        b, al, be, c, ll2 = bw_estep(y, *th)
        gains.append(ll2 - ll); ll = ll2
        if gains[-1] < tol:
            conv = True
            break
    return th, ll, it, conv, gains, tol


def bw_ref(inp):
    th, ll, it, conv, gains, tol = bw_run(inp)
    for gk in gains:  # ruling J-W2-12: every stop test is decided by at least 1e-11 in absolute terms
        assert abs(gk - tol) >= 1e-11, f"stop-rule margin {gk} vs {tol}"
    pi, A, mu, sd = th
    return {"initial": [float(x) for x in pi], "transition": [[float(x) for x in r] for r in A], "means": [float(x) for x in mu],
            "sds": [float(x) for x in sd], "log_likelihood": float(ll), "iterations": it, "converged": conv}


def bw_pick_tol(inp, mx=400):
    """Choose a tolerance between two consecutive gains with margin, so the stop iteration is the same in every build."""
    _, _, _, _, gains, _ = bw_run(dict(inp, tolerance=1e-30, max_iterations=mx))
    for k in range(1, len(gains)):
        lo, hi = gains[k], min(gains[:k])
        if 0 < lo and hi > 1e-10 and lo < 1e-7:
            t = float(mp.sqrt(lo * hi)) if lo > 0 else 1e-10
            if hi - t >= 1e-11 and t - lo >= 1e-11:
                return float(f"{t:.3g}")
    raise AssertionError("no tolerance with margin")


# ---------------------------------------------------------------- helpers

def mk(suite, op, ref, inp, code=None, cls=SA, desc=None, tags=(), verified=("reference-computed",), oc=None, limit=None):
    try:
        out = ref(inp)
        assert code is None, f"{suite.name}: expected {code}, got a value ({desc})"
        suite.add(op, inp, outputs=out, cls=cls, verified=verified, tags=("research", "synthetic") + tuple(tags),
                  description=desc, output_classes=oc, limit=limit)
    except QfErr as e:
        assert e.code == code, f"{suite.name} {desc}: expected {code}, got {e.code}"
        suite.add(op, inp, error=code, cls=EX, verified=("reference-computed",), tags=("invalid", "research") + tuple(tags),
                  description=desc)


def det(seed, n, lo=-1.0, hi=1.0, nd=6):
    x, out = seed, []
    for _ in range(n):
        x = (6364136223846793005 * x + 1442695040888963407) % 2 ** 64
        out.append(round(lo + (hi - lo) * (x >> 11) / 2 ** 53, nd))
    return out


def rand_cov(seed, n):
    a = det(seed, n * (n + 1), -0.3, 0.3)
    B = [a[i * (n + 1):(i + 1) * (n + 1)] for i in range(n)]
    S = [[round(sum(B[i][k] * B[j][k] for k in range(n + 1)) / (n + 1) + (0.01 if i == j else 0.0), 6) for j in range(n)] for i in range(n)]
    for i in range(n):
        for j in range(i):
            S[i][j] = S[j][i]
    return S


def build():
    suites = []
    # ---- optimisation
    s = Suite("optim_j", SPEC_OPT, G); suites.append(s)
    OPM, OPR, OPE = "research.portfolio.mean_variance", "research.portfolio.risk_parity", "risk.contrib.euler"
    hand = {"expected_returns": [0.08, 0.10], "covariance": [[0.04, 0.0], [0.0, 0.09]], "risk_aversion": 4.0,
            "lower": [-10.0, -10.0], "upper": [10.0, 10.0]}
    o = mv_ref(hand)
    assert abs(o["weights"][0] - 17 / 26) < 1e-16
    mk(s, OPM, mv_ref, hand, cls=RF, desc="hand: two uncorrelated assets, wide bounds, w1 = 17/26", verified=("hand", "reference-computed"), oc={"at_bound": EX})
    for i in range(20):  # J-5: 20 problems, binding constraints included
        n = 3 + i % 8
        S = rand_cov(1000 + i, n)
        mu = det(2000 + i, n, 0.0, 0.12)
        inp = {"expected_returns": mu, "covariance": S, "risk_aversion": [1.0, 3.0, 8.0, 20.0][i % 4]}
        if i % 3 == 1:
            inp.update(lower=[0.0] * n, upper=[round(1.5 / n + 0.05, 6)] * n)
        elif i % 3 == 2:
            inp.update(lower=[-0.5] * n, upper=[1.0] * n)
        for _ in range(8):  # strict-complementarity margin (J-W2-4): nudge the risk aversion until it holds
            try:
                mv_ref(inp)
                break
            except AssertionError:
                inp["risk_aversion"] = round(inp["risk_aversion"] * 1.37, 6)
        if True:
            mk(s, OPM, mv_ref, inp, cls=RF, desc=f"J-5 problem {i + 1}: {n} assets, " + ["long-only", "long-only with caps", "shorts to -0.5"][i % 3],
               verified=("kkt-certificate", "scipy-slsqp", "reference-computed"), oc={"at_bound": EX})
    base = dict(hand)
    for d, ch, code in [("risk aversion zero", {"risk_aversion": 0.0}, "E_DOMAIN"), ("lower above upper", {"lower": [0.5, -10.0], "upper": [0.4, 10.0]}, "E_DOMAIN"),
                        ("upper bounds sum below 1", {"lower": [0.0, 0.0], "upper": [0.4, 0.4]}, "E_DOMAIN"),
                        ("covariance not symmetric", {"covariance": [[0.04, 0.01], [0.0, 0.09]]}, "E_DOMAIN"),
                        ("covariance singular", {"covariance": [[1.0, 2.0], [2.0, 4.0]]}, "E_DOMAIN"),
                        ("bounds length", {"lower": [0.0]}, "E_INPUT"), ("covariance shape", {"covariance": [[0.04, 0.0]]}, "E_INPUT")]:
        mk(s, OPM, mv_ref, dict(base, **ch), code=code, desc=d)
    rh = {"covariance": [[0.04, 0.018], [0.018, 0.09]]}
    o = rp_ref(rh)
    assert abs(o["weights"][0] - 0.6) < 1e-15  # 1/0.2 : 1/0.3 = 0.6 : 0.4
    mk(s, OPR, rp_ref, rh, cls=RF, desc="hand: two assets, equal budgets, w = (0.6, 0.4) from 1/sigma for any correlation", verified=("hand", "reference-computed"))
    mk(s, OPR, rp_ref, dict(rh, budgets=[0.7, 0.3]), cls=RF, desc="two assets, budgets 70/30")
    for i in range(6):
        n = 3 + 2 * i
        inp = {"covariance": rand_cov(3000 + i, n)}
        if i % 2:
            bb = [abs(x) + 0.1 for x in det(3100 + i, n)]
            inp["budgets"] = [round(x / sum(bb), 12) for x in bb[:-1]]
            inp["budgets"].append(1.0 - sum(inp["budgets"]))
        mk(s, OPR, rp_ref, inp, cls=RF, desc=f"{n} assets, " + ("unequal budgets" if i % 2 else "equal budgets"))
    for d, ch, code in [("zero budget", {"budgets": [1.0, 0.0]}, "E_DOMAIN"), ("budgets sum 0.9", {"budgets": [0.5, 0.4]}, "E_DOMAIN"),
                        ("budgets length", {"budgets": [1.0]}, "E_INPUT"), ("not positive definite", {"covariance": [[0.04, 0.2], [0.2, 0.09]]}, "E_DOMAIN")]:
        mk(s, OPR, rp_ref, {**rh, "budgets": [0.5, 0.5], **ch}, code=code, desc=d)
    eh = {"weights": [0.5, 0.5], "covariance": [[0.04, 0.0], [0.0, 0.0]]}
    o = euler_ref(eh)
    assert o["volatility"] == 0.1 and o["contributions"] == [0.1, 0.0]
    mk(s, OPE, euler_ref, eh, desc="hand: one risky asset carries all the risk (vol 0.1, contributions 0.1 and 0)", verified=("hand", "reference-computed"))
    mk(s, OPE, euler_ref, {"weights": [1.0, -0.5], "covariance": rh["covariance"]}, desc="long-short: a hedge leg has negative contribution")
    for i in range(4):
        n = 4 + 3 * i
        mk(s, OPE, euler_ref, {"weights": det(4000 + i, n, -1, 1), "covariance": rand_cov(4100 + i, n)}, desc=f"{n} assets, signed weights")
    for d, ch, code in [("zero volatility", {"covariance": [[0.0, 0.0], [0.0, 0.0]]}, "E_DOMAIN"), ("weights length", {"weights": [1.0]}, "E_INPUT"),
                        ("asymmetric", {"covariance": [[0.04, 0.01], [0.0, 0.09]]}, "E_DOMAIN")]:
        mk(s, OPE, euler_ref, dict(eh, **ch), code=code, desc=d)

    # ---- estimation
    s = Suite("estim_j", SPEC_EST, G); suites.append(s)
    OPL, OPB = "research.estimate.ledoit_wolf", "research.estimate.black_litterman"
    lh = {"returns": [[1.0, 0.0], [-1.0, 0.0], [0.0, 1.0], [0.0, -1.0]]}
    o = lw_ref(lh)
    assert o["mu"] == 0.5 and o["shrinkage"] == 0.0  # S = I/2: spec worked example
    mk(s, OPL, lw_ref, lh, desc="hand: S already a multiple of I, shrinkage 0", verified=("hand", "reference-computed"))
    for i in range(7):
        T, n = 10 + 15 * i, 2 + i
        mk(s, OPL, lw_ref, {"returns": [det(5000 + 31 * i + t, n, -0.03, 0.03) for t in range(T)]}, desc=f"T={T}, N={n}",
           verified=("two-forms", "reference-computed"))
    mk(s, OPL, lw_ref, {"returns": [[0.01], [0.03], [-0.02]]}, desc="one asset: shrinkage 0, variance by n")
    for d, inp, code in [("one row", {"returns": [[0.01, 0.02]]}, "E_INPUT"), ("ragged", {"returns": [[0.01, 0.02], [0.01]]}, "E_INPUT")]:
        mk(s, OPL, lw_ref, inp, code=code, desc=d)
    bh = {"covariance": [[0.04]], "prior_returns": [0.05], "pick": [[1.0]], "views": [0.1], "view_covariance": [[0.002]], "tau": 0.05}
    o = bl_ref(bh)
    assert abs(o["posterior_returns"][0] - 0.075) < 1e-15  # (0.05/0.002 + 0.1/0.002)/(2/0.002)
    mk(s, OPB, bl_ref, bh, desc="hand: one asset, view as precise as the prior, posterior 0.075", verified=("hand", "two-forms", "reference-computed"))
    for i in range(5):
        n, k = 3 + i, 1 + i % 3
        S = rand_cov(6000 + i, n)
        P = [[round(x) * 1.0 for x in det(6100 + 7 * i + r, n, -1.4, 1.4)] for r in range(k)]
        for r in range(k):
            if not any(P[r]):
                P[r][r] = 1.0
        om = [[(0.001 * (r + 1) if r == c else 0.0) for c in range(k)] for r in range(k)]
        mk(s, OPB, bl_ref, {"covariance": S, "prior_returns": det(6200 + i, n, 0.0, 0.1), "pick": P, "views": det(6300 + i, k, -0.05, 0.1),
                            "view_covariance": om, "tau": 0.025 * (1 + i % 2)}, desc=f"{n} assets, {k} views", verified=("two-forms", "reference-computed"))
    for d, ch, code in [("tau zero", {"tau": 0.0}, "E_DOMAIN"), ("view covariance not PD", {"view_covariance": [[0.0]]}, "E_DOMAIN"),
                        ("pick width", {"pick": [[1.0, 0.0]]}, "E_INPUT"), ("no views", {"pick": [], "views": [], "view_covariance": []}, "E_INPUT")]:
        mk(s, OPB, bl_ref, dict(bh, **ch), code=code, desc=d)

    # ---- ES backtest
    s = Suite("esbt_j", SPEC_ES, G); suites.append(s)
    OPZ = "risk.backtest.es_z2"
    zh = {"losses": [1.0, 3.0, 0.5, 4.0], "var": [2.0, 2.0, 2.0, 2.0], "es": [2.5, 2.5, 2.5, 2.5], "alpha": 0.25}
    o = z2_ref(zh)
    assert abs(o["z2"] + 1.8) < 1e-15 and o["exceptions"] == 2
    mk(s, OPZ, z2_ref, zh, desc="hand: two exceptions, Z2 = 1 - (1.2 + 1.6)/1 = -1.8", verified=("hand", "reference-computed"), oc={"exceptions": EX})
    mk(s, OPZ, z2_ref, dict(zh, losses=[0.0, 0.0, 0.0, 0.0]), desc="no exceptions: Z2 = 1", oc={"exceptions": EX})
    for i in range(5):
        T = 250 * (i + 1)
        L = det(7000 + i, T, -2.5, 2.5)
        mk(s, OPZ, z2_ref, {"losses": L, "var": [1.96] * T, "es": [round(2.338 * (1 + 0.1 * i), 6)] * T, "alpha": 0.025},
           desc=f"T={T}, flat VaR and ES" + (", ES overstated" if i else ""), oc={"exceptions": EX})
    for d, ch, code in [("alpha 0", {"alpha": 0.0}, "E_DOMAIN"), ("alpha 1", {"alpha": 1.0}, "E_DOMAIN"), ("ES zero", {"es": [2.5, 0.0, 2.5, 2.5]}, "E_DOMAIN"),
                        ("length mismatch", {"var": [2.0]}, "E_INPUT"), ("empty", {"losses": [], "var": [], "es": []}, "E_INPUT")]:
        mk(s, OPZ, z2_ref, dict(zh, **ch), code=code, desc=d)

    # ---- Baum-Welch
    s = Suite("baumwelch_j", SPEC_BW, G); suites.append(s)
    OPW = "research.regime.baum_welch"
    oc = {"iterations": EX, "converged": EX, "log_likelihood": "likelihood_sum"}
    y1 = [0.5, -1.0, 2.0, 0.25, 1.5, -0.75]
    k1 = {"observations": y1, "initial": [1.0], "transition": [[1.0]], "means": [0.0], "sds": [1.0], "tolerance": 1e-10}
    o = bw_ref(k1)
    m = sum(y1) / 6; v = sum((x - m) ** 2 for x in y1) / 6
    assert abs(o["means"][0] - m) < 1e-15 and abs(o["sds"][0] - math.sqrt(v)) < 1e-15 and o["iterations"] == 2
    mk(s, OPW, bw_ref, k1, desc="hand: one state converges to the sample mean and population sd in one step, stops at iteration 2",
       verified=("hand", "reference-computed"), oc=oc, limit=BW_LIMIT)
    start = {"initial": [0.5, 0.5], "transition": [[0.8, 0.2], [0.2, 0.8]], "means": [-0.5, 1.5], "sds": [1.0, 1.0]}
    for i, T in enumerate((60, 100, 150)):
        reg = [(t // 25) % 2 for t in range(T)]
        noise = [sum(det(8000 + 13 * i + t, 6, -1, 1)) / math.sqrt(2) for t in range(T)]
        y = [round((2.0 if r else 0.0) + (1.5 if r else 1.0) * e, 6) for r, e in zip(reg, noise)]
        inp = dict(start, observations=y)
        inp["tolerance"] = bw_pick_tol(inp)
        mk(s, OPW, bw_ref, inp, desc=f"A4 start values, two states, {T} observations, blocks of 25", oc=oc, limit=BW_LIMIT)
        if i == 0:
            mk(s, OPW, bw_ref, dict(inp, max_iterations=5), desc="stopped at 5 iterations: not converged", oc=oc, limit=BW_LIMIT)
    y3 = [round(c + 0.4 * e, 6) for c, e in zip([-2.0] * 20 + [0.0] * 20 + [2.0] * 20, [sum(det(8500 + t, 4, -1, 1)) for t in range(60)])]
    inp = {"observations": y3, "initial": [0.4, 0.3, 0.3], "transition": [[0.9, 0.05, 0.05], [0.05, 0.9, 0.05], [0.05, 0.05, 0.9]],
           "means": [-1.5, 0.2, 1.5], "sds": [1.0, 1.0, 1.0]}
    inp["tolerance"] = bw_pick_tol(inp)
    mk(s, OPW, bw_ref, inp, desc="three states, 60 observations", oc=oc, limit=BW_LIMIT)
    eb = dict(start, observations=[0.1, 0.4, -0.2, 1.9, 2.2], tolerance=1e-10)
    for d, ch, code in [("rows do not sum to 1", {"transition": [[0.8, 0.1], [0.2, 0.8]]}, "E_DOMAIN"), ("sd zero", {"sds": [1.0, 0.0]}, "E_DOMAIN"),
                        ("one observation", {"observations": [0.1]}, "E_INPUT"), ("tolerance zero", {"tolerance": 0.0}, "E_DOMAIN"),
                        ("max iterations zero", {"max_iterations": 0}, "E_INPUT"), ("max iterations above 10,000", {"max_iterations": 10001}, "E_LIMIT"),
                        ("means length", {"means": [0.0]}, "E_INPUT"),
                        ("collapse: constant series", {"observations": [1.0, 1.0, 1.0, 1.0]}, "E_DOMAIN")]:
        mk(s, OPW, bw_ref, dict(eb, **ch), code=code, desc=d)
    return suites


def main():
    keep = common.GOLDEN
    common.GOLDEN = keep.parent / FOLDER
    tot = [0, 0, 0]
    for s in build():
        s.write()
        tot[0] += len(s.cases)
        tot[1] += sum(c["expected"]["status"] == "ok" for c in s.cases)
        tot[2] += sum(c["expected"]["status"] == "error" for c in s.cases)
    common.GOLDEN = keep
    note(f"stage J wave 2: {tot[0]} cases, value {tot[1]}, error {tot[2]}; mean-variance max |oracle - scipy SLSQP| {max(OUTSIDE_MV):.2e}")


if __name__ == "__main__":
    main()
