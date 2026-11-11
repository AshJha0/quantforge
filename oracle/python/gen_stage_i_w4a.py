"""Stage I wave 4a: costs, market impact and margin in `hedge.qp.solve`, and the risk-against-cost frontier
(specifications/08-hedging/hedge-costs-and-frontier.md, rulings I-24 on).

`qp4_ref` extends the wave 1 reference. With none of the new inputs it must return exactly the wave 1 golden, and it is
run on every `hedgeqp_i` case to assert that (ruling I-13: the cost wave adds inputs without changing meaning).

Solver: enumerate, per instrument, the state P (x > 0), N (x < 0), Z (x = 0), L (at lower), U (at upper), and whether the
margin constraint is active; solve each state's KKT system at 50 digits; keep the states whose signs, bounds, margin and
subgradient conditions hold; exactly one x must survive (the smooth part is strictly convex). Infeasibility is confirmed by
HiGHS on the split-variable LP. Outside: scipy 1.18 trust-constr on the split variables (x = p - n, p, n >= 0);
SLSQP was tried first and stalls near 1e-8.

    cd oracle/python && uv run python -W ignore gen_stage_i_w4a.py
"""
import itertools
import json
import math
from pathlib import Path

import mpmath as mp
import numpy as np
import scipy.optimize as so

import gen_stage_i_w1 as W
from gen_stage_i_w1 import fail, decide, run_error, sym_eig, M, RF, EX  # noqa: F401
from qf_oracle import common
from qf_oracle.common import Suite, note

mp.mp.dps = 50
G = "oracle/python/gen_stage_i_w4a.py"
SPEC = "specifications/08-hedging/hedge-costs-and-frontier.md"
HERE = Path(__file__).resolve().parent
QP, FR = "hedge.qp.solve", "hedge.frontier.solve"
NEW = ("half_spreads", "impact", "cost_weight", "margin_rates", "margin_limit")
MUT = []


def validate4(inp):
    """Wave 1 checks, then the new ones (I-24 order)."""
    m, n, E, f, lo, up, pol = W.qp_validate(inp)
    hs, im, mr = inp.get("half_spreads"), inp.get("impact"), inp.get("margin_rates")
    for v in (hs, im, mr):
        if v is not None and len(v) != n:
            fail("E_INPUT", "cost or margin length")
    if (mr is None) != ("margin_limit" not in inp):
        fail("E_INPUT", "margin_rates and margin_limit go together")
    if pol == "MIN_NORM" and any(k in inp for k in NEW):
        fail("E_INPUT", "MIN_NORM with costs or margin")
    if any(x < 0 for x in (hs or []) + (im or []) + (mr or [])) or inp.get("cost_weight", 1.0) < 0 or inp.get("margin_limit", 0.0) < 0:
        fail("E_DOMAIN", "negative cost, impact, margin or weight")
    return m, n, E, f, lo, up, pol


def qp4_core(inp):
    if not any(k in inp for k in NEW):
        return W.qp_core(inp)
    m, n, E, f, lo, up, pol = validate4(inp)
    A, b, w = M(inp["a"]), [mp.mpf(x) for x in inp["b"]], [mp.mpf(x) for x in inp["weights"]]
    lam = mp.mpf(inp.get("cost_weight", 1.0))
    hs = [mp.mpf(x) for x in inp.get("half_spreads", [0.0] * n)]
    eta = [mp.mpf(x) for x in inp.get("impact", [0.0] * n)]
    mr = [mp.mpf(x) for x in inp["margin_rates"]] if "margin_rates" in inp else None
    Mlim = mp.mpf(inp.get("margin_limit", 0.0))
    ridge = mp.mpf(inp.get("ridge", 0.0))
    k = len(E)
    # smooth part: x' Hs x + 2 c' x, Hs = A'WA + ridge I + lam diag(eta)
    Hs = mp.matrix(n, n)
    c = mp.matrix(n, 1)
    for i in range(m):
        for p in range(n):
            c[p] += A[i, p] * w[i] * b[i]
            for q in range(n):
                Hs[p, q] += A[i, p] * w[i] * A[i, q]
    for p in range(n):
        Hs[p, p] += ridge + lam * eta[p]
    if k:
        U_, S_, V_ = mp.svd_r(M(E), full_matrices=True)
        sv = [S_[i] for i in range(min(k, n))]
        if k > n or decide(min(sv), max(sv), "equality rank"):
            fail("E_SINGULAR", "equality rows dependent")
        Z = V_.T[:, k:] if k < n else None
    else:
        Z = mp.eye(n)
    hev, _ = sym_eig(Hs)
    hmax = max(abs(e) for e in hev)
    rank = 0
    if Z is not None:
        rev, _ = sym_eig(Z.T * Hs * Z)
        zero = [decide(e, hmax, "reduced Hessian") for e in rev]
        rank = sum(1 for z in zero if not z)
        if any(zero):
            fail("E_SINGULAR", "reduced Hessian singular")
    x = enumerate_states(Hs, c, E, f, lo, up, hs, lam, mr, Mlim, n)
    if x is None:
        fail("E_INFEASIBLE", "no feasible point")
    r = A * x + mp.matrix(b)
    risk = sum(w[i] * r[i] ** 2 for i in range(m)) + ridge * sum(x[p] ** 2 for p in range(n))
    cost = sum(hs[p] * abs(x[p]) + eta[p] * x[p] ** 2 for p in range(n))
    out = {"x": x, "r": r, "risk": risk, "cost": cost, "rank": rank, "lam": lam}
    if mr is not None:
        out["margin"] = sum(mr[p] * abs(x[p]) for p in range(n))
    return out


