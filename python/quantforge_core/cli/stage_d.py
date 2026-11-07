"""Handlers for the stage D operations. As in stage_c.py, a handler reads every input first; the
first call through `D`, the gated core modules, ends the E_SCHEMA stage."""
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

from .. import conventions, curves
from ..calendars import TENOR
from ..errors import QfError
from ..overnight import FALLBACKS, METHODS
from ..projection import ProjectionQuote
from .inputs import Inputs
from .stage_b import _curve, _objects, _pillars, _quotes, jumps
from .stage_c import _not_null, _present

Handler = Callable[[Inputs], Any]
_OPS: dict[str, Handler] = {}
D = SimpleNamespace()
_BOOT = ("SEQUENTIAL", "GLOBAL")


def op(name: str) -> Callable[[Handler], Handler]:
    def register(f: Handler) -> Handler:
        _OPS[name] = f
        return f

    return register


def _fixings(i: Inputs) -> list[tuple[Any, float]]:
    return [(f.date("date"), f.real("rate")) for f in _objects(i, "fixings")]


@op("rates.ois.compound_dated")
def _compound_dated(i: Inputs) -> Any:
    args = (i.enum("convention", tuple(conventions.REGISTRY)), i.date("start"), i.date("end"),
            i.enum("method", METHODS), i.integer("shift_days"), _fixings(i))
    rate, accrual, interest = D.overnight.compound_dated(*args)
    return {"compounded_rate": rate, "accrual": accrual, "interest": interest}


@op("rates.fallback.rate")
def _fallback(i: Inputs) -> Any:
    args = (i.enum("ibor", tuple(FALLBACKS)), i.date("start"), i.date("end"), _fixings(i))
    rate, spread, total = D.overnight.fallback(*args)
    return {"compounded_rate": rate, "spread_adjustment": spread, "fallback_rate": total}


def _dated_rates(i: Inputs, key: str) -> list[tuple[Any, float]]:
    return [(s.date("date"), s.real("rate")) for s in _objects(i, key)]


@op("rates.ois.step_curve")
def _step_curve(i: Inputs) -> Any:
    args = (i.date("as_of"), i.real("base_rate"), _dated_rates(i, "steps"),
            jumps(i, required=True), i.dates("dates"))
    factors, forwards = D.steps.step_curve(*args)
    return {"discount_factors": factors, "overnight_forwards": forwards}


@op("rates.ois.fit_steps")
def _fit_steps(i: Inputs) -> Any:
    args = (i.enum("convention", conventions.OVERNIGHT), i.date("as_of"), i.dates("step_dates"),
            _quotes(i), jumps(i, required=True))
    base, rates, error = D.steps.fit_steps(*args)
    return {"base_rate": base, "step_rates": rates}, {"max_repricing_error": error}


@op("rates.futures.convexity")
def _convexity(i: Inputs) -> Any:
    args = (i.real("price"), i.real("start_years"), i.real("end_years"), i.real("sigma"),
            i.real("mean_reversion"))
    rate, bias, forward = D.futures.convexity(*args)
    return {"futures_rate": rate, "convexity": bias, "forward_rate": forward}


@op("rates.csa.discount")
def _csa(i: Inputs) -> Any:
    _present(i, "fx")
    fx = None
    if i.has("fx"):
        f = i.object("fx")
        fx = (f.real("spot"), [(p.date("date"), p.real("forward")) for p in _objects(f, "forwards")])
    args = (_curve(i), i.real("collateral_spread"), fx, i.dates("dates"))
    return {"discount_factors": D.csa.discount(*args)}


def _tenor(i: Inputs) -> str:
    tenor = i.string("tenor")
    if TENOR.fullmatch(tenor) is None:
        raise QfError("E_SCHEMA", f"bad tenor {tenor}", "tenor")
    return tenor


@op("rates.basis.ois_spread")
def _ois_spread(i: Inputs) -> Any:
    args = (i.enum("convention", conventions.OVERNIGHT), _tenor(i), _curve(i, "discount"),
            _curve(i, "projection_a"), _curve(i, "projection_b"))
    return {"spread": D.csa.ois_spread(*args)}


def _term_quote(q: Inputs) -> ProjectionQuote:
    kind = q.enum("type", ("DEPOSIT", "FRA", "SWAP"))
    return ProjectionQuote(kind, q.integer("start_months" if kind == "FRA" else "months"),
                           q.real("rate"))


