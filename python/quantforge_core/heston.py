"""Heston, Bates and Merton prices and the SLV leverage reference scheme.

Spec: specifications/05-volatility/heston-family.md, rulings E-A12 to E-A14 in
specifications/stage-e-rulings.md. Prices use Lewis's single integral with the reference recipe:
Gauss-Legendre, 256 nodes on u in [0, 200]. The SLV scheme follows the spec step by step.
"""
import cmath
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from . import arb_surface
from .black import big_n
from .errors import QfError
from .numeric import ordered_sum, thomas

Floats = Sequence[float]
Cf = Callable[[complex], complex]


def _input(message: str, field: str | None = None) -> QfError:
    return QfError("E_INPUT", message, field)


def _domain(message: str, field: str | None = None) -> QfError:
    return QfError("E_DOMAIN", message, field)


@dataclass(frozen=True)
class Heston:
    v0: float
    kappa: float
    theta: float
    xi: float
    rho: float


@dataclass(frozen=True)
class Jumps:
    intensity: float
    mean_log_jump: float
    log_jump_vol: float

    @property
    def kbar(self) -> float:
        return math.exp(self.mean_log_jump + self.log_jump_vol**2 / 2) - 1


def check_heston(h: Heston) -> None:
    for key in ("v0", "kappa", "theta", "xi"):
        if not getattr(h, key) > 0:
            raise _domain(f"{key} must be above 0", "heston")
    if abs(h.rho) >= 1:
        raise _domain("|rho| must be below 1", "heston")


def _check_jumps(j: Jumps) -> None:
    if j.intensity < 0:
        raise _domain("intensity must not be negative", "jumps")
    if j.log_jump_vol < 0:
        raise _domain("log_jump_vol must not be negative", "jumps")


def _check_common(spot: float, strikes: Floats, t: float) -> None:
    if not strikes:
        raise _input("strikes is empty", "strikes")
    if not spot > 0:
        raise _domain("spot must be above 0", "spot")
    if any(not k > 0 for k in strikes):
        raise _domain("a strike is not above 0", "strikes")
    if not t > 0:
        raise _domain("expiry_years must be above 0", "expiry_years")


def heston_phi(h: Heston, t: float) -> Cf:
    """phi(u) of X = ln(S_T/F), the little-trap form [Alb07]."""
    xi2 = h.xi * h.xi

    def phi(u: complex) -> complex:
        iu = 1j * u
        b = h.kappa - h.rho * h.xi * iu
        d = cmath.sqrt(b * b + xi2 * (iu + u * u))
        g = (b - d) / (b + d)
        e = cmath.exp(-d * t)
        c = (h.kappa / xi2) * ((b - d) * t - 2 * cmath.log((1 - g * e) / (1 - g)))
        big_d = ((b - d) / xi2) * (1 - e) / (1 - g * e)
        return cmath.exp(c * h.theta + big_d * h.v0)

    return phi


def _jump_phi(j: Jumps, t: float) -> Cf:
    kbar = j.kbar

    def phi(u: complex) -> complex:
        iu = 1j * u
        jump = cmath.exp(iu * j.mean_log_jump - j.log_jump_vol**2 * u * u / 2)
        return cmath.exp(j.intensity * t * (jump - 1 - iu * kbar))

    return phi


def heston_cf(t: float, h: Heston, us: Floats) -> tuple[list[float], list[float]]:
    if not us:
        raise _input("u is empty", "u")
    if not t > 0:
        raise _domain("expiry_years must be above 0", "expiry_years")
    check_heston(h)
    if any(u < 0 for u in us):
        raise _domain("u must not be negative", "u")
    phi = heston_phi(h, t)
    values = [phi(complex(u)) for u in us]
    return [v.real for v in values], [v.imag for v in values]


def _unit_rule() -> tuple[tuple[float, ...], tuple[float, ...]]:
    """Gauss-Legendre, 1024 nodes on [-1, 1]: numpy's leggauss values, shipped as data."""
    from ._legendre_1024 import NODES, WEIGHTS

    return NODES, WEIGHTS


def _nodes(t: float) -> tuple[list[float], list[float]]:
    """The rule mapped to [0, 200/sqrt(min(T, 1))] (ruling E-A25: short expiries need more)."""
    half = 100 / math.sqrt(min(t, 1.0))
    xs, ws = _unit_rule()
    return [half * (x + 1) for x in xs], [half * w for w in ws]


