"""Handlers for the stage B operations. As in operations.py, a handler reads every input first:
the gate passed in as `core` wraps each core module, and the first call through it ends E_SCHEMA."""
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

from .. import calendars, conventions, curves, money
from .. import daycount as _daycount
from ..calendars import TENOR
from ..calibration import METHODS, PARAMETERS
from ..curves import CurveData
from ..errors import QfError
from ..fx import FxForward, FxMarket, FxSwap
from ..ois import OisTrade, Quote
from ..projection import FraTrade, ProjectionQuote, SwapTrade
from ..schedules import FREQUENCIES
from .inputs import Inputs

Result = Any


def _objects(i: Inputs, key: str) -> list[Inputs]:
    items = i.array(key)
    if not all(isinstance(v, dict) for v in items):
        raise QfError("E_SCHEMA", f"{key} must hold objects", key)
    return [Inputs(v, f"{key}.") for v in items]


def _curve(i: Inputs, key: str = "curve") -> CurveData:
    c = i.object(key)
    pillars = _objects(c, "pillars")
    return CurveData(
        c.date("as_of"),
        c.enum("interpolation", curves.INTERPOLATIONS),
        tuple(p.date("date") for p in pillars),
        tuple(p.real("discount_factor") for p in pillars),
    )


def _pillars(data: CurveData) -> list[dict[str, Any]]:
    return [
        {"date": d.isoformat(), "discount_factor": v}
        for d, v in zip(data.dates, data.discount_factors, strict=True)
    ]


def _tenor(i: Inputs) -> str:
    tenor = i.string("tenor")
    if TENOR.fullmatch(tenor) is None:
        raise QfError("E_SCHEMA", f"bad tenor {tenor}", "tenor")
    return tenor


def _quotes(i: Inputs) -> list[Quote]:
    quotes = []
    for q in _objects(i, "quotes"):
        if q.has("rate"):
            quotes.append(Quote(_tenor(q), q.real("rate")))
        else:
            quotes.append(Quote(_tenor(q), None, q.real("bid"), q.real("ask")))
    return quotes


def _ois_trade(i: Inputs) -> OisTrade:
    t = i.object("trade")
    return OisTrade(
        t.enum("convention", conventions.OVERNIGHT), _tenor(t), t.real("fixed_rate"),
        t.real("notional"), t.enum("side", ("PAY", "RECEIVE")),
    )


def _market(i: Inputs) -> FxMarket:
    return FxMarket(
        i.enum("pair", conventions.PAIRS), i.real("spot"), i.date("as_of"),
        _curve(i, "base_curve"), _curve(i, "quote_curve"),
    )


def _forward_trade(t: Inputs) -> FxForward:
    return FxForward(
        t.real("notional_base"), t.real("strike"), t.date("value_date"),
        t.enum("side", ("BUY", "SELL")),
    )


def _money(m: Inputs) -> tuple[str, str]:
    amount = m.string("amount")
    if money.AMOUNT_FORM.fullmatch(amount) is None:
        raise QfError("E_SCHEMA", "bad amount", "amount")
    return amount, m.enum("currency", tuple(money.MINOR_UNITS))


def _months(tenor: str) -> int:
    n, unit = int(tenor[:-1]), tenor[-1]
    if unit not in "MY":
        raise QfError("E_SCHEMA", "FX points need a month or year tenor", "tenor")
    return n * 12 if unit == "Y" else n


