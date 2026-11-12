"""R6 wave 3, R6-6: hedge solver at size (finding 7). Suite r6/hedgeqp_large_r6: `hedge.qp.solve` at n = 50 and n = 200 with
half-spreads, impact, a margin limit, equalities and bounds; plus the R6-6.2 column-scaling cases.

Method (oracle, not a language build):
1. HiGHS 1.16 (highspy) solves the convex QP in split variables x = p - q, p, q >= 0 (costs and margin linear there).
2. The sign state (positive, negative, zero, at a bound) and the margin activity are read off the HiGHS answer.
3. On that state the KKT system is linear in (x_free, lambda, mu); it is solved in binary64 and refined three times with
   residuals evaluated in 40-digit mpmath straight from A, W, b (no Hessian is formed in low precision).
4. The KKT conditions are then checked with a margin: free positions keep their sign, zero positions satisfy the
   subgradient bound strictly, bound and margin multipliers are strictly positive. A draw that fails the margin (a
   degenerate state, where builds could legitimately differ) is rejected; rejection never looks at a build's output.
5. Outside check (R6-6 acceptance): HiGHS's own x agrees with the exact x within its tolerance, and the KKT residual of
   the exact x on the split form is below 1e-9 relative to the gradient scale (recorded per case).

    cd oracle/python && uv run python -W ignore gen_r6_w3.py
"""
import json
import math
import sys
import time

import mpmath as mp
import numpy as np

from qf_oracle import common
from qf_oracle.common import Suite, note

G = "oracle/python/gen_r6_w3.py"
E = "date_and_convention"
mp.mp.dps = 40
SLACK = 1e-6
REPORT = []


def r6(v):
    return float(f"{v:.6g}")


def highs_split(P):
    import highspy
    A, b, w, lo, up = P["A"], P["b"], P["w"], P["lo"], P["up"]
    n = A.shape[1]
    H = A.T @ (w[:, None] * A) + P["ridge"] * np.eye(n) + P["cw"] * np.diag(P["impact"])
    gq = 2 * A.T @ (w * b)
    hs = P["cw"] * P["hs"]
    h = highspy.Highs()
    h.setOptionValue("output_flag", False)
    for k, v in (("primal_feasibility_tolerance", 1e-10), ("dual_feasibility_tolerance", 1e-10)):
        h.setOptionValue(k, v)
    inf = highspy.kHighsInf
    h.addVars(2 * n, np.zeros(2 * n), np.full(2 * n, inf))
    h.changeColsCost(2 * n, np.arange(2 * n, dtype=np.int32), np.concatenate([gq + hs, -gq + hs]))
    rows = []
    for j in range(n):
        if lo[j] is not None or up[j] is not None:
            rows.append(({j: 1.0, n + j: -1.0}, -inf if lo[j] is None else lo[j], inf if up[j] is None else up[j]))
    for i in range(P["E"].shape[0]):
        d = {j: P["E"][i, j] for j in range(n)}
        d.update({n + j: -P["E"][i, j] for j in range(n)})
        rows.append((d, P["e"][i], P["e"][i]))
    if P["mr"] is not None:
        d = {j: P["mr"][j] for j in range(n)}
        d.update({n + j: P["mr"][j] for j in range(n)})
        rows.append((d, -inf, P["L"]))
    for d, l_, u_ in rows:
        idx = np.array(sorted(d), dtype=np.int32)
        h.addRow(l_, u_, len(idx), idx, np.array([d[k] for k in idx]))
    Q = 2 * np.block([[H, -H], [-H, H]])
    start, index, value = [], [], []
    for c in range(2 * n):
        start.append(len(index))
        for r in range(c, 2 * n):
            if Q[r, c] != 0.0:
                index.append(r)
                value.append(Q[r, c])
    hess = highspy.HighsHessian()
    hess.dim_ = 2 * n
    hess.format_ = highspy.HessianFormat.kTriangular
    hess.start_ = np.array(start + [len(index)], dtype=np.int32)
    hess.index_ = np.array(index, dtype=np.int32)
    hess.value_ = np.array(value)
    h.passHessian(hess)
    h.run()
    st = h.modelStatusToString(h.getModelStatus())
    z = np.array(h.getSolution().col_value)
    return st, z[:n] - z[n:]


