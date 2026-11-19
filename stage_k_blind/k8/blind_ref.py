"""Blind implementation of CN_RANNACHER_SMOOTHED Bermudan scheme with forward-mode exact derivative.
Directions: 0..P-1 discount factors, P = a, P+1 = sigma."""
import json, math, os, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PACKET = "C:/Work/Claude/qf-blind/k8_packet"


class D:
    __slots__ = ("v", "d")

    def __init__(self, v, d):
        self.v = np.asarray(v, dtype=np.float64)
        self.d = np.asarray(d, dtype=np.float64)

    @staticmethod
    def const(x, nd):
        x = np.asarray(x, dtype=np.float64)
        return D(x, np.zeros(x.shape + (nd,)))

    def nd(self):
        return self.d.shape[-1]

    def _c(self, o):
        return o if isinstance(o, D) else D.const(o, self.nd())

    def __add__(s, o):
        o = s._c(o)
        return D(s.v + o.v, s.d + o.d)
    __radd__ = __add__

    def __sub__(s, o):
        o = s._c(o)
        return D(s.v - o.v, s.d - o.d)

    def __rsub__(s, o):
        o = s._c(o)
        return D(o.v - s.v, o.d - s.d)

    def __neg__(s):
        return D(-s.v, -s.d)

    def __mul__(s, o):
        o = s._c(o)
        return D(s.v * o.v, s.v[..., None] * o.d + o.v[..., None] * s.d)
    __rmul__ = __mul__

    def __truediv__(s, o):
        o = s._c(o)
        q = s.v / o.v
        return D(q, s.d / o.v[..., None] - q[..., None] * o.d / o.v[..., None])

    def __rtruediv__(s, o):
        return s._c(o) / s

    def __getitem__(s, i):
        return D(s.v[i], s.d[i])


def dexp(x):
    e = np.exp(x.v)
    return D(e, e[..., None] * x.d)


def dexpm1(x):
    return D(np.expm1(x.v), np.exp(x.v)[..., None] * x.d)


def dsqrt(x):
    r = np.sqrt(x.v)
    return D(r, x.d / (2 * r)[..., None])


def stack(lst):
    return D(np.array([e.v for e in lst]), np.array([e.d for e in lst]))


def concat(parts):
    return D(np.concatenate([p.v for p in parts]), np.concatenate([p.d for p in parts]))


def Mfun(p, q, nd):
    """M(p,q), branch chosen on binary64 values; derivative of the branch taken."""
    pv, qv = float(p.v), float(q.v)
    if pv >= 0 and qv >= 0:
        return p / 3.0 + q / 6.0
    if pv > 0 > qv:
        r = p / (p - q)
        t = p * p / (2.0 * (p - q))
        return t - t * r / 3.0
    if pv < 0 < qv:
        r = q / (q - p)
        return q * r * r / 6.0
    return D.const(0.0, nd)


def smooth(U, Eh, x, nd, xfactor="mult", dxv=None):
    nx = U.v.shape[0]
    f = U - Eh
    fl = f[0:1] * 2.0 - f[1:2]
    fr = f[nx - 1:nx] * 2.0 - f[nx - 2:nx - 1]
    fe = concat([fl, f, fr])  # index i+1 <-> f_i
    hl = []
    for i in range(nx):
        fi = fe[i + 1]
        hl.append(Mfun(fi, fe[i], nd) + Mfun(fi, fe[i + 2], nd))
    dd = [D.const(0.0, nd)] * nx
    for i in range(1, nx - 1):
        dd[i] = f[i - 1] - f[i] * 2.0 + f[i + 1]
    fv = f.v
    for j in range(nx - 1):
        a_, b_ = fv[j], fv[j + 1]
        if (a_ > 0 and b_ < 0) or (a_ < 0 and b_ > 0):
            if a_ > 0:
                pos, neg = j, j + 1
            else:
                pos, neg = j + 1, j
            rho = f[pos] / (f[pos] - f[neg])
            c = rho * (1.0 - rho) * (rho * 2.0 - 1.0) / 12.0 * ((dd[j] + dd[j + 1]) / 2.0)
            if xfactor == "x":
                c = c * x[j]      # alternative reading (not used by default)
            hl[pos] = hl[pos] - (1.0 - rho) * c
            hl[neg] = hl[neg] - rho * c
    h = stack(hl)
    Sl = [h[0]]
    for i in range(1, nx - 1):
        Sl.append(h[i] - (h[i - 1] - h[i] * 2.0 + h[i + 1]) / 6.0)
    Sl.append(h[nx - 1])
    return Eh + stack(Sl)


