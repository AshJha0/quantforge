"""One handler per operation. A handler reads its inputs, which is the E_SCHEMA stage, then calls
the core, which applies the rule checks in spec order. It returns (outputs, diagnostics)."""
from collections.abc import Callable
from datetime import date
from importlib import import_module
from types import FunctionType, ModuleType, SimpleNamespace
from typing import Any

from .. import compounding as compounding_module
from .. import cos as cos_module
from .. import data_checks as data_checks_module
from .. import roots as roots_module
from .. import store as store_module
from ..calendars import TENOR
from ..daycount import check_conditional
from ..errors import QfError
from ..snapshot import has_lone_surrogate
from .functions import real_function, root_function
from .inputs import Inputs, format_seconds, parse_instant, parse_u64
from .limits import check_limits
from .stage_b import handlers as _stage_b_handlers
from .stage_c import handlers as _stage_c_handlers
from .stage_d import handlers as _stage_d_handlers
from .stage_e import handlers as _stage_e_handlers

Result = dict[str, Any] | tuple[dict[str, Any], dict[str, Any]]
OPTIONS = ("CALL", "PUT")


# Reading inputs is the E_SCHEMA stage, and the first call into the core ends it. So each core
# module is reached through a gate, which applies limits.md at exactly that point.
_pending: tuple[str, Inputs] | None = None


def _pass_gate() -> None:
    global _pending
    if _pending is not None:
        name, i = _pending
        _pending = None
        check_limits(name, i.raw)


class _Core:
    """A gated core module, imported on first use so that start-up loads only what a stream needs."""

    def __init__(self, name: str):
        self._name = name
        self._loaded: ModuleType | None = None

    def __getattr__(self, name: str) -> Any:
        if self._loaded is None:
            self._loaded = import_module(f"quantforge_core.{self._name}")
        value = getattr(self._loaded, name)
        if not isinstance(value, FunctionType):
            return value

        def call(*args: Any, **kwargs: Any) -> Any:
            _pass_gate()
            return value(*args, **kwargs)

        return call


calendars = _Core("calendars")
compounding = _Core("compounding")
cos = _Core("cos")
data_checks = _Core("data_checks")
daycount = _Core("daycount")
integrate = _Core("integrate")
interp = _Core("interp")
linalg = _Core("linalg")
monte_carlo = _Core("monte_carlo")
pde = _Core("pde")
rng = _Core("rng")
roots = _Core("roots")
snapshot = _Core("snapshot")
sobol = _Core("sobol")
stats = _Core("stats")
store = _Core("store")
timezones = _Core("timezones")


_STAGE_B = SimpleNamespace(
    **{
        m: _Core(m)
        for m in (
            "calibration", "conventions", "curves", "fx", "hedging", "money", "ois", "projection",
            "schedules", "sensitivities", "usecases",
        )
    }
)


_STAGE_C = SimpleNamespace(
    **{m: _Core(m) for m in ("black", "equity", "sabr", "smile", "vol_usecase")}
)
_STAGE_D = SimpleNamespace(
    **{m: _Core(m)
       for m in ("bonds", "credit", "csa", "curve_fits", "equity_d", "futures", "inflation", "overnight", "risk_curve", "stage_d3", "steps", "xccy")}
)


def execute(operation: str, raw: dict[str, Any]) -> Result:
    global _pending
    i = Inputs(raw)
    _pending = (operation, i)
    result = OPERATIONS[operation](i)
    _pass_gate()
    return result


def _tenor(i: Inputs) -> str:
    tenor = i.string("tenor")
    if TENOR.fullmatch(tenor) is None:
        raise QfError("E_SCHEMA", f"bad tenor {tenor}", "tenor")
    return tenor


def _opt_calendar(i: Inputs) -> str | None:
    return i.enum("calendar", calendars.CALENDARS) if i.has("calendar") else None


def _iso(d: date) -> str:
    return d.isoformat()


