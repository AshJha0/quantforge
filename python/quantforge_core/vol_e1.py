"""Stage E, E1: arbitrage checks on SVI surfaces, local and forward vol, smile dynamics and vol of vol.

Specs: specifications/05-volatility/arb-free-surfaces.md and local-and-forward-vol.md, with
rulings E-A1 to E-A8 in specifications/stage-e-rulings.md. SVI itself is stage C (smile.py).
"""
import itertools
import math
from collections.abc import Sequence
from dataclasses import dataclass

from .black import big_n, small_n
from .errors import QfError
from .numeric import ordered_sum
from .smile import Svi, _check_svi, svi_calibrate

Floats = Sequence[float]


def _input(message: str, field: str | None = None) -> QfError:
    return QfError("E_INPUT", message, field)


def _domain(message: str, field: str | None = None) -> QfError:
    return QfError("E_DOMAIN", message, field)


def _arbitrage(message: str, field: str | None = None) -> QfError:
    return QfError("E_ARBITRAGE", message, field)


def _increasing(values: Floats) -> bool:
    return all(a < b for a, b in itertools.pairwise(values))


def _derivatives(p: Svi, k: float) -> tuple[float, float, float]:
    """w, w' and w'' of a raw SVI slice at k, as smile.svi_evaluate."""
    x = k - p.m
    big_r = math.sqrt(x * x + p.sigma**2)
    return p.total_variance(k), p.b * (p.rho + x / big_r), p.b * p.sigma**2 / big_r**3


def _g(k: float, w: float, w1: float, w2: float) -> float:
    return (1 - k * w1 / (2 * w)) ** 2 - (w1 * w1 / 4) * (1 / w + 0.25) + w2 / 2


@dataclass(frozen=True)
class Slice:
    expiry_years: float
    svi: Svi


def check_slices_input(slices: Sequence[Slice]) -> None:
    """The E_INPUT part of the `slices` checks."""
    if not slices:
        raise _input("slices is empty", "slices")
    if not _increasing([s.expiry_years for s in slices]):
        raise _input("expiry_years must be strictly increasing", "slices")


def check_slices(slices: Sequence[Slice]) -> None:
    """The `slices` object checks, in spec order. The count limit is applied at the CLI gate."""
    expiries = [s.expiry_years for s in slices]
    check_slices_input(slices)
    if any(t <= 0 for t in expiries):
        raise _domain("an expiry_years is not positive", "slices")
    for s in slices:
        _check_svi(s.svi)


def _wings(p: Svi) -> tuple[tuple[float, float], tuple[float, float]]:
    """((sL, cL), (sR, cR)), in binary64 exactly as written in the spec (ruling E-A2)."""
    left = (p.b * (1 - p.rho), p.a + p.b * (1 - p.rho) * p.m)
    right = (p.b * (1 + p.rho), p.a - p.b * (1 + p.rho) * p.m)
    return left, right


def _check(slices: Sequence[Slice], ks: Floats, reject: bool) -> dict[str, object]:
    butterfly: list[dict[str, object]] = []
    calendar: list[dict[str, object]] = []
    wings: list[dict[str, object]] = []
    previous: list[float] | None = None
    for j, s in enumerate(slices):
        ws = []
        for i, k in enumerate(ks):
            w, w1, w2 = _derivatives(s.svi, k)
            ws.append(w)
            if _g(k, w, w1, w2) < 0:
                butterfly.append({"expiry_index": j, "k_index": i})
        if previous is not None:
            calendar += [{"expiry_index": j, "k_index": i}
                         for i, (w, w0) in enumerate(zip(ws, previous, strict=True)) if w < w0]
        previous = ws
        sides = _wings(s.svi)
        for side, (slope, _) in zip(("LEFT", "RIGHT"), sides, strict=True):
            if slope >= 2:  # ruling E-A15: a slope of exactly 2 is flagged
                wings.append({"expiry_index": j, "side": side, "kind": "LEE"})
        if j:
            before = _wings(slices[j - 1].svi)
            for side, (slope, c), (slope0, c0) in zip(("LEFT", "RIGHT"), sides, before,
                                                      strict=True):
                if slope < slope0 or (slope == slope0 and c < c0):
                    wings.append({"expiry_index": j, "side": side, "kind": "CALENDAR"})
    free = not (butterfly or calendar or wings)
    if reject and not free:
        raise _arbitrage("the surface has arbitrage", "slices")
    return {"butterfly_violations": butterfly, "calendar_violations": calendar,
            "wing_violations": wings, "arbitrage_free": free}