@op("rates.curve.joint_bootstrap")
def _joint(i: Inputs) -> Any:
    ois_quotes = _quotes(Inputs({"quotes": i.array("ois_quotes")}, "ois_"))
    args = (i.enum("convention", conventions.OVERNIGHT), i.enum("index", conventions.TERM),
            i.date("as_of"), ois_quotes, [_term_quote(q) for q in _objects(i, "term_quotes")],
            i.enum("interpolation", curves.INTERPOLATIONS), i.enum("method", _BOOT))
    disc, proj, error = D.csa.joint_bootstrap(*args)
    return ({"discount_pillars": _pillars(disc), "projection_pillars": _pillars(proj)},
            {"max_repricing_error": error})


@op("calib.curve.smooth")
def _smooth(i: Inputs) -> Any:
    _not_null(i, "weights")
    weights = i.reals("weights") if i.has("weights") else None
    args = (i.reals("knots"), i.reals("maturities"), i.reals("zero_rates"), i.real("lambda"),
            weights)
    forwards, fitted, objective = D.curve_fits.smooth(*args)
    return {"forwards": forwards, "fitted": fitted, "objective": objective}


@op("calib.curve.robust")
def _robust(i: Inputs) -> Any:
    args = (i.reals("maturities"), i.reals("zero_rates"), i.real("tau"), i.real("delta"))
    betas, residuals, outliers, objective = D.curve_fits.robust(*args)
    return {"betas": betas, "residuals": residuals, "outliers": outliers, "objective": objective}


def handlers(core: SimpleNamespace) -> dict[str, Handler]:
    D.__dict__.update(core.__dict__)
    return _OPS


# Wave 2, D2: bonds and repo

def _bond(b: Inputs) -> Any:
    from ..bonds import FREQUENCIES, Bond
    frequency = b.integer("frequency")
    if frequency not in FREQUENCIES:
        raise QfError("E_SCHEMA", "frequency must be 1, 2 or 4", "frequency")
    return Bond(b.date("maturity"), b.real("coupon"), frequency)


@op("bond.price.from_yield")
def _bond_from_yield(i: Inputs) -> Any:
    args = (_bond(i.object("bond")), i.date("settlement"), i.real("yield"))
    return D.bonds.price_from_yield(*args)


@op("bond.yield.from_price")
def _bond_yield(i: Inputs) -> Any:
    args = (_bond(i.object("bond")), i.date("settlement"), i.real("clean_price"))
    return D.bonds.yield_from_price(*args)


@op("bond.price.from_curve")
def _bond_from_curve(i: Inputs) -> Any:
    args = (_bond(i.object("bond")), i.date("settlement"), _curve(i))
    return D.bonds.price_from_curve(*args)


@op("bond.spread.z")
def _bond_z(i: Inputs) -> Any:
    args = (_bond(i.object("bond")), i.date("settlement"), _curve(i), i.real("clean_price"))
    return {"z_spread": D.bonds.z_spread(*args)}


@op("bond.spread.asset_swap")
def _bond_asw(i: Inputs) -> Any:
    args = (_bond(i.object("bond")), i.date("settlement"), _curve(i), i.real("dirty_price"))
    annuity, spread = D.bonds.asset_swap(*args)
    return {"annuity": annuity, "spread": spread}


@op("bond.frn.price")
def _frn(i: Inputs) -> Any:
    from ..bonds import FREQUENCIES
    frequency = i.integer("frequency")
    if frequency not in FREQUENCIES:
        raise QfError("E_SCHEMA", "frequency must be 1, 2 or 4", "frequency")
    args = (i.date("settlement"), i.date("maturity"), frequency, i.real("current_rate"),
            i.real("margin"), i.real("discount_margin"), _curve(i, "discount"),
            _curve(i, "projection"))
    return D.bonds.frn_price(*args)


@op("repo.forward")
def _repo_forward(i: Inputs) -> Any:
    _present(i, "gc_rate")
    gc = i.real("gc_rate") if i.has("gc_rate") else None
    args = (_bond(i.object("bond")), i.date("start"), i.date("end"), i.real("clean_price"),
            i.real("repo_rate"), gc)
    return D.bonds.repo_forward(*args)


@op("repo.implied_rate")
def _repo_implied(i: Inputs) -> Any:
    args = (_bond(i.object("bond")), i.date("start"), i.date("end"), i.real("clean_price"),
            i.real("forward_clean"))
    return {"repo_rate": D.bonds.repo_implied(*args)}


def _month(i: Inputs, key: str) -> tuple[int, int]:
    import re
    text = i.string(key)
    m = re.fullmatch(r"(\d{4})-(\d{2})", text)
    if m is None or not 1 <= int(m[2]) <= 12 or int(m[1]) < 1:
        raise QfError("E_SCHEMA", f"{key} is not YYYY-MM", key)
    return int(m[1]), int(m[2])