def run(inp, literal_boundary=False, override=None, xfactor="mult", cell_override=None):
    cv = inp["curve"]
    times = list(cv["times"])
    dfs = list(cv["discount_factors"])
    P = len(times)
    nd = P + 2
    a_v = inp["mean_reversion"]
    s_v = inp["sigma"]
    if override:
        dfs = override.get("dfs", dfs)
        a_v = override.get("a", a_v)
        s_v = override.get("sigma", s_v)
    a = D(a_v, np.eye(nd)[P])
    sg = D(s_v, np.eye(nd)[P + 1])
    lnDF = [D(math.log(dfs[j]), np.eye(nd)[j] / dfs[j]) for j in range(P)]
    ts = [0.0] + times
    Ls = [D.const(0.0, nd)] + lnDF
    grid = dict(inp["grid"])
    if cell_override:
        grid.update(cell_override)
    nx = grid["nx"]
    spy = grid["steps_per_year"]
    width = grid["width"]
    ex = list(inp["exercise_times"])
    pay = list(inp["payment_times"])
    K = inp["fixed_rate"]
    phi = 1.0 if inp["swaption_type"] == "PAYER" else -1.0
    m = len(ex)
    tm = ex[-1]

    def lnP(s):
        for j, t in enumerate(ts):
            if s == t:
                return Ls[j]
        k = 0
        for j in range(P):
            if ts[j] < s:
                k = j
        w = (s - ts[k]) / (ts[k + 1] - ts[k])
        return Ls[k] + (Ls[k + 1] - Ls[k]) * w

    g = -dexpm1(a * (-2.0 * tm)) / (a * 2.0)
    sx = sg * dsqrt(g)
    h = sx * width
    dx = h * 2.0 / (nx - 1)
    x = stack([(-h) + dx * float(i) for i in range(nx)])
    c2 = sg * sg / (a * a * 2.0)
    c4 = sg * sg / (a * 4.0)

    def Ifun(t):
        return t + dexpm1(a * (-t)) * 2.0 / a - dexpm1(a * (-2.0 * t)) / (a * 2.0)

    def Ehat(t):
        It = Ifun(t)
        Dt = dexp(lnP(t) - c2 * It)
        e1 = dexpm1(a * (-t))
        e2 = dexpm1(a * (-2.0 * t))
        later = [s for s in pay if s > t]

        def Q(s):
            B = -dexpm1(a * (-(s - t))) / a
            base = lnP(s) - c2 * (It + B * e1 * e1) + c4 * e2 * B * B
            return dexp(base - B * x)
        ann = None
        prev = t
        for s in later:
            term = Q(s) * (s - prev)
            ann = term if ann is None else ann + term
            prev = s
        val = Dt - Q(later[-1]) - ann * K
        return val * phi

    s2 = sg * sg
    r2 = s2 / (dx * dx) * 0.5
    ax = a * x / (dx * 2.0)
    lo = -r2 - ax          # coefficient of U_{i-1}
    di = r2 * 2.0 + x
    up = -r2 + ax
    n = nx - 2
    lo_i = lo[1:nx - 1]
    di_i = di[1:nx - 1]
    up_i = up[1:nx - 1]
    lo_l = [lo_i[i] for i in range(n)]
    di_l = [di_i[i] for i in range(n)]
    up_l = [up_i[i] for i in range(n)]
    di_l[0] = di_l[0] + lo_l[0] * 2.0
    up_l[0] = up_l[0] - lo_l[0]
    di_l[n - 1] = di_l[n - 1] + up_l[n - 1] * 2.0
    lo_l[n - 1] = lo_l[n - 1] - up_l[n - 1]
    loS = stack(lo_l)
    diS = stack(di_l)
    upS = stack(up_l)

    def matvec(y):
        r = diS * y
        t1 = loS[1:] * y[0:n - 1]
        t2 = upS[:n - 1] * y[1:]
        t1f = concat([D.const(np.zeros(1), nd), t1])
        t2f = concat([t2, D.const(np.zeros(1), nd)])
        return r + t1f + t2f

    def matvec_full(U):
        return lo[1:nx - 1] * U[0:nx - 2] + di[1:nx - 1] * U[1:nx - 1] + up[1:nx - 1] * U[2:nx]

    factor_cache = {}

    def factors(c):
        if c in factor_cache:
            return factor_cache[c]
        lw = [loS[i] * c for i in range(n)]
        dg = [diS[i] * c + 1.0 for i in range(n)]
        uu = [upS[i] * c for i in range(n)]
        bp = [dg[0]]
        w = [None]
        for i in range(1, n):
            wi = lw[i] / bp[i - 1]
            w.append(wi)
            bp.append(dg[i] - wi * uu[i - 1])
        factor_cache[c] = (w, bp, uu)
        return factor_cache[c]

    def solve(c, rhs):
        w, bp, uu = factors(c)
        y = [rhs[0]]
        for i in range(1, n):
            y.append(rhs[i] - w[i] * y[i - 1])
        xsol = [None] * n
        xsol[n - 1] = y[n - 1] / bp[n - 1]
        for i in range(n - 2, -1, -1):
            xsol[i] = (y[i] - uu[i] * xsol[i + 1]) / bp[i]
        return stack(xsol)

    def with_bnd(yint):
        b0 = yint[0:1] * 2.0 - yint[1:2]
        b1 = yint[n - 1:n] * 2.0 - yint[n - 2:n - 1]
        return concat([b0, yint, b1])

    def step_cn(U, c):
        yi = U[1:nx - 1]
        if literal_boundary:
            rhs = yi - matvec_full(U) * c
        else:
            rhs = yi - matvec(yi) * c
        return with_bnd(solve(c, rhs))

    def step_half(U, c):
        return with_bnd(solve(c, U[1:nx - 1]))

    knots = [0.0] + ex
    U = smooth(D.const(np.zeros(nx), nd), Ehat(tm), x, nd, xfactor)
    for k in range(m, 0, -1):
        span = knots[k] - knots[k - 1]
        nst = max(1, math.ceil(spy * span))
        dt = span / nst
        c = dt / 2.0
        for st in range(nst):
            if st < 2:
                U = step_half(U, c)
                U = step_half(U, c)
            else:
                U = step_cn(U, c)
        if k - 1 >= 1:
            U = smooth(U, Ehat(knots[k - 1]), x, nd, xfactor)
    centre = (nx - 1) // 2
    return U[centre] * inp["notional"], P


def derive_all():
    inputs = json.load(open(PACKET + "/inputs/K-8.inputs.json"))
    out = {"cases": {}}
    for case in inputs["cases"]:
        pr, P = run(case["inputs"])
        res = {"price": float(pr.v)}
        if case["operation"] == "rates.shortrate.bermudan_ladder":
            res["d_price_d_discount_factors"] = [float(pr.d[j]) for j in range(P)]
            res["d_price_d_mean_reversion"] = float(pr.d[P])
            res["d_price_d_sigma"] = float(pr.d[P + 1])
        out["cases"][case["case_id"]] = res
        print(case["case_id"], res["price"], file=sys.stderr)
    return out


if __name__ == "__main__":
    out = derive_all()
    with open(HERE + "/blind_results.json", "w") as fh:
        json.dump(out, fh, indent=1)