def enumerate_states(Hs, c, E, f, lo, up, hs, lam, mr, Mlim, n):
    k = len(E)
    tiny = mp.mpf("1e-35")
    found = []
    opts = []
    for j in range(n):
        o = ["P", "N"]
        if (lo[j] is None or lo[j] < 0) and (up[j] is None or up[j] > 0):
            o.append("Z")
        if lo[j] is not None:
            o.append("L")
        if up[j] is not None:
            o.append("U")
        opts.append(o)
    for st in itertools.product(*opts):
        for act in ((False, True) if mr is not None else (False,)):
            free = [j for j in range(n) if st[j] in "PN"]
            fixed = {j: (mp.mpf(0) if st[j] == "Z" else mp.mpf(lo[j]) if st[j] == "L" else mp.mpf(up[j])) for j in range(n) if st[j] not in "PN"}
            s = {j: (1 if st[j] == "P" else -1) for j in free}
            nf = len(free)
            sz = nf + k + (1 if act else 0)
            Kmat = mp.matrix(sz, sz)
            rhs = mp.matrix(sz, 1)
            # stationarity on free coords: 2 (Hs x + c)_j + lam h_j s_j + E' l + mu m_j s_j = 0
            for a_, j in enumerate(free):
                for b_, q in enumerate(free):
                    Kmat[a_, b_] = 2 * Hs[j, q]
                rhs[a_] = -2 * c[j] - lam * hs[j] * s[j] - 2 * sum(Hs[j, q] * v for q, v in fixed.items())
                for r_ in range(k):
                    Kmat[a_, nf + r_] = mp.mpf(E[r_][j])
                if act:
                    Kmat[a_, nf + k] = mr[j] * s[j]
            for r_ in range(k):
                for b_, q in enumerate(free):
                    Kmat[nf + r_, b_] = mp.mpf(E[r_][q])
                rhs[nf + r_] = mp.mpf(f[r_]) - sum(mp.mpf(E[r_][q]) * v for q, v in fixed.items())
            if act:
                for b_, q in enumerate(free):
                    Kmat[nf + k, b_] = mr[q] * s[q]
                rhs[nf + k] = Mlim - sum(mr[q] * abs(v) for q, v in fixed.items())
            if sz:
                try:
                    sol = mp.lu_solve(Kmat, rhs)
                except ZeroDivisionError:
                    continue
            else:
                sol = mp.matrix(0, 1)
            x = [fixed.get(j, mp.mpf(0)) for j in range(n)]
            for a_, j in enumerate(free):
                x[j] = sol[a_]
            lmb = [sol[nf + r_] for r_ in range(k)]
            mu = sol[nf + k] if act else mp.mpf(0)
            if any(x[j] * s[j] <= tiny for j in free):
                continue
            if any(lo[j] is not None and x[j] < lo[j] - tiny or up[j] is not None and x[j] > up[j] + tiny for j in range(n)):
                continue
            if mr is not None:
                mg = sum(mr[j] * abs(x[j]) for j in range(n))
                if (not act and mg > Mlim + tiny) or (act and mu < -tiny):
                    continue
            # subgradient conditions on fixed coords
            ok = True
            for j, v in fixed.items():
                g = 2 * (sum(Hs[j, q] * x[q] for q in range(n)) + c[j]) + sum(mp.mpf(E[r_][j]) * lmb[r_] for r_ in range(k))
                kink = lam * hs[j] + (mu * mr[j] if mr is not None else 0)
                if st[j] == "Z":
                    ok &= abs(g) <= kink + tiny
                elif st[j] == "L":
                    sp = 1 if v >= 0 else -1  # right derivative of |x| at v
                    ok &= g + kink * sp >= -tiny
                else:
                    sm = 1 if v > 0 else -1  # left derivative of |x| at v
                    ok &= g + kink * sm <= tiny
            if not ok:
                continue
            if not any(max(abs(x[p] - y[p]) for p in range(n)) < mp.mpf("1e-30") for y in found):
                found.append(x)
    if not found:
        return None
    assert len(found) == 1, f"{len(found)} optimal points"
    return mp.matrix(found[0])