@op("bond.futures.conversion_factor")
def _conversion(i: Inputs) -> Any:
    bond, (year, month) = _bond(i.object("bond")), _month(i, "delivery_month")
    args = (bond, year, month, i.real("notional_coupon"))
    return {"conversion_factor": D.bonds.conversion_factor(*args)}


@op("bond.futures.basis")
def _futures_basis(i: Inputs) -> Any:
    bonds = [(_bond(b), b.real("clean_price"), b.real("conversion_factor"))
             for b in _objects(i, "bonds")]
    args = (i.real("futures_price"), i.date("settlement"), i.date("delivery"),
            i.real("repo_rate"), bonds)
    rows, ctd = D.bonds.futures_basis(*args)
    return {"bonds": rows, "ctd": ctd}


@op("bond.fit.nelson_siegel")
def _bond_fit(i: Inputs) -> Any:
    _not_null(i, "weights")
    bonds = [(_bond(b), b.real("dirty_price")) for b in _objects(i, "bonds")]
    weights = i.reals("weights") if i.has("weights") else None
    betas, residuals = D.bonds.fit_nelson_siegel(i.date("settlement"), i.real("tau"), bonds,
                                                 weights)
    return {"betas": betas, "residuals": residuals}


# Wave 2, D3: cross-currency and NDF

@op("fx.xccy.bootstrap")
def _xccy_bootstrap(i: Inputs) -> Any:
    quotes = [(q.integer("months"), q.real("spread")) for q in _objects(i, "quotes")]
    args = (_curve(i, "domestic"), _curve(i, "foreign_projection"),
            i.enum("domestic_convention", ("SOFR",)), i.enum("foreign_convention", ("ESTR",)),
            i.date("start"), quotes, i.enum("interpolation", curves.INTERPOLATIONS))
    data, error = D.xccy.bootstrap(*args)
    return {"pillars": _pillars(data)}, {"max_repricing_error": error}


@op("fx.xccy.pv")
def _xccy_pv(i: Inputs) -> Any:
    t = i.object("trade")
    args = (_curve(i, "domestic"), _curve(i, "foreign_projection"),
            _curve(i, "foreign_discount"), i.real("spot"), t.date("start"), t.integer("months"),
            t.real("foreign_notional"), t.real("spread"),
            t.enum("side", ("RECEIVE_FOREIGN", "PAY_FOREIGN")))
    foreign, domestic, value = D.xccy.pv(*args)
    return {"pv": value, "foreign_leg": foreign, "domestic_leg": domestic}


@op("fx.ndf.pv")
def _ndf(i: Inputs) -> Any:
    _present(i, "fixing")
    t = i.object("trade")
    fixing = i.real("fixing") if i.has("fixing") else None
    args = (_curve(i, "usd_curve"), _curve(i, "offshore_curve"), i.real("spot"),
            t.date("fixing_date"), t.date("payment_date"), t.real("strike"),
            t.real("usd_notional"), t.enum("side", ("BUY", "SELL")), fixing)
    value, forward = D.xccy.ndf_pv(*args)
    return {"pv": value, "forward": forward}


# Wave 2, D4: credit

def _hazard(h: Inputs) -> Any:
    pillars = _objects(h, "pillars")
    dates = [p.date("date") for p in pillars]
    return h.date("as_of"), dates, [p.real("survival") for p in pillars]


def _cds_quotes(i: Inputs, key: str = "quotes") -> list[tuple[str, float]]:
    return [(_tenor(q), q.real("spread")) for q in _objects(i, key)]


@op("credit.cds.price")
def _cds_price(i: Inputs) -> Any:
    t = i.object("trade")
    as_of, dates, survival = _hazard(i.object("hazard"))
    args = (i.date("trade_date"), _curve(i, "discount"), i.real("recovery"), t.date("maturity"),
            t.real("coupon"), t.real("notional"),
            t.enum("side", ("BUY_PROTECTION", "SELL_PROTECTION")),
            i.enum("payout", ("STANDARD", "DIGITAL")))
    hazard = D.credit.check_hazard(as_of, dates, survival)
    return D.credit.price(args[0], args[1], hazard, *args[2:])


@op("credit.cds.bootstrap")
def _cds_bootstrap(i: Inputs) -> Any:
    args = (i.date("trade_date"), _curve(i, "discount"), i.real("recovery"), _cds_quotes(i))
    pillars = D.credit.bootstrap(*args)
    return {"pillars": [{"date": d.isoformat(), "survival": q} for d, q in pillars]}


