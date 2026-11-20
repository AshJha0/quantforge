"""Handlers for the stage K wave 2b verbs: CVA capital (K-8g) and leverage ratio and large
exposures (K-8i).

Specifications: specifications/06-risk/cva-capital.md and leverage-large-exposures.md; rulings
KR-50 to KR-69 and KR-311 to KR-326 (specifications/stage-k-rulings-w2.md). Registration
(CORE_MODULES entries "cva" and "leverage", and the import of this module in operations.py) is
applied by the stage K coordinator: program/STAGE_K_W2B_HANDOVER.md.

Reading here is the E_SCHEMA stage (enums included); the core does the rest in the order of KR-67.
Every enum is taken from the core module (one copy, KR-50), imported inside the handler so that
start-up loads nothing.
"""

from typing import Any

from ..errors import QfError
from .inputs import Inputs
from .readers import _objects
from .registry import core, op


def _list(i: Inputs, key: str) -> list[Inputs]:
    """An optional array of objects: absent means empty (KR-319)."""
    return _objects(i, key) if i.has(key) else []


@op("risk.cva.ba")
def _cva_ba(i: Inputs) -> Any:
    from ..cva import (
        QUALITIES,
        RELATIONS,
        SECTORS,
        VERSIONS,
        Constituent,
        Counterparty,
        IndexHedge,
        NettingSet,
        SingleNameHedge,
    )

    cps = [
        Counterparty(
            id=c.string("id"),
            sector=c.enum("sector", SECTORS),
            quality=c.enum("quality", QUALITIES),
            netting_sets=tuple(
                NettingSet(n.real("ead"), n.real("m"), n.opt_boolean("imm", False))
                for n in _objects(c, "netting_sets")
            ),
        )
        for c in _objects(i, "counterparties")
    ]
    version = i.enum("version", VERSIONS)
    single = [
        SingleNameHedge(
            counterparty=h.string("counterparty"),
            relation=h.enum("relation", tuple(RELATIONS)),
            sector=h.enum("sector", SECTORS),
            quality=h.enum("quality", QUALITIES),
            m=h.real("m"),
            notional=h.real("notional"),
        )
        for h in _list(i, "single_name_hedges")
    ]
    index = [
        IndexHedge(
            m=h.real("m"),
            notional=h.real("notional"),
            constituents=tuple(
                Constituent(
                    k.enum("sector", SECTORS), k.enum("quality", QUALITIES), k.real("weight")
                )
                for k in _objects(h, "constituents")
            ),
        )
        for h in _list(i, "index_hedges")
    ]
    return core.cva.ba_cva(cps, version, single, index)


def _sensitivity(cls: str, kind: str, s: Inputs) -> Any:
    from ..cva import (
        CCS_TENORS,
        IR_DELTA_FACTORS,
        IR_VEGA_FACTORS,
        QUALITIES,
        CreditFactor,
        Sensitivity,
    )

    factor: Any
    if cls == "CCS":
        f = s.object("factor")
        factor = CreditFactor(
            name=f.string("name"),
            tenor=f.enum("tenor", CCS_TENORS),
            quality=f.enum("quality", QUALITIES),
            legal_group=f.opt_string("legal_group"),
            index=f.opt_string("index"),
            series=f.opt_string("series"),
        )
    elif cls == "IR":
        factor = s.enum("factor", IR_DELTA_FACTORS if kind == "DELTA" else IR_VEGA_FACTORS)
    else:
        factor = s.string("factor")
    return Sensitivity(s.string("bucket"), factor, s.real("s_cva"), s.real("s_hdg"))


@op("risk.cva.sa")
def _cva_sa(i: Inputs) -> Any:
    from ..cva import KINDS, RISK_CLASSES

    # CCS.VEGA is read here and refused by the core as E_INPUT (cva-capital.md, Errors)
    keys = {f"{c}.{k}" for c in RISK_CLASSES for k in KINDS}
    c = i.object("classes")
    classes: dict[str, list[Any]] = {}
    for key in c.raw:
        if key not in keys:
            raise QfError("E_SCHEMA", f"classes: {key} is not listed", "classes")
        cls, _, kind = key.partition(".")
        classes[key] = [_sensitivity(cls, kind, s) for s in _objects(c, key)]
    return core.cva.sa_cva(classes, i.string("reporting_currency"), i.opt_real("m_cva", 1.0))


@op("risk.capital.leverage")
def _leverage(i: Inputs) -> Any:
    from ..leverage import CCF_CATEGORIES, DerivativeSet, OffBalance, Sft, WrittenCreditDerivative

    return core.leverage.leverage(
        i.real("tier1"),
        i.reals("on_balance") if i.has("on_balance") else [],
        [
            DerivativeSet(
                v=d.real("v"),
                pfe=d.real("pfe"),
                cvm_received=d.opt_real("cvm_received", 0.0),
                cvm_provided=d.opt_real("cvm_provided", 0.0),
            )
            for d in _list(i, "derivatives")
        ],
        [
            WrittenCreditDerivative(
                notional=w.real("notional"),
                fair_value=w.real("fair_value"),
                purchased_offset=w.opt_real("purchased_offset", 0.0),
            )
            for w in _list(i, "written_credit_derivatives")
        ],
        [
            Sft(
                gross_assets=s.real("gross_assets"),
                mna=s.boolean("mna"),
                exposures=tuple(s.reals("exposures")),
                collateral=tuple(s.reals("collateral")),
            )
            for s in _list(i, "sfts")
        ],
        [
            OffBalance(o.real("notional"), o.enum("ccf_category", tuple(CCF_CATEGORIES)))
            for o in _list(i, "off_balance")
        ],
    )


@op("risk.capital.large_exposures")
def _large_exposures(i: Inputs) -> Any:
    from ..leverage import (
        RANKS,
        BankingBookExposure,
        LeCounterparty,
        OffBalanceExposure,
        Protection,
        TradingPosition,
    )

    tier1 = i.real("tier1")
    bank_gsib = i.opt_boolean("bank_gsib", False)
    cps = [
        LeCounterparty(
            id=c.string("id"),
            group=c.opt_string("group"),
            gsib=c.opt_boolean("gsib", False),
            exempt=c.opt_boolean("exempt", False),
        )
        for c in _objects(i, "counterparties")
    ]
    bb = [
        BankingBookExposure(b.string("counterparty"), b.real("value"))
        for b in _list(i, "banking_book")
    ]
    obs = [
        OffBalanceExposure(o.string("counterparty"), o.real("notional"), o.real("ccf"))
        for o in _list(i, "off_balance")
    ]
    crm = [
        Protection(p.string("counterparty"), p.string("provider"), p.real("protected"))
        for p in _list(i, "crm")
    ]
    tb = [
        TradingPosition(
            id=t.string("id"),
            counterparty=t.string("counterparty"),
            seniority=t.enum("seniority", tuple(RANKS)),
            notional=t.real("notional"),
            market_value=t.real("market_value"),
            maturity_years=t.opt_real("maturity_years"),
            cash_equity=t.opt_boolean("cash_equity", False),
            lgd_applies=t.opt_boolean("lgd_applies", True),
        )
        for t in _list(i, "trading_book")
    ]
    return core.leverage.large_exposures(tier1, cps, bb, obs, crm, tb, bank_gsib)
