"""Stage J curves lane (rulings J-C-1 to J-C-9): the financing term structure over the funding
curve (02-curves/financing-term-structure.md) and the liquidity cost curve
(10-execution/liquidity-curve.md)."""
import itertools
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from .errors import QfError


def _increasing_positive(ts: Sequence[float]) -> bool:
    return all(t > 0 for t in ts) and all(b > a for a, b in itertools.pairwise(ts))


def _lin(ts: Sequence[float], ys: Sequence[float], t: float) -> float:
    """Linear in y on the knots (0, 0), (ts[k], ys[k]) for t in (0, ts[-1]] (J-C-3)."""
    x0, y0 = 0.0, 0.0
    for x1, y1 in zip(ts, ys, strict=True):
        if t <= x1:
            return y0 + (t - x0) / (x1 - x0) * (y1 - y0)
        x0, y0 = x1, y1
    raise AssertionError("outside coverage")


@dataclass(frozen=True)
class FinancingCurve:
    """Cumulative funding `Z(t) t`, financing spread `S(t)` and borrow fee `B(t)` knots."""

    funding_times: list[float]
    funding_cum: list[float]
    quote_times: list[float]
    spread_cum: list[float]
    borrow_times: list[float]
    borrow_cum: list[float]

    @property
    def cover(self) -> float:
        c = min(self.funding_times[-1], self.quote_times[-1])
        return min(c, self.borrow_times[-1]) if self.borrow_times else c

    def zt(self, t: float) -> float:
        return _lin(self.funding_times, self.funding_cum, t)

    def s(self, t: float) -> float:
        return _lin(self.quote_times, self.spread_cum, t)

    def b(self, t: float) -> float:
        return _lin(self.borrow_times, self.borrow_cum, t) if self.borrow_times else 0.0

    def financing_df(self, t: float) -> float:
        return math.exp(-self.zt(t) - self.s(t))


def build_financing_curve(funding_times: Sequence[float], funding_zero_rates: Sequence[float],
                          quote_times: Sequence[float], repo_rates: Sequence[float],
                          borrow_times: Sequence[float], borrow_fees: Sequence[float]) -> FinancingCurve:
    """Bootstraps `S(T_i) = ln(1 + R_i T_i) - Z(T_i) T_i` (J-C-2) and `B(T_i) = b_i T_i` (J-C-4)."""
    if (len(funding_times) != len(funding_zero_rates) or len(quote_times) != len(repo_rates)
            or len(borrow_times) != len(borrow_fees) or not funding_times or not quote_times):
        raise QfError("E_INPUT", "curve arrays must pair up; funding and quotes non-empty",
                      "quote_times")
    for key, ts in (("funding_times", funding_times), ("quote_times", quote_times),
                    ("borrow_times", borrow_times)):
        if not _increasing_positive(ts):
            raise QfError("E_INPUT", "times must be positive and strictly increasing", key)
    if any(1.0 + r * t <= 0 for r, t in zip(repo_rates, quote_times, strict=True)):
        raise QfError("E_DOMAIN", "1 + R T must be positive", "repo_rates")
    if any(b < 0 for b in borrow_fees):
        raise QfError("E_DOMAIN", "borrow fees must be non-negative", "borrow_fees")
    bcum = [b * t for b, t in zip(borrow_fees, borrow_times, strict=True)]
    if any(y < x for x, y in itertools.pairwise(bcum)):
        raise QfError("E_DOMAIN", "cumulative borrow fee must not fall", "borrow_fees")
    fcum = [z * t for z, t in zip(funding_zero_rates, funding_times, strict=True)]
    ft = list(funding_times)
    scum = [math.log1p(r * t) - _lin(ft, fcum, t)
            if t <= ft[-1] else math.nan for r, t in zip(repo_rates, quote_times, strict=True)]
    if any(math.isnan(x) for x in scum):
        raise QfError("E_DOMAIN", "a quote lies beyond the funding curve", "quote_times")
    return FinancingCurve(ft, fcum, list(quote_times), scum, list(borrow_times), bcum)


def term_curve(curve: FinancingCurve, query_times: Sequence[float]) -> dict[str, Any]:
    """`repo.term.curve` (J-C-2, J-C-3)."""
    if not query_times or not _increasing_positive(query_times):
        raise QfError("E_INPUT", "query_times must be non-empty, positive, increasing", "query_times")
    if query_times[-1] > curve.cover:
        raise QfError("E_DOMAIN", "query beyond the curve's coverage", "query_times")
    pf = [curve.financing_df(t) for t in query_times]
    fwd: list[float] = []
    prev_t, prev_p = 0.0, 1.0
    for t, p in zip(query_times, pf, strict=True):
        fwd.append((prev_p / p - 1.0) / (t - prev_t))
        prev_t, prev_p = t, p
    return {
        "pillar_spreads": [s / t for s, t in zip(curve.spread_cum, curve.quote_times, strict=True)],
        "spread": [curve.s(t) / t for t in query_times],
        "financing_df": pf,
        "financing_rate": [(1.0 / p - 1.0) / t for p, t in zip(pf, query_times, strict=True)],
        "forward_financing": fwd,
        "borrow_fee": [curve.b(t) / t for t in query_times] if curve.borrow_times else None,
    }