def mpvec(v):
    return [mp.mpf(float(x)) for x in v]


class Exact:
    """KKT on a fixed state, refined in mpmath."""

    def __init__(self, P):
        self.P = P
        self.n = P["A"].shape[1]
        self.Am = [mpvec(r) for r in P["A"]]
        self.bm, self.wm = mpvec(P["b"]), mpvec(P["w"])

    def grad(self, x):
        """2 (A^T W (A x + b) + ridge x + cw impact x), in mpmath."""
        P, n = self.P, self.n
        r = [mp.fsum(a * xj for a, xj in zip(row, x)) + bi for row, bi in zip(self.Am, self.bm)]
        wr = [wi * ri for wi, ri in zip(self.wm, r)]
        g = [2 * mp.fsum(self.Am[i][j] * wr[i] for i in range(len(wr))) for j in range(n)]
        return [g[j] + 2 * mp.mpf(P["ridge"]) * x[j] + 2 * mp.mpf(P["cw"]) * mp.mpf(float(P["impact"][j])) * x[j] for j in range(n)], r

    def solve(self, state, x0, margin_active):
        """state[j] in {'+', '-', '0', 'L', 'U'}. Unknowns: x_F, lambda (k), mu (if margin active)."""
        P, n = self.P, self.n
        F = [j for j in range(n) if state[j] in "+-"]
        k = P["E"].shape[0]
        fixed = {j: (0.0 if state[j] == "0" else (P["lo"][j] if state[j] == "L" else P["up"][j])) for j in range(n) if state[j] not in "+-"}
        s = {j: (1.0 if state[j] == "+" else -1.0) for j in F}
        x = [mp.mpf(float(fixed[j])) if j in fixed else mp.mpf(float(x0[j])) for j in range(n)]
        lam = [mp.mpf(0)] * k
        mu = mp.mpf(0)
        H = self.P["A"].T @ (P["w"][:, None] * self.P["A"]) + P["ridge"] * np.eye(n) + P["cw"] * np.diag(P["impact"])
        nf, na = len(F), len(F) + k + (1 if margin_active else 0)
        K = np.zeros((na, na))
        K[:nf, :nf] = 2 * H[np.ix_(F, F)]
        if k:
            K[:nf, nf:nf + k] = P["E"][:, F].T
            K[nf:nf + k, :nf] = P["E"][:, F]
        if margin_active:
            mrF = np.array([P["mr"][j] * s[j] for j in F])
            K[:nf, -1] = mrF
            K[-1, :nf] = mrF
        hs, cw = P["hs"], P["cw"]
        for _ in range(4):
            g, _r = self.grad(x)
            Elam = [mp.fsum(mp.mpf(float(P["E"][i, j])) * lam[i] for i in range(k)) for j in range(n)]
            res = []
            for j in F:
                res.append(g[j] + Elam[j] + mp.mpf(cw * hs[j]) * s[j] + (mu * mp.mpf(float(P["mr"][j])) * s[j] if margin_active else 0))
            for i in range(k):
                res.append(mp.fsum(mp.mpf(float(P["E"][i, j])) * x[j] for j in range(n)) - mp.mpf(float(P["e"][i])))
            if margin_active:
                res.append(mp.fsum(mp.mpf(float(P["mr"][j])) * abs(x[j]) for j in range(n)) - mp.mpf(float(P["L"])))
            d = np.linalg.solve(K, -np.array([float(v) for v in res]))
            for t, j in enumerate(F):
                x[j] += mp.mpf(d[t])
            for i in range(k):
                lam[i] += mp.mpf(d[nf + i])
            if margin_active:
                mu += mp.mpf(d[-1])
        worst = max((abs(float(v)) for v in res), default=0.0)
        return x, lam, mu, worst

    def check(self, state, x, lam, mu, margin_active):
        """Strict KKT with SLACK; returns (ok, why, multipliers)."""
        P, n = self.P, self.n
        g, r = self.grad(x)
        k = P["E"].shape[0]
        Elam = [mp.fsum(mp.mpf(float(P["E"][i, j])) * lam[i] for i in range(k)) for j in range(n)]
        scale = max(1.0, max(abs(float(v)) for v in g))
        cw, hs = P["cw"], P["hs"]
        mr = P["mr"] if P["mr"] is not None else np.zeros(n)
        mu_f = float(mu) if margin_active else 0.0
        if margin_active and mu_f <= SLACK * scale:
            return False, f"margin multiplier {mu_f:.2e} not strictly positive"
        if P["mr"] is not None and not margin_active:
            used = sum(mr[j] * abs(float(x[j])) for j in range(n))
            if used >= P["L"] * (1 - SLACK):
                return False, "margin inactive but at its limit"
        for j in range(n):
            gj = float(g[j] + Elam[j])
            st = state[j]
            if st in "+-":
                if (float(x[j]) > SLACK) != (st == "+") or abs(float(x[j])) <= SLACK:
                    return False, f"free {j} lost its sign"
                if (P["lo"][j] is not None and float(x[j]) <= P["lo"][j] + SLACK) or (P["up"][j] is not None and float(x[j]) >= P["up"][j] - SLACK):
                    return False, f"free {j} at a bound"
            elif st == "0":
                if abs(gj) >= cw * hs[j] + mu_f * mr[j] - SLACK * scale:
                    return False, f"zero {j} subgradient not strict"
            else:
                sgn = 1.0 if float(x[j]) > 0 else -1.0
                m_ = -(gj + cw * hs[j] * sgn + mu_f * mr[j] * sgn)  # multiplier of x_j <= up (U) is m_; of x_j >= lo (L) is -m_
                mult = m_ if st == "U" else -m_
                if mult <= SLACK * scale:
                    return False, f"bound {j} multiplier {mult:.2e} not strictly positive"
        return True, "ok"


