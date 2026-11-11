"""Stage I wave 1: hedge solvers (specifications/08-hedging/hedge-solvers.md, rulings I-1 onwards).

Every golden, error codes included, is the output of the reference functions below (`*_ref`). An error case is built by
breaking one rule; the generator runs the reference on it, records the code the reference raises, and asserts that this is
the code the case was meant to reach (so a case that stops at an earlier rule is caught here, not by a language lane).

Self-checks, each an assertion:
- QP: the answer is the unique KKT point found by enumerating every active set at 50 digits (mpmath); KKT residual, primal
  feasibility, multiplier signs and complementarity are re-checked on the result; infeasibility is confirmed by HiGHS
  (`scipy.optimize.linprog`); every rank and singularity decision keeps a margin of at least 1e3 from its threshold.
- Integer: exhaustive search in exact rational arithmetic over a box proved to contain every minimiser (ellipsoid bound);
  the gap to the runner-up is either an exact tie (the tie rule is then pinned) or above 1e-9 relative.
- Outside references (rule 11.2.5, ruling I-2): scipy 1.18 `lsq_linear` (BVLS), `linalg.lstsq` (gelsd minimum norm) and
  `minimize` (SLSQP); numpy 2.5 `linalg.lstsq` and `linalg.solve`; QuantLib 1.44 `AnalyticEuropeanEngine` Greeks. A case
  counts only if every output agrees with the library value within the case's tolerance.

    cd oracle/python && uv run python -W ignore gen_stage_i_w1.py
"""
import itertools
import json
import math
from fractions import Fraction as Fr
from pathlib import Path

import mpmath as mp
import numpy as np
import QuantLib as ql
import scipy.linalg as sl
import scipy.optimize as so

from qf_oracle import common
from qf_oracle.common import Suite, note

mp.mp.dps = 50
G = "oracle/python/gen_stage_i_w1.py"
SPEC = "specifications/08-hedging/hedge-solvers.md"
FOLDER = "stage_i"
HERE = Path(__file__).resolve().parent
RF, SA, EX = "root_finding", "simple_analytic", "date_and_convention"
THRESH = mp.mpf("1e-12")  # rank and singularity threshold (ruling I-3)
MARGIN = mp.mpf(1000)     # goldens keep every decision this far from THRESH
LIMITS = {"factors": 1000, "instruments": 200, "equalities": 200, "integer_instruments": 12, "series": 100000, "positions": 1000}
QP, INT, MV, GR, BETA, RES = ("hedge.qp.solve", "hedge.integer.solve", "hedge.minvar.ratio", "hedge.greeks.neutralise",
                              "hedge.beta.futures", "hedge.residual.report")
MUTANTS = []


class QfErr(Exception):
    def __init__(self, code, why=""):
        super().__init__(f"{code}: {why}")
        self.code = code


def fail(code, why=""):
    raise QfErr(code, why)


def caught(name, gap, tol=1e-9):
    assert gap > tol, f"mutant '{name}' is not caught: gap {gap:.3e}"
    MUTANTS.append((name, float(gap)))


def finite_rule(inp):
    """F-2: every real input finite (E_DOMAIN). Nulls are skipped (legal only where the spec says)."""
    def walk(v):
        if (isinstance(v, float) and not math.isfinite(v)) or v in ("NaN", "Infinity", "-Infinity"):
            fail("E_DOMAIN", "non-finite input")
        if isinstance(v, (list, tuple)):
            for u in v:
                walk(u)
        if isinstance(v, dict):
            for u in v.values():
                walk(u)
    walk(inp)


def M(rows):
    return mp.matrix([[mp.mpf(x) for x in r] for r in rows])


def sym_eig(Hm):
    if Hm.rows == 1:  # mpmath eigsy needs at least 2 x 2
        return [Hm[0, 0]], mp.matrix([[1]])
    E, Q = mp.eigsy(Hm)
    return [E[i] for i in range(Hm.rows)], Q


def decide(value, scale, what):
    """Threshold decision `value <= THRESH * scale` with the I-3 margin asserted."""
    if scale == 0:
        return True
    r = abs(value) / scale
    assert r < THRESH / MARGIN or r > THRESH * MARGIN, f"{what}: ratio {mp.nstr(r, 5)} too close to the threshold"
    return r <= THRESH


def fl(v):
    return float(v)


# ================================================================================================ hedge.qp.solve
def qp_shapes(inp, integer=False):
    a, b, w = inp["a"], inp["b"], inp["weights"]
    m = len(a)
    n = len(a[0]) if m else 0
    lim_n = LIMITS["integer_instruments"] if integer else LIMITS["instruments"]
    if m > LIMITS["factors"] or n > lim_n or len(inp.get("eq_matrix", [])) > LIMITS["equalities"]:
        fail("E_LIMIT")
    finite_rule(inp)
    if m == 0 or n == 0 or any(len(r) != n for r in a) or len(b) != m or len(w) != m:
        fail("E_INPUT", "shape")
    return m, n


def qp_validate(inp):
    m, n = qp_shapes(inp)
    E, f = inp.get("eq_matrix"), inp.get("eq_rhs")
    if (E is None) != (f is None):
        fail("E_INPUT", "eq_matrix and eq_rhs go together")
    E, f = E or [], f or []
    if any(len(r) != n for r in E) or len(f) != len(E):
        fail("E_INPUT", "equality shape")
    lo, up = inp.get("lower"), inp.get("upper")
    for v in (lo, up):
        if v is not None and len(v) != n:
            fail("E_INPUT", "bound length")
    lo = lo or [None] * n
    up = up or [None] * n
    pol = inp.get("singular", "ERROR")
    if pol == "MIN_NORM" and any(x is not None for x in lo + up):
        fail("E_INPUT", "MIN_NORM with bounds")
    if any(x <= 0 for x in inp["weights"]):
        fail("E_DOMAIN", "weight")
    if inp.get("ridge", 0.0) < 0:
        fail("E_DOMAIN", "ridge")
    if any(l is not None and u is not None and l > u for l, u in zip(lo, up)):
        fail("E_DOMAIN", "lower above upper")
    return m, n, E, f, lo, up, pol


def qp_core(inp):
    """Returns (x, residual, objective, rank) in mpmath, or raises QfErr with the computed code."""
    m, n, E, f, lo, up, pol = qp_validate(inp)
    A, b, w = M(inp["a"]), [mp.mpf(x) for x in inp["b"]], [mp.mpf(x) for x in inp["weights"]]
    ridge = mp.mpf(inp.get("ridge", 0.0))
    rv = [mp.mpf(v) for v in inp["_rv"]] if "_rv" in inp else [ridge] * n  # per-coordinate ridge (integer lot space only)
    k = len(E)
    H = mp.matrix(n, n)
    c = mp.matrix(n, 1)
    for i in range(m):
        for p in range(n):
            c[p] += A[i, p] * w[i] * b[i]
            for q in range(n):
                H[p, q] += A[i, p] * w[i] * A[i, q]
    for p in range(n):
        H[p, p] += rv[p]
    # equality rank (I-3): smallest singular value against the largest
    Zcols = list(range(n))
    if k:
        Em = M(E)
        U, S, V = mp.svd_r(Em, full_matrices=True)
        sv = [S[i] for i in range(min(k, n))]
        smax = max(sv)
        if k > n or decide(min(sv), smax, "equality rank"):
            fail("E_SINGULAR", "equality rows dependent")
        Z = V.T[:, k:] if k < n else None  # rows of V are right singular vectors
        Fv = mp.matrix([mp.mpf(x) for x in f])
        xp = V.T[:, :k] * mp.diag([1 / s for s in sv]) * U.T * Fv
    else:
        Z = mp.eye(n)
        xp = mp.matrix(n, 1)
    hev, _ = sym_eig(H)
    hmax = max(abs(e) for e in hev)
    rank = 0
    if Z is not None:
        R = Z.T * H * Z
        rev, rQ = sym_eig(R)
        zero = [decide(e, hmax, "reduced Hessian") for e in rev]
        rank = sum(1 for z in zero if not z)
        if any(zero):
            if pol == "ERROR":
                fail("E_SINGULAR", "reduced Hessian singular")
            # MIN_NORM: x = xp + Z y, y the minimum-norm minimiser of the reduced problem (no bounds by validation)
            g = Z.T * (H * xp + c)
            y = mp.matrix(R.rows, 1)
            for j, e in enumerate(rev):
                if not zero[j]:
                    qj = rQ[:, j]
                    y -= qj * ((qj.T * g)[0] / e)
            x = xp + Z * y
            return finish(A, b, w, rv, x, rank, m, n)
    x = active_set(H, c, E, f, lo, up, n)
    return finish(A, b, w, rv, x, rank, m, n)