def forward_term_financed(curve: FinancingCurve, spot: float, maturity: float,
                          dividend_times: Sequence[float],
                          dividend_amounts: Sequence[float]) -> dict[str, Any]:
    """`eq.forward.term_financed`: `F = (S - sum A_i C(t_i)) / C(T)`,
    `C(t) = exp(-Z(t) t - S(t) + B(t))` (J-C-5)."""
    if len(dividend_times) != len(dividend_amounts):
        raise QfError("E_INPUT", "dividend arrays must pair up", "dividend_amounts")
    if any(b <= a for a, b in itertools.pairwise(dividend_times)):
        raise QfError("E_INPUT", "dividend_times must be strictly increasing", "dividend_times")
    if spot <= 0:
        raise QfError("E_DOMAIN", "spot must be positive", "spot")
    if not 0 < maturity <= curve.cover:
        raise QfError("E_DOMAIN", "maturity must lie in (0, coverage]", "maturity_years")
    if any(a < 0 for a in dividend_amounts):
        raise QfError("E_DOMAIN", "dividends must be non-negative", "dividend_amounts")

    def carry(t: float) -> float:
        return math.exp(-curve.zt(t) - curve.s(t) + curve.b(t))

    pv = 0.0
    for t, a in zip(dividend_times, dividend_amounts, strict=True):
        if 0 < t <= maturity:
            pv += a * carry(t)
    c = carry(maturity)
    fwd = (spot - pv) / c
    if fwd <= 0:
        raise QfError("E_DOMAIN", "forward is not positive", "dividend_amounts")
    return {"forward": fwd, "carry": fwd - spot, "carry_factor": c,
            "financing_df": curve.financing_df(maturity), "pv_dividends": pv}


def liquidity_cost(half_spread_bps: float, daily_volume: float, daily_vol: float,
                   coefficient: float, exponent: float, risk_multiplier: float,
                   sizes: Sequence[float], horizons: Sequence[float]) -> dict[str, Any]:
    """`liq.curve.cost` (J-C-6 to J-C-8): `c(Q, h) = s + Y sigma (Q / (V h))^delta
    + z sigma sqrt(h / 3)`, with the closed-form optimal horizon."""
    if not sizes or not horizons:
        raise QfError("E_INPUT", "sizes and horizons_days must be non-empty", "sizes")
    checks: list[tuple[bool, str]] = [
        (half_spread_bps < 0, "half_spread_bps"), (daily_volume <= 0, "daily_volume"),
        (daily_vol < 0, "daily_vol"), (coefficient < 0, "coefficient"),
        (risk_multiplier < 0, "risk_multiplier"), (not 0 < exponent <= 1, "exponent"),
        (any(q < 0 for q in sizes), "sizes"), (any(h <= 0 for h in horizons), "horizons_days")]
    for bad, key in checks:
        if bad:
            raise QfError("E_DOMAIN", f"{key} out of domain", key)
    sp = half_spread_bps / 10000.0
    imp: Callable[[float, float], float] = (
        lambda q, h: coefficient * daily_vol * (q / (daily_volume * h)) ** exponent)
    risk = [risk_multiplier * daily_vol * math.sqrt(h / 3.0) for h in horizons]
    impact = [[imp(q, h) for h in horizons] for q in sizes]
    out: dict[str, Any] = {
        "spread_cost": sp, "impact": impact, "timing_risk": risk,
        "total_cost": [[sp + row[j] + risk[j] for j in range(len(horizons))] for row in impact],
        "optimal_horizon": None, "min_cost": None}
    b = risk_multiplier * daily_vol / math.sqrt(3.0)
    if b > 0 and coefficient > 0:
        hs, cs = [], []
        for q in sizes:
            a = coefficient * daily_vol * (q / daily_volume) ** exponent
            if a == 0:
                hs.append(0.0)
                cs.append(sp)
                continue
            h = (2.0 * exponent * a / b) ** (1.0 / (exponent + 0.5))
            hs.append(h)
            cs.append(sp + a * h ** (-exponent) + b * math.sqrt(h))
        out["optimal_horizon"], out["min_cost"] = hs, cs
    return out