def _year_fraction(i: Inputs) -> Result:
    convention = i.enum("convention", daycount.CONVENTIONS)
    start, end = i.date("start"), i.date("end")
    # Keys a convention does not use are ignored, however they are written (rulings G2, G6).
    used: dict[str, Any] = {}
    if convention in ("ACT_ACT_ICMA", "ACT_365L"):
        used["frequency"] = i.opt_integer("frequency")
    if convention == "ACT_ACT_ICMA":
        used["ref_start"], used["ref_end"] = i.opt_date("ref_start"), i.opt_date("ref_end")
    if convention == "THIRTY_E_360_ISDA":
        used["termination"] = i.opt_date("termination")
    if convention == "BUS_252":
        used["calendar"] = _opt_calendar(i)
    check_conditional(convention, **used)
    return {"year_fraction": daycount.year_fraction(convention, start, end, **used)}


def _is_business_day(i: Inputs) -> Result:
    return {"is_business_day": calendars.is_business_day(i.enum("calendar", calendars.CALENDARS), i.date("date"))}


def _holidays(i: Inputs) -> Result:
    days = calendars.holidays(i.enum("calendar", calendars.CALENDARS), i.integer("year"))
    return {"dates": [_iso(d) for d in days]}


def _adjust(i: Inputs) -> Result:
    d = calendars.adjust(i.enum("calendar", calendars.CALENDARS), i.date("date"), i.enum("convention", calendars.CONVENTIONS))
    return {"date": _iso(d)}


def _add_business_days(i: Inputs) -> Result:
    d = calendars.add_business_days(i.enum("calendar", calendars.CALENDARS), i.date("date"), i.integer("days"))
    return {"date": _iso(d)}


def _business_days_between(i: Inputs) -> Result:
    n = calendars.business_days_between(i.enum("calendar", calendars.CALENDARS), i.date("start"), i.date("end"))
    return {"count": n}


def _add_tenor(i: Inputs) -> Result:
    d = calendars.add_tenor(
        i.enum("calendar", calendars.CALENDARS), i.date("date"), _tenor(i),
        i.enum("convention", calendars.CONVENTIONS), i.boolean("end_of_month"),
    )
    return {"date": _iso(d)}


def _compounding(i: Inputs) -> compounding_module.Compounding:
    kind = i.string("compounding")
    c = compounding.Compounding(kind, i.opt_integer("frequency") if kind == "PERIODIC" else None)
    c.validate()
    return c


def _discount_factor(i: Inputs) -> Result:
    rate, t = i.real("rate"), i.real("t")
    return {"discount_factor": compounding.discount_factor(rate, t, _compounding(i))}


def _convert(i: Inputs) -> Result:
    rate, t = i.real("rate"), i.real("t")
    source, target = _compounding(i.object("from")), _compounding(i.object("to"))
    return {"rate": compounding.convert(rate, t, source, target)}


def _snapshot_hash(i: Inputs) -> Result:
    form, snapshot_id = snapshot.hash_document(i.string("document_text"))
    return {"canonical": form, "snapshot_id": snapshot_id}


def _draw_inputs(i: Inputs) -> tuple[int, int, int, int]:
    seed, stream, count = i.u64("seed"), i.integer("stream"), _count(i)
    skip = i.opt_integer("skip", 0)
    if not 0 <= stream <= 1023:
        raise QfError("E_SCHEMA", "stream must be 0 to 1023", "stream")
    if skip < 0:
        raise QfError("E_SCHEMA", "skip must not be negative", "skip")
    return seed, stream, count, skip


def _count(i: Inputs) -> int:
    count = i.integer("count")
    if count < 1:
        raise QfError("E_SCHEMA", "count must be at least 1", "count")
    return count


def _next_u64(i: Inputs) -> Result:
    return {"values": [str(v) for v in rng.next_u64(*_draw_inputs(i))]}


def _uniforms(i: Inputs) -> Result:
    return {"values": rng.uniforms(*_draw_inputs(i))}


def _normals(i: Inputs) -> Result:
    return {"values": rng.normals(*_draw_inputs(i))}


def _inverse_normal(i: Inputs) -> Result:
    return {"z": rng.inverse_normal(i.reals("p"))}


