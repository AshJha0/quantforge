"""Calibration core (specifications/03-calibration/least-squares.md).

All three methods work on one stacked residual vector, whose squares sum to the objective:
sqrt(w_i) (m_i - y_i), then sqrt(lambda) (p - prior).
"""
import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from . import linalg, ois
from .curves import CurveData
from .errors import QfError
from .finite import guard

Floats = Sequence[float]
PARAMETERS = {"LINEAR": 2, "EXPONENTIAL": 2, "NELSON_SIEGEL": 4, "ROSENBROCK": 2}
METHODS = ("GAUSS_NEWTON", "LEVENBERG_MARQUARDT", "BFGS")
_GRADIENT_TOL = 1e-8
_STEP_TOL = 1e-12
_SHORTEST_STEP = 2.0**-80


@dataclass(frozen=True)
class Fit:
    parameters: list[float]
    objective: float
    iterations: int
    status: str
    residuals: list[float]


def _model(name: str, x: float, p: Floats) -> float:
    if name == "LINEAR":
        return p[0] + p[1] * x
    if name == "EXPONENTIAL":
        return p[0] * math.exp(-p[1] * x)
    decay = math.exp(-x / p[3])
    e = (1 - decay) / (x / p[3])
    return p[0] + p[1] * e + p[2] * (e - decay)


class _Problem:
    def __init__(self, model: str, x: Floats, y: Floats, weights: Floats, lam: float,
                 prior: Floats) -> None:
        self.model, self.x, self.y = model, x, y
        self.root_w = [math.sqrt(w) for w in weights]
        self.root_lam = math.sqrt(lam)
        self.lam = lam
        self.prior = prior

    def raw(self, p: Floats) -> list[float]:
        if self.model == "ROSENBROCK":
            return [1 - p[0], 10 * (p[1] - p[0] * p[0])]
        return [_model(self.model, x, p) - y for x, y in zip(self.x, self.y, strict=True)]

    def residuals(self, p: Floats) -> list[float]:
        raw = self.raw(p)
        if self.model != "ROSENBROCK":
            raw = [w * r for w, r in zip(self.root_w, raw, strict=True)]
        if self.lam:
            raw += [self.root_lam * (a - b) for a, b in zip(p, self.prior, strict=True)]
        return raw

    def objective(self, p: Floats) -> float:
        """A point where the model cannot be evaluated counts as infinitely bad."""
        try:
            value = math.fsum(r * r for r in self.residuals(p))
        except (ArithmeticError, ValueError):
            return math.inf
        return value if math.isfinite(value) else math.inf

    def jacobian(self, p: Floats) -> list[list[float]]:
        if self.model == "ROSENBROCK":
            rows = [[-1.0, 0.0], [-20 * p[0], 10.0]]
        elif self.model == "LINEAR":
            rows = [[w, w * x] for w, x in zip(self.root_w, self.x, strict=True)]
        elif self.model == "EXPONENTIAL":
            rows = []
            for w, x in zip(self.root_w, self.x, strict=True):
                e = math.exp(-p[1] * x)
                rows.append([w * e, -w * p[0] * x * e])
        else:
            return self._bumped(p)
        if self.lam and self.model != "ROSENBROCK":
            n = len(p)
            rows += [[self.root_lam if i == j else 0.0 for j in range(n)] for i in range(n)]
        return rows

    def _bumped(self, p: Floats) -> list[list[float]]:
        columns = []
        for j, v in enumerate(p):
            h = 1e-6 * (1 + abs(v))
            up = self.residuals([*p[:j], v + h, *p[j + 1:]])
            down = self.residuals([*p[:j], v - h, *p[j + 1:]])
            columns.append([(a - b) / (2 * h) for a, b in zip(up, down, strict=True)])
        return [list(row) for row in zip(*columns, strict=True)]


def _normal(jac: list[list[float]], r: Floats) -> tuple[list[list[float]], list[float]]:
    """Returns (J^T J, J^T r)."""
    n = len(jac[0])
    jtj = [[math.fsum(row[i] * row[j] for row in jac) for j in range(n)] for i in range(n)]
    jtr = [math.fsum(row[i] * v for row, v in zip(jac, r, strict=True)) for i in range(n)]
    if not all(math.isfinite(v) for v in jtr):
        raise QfError("E_NON_FINITE", "the gradient is not finite")
    return jtj, jtr


def _norm(v: Floats) -> float:
    return math.sqrt(math.fsum(a * a for a in v))


def _small_step(step: Floats, p: Floats) -> bool:
    return _norm(step) <= _STEP_TOL * (1 + _norm(p))


def _no_step() -> QfError:
    return QfError("E_NO_CONVERGENCE", "no acceptable step could be found")


def _no_convergence(max_iter: int) -> QfError:
    return QfError("E_NO_CONVERGENCE", f"no convergence in {max_iter} iterations", "max_iter")


