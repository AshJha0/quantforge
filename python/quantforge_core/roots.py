"""Root finders (specifications/01-core/root-finders.md)."""
import math
from collections.abc import Callable
from dataclasses import dataclass

from .errors import QfError

Fn = Callable[[float], float]
_EPS = 2.0**-52


@dataclass(frozen=True)
class RootResult:
    root: float
    iterations: int
    residual: float
    termination: str


def _finite(v: float) -> float:
    if not math.isfinite(v):
        raise QfError("E_NON_FINITE", "the function returned a non-finite value")
    return v


def _check_common(x_tol: float, f_tol: float, max_iter: int) -> None:
    if x_tol <= 0 or f_tol < 0 or max_iter < 1:
        raise QfError("E_INPUT", "need x_tol > 0, f_tol >= 0 and max_iter >= 1")


def _same_sign(u: float, v: float) -> bool:
    return (u > 0 and v > 0) or (u < 0 and v < 0)


def _no_convergence(max_iter: int) -> QfError:
    return QfError("E_NO_CONVERGENCE", f"no convergence in {max_iter} iterations", "max_iter")


def _bracket_start(f: Fn, a: float, b: float) -> tuple[float, float, RootResult | None]:
    if a >= b:
        raise QfError("E_INPUT", "need a < b")
    fa, fb = _finite(f(a)), _finite(f(b))
    if fa == 0:
        return fa, fb, RootResult(a, 0, 0.0, "EXACT")
    if fb == 0:
        return fa, fb, RootResult(b, 0, 0.0, "EXACT")
    if _same_sign(fa, fb):
        raise QfError("E_NOT_BRACKETED", "f(a) and f(b) have the same sign")
    return fa, fb, None


def bisection(
    f: Fn, a: float, b: float, x_tol: float = 1e-12, f_tol: float = 0.0, max_iter: int = 200
) -> RootResult:
    _check_common(x_tol, f_tol, max_iter)
    fa, _, done = _bracket_start(f, a, b)
    if done:
        return done
    for it in range(1, max_iter + 1):
        m = a + (b - a) / 2
        fm = _finite(f(m))
        if fm == 0:
            return RootResult(m, it, fm, "EXACT")
        if _same_sign(fa, fm):
            a, fa = m, fm
        else:
            b = m
        if (b - a) / 2 <= x_tol:
            return RootResult(m, it, fm, "X_TOL")
        if abs(fm) <= f_tol:
            return RootResult(m, it, fm, "F_TOL")
    raise _no_convergence(max_iter)


def brent(
    f: Fn, a: float, b: float, x_tol: float = 1e-12, f_tol: float = 0.0, max_iter: int = 200
) -> RootResult:
    _check_common(x_tol, f_tol, max_iter)
    fa, fb, done = _bracket_start(f, a, b)
    if done:
        return done
    c, fc = a, fa
    d = e = b - a
    for it in range(1, max_iter + 1):
        if _same_sign(fb, fc):
            c, fc = a, fa
            d = e = b - a
        if abs(fc) < abs(fb):
            a, fa = b, fb
            b, fb = c, fc
            c, fc = a, fa
        tol1 = 2 * _EPS * abs(b) + x_tol / 2
        xm = (c - b) / 2
        if abs(xm) <= tol1:
            return RootResult(b, it, fb, "X_TOL")
        if fb == 0:
            return RootResult(b, it, fb, "EXACT")
        if abs(fb) <= f_tol:
            return RootResult(b, it, fb, "F_TOL")
        if abs(e) >= tol1 and abs(fa) > abs(fb):
            s = fb / fa
            if a == c:
                p = 2 * xm * s
                q = 1 - s
            else:
                q = fa / fc
                r = fb / fc
                p = s * (2 * xm * q * (q - r) - (b - a) * (r - 1))
                q = (q - 1) * (r - 1) * (s - 1)
            if p > 0:
                q = -q
            p = abs(p)
            if 2 * p < min(3 * xm * q - abs(tol1 * q), abs(e * q)):
                e = d
                d = p / q
            else:
                d = e = xm
        else:
            d = e = xm
        a, fa = b, fb
        b += d if abs(d) > tol1 else math.copysign(tol1, xm)
        fb = _finite(f(b))
    raise _no_convergence(max_iter)


def newton(
    f: Fn,
    df: Fn,
    x0: float,
    a: float | None = None,
    b: float | None = None,
    x_tol: float = 1e-12,
    f_tol: float = 0.0,
    max_iter: int = 200,
) -> RootResult:
    if (a is None) != (b is None):
        raise QfError("E_SCHEMA", "a and b must both be given or both absent")
    _check_common(x_tol, f_tol, max_iter)
    bracketed = a is not None
    fa = 0.0
    fb = 0.0
    if bracketed:
        if a >= b:
            raise QfError("E_INPUT", "need a < b")
        fa, fb = _finite(f(a)), _finite(f(b))
        if _same_sign(fa, fb):
            raise QfError("E_NOT_BRACKETED", "f(a) and f(b) have the same sign")
        if not a <= x0 <= b:
            raise QfError("E_INPUT", "x0 is outside the bracket", "x0")
    x = x0
    fx = _finite(f(x))
    for it in range(1, max_iter + 1):
        if fx == 0:
            return RootResult(x, it - 1, fx, "EXACT")
        dfx = _finite(df(x))
        if dfx == 0:
            raise QfError("E_ZERO_DERIVATIVE", f"df({x}) is zero")
        if bracketed:
            # An end point with f exactly 0 stays: only the other end may move.
            if fa == 0:
                if _same_sign(fx, fb):
                    b, fb = x, fx
            elif fb == 0:
                if _same_sign(fx, fa):
                    a, fa = x, fx
            elif _same_sign(fx, fa):
                a, fa = x, fx
            else:
                b, fb = x, fx
        x_new = x - fx / dfx
        if bracketed and not a <= x_new <= b:
            x_new = a + (b - a) / 2
        f_new = _finite(f(x_new))
        if abs(x_new - x) <= x_tol * (1 + abs(x_new)):
            return RootResult(x_new, it, f_new, "X_TOL")
        if abs(f_new) <= f_tol:
            return RootResult(x_new, it, f_new, "EXACT" if f_new == 0 else "F_TOL")
        x, fx = x_new, f_new
    raise _no_convergence(max_iter)