def _set_state(i: Inputs) -> Result:
    state = [parse_u64(s, "state") for s in i.array("state")]
    if len(state) != 4:
        raise QfError("E_SCHEMA", "state needs four words", "state")
    return {"values": [str(v) for v in rng.set_state_next_u64(state, _count(i))]}


def _sobol_points(i: Inputs) -> Result:
    points = sobol.points(i.integer("dimensions"), i.integer("count"), i.opt_integer("skip", 0))
    return {"points": points}


def _root_result(r: roots_module.RootResult) -> Result:
    diagnostics = {
        "iterations": r.iterations, "residual": r.residual, "termination": r.termination,
    }
    return {"root": r.root}, diagnostics


def _tolerances(i: Inputs) -> dict[str, Any]:
    return {
        "x_tol": i.opt_real("x_tol", 1e-12),
        "f_tol": i.opt_real("f_tol", 0.0),
        "max_iter": i.opt_integer("max_iter", 200),
    }


def _bisection(i: Inputs) -> Result:
    f, _ = root_function(i.string("function"))
    return _root_result(roots.bisection(f, i.real("a"), i.real("b"), **_tolerances(i)))


def _brent(i: Inputs) -> Result:
    f, _ = root_function(i.string("function"))
    return _root_result(roots.brent(f, i.real("a"), i.real("b"), **_tolerances(i)))


def _newton(i: Inputs) -> Result:
    f, df = root_function(i.string("function"))
    if i.has("a") != i.has("b"):
        raise QfError("E_SCHEMA", "a and b must both be given or both absent")
    return _root_result(
        roots.newton(f, df, i.real("x0"), i.opt_real("a"), i.opt_real("b"), **_tolerances(i))
    )


def _fixed_rule(rule: Callable[..., float]) -> Callable[[Inputs], Result]:
    def handler(i: Inputs) -> Result:
        f = real_function(i.string("function"))
        return {"value": rule(f, i.real("a"), i.real("b"), i.integer("n"))}

    return handler


def _adaptive_simpson(i: Inputs) -> Result:
    f = real_function(i.string("function"))
    value = integrate.adaptive_simpson(
        f, i.real("a"), i.real("b"), i.opt_real("tol", 1e-10), i.opt_integer("max_depth", 50)
    )
    return {"value": value}


def _gauss_kronrod(i: Inputs) -> Result:
    f = real_function(i.string("function"))
    value, error = integrate.gauss_kronrod(
        f, i.real("a"), i.real("b"), i.opt_real("tol", 1e-10), i.opt_integer("max_intervals", 500)
    )
    return {"value": value}, {"error_estimate": error}


def _interp_evaluate(i: Inputs) -> Result:
    method = i.enum("method", tuple(interp.MIN_KNOTS))
    x, y, at = i.reals("x"), i.reals("y"), i.reals("at")
    params: dict[str, float] = {}
    if method == "cubic_clamped":
        params = {"slope_start": i.real("slope_start"), "slope_end": i.real("slope_end")}
    elif method == "tension":
        params = {"tension": i.real("tension")}
    values, derivatives = interp.evaluate(method, x, y, at, **params)
    if derivatives is None:
        return {"values": values}
    return {"values": values, "derivatives": derivatives}


def _monotone_convex(i: Inputs) -> Result:
    forwards, zero_rates = interp.monotone_convex(
        i.reals("t"), i.reals("r"), i.reals("at"), i.opt_boolean("positive", False)
    )
    return {"forwards": forwards, "zero_rates": zero_rates}


def _diff_central(i: Inputs) -> Result:
    f = real_function(i.string("function"))
    x, h, order = i.real("x"), i.real("h"), i.integer("order")
    if order not in (1, 2):
        raise QfError("E_SCHEMA", "order must be 1 or 2", "order")
    _pass_gate()
    if h <= 0:
        raise QfError("E_INPUT", "need h > 0", "h")
    if order == 1:
        return {"value": (f(x + h) - f(x - h)) / (2 * h)}
    return {"value": (f(x + h) - 2 * f(x) + f(x - h)) / (h * h)}


def _solve(i: Inputs) -> Result:
    return {"x": linalg.solve(i.matrix("a"), i.reals("b"))}


