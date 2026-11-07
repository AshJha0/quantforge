"""Levenberg-Marquardt on a residual function, for the stage C smile fits. Only the end result is
judged, so the path here is free. numpy only: scipy is a development dependency."""
from collections.abc import Callable, Iterable

import numpy as np

Residual = Callable[[np.ndarray], np.ndarray]


def _safe(residual: Residual, x: np.ndarray) -> np.ndarray | None:
    with np.errstate(all="ignore"):
        try:
            r = residual(x)
        except (ArithmeticError, ValueError):
            return None
    return r if np.all(np.isfinite(r)) else None


def _jacobian(residual: Residual, x: np.ndarray, r: np.ndarray) -> np.ndarray:
    jac = np.empty((r.size, x.size))
    for j in range(x.size):
        h = 1e-7 * (1.0 + abs(x[j]))
        up, down = x.copy(), x.copy()
        up[j] += h
        down[j] -= h
        r_up, r_down = _safe(residual, up), _safe(residual, down)
        if r_up is None or r_down is None:
            jac[:, j] = 0.0
        else:
            jac[:, j] = (r_up - r_down) / (2 * h)
    return jac


def levenberg_marquardt(
    residual: Residual, start: np.ndarray, max_iter: int = 300
) -> tuple[np.ndarray, float] | None:
    """Returns the end point and its sum of squares, or None if the start cannot be evaluated."""
    x = np.array(start, dtype=float)
    r = _safe(residual, x)
    if r is None:
        return None
    cost = float(r @ r)
    damping = 1e-3
    for _ in range(max_iter):
        if cost < 1e-30:
            break
        jac = _jacobian(residual, x, r)
        a, g = jac.T @ jac, jac.T @ r
        scale = np.maximum(np.diag(a), 1e-12)
        improved = False
        while damping < 1e12:
            try:
                step = np.linalg.solve(a + damping * np.diag(scale), -g)
            except np.linalg.LinAlgError:
                damping *= 10
                continue
            trial = x + step
            r_new = _safe(residual, trial)
            if r_new is not None and float(r_new @ r_new) < cost:
                improved = True
                break
            damping *= 4
        if not improved:
            break
        new_cost = float(r_new @ r_new)
        small = cost - new_cost <= 1e-15 * cost and float(np.abs(step).max()) < 1e-10
        x, r, cost = trial, r_new, new_cost
        damping = max(damping / 5, 1e-14)
        if small:
            break
    return x, cost


def best_of(residual: Residual, starts: Iterable[np.ndarray]) -> tuple[np.ndarray, float] | None:
    best: tuple[np.ndarray, float] | None = None
    for start in starts:
        result = levenberg_marquardt(residual, start)
        if result is not None and (best is None or result[1] < best[1]):
            best = result
    return best
