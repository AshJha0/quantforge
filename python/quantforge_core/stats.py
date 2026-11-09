"""Statistics and time series (specifications/01-core/statistics-and-time-series.md)."""
import itertools
import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from .errors import QfError
from .finite import guard
from .numeric import ordered_sum

Floats = Sequence[float]
_INV_SQRT_2PI = 1 / math.sqrt(2 * math.pi)


def _centre(x: Floats) -> tuple[float, list[float]]:
    """Returns (mean, deviations). Works on differences from x[0], which are exact for close
    values, so that rounding the mean to a double does not bias the central moments."""
    shift = x[0]
    d = [v - shift for v in x]
    offset = ordered_sum(d) / len(d)
    return shift + offset, [v - offset for v in d]


def _constant(x: Floats) -> bool:
    return min(x) == max(x)


def _dot(u: Floats, v: Floats) -> float:
    return ordered_sum(a * b for a, b in zip(u, v))


def normal(x: Floats) -> tuple[list[float], list[float]]:
    pdf = [math.exp(-v * v / 2) * _INV_SQRT_2PI for v in x]
    cdf = [math.erfc(-v / math.sqrt(2)) / 2 for v in x]
    return pdf, cdf


def summary(x: Floats) -> dict[str, float | int | None]:
    n = len(x)
    if n < 2:
        raise QfError("E_INPUT", "need at least 2 values", "x")
    m, dev = _centre(x)
    ss = _dot(dev, dev)
    variance = ss / (n - 1)
    skewness = kurtosis = None
    if min(x) != max(x):
        m2 = ss / n
        m3 = ordered_sum(v**3 for v in dev) / n
        m4 = ordered_sum(v**4 for v in dev) / n
        skewness = m3 / m2**1.5
        kurtosis = m4 / (m2 * m2) - 3
    return {
        "count": n, "mean": m, "variance": variance, "stdev": math.sqrt(variance),
        "skewness": skewness, "excess_kurtosis": kurtosis, "min": min(x), "max": max(x),
    }


def quantile(x: Floats, p: Floats) -> list[float]:
    if len(x) < 1:
        raise QfError("E_INPUT", "need at least 1 value", "x")
    if any(not 0 <= v <= 1 for v in p):
        raise QfError("E_DOMAIN", "p must lie in [0, 1]", "p")
    s = sorted(x)
    n = len(s)
    out = []
    for v in p:
        if v == 1:
            out.append(s[n - 1])
            continue
        h = (n - 1) * v
        k = math.floor(h)
        out.append(s[k] + (h - k) * (s[k + 1] - s[k]) if k + 1 < n else s[k])
    return out


def covariance(x: Floats, y: Floats) -> tuple[float, float | None]:
    if len(x) != len(y) or len(x) < 2:
        raise QfError("E_INPUT", "need equal lengths of at least 2")
    _, dx = _centre(x)
    _, dy = _centre(y)
    sxy, sxx, syy = _dot(dx, dy), _dot(dx, dx), _dot(dy, dy)
    correlation = None if _constant(x) or _constant(y) else sxy / math.sqrt(sxx * syy)
    return sxy / (len(x) - 1), correlation


@dataclass(frozen=True)
class Fit:
    alpha: float
    beta: float
    r_squared: float | None
    se_alpha: float
    se_beta: float


def _regress(x: Floats, y: Floats) -> tuple[float, float, float, float, float, float]:
    """Returns (alpha, beta, sse, syy, sxx, mean of x)."""
    mx, dx = _centre(x)
    my, dy = _centre(y)
    sxx = _dot(dx, dx)
    if _constant(x):
        raise QfError("E_SINGULAR", "zero variance in the regressor", "x")
    beta = _dot(dx, dy) / sxx
    sse = ordered_sum((b - beta * a) ** 2 for a, b in zip(dx, dy))
    return my - beta * mx, beta, sse, _dot(dy, dy), sxx, mx