def _cholesky(i: Inputs) -> Result:
    return {"l": linalg.cholesky(i.matrix("a"))}


def _eigen(i: Inputs) -> Result:
    return {"values": linalg.eigen_symmetric(i.matrix("a"))}


def _normal(i: Inputs) -> Result:
    pdf, cdf = stats.normal(i.reals("x"))
    return {"pdf": pdf, "cdf": cdf}


def _summary(i: Inputs) -> Result:
    return stats.summary(i.reals("x"))


def _quantile(i: Inputs) -> Result:
    return {"values": stats.quantile(i.reals("x"), i.reals("p"))}


def _covariance(i: Inputs) -> Result:
    cov, correlation = stats.covariance(i.reals("x"), i.reals("y"))
    return {"covariance": cov, "correlation": correlation}


def _ols(i: Inputs) -> Result:
    fit = stats.ols(i.reals("x"), i.reals("y"))
    return {
        "alpha": fit.alpha, "beta": fit.beta, "r_squared": fit.r_squared,
        "se_alpha": fit.se_alpha, "se_beta": fit.se_beta,
    }


def _returns(i: Inputs) -> Result:
    prices = i.reals("prices")
    return {"returns": stats.returns(prices, i.enum("kind", ("SIMPLE", "LOG")))}


def _rolling(i: Inputs) -> Result:
    x, window = i.reals("x"), i.integer("window")
    return {"values": stats.rolling(x, window, i.enum("statistic", ("MEAN", "STDEV")))}


def _ewma(i: Inputs) -> Result:
    return {"variance": stats.ewma_variance(i.reals("returns"), i.real("lambda"))}


def _acf(i: Inputs) -> Result:
    return {"acf": stats.autocorrelation(i.reals("x"), i.integer("max_lag"))}


def _ljung_box(i: Inputs) -> Result:
    return {"statistic": stats.ljung_box(i.reals("x"), i.integer("max_lag"))}


def _ar1(i: Inputs) -> Result:
    constant, phi, sigma = stats.ar1(i.reals("x"))
    return {"constant": constant, "phi": phi, "sigma": sigma}


def _resample_last(i: Inputs) -> Result:
    dates, values = i.dates("dates"), i.nullable_reals("values")
    kept_dates, kept_values = stats.resample_last(
        dates, values, i.enum("frequency", ("WEEK", "MONTH"))
    )
    return {"dates": [_iso(d) for d in kept_dates], "values": kept_values}


def _forward_fill(i: Inputs) -> Result:
    return {"values": stats.forward_fill(i.nullable_reals("values"), i.integer("limit"))}


def _pde(i: Inputs) -> Result:
    r = pde.bs_european(
        i.enum("option", OPTIONS), i.real("spot"), i.real("strike"), i.real("r"), i.real("q"),
        i.real("sigma"), i.real("t"), i.integer("space_steps"), i.integer("time_steps"),
        i.opt_real("width", 6.0), i.opt_integer("rannacher_steps", 2),
    )
    return {"price": r.price, "delta": r.delta, "gamma": r.gamma}, {"grid_h": r.grid_h}


def _monte_carlo(i: Inputs) -> Result:
    option = i.enum("option", OPTIONS)
    stream = i.opt_integer("stream", 0)
    if not 0 <= stream <= 1023:
        raise QfError("E_SCHEMA", "stream must be 0 to 1023", "stream")
    price, stderr = monte_carlo.gbm_european(
        option, i.real("spot"), i.real("strike"), i.real("r"), i.real("q"), i.real("sigma"),
        i.real("t"), i.integer("paths"), i.opt_integer("steps", 1), i.u64("seed"), stream,
        i.enum("method", monte_carlo.METHODS),
    )
    return {"price": price, "stderr": stderr}


def _cos_model(m: Inputs) -> cos_module.BlackScholes | cos_module.Heston:
    name = m.enum("name", ("BLACK_SCHOLES", "HESTON"))
    if name == "BLACK_SCHOLES":
        return cos.BlackScholes(m.real("sigma"))
    return cos.Heston(m.real("v0"), m.real("kappa"), m.real("theta"), m.real("sigma"), m.real("rho"))


