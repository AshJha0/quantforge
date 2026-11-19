"""Stage K wave 1 (PROPOSED specs, rulings KR-1 to KR-14): the bitemporal store query, the sequential par
bootstrap and its incremental update, recalibration triggers, intraday delta-gamma risk with a Lagrange
bound, and the Richardson guard.

Specifications: 01-core/bitemporal-store.md, 02-curves/incremental-update.md,
03-calibration/recalibration-triggers.md, 06-risk/intraday-risk-bounds.md, 06-risk/bermudan-ladder-k8.md
(`num.richardson.check`).

Error order (HR-122, ruling KR-230): E_LIMIT for the input sizes (the command-line gate; here, for library
calls, the `limits_first` check the finite guard runs first), the finite rule, structural E_INPUT, E_DOMAIN,
then the stale-cache E_INPUT of the incremental update.
"""

import itertools
import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from .errors import QfError
from .finite import guard, limits_first

Floats = Sequence[float]
LABEL = "latency-aware analytics on simulated data"  # KR-10
MAX_RECORDS = 100_000  # the generic array cap of limits.md (KR-231 supersedes 1,000,000)
MAX_QUOTES = 200  # limits.md row (KR-231)
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
    """Log checks 2 to 4 (structural E_INPUT), in the spec's order (after E_LIMIT and the finite rule,
    KR-230)."""
    for a, b in itertools.pairwise(records):
        if b.sequence <= a.sequence:
            raise _input("sequence must be strictly increasing", "records")
    for a, b in itertools.pairwise(records):
        if b.knowledge_time < a.knowledge_time:
            raise _input("knowledge_time went backwards", "records")
    for r in records:
        if r.valid_to is not None and r.valid_to <= r.valid_from:
            raise _input("valid_to must be after valid_from", "records")


def _records_limit(records: Sequence[BiRecord], *_: Any) -> None:
    if len(records) > MAX_RECORDS:
        raise _limit("records", MAX_RECORDS)


@limits_first(_records_limit)
def bitemporal_query(
    records: Sequence[BiRecord], series_id: str, knowledge_as_of: int, valid_at: int
) -> tuple[str, BiRecord | None]:
    """`core.store.bitemporal_query`: the record with the highest sequence among those known by K
    (inclusive) whose valid interval holds V. A deleted winner is WITHDRAWN (it masks older records)."""
    _records_limit(records)
    _check_log(records)
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


def _quotes_limit(quotes: Floats) -> None:
    if len(quotes) > MAX_QUOTES:
        raise _limit("quotes", MAX_QUOTES)


@limits_first(_quotes_limit)
def par_annual(quotes: Floats) -> dict[str, Any]:
    """`curve.bootstrap.par_annual`: discount factors of annual par swaps with accrual 1."""
    _quotes_limit(quotes)
    check_quotes_shape(len(quotes))
    _check_quotes(quotes, "quotes")
    return {"discount_factors": _bootstrap_from(quotes, [])}


def check_update_shape(n_previous: int, n_dfs: int, n_new: int) -> None:
    if n_previous < 1 or not n_previous == n_dfs == n_new:
        raise _input(
            "previous_quotes, previous_discount_factors and new_quotes must have one equal, "
            "non-zero length",
            "new_quotes",
        )


def _update_limit(previous_quotes: Floats, previous_dfs: Floats, new_quotes: Floats) -> None:
    for field, xs in (
        ("previous_quotes", previous_quotes),
        ("previous_discount_factors", previous_dfs),
        ("new_quotes", new_quotes),
    ):
        if len(xs) > MAX_QUOTES:
            raise _limit(field, MAX_QUOTES)


@limits_first(_update_limit)
def incremental_update(
    previous_quotes: Floats, previous_dfs: Floats, new_quotes: Floats
) -> dict[str, Any]:
    """`curve.incremental.update`: copies the pillars before the first changed quote and solves the
    rest. The cache must equal the bootstrap of `previous_quotes` bit for bit (E_INPUT otherwise; the
    last check, KR-230 step 6)."""
    _update_limit(previous_quotes, previous_dfs, new_quotes)
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
    """KR-233: exactly rounded sums, `mean = S1 / n`, `sigma = sqrt(S2 / (n - 1))`."""
    mean = math.fsum(xs) / len(xs)
    return math.sqrt(math.fsum((x - mean) * (x - mean) for x in xs) / (len(xs) - 1))


NOISE_FLOOR = 2.0**-26  # KR-233: sigma at or below 2^-26 max|c_i| is no noise scale


def _changes_limit(changes: Floats, *_: Any) -> None:
    if len(changes) > MAX_CHANGES:
        raise _limit("changes", MAX_CHANGES)


@limits_first(_changes_limit)
def trigger_check(
    changes: Floats, x_ref: float, x_now: float, days_since: float, k: float
) -> dict[str, Any]:
    """`calib.trigger.check`: fires iff `|x_now - x_ref| > k sigma sqrt(d)`, strictly. `false_alarm_rate`
    is the rate on noise with sigma estimated from the window (Student-t, n - 1 degrees of freedom,
    KR-232); `nominal_rate` is the known-sigma `2 Phi(-k)`."""
    _changes_limit(changes)
    check_changes_shape(len(changes))
    if not k > 0:
        raise _domain("k must be above 0", "k")
    if not days_since >= 1:
        raise _domain("days_since must be at least 1", "days_since")
    sigma = _sample_sd(changes)
    if sigma <= NOISE_FLOOR * max(abs(c) for c in changes):
        raise _domain("the changes have no noise scale (sigma at or below 2^-26 max|c|)", "changes")
    threshold = k * sigma * math.sqrt(days_since)
    return {
        "fire": abs(x_now - x_ref) > threshold,
        "sigma": sigma,
        "threshold": threshold,
        "false_alarm_rate": student_t_two_sided_tail(len(changes) - 1, k),
        "nominal_rate": two_sided_normal_tail(k),
    }


