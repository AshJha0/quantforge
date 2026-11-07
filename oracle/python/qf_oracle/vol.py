"""Stage C reference formulas, written from specifications/. Tests only."""
import math

import numpy as np
from scipy.linalg import solve_banded
from scipy.optimize import brentq, least_squares
from scipy.special import ndtr as N, ndtri as Ninv


def n(x):
    return math.exp(-x * x / 2) / math.sqrt(2 * math.pi)


def phi(t):
    return 1 if t == "CALL" else -1


def black(t, F, K, v, T, D=1.0):
    p = phi(t)
    if T == 0 or v == 0:
        return D * max(p * (F - K), 0.0)
    s = v * math.sqrt(T)
    d1 = (math.log(F / K) + s * s / 2) / s
    return D * p * (F * N(p * d1) - K * N(p * (d1 - s)))


def bachelier(t, F, K, v, T, D=1.0):
    p = phi(t)
    if T == 0 or v == 0:
        return D * max(p * (F - K), 0.0)
    s = v * math.sqrt(T)
    d = (F - K) / s
    return D * (p * (F - K) * N(p * d) + s * n(d))


def implied_black(t, F, K, price, T, D=1.0):
    return brentq(lambda v: black(t, F, K, v, T, D) - price, 1e-9, 20, xtol=1e-15, rtol=1e-14, maxiter=500)


def implied_bachelier(t, F, K, price, T, D=1.0):
    return brentq(lambda v: bachelier(t, F, K, v, T, D) - price, 1e-12, 1e4, xtol=1e-15, rtol=1e-14, maxiter=500)


def fwd_flat(S, r, b, T, divs):
    return S * math.exp((r - b) * T) - sum(a * math.exp((r - b) * (T - t)) for t, a in divs if 0 < t <= T)


def fwd_wrong(S, r, b, T, divs):
    return (S - sum(a * math.exp(-r * t) for t, a in divs if 0 < t <= T)) * math.exp((r - b) * T)


def fwd_rolled(S, r, b, T, divs):
    """Independent route: step the stock from dividend to dividend."""
    x, last = S, 0.0
    for t, a in divs:
        if 0 < t <= T:
            x = x * math.exp((r - b) * (t - last)) - a
            last = t
    return x * math.exp((r - b) * (T - last))


def greeks(model, t, K, v, T, S=None, r=None, q=None, F=None, D=None, shift=0.0):
    p = phi(t)
    rt = math.sqrt(T)
    if model == "BACHELIER":
        d = (F - K) / (v * rt)
        V = bachelier(t, F, K, v, T, D)
        return dict(price=V, delta=D * p * N(p * d), gamma=D * n(d) / (v * rt), vega=D * rt * n(d), theta=-D * v * n(d) / (2 * rt), rho=-T * V, vanna=-D * n(d) * d / v, volga=D * rt * n(d) * d * d / v)
    if model == "BLACK_SCHOLES":
        Fw, Dd, Q = S * math.exp((r - q) * T), math.exp(-r * T), math.exp(-q * T)
        s = v * rt
        d1 = (math.log(Fw / K) + s * s / 2) / s
        d2 = d1 - s
        V = black(t, Fw, K, v, T, Dd)
        vega = S * Q * n(d1) * rt
        return dict(price=V, delta=Q * p * N(p * d1), gamma=Q * n(d1) / (S * s), vega=vega, theta=-S * Q * n(d1) * v / (2 * rt) - p * r * K * Dd * N(p * d2) + p * q * S * Q * N(p * d1),
                    rho=p * K * T * Dd * N(p * d2), vanna=-Q * n(d1) * d2 / v, volga=vega * d1 * d2 / v)
    f, k = F + shift, K + shift
    s = v * rt
    d1 = (math.log(f / k) + s * s / 2) / s
    d2 = d1 - s
    V = black(t, f, k, v, T, D)
    vega = D * f * n(d1) * rt
    return dict(price=V, delta=D * p * N(p * d1), gamma=D * n(d1) / (f * s), vega=vega, theta=-D * f * n(d1) * v / (2 * rt), rho=-T * V, vanna=-D * n(d1) * d2 / v, volga=vega * d1 * d2 / v)