def _cos(i: Inputs) -> Result:
    price, a, b = cos.european(
        i.enum("option", OPTIONS), i.real("spot"), i.real("strike"), i.real("r"), i.real("q"),
        i.real("t"), _cos_model(i.object("model")), i.integer("terms"), i.real("truncation"),
    )
    return {"price": price}, {"a": a, "b": b}


def _quote(raw: Any) -> data_checks_module.Quote:
    if not isinstance(raw, dict):
        raise QfError("E_SCHEMA", "a quote is not an object", "quotes")
    q = Inputs(raw, "quotes.")
    for key in ("bid", "ask"):
        if key not in raw:
            raise QfError("E_SCHEMA", f"a quote has no {key}", "quotes")
    return data_checks.Quote(
        q.string("instrument_id"), parse_instant(raw.get("event_time"), "event_time"),
        q.opt_real("bid"), q.opt_real("ask"), q.enum("quote_status", ("FIRM", "INDICATIVE")),
    )


def _check_quotes(i: Inputs) -> Result:
    history: dict[str, list[float]] = {}
    if i.has("history"):
        h = i.object("history")
        history = {key: h.reals(key) for key in h.raw}
    results = data_checks.check_quotes(
        i.instant("as_of"),
        [_quote(q) for q in i.array("quotes")],
        i.integer("stale_after_seconds"),
        i.opt_real("max_relative_spread"),
        i.opt_boolean("positive_only", False),
        i.opt_real("outlier_threshold", 5.0),
        i.opt_integer("outlier_min_history", 5),
        history,
    )
    return {"results": results}


def _record(raw: Any) -> store_module.Record:
    if not isinstance(raw, dict):
        raise QfError("E_SCHEMA", "a record is not an object", "records")
    r = Inputs(raw, "records.")
    if "value" not in raw:
        raise QfError("E_SCHEMA", "a record has no value", "records")
    sequence, series_id = r.integer("sequence"), r.string("series_id")
    if sequence < 1 or not series_id or has_lone_surrogate(raw):
        raise QfError("E_SCHEMA", "bad sequence, series_id or string in a record", "records")
    return store.Record(
        sequence, series_id, r.instant("event_time"), r.instant("knowledge_time"),
        raw["value"], r.opt_boolean("deleted", False), raw,
    )


def _records(i: Inputs) -> list[store_module.Record]:
    return [_record(r) for r in i.array("records")]


def _zulu(seconds: int) -> str:
    return format_seconds(seconds, "Z")


def _query_as_of(i: Inputs) -> Result:
    log, as_of = _records(i), i.instant("as_of")
    series_id = i.opt_string("series_id")
    event_from, event_to = i.opt_instant("event_from"), i.opt_instant("event_to")
    store.check_log(log, as_of, event_from, event_to)
    return {"rows": store.query_as_of(log, as_of, _zulu, series_id, event_from, event_to)}


def _latest(i: Inputs) -> Result:
    log, as_of, series_id = _records(i), i.instant("as_of"), i.string("series_id")
    store.check_log(log, as_of)
    return {"row": store.latest(log, as_of, series_id, _zulu)}


def _store_snapshot(i: Inputs) -> Result:
    log, as_of = _records(i), i.instant("as_of")
    store.check_log(log, as_of)
    form, snapshot_id, _ = store.snapshot(log, as_of, _zulu)
    return {"canonical": form, "snapshot_id": snapshot_id}


def _replay(i: Inputs) -> Result:
    log = _records(i)
    checkpoints = [parse_instant(c, "checkpoints") for c in i.array("checkpoints")]
    store.check_log(log, *checkpoints)
    snapshots, head = store.replay(log, checkpoints, _zulu)
    return {"snapshots": snapshots, "head": head}


def _chain(i: Inputs) -> Result:
    log = _records(i)
    store.check_log(log)
    hashes = store.chain(log)
    return {"head": hashes[-1] if hashes else store.GENESIS, "hashes": hashes}


def _utc_offset(i: Inputs) -> Result:
    return {"offset_seconds": timezones.utc_offset(i.enum("zone", timezones.ZONES), i.instant("instant"))}