def state_of(P, x, margin_used):
    n = len(x)
    sc = max(1.0, float(np.max(np.abs(x))))
    st = []
    for j in range(n):
        if P["up"][j] is not None and abs(x[j] - P["up"][j]) <= 1e-7 * sc:
            st.append("U")
        elif P["lo"][j] is not None and abs(x[j] - P["lo"][j]) <= 1e-7 * sc:
            st.append("L")
        elif abs(x[j]) <= 1e-7 * sc:
            st.append("0")
        else:
            st.append("+" if x[j] > 0 else "-")
    active = P["mr"] is not None and margin_used >= P["L"] * (1 - 1e-7)
    return st, active


def draw(rng, n, m, k, costs=True, margin=True, bounds=True):
    A = np.array([[r6(v) for v in row] for row in rng.normal(0, 1, (m, n)) / math.sqrt(n)])
    b = np.array([r6(v) for v in rng.normal(0, 1, m)])
    w = np.array([r6(v) for v in rng.uniform(0.5, 2.0, m)])
    hs = np.array([r6(v) if rng.uniform() > 0.2 else 0.0 for v in rng.uniform(0.0, 0.05, n)]) if costs else np.zeros(n)
    imp = np.array([r6(v) for v in rng.uniform(0.0, 0.02, n)]) if costs else np.zeros(n)
    Em = np.array([[1.0] * n] + [[r6(v) for v in rng.normal(0, 1, n)] for _ in range(k - 1)]) if k else np.zeros((0, n))
    e = np.array([0.0] + [r6(v) for v in rng.normal(0, 0.5, k - 1)]) if k else np.zeros(0)
    P = dict(A=A, b=b, w=w, ridge=0.0, cw=1.0, hs=hs, impact=imp, E=Em, e=e, lo=[None] * n, up=[None] * n, mr=None, L=None)
    st, x = highs_split(P)
    assert st == "Optimal", st
    if bounds:
        u = np.quantile(np.abs(x), 0.85)
        P["lo"] = [r6(-u * rng.uniform(0.8, 1.5)) for _ in range(n)]
        P["up"] = [r6(u * rng.uniform(0.8, 1.5)) for _ in range(n)]
        st, x = highs_split(P)
    if margin:
        P["mr"] = np.array([r6(v) for v in rng.uniform(0.05, 0.2, n)])
        P["L"] = r6(0.6 * float(P["mr"] @ np.abs(x)))
    return P