def active_set(H, c, E, f, lo, up, n):
    """Unique minimiser of x'Hx + 2c'x subject to E x = f, lo <= x <= up, by enumerating active sets at 50 digits."""
    k = len(E)
    bnd = [j for j in range(n) if lo[j] is not None or up[j] is not None]
    choices = [[(None,)] + ([("L",)] if lo[j] is not None else []) + ([("U",)] if up[j] is not None else []) for j in bnd]
    found = []
    tiny = mp.mpf("1e-35")
    for combo in itertools.product(*choices):
        act = [(j, t[0]) for j, t in zip(bnd, combo) if t[0]]
        sz = n + k + len(act)
        K = mp.matrix(sz, sz)
        rhs = mp.matrix(sz, 1)
        for p in range(n):
            for q in range(n):
                K[p, q] = 2 * H[p, q]
            rhs[p] = -2 * c[p]
        for r in range(k):
            for p in range(n):
                K[p, n + r] = mp.mpf(E[r][p])
                K[n + r, p] = mp.mpf(E[r][p])
            rhs[n + r] = mp.mpf(f[r])
        for t, (j, side) in enumerate(act):
            s = -1 if side == "L" else 1  # gradient + E'l - mu_L e_j + mu_U e_j = 0
            K[j, n + k + t] = s
            K[n + k + t, j] = 1
            rhs[n + k + t] = mp.mpf(lo[j] if side == "L" else up[j])
        try:
            sol = mp.lu_solve(K, rhs)
        except ZeroDivisionError:
            continue
        x = [sol[p] for p in range(n)]
        if any(lo[j] is not None and x[j] < lo[j] - tiny for j in range(n)):
            continue
        if any(up[j] is not None and x[j] > up[j] + tiny for j in range(n)):
            continue
        if any(sol[n + k + t] < -tiny for t in range(len(act))):
            continue
        if not any(max(abs(x[p] - y[p]) for p in range(n)) < mp.mpf("1e-30") for y in found):
            found.append(x)
    if not found:
        return None
    assert len(found) == 1, "strictly convex QP with two KKT points"
    return mp.matrix(found[0])


def finish(A, b, w, rv, x, rank, m, n):
    if x is None:
        fail("E_INFEASIBLE", "no feasible point")
    r = A * x + mp.matrix(b)
    obj = sum(w[i] * r[i] ** 2 for i in range(m)) + sum(rv[p] * x[p] ** 2 for p in range(n))
    return x, r, obj, rank


def qp_ref(inp):
    x, r, obj, rank = qp_core(inp)
    return {"x": [fl(v) for v in x], "residual": [fl(v) for v in r], "objective": fl(obj), "rank": rank}


def kkt_check(inp, out):
    """Re-check stationarity, feasibility, complementarity and multiplier signs from the double outputs."""
    A, b, w = np.array(inp["a"]), np.array(inp["b"]), np.array(inp["weights"])
    ridge = inp.get("ridge", 0.0)
    x = np.array(out["x"])
    n = len(x)
    g = 2 * (A.T @ (w * (A @ x + b)) + ridge * x)
    lo = inp.get("lower") or [None] * n
    up = inp.get("upper") or [None] * n
    scale = 1 + np.abs(g).max() + np.abs(A).max() ** 2 * np.abs(x).max()
    act = [j for j in range(n) if (lo[j] is not None and abs(x[j] - lo[j]) < 1e-9) or (up[j] is not None and abs(x[j] - up[j]) < 1e-9)]
    free = [j for j in range(n) if j not in act]
    E = np.array(inp.get("eq_matrix") or np.zeros((0, n)))
    if len(E):
        assert np.abs(E @ x - np.array(inp["eq_rhs"])).max() < 1e-9, "equality feasibility"
    for j in range(n):
        assert (lo[j] is None or x[j] >= lo[j] - 1e-12) and (up[j] is None or x[j] <= up[j] + 1e-12), "bound feasibility"
    # stationarity on the free coordinates after the best equality multipliers; signs on the active ones
    if len(E):
        lam = np.linalg.lstsq(E[:, free].T, -g[free], rcond=None)[0] if free else np.zeros(len(E))
        gl = g + E.T @ lam
    else:
        gl = g
    assert np.abs(gl[free]).max(initial=0) < 1e-8 * scale, f"KKT stationarity {np.abs(gl[free]).max(initial=0)}"
    for j in act:
        if lo[j] is not None and abs(x[j] - lo[j]) < 1e-9:
            assert gl[j] >= -1e-8 * scale, "lower multiplier sign"
        else:
            assert gl[j] <= 1e-8 * scale, "upper multiplier sign"


def qp_outside(inp, out, tol):
    """A library optimiser's x; None when no library covers the case. Counted only if every output agrees."""
    A, b, w = np.array(inp["a"]), np.array(inp["b"]), np.array(inp["weights"])
    ridge = inp.get("ridge", 0.0)
    n = A.shape[1]
    sw = np.sqrt(w)
    At = np.vstack([A * sw[:, None], math.sqrt(ridge) * np.eye(n)]) if ridge else A * sw[:, None]
    bt = np.concatenate([b * sw, np.zeros(n)]) if ridge else b * sw
    lo, up = inp.get("lower"), inp.get("upper")
    if inp.get("eq_matrix"):
        if inp.get("singular") == "MIN_NORM":
            return None, "none"
        bounds = list(zip(lo or [None] * n, up or [None] * n))
        cons = [{"type": "eq", "fun": (lambda x, r=r, v=v: np.dot(r, x) - v), "jac": (lambda x, r=r: np.array(r))}
                for r, v in zip(inp["eq_matrix"], inp["eq_rhs"])]
        res = so.minimize(lambda x: float(np.sum((At @ x + bt) ** 2)), np.zeros(n), jac=lambda x: 2 * At.T @ (At @ x + bt),
                          method="SLSQP", bounds=bounds, constraints=cons, options={"ftol": 1e-16, "maxiter": 1000})
        return res.x, "scipy-1.18-slsqp"
    if lo is None and up is None:
        return sl.lstsq(At, -bt, lapack_driver="gelsd")[0], "scipy-1.18-lstsq"
    lb = np.array([-np.inf if v is None else v for v in (lo or [None] * n)])
    ub = np.array([np.inf if v is None else v for v in (up or [None] * n)])
    try:
        res = so.lsq_linear(At, -bt, bounds=(lb, ub), method="bvls", tol=1e-15, lsq_solver="exact")
    except ValueError:  # scipy refuses lower = upper
        return None, "scipy-1.18-bvls (refused)"
    return res.x, "scipy-1.18-bvls"


def agrees(xl, out, inp, tol):
    if xl is None:
        return False
    A, b, w = np.array(inp["a"]), np.array(inp["b"]), np.array(inp["weights"])
    r = A @ xl + b
    obj = float(np.sum(w * r * r) + inp.get("ridge", 0.0) * np.sum(xl * xl))
    pairs = list(zip(xl, out["x"])) + list(zip(r, out["residual"])) + [(obj, out["objective"])]
    return all(abs(p - q) <= tol + tol * abs(q) for p, q in pairs)


def infeasible_by_highs(inp):
    n = len(inp["a"][0])
    lo, up = inp.get("lower") or [None] * n, inp.get("upper") or [None] * n
    E = inp.get("eq_matrix")
    res = so.linprog(np.zeros(n), A_eq=np.array(E) if E else None, b_eq=np.array(inp["eq_rhs"]) if E else None,
                     bounds=list(zip(lo, up)), method="highs")
    return res.status == 2


