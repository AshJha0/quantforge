"""Handlers for book.* and usecase.factor_attribution (stage F, slice F5)."""
from typing import Any

from ..errors import QfError
from .inputs import Inputs
from .readers import _objects
from .registry import core, op


def _event(e: Inputs) -> Any:
    from ..book import EVENT_TYPES, Event
    kind = e.enum("type", EVENT_TYPES)
    d = e.date("date")
    if kind == "TRADE":
        return Event(d, kind, e.string("instrument"), e.real("quantity"), e.real("price"))
    if kind == "FIXING":
        return Event(d, kind, index=e.string("index"), value=e.real("value"))
    if kind == "EXPIRY":
        return Event(d, kind, e.string("instrument"), price=e.real("settlement_price"))
    if kind == "DEFAULT":
        return Event(d, kind, e.string("instrument"), price=e.real("recovery_price"))
    return Event(d, kind, e.string("from"), price=e.real("from_price"), to=e.string("to"),
                 to_price=e.real("to_price"))


@op("book.lifecycle.apply")
def _lifecycle(i: Inputs) -> Any:
    positions = [(p.string("instrument"), p.real("quantity"), p.real("average_cost"))
                 for p in _objects(i, "positions")]
    return core.book.lifecycle_apply(positions, [_event(e) for e in _objects(i, "events")])


@op("book.marks.resolve")
def _marks(i: Inputs) -> Any:
    from ..book import Source
    names = i.array("instruments")
    if any(not isinstance(n, str) for n in names):
        raise QfError("E_SCHEMA", "instruments must be strings", "instruments")
    sources = [Source(s.string("name"), tuple(
        (q.string("instrument"), q.date("date"), q.real("price")) for q in _objects(s, "quotes")))
        for s in _objects(i, "sources")]
    ipv = [(p.string("instrument"), p.real("price")) for p in _objects(i, "ipv")] \
        if i.has("ipv") else []
    threshold = i.real("ipv_threshold") if i.has("ipv_threshold") else 0.0
    return core.book.marks_resolve(i.date("as_of"), names, sources, i.integer("max_age_days"),
                                   ipv, threshold)


@op("usecase.factor_attribution")
def _factor_attribution(i: Inputs) -> Any:
    names = i.array("factor_names")
    if any(not isinstance(n, str) for n in names):
        raise QfError("E_SCHEMA", "factor_names must be strings", "factor_names")
    raw = i.array("factor_returns")
    if any(not isinstance(r, list) for r in raw):
        raise QfError("E_SCHEMA", "factor_returns must be rows", "factor_returns")
    rows = [Inputs({"r": r}, "factor_returns.").reals("r") for r in raw]
    return core.book.factor_attribution(i.reals("portfolio_returns"), rows, names)