def _lewis(phi: Cf, spot: float, strikes: Floats, t: float, r: float, q: float,
           call: bool) -> list[float]:
    forward = spot * math.exp((r - q) * t)
    discount = math.exp(-r * t)
    us, ws = _nodes(t)
    shifted = [phi(complex(u, -0.5)) for u in us]
    prices = []
    for strike in strikes:
        k = math.log(forward / strike)
        integral = ordered_sum(w * (cmath.exp(1j * u * k) * p).real / (u * u + 0.25)
                               for u, w, p in zip(us, ws, shifted, strict=True))
        price = discount * (forward - math.sqrt(forward * strike) / math.pi * integral)
        prices.append(price if call else price - discount * (forward - strike))
    return prices


def heston_price(spot: float, strikes: Floats, t: float, r: float, q: float, h: Heston,
                 option_type: str) -> list[float]:
    _check_common(spot, strikes, t)
    check_heston(h)
    return _lewis(heston_phi(h, t), spot, strikes, t, r, q, option_type == "CALL")


def bates_price(spot: float, strikes: Floats, t: float, r: float, q: float, h: Heston,
                j: Jumps, option_type: str) -> list[float]:
    _check_common(spot, strikes, t)
    check_heston(h)
    _check_jumps(j)
    base, jump = heston_phi(h, t), _jump_phi(j, t)
    return _lewis(lambda u: base(u) * jump(u), spot, strikes, t, r, q, option_type == "CALL")


def _bs(phi: float, s: float, k: float, t: float, r: float, q: float, v: float) -> float:
    root = v * math.sqrt(t)
    forward = s * math.exp((r - q) * t)
    d1 = math.log(forward / k) / root + root / 2
    return math.exp(-r * t) * phi * (forward * big_n(phi * d1) - k * big_n(phi * (d1 - root)))


def merton_price(spot: float, strikes: Floats, t: float, r: float, q: float, vol: float,
                 j: Jumps, option_type: str) -> list[float]:
    _check_common(spot, strikes, t)
    if not vol > 0:
        raise _domain("vol must be above 0", "vol")
    _check_jumps(j)
    phi = 1.0 if option_type == "CALL" else -1.0
    kbar = j.kbar
    rate = j.intensity * (1 + kbar) * t
    terms = []  # (weight, r_n, v_n)
    weight, total = math.exp(-rate), 0.0
    for n in range(200):
        terms.append((weight, r - j.intensity * kbar + n * math.log1p(kbar) / t,
                      math.sqrt(vol * vol + n * j.log_jump_vol**2 / t)))
        total += weight
        if total >= 1 - 1e-16:
            break
        weight *= rate / (n + 1)
    return [ordered_sum(w * _bs(phi, spot, k, t, rn, q, vn) for w, rn, vn in terms)
            for k in strikes]


# --- SLV leverage ---

@dataclass(frozen=True)
class Grid:
    nx: int
    nv: int
    nt: int
    x_min: float
    x_max: float
    v_max: float


def _rows(mu: Floats, s: Floats, h: float, dt: float,
          no_flux: bool) -> tuple[list[float], list[float], list[float]]:
    """(lower, diag, upper) of I - dt A on one line, as the spec's operator rows."""
    n = len(mu)
    faces = [mu[0], *((mu[k - 1] + mu[k]) / 2 for k in range(1, n)), mu[-1]]
    if no_flux:
        faces[0] = faces[-1] = 0.0
    plus = [max(f, 0.0) for f in faces]
    minus = [min(f, 0.0) for f in faces]
    h2 = h * h
    lower, diag, upper = [0.0] * n, [0.0] * n, [0.0] * n
    for k in range(n):
        end = no_flux and (k == 0 or k == n - 1)
        diag[k] = 1 + dt * s[k] / (2 * h2 if end else h2) + dt * (plus[k + 1] - minus[k]) / h
        if k + 1 < n:
            upper[k] = -dt * s[k + 1] / (2 * h2) + dt * minus[k + 1] / h
        if k > 0:
            lower[k] = -dt * s[k - 1] / (2 * h2) - dt * plus[k] / h
    return lower, diag, upper