def qp4_ref(inp):
    if not any(k in inp for k in NEW):
        return W.qp_ref(inp)
    o = qp4_core(inp)
    out = {"x": [float(v) for v in o["x"]], "residual": [float(v) for v in o["r"]], "objective": float(o["risk"] + o["lam"] * o["cost"]),
           "rank": o["rank"], "risk": float(o["risk"]), "cost": float(o["cost"])}
    if "margin" in o:
        out["margin"] = float(o["margin"])
    return out


def trust_constr(inp):
    """scipy trust-constr on the split form z = (p, n), x = p - n, p, n >= 0: a smooth QP with linear constraints.
    (SLSQP was tried first and stalls near 1e-8 here, above the root_finding tolerance.)"""
    A, b, w = np.array(inp["a"]), np.array(inp["b"]), np.array(inp["weights"])
    n = A.shape[1]
    lam = inp.get("cost_weight", 1.0)
    hs = np.array(inp.get("half_spreads", [0.0] * n))
    eta = np.array(inp.get("impact", [0.0] * n))
    Hs = A.T @ (w[:, None] * A) + inp.get("ridge", 0.0) * np.eye(n) + lam * np.diag(eta)
    c = A.T @ (w * b)
    Q = 2 * np.block([[Hs, -Hs], [-Hs, Hs]])
    q = np.concatenate([2 * c + lam * hs, -2 * c + lam * hs])
    rows, lo_, up_ = [], [], []
    for r_, v in zip(inp.get("eq_matrix") or [], inp.get("eq_rhs") or []):
        rows.append(list(r_) + [-x for x in r_]); lo_.append(v); up_.append(v)  # noqa: E702
    lo, up = inp.get("lower") or [None] * n, inp.get("upper") or [None] * n
    for j in range(n):
        if lo[j] is not None or up[j] is not None:
            e = [0.0] * (2 * n)
            e[j], e[n + j] = 1.0, -1.0
            rows.append(e); lo_.append(-np.inf if lo[j] is None else lo[j]); up_.append(np.inf if up[j] is None else up[j])  # noqa: E702
    if "margin_rates" in inp:
        rows.append(list(inp["margin_rates"]) * 2); lo_.append(-np.inf); up_.append(inp["margin_limit"])  # noqa: E702
    cons = [so.LinearConstraint(np.array(rows), lo_, up_)] if rows else []
    r = so.minimize(lambda z: 0.5 * z @ Q @ z + q @ z, np.zeros(2 * n), jac=lambda z: Q @ z + q, hess=lambda z: Q, method="trust-constr",
                    bounds=so.Bounds(np.zeros(2 * n), np.full(2 * n, np.inf)), constraints=cons, options={"gtol": 1e-15, "xtol": 1e-16, "maxiter": 20000})
    return r.x[:n] - r.x[n:]