_TWO_OVER_PI = 0.6366197723675814
_UP = 2.0**500
_DOWN = 2.0**-500


def _t_step(t: float, j: int, c2: float, odd: bool) -> float:
    if odd:
        return (t * ((2 * j + 2) * c2)) / (2 * j + 3)
    return (t * ((2 * j + 1) * c2)) / (2 * j + 2)


def student_t_two_sided_tail(nu: int, k: float) -> float:
    """`P(|T_nu| > k)` for an integer `nu >= 1` and `k > 0`, by the stated algorithm of KR-232: the closed-form
    finite sum of the t distribution where the tail is at least 1/8, else its remainder series (positive
    terms, no cancellation). Only + - * /, sqrt and one atan2 (odd nu), so the four builds agree to the
    last bit except through atan2."""
    rn = math.sqrt(nu)
    if k <= rn:
        den = nu + k * k
        c2 = nu / den
        root = math.sqrt(den)
        s, c = k / root, rn / root
    else:
        r = rn / k
        w = math.sqrt(1.0 + r * r)
        s, c = 1.0 / w, r / w
        c2 = c * c
    odd = nu % 2 == 1
    m = (nu - 1) // 2 if odd else nu // 2
    t, total, e = 1.0, 0.0, 0
    for j in range(m):
        if e == 0:
            total += t
        t = _t_step(t, j, c2, odd)
        if 0.0 < t < _DOWN:
            t *= _UP
            e += 1
    if odd:
        a = _TWO_OVER_PI * (math.atan2(c, s) - s * c * total)
    else:
        a = 1.0 - s * total
    if a >= 0.125:
        return a
    rem, j = 0.0, m
    while True:
        rem += t
        t = _t_step(t, j, c2, odd)
        j += 1
        if t <= rem * 2.0**-60:
            break
        if t < _DOWN:
            t *= _UP
            rem *= _UP
            e += 1
    out = _TWO_OVER_PI * s * c * rem if odd else s * rem
    for _ in range(e):
        out *= _DOWN
    return out


_C_HI = 0.70710678118654757  # 1/sqrt(2), rounded up
_C_LO = -4.8336466567264567e-17  # 1/sqrt(2) - _C_HI


def two_sided_normal_tail(k: float) -> float:
    """`2 (1 - Phi(k))` for k > 0 (KR-6), evaluated as `2 Phi(-k)` with a tail accurate to about 3e-16 relative.

    `erfc(k / sqrt 2)` is the same number in exact arithmetic, but rounding `k / sqrt 2` first costs about
    `2 y^2 eps` relative (`y = k / sqrt 2`): 1.2e-13 at k = 30, over the 1e-14 of trig_k-0009. As in the C++ normal
    CDF, the rounding error of the argument is carried and corrected by one Taylor term of erfc.
    """
    y = k * _C_HI
    dy = math.fma(k, _C_HI, -y) + k * _C_LO
    slope = -2.0 / math.sqrt(math.pi) * math.exp(-y * y)
    return 2.0 * ((math.erfc(y) + slope * dy) / 2.0)


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
    """The Lagrange bound `|h|^3 M3 / 6` with `M3 = T^3 |N| exp(-T min(y, y + h))` (KR-15), in the order of
    KR-234."""
    t, ah = p.maturity, abs(shift)
    e = math.exp(-t * min(p.yield_, p.yield_ + shift))
    return ah * ah * ah * (t * t * t * abs(p.notional) * e) / 6


def position_estimate(p: ZeroPosition, shift: float) -> float:
    """`V' h + V'' h^2 / 2` with `V = N exp(-y T)`, as `v * (-T h + T T h h / 2)` (KR-234)."""
    t = p.maturity
    v = p.notional * math.exp(-p.yield_ * t)
    return v * (-t * shift + t * t * shift * shift / 2)


ROUNDING_FACTOR = 2.0**-49  # 16 u (KR-234)


def position_rounding(p: ZeroPosition, shift: float) -> float:
    """The rounding allowance `rho` of KR-234: covers the binary64 error of the estimate, of the computed
    Lagrange bound and of the binary64 revaluation of the position."""
    t, ah = p.maturity, abs(shift)
    v = p.notional * math.exp(-p.yield_ * t)
    g = abs(math.expm1(-shift * t))
    scale = 1 + t * abs(p.yield_) + t * ah
    return (
        ROUNDING_FACTOR
        * scale
        * (abs(v) * (t * ah + t * t * (shift * shift) + g) + position_bound(p, shift))
    )


def _positions_limit(positions: Sequence[ZeroPosition], *_: Any) -> None:
    if len(positions) > MAX_POSITIONS:
        raise _limit("positions", MAX_POSITIONS)


@limits_first(_positions_limit)
def delta_gamma_bound(positions: Sequence[ZeroPosition], shift: float) -> dict[str, Any]:
    """`risk.intraday.delta_gamma_bound`: the delta-gamma P&L of a parallel yield move and a bound on its
    distance from the full revaluation: the per-position Lagrange bounds (no netting: their signs are unknown
    in general) plus the binary64 rounding allowance (KR-234), one exactly rounded sum."""
    _positions_limit(positions)
    check_positions_shape(len(positions))
    if any(not p.maturity > 0 for p in positions):
        raise _domain("every maturity must be above 0", "positions.maturity")
    parts = [position_bound(p, shift) for p in positions]
    parts += [position_rounding(p, shift) for p in positions]
    return {
        "estimate_pnl": math.fsum(position_estimate(p, shift) for p in positions),
        "bound": math.fsum(parts),
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