def ols(x: Floats, y: Floats) -> Fit:
    if len(x) != len(y) or len(x) < 3:
        raise QfError("E_INPUT", "need equal lengths of at least 3")
    alpha, beta, sse, syy, sxx, mx = _regress(x, y)
    s2 = sse / (len(x) - 2)
    return Fit(
        alpha,
        beta,
        None if _constant(y) else 1 - sse / syy,
        math.sqrt(s2 * (1 / len(x) + mx * mx / sxx)),
        math.sqrt(s2 / sxx),
    )


def returns(prices: Floats, kind: str) -> list[float]:
    if len(prices) < 2:
        raise QfError("E_INPUT", "need at least 2 prices", "prices")
    if any(p <= 0 for p in prices):
        raise QfError("E_DOMAIN", "prices must be positive", "prices")
    pairs = itertools.pairwise(prices)
    if kind == "SIMPLE":
        return [b / a - 1 for a, b in pairs]
    return [math.log(b / a) for a, b in pairs]


def rolling(x: Floats, window: int, statistic: str) -> list[float | None]:
    n = len(x)
    if window < 2 or window > n:
        raise QfError("E_INPUT", "need 2 <= window <= n", "window")
    out: list[float | None] = [None] * (window - 1)
    for end in range(window, n + 1):
        part = x[end - window:end]
        if statistic == "MEAN":
            out.append(ordered_sum(part) / window)
        else:
            _, dev = _centre(part)
            out.append(math.sqrt(_dot(dev, dev) / (window - 1)))
    return out


def ewma_variance(r: Floats, lam: float) -> list[float]:
    if len(r) < 1:
        raise QfError("E_INPUT", "need at least 1 return", "returns")
    if not 0 < lam < 1:
        raise QfError("E_DOMAIN", "lambda must lie in (0, 1)", "lambda")
    v = [r[0] * r[0]]
    for value in r[1:]:
        v.append(lam * v[-1] + (1 - lam) * value * value)
    return v


def autocorrelation(x: Floats, max_lag: int) -> list[float]:
    n = len(x)
    if max_lag < 1 or max_lag >= n:
        raise QfError("E_INPUT", "need 1 <= max_lag < n", "max_lag")
    _, dev = _centre(x)
    den = _dot(dev, dev)
    if _constant(x):
        raise QfError("E_DOMAIN", "zero variance", "x")
    return [
        ordered_sum(dev[t] * dev[t - k] for t in range(k, n)) / den
        for k in range(1, max_lag + 1)
    ]


def ljung_box(x: Floats, max_lag: int) -> float:
    acf = autocorrelation(x, max_lag)
    n = len(x)
    return n * (n + 2) * ordered_sum(a * a / (n - k) for k, a in enumerate(acf, 1))


def ar1(x: Floats) -> tuple[float, float, float]:
    """Returns (constant, phi, sigma)."""
    n = len(x)
    if n < 4:
        raise QfError("E_INPUT", "need at least 4 values", "x")
    constant, phi, sse, _, _, _ = _regress(x[:-1], x[1:])
    return constant, phi, math.sqrt(sse / (n - 3))


def resample_last(
    dates: Sequence[date], values: Sequence[float | None], frequency: str
) -> tuple[list[date], list[float]]:
    if len(dates) != len(values):
        raise QfError("E_INPUT", "dates and values differ in length")
    if any(b <= a for a, b in itertools.pairwise(dates)):
        raise QfError("E_INPUT", "dates must be strictly increasing", "dates")
    last: dict[tuple[int, int], tuple[date, float]] = {}
    for d, v in zip(dates, values):
        if v is not None:
            key = d.isocalendar()[:2] if frequency == "WEEK" else (d.year, d.month)
            last[key] = (d, v)
    kept = list(last.values())
    return [d for d, _ in kept], [v for _, v in kept]


def forward_fill(values: Sequence[float | None], limit: int) -> list[float | None]:
    if limit < 1:
        raise QfError("E_INPUT", "need limit >= 1", "limit")
    out: list[float | None] = []
    last = None
    age = 0
    for v in values:
        if v is not None:
            last, age = v, 0
            out.append(v)
        else:
            age += 1
            out.append(last if last is not None and age <= limit else None)
    return out


guard(globals())