def slsqp(inp):
    """scipy SLSQP on the same split form, three warm restarts."""
    A, b, w = np.array(inp["a"]), np.array(inp["b"]), np.array(inp["weights"])
    n = A.shape[1]
    lam = inp.get("cost_weight", 1.0)
    hs = np.array(inp.get("half_spreads", [0.0] * n))
    eta = np.array(inp.get("impact", [0.0] * n))
    Hs = A.T @ (w[:, None] * A) + inp.get("ridge", 0.0) * np.eye(n) + lam * np.diag(eta)
    c = A.T @ (w * b)
    Q = 2 * np.block([[Hs, -Hs], [-Hs, Hs]])
    q = np.concatenate([2 * c + lam * hs, -2 * c + lam * hs])
    cons = []
    for r_, v in zip(inp.get("eq_matrix") or [], inp.get("eq_rhs") or []):
        rr = np.array(list(r_) + [-x for x in r_])
        cons.append({"type": "eq", "fun": lambda z, rr=rr, v=v: rr @ z - v, "jac": lambda z, rr=rr: rr})
    lo, up = inp.get("lower") or [None] * n, inp.get("upper") or [None] * n
    for j in range(n):
        e = np.zeros(2 * n)
        e[j], e[n + j] = 1, -1
        if lo[j] is not None:
            cons.append({"type": "ineq", "fun": lambda z, e=e, l=lo[j]: e @ z - l, "jac": lambda z, e=e: e})
        if up[j] is not None:
            cons.append({"type": "ineq", "fun": lambda z, e=e, u=up[j]: u - e @ z, "jac": lambda z, e=e: -e})
    if "margin_rates" in inp:
        mm = np.array(list(inp["margin_rates"]) * 2)
        cons.append({"type": "ineq", "fun": lambda z: inp["margin_limit"] - mm @ z, "jac": lambda z: -mm})
    z = np.zeros(2 * n)
    for _ in range(3):
        z = so.minimize(lambda z: 0.5 * z @ Q @ z + q @ z, z, jac=lambda z: Q @ z + q, method="SLSQP", bounds=[(0, None)] * (2 * n),
                        constraints=cons, options={"ftol": 1e-16, "maxiter": 2000}).x
    return z[:n] - z[n:]


def bvls(inp):
    """Exact for problems with no spread cost, no margin and no equality: impact and ridge are extra least-squares rows."""
    if inp.get("half_spreads") or "margin_rates" in inp or inp.get("eq_matrix"):
        return None
    A, b, w = np.array(inp["a"]), np.array(inp["b"]), np.array(inp["weights"])
    n = A.shape[1]
    d = inp.get("ridge", 0.0) + inp.get("cost_weight", 1.0) * np.array(inp.get("impact", [0.0] * n))
    At = np.vstack([A * np.sqrt(w)[:, None], np.diag(np.sqrt(d))])
    bt = np.concatenate([b * np.sqrt(w), np.zeros(n)])
    lo, up = inp.get("lower") or [None] * n, inp.get("upper") or [None] * n
    lb = np.array([-np.inf if v is None else v for v in lo])
    ub = np.array([np.inf if v is None else v for v in up])
    if np.all(np.isinf(lb)) and np.all(np.isinf(ub)):
        return np.linalg.lstsq(At, -bt, rcond=None)[0]
    return so.lsq_linear(At, -bt, bounds=(lb, ub), method="bvls", tol=1e-15, lsq_solver="exact").x


def outside(inp, out):
    """Name of the first library solver that agrees with every x, or None."""
    for name, fn in (("scipy-1.18-bvls-or-lstsq", bvls), ("scipy-1.18-trust-constr-split", trust_constr), ("scipy-1.18-slsqp-split", slsqp)):
        x = fn(inp)
        if x is not None and agrees(x, out):
            return name
    return None


def agrees(x, out, tol=1e-10):
    return all(abs(p - q) <= tol + tol * abs(q) for p, q in zip(x, out["x"]))


def infeasible_by_highs(inp):
    n = len(inp["a"][0])
    lo, up = inp.get("lower") or [None] * n, inp.get("upper") or [None] * n
    Aeq = [list(r) + [-v for v in r] for r in inp.get("eq_matrix") or []]
    Aub, bub = [], []
    for j in range(n):
        e = [0.0] * (2 * n)
        e[j], e[n + j] = 1.0, -1.0
        if lo[j] is not None:
            Aub.append([-v for v in e]); bub.append(-lo[j])  # noqa: E702
        if up[j] is not None:
            Aub.append(e); bub.append(up[j])  # noqa: E702
    if "margin_rates" in inp:
        Aub.append(list(inp["margin_rates"]) * 2); bub.append(inp["margin_limit"])  # noqa: E702
    res = so.linprog(np.zeros(2 * n), A_ub=np.array(Aub) if Aub else None, b_ub=np.array(bub) if bub else None,
                     A_eq=np.array(Aeq) if Aeq else None, b_eq=np.array(inp["eq_rhs"]) if Aeq else None, bounds=[(0, None)] * (2 * n), method="highs")
    return res.status == 2


