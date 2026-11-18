"""Typed in-process API for the execution and microstructure layer (stage H item H-5,
`specifications/10-execution/library-interfaces.md`; ADR-0011).

Closed choices are enums, inputs and outputs are frozen dataclasses validated when built, and every
call delegates to the kernel in `execution.py`, so the numbers are the kernel's, bit for bit. The
dict-in, dict-out kernels stay for the CLI.

Thread safety: every function here is pure and holds no state; safe to call from any thread.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any

from . import execution as _k
from .errors import QfError


def _schema(field: str, why: str) -> QfError:
    return QfError("E_SCHEMA", f"{field}: {why}", field)


def _finite(field: str, *xs: float) -> None:
    for x in xs:
        if not math.isfinite(x):
            raise QfError("E_DOMAIN", f"{field} must be finite", field)


class Side(Enum):
    """Order side. Thread safety: immutable; safe to share between threads."""

    BUY = "BUY"
    SELL = "SELL"

    @classmethod
    def parse(cls, text: Any) -> Side:
        """The JSON spelling to the enum, once, at the edge; anything else is E_SCHEMA."""
        try:
            return cls(text)
        except ValueError:
            raise _schema("side", f"unknown value {text!r}") from None


class FillMode(Enum):
    """Whole units or continuous quantities. Thread safety: immutable; safe to share between
    threads."""

    UNITS = "UNITS"
    CONTINUOUS = "CONTINUOUS"

    @classmethod
    def parse(cls, text: Any) -> FillMode:
        try:
            return cls(text)
        except ValueError:
            raise _schema("mode", f"unknown value {text!r}") from None


def _need(value: Any, kind: type[Enum], field: str) -> Any:
    if not isinstance(value, kind):
        raise _schema(field, f"must be {kind.__name__}, not {type(value).__name__}")
    return value


@dataclass(frozen=True, slots=True)
class AcParams:
    """Almgren-Chriss model inputs ([AC00], HR-2, HR-5), checked when built in the order of
    almgren-chriss.md. Thread safety: immutable; safe to share between threads."""

    quantity: float
    horizon: float
    n_steps: int
    sigma: float
    epsilon: float
    eta: float
    gamma: float

    def __post_init__(self) -> None:
        for name in ("quantity", "horizon", "sigma", "epsilon", "eta", "gamma"):
            _finite(name, getattr(self, name))
        _k._ac_check(
            self.quantity,
            self.horizon,
            self.n_steps,
            self.sigma,
            self.epsilon,
            self.eta,
            self.gamma,
        )

    def _args(self) -> tuple[float, float, int, float, float, float, float]:
        return (
            self.quantity,
            self.horizon,
            self.n_steps,
            self.sigma,
            self.epsilon,
            self.eta,
            self.gamma,
        )


@dataclass(frozen=True, slots=True)
class Fill:
    """One execution. Thread safety: immutable; safe to share between threads."""

    quantity: float
    price: float

    def __post_init__(self) -> None:
        _finite("fills", self.quantity, self.price)
        if self.quantity <= 0:
            raise QfError("E_INPUT", "fill quantities must be positive", "fills")
        if self.price <= 0:
            raise QfError("E_DOMAIN", "prices must be positive", "fills")


@dataclass(frozen=True, slots=True)
class Schedule:
    """Child-order slices; `residual` is zero except for POV. Thread safety: immutable; safe to
    share between threads."""

    slices: tuple[float, ...]
    filled: float
    residual: float = 0.0


@dataclass(frozen=True, slots=True)
class AcTrajectory:
    """Holdings x_0..x_N, trades n_1..n_N, kappa, E, V and E + lambda V. Thread safety:
    immutable; safe to share between threads."""

    holdings: tuple[float, ...]
    trades: tuple[float, ...]
    kappa: float
    expected_cost: float
    variance: float
    objective: float


@dataclass(frozen=True, slots=True)
class AcFrontier:
    """One (lambda, E, V) per input, in input order. Thread safety: immutable; safe to share
    between threads."""

    risk_aversions: tuple[float, ...]
    expected_costs: tuple[float, ...]
    variances: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class OwOptimal:
    """Obizhaeva-Wang optimal blocks and rate. Thread safety: immutable; safe to share between
    threads."""

    initial_block: float
    rate: float
    final_block: float


@dataclass(frozen=True, slots=True)
class Shortfall:
    """Perold decomposition (HR-8); `vwap_slippage` is None without a benchmark. Thread safety:
    immutable; safe to share between threads."""

    delay: float
    execution: float
    opportunity: float
    total: float
    total_bps: float
    vwap_slippage: float | None = None


@dataclass(frozen=True, slots=True)
class Quotes:
    """Avellaneda-Stoikov reservation price, spread and quotes; bid <= ask. Thread safety:
    immutable; safe to share between threads."""

    reservation: float
    spread: float
    bid: float
    ask: float

    def __post_init__(self) -> None:
        if not self.bid <= self.ask:
            raise QfError("E_DOMAIN", "bid must not exceed ask", "bid")


def _schedule(out: dict[str, Any]) -> Schedule:
    s = tuple(out["slices"])
    if "filled" in out:
        return Schedule(s, out["filled"], out["residual"])
    return Schedule(s, sum(s))


def twap(quantity: float, n_buckets: int, mode: FillMode) -> Schedule:
    """`exec.schedule.twap`."""
    m = _need(mode, FillMode, "mode")
    _finite("quantity", quantity)
    return _schedule(_k.schedule_twap(quantity, n_buckets, m.value))


def vwap(quantity: float, profile: Sequence[float], mode: FillMode) -> Schedule:
    """`exec.schedule.vwap`."""
    m = _need(mode, FillMode, "mode")
    _finite("quantity", quantity)
    _finite("profile", *profile)
    return _schedule(_k.schedule_vwap(quantity, profile, m.value))


def pov(
    quantity: float, participation: float, market_volume: Sequence[float], mode: FillMode
) -> Schedule:
    """`exec.schedule.pov`."""
    m = _need(mode, FillMode, "mode")
    _finite("quantity", quantity)
    _finite("participation", participation)
    _finite("market_volume", *market_volume)
    return _schedule(_k.schedule_pov(quantity, participation, market_volume, m.value))


def ac_trajectory(params: AcParams, risk_aversion: float) -> AcTrajectory:
    """`exec.ac.trajectory`."""
    _finite("risk_aversion", risk_aversion)
    o = _k.ac_trajectory(*params._args(), risk_aversion)
    return AcTrajectory(
        tuple(o["holdings"]),
        tuple(o["trades"]),
        o["kappa"],
        o["expected_cost"],
        o["variance"],
        o["objective"],
    )


def ac_frontier(params: AcParams, risk_aversions: Sequence[float]) -> AcFrontier:
    """`exec.ac.frontier`."""
    _finite("risk_aversions", *risk_aversions)
    o = _k.ac_frontier(*params._args(), risk_aversions)
    return AcFrontier(tuple(o["risk_aversions"]), tuple(o["expected_costs"]), tuple(o["variances"]))


def impact_sqrt(
    quantity: float, daily_volume: float, daily_vol: float, coefficient: float
) -> float:
    """`exec.impact.sqrt`: impact as a fraction of price; assumed coefficient (HR-10)."""
    _finite("impact", quantity, daily_volume, daily_vol, coefficient)
    return float(_k.impact_sqrt(quantity, daily_volume, daily_vol, coefficient)["impact"])


def ow_optimal(quantity: float, horizon: float, resilience: float) -> OwOptimal:
    """`exec.impact.ow_optimal`."""
    _finite("ow_optimal", quantity, horizon, resilience)
    o = _k.impact_ow_optimal(quantity, horizon, resilience)
    return OwOptimal(o["initial_block"], o["rate"], o["final_block"])


def shortfall(
    side: Side,
    decision_price: float,
    arrival_price: float,
    end_price: float,
    order_quantity: float,
    fills: Sequence[Fill],
    fees: float,
    benchmark_vwap: float | None = None,
) -> Shortfall:
    """`exec.tca.shortfall`."""
    s = _need(side, Side, "side")
    for f in fills:
        if not isinstance(f, Fill):
            raise _schema("fills", "each fill must be a Fill")
    _finite("shortfall", decision_price, arrival_price, end_price, order_quantity, fees)
    if benchmark_vwap is not None:
        _finite("benchmark_vwap", benchmark_vwap)
    o = _k.tca_shortfall(
        s.value,
        decision_price,
        arrival_price,
        end_price,
        order_quantity,
        [(f.quantity, f.price) for f in fills],
        fees,
        benchmark_vwap,
    )
    return Shortfall(
        o["delay"],
        o["execution"],
        o["opportunity"],
        o["total"],
        o["total_bps"],
        o.get("vwap_slippage"),
    )


def as_quotes(
    mid: float, inventory: float, risk_aversion: float, sigma: float, time_left: float, k: float
) -> Quotes:
    """`micro.mm.as_quotes`."""
    _finite("as_quotes", mid, inventory, risk_aversion, sigma, time_left, k)
    o = _k.as_quotes(mid, inventory, risk_aversion, sigma, time_left, k)
    return Quotes(o["reservation"], o["spread"], o["bid"], o["ask"])
