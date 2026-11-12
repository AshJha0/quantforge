"""Closed-form exotics and American options (CRR tree, BAW, a reference FD scheme).

Spec: specifications/04-pricing/exotics.md, rulings E-A19 to E-A23 in
specifications/stage-e-rulings.md. Prices are per unit of underlying; b = r - q is the carry.
"""
import itertools
import math
from collections.abc import Callable, Sequence

from . import roots
from .black import big_n
from .errors import QfError
from .finite import guard
from .numeric import ordered_sum, thomas

Floats = Sequence[float]


def _input(message: str, field: str | None = None) -> QfError:
    return QfError("E_INPUT", message, field)


def _domain(message: str, field: str | None = None) -> QfError:
    return QfError("E_DOMAIN", message, field)


def _positive(**values: float) -> None:
    for key, value in values.items():
        if not value > 0:
            raise _domain(f"{key} must be above 0", key)


def _phi(option_type: str) -> float:
    return 1.0 if option_type == "CALL" else -1.0


def gbs(phi: float, s: float, k: float, t: float, r: float, b: float, v: float) -> float:
    root = v * math.sqrt(t)
    d1 = (math.log(s / k) + (b + v * v / 2) * t) / root
    d2 = d1 - root
    return phi * (s * math.exp((b - r) * t) * big_n(phi * d1) - k * math.exp(-r * t)
                  * big_n(phi * d2))


def digital(s: float, k: float, t: float, r: float, q: float, v: float, option_type: str,
            payoff: str, cash: float) -> float:
    _positive(spot=s, strike=k, expiry_years=t, vol=v, cash=cash)
    phi, root = _phi(option_type), v * math.sqrt(t)
    d1 = (math.log(s / k) + (r - q + v * v / 2) * t) / root
    if payoff == "CASH_OR_NOTHING":
        return cash * math.exp(-r * t) * big_n(phi * (d1 - root))
    return s * math.exp(-q * t) * big_n(phi * d1)


BGK_BETA = 0.5826  # ruling G-7: pinned, not -zeta(1/2)/sqrt(2 pi)


def barrier(s: float, k: float, t: float, r: float, q: float, v: float, option_type: str,
            h: float, rebate: float, barrier_type: str, monitoring: str | None = None,
            monitoring_per_year: int | None = None) -> float:
    """Continuous-barrier closed form; with `DISCRETE` monitoring, the Broadie-Glasserman-Kou
    shift `H exp(+-beta v sqrt(1/m))` away from spot (stage G, R9). The domain rule uses the
    unshifted barrier (G-8)."""
    discrete = _monitoring(monitoring, monitoring_per_year)
    _positive(spot=s, strike=k, expiry_years=t, vol=v, barrier=h)
    if rebate < 0:
        raise _domain("rebate must not be negative", "rebate")
    down = barrier_type.startswith("DOWN")
    if (down and s <= h) or (not down and s >= h):
        raise _domain("spot is on or beyond the barrier", "barrier")
    if discrete:
        assert monitoring_per_year is not None
        n = math.floor(monitoring_per_year * t + 0.5)  # G-30: ties round up
        if n < 1:
            raise _domain("the barrier is never observed (n = 0)", "monitoring_per_year")
        # R6-2.1: BGK only for regular knock-outs away from the barrier, with no rebate.
        regular = ((barrier_type == "DOWN_OUT" and option_type == "CALL" and h <= k)
                   or (barrier_type == "UP_OUT" and option_type == "PUT" and h >= k))
        if (not regular or rebate != 0
                or abs(math.log(s / h)) < 1.25 * v * math.sqrt(t / n)):
            raise _domain("outside the discrete-monitoring (BGK) envelope", "monitoring")
        shift = math.exp(BGK_BETA * v * math.sqrt(t / n))
        h = h / shift if down else h * shift
    phi, eta = _phi(option_type), 1.0 if down else -1.0
    b, sd = r - q, v * math.sqrt(t)
    mu = (b - v * v / 2) / (v * v)
    lam = math.sqrt(mu * mu + 2 * r / (v * v))
    carry, disc, ratio = math.exp((b - r) * t), math.exp(-r * t), h / s
    x1 = math.log(s / k) / sd + (1 + mu) * sd
    x2 = math.log(s / h) / sd + (1 + mu) * sd
    y1 = math.log(h * h / (s * k)) / sd + (1 + mu) * sd
    y2 = math.log(h / s) / sd + (1 + mu) * sd
    z = math.log(h / s) / sd + lam * sd

    def ab(x: float) -> float:
        return phi * s * carry * big_n(phi * x) - phi * k * disc * big_n(phi * x - phi * sd)

    def cd(y: float) -> float:
        return (float(phi * s * carry * ratio ** (2 * (mu + 1)) * big_n(eta * y)
                - phi * k * disc * ratio ** (2 * mu) * big_n(eta * y - eta * sd)))

    a, bb, c, d = ab(x1), ab(x2), cd(y1), cd(y2)
    e = rebate * disc * (big_n(eta * x2 - eta * sd) - ratio ** (2 * mu) * big_n(eta * y2 - eta * sd))
    f = rebate * (ratio ** (mu + lam) * big_n(eta * z)
                  + ratio ** (mu - lam) * big_n(eta * z - 2 * eta * lam * sd))
    above = k > h
    table = {
        ("DOWN_IN", 1.0): (c + e, a - bb + d + e),
        ("UP_IN", 1.0): (a + e, bb - c + d + e),
        ("DOWN_IN", -1.0): (bb - c + d + e, a + e),
        ("UP_IN", -1.0): (a - bb + d + e, c + e),
        ("DOWN_OUT", 1.0): (a - c + f, bb - d + f),
        ("UP_OUT", 1.0): (f, a - bb + c - d + f),
        ("DOWN_OUT", -1.0): (a - bb + c - d + f, f),
        ("UP_OUT", -1.0): (bb - d + f, a - c + f),
    }
    high, low = table[(barrier_type, phi)]
    return float(high if above else low)


