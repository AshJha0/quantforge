"""Value at risk, expected shortfall and backtests
(specifications/06-risk/var-es-and-backtests.md, rulings F-31 and F-32)."""
import itertools
import math
from collections.abc import Sequence

from . import rng
from .errors import QfError
from .finite import guard

LR_ZERO = 1e-12  # ruling F-32
_PLUS = {5: 0.40, 6: 0.50, 7: 0.65, 8: 0.75, 9: 0.85}


def _confidence(c: float) -> None:
    if not 0.5 <= c < 1:
        raise QfError("E_DOMAIN", "confidence must be in [0.5, 1)", "confidence")


def _tail(losses: Sequence[float], c: float) -> dict[str, object]:
    """Ruling F-31: k = ceil(n c), VaR the k-th smallest loss. Ruling R6-3.1: ES over a tail
    of weight w = n - n c, the m = floor(w) largest losses in full and L(m+1) with w - m."""
    ordered = sorted(losses)
    n = len(ordered)
    k = math.ceil(n * c)
    w = n - n * c
    down = ordered[::-1]
    if w <= 0:
        return {"var": ordered[k - 1], "es": down[0], "tail_count": 1}
    m = math.floor(w)
    parts = down[:m] + ([(w - m) * down[m]] if m < n and w > m else [])
    return {"var": ordered[k - 1], "es": math.fsum(parts) / w, "tail_count": math.ceil(w)}


def historical(pnl: Sequence[float], c: float) -> dict[str, object]:
    _confidence(c)
    if not pnl:
        raise QfError("E_INPUT", "no P&L", "pnl")
    return _tail([-v for v in pnl], c)


def filtered_historical(returns: Sequence[float], position: float, lam: float,
                        c: float) -> dict[str, object]:
    _confidence(c)
    if not returns:
        raise QfError("E_INPUT", "no returns", "returns")
    if not 0 < lam < 1:
        raise QfError("E_DOMAIN", "lambda must be in (0, 1)", "lambda")
    variances = [math.fsum(r * r for r in returns) / len(returns)]
    for r in returns:
        variances.append(lam * variances[-1] + (1 - lam) * r * r)
    if any(not v > 0 for v in variances[:-1]):
        raise QfError("E_DOMAIN", "a zero EWMA variance cannot rescale", "returns")
    last = math.sqrt(variances[-1])
    pnl = [position * r * last / math.sqrt(v) for r, v in zip(returns, variances, strict=False)]
    out = _tail([-v for v in pnl], c)
    out["sigma_next"] = last
    return out


def _phi(z: float) -> float:
    return math.exp(-z * z / 2) / math.sqrt(2 * math.pi)


def parametric(mean: float, std: float, c: float) -> dict[str, object]:
    _confidence(c)
    if not std > 0:
        raise QfError("E_DOMAIN", "std must be positive", "std")
    z = rng.ppnd16(c)
    return {"var": -mean + std * z, "es": -mean + std * _phi(z) / (1 - c)}


def monte_carlo(mean: Sequence[float], covariance: Sequence[Sequence[float]],
                weights: Sequence[float], paths: int, seed: int, c: float) -> dict[str, object]:
    _confidence(c)
    n = len(mean)
    if n == 0 or len(weights) != n or len(covariance) != n or any(len(r) != n for r in covariance):
        raise QfError("E_INPUT", "mean, covariance and weights must agree in size", "covariance")
    if paths < 1:
        raise QfError("E_DOMAIN", "paths must be at least 1", "paths")
    if any(covariance[i][j] != covariance[j][i] for i in range(n) for j in range(i)):
        raise QfError("E_DOMAIN", "covariance must be symmetric", "covariance")
    lower = [[0.0] * n for _ in range(n)]  # Cholesky-Banachiewicz
    for i in range(n):
        for j in range(i + 1):
            s = covariance[i][j] - sum(lower[i][k] * lower[j][k] for k in range(j))
            if i == j:
                if not s > 0:
                    raise QfError("E_NOT_POSITIVE_DEFINITE", "covariance is not positive definite",
                                  "covariance")
                lower[i][i] = math.sqrt(s)
            else:
                lower[i][j] = s / lower[j][j]
    z = rng.normals(seed, 0, paths * n)
    losses = []
    for p in range(paths):
        draw = z[p * n:(p + 1) * n]
        pnl = 0.0
        for i in range(n):
            r = mean[i] + sum(lower[i][k] * draw[k] for k in range(i + 1))
            pnl += weights[i] * r
        losses.append(-pnl)
    return _tail(losses, c)


