"""Stage F, plan item Q1: the four new curve interpolations of 02-curves/curve-framework.md (stage F section).

Float replicas written from the spec text. MONOTONE_CONVEX and MONOTONIC_LOG_CUBIC follow QuantLib 1.44's algorithms
(ConvexMonotone with quadraticity 0, monotonicity 1, forcePositive; MonotonicLogCubic), which is why the outside check
can hold them to 1e-12. TENSION_SPLINE and HYBRID are QuantForge's own.

A curve here is (times t_0 = 0 < t_1 < ... < t_n, smooth discount factors S_0 = 1, S_1..S_n), jumps already removed.
Each interpolator gives ln S(t) for t >= 0 and the instantaneous forward f(t) = -d ln S / dt.
"""
import math


# ------------------------------------------------------------------------------------------------ monotone convex
class _Sec:
    """One section of the convex monotone interpolation: value(x) (forward) and primitive(x) (integral from x_0)."""


def _cm_sections(x, y, fp_=False):
    """x: node times, y: discrete forwards, y[0] ignored. fp_ is QuantLib's forcePositive (the spec uses False).
    Returns (sections keyed by right node index, extrapolation section)."""
    n = len(x)
    secs = {}
    if n == 2:
        c = y[1]
        return {1: ("const", c, 0.0, x[0])}, ("const", c, 0.0, x[0])
    f = [0.0] * n
    for i in range(1, n - 1):
        dxp, dx = x[i] - x[i - 1], x[i + 1] - x[i]
        f[i] = dx / (dx + dxp) * y[i] + dxp / (dx + dxp) * y[i + 1]
    f[0] = 1.5 * y[1] - 0.5 * f[1]
    f[n - 1] = 1.5 * y[n - 1] - 0.5 * f[n - 2]
    if fp_:
        f[0] = 0.0 if f[0] < 0 else f[0]
        f[n - 1] = 0.0 if f[n - 1] < 0.0 else f[n - 1]
    prim = 0.0
    for i in range(1, n):
        gp, gn = f[i - 1] - y[i], f[i] - y[i]
        x0, x1, fa = x[i - 1], x[i], y[i]
        if abs(gp) < 1e-14 and abs(gn) < 1e-14:
            secs[i] = ("grad", f[i - 1], prim, x0, x1, f[i])
        elif (gp > 0 and -0.5 * gp >= gn >= -2 * gp) or (gp < 0 and -0.5 * gp <= gn <= -2 * gp):
            secs[i] = _quad_min(x0, x1, f[i - 1], f[i], fa, prim, fp_)
        elif (gp < 0 and gn > -2 * gp) or (gp > 0 and gn < -2 * gp):
            eta = (gn + 2 * gp) / (gn - gp)
            secs[i] = ("cm2", x0, x1 - x0, gp, gn, fa, eta, prim) if eta < 1.0 else _cm4min(x0, x1, gp, gn, fa, 1.0, prim, fp_)
        elif (gp > 0 and gn < 0 and gn > -0.5 * gp) or (gp < 0 and gn > 0 and gn < -0.5 * gp):
            eta = gn / (gn - gp) * 3.0
            secs[i] = ("cm3", x0, x1 - x0, gp, gn, fa, eta, prim) if eta > 0.0 else _cm4min(x0, x1, gp, gn, fa, 0.0, prim, fp_)
        else:
            eta = min(max(gn / (gp + gn), 0.0), 1.0)
            secs[i] = _cm4min(x0, x1, gp, gn, fa, eta, prim, fp_)
        prim += y[i] * (x[i] - x[i - 1])
    last = _sec_value(secs[n - 1], x[n - 1])
    return secs, ("const", last, prim, x[n - 1])


def _quad_min(x1, x4, fp, fn, fa, p1, fp_=True):
    a = 3 * fp + 3 * fn - 6 * fa
    b = -(4 * fp + 2 * fn - 6 * fa)
    c = fp
    d = b * b - 4 * a * c
    sc = x4 - x1
    split = None
    if d > 0 and fp_:
        aav, bav, cav = 36.0, -24 * (fp + fn), 4 * (fp * fp + fp * fn + fn * fn)
        dav = bav * bav - 4.0 * aav * cav
        if dav >= 0.0:
            avr = (-bav - math.sqrt(dav)) / (2 * aav)
            xr = fa / avr
            sc *= xr
            a = 3 * fp + 3 * fn - 6 * avr
            b = -(4 * fp + 2 * fn - 6 * avr)
            c = fp
            xroot = -b / (2 * a)
            x2 = x1 + xr * (x4 - x1) * xroot
            x3 = x4 - xr * (x4 - x1) * (1 - xroot)
            p2 = p1 + sc * (a / 3 * xroot * xroot + b / 2 * xroot + c) * xroot
            split = (xr, x2, x3, p2)
    return ("qmin", x1, x4, a, b, c, sc, p1, split)


