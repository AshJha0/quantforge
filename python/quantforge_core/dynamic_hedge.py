"""Dynamic delta-hedge backtest and hedge effectiveness
(specifications/08-hedging/dynamic-hedge-and-effectiveness.md, rulings I-29 to I-32)."""
import itertools
import math
from collections.abc import Sequence
from typing import Any

from .errors import QfError
from .finite import guard

Floats = Sequence[float]


def _cdf(x: float) -> float:
    return 0.5 * math.erfc(-x / math.sqrt(2))


def _centred(v: Floats) -> list[float]:
    mean = math.fsum(v) / len(v)
    return [e - mean for e in v]


def effectiveness(item_changes: Floats, hedge_changes: Floats) -> dict[str, float]:
    """`hedge.effectiveness`: dollar offset (cumulative, I-30), regression slope and R^2 of the
    hedge on the item, and variance reduction, with sample (co)variances over n - 1 (I-31)."""
    x, y = list(item_changes), list(hedge_changes)
    if len(x) != len(y):
        raise QfError("E_INPUT", "the two series differ in length", "hedge_changes")
    if len(x) < 3:
        raise QfError("E_INPUT", "at least 3 changes are needed", "item_changes")
    total = math.fsum(x)
    if total == 0:
        raise QfError("E_DOMAIN", "the hedged item does not change in total", "item_changes")
    dx, dy = _centred(x), _centred(y)
    dsum = _centred([p + q for p, q in zip(x, y)])
    n1 = len(x) - 1
    var_x = math.fsum(v * v for v in dx) / n1
    var_y = math.fsum(v * v for v in dy) / n1
    if var_x == 0:
        raise QfError("E_DOMAIN", "the hedged item has no variance", "item_changes")
    if var_y == 0:
        raise QfError("E_DOMAIN", "the hedge has no variance", "hedge_changes")
    cov = math.fsum(p * q for p, q in zip(dx, dy)) / n1
    var_sum = math.fsum(v * v for v in dsum) / n1
    return {"dollar_offset": -math.fsum(y) / total + 0.0, "regression_slope": cov / var_x + 0.0,
            "regression_r2": cov * cov / (var_x * var_y), "variance_reduction":
            1 - var_sum / var_x + 0.0}


def _value_delta(kind: str, spot: float, strike: float, tau: float, rate: float, q: float,
                 vol: float) -> tuple[float, float]:
    """Black-Scholes-Merton (value, delta); at tau = 0 the payoff (delta unused)."""
    if tau <= 0:
        payoff = spot - strike if kind == "CALL" else strike - spot
        return max(payoff, 0.0), 0.0
    root = vol * math.sqrt(tau)
    d1 = (math.log(spot / strike) + (rate - q + vol * vol / 2) * tau) / root
    d2 = d1 - root
    carry, df = math.exp(-q * tau), math.exp(-rate * tau)
    if kind == "CALL":
        return spot * carry * _cdf(d1) - strike * df * _cdf(d2), carry * _cdf(d1)
    return strike * df * _cdf(-d2) - spot * carry * _cdf(-d1), -carry * _cdf(-d1)


def backtest_delta(option_type: str, strike: float, expiry_years: float, quantity: float,
                   rate: float, dividend_yield: float, hedge_volatility: float,
                   times: Floats, spots: Floats) -> dict[str, Any]:
    """`hedge.backtest.delta`: replays a self-financing delta hedge of `quantity` European
    options along a given path (I-29) and reports the effectiveness of the hedge leg.

    Returns {option_values, shares, portfolio_values, final_pnl} and the `hedge.effectiveness`
    outputs."""
    m = len(times)
    if len(spots) != m:
        raise QfError("E_INPUT", "times and spots differ in length", "spots")
    if m < 4:
        raise QfError("E_INPUT", "a path needs at least 4 dates", "times")
    if times[0] != 0:
        raise QfError("E_INPUT", "times must start at 0", "times")
    if any(b <= a for a, b in itertools.pairwise(times)):
        raise QfError("E_INPUT", "times must be strictly increasing", "times")
    if times[-1] > expiry_years:
        raise QfError("E_INPUT", "the path ends after expiry", "times")
    if any(s <= 0 for s in spots):
        raise QfError("E_DOMAIN", "spots must be positive", "spots")
    for name, v in (("strike", strike), ("expiry_years", expiry_years),
                    ("hedge_volatility", hedge_volatility)):
        if v <= 0:
            raise QfError("E_DOMAIN", f"{name} must be positive", name)

    marks = [_value_delta(option_type, s, strike, expiry_years - t, rate, dividend_yield,
                          hedge_volatility) for t, s in zip(times, spots)]
    values = [v for v, _ in marks]
    shares = [-quantity * marks[i][1] for i in range(m - 1)]
    cash = -quantity * values[0] - shares[0] * spots[0]
    portfolio = [0.0]
    for i in range(m - 1):
        dt = times[i + 1] - times[i]
        cash = cash * math.exp(rate * dt) + shares[i] * spots[i] * math.expm1(dividend_yield * dt)
        portfolio.append(quantity * values[i + 1] + shares[i] * spots[i + 1] + cash)
        if i + 1 < m - 1:
            cash -= (shares[i + 1] - shares[i]) * spots[i + 1]
    item = [quantity * (values[i + 1] - values[i]) for i in range(m - 1)]
    hedge = [(portfolio[i + 1] - portfolio[i]) - item[i] for i in range(m - 1)]
    stats = effectiveness(item, hedge)
    return {"option_values": values, "shares": [v + 0.0 for v in shares],
            "portfolio_values": [v + 0.0 for v in portfolio], "final_pnl": portfolio[-1] + 0.0,
            **stats}


guard(globals())
