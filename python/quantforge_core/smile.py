"""Delta conventions, SVI, SSVI and the vol surface
(specifications/05-volatility/smile-and-surface.md, surface risk in 06-risk/vol-greeks.md)."""
import itertools
import math
from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass

lazy import numpy as np

from .black import big_n, black76_position, n_inverse
from .errors import QfError
from .fitting import best_of

Floats = Sequence[float]


def _domain(message: str, field: str | None = None) -> QfError:
    return QfError("E_DOMAIN", message, field)


def _input(message: str, field: str | None = None) -> QfError:
    return QfError("E_INPUT", message, field)


def _increasing(values: Floats) -> bool:
    return all(a < b for a, b in itertools.pairwise(values))


# --- delta ---


def _not_empty(**lists: Sequence[object]) -> None:
    """Ruling C17: an empty list is E_INPUT, ahead of every E_DOMAIN."""
    for key, values in lists.items():
        if not values:
            raise _input(f"{key} is empty", key)


def _scale_matches(convention: str, scale: float | None) -> None:
    """Ruling C15: the first rule check."""
    if (convention == "FORWARD") != (scale is None):
        raise _input("scale must be null with FORWARD and a number with SPOT", "scale")


def _delta_scale(convention: str, scale: float | None) -> float:
    _scale_matches(convention, scale)
    if scale is None:
        return 1.0
    if scale <= 0:
        raise _domain("scale must be above 0", "scale")
    return scale


def _delta_common(forward: float, vol: float, expiry_years: float) -> None:
    if forward <= 0 or vol <= 0 or expiry_years <= 0:
        raise _domain("forward, vol and expiry_years must be above 0")


def delta_to_strike(
    forward: float, vol: float, expiry_years: float, option_type: str, delta: float,
    convention: str, scale: float | None,
) -> float:
    s = _delta_scale(convention, scale)
    _delta_common(forward, vol, expiry_years)
    phi = 1.0 if option_type == "CALL" else -1.0
    p = phi * delta / s
    if not 0 < p < 1:
        raise _domain("the delta is out of range", "delta")
    d1 = phi * n_inverse(p)
    root = vol * math.sqrt(expiry_years)
    return forward * math.exp(-d1 * root + 0.5 * root * root)


def delta_from_strike(
    forward: float, vol: float, expiry_years: float, option_type: str, strike: float,
    convention: str, scale: float | None,
) -> float:
    s = _delta_scale(convention, scale)
    _delta_common(forward, vol, expiry_years)
    if strike <= 0:
        raise _domain("strike must be above 0", "strike")
    phi = 1.0 if option_type == "CALL" else -1.0
    root = vol * math.sqrt(expiry_years)
    d1 = (math.log(forward / strike) + 0.5 * root * root) / root
    return phi * s * big_n(phi * d1)


def rr_bf(
    forward: float, expiry_years: float, atm_vol: float, atm_convention: str, rr: float, bf: float,
    delta: float, convention: str, scale: float | None,
) -> dict[str, float]:
    _scale_matches(convention, scale)
    call_vol, put_vol = atm_vol + bf + rr / 2, atm_vol + bf - rr / 2
    if min(atm_vol, call_vol, put_vol) <= 0:
        raise _domain("a vol is not above 0")
    _delta_common(forward, atm_vol, expiry_years)
    atm_strike = forward
    if atm_convention == "DELTA_NEUTRAL":
        atm_strike = forward * math.exp(atm_vol * atm_vol * expiry_years / 2)
    return {
        "atm_strike": atm_strike, "call_vol": call_vol, "put_vol": put_vol,
        "call_strike": delta_to_strike(
            forward, call_vol, expiry_years, "CALL", delta, convention, scale
        ),
        "put_strike": delta_to_strike(
            forward, put_vol, expiry_years, "PUT", -delta, convention, scale
        ),
    }


# --- SVI ---


@dataclass(frozen=True)
class Svi:
    a: float
    b: float
    rho: float
    m: float
    sigma: float

    def total_variance(self, k: float) -> float:
        x = k - self.m
        return self.a + self.b * (self.rho * x + math.sqrt(x * x + self.sigma**2))