def _check_grid(ks: Floats) -> None:
    if not ks or not _increasing(ks):
        raise _input("log_moneyness must be strictly increasing, with at least 1 point",
                     "log_moneyness")


def surface_check(slices: Sequence[Slice], ks: Floats, reject: bool) -> dict[str, object]:
    check_slices(slices)
    _check_grid(ks)
    return _check(slices, ks, reject)


def ssvi_to_svi(rho: float, eta: float, gamma: float, theta: float) -> Svi:
    if abs(rho) >= 1 or eta <= 0 or not 0 < gamma <= 1 or theta <= 0:
        raise _domain("ssvi parameters are out of range")
    phi = eta * theta**-gamma * (1 + theta) ** (gamma - 1)
    return Svi(theta * (1 - rho * rho) / 2, theta * phi / 2, rho, -rho / phi,
               math.sqrt(1 - rho * rho) / phi)


def fit_surface(expiries: Floats, ks: Floats, rows: Sequence[Floats],
                reject: bool) -> tuple[list[Slice], list[float], dict[str, object]]:
    if not expiries or not _increasing(expiries):
        raise _input("expiry_years must be strictly increasing", "expiry_years")
    if len(rows) != len(expiries):
        raise _input("one total_variance row is needed per expiry", "total_variance")
    fitted, rmses = [], []
    for t, row in zip(expiries, rows, strict=True):
        p, rmse = svi_calibrate(ks, row, None)
        fitted.append(Slice(t, p))
        rmses.append(rmse)
    check_slices(fitted)
    return fitted, rmses, _check(fitted, ks, reject)


def _surface(slices: Sequence[Slice], t: float, k: float) -> tuple[float, float, float, float]:
    """(w, w_k, w_kk, w_T) at (t, k), by ruling E-A4."""
    n = len(slices)
    if n == 1 or t < slices[0].expiry_years or t >= slices[-1].expiry_years:
        s = slices[0] if t < slices[0].expiry_years else slices[-1]
        w, w1, w2 = _derivatives(s.svi, k)
        scale = t / s.expiry_years
        return w * scale, w1 * scale, w2 * scale, w / s.expiry_years
    j = max(i for i in range(n - 1) if slices[i].expiry_years <= t)
    t0, t1 = slices[j].expiry_years, slices[j + 1].expiry_years
    lam = (t - t0) / (t1 - t0)
    a, b = _derivatives(slices[j].svi, k), _derivatives(slices[j + 1].svi, k)
    w, w1, w2 = ((1 - lam) * x + lam * y for x, y in zip(a, b, strict=True))
    return w, w1, w2, (b[0] - a[0]) / (t1 - t0)


def dupire(slices: Sequence[Slice],
           points: Sequence[tuple[float, float]]) -> tuple[list[float], list[float], list[float]]:
    check_slices(slices)
    if not points:
        raise _input("points is empty", "points")
    if any(t <= 0 for t, _ in points):
        raise _domain("a point has expiry_years not above 0", "points")
    ws, vols, local = [], [], []
    for t, k in points:
        w, w1, w2, wt = _surface(slices, t, k)
        if wt <= 0:
            raise _arbitrage("w_T is not positive: calendar arbitrage", "points")
        g = _g(k, w, w1, w2)
        if g <= 0:
            raise _arbitrage("g is not positive: butterfly arbitrage", "points")
        ws.append(w)
        vols.append(math.sqrt(w / t))
        local.append(math.sqrt(wt / g))
    return ws, vols, local


