"""Handlers for the stage K wave 1b verbs: SA-CCR (K-8d) and FRTB IMA backtesting (K-8e).

Specifications: specifications/06-risk/sa-ccr.md and specifications/06-risk/frtb-ima-backtest.md.
Registration (CORE_MODULES entries "saccr" and "frtb_backtest", and the import of this module in
operations.py) is applied by the stage K coordinator: program/STAGE_K_W1B_HANDOVER.md."""

from typing import Any

from .inputs import Inputs
from .readers import _objects
from .registry import core, op

_CLASSES = ("IR", "FX", "CREDIT", "EQUITY", "COMMODITY")
_KINDS = ("LINEAR", "OPTION", "CDO")
_POSITIONS = ("LONG", "SHORT", "BOUGHT", "SOLD")
_TREATMENTS = ("NORMAL", "BASIS", "VOLATILITY")
_SUBCLASSES = (
    "AAA", "AA", "A", "BBB", "BB", "B", "CCC", "IG", "SG", "SINGLE", "INDEX",
    "ELECTRICITY", "OIL_GAS", "METALS", "AGRICULTURAL", "OTHER",
)  # fmt: skip


def _trade(t: Inputs) -> Any:
    from ..saccr import Trade

    return Trade(
        id=t.string("id"),
        asset_class=t.enum("asset_class", _CLASSES),
        notional=t.real("notional"),
        market_value=t.real("market_value"),
        maturity=t.real("maturity"),
        kind=t.enum("kind", _KINDS) if t.has("kind") else "LINEAR",
        position=t.enum("position", _POSITIONS),
        treatment=t.enum("treatment", _TREATMENTS) if t.has("treatment") else "NORMAL",
        start=t.opt_real("start"),
        end=t.opt_real("end"),
        hedging_set=t.opt_string("hedging_set"),
        entity=t.opt_string("entity"),
        subclass=t.enum("subclass", _SUBCLASSES) if t.has("subclass") else None,
        option_type=t.enum("option_type", ("CALL", "PUT")) if t.has("option_type") else None,
        underlying_price=t.opt_real("underlying_price"),
        strike=t.opt_real("strike"),
        exercise=t.opt_real("exercise"),
        shift=t.opt_real("shift", 0.0),
        attachment=t.opt_real("attachment"),
        detachment=t.opt_real("detachment"),
    )


@op("risk.saccr.ead")
def _saccr_ead(i: Inputs) -> Any:
    from ..saccr import Margin

    trades = [_trade(t) for t in _objects(i, "trades")]
    margin = None
    if i.has("margin"):
        m = i.object("margin")
        margin = Margin(
            threshold=m.real("threshold"),
            mta=m.real("mta"),
            nica=m.real("nica"),
            remargin_days=m.integer("remargin_days"),
            mpor_days=m.opt_integer("mpor_days"),
            illiquid=m.opt_boolean("illiquid", False),
            disputes=m.opt_boolean("disputes", False),
        )
    collateral = i.opt_real("collateral", 0.0)
    ir_offset = i.opt_boolean("ir_offset", True)
    return core.saccr.ead(trades, collateral, margin, ir_offset)


@op("risk.frtb.backtest.zone")
def _frtb_zone(i: Inputs) -> Any:
    return core.frtb_backtest.backtest_zone(
        i.integer("observations"),
        i.integer("exceptions_actual"),
        i.integer("exceptions_hypothetical"),
    )


@op("risk.frtb.backtest.desk")
def _frtb_desk(i: Inputs) -> Any:
    return core.frtb_backtest.backtest_desk(
        i.integer("observations"),
        i.integer("exceptions_99_actual"),
        i.integer("exceptions_99_hypothetical"),
        i.integer("exceptions_975_actual"),
        i.integer("exceptions_975_hypothetical"),
    )


@op("risk.frtb.backtest.count")
def _frtb_count(i: Inputs) -> Any:
    return core.frtb_backtest.count_exceptions(
        i.nullable_reals("var"), i.nullable_reals("actual"), i.nullable_reals("hypothetical")
    )
