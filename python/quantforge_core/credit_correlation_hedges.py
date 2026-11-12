"""Credit and correlation hedges (specifications/08-hedging/credit-and-correlation-hedges.md,
rulings I-15 to I-19).

Both hedges stack per-unit risks of the hedge instruments into a square matrix (row per target,
column per instrument) and solve for the quantities that cancel the book's risk, as
`hedge_solvers.greeks_neutralise` does. The credit risks come from the stage D ISDA legs in
`credit` on hazard curves bumped section by section; the correlation risks are closed-form
Margrabe and Black-Scholes-Merton Greeks.
"""
import math
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any

import numpy as np

from . import credit, curves
from .curves import CurveData
from .errors import QfError
from .finite import guard

THRESHOLD = 1e-12  # ruling I-3


def _z(v: float) -> float:
    return float(v) + 0.0


def _solve_square(g: list[list[float]], rhs: list[float], field: str) -> list[float]:
    """Solves g q = rhs after the I-3 singularity check on g."""
    m = np.asarray(g, dtype=float)
    s = np.linalg.svd(m, compute_uv=False)
    if s[-1] <= THRESHOLD * s[0]:
        raise QfError("E_SINGULAR", "the hedges cannot set the targets independently", field)
    return [float(v) for v in np.linalg.solve(m, np.asarray(rhs, dtype=float))]


# ----- hedge.credit.cds -----

Trade = tuple[date, float, float, str]  # (maturity, coupon, notional, side)
Contract = tuple[date, float]  # (maturity, coupon)


def _bucket_targets(targets: Sequence[str], pillars: int) -> list[int]:
    """Row index of each target in the risk vector [cs01, jtd, bucket_1 .. bucket_P]."""
    rows = []
    for t in targets:
        if t == "CS01":
            rows.append(0)
        elif t == "JTD":
            rows.append(1)
        elif t.startswith("BUCKET_") and t[7:].isdigit() and 1 <= int(t[7:]) <= pillars:
            rows.append(1 + int(t[7:]))
        else:
            raise QfError("E_INPUT", f"unknown target {t}", "targets")
    return rows


class _Risks:
    """Per-unit risks of bought protection (ruling I-15, I-16) on one market."""

    def __init__(self, trade_date: date, discount: CurveData, hazard: credit.Hazard,
                 recovery: float):
        self.trade_date, self.recovery = trade_date, recovery
        self.curve = curves.build(discount)
        self.hazard = hazard
        self.eps = 1e-4 / (1 - recovery)
        self.survival = [math.exp(v) for v in hazard.logs[1:]]
        self.spans = [b - a for a, b in zip(hazard.times, hazard.times[1:])]
        p = len(self.spans)
        bumps = [(-1, sign) for sign in (1.0, -1.0)] + [
            (k, sign) for k in range(p) for sign in (1.0, -1.0)]
        self.models = {(k, sign): credit.Model(trade_date, self.curve, self._bumped(k, sign))
                       for k, sign in bumps}
        self.base = credit.Model(trade_date, self.curve, hazard)
        self._cache: dict[Contract, tuple[float, float, list[float]]] = {}

    def _bumped(self, section: int, sign: float) -> credit.Hazard:
        """The hazard curve with section `section` (or every section, -1) shifted by sign eps.
        Pillars before the first shifted section keep their survival bit for bit."""
        out, shift = [], 0.0
        for j, q in enumerate(self.survival):
            if section in (-1, j):
                shift += sign * self.eps * self.spans[j]
            out.append(q if shift == 0.0 else math.exp(self.hazard.logs[j + 1] - shift))
        bumped = credit.Hazard(self.hazard.as_of, self.hazard.dates, out)
        for j, q in enumerate(self.survival):  # keep the exact logs where nothing moved
            if out[j] is q:
                bumped.logs[j + 1] = self.hazard.logs[j + 1]
        return bumped

    def _pv(self, model: credit.Model, mat: date, coupon: float) -> float:
        r = credit._price(model, mat, coupon, 1 - self.recovery)
        return r.protection_leg - coupon * r.rpv01 + r.accrued * r.pcs

    def unit(self, mat: date, coupon: float) -> tuple[float, float, list[float]]:
        """(pv, upfront, [cs01, jtd, bucket_1 .. bucket_P]) per unit of bought protection."""
        key = (mat, coupon)
        if key not in self._cache:
            base = credit._price(self.base, mat, coupon, 1 - self.recovery)
            pv = base.protection_leg - coupon * base.rpv01 + base.accrued * base.pcs

            def cs01(section: int) -> float:
                up = self._pv(self.models[(section, 1.0)], mat, coupon)
                down = self._pv(self.models[(section, -1.0)], mat, coupon)
                return (up - down) / 2

            risks = [cs01(-1), (1 - self.recovery) - pv,
                     *(cs01(k) for k in range(len(self.spans)))]
            self._cache[key] = (pv, base.upfront, risks)
        return self._cache[key]