# ================================================================================================ hedge.integer.solve
def int_ref(inp):
    m, n = qp_shapes(inp, integer=True)
    lots = inp["lot_sizes"]
    lo, up = inp.get("lower_lots"), inp.get("upper_lots")
    for v in (lo, up):
        if v is not None and len(v) != n:
            fail("E_INPUT", "bound length")
    if len(lots) != n:
        fail("E_INPUT", "lot_sizes length")
    lo, up = lo or [None] * n, up or [None] * n
    if any(x <= 0 for x in inp["weights"]):
        fail("E_DOMAIN", "weight")
    if inp.get("ridge", 0.0) < 0:
        fail("E_DOMAIN", "ridge")
    if any(x <= 0 for x in lots):
        fail("E_DOMAIN", "lot size")
    if any(l is not None and u is not None and l > u for l, u in zip(lo, up)):
        fail("E_DOMAIN", "lower above upper")
    # lot space: x = L n. Continuous problem must be strictly convex (I-6)
    a_l = [[inp["a"][i][j] * lots[j] for j in range(n)] for i in range(m)]
    A = [[Fr(inp["a"][i][j]) * Fr(lots[j]) for j in range(n)] for i in range(m)]
    b = [Fr(x) for x in inp["b"]]
    w = [Fr(x) for x in inp["weights"]]
    ridge = Fr(inp.get("ridge", 0.0))
    L = [Fr(x) for x in lots]

    def obj(nv):
        s = Fr(0)
        for i in range(m):
            r = b[i] + sum(A[i][j] * nv[j] for j in range(n))
            s += w[i] * r * r
        return s + ridge * sum((L[j] * nv[j]) ** 2 for j in range(n))

    qin = {"a": a_l, "b": inp["b"], "weights": inp["weights"], "_rv": [mp.mpf(inp.get("ridge", 0.0)) * mp.mpf(x) ** 2 for x in lots]}
    Hm = mp.matrix(n, n)
    for p in range(n):
        for q in range(n):
            Hm[p, q] = sum(mp.mpf(A[i][p].numerator) / A[i][p].denominator * w[i].numerator / w[i].denominator *
                           mp.mpf(A[i][q].numerator) / A[i][q].denominator for i in range(m))
        Hm[p, p] += mp.mpf(ridge.numerator) / ridge.denominator * (mp.mpf(L[p].numerator) / L[p].denominator) ** 2
    hev, _ = sym_eig(Hm)
    if decide(min(hev), max(abs(e) for e in hev), "integer Hessian"):
        fail("E_SINGULAR", "continuous problem not strictly convex")
    # continuous relaxation in lot space (bounds as reals) gives continuous_objective
    xr, _, cobj, _ = qp_core(dict(qin, lower=[None if v is None else float(v) for v in lo], upper=[None if v is None else float(v) for v in up]))
    # incumbent: relaxed solution rounded half away from zero, then clipped (any feasible point would do)
    inc = [int(mp.sign(v) * mp.floor(abs(v) + mp.mpf(0.5))) for v in xr]
    inc = [max(lo[j], v) if lo[j] is not None else v for j, v in enumerate(inc)]
    inc = [min(up[j], v) if up[j] is not None else v for j, v in enumerate(inc)]
    best = obj(inc)
    # unconstrained minimiser and ellipsoid box: f(n) - f* = (n - n*)' H (n - n*) <= best - f*
    xu, _, fstar, _ = qp_core(qin)
    Hi = Hm ** -1
    delta = mp.mpf(best.numerator) / best.denominator - fstar
    rad = [mp.sqrt(max(delta, 0) * Hi[j, j]) * (1 + mp.mpf("1e-20")) + mp.mpf("1e-20") for j in range(n)]
    rng = []
    for j in range(n):
        a0, a1 = int(mp.ceil(xu[j] - rad[j])), int(mp.floor(xu[j] + rad[j]))
        if lo[j] is not None:
            a0 = max(a0, lo[j])
        if up[j] is not None:
            a1 = min(a1, up[j])
        rng.append(range(a0, a1 + 1))
    size = math.prod(len(r) for r in rng)
    assert 0 < size <= 2_000_000, f"enumeration box {size}"
    scored = sorted(((obj(list(nv)), sum(abs(v) for v in nv), list(nv)) for nv in itertools.product(*rng)))
    fb = scored[0][0]
    # tie rule (I-7): objectives within 1e-12 relative are tied; then smaller sum |n|, then lexicographically smaller n
    tied = [s for s in scored if abs(s[0] - fb) <= Fr(1, 10 ** 12) * max(abs(fb), Fr(1, 10 ** 300))]
    win = min(tied, key=lambda s: (s[1], s[2]))
    rest = [s for s in scored if s not in tied]
    if rest:
        gap = (rest[0][0] - fb) / max(fb, Fr(1, 10 ** 300))
        assert gap > Fr(1, 10 ** 9), "near tie inside the I-7 margin"
    assert all(s[0] == fb for s in tied), "a tie that is not exact"
    nv = win[2]
    x = [float(Fr(lots[j]) * nv[j]) for j in range(n)]
    r = [b[i] + sum(A[i][j] * nv[j] for j in range(n)) for i in range(m)]
    o = obj(nv)
    return {"lots": nv, "x": x, "residual": [float(v) for v in r], "objective": float(o),
            "continuous_objective": fl(cobj), "rounding_cost": fl(mp.mpf(o.numerator) / o.denominator - cobj)}, len(tied), size


# ================================================================================================ hedge.minvar.ratio
def mv_ref(inp):
    cov, ex, hs = inp.get("covariance"), inp.get("exposure_changes"), inp.get("hedge_changes")
    if cov is not None and len(cov) > LIMITS["instruments"] + 1 or ex is not None and len(ex) > LIMITS["series"]:
        fail("E_LIMIT")
    finite_rule(inp)
    if (cov is None) == (ex is None and hs is None) or (ex is None) != (hs is None):
        fail("E_INPUT", "give covariance, or both series")
    if cov is not None:
        d = len(cov)
        if d < 2 or any(len(r) != d for r in cov):
            fail("E_INPUT", "covariance shape")
        S = M(cov)
        big = max(abs(x) for r in cov for x in r)
        if any(abs(cov[i][j] - cov[j][i]) > 1e-12 * big for i in range(d) for j in range(d)):
            fail("E_INPUT", "covariance not symmetric")
    else:
        T, k = len(ex), len(hs)
        if k < 1 or any(len(s) != T for s in hs):
            fail("E_INPUT", "series shape")
        if T < k + 2:
            fail("E_INPUT", "too few observations")
        X = [[mp.mpf(v) for v in ex]] + [[mp.mpf(v) for v in s] for s in hs]
        mu = [sum(r) / T for r in X]
        d = k + 1
        S = mp.matrix(d, d)
        for i in range(d):
            for j in range(d):
                S[i, j] = sum((X[i][t] - mu[i]) * (X[j][t] - mu[j]) for t in range(T)) / (T - 1)
    k = d - 1
    if S[0, 0] <= 0:
        fail("E_DOMAIN", "exposure variance not positive")
    Shh = mp.matrix([[S[i, j] for j in range(1, d)] for i in range(1, d)])
    she = mp.matrix([S[i, 0] for i in range(1, d)])
    # Cholesky pivot rule (I-8): a pivot at or below 1e-12 of the largest diagonal entry is singular
    dmax = max(Shh[i, i] for i in range(k))
    Lc = mp.matrix(k, k)
    for j in range(k):
        piv = Shh[j, j] - sum(Lc[j, p] ** 2 for p in range(j))
        if piv <= 0 or decide(piv, dmax, "minvar pivot"):
            fail("E_SINGULAR", "hedge covariance singular")
        Lc[j, j] = mp.sqrt(piv)
        for i in range(j + 1, k):
            Lc[i, j] = (Shh[i, j] - sum(Lc[i, p] * Lc[j, p] for p in range(j))) / Lc[j, j]
    h = -(Shh ** -1) * she
    after = S[0, 0] + (she.T * h)[0]
    if after < 0:
        assert after < -THRESH * MARGIN * S[0, 0]
        fail("E_NOT_POSITIVE_DEFINITE", "covariance not positive semi-definite")
    return {"hedge": [fl(v) for v in h], "variance_before": fl(S[0, 0]), "variance_after": fl(after),
            "effectiveness": fl(1 - after / S[0, 0])}