def _cm4min(x0, x1, gp, gn, fa, eta, prim, fp_=True):
    sc = x1 - x0
    A = -0.5 * (eta * gp + (1 - eta) * gn)
    split = None
    if A + fa <= 0.0 and fp_:
        fp, fn = gp + fa, gn + fa
        shift = (eta * fp + (1 - eta) * fn) / 3.0 - fa
        period = shift * sc / (fa + shift)
        xadj = sc - period
        xr = xadj / sc
        fa += shift
        gn, gp = fn - fa, fp - fa
        A = -(eta * gp + (1.0 - eta) * gn) / 2.0
        split = (xr, x0 + xadj * eta, x0 + sc - xadj * (1.0 - eta))
    return ("cm4", x0, sc, gp, gn, fa, eta, prim, A, split)


def _sec_value(s, x):
    k = s[0]
    if k == "const":
        return s[1]
    if k == "grad":
        _, fp, pr, x0, x1, fn = s
        return fp + (x - x0) * (fn - fp) / (x1 - x0)
    if k == "qmin":
        _, x1, x4, a, b, c, sc, p1, sp = s
        xv = (x - x1) / (x4 - x1)
        if sp:
            xr, x2, x3, _ = sp
            if x <= x2:
                xv /= xr
            elif x < x3:
                return 0.0
            else:
                xv = 1.0 - (1.0 - xv) / xr
        return c + b * xv + a * xv * xv
    if k == "cm2":
        _, x0, sc, gp, gn, fa, e, pr = s
        xv = (x - x0) / sc
        return fa + gp if xv <= e else fa + gp + (gn - gp) / ((1 - e) * (1 - e)) * (xv - e) * (xv - e)
    if k == "cm3":
        _, x0, sc, gp, gn, fa, e, pr = s
        xv = (x - x0) / sc
        return fa + gn + (gp - gn) / (e * e) * (e - xv) * (e - xv) if xv <= e else fa + gn
    _, x0, sc, gp, gn, fa, e, pr, A, sp = s
    xv = (x - x0) / sc
    if sp:
        xr, x2, x3 = sp
        if x <= x2:
            xv /= xr
            return fa + A + (gp - A) * (e - xv) * (e - xv) / (e * e)
        if x < x3:
            return 0.0
        xv = 1.0 - (1.0 - xv) / xr
        return fa + A + (gn - A) * (xv - e) * (xv - e) / ((1 - e) * (1 - e))
    if e == 0.0 and xv <= 0.0:
        return fa + gp   # limit at the left end when eta = 0 (spec rule (e)); QuantLib divides 0 by 0 here
    if xv <= e:
        return fa + A + (gp - A) * (e - xv) * (e - xv) / (e * e)
    return fa + A + (gn - A) * (xv - e) * (xv - e) / ((1 - e) * (1 - e))


