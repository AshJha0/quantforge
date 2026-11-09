"""Handlers for the hedging verbs. A handler reads every input first; the first call through `core`, the gated core modules, ends the E_SCHEMA stage."""
from .registry import core, op


@op("hedge.solve")
def hedge_solve(i):
    x, residual, objective = core.hedging.solve(
        i.matrix("a"), i.reals("b"), i.reals("weights"), i.reals("costs"), i.real("lambda"))
    return {"x": x, "residual": residual, "objective": objective}


@op("hedge.spread_cost")
def spread_cost(i):
    return {"cost": core.hedging.spread_cost(i.reals("quantities"), i.reals("half_spreads"))}