# ================================================================================================ hedge.greeks.neutralise
GREEKS = ("DELTA", "GAMMA", "VEGA")


def bs_greeks(S, r, q, v, ins):
    if ins["instrument"] == "UNDERLYING":
        return {"DELTA": mp.mpf(1), "GAMMA": mp.mpf(0), "VEGA": mp.mpf(0)}
    S, r, q, v, K, T = map(mp.mpf, (S, r, q, v, ins["strike"], ins["expiry_years"]))
    sq = v * mp.sqrt(T)
    d1 = (mp.log(S / K) + (r - q + v * v / 2) * T) / sq
    dq = mp.exp(-q * T)
    pdf = mp.npdf(d1)
    delta = dq * mp.ncdf(d1) if ins["instrument"] == "CALL" else -dq * mp.ncdf(-d1)
    return {"DELTA": delta, "GAMMA": dq * pdf / (S * sq), "VEGA": S * dq * pdf * mp.sqrt(T)}


def instr_check(ins, with_qty):
    keys = set(ins)
    if ins.get("instrument") == "UNDERLYING":
        if keys & {"strike", "expiry_years"}:
            fail("E_INPUT", "underlying takes no strike or expiry")
    elif not {"strike", "expiry_years"} <= keys:
        fail("E_INPUT", "option needs strike and expiry")


def gr_ref(inp):
    port, hed, tg = inp["portfolio"], inp["hedges"], inp["targets"]
    if len(port) > LIMITS["positions"] or len(hed) > 3:
        fail("E_LIMIT")
    finite_rule(inp)
    for p in port:
        instr_check(p, True)
    for h in hed:
        instr_check(h, False)
    if len(hed) == 0 or len(tg) != len(hed) or len(set(tg)) != len(tg):
        fail("E_INPUT", "targets and hedges")
    if inp["spot"] <= 0 or inp["volatility"] <= 0:
        fail("E_DOMAIN", "spot or volatility")
    for x in port + hed:
        if x["instrument"] != "UNDERLYING" and (x["strike"] <= 0 or x["expiry_years"] <= 0):
            fail("E_DOMAIN", "strike or expiry")
    S, r, q, v = inp["spot"], inp["rate"], inp["dividend_yield"], inp["volatility"]
    before = {g: sum(mp.mpf(p["quantity"]) * bs_greeks(S, r, q, v, p)[g] for p in port) for g in GREEKS}
    hg = [bs_greeks(S, r, q, v, h) for h in hed]
    Gm = mp.matrix([[hg[j][t] for j in range(len(hed))] for t in tg])
    U, Sv, V = mp.svd_r(Gm)
    sv = [Sv[i] for i in range(len(tg))]
    if decide(min(sv), max(sv), "greek matrix"):
        fail("E_SINGULAR", "hedge Greeks dependent")
    qv = mp.lu_solve(Gm, mp.matrix([-before[t] for t in tg]))
    after = {g: before[g] + sum(qv[j] * hg[j][g] for j in range(len(hed))) for g in GREEKS}
    return {"quantities": [fl(x) for x in qv], "greeks_before": {g.lower(): fl(before[g]) for g in GREEKS},
            "greeks_after": {g.lower(): fl(after[g]) for g in GREEKS}}


def ql_greeks(inp, ins):
    if ins["instrument"] == "UNDERLYING":
        return {"DELTA": 1.0, "GAMMA": 0.0, "VEGA": 0.0}
    dc, today = ql.Actual365Fixed(), ql.Date(11, 11, 2026)
    ql.Settings.instance().evaluationDate = today
    T = ins["expiry_years"]
    days = round(T * 365)
    assert abs(days - T * 365) < 1e-9, "expiry must be whole ACT/365F days for the QuantLib check"
    proc = ql.BlackScholesMertonProcess(ql.QuoteHandle(ql.SimpleQuote(inp["spot"])),
                                        ql.YieldTermStructureHandle(ql.FlatForward(today, inp["dividend_yield"], dc, ql.Continuous)),
                                        ql.YieldTermStructureHandle(ql.FlatForward(today, inp["rate"], dc, ql.Continuous)),
                                        ql.BlackVolTermStructureHandle(ql.BlackConstantVol(today, ql.NullCalendar(), inp["volatility"], dc)))
    opt = ql.EuropeanOption(ql.PlainVanillaPayoff(ql.Option.Call if ins["instrument"] == "CALL" else ql.Option.Put, ins["strike"]),
                            ql.EuropeanExercise(today + days))
    opt.setPricingEngine(ql.AnalyticEuropeanEngine(proc))
    return {"DELTA": opt.delta(), "GAMMA": opt.gamma(), "VEGA": opt.vega()}


# ================================================================================================ hedge.beta.futures
def half_away(x):
    return int(mp.sign(x) * mp.floor(abs(x) + mp.mpf(0.5)))


def beta_ref(inp):
    finite_rule(inp)
    rnd = inp.get("rounding", "NEAREST")
    if inp["portfolio_value"] <= 0 or inp["futures_price"] <= 0 or inp["multiplier"] <= 0:
        fail("E_DOMAIN", "value, price and multiplier positive")
    V, b0, bt, F, mlt = map(mp.mpf, (inp["portfolio_value"], inp["portfolio_beta"], inp["target_beta"], inp["futures_price"], inp["multiplier"]))
    N = (bt - b0) * V / (F * mlt)
    if rnd == "NEAREST":
        frac = abs(N) - mp.floor(abs(N))
        assert abs(frac - mp.mpf(0.5)) > mp.mpf("1e-9") or frac == mp.mpf(0.5), "rounding too close to a half"
    held = mp.mpf(half_away(N)) if rnd == "NEAREST" else N
    return {"contracts": fl(N), "contracts_held": fl(held), "beta_after": fl(b0 + held * F * mlt / V)}


# ================================================================================================ hedge.residual.report
def res_ref(inp):
    a, b, x, cov = inp["a"], inp["b"], inp["x"], inp["covariance"]
    m = len(a)
    if m > LIMITS["factors"] or (m and len(a[0]) > LIMITS["instruments"]):
        fail("E_LIMIT")
    finite_rule(inp)
    n = len(a[0]) if m else 0
    if m == 0 or n == 0 or any(len(r) != n for r in a) or len(b) != m or len(x) != n or len(cov) != m or any(len(r) != m for r in cov):
        fail("E_INPUT", "shape")
    big = max(abs(v) for r in cov for v in r)
    if any(abs(cov[i][j] - cov[j][i]) > 1e-12 * big for i in range(m) for j in range(m)):
        fail("E_INPUT", "covariance not symmetric")
    S = M(cov)
    ev, _ = sym_eig(S)
    emax = max(abs(e) for e in ev)
    if min(ev) < 0 and not decide(min(ev), emax, "covariance eigenvalue"):
        fail("E_NOT_POSITIVE_DEFINITE", "covariance has a negative eigenvalue")
    A = M(a)
    r = A * mp.matrix([mp.mpf(v) for v in x]) + mp.matrix([mp.mpf(v) for v in b])
    bb = mp.matrix([mp.mpf(v) for v in b])
    vb = (bb.T * S * bb)[0]
    if vb <= 0:
        fail("E_DOMAIN", "unhedged variance is zero")
    Sr = S * r
    va = (r.T * Sr)[0]
    return {"residual": [fl(v) for v in r], "variance_before": fl(vb), "variance_after": fl(va),
            "volatility_after": fl(mp.sqrt(max(va, 0))), "effectiveness": fl(1 - va / vb),
            "contributions": [fl(r[i] * Sr[i]) for i in range(m)]}


# ================================================================================================ cases
def run_error(s, op, ref, inp, want, desc, tags):
    try:
        ref(inp)
    except QfErr as e:
        assert e.code == want, f"{desc}: reached {e.code}, meant {want}"
        s.add(op, inp, error=e.code, cls=EX, verified=["reference-computed"], tags=["invalid"] + tags, description=desc)
        return
    raise AssertionError(f"{desc}: no error raised")