def _monitoring(monitoring: str | None, per_year: int | None) -> bool:
    """Checks `monitoring` and `monitoring_per_year`; True for discrete monitoring."""
    if monitoring not in (None, "CONTINUOUS", "DISCRETE"):
        raise _input(f"{monitoring} is not a monitoring", "monitoring")
    if monitoring == "DISCRETE":
        if per_year is None:
            raise _input("DISCRETE needs monitoring_per_year", "monitoring_per_year")
        if per_year < 1:
            raise _domain("monitoring_per_year must be at least 1", "monitoring_per_year")
        return True
    if per_year is not None:
        raise _input("monitoring_per_year needs DISCRETE monitoring", "monitoring_per_year")
    return False


def asian_geometric(s: float, k: float, t: float, r: float, q: float, v: float,
                    option_type: str, averaging: str, fixings: Floats) -> float:
    _positive(spot=s, strike=k, expiry_years=t, vol=v)
    phi, b = _phi(option_type), r - q
    if averaging == "CONTINUOUS":
        if fixings:
            raise _input("fixing_years must be empty for CONTINUOUS", "fixing_years")
        return gbs(phi, s, k, t, r, (b - v * v / 6) / 2, v / math.sqrt(3))
    if not fixings or any(a >= c for a, c in itertools.pairwise(fixings)):
        raise _input("fixing_years must be strictly increasing, at least 1", "fixing_years")
    if not 0 < fixings[0] or fixings[-1] > t:
        raise _input("each fixing must lie in (0, T]", "fixing_years")
    n = len(fixings)
    m = math.log(s) + (b - v * v / 2) * ordered_sum(fixings) / n
    big_v = v * v * ordered_sum(min(a, c) for a in fixings for c in fixings) / (n * n)
    d1 = (m - math.log(k) + big_v) / math.sqrt(big_v)
    d2 = d1 - math.sqrt(big_v)
    mean = math.exp(m + big_v / 2)
    return math.exp(-r * t) * phi * (mean * big_n(phi * d1) - k * big_n(phi * d2))


def lookback(s: float, t: float, r: float, q: float, v: float, option_type: str,
             extreme: float) -> float:
    _positive(spot=s, expiry_years=t, vol=v)
    call = option_type == "CALL"
    if (call and not 0 < extreme <= s) or (not call and extreme < s):
        raise _domain("running_extreme is on the wrong side of spot", "running_extreme")
    b = r - q
    if abs(b) <= 1e-8 * v * v:  # ruling E-A26: the closed form divides by b
        raise _domain("carry too close to zero: the closed form divides by b", "dividend_yield")
    root = v * math.sqrt(t)
    x1 = (math.log(s / extreme) + (b + v * v / 2) * t) / root
    x2 = x1 - root
    half = v * v / (2 * b)
    power = (s / extreme) ** (-2 * b / (v * v))
    shift = 2 * b * math.sqrt(t) / v
    carry, disc = math.exp((b - r) * t), math.exp(-r * t)
    if call:
        return (float(s * carry * big_n(x1) - extreme * disc * big_n(x2)
                + s * disc * half * (power * big_n(-x1 + shift) - math.exp(b * t) * big_n(-x1))))
    return (float(-s * carry * big_n(-x1) + extreme * disc * big_n(-x2)
            + s * disc * half * (-power * big_n(x1 - shift) + math.exp(b * t) * big_n(x1))))