def _xlogy(x: float, y: float) -> float:
    return 0.0 if x == 0 else x * math.log(y)


def _lr_uc(n: int, x: int, c: float) -> float:
    p, p_hat = 1 - c, x / n
    lr = (-2 * (_xlogy(n - x, 1 - p) + _xlogy(x, p))
          + 2 * (_xlogy(n - x, 1 - p_hat) + _xlogy(x, p_hat)))
    return 0.0 if lr < LR_ZERO else lr


def _chi2_sf(lr: float, df: int) -> float:
    if df == 1:
        return math.erfc(math.sqrt(lr / 2))
    return math.exp(-lr / 2)


def kupiec(n: int, x: int, c: float) -> dict[str, object]:
    _confidence(c)
    if n < 1:
        raise QfError("E_DOMAIN", "observations must be at least 1", "observations")
    if not 0 <= x <= n:
        raise QfError("E_DOMAIN", "exceptions must be in [0, observations]", "exceptions")
    lr = _lr_uc(n, x, c)
    return {"lr_uc": lr, "p_value": _chi2_sf(lr, 1)}


def christoffersen(exceptions: Sequence[bool], c: float) -> dict[str, object]:
    _confidence(c)
    n = len(exceptions)
    if n < 2:
        raise QfError("E_INPUT", "need at least 2 days", "exceptions")
    counts = {"n00": 0, "n01": 0, "n10": 0, "n11": 0}
    for a, b in itertools.pairwise(exceptions):
        counts[f"n{int(a)}{int(b)}"] += 1
    n00, n01, n10, n11 = counts["n00"], counts["n01"], counts["n10"], counts["n11"]
    lr_uc = _lr_uc(n, sum(1 for e in exceptions if e), c)
    pi01 = n01 / (n00 + n01) if n00 + n01 else 0.0
    pi11 = n11 / (n10 + n11) if n10 + n11 else 0.0
    pi = (n01 + n11) / (n - 1)
    lr_ind = -2 * (_xlogy(n00 + n10, 1 - pi) + _xlogy(n01 + n11, pi)
                   - _xlogy(n00, 1 - pi01) - _xlogy(n01, pi01)
                   - _xlogy(n10, 1 - pi11) - _xlogy(n11, pi11))
    if lr_ind < LR_ZERO:
        lr_ind = 0.0
    lr_cc = lr_uc + lr_ind
    return {"lr_uc": lr_uc, "lr_ind": lr_ind, "lr_cc": lr_cc,
            "p_uc": _chi2_sf(lr_uc, 1), "p_ind": _chi2_sf(lr_ind, 1), "p_cc": _chi2_sf(lr_cc, 2),
            "transitions": counts}


def traffic_light(n: int, x: int, c: float) -> dict[str, object]:
    _confidence(c)
    if n < 1:
        raise QfError("E_DOMAIN", "observations must be at least 1", "observations")
    if not 0 <= x <= n:
        raise QfError("E_DOMAIN", "exceptions must be in [0, observations]", "exceptions")
    p = 1 - c
    lp, lq = math.log(p), math.log1p(-p)
    terms = [math.exp(math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)
                      + k * lp + (n - k) * lq) for k in range(x + 1)]
    cumulative = min(math.fsum(terms), 1.0)
    zone = "GREEN" if cumulative < 0.95 else "YELLOW" if cumulative < 0.9999 else "RED"
    plus: float | None = None
    if n == 250 and c == 0.99:
        plus = 0.0 if x <= 4 else _PLUS.get(x, 1.0)
    return {"cumulative_probability": cumulative, "zone": zone, "plus_factor": plus}



TENORS = {"0.25Y": 0.25, "0.5Y": 0.5, "1Y": 1.0, "2Y": 2.0, "3Y": 3.0, "5Y": 5.0, "10Y": 10.0,
          "15Y": 15.0, "20Y": 20.0, "30Y": 30.0}