def qp_suite(reg):
    s = Suite("hedgeqp_i", SPEC, G)
    n_out = 0
    A3 = [[1.0, 0.5, 0.2], [0.3, 1.2, 0.4], [0.1, 0.6, 1.5], [0.8, 0.2, 0.9], [0.4, 0.9, 0.3]]
    b3 = [-2.0, 1.5, -0.7, 0.9, -1.1]
    w5 = [1.0, 2.0, 0.5, 1.5, 1.0]
    # key-rate style multi-instrument hedge: 5 key rates, 3 bonds (DV01 per 1 face, in thousands)
    KR = [[0.45, 0.10, 0.02], [0.30, 0.85, 0.15], [0.05, 0.70, 0.60], [0.0, 0.20, 1.10], [0.0, 0.02, 0.55]]
    bKR = [-12.0, -25.0, -31.0, -18.0, -7.5]
    cases = [
        ("weighted least squares, 5 factors and 3 instruments", dict(a=A3, b=b3, weights=w5)),
        ("unit weights", dict(a=A3, b=b3, weights=[1.0] * 5)),
        ("ridge 0.1", dict(a=A3, b=b3, weights=w5, ridge=0.1)),
        ("ridge 10, strong shrinkage", dict(a=A3, b=b3, weights=w5, ridge=10.0)),
        ("square exact hedge, zero residual", dict(a=[[1.0, 0.5], [0.2, 1.0]], b=[3.0, -1.0], weights=[1.0, 1.0])),
        ("single instrument, single factor (stage B form)", dict(a=[[0.8]], b=[-4.0], weights=[1.0])),
        ("single instrument, three factors", dict(a=[[1.0], [0.9], [1.2]], b=[-1.0, -1.1, -0.8], weights=[1.0, 1.0, 2.0])),
        ("key-rate hedge with three bonds", dict(a=KR, b=bKR, weights=[1.0] * 5)),
        ("key-rate hedge, long-only bounds bind", dict(a=KR, b=bKR, weights=[1.0] * 5, lower=[0.0, 0.0, 0.0], upper=[None, 20.0, None])),
        ("upper bound binds on one instrument", dict(a=A3, b=b3, weights=w5, upper=[0.5, None, None])),
        ("lower bounds bind on two instruments", dict(a=A3, b=b3, weights=w5, lower=[0.0, 0.0, 0.0])),
        ("box bounds, none binding", dict(a=A3, b=b3, weights=w5, lower=[-10.0] * 3, upper=[10.0] * 3)),
        ("fixed variable (lower = upper)", dict(a=A3, b=b3, weights=w5, lower=[None, 0.25, None], upper=[None, 0.25, None])),
        ("budget equality: positions sum to zero", dict(a=A3, b=b3, weights=w5, eq_matrix=[[1.0, 1.0, 1.0]], eq_rhs=[0.0])),
        ("equality and bounds together", dict(a=A3, b=b3, weights=w5, eq_matrix=[[1.0, 1.0, 1.0]], eq_rhs=[1.0], lower=[0.0, 0.0, 0.0])),
        ("two equalities leave one free direction", dict(a=A3, b=b3, weights=w5, eq_matrix=[[1.0, 0.0, -1.0], [0.0, 1.0, 1.0]], eq_rhs=[0.5, 0.2])),
        ("equalities fix every position (k = n)", dict(a=A3, b=b3, weights=w5, eq_matrix=[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]], eq_rhs=[0.1, -0.2, 0.3])),
        ("duplicate instruments, MIN_NORM splits evenly", dict(a=[[1.0, 1.0, 0.0], [0.5, 0.5, 1.0]], b=[-2.0, -1.0], weights=[1.0, 1.0], singular="MIN_NORM")),
        ("zero column, MIN_NORM leaves it at zero", dict(a=[[1.0, 0.0], [2.0, 0.0], [0.5, 0.0]], b=[1.0, -1.0, 2.0], weights=[1.0, 1.0, 1.0], singular="MIN_NORM")),
        ("more instruments than factors, MIN_NORM", dict(a=[[1.0, 0.4, 0.2, 0.7]], b=[-3.0], weights=[2.0], singular="MIN_NORM")),
        ("MIN_NORM on a regular problem equals the unique solution", dict(a=A3, b=b3, weights=w5, singular="MIN_NORM")),
        ("MIN_NORM with an equality on duplicate instruments", dict(a=[[1.0, 1.0, 0.3], [0.2, 0.2, 1.0]], b=[-1.0, 0.5], weights=[1.0, 1.0], eq_matrix=[[0.0, 0.0, 1.0]], eq_rhs=[0.1], singular="MIN_NORM")),
        ("singular A made regular by ridge", dict(a=[[1.0, 1.0, 0.0], [0.5, 0.5, 1.0]], b=[-2.0, -1.0], weights=[1.0, 1.0], ridge=1e-3)),
        ("duplicate instruments made regular by an equality", dict(a=[[1.0, 1.0, 0.0], [0.5, 0.5, 1.0]], b=[-2.0, -1.0], weights=[1.0, 1.0], eq_matrix=[[1.0, -1.0, 0.0]], eq_rhs=[0.0])),
        ("weights spanning six decades", dict(a=A3, b=b3, weights=[1e-3, 1.0, 1e3, 1.0, 10.0])),
        ("already hedged: b = 0 gives x = 0", dict(a=A3, b=[0.0] * 5, weights=w5)),
        ("negative zero in b is zero (F-3)", dict(a=[[1.0, 0.5], [0.2, 1.0]], b=[-0.0, 2.0], weights=[1.0, 1.0])),
    ]
    for desc, inp in cases:
        out = qp_ref(inp)
        kkt_check(inp, out)
        xl, lib = qp_outside(inp, out, 1e-10)
        ok = agrees(xl, out, inp, 1e-10)
        n_out += ok
        if not ok:
            note(f"  hedgeqp not counted ({lib}): {desc}")
        s.add(QP, inp, out, cls=RF, verified=["mpmath-50-active-set", "kkt-check"] + ([lib] if ok else []),
              output_classes={"rank": EX}, tags=["hedge", "qp"], description=desc)
    # MIN_NORM check: duplicate instruments split evenly
    assert abs(s.cases[17]["expected"]["outputs"]["x"][0] - s.cases[17]["expected"]["outputs"]["x"][1]) < 1e-15
    # mutants
    base = dict(a=A3, b=b3, weights=w5, upper=[0.5, None, None])
    o1 = qp_ref(base)["x"]
    o2 = qp_ref(dict(a=A3, b=b3, weights=w5))["x"]
    caught("bounds ignored (clip the free solution instead of re-solving)", max(abs(min(v, 0.5) - u) if j == 0 else abs(v - u) for j, (v, u) in enumerate(zip(o2, o1))))
    o3 = qp_ref(dict(a=A3, b=b3, weights=[1.0] * 5))["x"]
    caught("weights dropped", max(abs(p - q) for p, q in zip(o2, o3)))
    o4 = qp_ref(dict(a=A3, b=b3, weights=w5, ridge=0.1))["x"]
    caught("ridge ignored", max(abs(p - q) for p, q in zip(o2, o4)))
    # errors: every code computed by qp_ref
    e = dict(a=A3, b=b3, weights=w5)
    errs = [
        (dict(e, b=b3[:4]), "E_INPUT", "b shorter than a"),
        (dict(e, a=[[1.0, 0.5, 0.2], [0.3, 1.2]] + A3[2:]), "E_INPUT", "ragged a"),
        (dict(e, eq_matrix=[[1.0, 1.0, 1.0]]), "E_INPUT", "eq_matrix without eq_rhs"),
        (dict(e, lower=[0.0, 0.0]), "E_INPUT", "lower of the wrong length"),
        (dict(e, lower=[0.0, None, None], singular="MIN_NORM"), "E_INPUT", "MIN_NORM with a bound"),
        (dict(e, weights=[1.0, 0.0, 1.0, 1.0, 1.0]), "E_DOMAIN", "zero weight"),
        (dict(e, ridge=-0.1), "E_DOMAIN", "negative ridge"),
        (dict(e, lower=[1.0, None, None], upper=[0.5, None, None]), "E_DOMAIN", "lower above upper"),
        (dict(e, b=[-2.0, "NaN", -0.7, 0.9, -1.1]), "E_DOMAIN", "NaN in b (F-2)"),
        (dict(a=[[1.0, 1.0, 0.0], [0.5, 0.5, 1.0]], b=[-2.0, -1.0], weights=[1.0, 1.0]), "E_SINGULAR", "duplicate instruments, policy ERROR"),
        (dict(a=[[1.0, 0.0], [2.0, 0.0]], b=[1.0, 1.0], weights=[1.0, 1.0]), "E_SINGULAR", "zero column"),
        (dict(e, eq_matrix=[[1.0, 1.0, 1.0], [2.0, 2.0, 2.0]], eq_rhs=[0.0, 0.0]), "E_SINGULAR", "dependent equality rows"),
        (dict(e, eq_matrix=[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0], [1.0, 1.0, 1.0]], eq_rhs=[0.0] * 4), "E_SINGULAR", "more equalities than instruments"),
        (dict(e, eq_matrix=[[1.0, 1.0, 1.0]], eq_rhs=[5.0], upper=[1.0, 1.0, 1.0]), "E_INFEASIBLE", "budget above the sum of upper bounds"),
        (dict(e, eq_matrix=[[1.0, -1.0, 0.0]], eq_rhs=[2.0], lower=[0.0, 0.0, None], upper=[1.0, None, None]), "E_INFEASIBLE", "equality outside the box"),
        (dict(e, lower=[None, 1.0, None], upper=[None, 1.0, None], eq_matrix=[[0.0, 1.0, 0.0]], eq_rhs=[2.0]), "E_INFEASIBLE", "fixed variable against an equality"),
        (dict(a=[[1.0, 1.0, 0.0], [0.5, 0.5, 1.0]], b=[-2.0, -1.0], weights=[0.0, 1.0]), "E_DOMAIN", "zero weight before the singular test"),
    ]
    for inp, code, desc in errs:
        if code == "E_INFEASIBLE":
            assert infeasible_by_highs(inp), desc
        run_error(s, QP, qp_ref, inp, code, desc, ["hedge", "qp"])
    return s, n_out, "scipy 1.18 optimisers on the same problem (lsq_linear BVLS for bounds, linalg.lstsq gelsd for unconstrained and MIN_NORM, minimize SLSQP for equalities); every output within root_finding"