def bump_greeks(model, t, K, v, T, S=None, r=None, q=None, F=None, D=None, shift=0.0):
    def V(u, x):
        if model == "BLACK_SCHOLES":
            return black(t, u * math.exp((r - q) * T), K, x, T, math.exp(-r * T))
        if model == "BACHELIER":
            return bachelier(t, u, K, x, T, D)
        return black(t, u, K + shift, x, T, D)
    U = S if model == "BLACK_SCHOLES" else (F if model == "BACHELIER" else F + shift)
    hu = 1e-4 * (max(abs(U), 1.0) if model == "BACHELIER" else U)
    hv = 1e-4 * v
    c = V(U, v)
    return dict(delta=(V(U + hu, v) - V(U - hu, v)) / (2 * hu), gamma=(V(U + hu, v) - 2 * c + V(U - hu, v)) / hu ** 2, vega=(V(U, v + hv) - V(U, v - hv)) / (2 * hv),
                volga=(V(U, v + hv) - 2 * c + V(U, v - hv)) / hv ** 2, vanna=(V(U + hu, v + hv) - V(U + hu, v - hv) - V(U - hu, v + hv) + V(U - hu, v - hv)) / (4 * hu * hv))


def to_strike(F, v, T, t, delta, s=1.0):
    p = phi(t)
    d1 = p * float(Ninv(p * delta / s))
    return F * math.exp(-d1 * v * math.sqrt(T) + v * v * T / 2)


def from_strike(F, v, T, t, K, s=1.0):
    p = phi(t)
    d1 = (math.log(F / K) + v * v * T / 2) / (v * math.sqrt(T))
    return p * s * float(N(p * d1))


def svi_w(P, k):
    a, b, rho, m, sg = P
    return a + b * (rho * (k - m) + math.sqrt((k - m) ** 2 + sg * sg))


def svi_g(P, k):
    a, b, rho, m, sg = P
    R = math.sqrt((k - m) ** 2 + sg * sg)
    w = svi_w(P, k)
    w1 = b * (rho + (k - m) / R)
    w2 = b * sg * sg / R ** 3
    return (1 - k * w1 / (2 * w)) ** 2 - w1 * w1 / 4 * (1 / w + .25) + w2 / 2


def fit(res, starts, lo, hi):
    """Best of several starts; returns (x, rmse, spread of the near-best solutions)."""
    best = []
    for s in starts:
        r = least_squares(res, s, bounds=(lo, hi), xtol=1e-15, ftol=1e-15, gtol=1e-15, max_nfev=20000)
        best.append((float(np.sqrt(np.mean(r.fun ** 2))), r.x))
    best.sort(key=lambda z: z[0])
    near = [x for e, x in best if e <= best[0][0] * (1 + 1e-6) + 1e-13]
    return best[0][1], best[0][0], max(float(np.max(np.abs(x - near[0]))) for x in near)


def svi_fit(ks, ws):
    ks, ws = np.array(ks), np.array(ws)
    res = lambda x: np.array([svi_w(x, k) for k in ks]) - ws  # noqa: E731
    wm = float(min(ws))
    starts = [[wm * .5, .1, -.3, 0, .1], [wm * .8, .05, 0, .05, .2], [0, .2, -.6, -.05, .3], [wm * .2, .3, .2, .1, .05]]
    return fit(res, starts, [-1, 1e-8, -.999, -2, 1e-6], [5, 5, .999, 2, 5])


def ssvi_phi(th, eta, g):
    return eta * th ** -g * (1 + th) ** (g - 1)


def ssvi_w(k, th, rho, eta, g):
    p = ssvi_phi(th, eta, g)
    return th / 2 * (1 + rho * p * k + math.sqrt((p * k + rho) ** 2 + 1 - rho * rho))


def surf_w(sf, T, k):
    Ts, ks, vs = sf["expiry_years"], sf["log_moneyness"], sf["vols"]
    kk = min(max(k, ks[0]), ks[-1])

    def sl(j):
        i = min(max(int(np.searchsorted(ks, kk, side="right")) - 1, 0), len(ks) - 2)
        u = (kk - ks[i]) / (ks[i + 1] - ks[i])
        return (1 - u) * vs[j][i] ** 2 * Ts[j] + u * vs[j][i + 1] ** 2 * Ts[j]
    if T <= Ts[0]:
        return sl(0) * T / Ts[0]
    if T >= Ts[-1]:
        return sl(len(Ts) - 1) * T / Ts[-1]
    j = int(np.searchsorted(Ts, T, side="right")) - 1
    u = (T - Ts[j]) / (Ts[j + 1] - Ts[j])
    return (1 - u) * sl(j) + u * sl(j + 1)


