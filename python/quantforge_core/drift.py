"""Drift detectors (A3; rulings J-W3-10 to J-W3-13; 11-research/drift-detectors.md):
two-sided CUSUM, Page-Hinkley, the population stability index and the two-sample KS test."""
import math
from collections.abc import Sequence
from fractions import Fraction
from typing import Any

from .errors import QfError

PSI_FLOOR = 1e-4


def _nonempty(x: Sequence[float], field: str) -> None:
    if not x:
        raise QfError("E_INPUT", f"{field} must not be empty", field)


def cusum(x: Sequence[float], k: float, h: float, mu0: float = 0.0, sigma: float = 1.0,
          reset: bool = True) -> dict[str, Any]:
    """J-W3-10: tabular two-sided CUSUM on z = (x - mu0) / sigma; alarm when a sum exceeds h."""
    _nonempty(x, "x")
    if not k > 0 or not h > 0 or not sigma > 0:
        raise QfError("E_DOMAIN", "k, h and sigma must be positive", "k")
    sp = sm = 0.0
    alarms: list[int] = []
    directions: list[int] = []
    for t, v in enumerate(x):
        z = (v - mu0) / sigma
        sp = max(0.0, sp + z - k)
        sm = max(0.0, sm - z - k)
        if sp > h or sm > h:
            alarms.append(t)
            directions.append(1 if sp > h else -1)
            if not reset:
                break
            sp = sm = 0.0
    return {"alarms": alarms, "directions": directions, "s_plus": sp, "s_minus": sm}


def page_hinkley(x: Sequence[float], delta: float, lam: float, direction: str = "both",
                 reset: bool = True) -> dict[str, Any]:
    """J-W3-11: m_t = sum_{s<=t} (x_s - xbar_s - delta) from the last restart, xbar_s the running mean
    at step s; alarm when m_t - min m > lambda. The down-test is the same on -x."""
    _nonempty(x, "x")
    if not delta >= 0 or not lam > 0:
        raise QfError("E_DOMAIN", "delta must be >= 0 and lambda > 0", "delta")
    if direction not in ("up", "down", "both"):
        raise QfError("E_INPUT", "direction must be up, down or both", "direction")
    alarms: list[int] = []
    directions: list[int] = []
    n, total, up, up_min, dn, dn_min = 0, 0.0, 0.0, 0.0, 0.0, 0.0
    for t, v in enumerate(x):
        n += 1
        total += v
        mean = total / n
        up += v - mean - delta
        dn += mean - v - delta
        up_min = min(up_min, up)
        dn_min = min(dn_min, dn)
        hit_up = direction != "down" and up - up_min > lam
        hit_dn = direction != "up" and dn - dn_min > lam
        if hit_up or hit_dn:
            alarms.append(t)
            directions.append(1 if hit_up else -1)
            if not reset:
                break
            n, total, up, up_min, dn, dn_min = 0, 0.0, 0.0, 0.0, 0.0, 0.0
    return {"alarms": alarms, "directions": directions}


def psi(reference: Sequence[float], test: Sequence[float], bins: int = 10,
        threshold: float = 0.25) -> dict[str, Any]:
    """J-W3-12: bins at the reference's type-1 quantiles, shares floored at 1e-4."""
    if bins < 2:
        raise QfError("E_INPUT", "bins must be at least 2", "bins")
    if len(reference) < bins or len(test) < bins:
        raise QfError("E_INPUT", "reference and test need at least bins values each", "reference")
    if not threshold > 0:
        raise QfError("E_DOMAIN", "threshold must be positive", "threshold")
    r = sorted(reference)
    n = len(r)
    edges = [r[-(-j * n // bins) - 1] for j in range(1, bins)]

    def shares(sample: Sequence[float]) -> list[float]:
        counts = [0] * bins
        for v in sample:
            lo, hi = 0, bins - 1  # first bin whose upper edge is >= v
            while lo < hi:
                mid = (lo + hi) // 2
                if v <= edges[mid]:
                    hi = mid
                else:
                    lo = mid + 1
            counts[lo] += 1
        return [max(c / len(sample), PSI_FLOOR) for c in counts]

    rs, ts = shares(reference), shares(test)
    value = math.fsum((a - e) * math.log(a / e) for a, e in zip(ts, rs, strict=True))
    return {"psi": value, "reference_shares": rs, "test_shares": ts, "alarm": value > threshold}


def _ks_d_scaled(a: Sequence[float], b: Sequence[float]) -> int:
    """D n m as an integer: max |i m - j n| over the merged order, ties stepped together."""
    xa, xb = sorted(a), sorted(b)
    n, m = len(xa), len(xb)
    i = j = 0
    best = 0
    while i < n or j < m:
        v = min(xa[i] if i < n else math.inf, xb[j] if j < m else math.inf)
        while i < n and xa[i] == v:
            i += 1
        while j < m and xb[j] == v:
            j += 1
        best = max(best, abs(i * m - j * n))
    return best


def _ks_p(n: int, m: int, d: int) -> float:
    """P(D' n m >= d) under the continuous null, by counting lattice paths with |i m - j n| < d."""
    if d <= 0:
        return 1.0
    row = [1 if j * n < d else 0 for j in range(m + 1)]
    for j in range(1, m + 1):
        if row[j]:
            row[j] = row[j - 1]
    for i in range(1, n + 1):
        new = [0] * (m + 1)
        new[0] = row[0] if i * m < d else 0
        for j in range(1, m + 1):
            new[j] = (row[j] + new[j - 1]) if abs(i * m - j * n) < d else 0
        row = new
    total = math.comb(n + m, n)
    return float(Fraction(total - row[m], total))


def ks(a: Sequence[float], b: Sequence[float], level: float = 0.05) -> dict[str, Any]:
    """J-W3-13: two-sample Kolmogorov-Smirnov statistic and exact two-sided p-value."""
    _nonempty(a, "a")
    _nonempty(b, "b")
    if not 0 < level < 1:
        raise QfError("E_DOMAIN", "level must lie in (0, 1)", "level")
    n, m = len(a), len(b)
    d = _ks_d_scaled(a, b)
    p = _ks_p(n, m, d)
    return {"statistic": d / (n * m), "p_value": p, "reject": p <= level}