def _gauss_newton(problem: _Problem, start: Floats, max_iter: int) -> tuple[list[float], int, str]:
    p = list(start)
    value = problem.objective(p)
    for it in range(1, max_iter + 1):
        jtj, jtr = _normal(problem.jacobian(p), problem.residuals(p))
        if 2 * _norm(jtr) <= _GRADIENT_TOL:
            return p, it, "GRADIENT"
        step = linalg.solve(jtj, [-g for g in jtr])
        for _ in range(60):
            trial = [a + b for a, b in zip(p, step, strict=True)]
            trial_value = problem.objective(trial)
            if trial_value < value:
                break
            if _small_step(step, p):
                return p, it, "STEP"
            step = [s / 2 for s in step]
        else:
            raise _no_step()
        p, value = trial, trial_value
        if _small_step(step, p):
            return p, it, "STEP"
    raise _no_convergence(max_iter)


def _levenberg_marquardt(
    problem: _Problem, start: Floats, max_iter: int, lower: Floats, upper: Floats
) -> tuple[list[float], int, str]:
    n = len(start)
    p = [min(max(v, lo), hi) for v, lo, hi in zip(start, lower, upper, strict=True)]
    value = problem.objective(p)
    mu = 1e-3
    for it in range(1, max_iter + 1):
        jtj, jtr = _normal(problem.jacobian(p), problem.residuals(p))
        # A variable on a bound that the gradient pushes outwards takes no part in the step.
        free = [
            i for i in range(n)
            if not ((p[i] <= lower[i] and jtr[i] > 0) or (p[i] >= upper[i] and jtr[i] < 0))
        ]
        if 2 * _norm([jtr[i] for i in free]) <= _GRADIENT_TOL:
            return p, it, "GRADIENT"
        accepted = False
        while mu < 1e20:
            a = [[jtj[i][j] for j in free] for i in free]
            for k, i in enumerate(free):
                a[k][k] += mu * max(jtj[i][i], 1e-12)
            step = linalg.lu_solve(a, [-jtr[i] for i in free])
            trial = list(p)
            for k, i in enumerate(free):
                trial[i] = min(max(p[i] + step[k], lower[i]), upper[i])
            trial_value = problem.objective(trial)
            if trial_value < value:
                accepted = True
                break
            if _small_step([a - b for a, b in zip(trial, p, strict=True)], p):
                return p, it, "STEP"
            mu *= 4
        if not accepted:
            raise _no_step()
        moved = [a - b for a, b in zip(trial, p, strict=True)]
        p, value = trial, trial_value
        mu = max(mu * 0.3, 1e-15)
        if _small_step(moved, p):
            return p, it, "STEP"
    raise _no_convergence(max_iter)


def _gradient(problem: _Problem, p: Floats) -> list[float]:
    _, jtr = _normal(problem.jacobian(p), problem.residuals(p))
    return [2 * g for g in jtr]


def _line_search(
    problem: _Problem, p: Floats, value: float, g: Floats, d: Floats
) -> tuple[float, list[float], float, list[float]] | None:
    """Weak Wolfe conditions, by bisection."""
    slope = math.fsum(a * b for a, b in zip(g, d, strict=True))
    low, high, a = 0.0, math.inf, 1.0
    for _ in range(80):
        trial = [x + a * s for x, s in zip(p, d, strict=True)]
        trial_value = problem.objective(trial)
        if not trial_value <= value + 1e-4 * a * slope:
            high = a
        else:
            trial_g = _gradient(problem, trial)
            if math.fsum(x * y for x, y in zip(trial_g, d, strict=True)) >= 0.9 * slope:
                return a, trial, trial_value, trial_g
            low = a
        a = 2 * low if math.isinf(high) else (low + high) / 2
    if low > 0:
        trial = [x + low * s for x, s in zip(p, d, strict=True)]
        return low, trial, problem.objective(trial), _gradient(problem, trial)
    return None


def _bfgs(problem: _Problem, start: Floats, max_iter: int) -> tuple[list[float], int, str]:
    n = len(start)
    p = list(start)
    value = problem.objective(p)
    g = _gradient(problem, p)
    h = [[float(i == j) for j in range(n)] for i in range(n)]
    first = True
    for it in range(1, max_iter + 1):
        if _norm(g) <= _GRADIENT_TOL:
            return p, it, "GRADIENT"
        d = [-math.fsum(row[j] * g[j] for j in range(n)) for row in h]
        found = _line_search(problem, p, value, g, d)
        if found is None:
            if first:
                if _small_step([v * _SHORTEST_STEP for v in d], p):
                    return p, it, "STEP"
                raise _no_step()
            h = [[float(i == j) for j in range(n)] for i in range(n)]
            first = True
            continue
        a, trial, value, new_g = found
        s = [a * v for v in d]
        y = [u - v for u, v in zip(new_g, g, strict=True)]
        p, g = trial, new_g
        if _small_step(s, p):
            return p, it, "STEP"
        sy = math.fsum(u * v for u, v in zip(s, y, strict=True))
        if sy > 0:
            if first:
                scale = sy / math.fsum(v * v for v in y)
                h = [[scale * float(i == j) for j in range(n)] for i in range(n)]
                first = False
            hy = [math.fsum(row[j] * y[j] for j in range(n)) for row in h]
            yhy = math.fsum(u * v for u, v in zip(y, hy, strict=True))
            for i in range(n):
                for j in range(n):
                    h[i][j] += (
                        (1 + yhy / sy) * s[i] * s[j] / sy - (hy[i] * s[j] + s[i] * hy[j]) / sy
                    )
    raise _no_convergence(max_iter)