def inputs_of(P):
    n = P["A"].shape[1]
    inp = {"a": P["A"].tolist(), "b": P["b"].tolist(), "weights": P["w"].tolist()}
    if P["E"].shape[0]:
        inp["eq_matrix"], inp["eq_rhs"] = P["E"].tolist(), P["e"].tolist()
    if any(v is not None for v in P["lo"]):
        inp["lower"], inp["upper"] = list(P["lo"]), list(P["up"])
    if np.any(P["hs"]) or np.any(P["impact"]):
        inp["half_spreads"], inp["impact"] = P["hs"].tolist(), P["impact"].tolist()
    if P["mr"] is not None:
        inp["margin_rates"], inp["margin_limit"] = P["mr"].tolist(), P["L"]
    assert len(inp["a"][0]) == n
    return inp


def solve_case(P):
    st, xh = highs_split(P)
    assert st == "Optimal", st
    used = float(P["mr"] @ np.abs(xh)) if P["mr"] is not None else 0.0
    state, active = state_of(P, xh, used)
    ex = Exact(P)
    x, lam, mu, worst = ex.solve(state, xh, active)
    ok, why = ex.check(state, x, lam, mu, active)
    if not ok:
        return None, why
    g, r = ex.grad(x)
    n = len(x)
    xf = [float(v) for v in x]
    risk = mp.fsum(wi * ri * ri for wi, ri in zip(ex.wm, r)) + P["ridge"] * mp.fsum(v * v for v in x)
    cost = mp.fsum(mp.mpf(float(P["hs"][j])) * abs(x[j]) + mp.mpf(float(P["impact"][j])) * x[j] ** 2 for j in range(n))
    out = {"x": xf, "residual": [float(v) for v in r], "objective": float(risk + P["cw"] * cost), "rank": n - P["E"].shape[0],
           "risk": float(risk), "cost": float(cost)}
    if P["mr"] is not None:
        out["margin"] = float(mp.fsum(mp.mpf(float(P["mr"][j])) * abs(x[j]) for j in range(n)))
    gap = float(np.max(np.abs(np.array(xf) - xh)))
    kkt = worst / max(1.0, max(abs(float(v)) for v in g))
    assert kkt < 1e-9, kkt
    meta = {"highs_gap": gap, "kkt_residual_rel": kkt, "states": {s: state.count(s) for s in "+-0LU"}, "margin_active": active}
    return out, meta