def int_suite(reg):
    s = Suite("hedgeint_i", SPEC, G)
    A3 = [[1.0, 0.5, 0.2], [0.3, 1.2, 0.4], [0.1, 0.6, 1.5], [0.8, 0.2, 0.9], [0.4, 0.9, 0.3]]
    b3 = [-20.0, 15.0, -7.0, 9.0, -11.0]
    w5 = [1.0, 2.0, 0.5, 1.5, 1.0]
    cases = [
        ("three instruments, unit lots", dict(a=A3, b=b3, weights=w5, lot_sizes=[1.0, 1.0, 1.0])),
        ("three instruments, mixed lots", dict(a=A3, b=b3, weights=w5, lot_sizes=[0.5, 2.0, 1.0])),
        ("lot bounds bind", dict(a=A3, b=b3, weights=w5, lot_sizes=[1.0, 1.0, 1.0], lower_lots=[-3, None, -1], upper_lots=[3, 2, None])),
        ("ridge with integer lots", dict(a=A3, b=b3, weights=w5, ridge=0.5, lot_sizes=[1.0, 1.0, 1.0])),
        ("single futures contract hedge (size 250)", dict(a=[[250.0]], b=[-3100.0], weights=[1.0], lot_sizes=[1.0])),
        ("single instrument, two weighted factors", dict(a=[[1.0], [1.0]], b=[-2.6, -1.0], weights=[1.0, 3.0], lot_sizes=[1.0])),
        ("exact tie between 0 and -1 lots: smaller sum |n| wins", dict(a=[[1.0]], b=[0.5], weights=[1.0], lot_sizes=[1.0])),
        ("exact tie between 1 and 2 lots: smaller sum |n| wins", dict(a=[[1.0]], b=[-1.5], weights=[1.0], lot_sizes=[1.0])),
        ("exact tie with equal sum |n|: lexicographically smaller", dict(a=[[1.0, 1.0]], b=[-1.0], weights=[1.0], ridge=0.25, lot_sizes=[1.0, 1.0])),
        ("rounding the relaxed solution is not optimal", dict(a=[[1.0, 0.95], [0.95, 1.0]], b=[-1.265, -1.27], weights=[1.0, 1.0], lot_sizes=[1.0, 1.0])),
        ("four instruments, key-rate style", dict(a=[[0.45, 0.10, 0.02, 0.0], [0.30, 0.85, 0.15, 0.05], [0.05, 0.70, 0.60, 0.2], [0.0, 0.20, 1.10, 0.7], [0.0, 0.02, 0.55, 1.2]],
                                                  b=[-12.0, -25.0, -31.0, -18.0, -7.5], weights=[1.0] * 5, lot_sizes=[1.0, 1.0, 1.0, 1.0])),
        ("zero exposure gives zero lots", dict(a=A3, b=[0.0] * 5, weights=w5, lot_sizes=[1.0, 1.0, 1.0])),
    ]
    tie_cases = 0
    for desc, inp in cases:
        out, ntied, size = int_ref(inp)
        if "tie" in desc and "not" not in desc:
            assert ntied > 1, desc
            tie_cases += 1
        else:
            assert ntied == 1, desc
        s.add(INT, inp, out, cls=RF, verified=["exact-rational-enumeration", "ellipsoid-bound"],
              output_classes={"lots": EX}, tags=["hedge", "integer"], description=f"{desc} (searched {size} points)")
    c10 = cases[9][1]
    naive = [half_away(v) for v in qp_ref({k: c10[k] for k in ("a", "b", "weights")})["x"]]
    assert s.cases[9]["expected"]["outputs"]["lots"] != naive, "case 10 must defeat naive rounding"
    fn = sum((bi + sum(ai[j] * naive[j] for j in range(2))) ** 2 for ai, bi in zip(c10["a"], c10["b"]))
    caught("naive rounding of the relaxed solution", fn - s.cases[9]["expected"]["outputs"]["objective"])
    e = dict(a=A3, b=b3, weights=w5, lot_sizes=[1.0, 1.0, 1.0])
    errs = [
        (dict(e, lot_sizes=[1.0, 1.0]), "E_INPUT", "lot_sizes of the wrong length"),
        (dict(e, lot_sizes=[1.0, 0.0, 1.0]), "E_DOMAIN", "zero lot size"),
        (dict(e, lower_lots=[2, None, None], upper_lots=[1, None, None]), "E_DOMAIN", "lower lots above upper lots"),
        (dict(a=[[1.0, 1.0]], b=[-1.0], weights=[1.0], lot_sizes=[1.0, 1.0]), "E_SINGULAR", "duplicate instruments without ridge"),
        (dict(a=[[1.0] * 13], b=[-1.0], weights=[1.0], lot_sizes=[1.0] * 13), "E_LIMIT", "13 instruments (limit 12)"),
        (dict(e, weights=[1.0, -1.0, 1.0, 1.0, 1.0]), "E_DOMAIN", "negative weight"),
    ]
    for inp, code, desc in errs:
        run_error(s, INT, lambda i: int_ref(i)[0], inp, code, desc, ["hedge", "integer"])
    return s, 0, "no outside library solves integer least squares; uncounted (exact rational enumeration is the oracle)"