def _check_svi(p: Svi) -> None:
    if p.b < 0 or abs(p.rho) >= 1 or p.sigma <= 0:
        raise _domain("svi parameters are out of range", "svi")
    if p.a + p.b * p.sigma * math.sqrt(1 - p.rho**2) <= 0:
        raise _domain("svi minimum variance is not positive", "svi")


def svi_evaluate(p: Svi, ks: Floats, expiry_years: float) -> dict[str, object]:
    _not_empty(log_moneyness=ks)
    _check_svi(p)
    if expiry_years <= 0:
        raise _domain("expiry_years must be above 0", "expiry_years")
    ws, vols, gs = [], [], []
    for k in ks:
        w = p.total_variance(k)
        x = k - p.m
        big_r = math.sqrt(x * x + p.sigma**2)
        w1 = p.b * (p.rho + x / big_r)
        w2 = p.b * p.sigma**2 / big_r**3
        g = (1 - k * w1 / (2 * w)) ** 2 - (w1 * w1 / 4) * (1 / w + 0.25) + w2 / 2
        ws.append(w)
        vols.append(math.sqrt(w / expiry_years))
        gs.append(g)
    min_g = min(gs)
    return {
        "total_variance": ws, "implied_vol": vols, "g": gs, "min_g": min_g,
        "butterfly_free": min_g >= 0,
    }


def _svi_from(x: np.ndarray) -> tuple[float, float, float, float, float]:
    """Unconstrained to the domain: the excess of `a` over its bound stays positive."""
    b, rho, sigma = math.exp(x[1]), math.tanh(x[2]), math.exp(x[4])
    a = math.exp(x[0]) - b * sigma * math.sqrt(1 - rho * rho)
    return a, b, rho, x[3], sigma


def _svi_starts(k: np.ndarray, w: np.ndarray, root_weight: np.ndarray) -> list[np.ndarray]:
    """For fixed (m, sigma) the model is linear in (a, b, b rho): solve that for each start."""
    starts = []
    for m in np.quantile(k, (0.1, 0.3, 0.5, 0.7, 0.9)):
        for sigma in (0.02, 0.08, 0.2, 0.5):
            big_r = np.sqrt((k - m) ** 2 + sigma**2)
            design = np.column_stack((np.ones_like(k), big_r, k - m)) * root_weight[:, None]
            a, b, c = np.linalg.lstsq(design, w * root_weight, rcond=None)[0]
            b = max(b, 1e-3)
            rho = min(max(c / b, -0.95), 0.95)
            excess = max(a + b * sigma * math.sqrt(1 - rho * rho), 1e-4)
            starts.append(
                np.array((math.log(excess), math.log(b), math.atanh(rho), m, math.log(sigma)))
            )
    return starts


def svi_calibrate(ks: Floats, ws: Floats, weights: Floats | None) -> tuple[Svi, float]:
    if len(ks) != len(ws) or (weights is not None and len(weights) != len(ks)):
        raise _input("lengths differ", "total_variance")
    if len(ks) < 5:
        raise _input("fewer than 5 points", "log_moneyness")
    if not _increasing(ks):
        raise _input("log_moneyness must be strictly increasing", "log_moneyness")
    if min(ws) <= 0:
        raise _domain("a total_variance is not positive", "total_variance")
    if weights is not None and min(weights) <= 0:
        raise _domain("a weight is not positive", "weights")
    k, w = np.array(ks), np.array(ws)
    weight = np.ones_like(k) if weights is None else np.array(weights)
    root_weight = np.sqrt(weight)

    def residual(x: np.ndarray) -> np.ndarray:
        a, b, rho, m, sigma = _svi_from(x)
        return root_weight * (a + b * (rho * (k - m) + np.sqrt((k - m) ** 2 + sigma**2)) - w)

    best = best_of(residual, _svi_starts(k, w, root_weight))
    if best is None:
        raise QfError("E_NO_CONVERGENCE", "the SVI fit found no start")
    return Svi(*_svi_from(best[0])), math.sqrt(best[1] / float(weight.sum()))


# --- SSVI ---


def _ssvi_phi(theta: float, eta: float, gamma: float) -> float:
    return eta * theta**-gamma * (1 + theta) ** (gamma - 1)


