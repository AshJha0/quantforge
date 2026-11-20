"""Handlers for the stage K wave 2 lane A verbs: FRTB DRC and RRAO (K-8a) and FRTB IMA (K-8f).

Specifications: specifications/06-risk/frtb-drc-rrao.md and specifications/06-risk/frtb-ima.md.
Registration (CORE_MODULES entries "frtb_drc" and "frtb_ima", the import of this module in
operations.py and the limits hook) is applied by the stage K coordinator:
program/STAGE_K_W2A_HANDOVER.md. Every E_SCHEMA check (missing field, wrong type, unlisted enum)
happens here, before the gate."""

import re
from typing import Any

from ..errors import QfError
from .inputs import Inputs
from .readers import _objects
from .registry import core, op

_BUCKETS = ("CORPORATE", "SOVEREIGN", "LOCAL_GOV")
_SENIORITIES = ("COVERED", "SENIOR", "NON_SENIOR", "EQUITY")
_RATINGS = ("AAA", "AA", "A", "BBB", "BB", "B", "CCC", "UNRATED", "DEFAULTED")
_KINDS = ("EXOTIC", "OTHER")
_ZONES = ("GREEN", "AMBER")
_CLASSES = ("IR", "EQ", "FX", "COM", "CS")
_ROWS = ("A", "B", "C", "D")
_FX = re.compile(r"[A-Z]{3}/[A-Z]{3}")


def _schema(key: str, why: str) -> QfError:
    return QfError("E_SCHEMA", f"{key}: {why}", key)


@op("risk.frtb.drc_nonsec")
def _drc_nonsec(i: Inputs) -> Any:
    from ..frtb_drc import Position

    positions = [
        Position(
            id=p.string("id"),
            obligor=p.string("obligor"),
            bucket=p.enum("bucket", _BUCKETS),
            seniority=p.enum("seniority", _SENIORITIES),
            notional=p.real("notional"),
            market_value=p.real("market_value"),
            maturity_years=p.real("maturity_years"),
            cash_equity=p.opt_boolean("cash_equity", False),
            lgd_applies=p.opt_boolean("lgd_applies", True),
        )
        for p in _objects(i, "positions")
    ]
    r = i.object("ratings")
    ratings = {name: r.enum(name, _RATINGS) for name in r.raw}
    return core.frtb_drc.drc_nonsec(positions, ratings)


@op("risk.frtb.drc_sec_nonctp")
def _drc_sec(i: Inputs) -> Any:
    from ..frtb_drc import SecPosition

    positions = [
        SecPosition(
            id=p.string("id"),
            bucket=p.string("bucket"),
            pool=p.string("pool"),
            tranche=p.string("tranche"),
            market_value=p.real("market_value"),
            maturity_years=p.real("maturity_years"),
            rw=p.real("rw"),
        )
        for p in _objects(i, "positions")
    ]
    return core.frtb_drc.drc_sec_nonctp(positions)


@op("risk.frtb.drc_ctp")
def _drc_ctp(i: Inputs) -> Any:
    from ..frtb_drc import CtpPosition

    positions = None
    if i.has("positions"):
        positions = [
            CtpPosition(
                id=p.string("id"),
                index=p.string("index"),
                series=p.string("series"),
                tranche=p.string("tranche"),
                market_value=p.real("market_value"),
                maturity_years=p.real("maturity_years"),
                rw=p.real("rw"),
            )
            for p in _objects(i, "positions")
        ]
    bucket_drc = i.reals("bucket_drc") if i.has("bucket_drc") else None
    return core.frtb_drc.drc_ctp(positions, bucket_drc)


@op("risk.frtb.rrao")
def _rrao(i: Inputs) -> Any:
    from ..frtb_drc import Instrument

    instruments = [
        Instrument(
            id=x.string("id"),
            gross_notional=x.real("gross_notional"),
            kind=x.enum("kind", _KINDS),
            listed_or_clearable=x.boolean("listed_or_clearable"),
            back_to_back=x.boolean("back_to_back"),
        )
        for x in _objects(i, "instruments")
    ]
    return core.frtb_drc.rrao(instruments)


@op("risk.frtb.pla")
def _pla(i: Inputs) -> Any:
    return core.frtb_ima.pla(i.reals("hpl"), i.reals("rtpl"))


@op("risk.frtb.pla.ks_pvalue")
def _pla_pvalue(i: Inputs) -> Any:
    return core.frtb_ima.pla_ks_pvalue(i.real("ks"), i.integer("n"))


@op("risk.frtb.ima.lh")
def _lh(i: Inputs) -> Any:
    from ..frtb_ima import LH_TABLE

    category = i.enum("category", tuple(LH_TABLE)) if i.has("category") else None
    fx_pair = None
    if i.has("fx_pair"):
        fx_pair = i.string("fx_pair")
        if _FX.fullmatch(fx_pair) is None:
            raise _schema("fx_pair", "not of the form AAA/BBB")
    constituents = None
    if i.has("constituents"):
        constituents = [(c.real("weight"), c.integer("n")) for c in _objects(i, "constituents")]
    maturity = i.opt_real("maturity_days")
    return core.frtb_ima.liquidity_horizon(category, fx_pair, constituents, maturity)


@op("risk.frtb.ima.es_lh")
def _es_lh(i: Inputs) -> Any:
    es_t = i.reals("es_t") if i.has("es_t") else None
    sigma = i.reals("sigma") if i.has("sigma") else None
    pnl = i.matrix("pnl") if i.has("pnl") else None
    return core.frtb_ima.es_lh(es_t, sigma, pnl)


def _triple(t: Inputs) -> tuple[float, float, float]:
    return t.real("es_rs"), t.real("es_fc"), t.real("es_rc")


@op("risk.frtb.ima.es_stressed")
def _es_stressed(i: Inputs) -> Any:
    return core.frtb_ima.es_stressed(*_triple(i))


@op("risk.frtb.ima.imcc")
def _imcc(i: Inputs) -> Any:
    portfolio = _triple(i.object("portfolio"))
    c = i.object("classes")
    for key in c.raw:
        if key not in _CLASSES:
            raise _schema(f"classes.{key}", "not a risk class (IR, EQ, FX, COM, CS)")
    classes = {key: _triple(c.object(key)) for key in c.raw}
    return core.frtb_ima.imcc(portfolio, classes)


@op("risk.frtb.ima.ses")
def _ses(i: Inputs) -> Any:
    return core.frtb_ima.ses(i.reals("idio_credit"), i.reals("idio_equity"), i.reals("other"))


@op("risk.frtb.ima.capital")
def _capital(i: Inputs) -> Any:
    desks = [(d.enum("zone", _ZONES), d.real("sa")) for d in _objects(i, "desks")]
    return core.frtb_ima.capital(
        i.real("imcc_prev"),
        i.real("ses_prev"),
        i.real("imcc_avg"),
        i.real("ses_avg"),
        i.integer("exceptions"),
        i.real("drc"),
        desks,
        i.real("c_u"),
        i.real("sa_all"),
        i.opt_real("qualitative_addon", 0.0),
    )


@op("risk.frtb.rfet")
def _rfet(i: Inputs) -> Any:
    return core.frtb_ima.rfet(i.date("as_of"), i.dates("observations"))


@op("risk.frtb.rfet.bucket")
def _rfet_bucket(i: Inputs) -> Any:
    return core.frtb_ima.rfet_bucket(i.enum("row", _ROWS), i.opt_real("t"), i.opt_real("delta"))