def mv_suite(reg):
    s = Suite("hedgemv_i", SPEC, G)
    n_out = 0
    ex = [0.012, -0.008, 0.015, 0.003, -0.011, 0.007, -0.002, 0.009, -0.013, 0.004, 0.006, -0.005]
    h1 = [0.010, -0.006, 0.013, 0.001, -0.010, 0.008, -0.001, 0.007, -0.012, 0.005, 0.004, -0.006]
    h2 = [0.002, 0.001, -0.003, 0.004, 0.000, -0.002, 0.003, 0.001, -0.001, 0.002, -0.004, 0.001]
    cases = [
        ("Hull-style single hedge from a covariance: rho sigma_S / sigma_F", dict(covariance=[[0.0263 ** 2, 0.928 * 0.0263 * 0.0313], [0.928 * 0.0263 * 0.0313, 0.0313 ** 2]])),
        ("two hedge instruments from a covariance", dict(covariance=[[0.04, 0.018, 0.006], [0.018, 0.0225, 0.003], [0.006, 0.003, 0.01]])),
        ("uncorrelated hedge: ratio 0, no reduction", dict(covariance=[[0.04, 0.0], [0.0, 0.09]])),
        ("perfectly correlated hedge: effectiveness 1", dict(covariance=[[0.04, 0.06], [0.06, 0.09]])),
        ("three hedge instruments", dict(covariance=[[0.05, 0.02, 0.01, -0.005], [0.02, 0.03, 0.004, 0.0], [0.01, 0.004, 0.02, 0.002], [-0.005, 0.0, 0.002, 0.015]])),
        ("single hedge from return series", dict(exposure_changes=ex, hedge_changes=[h1])),
        ("two hedges from return series", dict(exposure_changes=ex, hedge_changes=[h1, h2])),
        ("series with the minimum length k + 2", dict(exposure_changes=ex[:3], hedge_changes=[h1[:3]])),
        ("short position in the exposure (negative covariance)", dict(covariance=[[0.04, -0.018], [-0.018, 0.0225]])),
    ]
    for desc, inp in cases:
        out = mv_ref(inp)
        if "covariance" in inp:
            C = np.array(inp["covariance"])
            hl = -np.linalg.solve(C[1:, 1:], C[1:, 0])
            lib = "numpy-2.5-solve"
        else:
            Xh = np.column_stack([np.ones(len(inp["exposure_changes"]))] + [np.array(h) for h in inp["hedge_changes"]])
            hl = -np.linalg.lstsq(Xh, np.array(inp["exposure_changes"]), rcond=None)[0][1:]
            lib = "numpy-2.5-lstsq-ols"
        ok = all(abs(p - q) <= 1e-10 + 1e-10 * abs(q) for p, q in zip(hl, out["hedge"]))
        n_out += ok
        s.add(MV, inp, out, cls=RF, verified=["mpmath-50"] + ([lib] if ok else []), tags=["hedge", "minvar"], description=desc)
    # Hull's single-instrument formula h = rho sigma_S / sigma_F (sign: units held are -h)
    assert abs(-s.cases[0]["expected"]["outputs"]["hedge"][0] - 0.928 * 0.0263 / 0.0313) < 1e-14
    o = mv_ref(dict(exposure_changes=ex, hedge_changes=[h1]))
    o_pop = (np.cov(ex, h1, ddof=0)[0, 0])
    caught("population divisor for the variances", abs(o["variance_before"] - o_pop), 1e-12)
    e = dict(covariance=[[0.04, 0.018], [0.018, 0.0225]])
    errs = [
        (dict(e, exposure_changes=ex), "E_INPUT", "covariance and a series together"),
        (dict(exposure_changes=ex), "E_INPUT", "exposure series without hedge series"),
        (dict(covariance=[[0.04, 0.018], [0.0185, 0.0225]]), "E_INPUT", "covariance not symmetric"),
        (dict(exposure_changes=ex[:2], hedge_changes=[h1[:2]]), "E_INPUT", "fewer than k + 2 observations"),
        (dict(covariance=[[0.0, 0.0], [0.0, 0.0225]]), "E_DOMAIN", "zero exposure variance"),
        (dict(covariance=[[0.04, 0.01, 0.01], [0.01, 0.0225, 0.0225], [0.01, 0.0225, 0.0225]]), "E_SINGULAR", "two identical hedge instruments"),
        (dict(covariance=[[0.04, 0.0], [0.0, 0.0]]), "E_SINGULAR", "hedge with zero variance"),
        (dict(covariance=[[0.04, 0.05], [0.05, 0.0225]]), "E_NOT_POSITIVE_DEFINITE", "correlation above 1 (variance after below 0)"),
    ]
    for inp, code, desc in errs:
        run_error(s, MV, mv_ref, inp, code, desc, ["hedge", "minvar"])
    return s, n_out, "numpy 2.5 linalg.solve on the hedge block (covariance input) and linalg.lstsq OLS with intercept (series input); hedge within root_finding; variances are arithmetic"


def gr_suite(reg):
    s = Suite("hedgegreeks_i", SPEC, G)
    n_out = 0
    mkt = dict(spot=100.0, rate=0.03, dividend_yield=0.01, volatility=0.25)
    port = [{"instrument": "CALL", "strike": 100.0, "expiry_years": 182 / 365, "quantity": -1000.0},
            {"instrument": "PUT", "strike": 90.0, "expiry_years": 1.0, "quantity": 500.0}]
    U = {"instrument": "UNDERLYING"}
    c1 = {"instrument": "CALL", "strike": 105.0, "expiry_years": 91 / 365}
    p2 = {"instrument": "PUT", "strike": 95.0, "expiry_years": 2.0}
    cases = [
        ("delta hedge with the underlying", dict(mkt, portfolio=port, hedges=[U], targets=["DELTA"])),
        ("delta-gamma hedge: underlying and a call", dict(mkt, portfolio=port, hedges=[U, c1], targets=["DELTA", "GAMMA"])),
        ("delta-gamma-vega hedge: underlying, call, long put", dict(mkt, portfolio=port, hedges=[U, c1, p2], targets=["DELTA", "GAMMA", "VEGA"])),
        ("vega hedge only with a long-dated put", dict(mkt, portfolio=port, hedges=[p2], targets=["VEGA"])),
        ("gamma-vega hedge with two options, delta left", dict(mkt, portfolio=port, hedges=[c1, p2], targets=["GAMMA", "VEGA"])),
        ("targets listed in another order", dict(mkt, portfolio=port, hedges=[c1, U], targets=["GAMMA", "DELTA"])),
        ("short-dated deep in-the-money call book", dict(mkt, portfolio=[{"instrument": "CALL", "strike": 70.0, "expiry_years": 37 / 365, "quantity": 200.0}], hedges=[U], targets=["DELTA"])),
        ("portfolio holding the underlying", dict(mkt, portfolio=port + [{"instrument": "UNDERLYING", "quantity": 300.0}], hedges=[U, c1], targets=["DELTA", "GAMMA"])),
        ("zero rates and dividends", dict(mkt, rate=0.0, dividend_yield=0.0, portfolio=port, hedges=[U, c1], targets=["DELTA", "GAMMA"])),
        ("negative rate", dict(mkt, rate=-0.005, portfolio=port, hedges=[U, c1, p2], targets=["DELTA", "GAMMA", "VEGA"])),
    ]
    for desc, inp in cases:
        out = gr_ref(inp)
        scale = max(abs(v) for v in out["greeks_before"].values())
        lim = {"absolute": 1e-10 * max(1.0, scale), "relative": 1e-10, "reason": "targeted Greeks after hedging are zero up to rounding of the before value"}
        qg = [ql_greeks(inp, h) for h in inp["hedges"]]
        Gq = np.array([[g[t] for g in qg] for t in inp["targets"]])
        bq = {t: sum(p["quantity"] * ql_greeks(inp, p)[t] for p in inp["portfolio"]) for t in GREEKS}
        ql_q = np.linalg.solve(Gq, -np.array([bq[t] for t in inp["targets"]]))
        ok = all(abs(p - q) <= 1e-10 + 1e-10 * abs(q) for p, q in zip(ql_q, out["quantities"])) and \
            all(abs(bq[t] - out["greeks_before"][t.lower()]) <= lim["absolute"] + 1e-10 * abs(bq[t]) for t in GREEKS)
        n_out += ok
        if not ok:
            note(f"  hedgegreeks not counted: {desc} {ql_q} {out['quantities']}")
        s.add(GR, inp, out, cls=RF, limit=lim, verified=["mpmath-50"] + (["quantlib-1.44-analytic-european", "numpy-2.5-solve"] if ok else []),
              tags=["hedge", "greeks"], description=desc)
    o = gr_ref(cases[1][1])
    caught("delta without the dividend discount exp(-qT)", abs(o["quantities"][0] - gr_ref(dict(cases[1][1], dividend_yield=0.0))["quantities"][0]), 1e-6)
    e = dict(mkt, portfolio=port, hedges=[U, c1], targets=["DELTA", "GAMMA"])
    errs = [
        (dict(e, targets=["DELTA"]), "E_INPUT", "fewer targets than hedges"),
        (dict(e, targets=["DELTA", "DELTA"]), "E_INPUT", "repeated target"),
        (dict(e, hedges=[{"instrument": "UNDERLYING", "strike": 100.0}, c1]), "E_INPUT", "underlying with a strike"),
        (dict(e, hedges=[U, {"instrument": "CALL", "strike": 105.0}]), "E_INPUT", "option without an expiry"),
        (dict(e, volatility=0.0), "E_DOMAIN", "zero volatility"),
        (dict(e, hedges=[U, dict(c1, strike=-5.0)]), "E_DOMAIN", "negative strike"),
        (dict(e, hedges=[U, {"instrument": "UNDERLYING"}]), "E_SINGULAR", "underlying twice: no gamma"),
        (dict(e, hedges=[c1, dict(c1)]), "E_SINGULAR", "the same call twice"),
        (dict(e, hedges=[U, U, U, U], targets=["DELTA", "GAMMA", "VEGA", "DELTA"]), "E_LIMIT", "four hedges (limit 3)"),
    ]
    for inp, code, desc in errs:
        run_error(s, GR, gr_ref, inp, code, desc, ["hedge", "greeks"])
    return s, n_out, "QuantLib 1.44 AnalyticEuropeanEngine delta, gamma and vega per instrument, then numpy 2.5 linalg.solve; quantities and before-Greeks within root_finding"


