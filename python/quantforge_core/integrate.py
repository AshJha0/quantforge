"""Numerical integration (specifications/01-core/integration.md)."""
import math
from collections.abc import Callable
from functools import lru_cache

from .errors import QfError
from .numeric import ordered_sum

Fn = Callable[[float], float]

_KX = (0.991455371120812639206854697526329, 0.949107912342758524526189684047851,
       0.864864423359769072789712788640926, 0.741531185599394439863864773280788,
       0.586087235467691130294144838258730, 0.405845151377397166906606412076961,
       0.207784955007898467600689403773244, 0.0)
_WK = (0.022935322010529224963732008058970, 0.063092092629978553290700663189204,
       0.104790010322250183839876322541518, 0.140653259715525918998541745705333,
       0.169004726639267902826583426140209, 0.190350578064785409913256402421014,
       0.204432940075298892414161999234649, 0.209482141084727828012999174351914)
_WG = (0.129484966168869693270611432679082, 0.279705391489276667901467771423780,
       0.381830050505118944950369775488975, 0.417959183673469387755102040816327)


def _check_range(a: float, b: float) -> None:
    if a >= b:
        raise QfError("E_INPUT", "need a < b")


def trapezoid(f: Fn, a: float, b: float, n: int) -> float:
    _check_range(a, b)
    if n < 1:
        raise QfError("E_INPUT", "need n >= 1", "n")
    h = (b - a) / n
    total = f(a) / 2
    for i in range(1, n):
        total += f(a + i * h)
    total += f(a + n * h) / 2
    return h * total


def simpson(f: Fn, a: float, b: float, n: int) -> float:
    _check_range(a, b)
    if n < 2 or n % 2:
        raise QfError("E_INPUT", "need an even n >= 2", "n")
    h = (b - a) / n
    total = f(a)
    for i in range(1, n):
        total += (4 if i % 2 else 2) * f(a + i * h)
    total += f(a + n * h)
    return h / 3 * total


@lru_cache(maxsize=64)
def legendre_rule(n: int) -> tuple[tuple[float, ...], tuple[float, ...]]:
    """Nodes, ascending, and weights."""
    nodes = [0.0] * n
    weights = [0.0] * n

    def evaluate(t: float) -> tuple[float, float]:
        previous, current = 1.0, t
        for k in range(2, n + 1):
            previous, current = current, ((2 * k - 1) * t * current - (k - 1) * previous) / k
        return current, n * (t * current - previous) / (t * t - 1)

    for i in range(1, (n + 1) // 2 + 1):
        if n % 2 and i == (n + 1) // 2:
            t = 0.0
        else:
            t = math.cos(math.pi * (i - 0.25) / (n + 0.5))
            for _ in range(100):
                p, dp = evaluate(t)
                step = p / dp
                t -= step
                if abs(step) < 1e-16:
                    break
        _, dp = evaluate(t)
        w = 2 / ((1 - t * t) * dp * dp)
        nodes[n - i], weights[n - i] = t, w
        nodes[i - 1], weights[i - 1] = -t, w
    return tuple(nodes), tuple(weights)


def gauss_legendre(f: Fn, a: float, b: float, n: int) -> float:
    _check_range(a, b)
    if not 1 <= n <= 64:
        raise QfError("E_INPUT", "n must be 1 to 64", "n")
    nodes, weights = legendre_rule(n)
    mid, half = (a + b) / 2, (b - a) / 2
    return half * ordered_sum(w * f(mid + half * t) for t, w in zip(nodes, weights))


def adaptive_simpson(
    f: Fn, a: float, b: float, tol: float = 1e-10, max_depth: int = 50
) -> float:
    _check_range(a, b)
    if tol <= 0:
        raise QfError("E_INPUT", "need tol > 0", "tol")
    if max_depth < 1:
        raise QfError("E_INPUT", "need max_depth >= 1", "max_depth")

    def rule(width: float, fl: float, fm: float, fr: float) -> float:
        return width / 6 * (fl + 4 * fm + fr)

    def refine(
        left: float, right: float, fl: float, fm: float, fr: float,
        whole: float, tol_here: float, depth: int,
    ) -> float:
        mid = left + (right - left) / 2
        flm, frm = f(left + (mid - left) / 2), f(mid + (right - mid) / 2)
        s1, s2 = rule(mid - left, fl, flm, fm), rule(right - mid, fm, frm, fr)
        delta = s1 + s2 - whole
        if abs(delta) <= 15 * tol_here:
            return s1 + s2 + delta / 15
        if depth >= max_depth:
            raise QfError("E_NO_CONVERGENCE", f"depth went beyond {max_depth}", "max_depth")
        return refine(left, mid, fl, flm, fm, s1, tol_here / 2, depth + 1) + refine(
            mid, right, fm, frm, fr, s2, tol_here / 2, depth + 1
        )

    fa, fm, fb = f(a), f(a + (b - a) / 2), f(b)
    return refine(a, b, fa, fm, fb, rule(b - a, fa, fm, fb), tol, 0)


def _kronrod(f: Fn, a: float, b: float) -> tuple[float, float]:
    mid, half = (a + b) / 2, (b - a) / 2
    k15 = 0.0
    g7 = 0.0
    for i, x in enumerate(_KX):
        v = f(mid) if x == 0 else f(mid - half * x) + f(mid + half * x)
        k15 += _WK[i] * v
        if i % 2:
            g7 += _WG[i // 2] * v
    return half * k15, abs(half * (k15 - g7))


def gauss_kronrod(
    f: Fn, a: float, b: float, tol: float = 1e-10, max_intervals: int = 500
) -> tuple[float, float]:
    """Returns (value, error_estimate)."""
    _check_range(a, b)
    if tol <= 0:
        raise QfError("E_INPUT", "need tol > 0", "tol")
    if max_intervals < 1:
        raise QfError("E_INPUT", "need max_intervals >= 1", "max_intervals")
    value, error = _kronrod(f, a, b)
    intervals = [(a, b, value, error)]
    while True:
        value = ordered_sum(iv[2] for iv in intervals)
        error = ordered_sum(iv[3] for iv in intervals)
        if error <= max(tol, 1e-14 * abs(value)):
            return value, error
        if len(intervals) + 1 > max_intervals:
            raise QfError("E_NO_CONVERGENCE", f"more than {max_intervals} intervals")
        worst = max(range(len(intervals)), key=lambda i: intervals[i][3])
        left, right, _, _ = intervals.pop(worst)
        mid = left + (right - left) / 2
        intervals.append((left, mid, *_kronrod(f, left, mid)))
        intervals.append((mid, right, *_kronrod(f, mid, right)))