def qp_large():
    s = Suite("hedgeqp_large_r6", "specifications/08-hedging/hedge-costs-and-frontier.md", G)
    s.compact = True
    plan = [(50, 80, 0, dict(margin=False, bounds=False), "n = 50, costs only"),
            (50, 80, 0, dict(bounds=False), "n = 50, costs and margin"),
            (50, 80, 3, dict(), "n = 50, costs, margin, 3 equalities, bounds"),
            (200, 250, 3, dict(), "n = 200, costs, margin, 3 equalities, bounds"),
            (200, 250, 3, dict(margin=False), "n = 200, costs, 3 equalities, bounds, no margin")]
    rng = np.random.default_rng(20261112)
    for n, m, k, kw, d in plan:
        rej = 0
        while True:
            t0 = time.time()
            P = draw(rng, n, m, k, **kw)
            out, meta = solve_case(P)
            if out is not None:
                break
            rej += 1
            note(f"  {d}: draw rejected ({meta})")
        note(f"hedgeqp_large_r6 {d}: states {meta['states']}, margin active {meta['margin_active']}, HiGHS gap {meta['highs_gap']:.1e}, "
             f"KKT residual {meta['kkt_residual_rel']:.1e}, rejected {rej}, {time.time() - t0:.0f}s")
        REPORT.append(dict(description=d, **meta, rejected=rej))
        s.add("hedge.qp.solve", inputs_of(P), out, cls="root_finding", output_classes={"rank": E},
              verified=["exact-kkt-mpmath-40 on the HiGHS state", f"highspy-1.16-qp-split (x within {meta['highs_gap']:.0e}, KKT residual {meta['kkt_residual_rel']:.0e})"],
              tags=["r6", "hedge", "qp", "cost", "large", "synthetic"], description=d)
    return s


# ---------------------------------------------------------------------------------- R6-6.2 scaling before the rank decision
def exact_wls(A, b, w, ridge=0.0):
    A = mp.matrix(A); n = A.cols
    W = mp.diag(w)
    H = A.T * W * A + ridge * mp.eye(n)
    x = -mp.lu_solve(H, A.T * W * mp.matrix(b))
    return [x[j] for j in range(n)], H


def scaled_ratio(H):
    n = H.rows
    d = [1 / mp.sqrt(H[j, j]) for j in range(n)]
    S = mp.matrix(n, n)
    for i in range(n):
        for j in range(n):
            S[i, j] = d[i] * H[i, j] * d[j]
    ev = mp.eigsy(S)[0]
    return min(abs(v) for v in ev) / max(abs(v) for v in ev)


def raw_ratio(H):
    ev = mp.eigsy(H)[0]
    return min(abs(v) for v in ev) / max(abs(v) for v in ev)


def scaling():
    s = Suite("hedgescale_r6", "specifications/08-hedging/hedge-solvers.md", G)
    base_A = [[1.0, 0.5, 0.2], [0.3, 1.2, 0.4], [0.1, 0.6, 1.5], [0.8, 0.2, 0.9]]
    b = [-2.0, 1.5, -0.7, 0.9]
    cases = [("column 3 in units 1e8 times larger (bp against currency)", [1.0, 1.0, 1e8], [1.0, 2.0, 0.5, 1.5]),
             ("columns at 1e-5 and 1e5", [1e-5, 1.0, 1e5], [1.0, 1.0, 1.0, 1.0]),
             ("weights 1e-3 to 1e3 and a column at 1e8", [1.0, 1e8, 1.0], [1e-3, 1.0, 10.0, 1e3])]
    for d, cs, w in cases:
        A = [[a * c for a, c in zip(row, cs)] for row in base_A]
        x, H = exact_wls(A, b, w)
        rr, sr = raw_ratio(H), scaled_ratio(H)
        assert rr < 1e-15 and sr > 1e-9, (d, rr, sr)  # unscaled I-3 test would refuse it; scaled is a factor 1e3 or more clear
        r = [mp.fsum(mp.mpf(a) * xj for a, xj in zip(row, x)) + bi for row, bi in zip(A, b)]
        obj = mp.fsum(mp.mpf(wi) * ri * ri for wi, ri in zip(w, r))
        s.add("hedge.qp.solve", {"a": A, "b": b, "weights": w}, {"x": [float(v) for v in x], "residual": [float(v) for v in r], "objective": float(obj), "rank": 3},
              cls="root_finding", output_classes={"rank": E}, limit={"absolute": 1e-10, "relative": 1e-9, "reason": "R6-6.2: positions differ by up to 1e10 in size; relative"},
              verified=["mpmath-40 normal equations"], tags=["r6", "hedge", "qp", "scaling", "synthetic"],
              description=f"{d}: unscaled eigenvalue ratio {float(rr):.1e} (was E_SINGULAR), scaled {float(sr):.1e} (R6-6.2)")
    # a genuinely singular problem stays singular after scaling: column 3 = 1e6 x column 1
    A = [[row[0], row[1], 1e6 * row[0]] for row in base_A]
    H = mp.matrix(A).T * mp.matrix(A)
    assert scaled_ratio(H) < 1e-25
    s.add("hedge.qp.solve", {"a": A, "b": b, "weights": [1.0] * 4}, error="E_SINGULAR", cls=E, tags=["r6", "hedge", "qp", "scaling", "invalid", "synthetic"],
          description="column 3 is 1e6 times column 1: singular before and after scaling")
    return s