# ================================================================================================ hedge.frontier.solve
def fr_ref(inp):
    cw = inp["cost_weights"]
    if len(cw) > 50:
        fail("E_LIMIT")
    W.finite_rule(inp)
    base = {k: v for k, v in inp.items() if k != "cost_weights"}
    if "cost_weight" in inp:
        fail("E_INPUT", "cost_weight with cost_weights")
    if not cw or any(b <= a for a, b in zip(cw, cw[1:])):
        fail("E_INPUT", "cost_weights empty or not increasing")
    if "half_spreads" not in inp and "impact" not in inp:
        fail("E_INPUT", "a frontier needs costs")
    pts = []
    for lam in cw:
        o = qp4_ref(dict(base, cost_weight=lam))
        pts.append({"cost_weight": lam, "x": o["x"], "risk": o["risk"], "cost": o["cost"]})
    return {"points": pts}


# ================================================================================================ suites
def qp_cost_suite():
    # ruling I-13 self-check: every wave 1 golden is reproduced exactly by the extended reference
    w1 = json.loads((HERE.parents[1] / "datasets" / "golden" / W.FOLDER / "hedgeqp_i.json").read_text(encoding="utf-8"))
    for c in w1["cases"]:
        try:
            got = {"status": "ok", "outputs": qp4_ref(c["inputs"])}
        except W.QfErr as e:
            got = {"status": "error", "error_code": e.code}
        assert got == c["expected"], c["case_id"]
    s = Suite("hedgecost_i", SPEC, G)
    A3 = [[1.0, 0.5, 0.2], [0.3, 1.2, 0.4], [0.1, 0.6, 1.5], [0.8, 0.2, 0.9], [0.4, 0.9, 0.3]]
    b3 = [-2.0, 1.5, -0.7, 0.9, -1.1]
    w5 = [1.0, 2.0, 0.5, 1.5, 1.0]
    base = dict(a=A3, b=b3, weights=w5)
    cases = [
        ("half-spread cost shrinks every position", dict(base, half_spreads=[0.05, 0.05, 0.05])),
        ("a costly instrument is left out (x = 0)", dict(base, half_spreads=[0.01, 5.0, 0.01])),
        ("cost weight 0 equals the wave 1 answer", dict(base, half_spreads=[0.3, 0.3, 0.3], cost_weight=0.0)),
        ("cost weight 4", dict(base, half_spreads=[0.05, 0.1, 0.02], cost_weight=4.0)),
        ("linear impact only (quadratic cost)", dict(base, impact=[0.5, 0.5, 2.0])),
        ("spread and impact together", dict(base, half_spreads=[0.05, 0.1, 0.02], impact=[0.2, 0.2, 0.2])),
        ("liquidity caps as bounds, with costs", dict(base, half_spreads=[0.02, 0.02, 0.02], lower=[-0.6, -0.4, -0.4], upper=[0.6, 0.4, 0.4])),
        ("margin limit binds", dict(base, margin_rates=[0.1, 0.2, 0.15], margin_limit=0.2)),
        ("margin limit slack", dict(base, margin_rates=[0.1, 0.2, 0.15], margin_limit=10.0)),
        ("margin, costs and a budget equality", dict(base, half_spreads=[0.02, 0.02, 0.02], margin_rates=[0.1, 0.1, 0.1], margin_limit=0.15, eq_matrix=[[1.0, 1.0, 1.0]], eq_rhs=[0.0])),
        ("margin binds with a bound at a positive level", dict(base, lower=[0.5, None, None], margin_rates=[0.2, 0.1, 0.1], margin_limit=0.2)),
        ("singular A made regular by impact", dict(a=[[1.0, 1.0, 0.0], [0.5, 0.5, 1.0]], b=[-2.0, -1.0], weights=[1.0, 1.0], impact=[0.1, 0.1, 0.1])),
        ("cost on a fixed position", dict(base, half_spreads=[0.1, 0.1, 0.1], lower=[None, -0.3, None], upper=[None, -0.3, None])),
    ]
    n_out = 0
    for desc, inp in cases:
        out = qp4_ref(inp)
        lib = outside(inp, out)
        ok = lib is not None
        n_out += ok
        if not ok:
            note(f"  hedgecost not counted: {desc}")
        s.add(QP, inp, out, cls=RF, output_classes={"rank": EX}, verified=["mpmath-50-state-enumeration"] + ([lib] if ok else []),
              tags=["hedge", "qp", "cost"], description=desc)
    o = {c["description"]: c["expected"]["outputs"] for c in s.cases}
    assert o["a costly instrument is left out (x = 0)"]["x"][1] == 0.0
    assert o["cost weight 0 equals the wave 1 answer"]["x"] == W.qp_ref(base)["x"]
    assert abs(o["margin limit binds"]["margin"] - 0.2) < 1e-15
    caught("costs ignored", max(abs(p - q) for p, q in zip(o["half-spread cost shrinks every position"]["x"], W.qp_ref(base)["x"])))
    caught("margin constraint ignored", max(abs(p - q) for p, q in zip(o["margin limit binds"]["x"], W.qp_ref(base)["x"])))
    e = dict(base, half_spreads=[0.05, 0.05, 0.05])
    errs = [
        (dict(e, half_spreads=[0.05, 0.05]), "E_INPUT", "half_spreads of the wrong length"),
        (dict(base, margin_rates=[0.1, 0.1, 0.1]), "E_INPUT", "margin_rates without margin_limit"),
        (dict(e, singular="MIN_NORM"), "E_INPUT", "MIN_NORM with costs"),
        (dict(e, half_spreads=[0.05, -0.01, 0.05]), "E_DOMAIN", "negative half-spread"),
        (dict(e, cost_weight=-1.0), "E_DOMAIN", "negative cost weight"),
        (dict(base, margin_rates=[0.1, 0.1, 0.1], margin_limit=-1.0), "E_DOMAIN", "negative margin limit"),
        (dict(a=[[1.0, 1.0, 0.0], [0.5, 0.5, 1.0]], b=[-2.0, -1.0], weights=[1.0, 1.0], half_spreads=[0.1, 0.1, 0.1]), "E_SINGULAR", "spread cost does not make a singular problem regular"),
        (dict(base, margin_rates=[0.1, 0.1, 0.1], margin_limit=0.05, lower=[1.0, None, None]), "E_INFEASIBLE", "a bound needs more margin than the limit"),
        (dict(base, margin_rates=[0.1, 0.1, 0.1], margin_limit=0.05, eq_matrix=[[1.0, 0.0, 0.0]], eq_rhs=[-1.0]), "E_INFEASIBLE", "an equality needs more margin than the limit"),
    ]
    for inp, code, desc in errs:
        if code == "E_INFEASIBLE":
            assert infeasible_by_highs(inp), desc
        run_error(s, QP, qp4_ref, inp, code, desc, ["hedge", "qp", "cost"])
    # I-54 (after the builds): an instrument exactly at its hold/not-hold switch (|g_1| = cost_weight h_1 at x_1 = 0)
    sw = dict(a=[[1.0, 0.0], [0.0, 1.0]], b=[-1.0, -2.0], weights=[1.0, 1.0], half_spreads=[2.0, 0.5])
    so_ = qp4_ref(sw)
    assert so_["x"] == [0.0, 1.75], so_
    lib = outside(sw, so_)
    n_out += lib is not None
    s.add(QP, sw, so_, cls=RF, output_classes={"rank": EX}, verified=["mpmath-50-state-enumeration"] + ([lib] if lib else []),
          tags=["hedge", "qp", "cost"], description="instrument 1 exactly at its switch point: x_1 = 0 exactly (I-54, after the builds)")
    return s, n_out, "scipy 1.18 solvers on the same problem, first that agrees: lsq_linear BVLS or lstsq (no spread, margin or equality: exact), minimize trust-constr, minimize SLSQP (both on the split form x = p - n, p, n >= 0); x within root_finding; verified_by names the solver"