@op("credit.index.intrinsic")
def _cds_index(i: Inputs) -> Any:
    t = i.object("trade")
    raw = [(_hazard(n.object("hazard")), n.real("recovery"), n.real("weight"))
           for n in _objects(i, "names")]
    trade_date, disc = i.date("trade_date"), _curve(i, "discount")
    mat, coupon, quoted = t.date("maturity"), t.real("coupon"), i.real("quoted_upfront")
    names = [(D.credit.check_hazard(*h), r, w) for h, r, w in raw]
    ups, intrinsic, basis = D.credit.index_intrinsic(trade_date, disc, names, mat, coupon,
                                                     quoted)
    return {"name_upfronts": ups, "intrinsic_upfront": intrinsic, "basis": basis}


@op("credit.curve.composite")
def _cds_composite(i: Inputs) -> Any:
    constituents = [(_cds_quotes(c), c.real("weight")) for c in _objects(i, "constituents")]
    args = (i.date("trade_date"), _curve(i, "discount"), i.real("recovery"), constituents,
            i.real("scale"))
    spreads, pillars = D.credit.composite(*args)
    return {"spreads": spreads,
            "pillars": [{"date": d.isoformat(), "survival": q} for d, q in pillars]}


# Wave 2, D5: equity

def _divs(i: Inputs, key: str = "dividends") -> list[tuple[Any, float]]:
    return [(d.date("ex_date"), d.real("amount")) for d in _objects(i, key)]


@op("eq.dividend.implied")
def _div_implied(i: Inputs) -> Any:
    futures = [(f.date("expiry"), f.real("price")) for f in _objects(i, "futures")]
    args = (i.real("spot"), _curve(i, "funding"), i.real("borrow_rate"), futures)
    xs, periods, yields = D.equity_d.dividend_implied(*args)
    return {"pv_dividends": xs, "period_pv_dividends": periods, "dividend_yields": yields}


@op("eq.borrow.implied")
def _borrow_implied(i: Inputs) -> Any:
    args = (i.real("spot"), _curve(i, "funding"), _divs(i), i.date("expiry"), i.real("forward"))
    return {"borrow_rate": D.equity_d.borrow_implied(*args)}


@op("eq.futures.basis")
def _eq_futures_basis(i: Inputs) -> Any:
    args = (i.real("spot"), _curve(i, "funding"), i.real("borrow_rate"),
            i.real("financing_spread"), _divs(i), i.date("expiry"), i.real("futures_price"))
    fair, basis, implied = D.equity_d.futures_basis(*args)
    return {"fair_price": fair, "basis": basis, "implied_financing_spread": implied}


@op("eq.index.dividends")
def _index_divs(i: Inputs) -> Any:
    cons = [(c.string("id"), c.real("shares"), c.real("price"), _divs(c))
            for c in _objects(i, "constituents")]
    periods = [(p.date("start"), p.date("end")) for p in _objects(i, "periods")]
    args = (i.real("divisor"), cons, periods, i.reals("implied_period_points"))
    return D.equity_d.index_dividends(*args)


def _members(i: Inputs, key: str) -> list[tuple[str, float, float]]:
    return [(c.string("id"), c.real("shares"), c.real("price")) for c in _objects(i, key)]


@op("eq.index.rebalance")
def _rebalance(i: Inputs) -> Any:
    args = (i.real("divisor"), _members(i, "constituents"), _members(i, "new_constituents"))
    level, divisor, weights = D.equity_d.rebalance(*args)
    return {"level": level, "new_divisor": divisor, "weights": weights}


_ACTION_KEYS = {"SPLIT": ("ratio",), "REVERSE_SPLIT": ("ratio",),
                "RIGHTS": ("new_per_old", "subscription_price"), "SPECIAL_DIVIDEND": ("amount",)}


@op("eq.corporate_action.adjust")
def _corporate_action(i: Inputs) -> Any:
    action = i.enum("action", tuple(_ACTION_KEYS))
    params = {k: i.real(k) for k in _ACTION_KEYS[action]}
    args = (action, i.real("cum_price"), i.real("shares"), i.real("strike"), params)
    return D.equity_d.corporate_action(*args)


@op("eq.trs.pv")
def _trs(i: Inputs) -> Any:
    _present(i, "current_rate")
    t = i.object("trade")
    current = i.real("current_rate") if i.has("current_rate") else None
    args = (i.real("spot"), _curve(i, "funding"), i.real("borrow_rate"), _divs(i),
            t.date("start"), t.date("end"), t.real("initial_price"), t.real("shares"),
            t.real("spread"), t.enum("side", ("RECEIVE_EQUITY", "PAY_EQUITY")), current)
    equity, funding_leg, value = D.equity_d.trs_pv(*args)
    return {"equity_leg": equity, "funding_leg": funding_leg, "pv": value}