# ---------------------------------------------------------------------------------- R6-11 audit rulings with goldens
def audit_suite():
    from pathlib import Path
    gold = Path(__file__).resolve().parents[2] / "datasets" / "golden" / "stage_i"
    sel = next(c for c in json.loads((gold / "hedgeselect_i.json").read_text(encoding="utf-8"))["cases"] if c["case_id"] == "hedgeselect_i-0018")["inputs"]
    n = len(sel["a"][0])
    s = Suite("hedgeaudit_r6", "specifications/08-hedging/hedge-solvers.md", G)
    s.add("hedge.select.solve", dict(sel, max_instruments=n + 1), error="E_INPUT", cls=E, tags=["r6", "audit", "invalid", "synthetic"],
          description=f"audit item 6: max_instruments {n + 1} > n = {n} is E_INPUT, checked before the subset-count E_LIMIT (R6-11.6)")
    s.add("hedge.minvar.ratio", {"covariance": [[1.0, 0.1, 0.1], [0.1, 1.0, 1.2], [0.1, 1.2, 1.0]]}, error="E_NOT_POSITIVE_DEFINITE", cls=E,
          tags=["r6", "audit", "invalid", "synthetic"], description="audit item 7: hedge block indefinite (correlation 1.2): negative pivot is E_NOT_POSITIVE_DEFINITE (R6-11.7)")
    q = {"a": [[1.0, 0.5, 0.2], [0.3, 1.2, 0.4], [0.1, 0.6, 1.5], [0.8, 0.2, 0.9], [0.4, 0.9, 0.3]], "b": [-2.0, 1.5, -0.7, 0.9, -1.1], "weights": [1.0, 2.0, 0.5, 1.5, 1.0]}
    s.add("hedge.qp.solve", dict(q, eq_matrix=[], eq_rhs=[]), error="E_INPUT", cls=E, tags=["r6", "audit", "invalid", "synthetic"],
          description="audit item 13: an empty eq_matrix is E_INPUT; no equalities means both keys absent (R6-11.13)")
    return s


# ---------------------------------------------------------------------------------- R6-11 use case 6
def uc6_ref(inp):
    import gen_stage_i_w1 as W
    S, r, q, v = inp["spot"], inp["rate"], inp["dividend_yield"], inp["volatility"]
    T = inp["targets"]
    gb = {g: mp.fsum(p["quantity"] * W.bs_greeks(S, r, q, v, p)[g] for p in inp["portfolio"]) for g in ("DELTA", "GAMMA", "VEGA")}
    A = [[float(h["lot_size"] * W.bs_greeks(S, r, q, v, h)[t]) for h in inp["hedges"]] for t in T]
    b = [float(gb[t]) for t in T]
    w = [1.0 / max(1.0, abs(x)) ** 2 for x in b]
    n = len(inp["hedges"])
    out, _, _ = W.int_ref({"a": A, "b": b, "weights": w, "lot_sizes": [1.0] * n, "lower_lots": [-inp["max_lots"]] * n, "upper_lots": [inp["max_lots"]] * n})
    lots = [int(x) for x in out["lots"]]
    after = {g: gb[g] + mp.fsum(lots[j] * inp["hedges"][j]["lot_size"] * W.bs_greeks(S, r, q, v, inp["hedges"][j])[g] for j in range(n)) for g in gb}
    cost = sum(abs(lots[j]) * inp["hedges"][j]["lot_size"] * inp["hedges"][j]["half_spread"] for j in range(n))
    return {"greeks_before": {g.lower(): float(x) for g, x in gb.items()}, "lots": lots, "greeks_after": {g.lower(): float(x) for g, x in after.items()},
            "hedge_cost": float(cost), "rounding_cost": out["rounding_cost"]}