def _ssvi_w(k: float, theta: float, rho: float, phi: float) -> float:
    x = phi * k
    return theta / 2 * (1 + rho * x + math.sqrt((x + rho) ** 2 + 1 - rho * rho))


def ssvi_evaluate(
    rho: float, eta: float, gamma: float, thetas: Floats, ks: Floats
) -> dict[str, object]:
    _not_empty(thetas=thetas, log_moneyness=ks)
    if abs(rho) >= 1 or eta <= 0 or not 0 < gamma <= 1 or any(t <= 0 for t in thetas):
        raise _domain("ssvi parameters are out of range")
    if not _increasing(thetas):
        raise _input("thetas must be strictly increasing", "thetas")
    rows, butterfly, calendar = [], True, True
    for theta in thetas:
        phi = _ssvi_phi(theta, eta, gamma)
        rows.append([_ssvi_w(k, theta, rho, phi) for k in ks])
        one = 1 + abs(rho)
        butterfly = butterfly and theta * phi * one < 4 and theta * phi * phi * one <= 4
        bound = 1 + math.sqrt(1 - rho * rho)
        calendar = calendar and rho * rho * (1 - gamma) / (1 + theta) <= bound
    return {"total_variance": rows, "butterfly_free": butterfly, "calendar_free": calendar}


def ssvi_calibrate(
    thetas: Floats, ks: Floats, rows: Sequence[Floats]
) -> tuple[float, float, float, float]:
    if len(rows) != len(thetas) or any(len(r) != len(ks) for r in rows):
        raise _input("rows do not match thetas and log_moneyness", "total_variance")
    if len(thetas) * len(ks) < 3:
        raise _input("fewer than 3 points", "total_variance")
    if any(t <= 0 for t in thetas):
        raise _domain("a theta is not positive", "thetas")
    if not _increasing(thetas):
        raise _input("thetas must be strictly increasing", "thetas")
    th = np.array(thetas)[:, None]
    k = np.array(ks)[None, :]
    target = np.array(rows)

    def unpack(x: np.ndarray) -> tuple[float, float, float]:
        return math.tanh(x[0]), math.exp(x[1]), 1 / (1 + math.exp(-x[2]))

    def residual(x: np.ndarray) -> np.ndarray:
        rho, eta, gamma = unpack(x)
        u = eta * th**-gamma * (1 + th) ** (gamma - 1) * k
        w = th / 2 * (1 + rho * u + np.sqrt((u + rho) ** 2 + 1 - rho * rho))
        return (w - target).ravel()

    starts = [
        np.array((math.atanh(r), math.log(e), g))
        for r in (-0.7, -0.2, 0.3) for e in (0.3, 1.0, 3.0) for g in (-1.0, 0.0, 1.5)
    ]
    best = best_of(residual, starts)
    if best is None:
        raise QfError("E_NO_CONVERGENCE", "the SSVI fit found no start")
    rho, eta, gamma = unpack(best[0])
    return rho, eta, gamma, math.sqrt(best[1] / target.size)


# --- surface ---


@dataclass
class Surface:
    expiry_years: list[float]
    log_moneyness: list[float]
    vols: list[list[float]]


def check_surface(s: Surface) -> None:
    ts, ks, vols = s.expiry_years, s.log_moneyness, s.vols
    if not ts or not ks or len(vols) != len(ts) or any(len(r) != len(ks) for r in vols):
        raise _input("the vols shape does not match the grids", "surface")
    if not _increasing(ts) or not _increasing(ks):
        raise _input("grids must be strictly increasing", "surface")
    if min(ts) <= 0 or min(min(r) for r in vols) <= 0:
        raise _domain("a grid time or vol is not positive", "surface")


def _slice_w(s: Surface, j: int, k: float) -> float:
    ks, t, row = s.log_moneyness, s.expiry_years[j], s.vols[j]
    if k <= ks[0]:
        return row[0] ** 2 * t
    if k >= ks[-1]:
        return row[-1] ** 2 * t
    i = bisect_right(ks, k) - 1
    u = (k - ks[i]) / (ks[i + 1] - ks[i])
    return (1 - u) * row[i] ** 2 * t + u * row[i + 1] ** 2 * t