def surf_check(sf, tol=1e-12):
    Ts, ks, vs = sf["expiry_years"], sf["log_moneyness"], sf["vols"]
    w = [[v * v * T for v in row] for T, row in zip(Ts, vs)]
    cal = [{"expiry_index": j, "k_index": i} for j in range(1, len(Ts)) for i in range(len(ks)) if w[j][i] < w[j - 1][i] - tol]
    but, gaps = [], []
    K = [math.exp(k) for k in ks]
    for j, T in enumerate(Ts):
        c = [black("CALL", 1.0, x, v, T) for x, v in zip(K, vs[j])]
        s = [(c[i + 1] - c[i]) / (K[i + 1] - K[i]) for i in range(len(K) - 1)]
        but += [{"expiry_index": j, "k_index": i, "kind": "SLOPE"} for i, x in enumerate(s) if x < -1 - tol or x > tol]
        but += [{"expiry_index": j, "k_index": i + 1, "kind": "CONVEXITY"} for i in range(len(s) - 1) if s[i + 1] < s[i] - tol]
        gaps += [abs(s[i + 1] - s[i]) for i in range(len(s) - 1)]
    return cal, but, min(gaps)


def hagan(f, x, T, al, be, rho, nu):
    A = (f * x) ** (1 - be)
    L = math.log(f / x)
    c = (1 - be) ** 2 * L * L
    z = nu / al * math.sqrt(A) * L
    m = 1 - rho * z / 2 - (3 * rho ** 2 - 2) * z * z / 12 if abs(z) < 1e-7 else z / math.log((math.sqrt(1 - 2 * rho * z + z * z) + z - rho) / (1 - rho))
    den = math.sqrt(A) * (1 + c / 24 + c * c / 1920)
    h = 1 + T * ((1 - be) ** 2 * al * al / (24 * A) + rho * be * nu * al / (4 * math.sqrt(A)) + (2 - 3 * rho ** 2) * nu ** 2 / 24)
    return al * m * h / den


def sabr_density(f, x, T, al, be, rho, nu, h):
    c = lambda y: black("CALL", f, y, hagan(f, y, T, al, be, rho, nu), T)  # noqa: E731
    return (c(x + h) - 2 * c(x) + c(x - h)) / h ** 2


def sabr_fit(f, T, be, xs, vols):
    vols = np.array(vols)
    res = lambda p: np.array([hagan(f, x, T, p[0], be, p[1], p[2]) for x in xs]) - vols  # noqa: E731
    atm = float(np.median(vols)) * f ** (1 - be)
    return fit(res, [[atm, 0, .3], [atm, -.5, .6], [atm * .8, .4, .2], [atm * 1.2, -.2, 1.0]], [1e-8, -.999, 1e-8], [50, .999, 10])


def arbfree(f0, T, al, be, rho, nu, cells, below, steps, xs, sign=1.0):
    J = cells
    h = f0 / (below - .5)
    u = (np.arange(1, J + 1) - .5) * h
    z = (u ** (1 - be) - f0 ** (1 - be)) / (1 - be)
    Dsq = (al * al + 2 * rho * al * nu * z + nu * nu * z * z) * u ** (2 * be)
    with np.errstate(divide="ignore", invalid="ignore"):
        G = (u ** be - f0 ** be) / (u - f0)
    G[below - 1] = be * f0 ** (be - 1) if be > 0 else 0.0
    dt = T / steps
    lam = dt / h ** 2
    Q = np.zeros(J)
    Q[below - 1] = 1 / h
    PL = PR = 0.0
    for i in range(1, steps + 1):
        M = Dsq * np.exp(sign * rho * nu * al * G * i * dt) / 2
        ab = np.zeros((3, J))
        ab[1] = 1 + 2 * lam * M
        ab[1, 0] = 1 + 3 * lam * M[0]
        ab[1, -1] = 1 + 3 * lam * M[-1]
        ab[0, 1:] = -lam * M[1:]
        ab[2, :-1] = -lam * M[:-1]
        Q = solve_banded((1, 1), ab, Q)
        PL += 2 * dt * M[0] * Q[0] / h
        PR += 2 * dt * M[-1] * Q[-1] / h
    umax = J * h
    calls = []
    for x in xs:
        c = int(x / h)
        top = (c + 1) * h
        calls.append(float(np.sum((u[c + 1:] - x) * Q[c + 1:]) * h + Q[c] * (top - x) ** 2 / 2 + (umax - x) * PR))
    return dict(calls=calls, mass=float(np.sum(Q) * h + PL + PR), mean=float(np.sum(u * Q) * h + umax * PR), absorbed=float(PL), min_density=float(Q.min()))