def _sec_prim(s, x):
    k = s[0]
    if k == "const":
        _, v, pr, x0 = s
        return pr + (x - x0) * v
    if k == "grad":
        _, fp, pr, x0, x1, fn = s
        g = (fn - fp) / (x1 - x0)
        return pr + (x - x0) * (fp + 0.5 * (x - x0) * g)
    if k == "qmin":
        _, x1, x4, a, b, c, sc, p1, sp = s
        xv = (x - x1) / (x4 - x1)
        if sp:
            xr, x2, x3, p2 = sp
            if x < x2:
                xv /= xr
            elif x < x3:
                return p2
            else:
                xv = 1.0 - (1.0 - xv) / xr
        return p1 + sc * (a / 3 * xv * xv + b / 2 * xv + c) * xv
    if k == "cm2":
        _, x0, sc, gp, gn, fa, e, pr = s
        xv = (x - x0) / sc
        if xv <= e:
            return pr + sc * (fa * xv + gp * xv)
        return pr + sc * (fa * xv + gp * xv + (gn - gp) / ((1 - e) * (1 - e)) * (1.0 / 3.0 * (xv ** 3 - e ** 3) - e * xv * xv + e * e * xv))
    if k == "cm3":
        _, x0, sc, gp, gn, fa, e, pr = s
        xv = (x - x0) / sc
        if xv <= e:
            return pr + sc * (fa * xv + gn * xv + (gp - gn) / (e * e) * (1.0 / 3.0 * xv ** 3 - e * xv * xv + e * e * xv))
        return pr + sc * (fa * xv + gn * xv + (gp - gn) / (e * e) * (1.0 / 3.0 * e ** 3))
    _, x0, sc, gp, gn, fa, e, pr, A, sp = s
    xv = (x - x0) / sc
    if sp:
        xr = sp[0]
        x2, x3 = sp[1], sp[2]
        if x <= x2:
            xv /= xr
            return pr + sc * xr * (fa + A + (gp - A) / (e * e) * (e * e - e * xv + 1.0 / 3.0 * xv * xv)) * xv
        if x <= x3:
            return pr + sc * xr * (fa * e + A * e + (gp - A) / (e * e) * (1.0 / 3.0 * e ** 3))
        xv = 1.0 - (1.0 - xv) / xr
        return pr + sc * xr * (fa * xv + A * xv + (gp - A) * (1.0 / 3.0 * e) + (gn - A) / ((1.0 - e) * (1.0 - e)) *
                               (1.0 / 3.0 * xv ** 3 - e * xv * xv + e * e * xv - 1.0 / 3.0 * e ** 3))
    if e == 0.0 and xv <= 0.0:
        return pr
    if xv <= e:
        return pr + sc * (fa + A + (gp - A) / (e * e) * (e * e - e * xv + 1.0 / 3.0 * xv * xv)) * xv
    return pr + sc * (fa * xv + A * xv + (gp - A) * (1.0 / 3.0 * e) + (gn - A) / ((1 - e) * (1 - e)) *
                      (1.0 / 3.0 * xv ** 3 - e * xv * xv + e * e * xv - 1.0 / 3.0 * e ** 3))


class MonotoneConvex:
    def __init__(self, t, S, force_positive=False):
        self.x = list(t)
        lnS = [math.log(s) for s in S]
        self.y = [0.0] + [(lnS[i - 1] - lnS[i]) / (t[i] - t[i - 1]) for i in range(1, len(t))]
        self.secs, self.ext = _cm_sections(self.x, self.y, force_positive)

    def _sec(self, t):
        if t >= self.x[-1]:
            return self.ext
        i = next(k for k in range(1, len(self.x)) if self.x[k] > t)
        return self.secs[i]

    def ln_s(self, t):
        return -_sec_prim(self._sec(t), t)

    def fwd(self, t):
        return _sec_value(self._sec(t), t)


# ------------------------------------------------------------------------------------------------ monotonic log cubic
def thomas(sub, dia, sup, rhs):
    n = len(dia)
    c, d = [0.0] * n, [0.0] * n
    c[0], d[0] = sup[0] / dia[0], rhs[0] / dia[0]
    for i in range(1, n):
        m = dia[i] - sub[i] * c[i - 1]
        c[i] = sup[i] / m if i < n - 1 else 0.0
        d[i] = (rhs[i] - sub[i] * d[i - 1]) / m
    xs = [0.0] * n
    xs[-1] = d[-1]
    for i in range(n - 2, -1, -1):
        xs[i] = d[i] - c[i] * xs[i + 1]
    return xs