def handlers(core: SimpleNamespace) -> dict[str, Callable[[Inputs], Result]]:
    def convert(i):
        units = tuple(money.UNITS)
        return {"value": core.money.convert(
            i.real("value"), i.enum("from", units), i.enum("to", units))}

    def add_money(i):
        a, b = _money(i.object("a")), _money(i.object("b"))
        amount, currency = core.money.add_money(*a, *b)
        return {"amount": amount, "currency": currency}

    def round_money(i):
        amount, currency = core.money.round_money(*_money(i))
        return {"amount": amount, "currency": currency}

    def lookup(i):
        return core.conventions.lookup(i.enum("id", tuple(conventions.REGISTRY)))

    def schedule(i):
        start, end = i.date("start"), i.date("end")
        frequency = i.integer("frequency_months")
        if frequency not in FREQUENCIES:
            raise QfError("E_SCHEMA", "frequency_months is not listed", "frequency_months")
        periods = core.schedules.generate(
            start, end, frequency, i.enum("calendar", calendars.CALENDARS),
            i.boolean("end_of_month"), i.integer("payment_lag"),
        )
        return {"periods": [
            {"start": p.start.isoformat(), "end": p.end.isoformat(),
             "payment": p.payment.isoformat()}
            for p in periods
        ]}

    def curve_discount(i):
        data = _curve(i)
        factors, zeros = core.curves.discount(data, i.dates("dates"))
        return {"discount_factors": factors, "zero_rates": zeros}

    def curve_forward(i):
        data, start, end = _curve(i), i.date("start"), i.date("end")
        day_count = i.enum("day_count", _daycount.CONVENTIONS)
        _daycount.check_conditional(day_count)
        return {"forward": core.curves.forward(data, start, end, day_count)}

    def bootstrap(i):
        data, error = core.ois.bootstrap(
            i.enum("convention", conventions.OVERNIGHT), i.date("as_of"), _quotes(i),
            i.enum("interpolation", curves.INTERPOLATIONS),
            i.enum("method", ("SEQUENTIAL", "GLOBAL")),
        )
        return {"pillars": _pillars(data)}, {"max_repricing_error": error}

    def compound(i):
        days = i.array("days")
        if not all(isinstance(n, int) and not isinstance(n, bool) for n in days):
            raise QfError("E_SCHEMA", "days must be integers", "days")
        denominator = i.integer("denominator")
        if denominator not in (360, 365):
            raise QfError("E_SCHEMA", "denominator is not listed", "denominator")
        return {"compounded_rate": core.ois.compound(i.reals("rates"), days, denominator)}

    def ois_pv(i):
        value, par, annuity = core.ois.pv(_curve(i), _ois_trade(i), i.opt_string("snapshot_id"))
        return {"valuation": value, "par_rate": par, "annuity": annuity}

    def projection_quote(q):
        kind = q.enum("type", ("DEPOSIT", "FRA", "SWAP"))
        months = q.integer("start_months" if kind == "FRA" else "months")
        return ProjectionQuote(kind, months, q.real("rate"))

    def index(i):
        return i.enum("index", conventions.TERM)

    def projection_bootstrap(i):
        data, error = core.projection.bootstrap(
            _curve(i, "discount"), index(i), i.date("as_of"),
            [projection_quote(q) for q in _objects(i, "quotes")],
            i.enum("interpolation", curves.INTERPOLATIONS),
        )
        return {"pillars": _pillars(data)}, {"max_repricing_error": error}

    def swap_pv(i):
        t = i.object("trade")
        trade = SwapTrade(index(t), t.integer("tenor_months"), t.real("fixed_rate"),
                          t.real("notional"), t.enum("side", ("PAY", "RECEIVE")))
        value, par = core.projection.swap_pv(
            _curve(i, "discount"), _curve(i, "projection"), trade, i.opt_string("snapshot_id"))
        return {"valuation": value, "par_rate": par}

    def fra_pv(i):
        t = i.object("trade")
        trade = FraTrade(index(t), t.date("start"), t.real("fixed_rate"), t.real("notional"),
                         t.enum("side", ("PAY", "RECEIVE")))
        value, rate = core.projection.fra_pv(
            _curve(i, "discount"), _curve(i, "projection"), trade, i.opt_string("snapshot_id"))
        return {"valuation": value, "forward_rate": rate}

    def basis(i):
        return {"spread": core.projection.basis_spread(
            _curve(i, "discount"), _curve(i, "projection"), index(i), i.integer("tenor_months"))}

    def spot_date(i):
        d = core.fx.spot_date(i.enum("pair", conventions.PAIRS), i.date("trade_date"))
        return {"spot_date": d.isoformat()}

    def outright(i):
        f, points = core.fx.outright(_market(i), i.date("value_date"))
        return {"forward": f, "points": points}

    def fx_pv(i):
        value, delta = core.fx.forward_pv(_market(i), _forward_trade(i.object("trade")))
        return {"valuation": value, "fx_delta": delta}

    def fx_swap(i):
        t = i.object("trade")
        trade = FxSwap(t.real("notional_base"), t.date("near_date"), t.real("near_rate"),
                       t.date("far_date"), t.real("far_rate"), t.enum("far_side", ("BUY", "SELL")))
        value, delta = core.fx.swap_pv(_market(i), trade)
        return {"valuation": value, "fx_delta": delta}

    def fx_implied(i):
        market = _market(i)
        points = [(_months(_tenor(p)), p.real("points")) for p in _objects(i, "points")]
        return {"nodes": core.fx.implied(market, points)}

    def fit(i):
        model = i.enum("model", tuple(PARAMETERS))
        report = i.opt_boolean("report_parameters", True)
        optional = {k: i.reals(k) for k in ("weights", "prior", "lower", "upper") if i.has(k)}
        result = core.calibration.fit(
            model, i.reals("x"), i.reals("y"), i.reals("start"), i.enum("method", METHODS),
            regularisation=i.opt_real("regularisation", 0.0),
            max_iter=i.opt_integer("max_iter", 1000), **optional,
        )
        outputs = {"objective": result.objective}
        if report:
            outputs["parameters"] = result.parameters
        return outputs, {"iterations": result.iterations, "status": result.status,
                         "residuals": result.residuals}

    def bid_ask(i):
        return {"breaches": core.calibration.check_bid_ask(
            i.reals("fitted"), i.reals("bid"), i.reals("ask"))}

    def curve_report(i):
        quotes = _quotes(i)
        jacobian, condition, error = core.calibration.curve_report(
            i.enum("convention", conventions.OVERNIGHT), i.date("as_of"), quotes,
            i.enum("interpolation", curves.INTERPOLATIONS),
        )
        diagnostics = {"inputs": [q.tenor for q in quotes], "status": "OK",
                       "max_repricing_error": error, "tolerance_breach": None}
        return {"jacobian": jacobian, "condition_number": condition}, diagnostics

    def dv01(i):
        value, keys = core.sensitivities.dv01(
            i.date("as_of"), _quotes(i), i.enum("interpolation", curves.INTERPOLATIONS),
            _ois_trade(i),
        )
        return {"dv01": value, "key_rate": keys}

    def cashflows(i):
        flows = [(c.real("t"), c.real("amount")) for c in _objects(i, "cashflows")]
        pv, duration, convexity = core.sensitivities.cashflows(flows, i.real("yield"))
        return {"pv": pv, "duration": duration, "convexity": convexity}

    def hedge_solve(i):
        x, residual, objective = core.hedging.solve(
            i.matrix("a"), i.reals("b"), i.reals("weights"), i.reals("costs"), i.real("lambda"))
        return {"x": x, "residual": residual, "objective": objective}

    def spread_cost(i):
        return {"cost": core.hedging.spread_cost(i.reals("quantities"), i.reals("half_spreads"))}

    def fx_hedge(i):
        market = _market(i)
        book = [_forward_trade(t) for t in _objects(i, "book")]
        return core.usecases.fx_hedge(market, book, i.real("half_spread"))

    def rates_hedge(i):
        tenors = [_tenor(Inputs({"tenor": t})) for t in i.array("hedge_tenors")]
        return core.usecases.rates_hedge(
            i.date("as_of"), _quotes(i), i.enum("interpolation", curves.INTERPOLATIONS),
            _ois_trade(i), tenors, i.real("hedge_unit_notional"), i.real("half_spread_bp"),
        )

    return {
        "core.units.convert": convert,
        "core.units.add_money": add_money,
        "core.units.round_money": round_money,
        "core.conventions.lookup": lookup,
        "rates.schedule.generate": schedule,
        "rates.curve.discount": curve_discount,
        "rates.curve.forward": curve_forward,
        "rates.ois.bootstrap": bootstrap,
        "rates.ois.compound": compound,
        "rates.ois.pv": ois_pv,
        "rates.projection.bootstrap": projection_bootstrap,
        "rates.swap.pv": swap_pv,
        "rates.fra.pv": fra_pv,
        "rates.basis.spread": basis,
        "fx.spot_date": spot_date,
        "fx.forward.outright": outright,
        "fx.forward.pv": fx_pv,
        "fx.swap.pv": fx_swap,
        "fx.curve.implied": fx_implied,
        "calib.fit": fit,
        "calib.check_bid_ask": bid_ask,
        "calib.curve_report": curve_report,
        "risk.ois.dv01": dv01,
        "risk.cashflows": cashflows,
        "hedge.solve": hedge_solve,
        "hedge.spread_cost": spread_cost,
        "usecase.fx_hedge": fx_hedge,
        "usecase.rates_hedge": rates_hedge,
    }