def forward_vols(expiries: Floats, vols: Floats) -> list[float]:
    if not expiries or len(vols) != len(expiries):
        raise _input("expiry_years and vols must be non-empty and of one length", "vols")
    if not _increasing(expiries):
        raise _input("expiry_years must be strictly increasing", "expiry_years")
    if expiries[0] <= 0:  # ruling E-A36
        raise _domain("the first expiry_years is not above 0", "expiry_years")
    if any(v <= 0 for v in vols):
        raise _domain("a vol is not above 0", "vols")
    out = [vols[0]]
    for i in range(1, len(vols)):
        radicand = (vols[i] ** 2 * expiries[i] - vols[i - 1] ** 2 * expiries[i - 1]) / (
            expiries[i] - expiries[i - 1])
        if radicand < 0:
            raise _arbitrage("negative forward variance", "vols")
        out.append(math.sqrt(radicand))
    return out


def _black(phi: float, f: float, k: float, v: float, t: float, d: float) -> tuple[float, float]:
    """(price, d1) of a Black option on the forward."""
    root = v * math.sqrt(t)
    d1 = math.log(f / k) / root + root / 2
    d2 = d1 - root
    return d * phi * (f * big_n(phi * d1) - k * big_n(phi * d2)), d1


def smile_dynamics(p: Svi, t: float, spot: float, shifted: float, rate: float, q: float,
                   strikes: Floats, rule: str, option_type: str) -> dict[str, list[float]]:
    if not strikes:
        raise _input("strikes is empty", "strikes")
    _check_svi(p)
    if t <= 0:
        raise _domain("expiry_years must be above 0", "expiry_years")
    if spot <= 0:
        raise _domain("spot must be above 0", "spot")
    if shifted <= 0:
        raise _domain("spot_shifted must be above 0", "spot_shifted")
    if any(k <= 0 for k in strikes):
        raise _domain("a strike is not above 0", "strikes")
    growth = math.exp((rate - q) * t)
    f0, f1, d = spot * growth, shifted * growth, math.exp(-rate * t)
    phi = 1.0 if option_type == "CALL" else -1.0
    carry = math.exp(-q * t)
    out: dict[str, list[float]] = {
        "vols_base": [], "vols_shifted": [], "prices_base": [], "prices_shifted": [],
        "deltas": []}
    for strike in strikes:
        k0 = math.log(strike / f0)
        w, w1, _ = _derivatives(p, k0)
        v0 = math.sqrt(w / t)
        v1 = v0 if rule == "STICKY_STRIKE" else math.sqrt(p.total_variance(
            math.log(strike / f1)) / t)
        price0, d1 = _black(phi, f0, strike, v0, t, d)
        price1, _ = _black(phi, f1, strike, v1, t, d)
        delta = carry * big_n(d1) if phi > 0 else -carry * big_n(-d1)
        if rule == "STICKY_DELTA":
            vega = spot * carry * small_n(d1) * math.sqrt(t)
            delta += vega * (-(w1 / (2 * v0 * t)) / spot)
        out["vols_base"].append(v0)
        out["vols_shifted"].append(v1)
        out["prices_base"].append(price0)
        out["prices_shifted"].append(price1)
        out["deltas"].append(delta)
    return out


def vol_of_vol(vols: Floats, periods_per_year: float, method: str) -> tuple[float, float]:
    """(vol_of_vol, mean_change): sample standard deviation, divisor n - 1 (ruling E-A7)."""
    if len(vols) < 3:
        raise _input("at least 3 vols are needed", "vols")
    if any(v <= 0 for v in vols):
        raise _domain("a vol is not above 0", "vols")
    if periods_per_year <= 0:
        raise _domain("periods_per_year must be above 0", "periods_per_year")
    pairs = list(itertools.pairwise(vols))
    xs = [math.log(b / a) for a, b in pairs] if method == "LOG" else [b - a for a, b in pairs]
    mean = ordered_sum(xs) / len(xs)
    spread = ordered_sum((x - mean) ** 2 for x in xs) / (len(xs) - 1)
    return math.sqrt(periods_per_year) * math.sqrt(spread), mean