def quanto(s: float, k: float, t: float, rd: float, rf: float, q: float, v: float,
           fx_vol: float, rho: float, option_type: str) -> float:
    _positive(spot=s, strike=k, expiry_years=t, vol=v, fx_vol=fx_vol)
    if not -1 <= rho <= 1:
        raise _domain("correlation must be in [-1, 1]", "correlation")
    return gbs(_phi(option_type), s, k, t, rd, rf - q - rho * v * fx_vol, v)


def chooser(s: float, k: float, t: float, r: float, q: float, v: float, choose: float) -> float:
    _positive(spot=s, strike=k, expiry_years=t, vol=v)
    if not 0 < choose <= t:
        raise _input("choose_years must lie in (0, T]", "choose_years")
    b = r - q
    d = (math.log(s / k) + (b + v * v / 2) * t) / (v * math.sqrt(t))
    y = (math.log(s / k) + b * t + v * v * choose / 2) / (v * math.sqrt(choose))
    carry, disc = s * math.exp((b - r) * t), k * math.exp(-r * t)
    return (carry * big_n(d) - disc * big_n(d - v * math.sqrt(t)) - carry * big_n(-y)
            + disc * big_n(-y + v * math.sqrt(choose)))


def kirk(f1: float, f2: float, k: float, t: float, r: float, v1: float, v2: float,
         rho: float) -> float:
    _positive(forward_1=f1, forward_2=f2)
    if not f2 + k > 0:
        raise _domain("forward_2 + strike must be above 0", "strike")
    _positive(expiry_years=t, vol_1=v1, vol_2=v2)
    if not -1 <= rho <= 1:
        raise _domain("correlation must be in [-1, 1]", "correlation")
    f = f2 / (f2 + k)
    sv = math.sqrt(v1 * v1 - 2 * rho * v1 * v2 * f + v2 * v2 * f * f)
    d1 = (math.log(f1 / (f2 + k)) + sv * sv * t / 2) / (sv * math.sqrt(t))
    return math.exp(-r * t) * (f1 * big_n(d1) - (f2 + k) * big_n(d1 - sv * math.sqrt(t)))


def basket(forwards: Floats, weights: Floats, vols: Floats, corr: Sequence[Floats], k: float,
           t: float, r: float, option_type: str) -> dict[str, float]:
    n = len(forwards)
    if n == 0 or len(weights) != n or len(vols) != n:
        raise _input("forwards, weights and vols must have one length", "weights")
    if len(corr) != n or any(len(row) != n for row in corr) or any(
            corr[i][j] != corr[j][i] or not -1 <= corr[i][j] <= 1
            for i in range(n) for j in range(n)) or any(corr[i][i] != 1 for i in range(n)):
        raise _input("correlation must be square, symmetric, unit diagonal, in [-1, 1]",
                     "correlation")
    if any(f <= 0 for f in forwards):
        raise _domain("a forward is not above 0", "forwards")
    if any(w < 0 for w in weights) or not any(w > 0 for w in weights):
        raise _domain("weights must be non-negative and not all 0", "weights")
    if any(v <= 0 for v in vols):
        raise _domain("a vol is not above 0", "vols")
    _positive(strike=k, expiry_years=t)
    m1 = ordered_sum(w * f for w, f in zip(weights, forwards, strict=True))
    m2 = ordered_sum(weights[i] * weights[j] * forwards[i] * forwards[j]
                     * math.exp(corr[i][j] * vols[i] * vols[j] * t)
                     for i in range(n) for j in range(n))
    vb = math.sqrt(math.log(m2 / (m1 * m1)) / t)
    price = gbs(_phi(option_type), m1, k, t, r, 0.0, vb)
    return {"price": price, "basket_forward": m1, "basket_vol": vb}


# --- American ---

def crr(s: float, k: float, t: float, r: float, q: float, v: float, option_type: str,
        steps: int) -> dict[str, float]:
    _positive(spot=s, strike=k, expiry_years=t, vol=v)
    if steps < 1:
        raise _input("steps must be at least 1", "steps")
    dt = t / steps
    u = math.exp(v * math.sqrt(dt))
    d = 1 / u
    p = (math.exp((r - q) * dt) - d) / (u - d)
    if not 0 < p < 1:
        raise _domain("the up-move probability is outside (0, 1)", "steps")
    phi, disc = _phi(option_type), math.exp(-r * dt)

    def payoff(i: int, j: int) -> float:
        return max(phi * (s * u ** (i - 2 * j) - k), 0.0)

    american = [payoff(steps, j) for j in range(steps + 1)]
    european = american[:]
    for i in range(steps - 1, -1, -1):
        european = [disc * (p * european[j] + (1 - p) * european[j + 1]) for j in range(i + 1)]
        american = [max(disc * (p * american[j] + (1 - p) * american[j + 1]), payoff(i, j))
                    for j in range(i + 1)]
    return {"american": american[0], "european": european[0],
            "early_exercise_premium": american[0] - european[0]}


