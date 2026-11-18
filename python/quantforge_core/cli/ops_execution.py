"""Stage H wave 1 verbs (rulings HR-1 to HR-10): execution schedules, Almgren-Chriss, impact,
implementation-shortfall TCA and Avellaneda-Stoikov quotes."""

from typing import Any

from .inputs import Inputs
from .readers import _objects
from .registry import core, op

MODES = ("UNITS", "CONTINUOUS")  # HR-3
SIDES = ("BUY", "SELL")  # HR-2


def _mode(i: Inputs) -> str:
    """`mode` is `UNITS` or `CONTINUOUS`; absent means `CONTINUOUS`."""
    return i.enum("mode", MODES) if i.has("mode") else "CONTINUOUS"


@op("exec.schedule.twap")
def exec_schedule_twap(i: Inputs) -> Any:
    q, n, m = i.real("quantity"), i.integer("n_buckets"), _mode(i)
    return core.execution.schedule_twap(q, n, m)


@op("exec.schedule.vwap")
def exec_schedule_vwap(i: Inputs) -> Any:
    q, w, m = i.real("quantity"), i.reals("profile"), _mode(i)
    return core.execution.schedule_vwap(q, w, m)


@op("exec.schedule.pov")
def exec_schedule_pov(i: Inputs) -> Any:
    q, p = i.real("quantity"), i.real("participation")
    v, m = i.reals("market_volume"), _mode(i)
    return core.execution.schedule_pov(q, p, v, m)


def _ac(i: Inputs) -> tuple[float, float, int, float, float, float, float]:
    return (
        i.real("quantity"),
        i.real("horizon"),
        i.integer("n_steps"),
        i.real("sigma"),
        i.real("epsilon"),
        i.real("eta"),
        i.real("gamma"),
    )


@op("exec.ac.trajectory")
def exec_ac_trajectory(i: Inputs) -> Any:
    a, lam = _ac(i), i.real("risk_aversion")
    return core.execution.ac_trajectory(*a, lam)


@op("exec.ac.frontier")
def exec_ac_frontier(i: Inputs) -> Any:
    a, lams = _ac(i), i.reals("risk_aversions")
    return core.execution.ac_frontier(*a, lams)


@op("exec.impact.sqrt")
def exec_impact_sqrt(i: Inputs) -> Any:
    q, v, s = i.real("quantity"), i.real("daily_volume"), i.real("daily_vol")
    y = i.opt_real("coefficient", 1.0)
    return core.execution.impact_sqrt(q, v, s, y)


@op("exec.impact.ow_optimal")
def exec_impact_ow_optimal(i: Inputs) -> Any:
    q, t, r = i.real("quantity"), i.real("horizon"), i.real("resilience")
    return core.execution.impact_ow_optimal(q, t, r)


@op("exec.tca.shortfall")
def exec_tca_shortfall(i: Inputs) -> Any:
    side = i.enum("side", SIDES)
    pd, p0, pc = i.real("decision_price"), i.real("arrival_price"), i.real("end_price")
    x = i.real("order_quantity")
    fills = [(f.real("quantity"), f.real("price")) for f in _objects(i, "fills")]
    fees, vwap = i.opt_real("fees", 0.0), i.opt_real("benchmark_vwap")
    return core.execution.tca_shortfall(side, pd, p0, pc, x, fills, fees, vwap)


@op("micro.mm.as_quotes")
def micro_mm_as_quotes(i: Inputs) -> Any:
    s, q = i.real("mid"), i.real("inventory")
    g, sig = i.real("risk_aversion"), i.real("sigma")
    t, k = i.real("time_left"), i.real("k")
    return core.execution.as_quotes(s, q, g, sig, t, k)


@op("usecase.execution_tca")
def usecase_execution_tca(i: Inputs) -> Any:
    a, lam = _ac(i), i.real("risk_aversion")
    side = i.enum("side", SIDES)
    pd, p0, pc = i.real("decision_price"), i.real("arrival_price"), i.real("end_price")
    fp, m = i.reals("fill_prices"), i.integer("completed_steps")
    fee = i.real("fee_per_unit")
    return core.execution.execution_tca(a, lam, side, pd, p0, pc, fp, m, fee)