class MonotonicLogCubic:
    """QuantLib MonotonicLogCubic: natural spline slopes on ln S (second derivative 0 at both ends), Hyman filter."""

    def __init__(self, t, S, monotonic=True):
        x = list(t)
        y = [math.log(s) for s in S]
        n = len(x)
        dx = [x[i + 1] - x[i] for i in range(n - 1)]
        Sl = [(y[i + 1] - y[i]) / dx[i] for i in range(n - 1)]
        sub, dia, sup, rhs = [0.0] * n, [0.0] * n, [0.0] * n, [0.0] * n
        for i in range(1, n - 1):
            sub[i], dia[i], sup[i] = dx[i], 2.0 * (dx[i] + dx[i - 1]), dx[i - 1]
            rhs[i] = 3.0 * (dx[i] * Sl[i - 1] + dx[i - 1] * Sl[i])
        dia[0], sup[0], rhs[0] = 2.0, 1.0, 3.0 * Sl[0]
        sub[n - 1], dia[n - 1], rhs[n - 1] = 1.0, 2.0, 3.0 * Sl[n - 2]
        tmp = thomas(sub, dia, sup, rhs)
        if monotonic:
            for i in range(n):
                if i == 0 or i == n - 1:
                    s = Sl[0] if i == 0 else Sl[n - 2]
                    tmp[i] = math.copysign(min(abs(tmp[i]), abs(3.0 * s)), tmp[i]) if tmp[i] * s > 0.0 else 0.0
                    continue
                pm = (Sl[i - 1] * dx[i] + Sl[i] * dx[i - 1]) / (dx[i - 1] + dx[i])
                M = 3.0 * min(abs(Sl[i - 1]), abs(Sl[i]), abs(pm))
                if i > 1 and (Sl[i - 1] - Sl[i - 2]) * (Sl[i] - Sl[i - 1]) > 0.0:
                    pd = (Sl[i - 1] * (2.0 * dx[i - 1] + dx[i - 2]) - Sl[i - 2] * dx[i - 1]) / (dx[i - 2] + dx[i - 1])
                    if pm * pd > 0.0 and pm * (Sl[i - 1] - Sl[i - 2]) > 0.0:
                        M = max(M, 1.5 * min(abs(pm), abs(pd)))
                if i < n - 2 and (Sl[i] - Sl[i - 1]) * (Sl[i + 1] - Sl[i]) > 0.0:
                    pu = (Sl[i] * (2.0 * dx[i] + dx[i + 1]) - Sl[i + 1] * dx[i]) / (dx[i] + dx[i + 1])
                    if pm * pu > 0.0 and -pm * (Sl[i] - Sl[i - 1]) > 0.0:
                        M = max(M, 1.5 * min(abs(pm), abs(pu)))
                tmp[i] = math.copysign(min(abs(tmp[i]), M), tmp[i]) if tmp[i] * pm > 0.0 else 0.0
        self.x, self.y, self.slope = x, y, tmp
        self.b = [(3.0 * Sl[i] - tmp[i + 1] - 2.0 * tmp[i]) / dx[i] for i in range(n - 1)]
        self.c = [(tmp[i + 1] + tmp[i] - 2.0 * Sl[i]) / (dx[i] * dx[i]) for i in range(n - 1)]

    def _j(self, t):
        return min(next((k for k in range(1, len(self.x)) if self.x[k] > t), len(self.x) - 1) - 1, len(self.x) - 2)

    def ln_s(self, t):
        if t > self.x[-1]:
            return self.y[-1] - self.fwd(self.x[-1]) * (t - self.x[-1])
        j = self._j(t)
        d = t - self.x[j]
        return self.y[j] + d * (self.slope[j] + d * (self.b[j] + d * self.c[j]))

    def fwd(self, t):
        if t > self.x[-1]:
            t = self.x[-1]
        j = self._j(t)
        d = t - self.x[j]
        return -(self.slope[j] + (2.0 * self.b[j] + 3.0 * self.c[j] * d) * d)


# ------------------------------------------------------------------------------------------------ tension spline
def _em1(z):
    """(1 - e^{-z}) for z >= 0, accurate for small z."""
    return -math.expm1(-z)


