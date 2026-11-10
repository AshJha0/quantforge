"""Book: trade and position lifecycle, end-of-day marks
(specifications/07-portfolio/book-lifecycle.md, ruling F-34)."""
import itertools
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from .errors import QfError
from .finite import guard

EVENT_TYPES = ("TRADE", "FIXING", "EXPIRY", "DEFAULT", "ROLL")


@dataclass(frozen=True)
class Event:
    """Keys a type does not use stay at their defaults."""

    date: date
    type: str
    instrument: str = ""
    quantity: float = 0.0
    price: float = 0.0
    index: str = ""
    value: float = 0.0
    to: str = ""
    to_price: float = 0.0


class _Book:
    def __init__(self, positions: Sequence[tuple[str, float, float]]):
        self.held: dict[str, tuple[float, float]] = {}
        for instrument, q, a in positions:
            if q != 0:
                self.held[instrument] = (q, a)
        self.realized: dict[str, float] = {}
        self.closed: set[str] = set()

    def trade(self, instrument: str, dq: float, p: float) -> None:
        q, a = self.held.get(instrument, (0.0, 0.0))
        if q == 0 or (q > 0) == (dq > 0):
            nq = q + dq
            self.held[instrument] = (nq, (q * a + dq * p) / nq)
            return
        c = min(abs(dq), abs(q))
        sign = 1.0 if q > 0 else -1.0
        self.realized[instrument] = self.realized.get(instrument, 0.0) + sign * c * (p - a)
        nq = q + dq
        if nq == 0:
            del self.held[instrument]
        elif (nq > 0) == (q > 0):
            self.held[instrument] = (nq, a)
        else:
            self.held[instrument] = (nq, p)

    def close(self, instrument: str, price: float) -> float:
        if instrument not in self.held:
            raise QfError("E_INPUT", f"{instrument} is not held", "events")
        q = self.held[instrument][0]
        self.trade(instrument, -q, price)
        self.closed.add(instrument)
        return q

    def open_check(self, instrument: str) -> None:
        if instrument in self.closed:
            raise QfError("E_INPUT", f"{instrument} is closed", "events")


def lifecycle_apply(positions: Sequence[tuple[str, float, float]],
                    events: Sequence[Event]) -> dict[str, object]:
    if any(b.date < a.date for a, b in itertools.pairwise(events)):
        raise QfError("E_INPUT", "events must be in date order", "events")
    book = _Book(positions)
    fixings: dict[tuple[str, date], float] = {}
    for e in events:
        if e.type == "TRADE":
            if e.quantity == 0:
                raise QfError("E_DOMAIN", "quantity must not be 0", "events")
            book.open_check(e.instrument)
            book.trade(e.instrument, e.quantity, e.price)
        elif e.type == "FIXING":
            if (e.index, e.date) in fixings:
                raise QfError("E_INPUT", "the same fixing twice", "events")
            fixings[(e.index, e.date)] = e.value
        elif e.type in ("EXPIRY", "DEFAULT"):
            book.close(e.instrument, e.price)
        else:  # ROLL
            book.open_check(e.to)
            q = book.close(e.instrument, e.price)
            book.trade(e.to, q, e.to_price)
    return {
        "positions": [{"instrument": k, "quantity": q, "average_cost": a}
                      for k, (q, a) in sorted(book.held.items())],
        "realized_pnl": [{"instrument": k, "pnl": v} for k, v in sorted(book.realized.items())],
        "total_realized": sum(v for _, v in sorted(book.realized.items())),
        "fixings": [{"index": i, "date": d.isoformat(), "value": v}
                    for (i, d), v in sorted(fixings.items())],
    }


@dataclass(frozen=True)
class Source:
    name: str
    quotes: tuple[tuple[str, date, float], ...]


def marks_resolve(as_of: date, instruments: Sequence[str], sources: Sequence[Source],
                  max_age_days: int, ipv: Sequence[tuple[str, float]],
                  ipv_threshold: float) -> dict[str, object]:
    if len({s.name for s in sources}) != len(sources):
        raise QfError("E_INPUT", "source names must be unique", "sources")
    if max_age_days < 0:
        raise QfError("E_DOMAIN", "max_age_days must not be negative", "max_age_days")
    if any(not p > 0 for _, p in ipv):
        raise QfError("E_DOMAIN", "IPV prices must be positive", "ipv")
    checks = dict(ipv)
    marks = []
    for inst in instruments:
        price: float | None = None
        source: str | None = None
        status, age = "MISSING", None
        for rank, s in enumerate(sources):
            today = [p for i, d, p in s.quotes if i == inst and d == as_of]
            if today:
                price, source, age = today[0], s.name, 0
                status = "PRIMARY" if rank == 0 else "FALLBACK"
                break
        if price is None:
            best: tuple[date, int, float, str] | None = None
            for rank, s in enumerate(sources):
                for i, d, p in s.quotes:
                    gap = (as_of - d).days
                    if i == inst and 0 < gap <= max_age_days and (
                            best is None or d > best[0] or (d == best[0] and rank < best[1])):
                        best = (d, rank, p, s.name)
            if best is not None:
                price, source, status, age = best[2], best[3], "STALE", (as_of - best[0]).days
        diff: float | None = None
        breach = False
        if price is not None and inst in checks:
            diff = (price - checks[inst]) / checks[inst]
            breach = abs(diff) > ipv_threshold
        marks.append({"instrument": inst, "price": price, "source": source, "status": status,
                      "age_days": age, "ipv_diff": diff, "ipv_breach": breach})
    return {"marks": marks}


def factor_attribution(portfolio: Sequence[float], factors: Sequence[Sequence[float]],
                       names: Sequence[str]) -> dict[str, object]:
    """Use case 4 (04-pricing/use-cases.md): OLS with an intercept."""
    t = len(portfolio)
    k = len(names)
    if len(factors) != t or any(len(r) != k for r in factors):
        raise QfError("E_INPUT", "factor_returns must be T x K with K names", "factor_returns")
    if t < k + 2:
        raise QfError("E_INPUT", "need T >= K + 2", "portfolio_returns")
    import numpy  # loaded only here, to keep CLI start-up short

    x = numpy.column_stack([numpy.ones(t), numpy.array(factors, dtype=float).reshape(t, k)])
    y = numpy.array(portfolio, dtype=float)
    sv = numpy.linalg.svd(x, compute_uv=False)
    if sv[-1] < 1e-12 * sv[0]:
        raise QfError("E_DOMAIN", "the factors are collinear", "factor_returns")
    coef, *_ = numpy.linalg.lstsq(x, y, rcond=None)
    resid = y - x @ coef
    ssr = float(resid @ resid)
    sst = float(((y - y.mean()) ** 2).sum())
    vol2 = ssr / (t - k - 1)
    inv = numpy.linalg.inv(x.T @ x)
    means = x[:, 1:].mean(axis=0)
    betas = [float(b) for b in coef[1:]]
    return {
        "alpha": float(coef[0]),
        "betas": betas,
        "contributions": [b * float(m) for b, m in zip(betas, means, strict=True)],
        "mean_return": float(y.mean()),
        "r_squared": 1 - ssr / sst,
        "residual_vol": vol2 ** 0.5,
        "beta_se": [float((vol2 * inv[i + 1, i + 1]) ** 0.5) for i in range(k)],
    }


guard(globals())