def _query(s: Surface, t: float, k: float) -> float:
    ts = s.expiry_years
    if t <= ts[0]:
        return _slice_w(s, 0, k) * t / ts[0]
    if t >= ts[-1]:
        return _slice_w(s, len(ts) - 1, k) * t / ts[-1]
    j = bisect_right(ts, t) - 1
    u = (t - ts[j]) / (ts[j + 1] - ts[j])
    return (1 - u) * _slice_w(s, j, k) + u * _slice_w(s, j + 1, k)


def surface_query(s: Surface, points: Sequence[tuple[float, float]]) -> tuple[list[float], list[float]]:
    _not_empty(points=points)
    check_surface(s)
    if any(t <= 0 for t, _ in points):
        raise _domain("expiry_years must be above 0", "points")
    ws = [_query(s, t, k) for t, k in points]
    return ws, [math.sqrt(w / p[0]) for w, p in zip(ws, points, strict=True)]


def _undiscounted_call(k_log: float, v: float, t: float) -> float:
    root = v * math.sqrt(t)
    d1 = -k_log / root + root / 2
    return big_n(d1) - math.exp(k_log) * big_n(d1 - root)


def surface_check(s: Surface) -> dict[str, object]:
    check_surface(s)
    tol = 1e-12
    calendar, butterfly = [], []
    ts, ks = s.expiry_years, s.log_moneyness
    for j in range(1, len(ts)):
        for i in range(len(ks)):
            if s.vols[j][i] ** 2 * ts[j] < s.vols[j - 1][i] ** 2 * ts[j - 1] - tol:
                calendar.append({"expiry_index": j, "k_index": i})
    strikes = [math.exp(k) for k in ks]
    for j, t in enumerate(ts):
        c = [_undiscounted_call(k, v, t) for k, v in zip(ks, s.vols[j], strict=True)]
        slopes = [
            (c[i + 1] - c[i]) / (strikes[i + 1] - strikes[i]) for i in range(len(ks) - 1)
        ]
        for i, slope in enumerate(slopes):
            if slope < -1 - tol or slope > tol:
                butterfly.append({"expiry_index": j, "k_index": i, "kind": "SLOPE"})
        for i in range(len(slopes) - 1):
            if slopes[i + 1] < slopes[i] - tol:
                butterfly.append({"expiry_index": j, "k_index": i + 1, "kind": "CONVEXITY"})
    return {
        "calendar_violations": calendar, "butterfly_violations": butterfly,
        "arbitrage_free": not calendar and not butterfly,
    }


@dataclass(frozen=True)
class Position:
    option_type: str
    forward: float
    strike: float
    discount_factor: float
    expiry_years: float
    quantity: float


def _book_pv(s: Surface, book: Sequence[Position]) -> float:
    total = 0.0
    for p in book:
        k = math.log(p.strike / p.forward)
        v = math.sqrt(_query(s, p.expiry_years, k) / p.expiry_years)
        total += black76_position(
            p.option_type, p.forward, p.strike, p.discount_factor, p.expiry_years, v, p.quantity
        )[0]
    return total


def surface_vega(s: Surface, book: Sequence[Position]) -> dict[str, object]:
    _not_empty(positions=book)
    check_surface(s)
    for p in book:
        if min(p.forward, p.strike, p.discount_factor, p.expiry_years) <= 0:
            raise _domain("a position input is not positive", "positions")
    h = 1e-4
    if min(min(r) for r in s.vols) - h <= 0:
        raise _domain("a node vol is too small to bump", "surface")
    buckets = []
    for row in s.vols:
        out = []
        for i, v in enumerate(row):
            row[i] = v + h
            up = _book_pv(s, book)
            row[i] = v - h
            down = _book_pv(s, book)
            row[i] = v
            out.append((up - down) / (2 * h))
        buckets.append(out)

    def moved(by: float) -> float:
        return _book_pv(
            Surface(s.expiry_years, s.log_moneyness, [[v + by for v in r] for r in s.vols]), book
        )

    total = 0.0
    for out in buckets:
        for v in out:
            total += v
    return {
        "pv": _book_pv(s, book), "bucket_vega": buckets,
        "parallel_vega": (moved(h) - moved(-h)) / (2 * h), "bucket_sum": total,
    }