def uc6_suite():
    s = Suite("uc6_r6", "specifications/04-pricing/use-cases.md", G)
    mk = dict(spot=100.0, rate=0.03, dividend_yield=0.01, volatility=0.22)
    book = [{"instrument": "CALL", "strike": 105.0, "expiry_years": 0.5, "quantity": -1500.0},
            {"instrument": "PUT", "strike": 92.0, "expiry_years": 1.0, "quantity": 800.0},
            {"instrument": "CALL", "strike": 100.0, "expiry_years": 0.25, "quantity": 600.0}]
    fut = {"instrument": "UNDERLYING", "lot_size": 100.0, "half_spread": 0.01}
    c1 = {"instrument": "CALL", "strike": 100.0, "expiry_years": 0.75, "lot_size": 100.0, "half_spread": 0.05}
    p1 = {"instrument": "PUT", "strike": 95.0, "expiry_years": 0.5, "lot_size": 100.0, "half_spread": 0.04}
    cases = [("delta only, futures in lots of 100", dict(mk, portfolio=book, hedges=[fut], targets=["DELTA"], max_lots=1000)),
             ("delta and vega with futures and one listed call", dict(mk, portfolio=book, hedges=[fut, c1], targets=["DELTA", "VEGA"], max_lots=1000)),
             ("delta, gamma and vega with futures, a call and a put", dict(mk, portfolio=book, hedges=[fut, c1, p1], targets=["DELTA", "GAMMA", "VEGA"], max_lots=1000)),
             ("lot bound binds", dict(mk, portfolio=book, hedges=[fut, c1], targets=["DELTA", "VEGA"], max_lots=3))]
    for d, inp in cases:
        s.add("usecase.option_hedge_lots", inp, uc6_ref(inp), cls="root_finding",
              output_classes={"lots": E}, verified=["mpmath-50 Greeks", "exact rational integer search (stage I int_ref)"],
              tags=["r6", "usecase", "hedge", "synthetic"], description=d)
    base = cases[1][1]
    for d, inp, code in (("no hedges", dict(base, hedges=[]), "E_INPUT"), ("lot size 0", dict(base, hedges=[dict(fut, lot_size=0.0), c1]), "E_DOMAIN"),
                         ("unknown target", dict(base, targets=["THETA"]), "E_SCHEMA"), ("negative half-spread", dict(base, hedges=[dict(fut, half_spread=-0.01), c1]), "E_DOMAIN"),
                         ("max_lots below 1", dict(base, max_lots=0), "E_DOMAIN"), ("NaN volatility", dict(base, volatility="NaN"), "E_DOMAIN")):
        s.add("usecase.option_hedge_lots", inp, error=code, cls=E, tags=["r6", "usecase", "invalid", "synthetic"] + (["e1"] if "NaN" in d else []), description=d)
    return s


def main():
    keep = common.GOLDEN
    common.GOLDEN = keep.parent / "r6"
    for fn in ([scaling] if "scale" in sys.argv else [audit_suite] if "audit" in sys.argv else [uc6_suite] if "uc6" in sys.argv else [qp_large, scaling, audit_suite, uc6_suite]):
        fn().write()
    common.GOLDEN = keep
    from pathlib import Path
    if REPORT:
        (Path(__file__).resolve().parent.parent / "R6_HEDGE_LARGE.json").write_text(json.dumps(REPORT, indent=1) + chr(10), encoding="utf-8", newline=chr(10))


if __name__ == "__main__":
    main()
