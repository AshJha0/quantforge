"""Stage H wave 1 verbs (rulings HR-1 to HR-10): execution schedules, Almgren-Chriss, impact,
implementation-shortfall TCA and Avellaneda-Stoikov quotes."""

from typing import Any

from ..errors import QfError
from .inputs import Inputs, _is_real, real_value
from .readers import _objects
from .registry import core, op

MODES = ("UNITS", "CONTINUOUS")  # HR-3
SIDES = ("BUY", "SELL")  # HR-2
PAIR_MODES = ("CASH_BALANCED", "HEDGED")  # HR-62


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


# Stage H wave 2 execution (rulings HR-59 to HR-66): adaptive-algos.md and tca-pretrade.md.


@op("exec.algo.arrival")
def exec_algo_arrival(i: Inputs) -> Any:
    q, n, k, m = i.real("quantity"), i.integer("n_buckets"), i.real("urgency"), _mode(i)
    return core.adaptive_exec.algo_arrival(q, n, k, m)


@op("exec.algo.close")
def exec_algo_close(i: Inputs) -> Any:
    q, v, p = i.real("quantity"), i.real("close_volume"), i.real("auction_participation")
    w, m = i.reals("profile"), _mode(i)
    return core.adaptive_exec.algo_close(q, v, p, w, m)


def _books(i: Inputs) -> list[list[tuple[float, float]]]:
    books = i.array("books")
    out: list[list[tuple[float, float]]] = []
    for b, book in enumerate(books):
        if not isinstance(book, list):
            raise QfError("E_SCHEMA", f"books/{b} must be an array of levels", "books")
        levels: list[tuple[float, float]] = []
        for k, lvl in enumerate(book):
            if not (isinstance(lvl, list) and len(lvl) == 2 and all(_is_real(v) for v in lvl)):
                raise QfError("E_SCHEMA", f"books/{b}/{k} must be [price, size]", "books")
            path = f"books/{b}/{k}"
            levels.append((real_value(lvl[0], path), real_value(lvl[1], path)))
        out.append(levels)
    return out


@op("exec.algo.liquidity_seek")
def exec_algo_liquidity_seek(i: Inputs) -> Any:
    side, q = i.enum("side", SIDES), i.real("quantity")
    lim, a, books = i.real("limit_price"), i.real("take_fraction"), _books(i)
    return core.adaptive_exec.algo_liquidity_seek(side, q, lim, a, books)


@op("exec.algo.pair")
def exec_algo_pair(i: Inputs) -> Any:
    a, b = i.object("leg_a"), i.object("leg_b")
    leg_a = (a.enum("side", SIDES), a.real("quantity"), a.real("price"))
    leg_b = (b.enum("side", SIDES), b.real("price"))
    pm, h = i.enum("pair_mode", PAIR_MODES), i.opt_real("hedge_ratio")
    n, m = i.integer("n_buckets"), _mode(i)
    return core.adaptive_exec.algo_pair(leg_a, leg_b, pm, h, n, m)


@op("exec.algo.basket")
def exec_algo_basket(i: Inputs) -> Any:
    legs = [
        (g.enum("side", SIDES), g.real("quantity"), g.real("price")) for g in _objects(i, "legs")
    ]
    n, m = i.integer("n_buckets"), _mode(i)
    return core.adaptive_exec.algo_basket(legs, n, m)


@op("exec.tca.pretrade")
def exec_tca_pretrade(i: Inputs) -> Any:
    q, adv, s = i.real("quantity"), i.real("adv"), i.real("daily_vol")
    p, hs = i.real("participation"), i.real("half_spread_bps")
    k = i.object("params")
    params = (k.real("a1"), k.real("a2"), k.real("a3"), k.real("a4"), k.real("b1"))
    return core.adaptive_exec.tca_pretrade(q, adv, s, p, hs, params, i.opt_real("price"))


@op("exec.tca.attribution")
def exec_tca_attribution(i: Inputs) -> Any:
    side = i.enum("side", SIDES)
    pd, m0, pc = i.real("decision_price"), i.real("arrival_mid"), i.real("end_price")
    x = i.real("order_quantity")
    fills = [(f.real("quantity"), f.real("price"), f.real("mid")) for f in _objects(i, "fills")]
    fees = i.opt_real("fees", 0.0)
    return core.adaptive_exec.tca_attribution(side, pd, m0, pc, x, fills, fees)


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