def slv_leverage(spot: float, t: float, r: float, q: float, h: Heston,
                 slices: Sequence[arb_surface.Slice], grid: Grid) -> dict[str, object]:
    # Ruling E-A37: every E_INPUT rule first, then E_DOMAIN, each in input order.
    arb_surface.check_slices_input(slices)
    if grid.nx < 5 or grid.nv < 5 or grid.nt < 2:
        raise _input("nx and nv must be at least 5 and nt at least 2", "grid")
    if spot > 0 and not grid.x_min < math.log(spot) < grid.x_max:  # ln needs spot > 0
        raise _input("ln(spot) must lie inside (x_min, x_max)", "grid")
    if not spot > 0:
        raise _domain("spot must be above 0", "spot")
    if not t > 0:
        raise _domain("expiry_years must be above 0", "expiry_years")
    check_heston(h)
    arb_surface.check_slices(slices)
    if not grid.v_max > 0:
        raise _domain("v_max must be above 0", "grid")
    nx, nv, nt = grid.nx, grid.nv, grid.nt
    dx = (grid.x_max - grid.x_min) / (nx - 1)
    dv = grid.v_max / (nv + 1)
    dt = t / nt
    xs = [grid.x_min + i * dx for i in range(nx)]
    vs = [(j + 1) * dv for j in range(nv)]
    log_spot = math.log(spot)

    def local_vol(time: float, x: float) -> float:
        k = x - (log_spot + (r - q) * time)
        return arb_surface.dupire(slices, [(time, k)])[2][0]

    def leverage(p: list[list[float]], time: float) -> list[float]:
        m = [ordered_sum(row) for row in p]
        e = [ordered_sum(v * x for v, x in zip(vs, row, strict=True)) for row in p]
        eps = 1e-10 * max(m)
        ebar = ordered_sum(e) / ordered_sum(m)
        return [math.sqrt(local_vol(time, x) ** 2 / ((ei + eps * ebar) / (mi + eps)))
                for x, mi, ei in zip(xs, m, e, strict=True)]

    # Start density at t_1 = dt.
    l0sq = local_vol(dt, log_spot + (r - q) * dt) ** 2 / h.v0
    mean_x = log_spot + (r - q - l0sq * h.v0 / 2) * dt
    mean_v = h.v0 + h.kappa * (h.theta - h.v0) * dt
    sx = max(math.sqrt(l0sq * h.v0 * dt), 2 * dx)
    sv = max(h.xi * math.sqrt(h.v0 * dt), 2 * dv)
    one = 1 - h.rho * h.rho
    norm = 1 / (2 * math.pi * sx * sv * math.sqrt(one))
    p = []
    for x in xs:
        zx = (x - mean_x) / sx
        p.append([norm * math.exp(-(zx * zx - 2 * h.rho * zx * ((v - mean_v) / sv)
                                    + ((v - mean_v) / sv) ** 2) / (2 * one)) for v in vs])
    scale = ordered_sum(ordered_sum(row) for row in p) * dx * dv
    p = [[x / scale for x in row] for row in p]

    v_mu = [h.kappa * (h.theta - v) for v in vs]
    v_s = [h.xi * h.xi * v for v in vs]
    v_rows = _rows(v_mu, v_s, dv, dt, True)
    for n in range(1, nt):
        lev = leverage(p, n * dt)
        # 1. mixed term, explicit, interior nodes
        f = [[h.rho * h.xi * lev[i] * vs[j] * p[i][j] for j in range(nv)] for i in range(nx)]
        star = [row[:] for row in p]
        for i in range(1, nx - 1):
            for j in range(1, nv - 1):
                star[i][j] = p[i][j] + dt * (f[i + 1][j + 1] - f[i + 1][j - 1] - f[i - 1][j + 1]
                                             + f[i - 1][j - 1]) / (4 * dx * dv)
        # 2. x, implicit for each j, Dirichlet ends
        lsq = [x * x for x in lev]
        for j in range(nv):
            mu = [r - q - ls * vs[j] / 2 for ls in lsq]
            s = [ls * vs[j] for ls in lsq]
            lower, diag, upper = _rows(mu, s, dx, dt, False)
            lower[0] = upper[0] = lower[-1] = upper[-1] = 0.0
            diag[0] = diag[-1] = 1.0
            rhs = [star[i][j] for i in range(nx)]
            rhs[0] = rhs[-1] = 0.0
            column = thomas(lower, diag, upper, rhs)
            for i in range(nx):
                star[i][j] = column[i]
        # 3. v, implicit for each i, no flux; 4. floor
        p = [[max(x, 0.0) for x in thomas(*v_rows, star[i])] for i in range(nx)]
    mass = ordered_sum(ordered_sum(row) for row in p) * dx * dv
    return {"x": xs, "leverage": leverage(p, t), "mass": mass}