def fit(
    model: str, x: Floats, y: Floats, start: Floats, method: str,
    weights: Floats | None = None, regularisation: float = 0.0, prior: Floats | None = None,
    lower: Floats | None = None, upper: Floats | None = None, max_iter: int = 1000,
) -> Fit:
    n = PARAMETERS[model]
    if len(x) != len(y):
        raise QfError("E_INPUT", "x and y differ in length")
    if len(start) != n:
        raise QfError("E_INPUT", f"start needs {n} values", "start")
    if model == "ROSENBROCK":
        weights = None
    if weights is not None and len(weights) != len(x):
        raise QfError("E_INPUT", "weights have the wrong length", "weights")
    if prior is not None and len(prior) != n:
        raise QfError("E_INPUT", "prior has the wrong length", "prior")
    bounded = lower is not None or upper is not None
    if bounded and method != "LEVENBERG_MARQUARDT":
        raise QfError("E_INPUT", "bounds need LEVENBERG_MARQUARDT")
    if any(b is not None and len(b) != n for b in (lower, upper)):
        raise QfError("E_INPUT", "bounds have the wrong length")
    if max_iter < 1:
        raise QfError("E_INPUT", "need max_iter >= 1", "max_iter")
    if lower is not None and upper is not None and any(
        lo > hi for lo, hi in zip(lower, upper, strict=True)
    ):
        raise QfError("E_INPUT", "lower is above upper")
    if weights is not None and any(w < 0 for w in weights):
        raise QfError("E_DOMAIN", "weights must not be negative", "weights")
    if regularisation < 0:
        raise QfError("E_DOMAIN", "regularisation must not be negative", "regularisation")

    problem = _Problem(
        model, x, y, weights if weights is not None else [1.0] * len(x), regularisation,
        prior if prior is not None else [0.0] * n,
    )
    box_low = lower if lower is not None else [-math.inf] * n
    box_high = upper if upper is not None else [math.inf] * n
    start = [min(max(v, lo), hi) for v, lo, hi in zip(start, box_low, box_high, strict=True)]
    if not math.isfinite(problem.objective(start)):
        raise QfError("E_NON_FINITE", "the objective is not finite at start", "start")
    if method == "GAUSS_NEWTON":
        p, iterations, status = _gauss_newton(problem, start, max_iter)
    elif method == "BFGS":
        p, iterations, status = _bfgs(problem, start, max_iter)
    else:
        p, iterations, status = _levenberg_marquardt(
            problem, start, max_iter, box_low, box_high
        )
    return Fit(p, problem.objective(p), iterations, status, problem.raw(p))


def check_bid_ask(fitted: Floats, bid: Floats, ask: Floats) -> list[dict[str, object]]:
    if not len(fitted) == len(bid) == len(ask):
        raise QfError("E_INPUT", "fitted, bid and ask differ in length")
    if any(b > a for b, a in zip(bid, ask, strict=True)):
        raise QfError("E_INPUT", "bid is above ask")
    breaches: list[dict[str, object]] = []
    for i, (f, b, a) in enumerate(zip(fitted, bid, ask, strict=True)):
        if f < b:
            breaches.append({"index": i, "side": "BID", "distance": b - f})
        elif f > a:
            breaches.append({"index": i, "side": "ASK", "distance": f - a})
    return breaches


def _zero_rates(data: CurveData) -> list[float]:
    return [
        -math.log(v) / ((d - data.as_of).days / 365)
        for d, v in zip(data.dates, data.discount_factors, strict=True)
    ]


def curve_report(
    convention: str, as_of: date, quotes: Sequence[ois.Quote], interpolation: str
) -> tuple[list[list[float]], float, float]:
    """Returns (jacobian, condition number, max repricing error), by a central bump of 1e-5."""
    import numpy  # loaded only here, to keep CLI start-up short

    _, error = ois.bootstrap(convention, as_of, quotes, interpolation)
    h = 1e-5
    n = len(quotes)
    jacobian = [[0.0] * n for _ in range(n)]
    for j in range(n):
        sides = []
        for bump in (h, -h):
            moved = [
                ois.Quote(q.tenor, q.mid + bump) if k == j else ois.Quote(q.tenor, q.mid)
                for k, q in enumerate(quotes)
            ]
            sides.append(_zero_rates(ois.bootstrap(convention, as_of, moved, interpolation)[0]))
        for i in range(n):
            jacobian[i][j] = (sides[0][i] - sides[1][i]) / (2 * h)
    return jacobian, float(numpy.linalg.cond(numpy.array(jacobian), 2)), error


guard(globals())
