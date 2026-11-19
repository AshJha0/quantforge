"""Stage K wave 1 (PROPOSED specs, rulings KR-1 to KR-14): the bitemporal store query, the sequential par
bootstrap and its incremental update, recalibration triggers, intraday delta-gamma risk with a Lagrange
bound, and the Richardson guard.

Specifications: 01-core/bitemporal-store.md, 02-curves/incremental-update.md,
03-calibration/recalibration-triggers.md, 06-risk/intraday-risk-bounds.md, 06-risk/bermudan-ladder-k8.md
(`num.richardson.check`).

Error order (HR-66): structural E_INPUT (the `check_*_shape` functions, which the CLI calls before the
finite rule), then E_DOMAIN, then value-dependent E_INPUT, then E_LIMIT.
"""

import itertools
import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from .errors import QfError
from .finite import guard

Floats = Sequence[float]
LABEL = "latency-aware analytics on simulated data"  # KR-10
MAX_RECORDS = 1_000_000
MAX_QUOTES = 200
MAX_CHANGES = 100_000
MAX_POSITIONS = 100_000


def _input(message: str, field: str | None = None) -> QfError:
    return QfError("E_INPUT", message, field)


def _domain(message: str, field: str | None = None) -> QfError:
    return QfError("E_DOMAIN", message, field)


def _limit(field: str, limit: int) -> QfError:
    return QfError("E_LIMIT", f"{field} is above its limit of {limit}", field)


# --- bitemporal store (KR-2, KR-3, KR-14) ---------------------------------------------------------


@dataclass(frozen=True)
class BiRecord:
    """One bitemporal record; instants are whole seconds since the epoch, `valid_to` None is open."""

    sequence: int
    series_id: str
    valid_from: int
    valid_to: int | None
    knowledge_time: int
    value: Any
    deleted: bool


def _check_log(records: Sequence[BiRecord]) -> None:
    """Log checks 2 to 4 (structural E_INPUT), in the spec's order. Private, so the finite guard
    does not run first (HR-66: structural E_INPUT before E_DOMAIN)."""
    for a, b in itertools.pairwise(records):
        if b.sequence <= a.sequence:
            raise _input("sequence must be strictly increasing", "records")
    for a, b in itertools.pairwise(records):
        if b.knowledge_time < a.knowledge_time:
            raise _input("knowledge_time went backwards", "records")
    for r in records:
        if r.valid_to is not None and r.valid_to <= r.valid_from:
            raise _input("valid_to must be after valid_from", "records")


def bitemporal_query(
    records: Sequence[BiRecord], series_id: str, knowledge_as_of: int, valid_at: int
) -> tuple[str, BiRecord | None]:
    """`core.store.bitemporal_query`: the record with the highest sequence among those known by K
    (inclusive) whose valid interval holds V. A deleted winner is WITHDRAWN (it masks older records)."""
    _check_log(records)
    if len(records) > MAX_RECORDS:
        raise _limit("records", MAX_RECORDS)
    best: BiRecord | None = None
    for r in records:
        if (
            r.series_id == series_id
            and r.knowledge_time <= knowledge_as_of
            and r.valid_from <= valid_at
            and (r.valid_to is None or valid_at < r.valid_to)
            and (best is None or r.sequence > best.sequence)
        ):
            best = r
    if best is None:
        return "NONE", None
    if best.deleted:
        return "WITHDRAWN", None
    return "FOUND", best


# --- par bootstrap and incremental update (KR-5) --------------------------------------------------


def check_quotes_shape(n: int) -> None:
    if n < 1:
        raise _input("quotes must hold at least one quote", "quotes")


def _bootstrap_from(quotes: Floats, head: list[float]) -> list[float]:
    """Continues the recursion `P_k = (1 - S_k sum_(i<k) P_i) / (1 + S_k)` after the pillars in
    `head`. The running sum is accumulated left to right, so a continuation is bit-identical to a
    full build over the same quotes."""
    out = list(head)
    acc = 0.0
    for p in out:
        acc += p
    for s in quotes[len(head) :]:
        p = (1.0 - s * acc) / (1.0 + s)
        out.append(p)
        acc += p
    return out


def _check_quotes(quotes: Floats, field: str) -> None:
    if any(not s > -1 for s in quotes):
        raise _domain("every quote must be above -1", field)


def par_annual(quotes: Floats) -> dict[str, Any]:
    """`curve.bootstrap.par_annual`: discount factors of annual par swaps with accrual 1."""
    check_quotes_shape(len(quotes))
    _check_quotes(quotes, "quotes")
    if len(quotes) > MAX_QUOTES:
        raise _limit("quotes", MAX_QUOTES)
    return {"discount_factors": _bootstrap_from(quotes, [])}


def check_update_shape(n_previous: int, n_dfs: int, n_new: int) -> None:
    if n_previous < 1 or not n_previous == n_dfs == n_new:
        raise _input(
            "previous_quotes, previous_discount_factors and new_quotes must have one equal, "
            "non-zero length",
            "new_quotes",
        )