def caught(name, gap, tol=1e-9):
    assert gap > tol, f"mutant '{name}' is not caught: gap {gap:.3e}"
    MUT.append((name, float(gap)))


def frontier_suite():
    s = Suite("hedgefrontier_i", SPEC, G)
    A3 = [[1.0, 0.5, 0.2], [0.3, 1.2, 0.4], [0.1, 0.6, 1.5], [0.8, 0.2, 0.9], [0.4, 0.9, 0.3]]
    base = dict(a=A3, b=[-2.0, 1.5, -0.7, 0.9, -1.1], weights=[1.0, 2.0, 0.5, 1.5, 1.0])
    KR = [[0.45, 0.10, 0.02], [0.30, 0.85, 0.15], [0.05, 0.70, 0.60], [0.0, 0.20, 1.10], [0.0, 0.02, 0.55]]
    cases = [
        ("spread-cost frontier, seven points", dict(base, half_spreads=[0.05, 0.1, 0.02], cost_weights=[0.0, 0.5, 1.0, 2.0, 5.0, 10.0, 50.0])),
        ("impact-only frontier", dict(base, impact=[0.5, 0.5, 2.0], cost_weights=[0.0, 0.1, 1.0, 10.0])),
        ("key-rate hedge frontier with long-only bounds", dict(a=KR, b=[-12.0, -25.0, -31.0, -18.0, -7.5], weights=[1.0] * 5, lower=[0.0, 0.0, 0.0],
                                                               half_spreads=[0.02, 0.03, 0.05], impact=[0.001, 0.001, 0.002], cost_weights=[0.0, 1.0, 10.0, 100.0])),
        ("frontier with a binding margin", dict(base, half_spreads=[0.05, 0.1, 0.02], margin_rates=[0.1, 0.2, 0.15], margin_limit=0.2, cost_weights=[0.0, 1.0, 10.0])),
    ]
    n_out = 0
    for desc, inp in cases:
        out = fr_ref(inp)
        pts = out["points"]
        # frontier self-check: risk non-decreasing and cost non-increasing in the cost weight
        assert all(b["risk"] >= a["risk"] - 1e-12 and b["cost"] <= a["cost"] + 1e-12 for a, b in zip(pts, pts[1:])), desc
        libs = [outside(dict({k: v for k, v in inp.items() if k != "cost_weights"}, cost_weight=p["cost_weight"]), p) for p in pts]
        ok = all(libs)
        n_out += ok
        if not ok:
            note(f"  hedgefrontier not counted: {desc}")
        s.add(FR, inp, out, cls=RF, verified=["mpmath-50-state-enumeration", "monotone-frontier"] + (sorted(set(libs)) if ok else []),
              tags=["hedge", "frontier"], description=desc)
    e = dict(base, half_spreads=[0.05, 0.1, 0.02], cost_weights=[0.0, 1.0])
    errs = [
        (dict(e, cost_weights=[1.0, 1.0]), "E_INPUT", "cost weights not increasing"),
        (dict(e, cost_weights=[]), "E_INPUT", "no cost weights"),
        (dict(base, cost_weights=[0.0, 1.0]), "E_INPUT", "a frontier without costs"),
        (dict(e, cost_weight=1.0), "E_INPUT", "cost_weight with cost_weights"),
        (dict(e, cost_weights=[-1.0, 1.0]), "E_DOMAIN", "negative cost weight"),
        (dict(e, cost_weights=[float(i) for i in range(51)]), "E_LIMIT", "51 points (limit 50)"),
    ]
    for inp, code, desc in errs:
        run_error(s, FR, fr_ref, inp, code, desc, ["hedge", "frontier"])
    return s, n_out, "the hedgecost_i solver list at every frontier point; a case counts if every point's x agrees within root_finding"