def credit_cds(trade_date: date, discount: CurveData, hazard_as_of: date,
               hazard_dates: Sequence[date], survival: Sequence[float], recovery: float,
               book: Sequence[Trade], hedges: Sequence[Contract],
               targets: Sequence[str]) -> dict[str, Any]:
    """`hedge.credit.cds`: notionals of CDS contracts (positive buys protection) that cancel the
    book's targeted CS01, JTD and bucket CS01s (rulings I-15, I-16).

    Returns {notionals, book: {pv, cs01, jtd, buckets}, after: {cs01, jtd, buckets},
    hedge_upfront}."""
    if discount.interpolation != "LOG_LINEAR_DF":  # ruling R1-4, the first rule check
        raise QfError("E_INPUT", "credit needs LOG_LINEAR_DF discounting",
                      "discount.interpolation")
    if not book:
        raise QfError("E_INPUT", "the book is empty", "book")
    if not hedges:
        raise QfError("E_INPUT", "no hedge contracts", "hedges")
    if len(targets) != len(hedges):
        raise QfError("E_INPUT", "one target per hedge contract", "targets")
    if len(set(targets)) != len(targets):
        raise QfError("E_INPUT", "a target is repeated", "targets")
    rows = _bucket_targets(targets, len(hazard_dates))
    contracts: list[Contract] = [(t[0], t[1]) for t in book] + list(hedges)
    if any(mat <= trade_date for mat, _ in contracts):
        raise QfError("E_INPUT", "a maturity is not after trade_date", "maturity")
    credit._check_as_of(trade_date, discount.as_of, hazard_as_of)
    hazard = credit.check_hazard(hazard_as_of, hazard_dates, survival)
    credit._check_recovery(recovery)
    if any(t[2] < 0 for t in book):
        raise QfError("E_DOMAIN", "a book notional is negative", "notional")
    if any(coupon < 0 for _, coupon in contracts):
        raise QfError("E_DOMAIN", "a coupon is negative", "coupon")

    risks = _Risks(trade_date, discount, hazard, recovery)
    size = 2 + len(hazard_dates)
    book_pv: list[float] = []
    book_risk: list[list[float]] = [[] for _ in range(size)]
    for mat, coupon, notional, side in book:
        scale = notional if side == "BUY_PROTECTION" else -notional
        pv, _, unit = risks.unit(mat, coupon)
        book_pv.append(scale * pv)
        for c in range(size):
            book_risk[c].append(scale * unit[c])
    totals = [math.fsum(v) for v in book_risk]
    per_hedge = [risks.unit(mat, coupon) for mat, coupon in hedges]
    g = [[h[2][r] for h in per_hedge] for r in rows]
    notionals = _solve_square(g, [-totals[r] for r in rows], "hedges")
    after = [math.fsum([totals[c], *(n * h[2][c] for n, h in zip(notionals, per_hedge))])
             for c in range(size)]
    upfront = math.fsum(n * h[1] for n, h in zip(notionals, per_hedge))
    return {
        "notionals": [_z(v) for v in notionals],
        "book": {"pv": _z(math.fsum(book_pv)), "cs01": _z(totals[0]), "jtd": _z(totals[1]),
                 "buckets": [_z(v) for v in totals[2:]]},
        "after": {"cs01": _z(after[0]), "jtd": _z(after[1]),
                  "buckets": [_z(v) for v in after[2:]]},
        "hedge_upfront": _z(upfront),
    }


# ----- hedge.correlation.neutralise -----

KEYS = {
    "EXCHANGE": {"quantity1", "quantity2", "expiry_years"},
    "CALL_1": {"strike", "expiry_years"}, "PUT_1": {"strike", "expiry_years"},
    "CALL_2": {"strike", "expiry_years"}, "PUT_2": {"strike", "expiry_years"},
    "UNDERLYING_1": set(), "UNDERLYING_2": set(),
}
TARGETS = ("DELTA_1", "DELTA_2", "VEGA_1", "VEGA_2", "CORRELATION")
Position = tuple[str, Mapping[str, float]]  # (instrument, its numeric keys)


def _cdf(x: float) -> float:
    return 0.5 * math.erfc(-x / math.sqrt(2))


def _pdf(x: float) -> float:
    return math.exp(-x * x / 2) / math.sqrt(2 * math.pi)