def _to_local(i: Inputs) -> Result:
    return {"local": format_seconds(timezones.to_local(i.enum("zone", timezones.ZONES), i.instant("instant")))}


def _overlap(i: Inputs) -> str | None:
    return i.enum("overlap", ("EARLIER", "LATER")) if i.has("overlap") else None


def _to_instant(i: Inputs) -> Result:
    instant = timezones.to_instant(i.enum("zone", timezones.ZONES), i.local("local"), _overlap(i))
    return {"instant": format_seconds(instant, "Z")}


def _business_date(i: Inputs) -> Result:
    d = timezones.business_date(
        i.instant("instant"), i.enum("zone", timezones.ZONES), i.cutoff("cutoff"), i.enum("calendar", calendars.CALENDARS)
    )
    return {"date": _iso(d)}


OPERATIONS: dict[str, Callable[[Inputs], Result]] = {
    "core.daycount.year_fraction": _year_fraction,
    "core.calendar.is_business_day": _is_business_day,
    "core.calendar.holidays": _holidays,
    "core.calendar.adjust": _adjust,
    "core.calendar.add_business_days": _add_business_days,
    "core.calendar.business_days_between": _business_days_between,
    "core.calendar.add_tenor": _add_tenor,
    "core.compounding.discount_factor": _discount_factor,
    "core.compounding.convert": _convert,
    "core.snapshot.hash": _snapshot_hash,
    "core.rng.next_u64": _next_u64,
    "core.rng.uniforms": _uniforms,
    "core.rng.normals": _normals,
    "core.rng.inverse_normal": _inverse_normal,
    "core.rng.set_state_next_u64": _set_state,
    "core.sobol.points": _sobol_points,
    "core.root.bisection": _bisection,
    "core.root.brent": _brent,
    "core.root.newton": _newton,
    "core.integrate.trapezoid": _fixed_rule(integrate.trapezoid),
    "core.integrate.simpson": _fixed_rule(integrate.simpson),
    "core.integrate.gauss_legendre": _fixed_rule(integrate.gauss_legendre),
    "core.integrate.adaptive_simpson": _adaptive_simpson,
    "core.integrate.gauss_kronrod": _gauss_kronrod,
    "core.interp.evaluate": _interp_evaluate,
    "core.interp.monotone_convex": _monotone_convex,
    "core.diff.central": _diff_central,
    "core.linalg.solve": _solve,
    "core.linalg.cholesky": _cholesky,
    "core.linalg.eigen_symmetric": _eigen,
    "core.stats.normal": _normal,
    "core.stats.summary": _summary,
    "core.stats.quantile": _quantile,
    "core.stats.covariance": _covariance,
    "core.stats.ols": _ols,
    "core.ts.returns": _returns,
    "core.ts.rolling": _rolling,
    "core.ts.ewma_variance": _ewma,
    "core.ts.autocorrelation": _acf,
    "core.ts.ljung_box": _ljung_box,
    "core.ts.ar1": _ar1,
    "core.ts.resample_last": _resample_last,
    "core.ts.forward_fill": _forward_fill,
    "core.pde.bs_european": _pde,
    "core.mc.gbm_european": _monte_carlo,
    "core.cos.european": _cos,
    "core.data.check_quotes": _check_quotes,
    "core.store.query_as_of": _query_as_of,
    "core.store.latest": _latest,
    "core.store.snapshot": _store_snapshot,
    "core.store.replay": _replay,
    "core.store.chain": _chain,
    "core.time.utc_offset": _utc_offset,
    "core.time.to_local": _to_local,
    "core.time.to_instant": _to_instant,
    "core.time.business_date": _business_date,
}
OPERATIONS.update(_stage_b_handlers(_STAGE_B))
OPERATIONS.update(_stage_c_handlers(_STAGE_C))
OPERATIONS.update(_stage_d_handlers(_STAGE_D))
OPERATIONS.update(_stage_e_handlers(SimpleNamespace(**{m: _Core(m) for m in ("correlation", "exotics", "fx_smile", "heston", "rates_vol", "vol_e1", "vol_e7")})))