def main():
    keep = common.GOLDEN
    common.GOLDEN = keep.parent / W.FOLDER
    reg_p = HERE.parent / "outside_register_i.json"
    reg = json.loads(reg_p.read_text(encoding="utf-8"))
    for s, n_out, rule in (qp_cost_suite(), frontier_suite()):
        for c in s.cases:
            c["tags"].append("synthetic")
        s.write()
        reg[s.name] = {"counted": n_out, "total": len(s.cases), "rule": rule}
        note(f"{s.name}: {len(s.cases)} cases, outside {n_out}")
    common.GOLDEN = keep
    suites = {k: v for k, v in reg.items() if not k.startswith("_")}
    cnt, tot = sum(v["counted"] for v in suites.values()), sum(v["total"] for v in suites.values())
    reg["_stage"] = {"counted": cnt, "total": tot, "share": round(cnt / tot, 4), "floor": 0.60,
                     "note": "Stage I so far, error cases in the denominator (ruling I-2); the floor applies at release"}
    reg_p.write_text(json.dumps(reg, indent=1) + "\n", encoding="utf-8", newline="\n")
    note(f"stage I outside so far: {cnt} of {tot} = {100 * cnt / tot:.1f}%")
    for m_, g in MUT:
        note(f"  mutant caught: {m_} (gap {g:.3e})")


if __name__ == "__main__":
    main()
