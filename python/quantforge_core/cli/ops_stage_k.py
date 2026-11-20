"""Stage K wave 1 verbs (rulings KR-1 to KR-14 of `stage-k-rulings-w1.md`, confirmed except KR-8).

Error order HR-122 (ruling KR-230): reading the inputs is E_SCHEMA; the gate then applies the size limits
(limits.md, KR-231) and the finite rule; the core applies structural E_INPUT, E_DOMAIN and, for the
incremental update, the stale-cache E_INPUT."""

from typing import Any

from .. import stage_k as sk
from ..errors import QfError
from ..snapshot import has_lone_surrogate
from .inputs import Inputs, format_seconds
from .ops_core import _any_value
from .readers import _objects
from .registry import core, op


def _zulu(seconds: int) -> str:
    return format_seconds(seconds, "Z")


def _bi_record(raw: Any) -> sk.BiRecord:
    if not isinstance(raw, dict):
        raise QfError("E_SCHEMA", "a record is not an object", "records")
    r = Inputs(raw, "records.")
    if "value" not in raw or "valid_to" not in raw:
        raise QfError("E_SCHEMA", "a record has no value or no valid_to", "records")
    sequence, series_id = r.integer("sequence"), r.string("series_id")
    if sequence < 1 or not series_id or has_lone_surrogate(raw):
        raise QfError("E_SCHEMA", "bad sequence, series_id or string in a record", "records")
    return sk.BiRecord(
        sequence,
        series_id,
        r.instant("valid_from"),
        r.opt_instant("valid_to"),
        r.instant("knowledge_time"),
        _any_value(raw["value"]),
        r.opt_boolean("deleted", False),
    )


@op("core.store.bitemporal_query")
def _bitemporal_query(i: Inputs) -> Any:
    log = [_bi_record(r) for r in i.array("records")]
    series_id = i.string("series_id")
    k, v = i.instant("knowledge_as_of"), i.instant("valid_at")
    status, w = core.stage_k.bitemporal_query(log, series_id, k, v)
    if w is None:
        return {"status": status, "row": None}
    row = {
        "sequence": w.sequence,
        "valid_from": _zulu(w.valid_from),
        "valid_to": None if w.valid_to is None else _zulu(w.valid_to),
        "knowledge_time": _zulu(w.knowledge_time),
        "value": w.value,
    }
    return {"status": status, "row": row}


@op("curve.bootstrap.par_annual")
def _par_annual(i: Inputs) -> Any:
    quotes = i.reals("quotes")
    return core.stage_k.par_annual(quotes)


@op("curve.incremental.update")
def _incremental(i: Inputs) -> Any:
    pq, pd = i.reals("previous_quotes"), i.reals("previous_discount_factors")
    nq = i.reals("new_quotes")
    return core.stage_k.incremental_update(pq, pd, nq)


@op("calib.trigger.check")
def _trigger(i: Inputs) -> Any:
    changes = i.reals("changes")
    x_ref, x_now = i.real("x_ref"), i.real("x_now")
    d, k = i.real("days_since"), i.real("k")
    return core.stage_k.trigger_check(changes, x_ref, x_now, d, k)


@op("risk.intraday.delta_gamma_bound")
def _intraday(i: Inputs) -> Any:
    positions = [
        sk.ZeroPosition(p.real("notional"), p.real("maturity"), p.real("yield"))
        for p in _objects(i, "positions")
    ]
    shift = i.real("shift")
    return core.stage_k.delta_gamma_bound(positions, shift)


@op("num.richardson.check")
def _richardson(i: Inputs) -> Any:
    values = i.reals("values")
    ratio, p = i.real("ratio"), i.real("assumed_order")
    return core.stage_k.richardson_check(values, ratio, p)