class _Market:
    def __init__(self, spot1: float, spot2: float, rate: float, yield1: float, yield2: float,
                 vol1: float, vol2: float, rho: float):
        self.spot, self.yields, self.vols = (spot1, spot2), (yield1, yield2), (vol1, vol2)
        self.rate, self.rho = rate, rho
        # (vol1 - vol2)^2 + 2 (1 - rho) vol1 vol2: exactly 0 when vol1 = vol2 and rho = 1.
        self.spread = math.sqrt((vol1 - vol2) ** 2 + 2 * (1 - rho) * vol1 * vol2)

    def greeks(self, kind: str, k: Mapping[str, float]) -> list[float]:
        """[delta_1, delta_2, vega_1, vega_2, correlation01] of one unit."""
        out = [0.0] * 5
        if kind.startswith("UNDERLYING_"):
            out[int(kind[-1]) - 1] = 1.0
            return out
        t = k["expiry_years"]
        root_t = math.sqrt(t)
        if kind == "EXCHANGE":
            v1, v2 = self.vols
            s = self.spread
            carry1 = k["quantity1"] * math.exp(-self.yields[0] * t)
            carry2 = k["quantity2"] * math.exp(-self.yields[1] * t)
            f1, f2 = carry1 * self.spot[0], carry2 * self.spot[1]
            d1 = (math.log(f1 / f2) + s * s * t / 2) / (s * root_t)
            d2 = d1 - s * root_t
            dv_ds = f1 * _pdf(d1) * root_t
            return [carry1 * _cdf(d1), -carry2 * _cdf(d2), dv_ds * (v1 - self.rho * v2) / s,
                    dv_ds * (v2 - self.rho * v1) / s, dv_ds * (-v1 * v2 / s) * 0.01]
        asset = int(kind[-1]) - 1
        spot, q, vol = self.spot[asset], self.yields[asset], self.vols[asset]
        d1 = (math.log(spot / k["strike"]) + (self.rate - q + vol * vol / 2) * t) / (vol * root_t)
        carry = math.exp(-q * t)
        out[asset] = carry * _cdf(d1) if kind.startswith("CALL") else -carry * _cdf(-d1)
        out[2 + asset] = spot * carry * _pdf(d1) * root_t
        return out


def correlation_neutralise(spot1: float, spot2: float, rate: float, yield1: float,
                           yield2: float, vol1: float, vol2: float, correlation: float,
                           book: Sequence[Position], hedges: Sequence[Position],
                           targets: Sequence[str]) -> dict[str, Any]:
    """`hedge.correlation.neutralise`: quantities of exchange options, vanillas and underlyings
    that set the targeted Greeks of a two-asset book to zero (rulings I-17, I-18). Book
    positions carry a `quantity` key besides their kind's keys.

    Returns {quantities, greeks_before, greeks_after}."""
    for held, items in ((True, book), (False, hedges)):
        for kind, keys in items:
            expected = KEYS[kind] | ({"quantity"} if held else set())
            if set(keys) != expected:
                raise QfError("E_INPUT", f"{kind} takes exactly {sorted(expected)}",
                              "book" if held else "hedges")
    if not hedges:
        raise QfError("E_INPUT", "no hedge instruments", "hedges")
    if len(targets) != len(hedges):
        raise QfError("E_INPUT", "one target per hedge instrument", "targets")
    if len(set(targets)) != len(targets):
        raise QfError("E_INPUT", "a target is repeated", "targets")
    for name, v in (("spot1", spot1), ("spot2", spot2), ("vol1", vol1), ("vol2", vol2)):
        if v <= 0:
            raise QfError("E_DOMAIN", f"{name} must be positive", name)
    if not -1 <= correlation <= 1:
        raise QfError("E_DOMAIN", "correlation must be in [-1, 1]", "correlation")
    for _, keys in (*book, *hedges):
        for name in ("quantity1", "quantity2", "strike", "expiry_years"):
            if name in keys and keys[name] <= 0:
                raise QfError("E_DOMAIN", f"{name} must be positive", name)
    market = _Market(spot1, spot2, rate, yield1, yield2, vol1, vol2, correlation)
    if market.spread == 0 and any(kind == "EXCHANGE" for kind, _ in (*book, *hedges)):
        raise QfError("E_DOMAIN", "the spread volatility is zero", "correlation")

    terms = [(keys["quantity"], market.greeks(kind, keys)) for kind, keys in book]
    before = [math.fsum(q * g[c] for q, g in terms) for c in range(5)]
    per_hedge = [market.greeks(kind, keys) for kind, keys in hedges]
    rows = [TARGETS.index(t) for t in targets]
    g = [[h[r] for h in per_hedge] for r in rows]
    quantities = _solve_square(g, [-before[r] for r in rows], "hedges")
    after = [math.fsum([before[c], *(q * h[c] for q, h in zip(quantities, per_hedge))])
             for c in range(5)]
    names = ("delta_1", "delta_2", "vega_1", "vega_2", "correlation01")
    return {"quantities": [_z(v) for v in quantities],
            "greeks_before": {n: _z(v) for n, v in zip(names, before)},
            "greeks_after": {n: _z(v) for n, v in zip(names, after)}}


guard(globals())
