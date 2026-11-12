"""Cross-asset hedge, equity and rates (specifications/08-hedging/cross-asset-hedge.md, rulings
I-20 to I-23).

Each instrument's risk per unit is found by repricing: `EQ01` from spot times 1.01 and 0.99, and
`KR01_k` from pillar k's zero rate moved by +-1bp with the curve rebuilt (I-21). The hedge is then
the wave 1 weighted least-squares solve (`hedge_solvers`) on that risk matrix.
"""
import itertools
import math
from collections.abc import Mapping, Sequence
from typing import Any

from .errors import QfError
from .finite import guard
from .hedge_solvers import _qp_core

KEYS = {"CALL": {"strike", "expiry_years"}, "PUT": {"strike", "expiry_years"},
        "FORWARD": {"strike", "expiry_years"}, "ZCB": {"expiry_years", "notional"},
        "UNDERLYING": set()}
Position = tuple[str, Mapping[str, float]]  # (instrument, its numeric keys)
_BP = 1e-4


def _cdf(x: float) -> float:
    return 0.5 * math.erfc(-x / math.sqrt(2))


def _zero(times: Sequence[float], rates: Sequence[float], t: float) -> float:
    """z(t): flat before the first pillar, linear in time between pillars (I-20)."""
    if t <= times[0]:
        return rates[0]
    for k in range(1, len(times)):
        if t <= times[k]:
            u = (t - times[k - 1]) / (times[k] - times[k - 1])
            return rates[k - 1] + u * (rates[k] - rates[k - 1])
    raise QfError("E_INPUT", "a maturity is after the last curve pillar (ruling I-20)",
                  "expiry_years")


def _value(kind: str, keys: Mapping[str, float], spot: float, q: float, vol: float,
           times: Sequence[float], rates: Sequence[float]) -> float:
    if kind == "UNDERLYING":
        return spot
    t = keys["expiry_years"]
    df = math.exp(-_zero(times, rates, t) * t)
    if kind == "ZCB":
        return keys["notional"] * df
    forward_spot = spot * math.exp(-q * t)
    strike = keys["strike"]
    if kind == "FORWARD":
        return forward_spot - strike * df
    root_t = vol * math.sqrt(t)
    d1 = (math.log(forward_spot / (strike * df)) + root_t * root_t / 2) / root_t
    d2 = d1 - root_t
    if kind == "CALL":
        return forward_spot * _cdf(d1) - strike * df * _cdf(d2)
    return strike * df * _cdf(-d2) - forward_spot * _cdf(-d1)


def _risks(kind: str, keys: Mapping[str, float], spot: float, q: float, vol: float,
           times: Sequence[float], rates: Sequence[float]) -> list[float]:
    """[EQ01, KR01_1 .. KR01_P] per unit (I-21)."""
    def value(s: float, z: Sequence[float]) -> float:
        return _value(kind, keys, s, q, vol, times, z)

    out = [(value(1.01 * spot, rates) - value(0.99 * spot, rates)) / 2]
    for k in range(len(rates)):
        up, down = list(rates), list(rates)
        up[k] += _BP
        down[k] -= _BP
        out.append((value(spot, up) - value(spot, down)) / 2)
    return out


def crossasset_solve(spot: float, dividend_yield: float, volatility: float,
                     times: Sequence[float], zero_rates: Sequence[float],
                     book: Sequence[Position], hedges: Sequence[Position],
                     weights: Sequence[float], ridge: float = 0.0) -> dict[str, Any]:
    """`hedge.crossasset.solve`: positions in the hedges minimising the weighted residual of the
    equity and key-rate risks together. Book positions carry a `quantity` key.

    Returns {positions, book_risk, residual_risk, objective}."""
    if not times or len(zero_rates) != len(times):
        raise QfError("E_INPUT", "the curve needs pillars and one zero rate per time", "curve")
    if times[0] <= 0 or any(b <= a for a, b in itertools.pairwise(times)):
        raise QfError("E_INPUT", "curve times must be positive and increasing", "curve")
    for held, items in ((True, book), (False, hedges)):
        for kind, keys in items:
            expected = KEYS[kind] | ({"quantity"} if held else set())
            if set(keys) != expected:
                raise QfError("E_INPUT", f"{kind} takes exactly {sorted(expected)}",
                              "book" if held else "hedges")
    if not book:
        raise QfError("E_INPUT", "the book is empty", "book")
    if not hedges:
        raise QfError("E_INPUT", "no hedge instruments", "hedges")
    if len(weights) != 1 + len(times):
        raise QfError("E_INPUT", "one weight per risk factor (1 + pillars)", "weights")
    if any(k.get("expiry_years", 0.0) > times[-1] for _, k in (*book, *hedges)):
        raise QfError("E_INPUT", "a maturity is after the last curve pillar (ruling I-20)",
                      "expiry_years")
    if spot <= 0:
        raise QfError("E_DOMAIN", "spot must be positive", "spot")
    if volatility <= 0:
        raise QfError("E_DOMAIN", "volatility must be positive", "volatility")
    if any(w <= 0 for w in weights):
        raise QfError("E_DOMAIN", "weights must be positive", "weights")
    if ridge < 0:
        raise QfError("E_DOMAIN", "ridge must not be negative", "ridge")
    for _, keys in (*book, *hedges):
        for name in ("strike", "expiry_years", "notional"):
            if name in keys and keys[name] <= 0:
                raise QfError("E_DOMAIN", f"{name} must be positive", name)

    def risk(kind: str, keys: Mapping[str, float]) -> list[float]:
        return _risks(kind, keys, spot, dividend_yield, volatility, times, zero_rates)

    size = 1 + len(times)
    terms = [(keys["quantity"], risk(kind, keys)) for kind, keys in book]
    book_risk = [math.fsum(q * r[f] for q, r in terms) for f in range(size)]
    columns = [risk(kind, keys) for kind, keys in hedges]
    a = [[c[f] for c in columns] for f in range(size)]
    out = _qp_core(a, book_risk, weights, ridge, None, None, None, None, "ERROR")
    return {"positions": out["x"], "book_risk": [v + 0.0 for v in book_risk],
            "residual_risk": out["residual"], "objective": out["objective"]}


guard(globals())