def beta_suite(reg):
    s = Suite("hedgebeta_i", SPEC, G)
    base = dict(portfolio_value=5_050_000.0, portfolio_beta=1.5, target_beta=0.0, futures_price=1010.0, multiplier=250.0)
    cases = [
        ("Hull's example: beta 1.5 to 0, 30 contracts short", base),
        ("halve the beta", dict(base, target_beta=0.75)),
        ("raise the beta (long futures)", dict(base, target_beta=2.0)),
        ("no rounding", dict(base, target_beta=0.43, rounding="NONE")),
        ("rounding to nearest, fraction above a half", dict(base, target_beta=0.47)),
        ("exact half rounds away from zero", dict(portfolio_value=1_000_000.0, portfolio_beta=1.0, target_beta=0.0, futures_price=4000.0, multiplier=100.0)),
        ("negative beta portfolio", dict(base, portfolio_beta=-0.3)),
        ("target equals beta: no contracts", dict(base, target_beta=1.5)),
    ]
    for desc, inp in cases:
        s.add(BETA, inp, beta_ref(inp), cls=SA, output_classes={"contracts_held": SA}, verified=["mpmath-50"], tags=["hedge", "beta"], description=desc)
    assert s.cases[0]["expected"]["outputs"]["contracts_held"] == -30.0
    assert s.cases[5]["expected"]["outputs"]["contracts_held"] == -3.0 and s.cases[5]["expected"]["outputs"]["contracts"] == -2.5
    caught("round half to even (banker's) at -2.5", abs(s.cases[5]["expected"]["outputs"]["contracts_held"] - round(-2.5)))
    e = base
    errs = [(dict(e, futures_price=0.0), "E_DOMAIN", "zero futures price"), (dict(e, multiplier=-250.0), "E_DOMAIN", "negative multiplier"),
            (dict(e, portfolio_value=0.0), "E_DOMAIN", "zero portfolio value"), (dict(e, portfolio_beta="Infinity"), "E_DOMAIN", "infinite beta (F-2)")]
    for inp, code, desc in errs:
        run_error(s, BETA, beta_ref, inp, code, desc, ["hedge", "beta"])
    return s, 0, "no outside library; Hull's worked example (30 contracts) is a textbook check, not counted"


def res_suite(reg):
    s = Suite("hedgeres_i", SPEC, G)
    A3 = [[1.0, 0.5, 0.2], [0.3, 1.2, 0.4], [0.1, 0.6, 1.5]]
    b3 = [-2.0, 1.5, -0.7]
    cov = [[1e-4, 4e-5, 1e-5], [4e-5, 9e-5, 3e-5], [1e-5, 3e-5, 1.6e-4]]
    xq = qp_ref(dict(a=A3, b=b3, weights=[1.0] * 3))["x"]
    cases = [
        ("exact hedge from the QP: residual near zero", dict(a=A3, b=b3, x=xq, covariance=cov)),
        ("partial hedge", dict(a=A3, b=b3, x=[1.0, -0.5, 0.2], covariance=cov)),
        ("no hedge: effectiveness 0", dict(a=A3, b=b3, x=[0.0, 0.0, 0.0], covariance=cov)),
        ("over-hedge: effectiveness below 0", dict(a=A3, b=b3, x=[6.0, -4.0, 2.0], covariance=cov)),
        ("diagonal covariance", dict(a=A3, b=b3, x=[1.0, -0.5, 0.2], covariance=[[1e-4, 0, 0], [0, 9e-5, 0], [0, 0, 1.6e-4]])),
        ("singular PSD covariance (one factor)", dict(a=A3, b=b3, x=[1.0, -0.5, 0.2], covariance=[[1.0, 2.0, 3.0], [2.0, 4.0, 6.0], [3.0, 6.0, 9.0]])),
        ("one instrument, two factors", dict(a=[[1.0], [0.8]], b=[-1.0, -0.5], x=[0.7], covariance=[[1.0, 0.5], [0.5, 1.0]])),
    ]
    for desc, inp in cases:
        out = res_ref(inp)
        assert abs(sum(out["contributions"]) - out["variance_after"]) <= 1e-12 * (1 + abs(out["variance_after"]))
        s.add(RES, inp, out, cls=RF, limit={"absolute": 1e-12, "relative": 1e-10, "reason": "residual of an exact hedge is rounding noise"} if "exact" in desc else None,
              verified=["mpmath-50", "euler-sum"], tags=["hedge", "residual"], description=desc)
    e = dict(a=A3, b=b3, x=[1.0, -0.5, 0.2], covariance=cov)
    errs = [(dict(e, x=[1.0, 0.0]), "E_INPUT", "x of the wrong length"),
            (dict(e, covariance=[[1e-4, 4e-5, 1e-5], [4e-5, 9e-5, 3e-5], [2e-5, 3e-5, 1.6e-4]]), "E_INPUT", "covariance not symmetric"),
            (dict(e, covariance=[[1.0, 2.0, 0.0], [2.0, 1.0, 0.0], [0.0, 0.0, 1.0]]), "E_NOT_POSITIVE_DEFINITE", "covariance with eigenvalue -1"),
            (dict(e, b=[0.0, 0.0, 0.0]), "E_DOMAIN", "zero unhedged variance")]
    for inp, code, desc in errs:
        run_error(s, RES, res_ref, inp, code, desc, ["hedge", "residual"])
    return s, 0, "arithmetic only; no library model value, uncounted"


def main():
    keep = common.GOLDEN
    common.GOLDEN = keep.parent / FOLDER
    reg_p = HERE.parent / "outside_register_i.json"
    reg = json.loads(reg_p.read_text(encoding="utf-8")) if reg_p.exists() else {}  # later waves keep their rows
    tot = cnt = 0
    for fn in (qp_suite, int_suite, mv_suite, gr_suite, beta_suite, res_suite):
        s, n_out, rule = fn(reg)
        for c in s.cases:
            c["tags"].append("synthetic")
        s.write()
        reg[s.name] = {"counted": n_out, "total": len(s.cases), "rule": rule}
        tot += len(s.cases)
        cnt += n_out
        note(f"{s.name}: {len(s.cases)} cases, outside {n_out}")
    common.GOLDEN = keep
    reg["_wave1"] = {"counted": cnt, "total": tot, "share": round(cnt / tot, 4), "floor": 0.60,
                     "note": "Floor is measured over the stage at release, error cases in the denominator (ruling I-2)"}
    reg_p.write_text(json.dumps(reg, indent=1) + "\n", encoding="utf-8", newline="\n")
    note(f"wave 1 outside: {cnt} of {tot} = {100 * cnt / tot:.1f}%")
    for m_, g in MUTANTS:
        note(f"  mutant caught: {m_} (gap {g:.3e})")


if __name__ == "__main__":
    main()