class TensionSpline:
    """Exponential tension spline on ln S, tension s > 0 per year, natural ends (M_0 = M_n = 0). Stable forms (spec)."""

    def __init__(self, t, S, s):
        x = list(t)
        y = [math.log(v) for v in S]
        n = len(x)
        h = [x[i + 1] - x[i] for i in range(n - 1)]
        al, be = [], []
        for hi in h:
            z = s * hi
            if z < 1e-3:   # series: alpha = h/6 (1 - z^2/60), beta = h/3 (1 - z^2/15)  (error below 1e-16 relative)
                al.append(hi / 6 * (1 - z * z / 60))
                be.append(hi / 3 * (1 - z * z / 15))
            else:
                # alpha = 1/(s^2 h) - 1/(s sinh z),  beta = coth(z)/s - 1/(s^2 h)
                e2 = math.exp(-2 * z)
                al.append(1 / (s * s * hi) - 2 * math.exp(-z) / (s * (1 - e2)))
                be.append((1 + e2) / (s * (1 - e2)) - 1 / (s * s * hi))
        M = [0.0] * n
        if n > 2:
            m = n - 2
            sub = [al[i] for i in range(m)]
            dia = [be[i] + be[i + 1] for i in range(m)]
            sup = [al[i + 1] for i in range(m)]
            rhs = [(y[i + 2] - y[i + 1]) / h[i + 1] - (y[i + 1] - y[i]) / h[i] for i in range(m)]
            sub[0] = 0.0
            sup[-1] = 0.0
            M[1:-1] = thomas(sub, dia, sup, rhs)
        self.x, self.y, self.h, self.M, self.s = x, y, h, M, s

    def _j(self, t):
        return min(next((k for k in range(1, len(self.x)) if self.x[k] > t), len(self.x) - 1) - 1, len(self.x) - 2)

    def _parts(self, j, t):
        s, h, x0 = self.s, self.h[j], self.x[j]
        a, b = t - x0, self.x[j + 1] - t
        z = s * h
        if z < 1e-3:
            # cubic-spline limit with the O(z^2) term dropped: |error| below 1e-12 h^2 |M|
            ra = (a / h) * (a * a - h * h) / 6
            rb = (b / h) * (b * b - h * h) / 6
            dra = (3 * a * a - h * h) / (6 * h)
            drb = -(3 * b * b - h * h) / (6 * h)
            return ra, rb, dra, drb
        den = 1 - math.exp(-2 * z)
        # sinh(s a)/sinh(s h) = e^{-s b} (1 - e^{-2 s a}) / (1 - e^{-2 z}), the same with a and b swapped
        sa = math.exp(-s * b) * _em1(2 * s * a) / den
        sb = math.exp(-s * a) * _em1(2 * s * b) / den
        ca = math.exp(-s * b) * (1 + math.exp(-2 * s * a)) / den   # cosh(s a)/sinh(s h)
        cb = math.exp(-s * a) * (1 + math.exp(-2 * s * b)) / den
        ra = (sa - a / h) / (s * s)
        rb = (sb - b / h) / (s * s)
        return ra, rb, (s * ca - 1 / h) / (s * s), -(s * cb - 1 / h) / (s * s)

    def ln_s(self, t):
        if t > self.x[-1]:
            return self.y[-1] - self.fwd(self.x[-1]) * (t - self.x[-1])
        j = self._j(t)
        h = self.h[j]
        a, b = t - self.x[j], self.x[j + 1] - t
        ra, rb, _, _ = self._parts(j, t)
        return self.y[j] * b / h + self.y[j + 1] * a / h + self.M[j] * rb + self.M[j + 1] * ra

    def fwd(self, t):
        if t > self.x[-1]:
            t = self.x[-1]
        j = self._j(t)
        h = self.h[j]
        _, _, dra, drb = self._parts(j, t)
        return -((self.y[j + 1] - self.y[j]) / h + self.M[j] * drb + self.M[j + 1] * dra)


# ------------------------------------------------------------------------------------------------ hybrid
class Hybrid:
    """LOG_LINEAR_DF (flat forward) on segments ending at or before node k = step_end; MONOTONE_CONVEX from node k on."""

    def __init__(self, t, S, k):
        self.t, self.lnS, self.k = list(t), [math.log(v) for v in S], k
        self.cm = MonotoneConvex([x - t[k] for x in t[k:]], [v / S[k] for v in S[k:]]) if k < len(t) - 1 else None

    def ln_s(self, t):
        T, L, k = self.t, self.lnS, self.k
        if t <= T[k] or self.cm is None:
            if t > T[-1]:
                f = (L[-2] - L[-1]) / (T[-1] - T[-2])
                return L[-1] - f * (t - T[-1])
            i = next(j for j in range(len(T) - 1) if t <= T[j + 1])
            u = (t - T[i]) / (T[i + 1] - T[i])
            return (1 - u) * L[i] + u * L[i + 1]
        return L[k] + self.cm.ln_s(t - T[k])

    def fwd(self, t):
        T, L, k = self.t, self.lnS, self.k
        if t < T[k] or self.cm is None:
            i = next((j for j in range(len(T) - 1) if t < T[j + 1]), len(T) - 2)
            return (L[i] - L[i + 1]) / (T[i + 1] - T[i])
        return self.cm.fwd(t - T[k])


def make(kind, t, S, tension=None, k=None):
    if kind == "MONOTONE_CONVEX":
        return MonotoneConvex(t, S)
    if kind == "MONOTONIC_LOG_CUBIC":
        return MonotonicLogCubic(t, S)
    if kind == "TENSION_SPLINE":
        return TensionSpline(t, S, tension)
    if kind == "HYBRID":
        return Hybrid(t, S, k)
    raise ValueError(kind)