def _solve(f: Callable[[float], float], low: float, high: float) -> float:
    return roots.brent(f, low, high, x_tol=1e-13, max_iter=500).root


def baw(s: float, k: float, t: float, r: float, q: float, v: float, option_type: str) -> float:
    _positive(spot=s, strike=k, expiry_years=t, vol=v)
    if r <= 0:  # rulings E-A22, E-A27
        raise _domain("BAW needs r above 0", "rate")
    b = r - q
    phi = _phi(option_type)
    if phi > 0 and b >= r:
        return gbs(1.0, s, k, t, r, b, v)
    big_m, big_n_ = 2 * r / (v * v), 2 * b / (v * v)
    kt = 1 - math.exp(-r * t)
    root = math.sqrt((big_n_ - 1) ** 2 + 4 * big_m / kt)
    carry = math.exp((b - r) * t)

    def d1(x: float) -> float:
        return (math.log(x / k) + (b + v * v / 2) * t) / (v * math.sqrt(t))

    if phi > 0:
        q2 = (-(big_n_ - 1) + root) / 2

        def f(x: float) -> float:
            return x - k - gbs(1.0, x, k, t, r, b, v) - (1 - carry * big_n(d1(x))) * x / q2

        high = 2 * k
        while f(high) < 0:
            high *= 2
        star = _solve(f, k, high)
        if s >= star:
            return s - k
        a2 = (star / q2) * (1 - carry * big_n(d1(star)))
        return float(gbs(1.0, s, k, t, r, b, v) + a2 * (s / star) ** q2)
    q1 = (-(big_n_ - 1) - root) / 2

    def g(x: float) -> float:
        return k - x - gbs(-1.0, x, k, t, r, b, v) + (1 - carry * big_n(-d1(x))) * x / q1

    low = k / 2
    while g(low) < 0:
        low /= 2
    star = _solve(g, low, k)
    if s <= star:
        return k - s
    a1 = -(star / q1) * (1 - carry * big_n(-d1(star)))
    return float(gbs(-1.0, s, k, t, r, b, v) + a1 * (s / star) ** q1)


def fd(s: float, k: float, t: float, r: float, q: float, v: float, option_type: str,
       exercise: str, nx: int, nt: int, width: float) -> dict[str, float]:
    _positive(spot=s, strike=k, expiry_years=t, vol=v)
    if nx < 5 or nx % 2 == 0:
        raise _input("nx must be odd and at least 5", "grid")
    if nt < 1:
        raise _input("nt must be at least 1", "grid")
    if not width > 0:
        raise _domain("width must be above 0", "grid")
    phi = _phi(option_type)
    h = width * v * math.sqrt(t)
    dx = 2 * h / (nx - 1)
    dt = t / nt
    xs = [math.log(s) - h + i * dx for i in range(nx)]
    spots = [math.exp(x) for x in xs]
    payoff = [max(phi * (x - k), 0.0) for x in spots]
    mu = r - q - v * v / 2
    a = dt * (v * v / (2 * dx * dx) - mu / (2 * dx))
    c = dt * (v * v / (2 * dx * dx) + mu / (2 * dx))
    lower = [0.0] + [-a] * (nx - 2) + [0.0]
    diag = [1.0] + [1 + dt * (v * v / (dx * dx) + r)] * (nx - 2) + [1.0]
    upper = [0.0] + [-c] * (nx - 2) + [0.0]
    american = exercise == "AMERICAN"
    values = payoff[:]
    for n in range(nt):
        rhs = values[:]
        if american:
            rhs[0], rhs[-1] = payoff[0], payoff[-1]
        else:
            tau = (n + 1) * dt
            rhs[0], rhs[-1] = (max(phi * (x * math.exp(-q * tau) - k * math.exp(-r * tau)), 0.0)
                               for x in (spots[0], spots[-1]))
        values = thomas(lower, diag, upper, rhs)
        if american:
            values = [max(x, p) for x, p in zip(values, payoff, strict=True)]
    i = (nx - 1) // 2
    left, mid, right = values[i - 1], values[i], values[i + 1]
    return {
        "price": mid,
        "delta": (right - left) / (2 * dx * s),
        "gamma": ((right - 2 * mid + left) / (dx * dx) - (right - left) / (2 * dx)) / (s * s),
    }


guard(globals())