GIRR_FACTORS = (*TENORS, "INFLATION", "XCCY_BASIS")
_WEIGHT = {0.25: 0.017, 0.5: 0.017, 1.0: 0.016, 2.0: 0.013, 3.0: 0.012}
_REDUCED = ("EUR", "USD", "GBP", "AUD", "JPY", "SEK", "CAD")
_SCENARIOS = ("high", "medium", "low")


def _risk_weight(factor: str) -> float:
    if factor in ("INFLATION", "XCCY_BASIS"):
        return 0.016
    return _WEIGHT.get(TENORS[factor], 0.011)


def _rho(a: tuple[str, str], b: tuple[str, str]) -> float:
    """MAR21.45 to MAR21.49 for (curve, factor) pairs in one currency."""
    (ca, fa), (cb, fb) = a, b
    if fa == "XCCY_BASIS" or fb == "XCCY_BASIS":
        return 0.0
    if fa == "INFLATION" and fb == "INFLATION":
        return 0.999
    if fa == "INFLATION" or fb == "INFLATION":
        return 0.4
    ta, tb = TENORS[fa], TENORS[fb]
    rho = max(math.exp(-0.03 * abs(ta - tb) / min(ta, tb)), 0.4)
    return rho if ca == cb else rho * 0.999


def _scaled(x: float, scenario: str) -> float:
    if scenario == "high":
        return min(1.25 * x, 1.0)
    if scenario == "low":
        return max(2 * x - 1, 0.75 * x)
    return x


def girr_delta(sensitivities: Sequence[tuple[str, str, str, float]], reduction: bool,
               reporting: str | None) -> dict[str, object]:
    """sensitivities: (currency, curve, risk_factor, sensitivity)."""
    if not sensitivities:
        raise QfError("E_INPUT", "no sensitivities", "sensitivities")
    keys = [(c, k, f) for c, k, f, _ in sensitivities]
    if len(set(keys)) != len(keys):
        raise QfError("E_INPUT", "duplicate risk factor", "sensitivities")
    reduced = {*_REDUCED, *([reporting] if reporting else [])} if reduction else set()
    buckets: dict[str, list[tuple[tuple[str, str], float]]] = {}
    for ccy, curve, factor, s in sensitivities:
        rw = _risk_weight(factor)
        if ccy in reduced:
            rw /= math.sqrt(2)
        buckets.setdefault(ccy, []).append(((curve, factor), rw * s))
    order = sorted(buckets)
    scenarios: dict[str, object] = {}
    deltas: dict[str, float] = {}
    for sc in _SCENARIOS:
        ks, ss = [], []
        for ccy in order:
            items = buckets[ccy]
            total = sum(w * w for _, w in items)
            for i, (fi, wi) in enumerate(items):
                for j, (fj, wj) in enumerate(items):
                    if i != j:
                        total += _scaled(_rho(fi, fj), sc) * wi * wj
            ks.append(math.sqrt(max(0.0, total)))
            ss.append(sum(w for _, w in items))
        gamma = _scaled(0.5, sc)

        def under(s: Sequence[float], ks: Sequence[float] = ks, gamma: float = gamma) -> float:
            total = sum(k * k for k in ks)
            for b in range(len(s)):
                for c in range(len(s)):
                    if b != c:
                        total += gamma * s[b] * s[c]
            return total

        used = list(ss)
        value = under(ss)
        alternative = False
        if value < 0:
            alternative = True
            used = [max(min(s, k), -k) for s, k in zip(ss, ks, strict=True)]
            value = under(used)
        delta = math.sqrt(max(0.0, value))
        deltas[sc] = delta
        scenarios[sc] = {
            "buckets": [{"currency": c, "k": k, "s": s, "s_used": u}
                        for c, k, s, u in zip(order, ks, ss, used, strict=True)],
            "delta": delta, "alternative_used": alternative}
    binding = max(_SCENARIOS, key=lambda sc: (deltas[sc], -_SCENARIOS.index(sc)))
    return {"scenarios": scenarios, "capital": deltas[binding], "binding_scenario": binding}


guard(globals())