def incremental_update(
    previous_quotes: Floats, previous_dfs: Floats, new_quotes: Floats
) -> dict[str, Any]:
    """`curve.incremental.update`: copies the pillars before the first changed quote and solves the
    rest. The cache must equal the bootstrap of `previous_quotes` bit for bit (E_INPUT otherwise)."""
    check_update_shape(len(previous_quotes), len(previous_dfs), len(new_quotes))
    _check_quotes(previous_quotes, "previous_quotes")
    _check_quotes(new_quotes, "new_quotes")
    fresh = _bootstrap_from(previous_quotes, [])
    if any(
        a != b or math.copysign(1.0, a) != math.copysign(1.0, b)
        for a, b in zip(fresh, previous_dfs, strict=True)
    ):
        raise _input(
            "previous_discount_factors is not the bootstrap of previous_quotes",
            "previous_discount_factors",
        )
    if len(new_quotes) > MAX_QUOTES:
        raise _limit("new_quotes", MAX_QUOTES)
    j = next((i for i, (a, b) in enumerate(zip(previous_quotes, new_quotes)) if a != b), None)
    if j is None:
        return {
            "discount_factors": list(previous_dfs),
            "first_changed_index": None,
            "recomputed": 0,
        }
    dfs = _bootstrap_from(new_quotes, list(previous_dfs[:j]))
    return {"discount_factors": dfs, "first_changed_index": j, "recomputed": len(new_quotes) - j}


# --- recalibration trigger (KR-6, KR-13) ----------------------------------------------------------


def check_changes_shape(n: int) -> None:
    if n < 2:
        raise _input("changes must hold at least two one-day changes", "changes")


def _sample_sd(xs: Floats) -> float:
    mean = math.fsum(xs) / len(xs)
    return math.sqrt(math.fsum((x - mean) ** 2 for x in xs) / (len(xs) - 1))


def trigger_check(
    changes: Floats, x_ref: float, x_now: float, days_since: float, k: float
) -> dict[str, Any]:
    """`calib.trigger.check`: fires iff `|x_now - x_ref| > k sigma sqrt(d)`, strictly."""
    check_changes_shape(len(changes))
    if not k > 0:
        raise _domain("k must be above 0", "k")
    if not days_since >= 1:
        raise _domain("days_since must be at least 1", "days_since")
    sigma = _sample_sd(changes)
    if sigma == 0:
        raise _domain("the changes have zero standard deviation: no noise scale", "changes")
    if len(changes) > MAX_CHANGES:
        raise _limit("changes", MAX_CHANGES)
    threshold = k * sigma * math.sqrt(days_since)
    return {
        "fire": abs(x_now - x_ref) > threshold,
        "sigma": sigma,
        "threshold": threshold,
        "false_alarm_rate": math.erfc(k / math.sqrt(2.0)),
    }


# --- intraday delta-gamma with a Lagrange bound (KR-7, KR-10, KR-12) -----------------------------


@dataclass(frozen=True)
class ZeroPosition:
    notional: float
    maturity: float
    yield_: float


def check_positions_shape(n: int) -> None:
    if n < 1:
        raise _input("positions must not be empty", "positions")


def position_bound(p: ZeroPosition, shift: float) -> float:
    """`|h|^3 M3 / 6` with `M3 = T^3 |N| exp(-T min(y, y + h))`."""
    t = p.maturity
    m3 = t**3 * abs(p.notional) * math.exp(-t * min(p.yield_, p.yield_ + shift))
    return abs(shift) ** 3 * m3 / 6


def position_estimate(p: ZeroPosition, shift: float) -> float:
    """`V' h + V'' h^2 / 2` with `V = N exp(-y T)`."""
    t = p.maturity
    v = p.notional * math.exp(-p.yield_ * t)
    return v * (-t * shift + t * t * shift * shift / 2)


def delta_gamma_bound(positions: Sequence[ZeroPosition], shift: float) -> dict[str, Any]:
    """`risk.intraday.delta_gamma_bound`: the delta-gamma P&L of a parallel yield move and the sum of
    the per-position remainder bounds (no netting: their signs are unknown in general)."""
    check_positions_shape(len(positions))
    if any(not p.maturity > 0 for p in positions):
        raise _domain("every maturity must be above 0", "positions.maturity")
    if len(positions) > MAX_POSITIONS:
        raise _limit("positions", MAX_POSITIONS)
    return {
        "estimate_pnl": math.fsum(position_estimate(p, shift) for p in positions),
        "bound": math.fsum(position_bound(p, shift) for p in positions),
        "label": LABEL,
    }


def zero_revalue(positions: Sequence[ZeroPosition], shift: float) -> float:
    """Full revaluation `sum N (exp(-(y + h) T) - exp(-y T))`; test helper, not an operation."""
    return math.fsum(
        p.notional * math.exp(-p.yield_ * p.maturity) * math.expm1(-shift * p.maturity)
        for p in positions
    )


# --- Richardson guard (KR-9, KR-12) ---------------------------------------------------------------


def check_values_shape(n: int) -> None:
    if n != 3:
        raise _input("values must hold exactly three grid values", "values")


def richardson_check(values: Floats, ratio: float, assumed_order: float) -> dict[str, Any]:
    """`num.richardson.check`: extrapolates only when the differences keep one sign and the
    observed order is within 0.5 of the assumed order."""
    check_values_shape(len(values))
    if not ratio > 1:
        raise _domain("ratio must be above 1", "ratio")
    if not assumed_order > 0:
        raise _domain("assumed_order must be above 0", "assumed_order")
    f1, f2, f3 = values
    d1, d2 = f1 - f2, f2 - f3
    if d1 == 0 or d2 == 0 or (d1 > 0) != (d2 > 0):
        return {"status": "NON_MONOTONE", "observed_order": None, "extrapolated": None}
    observed = math.log(d1 / d2) / math.log(ratio)
    if not abs(observed - assumed_order) <= 0.5:
        return {"status": "ORDER_MISMATCH", "observed_order": observed, "extrapolated": None}
    rp = ratio**assumed_order
    return {"status": "OK", "observed_order": observed, "extrapolated": (rp * f3 - f2) / (rp - 1)}


guard(globals())
