"""Input limits (specifications/01-core/limits.md). Runs after every E_SCHEMA check has passed."""
import math
from collections.abc import Callable, Mapping
from typing import Any

from ..errors import QfError
from ..snapshot import MAX_DEPTH, nesting_depth

Raw = Mapping[str, Any]
MAX_ARRAY = 100_000
MAX_MATRIX_ROWS = 200
MAX_TEXT_BYTES = 1_048_576
MAX_SKIP = 10_000_000
MAX_QUOTES = 100


def _over(key: str, limit: int) -> QfError:
    return QfError("E_LIMIT", f"{key} is above its limit of {limit}", key)


def _size(raw: Raw, key: str, default: int = 0) -> int:
    """An integer input, or the default. Values below a minimum are left to the rule checks."""
    value = raw.get(key)
    return default if value is None else value


def _cap(raw: Raw, key: str, limit: int) -> None:
    if _size(raw, key) > limit:
        raise _over(key, limit)


def _cap_product(raw: Raw, a: str, b: str, limit: int, default_b: int = 0) -> None:
    x, y = _size(raw, a), _size(raw, b, default_b)
    if x > 0 and y > 0 and x * y > limit:
        raise _over(f"{a} x {b}", limit)


def _caps(**limits: int) -> Callable[[Raw], None]:
    def check(raw: Raw) -> None:
        for key, limit in limits.items():
            _cap(raw, key, limit)

    return check


def _matrix(raw: Raw) -> None:
    if len(raw["a"]) > MAX_MATRIX_ROWS:
        raise _over("a", MAX_MATRIX_ROWS)


def _sobol(raw: Raw) -> None:
    _cap_product(raw, "count", "dimensions", MAX_ARRAY)
    _cap(raw, "skip", MAX_SKIP)


def _text(raw: Raw) -> None:
    if len(raw["document_text"].encode("utf-8", "surrogatepass")) > MAX_TEXT_BYTES:
        raise _over("document_text", MAX_TEXT_BYTES)


def _add_business_days(raw: Raw) -> None:
    if abs(raw["days"]) > 30_000:
        raise _over("days", 30_000)


def _record_depth(raw: Raw) -> None:
    for record in raw["records"]:
        if any(nesting_depth(v) > MAX_DEPTH for v in record.values()):
            raise _over("records", MAX_DEPTH)


def _replay(raw: Raw) -> None:
    _record_depth(raw)
    count = len(raw["checkpoints"])
    if count > 1000:
        raise _over("checkpoints", 1000)
    if count * len(raw["records"]) > 10_000_000:
        raise _over("records x checkpoints", 10_000_000)


def _start_length(raw: Raw) -> None:
    if len(raw["start"]) > 20:
        raise _over("start", 20)
    _cap(raw, "max_iter", 100_000)


def _hedge_tenors(raw: Raw) -> None:
    if len(raw["hedge_tenors"]) > 20:
        raise _over("hedge_tenors", 20)


def _hedge(raw: Raw) -> None:
    if any(len(row) > 20 for row in raw["a"]):
        raise _over("a", 20)


def _rows_cols(key: str, rows: int, cols: int) -> Callable[[Raw], None]:
    """A matrix input of at most `rows` rows of at most `cols` entries."""
    def check(raw: Raw) -> None:
        value = raw.get(key)
        if isinstance(value, list):
            if len(value) > rows:
                raise _over(key, rows)
            if any(isinstance(r, list) and len(r) > cols for r in value):
                raise _over(key, cols)

    return check


def _all(*checks: Callable[[Raw], None]) -> Callable[[Raw], None]:
    def check(raw: Raw) -> None:
        for c in checks:
            c(raw)

    return check


_RNG = _caps(count=MAX_ARRAY, skip=MAX_SKIP)
_ROOT = _caps(max_iter=100_000)
_POINTS = _caps(n=10_000_000)
_LAGS = _caps(max_lag=1000)

def _caps_list(key: str, limit: int) -> Callable[[Raw], None]:
    def check(raw: Raw) -> None:
        value = raw.get(key)
        if isinstance(value, list) and len(value) > limit:
            raise _over(key, limit)

    return check


def _fd_grid(raw: Raw) -> None:
    grid = raw.get("grid")
    if isinstance(grid, dict):
        _cap(grid, "nx", 1001)
        _cap(grid, "nt", 10_000)


def _scheme_grid(raw: Raw) -> None:
    """The G-18 scheme grid: nx at most 10,001, steps_per_year at most 100,000."""
    grid = raw.get("grid")
    if not isinstance(grid, dict):
        return
    _cap(grid, "nx", 10_001)
    _cap(grid, "steps_per_year", 100_000)
    # G-31: combined grid work nx x total steps <= 5e8, total steps summed over the knot
    # intervals exactly as the scheme counts them.
    knots = raw.get("exercise_times") or raw.get("payment_times") or []
    nx, spy = grid.get("nx"), grid.get("steps_per_year")
    if isinstance(nx, int) and isinstance(spy, int) and nx > 0 and spy > 0:
        total, prev = 0, 0.0
        for t in knots:
            if isinstance(t, (int, float)) and not isinstance(t, bool) and t > prev:
                total += max(1, math.ceil(spy * (t - prev)))
                prev = t
        if nx * total > 500_000_000:
            raise _over("nx x total time steps", 500_000_000)


def _slv_grid(raw: Raw) -> None:
    grid = raw.get("grid")
    if isinstance(grid, dict):
        for key, limit in (("nx", 1000), ("nv", 1000), ("nt", 10_000)):
            _cap(grid, key, limit)


# Ruling I-4: factors 1,000, instruments 200, equality rows 200, integer instruments 12, series
# 100,000 (the generic array cap), portfolio positions 1,000, Greek hedge instruments 3.
_I_FACTORS, _I_INSTRUMENTS = 1000, 200
_HEDGE_QP = _all(_rows_cols("a", _I_FACTORS, _I_INSTRUMENTS),
                 _rows_cols("eq_matrix", _I_INSTRUMENTS, _I_INSTRUMENTS))
_HEDGE_INTEGER = _all(_rows_cols("a", _I_FACTORS, 12), _caps_list("lot_sizes", 12))
_HEDGE_MINVAR = _all(_rows_cols("covariance", _I_INSTRUMENTS + 1, _I_INSTRUMENTS + 1),
                     _rows_cols("hedge_changes", _I_INSTRUMENTS, MAX_ARRAY))
_HEDGE_GREEKS = _all(_caps_list("portfolio", 1000), _caps_list("hedges", 3))
# Ruling I-19: credit book 1,000 trades and 50 hedges; correlation book 1,000 and 5 hedges.
_HEDGE_CREDIT = _all(_caps_list("book", 1000), _caps_list("hedges", 50))
_HEDGE_CORRELATION = _all(_caps_list("book", 1000), _caps_list("hedges", 5))
# Ruling I-23: cross-asset book 1,000 positions, hedges 200, curve pillars 100.
def _crossasset_curve(raw: Raw) -> None:
    curve = raw.get("curve")
    if isinstance(curve, dict):
        _caps_list("times", 100)(curve)
        _caps_list("zero_rates", 100)(curve)


_HEDGE_CROSSASSET = _all(_caps_list("book", 1000), _caps_list("hedges", 200), _crossasset_curve)
_HEDGE_RESIDUAL = _all(_rows_cols("a", _I_FACTORS, _I_INSTRUMENTS),
                       _rows_cols("covariance", _I_FACTORS, _I_FACTORS))

_BY_OPERATION: dict[str, Callable[[Raw], None]] = {
    "core.integrate.trapezoid": _POINTS,
    "core.integrate.simpson": _POINTS,
    "core.integrate.adaptive_simpson": _caps(max_depth=60),
    "core.integrate.gauss_kronrod": _caps(max_intervals=10_000),
    "core.root.bisection": _ROOT,
    "core.root.brent": _ROOT,
    "core.root.newton": _ROOT,
    "core.rng.next_u64": _RNG,
    "core.rng.uniforms": _RNG,
    "core.rng.normals": _RNG,
    "core.rng.set_state_next_u64": _RNG,
    "core.sobol.points": _sobol,
    "core.mc.gbm_european": lambda r: _cap_product(r, "paths", "steps", 1_000_000, 1),
    "core.pde.bs_european": lambda r: _cap_product(
        r, "space_steps", "time_steps", 10_000_000
    ),
    "core.cos.european": _caps(terms=100_000),
    "core.calendar.add_business_days": _add_business_days,
    "core.ts.rolling": _caps(window=1000),
    "core.ts.autocorrelation": _LAGS,
    "core.ts.ljung_box": _LAGS,
    "core.linalg.solve": _matrix,
    "core.linalg.cholesky": _matrix,
    "core.linalg.eigen_symmetric": _matrix,
    "core.snapshot.hash": _text,
    "core.store.query_as_of": _record_depth,
    "core.store.latest": _record_depth,
    "core.store.snapshot": _record_depth,
    "core.store.chain": _record_depth,
    "core.store.replay": _replay,
    "calib.fit": _start_length,
    "hedge.solve": _hedge,
    "rates.schedule.generate": _caps(payment_lag=30_000),
    "usecase.rates_hedge": _hedge_tenors,
    "vol.slv.leverage": _slv_grid,
    "vol.volofvol.measure": _caps_list("vols", 10_000),
    "exotic.american.crr": _caps(steps=20_000),
    "exotic.american.fd": _fd_grid,
    "vol.sabr.arbfree": _caps(cells=20_000, steps=20_000),
    "risk.var.monte_carlo": _caps(paths=10_000_000),
    # Stage G (ruling G-6 and the operation specs).
    "exotic.barrier.price": _caps(monitoring_per_year=1_000_000),
    "risk.mc.greeks": _caps(paths=10_000_000),
    "rates.shortrate.bermudan_swaption": _scheme_grid,
    "rates.shortrate.callable_bond": _scheme_grid,
    "rates.shortrate.bermudan_ladder": _scheme_grid,
    # Stage I wave 1 (ruling I-4).
    "hedge.qp.solve": _HEDGE_QP,
    "hedge.integer.solve": _HEDGE_INTEGER,
    "hedge.minvar.ratio": _HEDGE_MINVAR,
    "hedge.greeks.neutralise": _HEDGE_GREEKS,
    "hedge.residual.report": _HEDGE_RESIDUAL,
    "hedge.credit.cds": _HEDGE_CREDIT,
    "hedge.correlation.neutralise": _HEDGE_CORRELATION,
    "hedge.crossasset.solve": _HEDGE_CROSSASSET,
    "hedge.frontier.solve": _all(_HEDGE_QP, _caps_list("cost_weights", 50)),
    # Ruling I-35: selection over at most 20 instruments. I-32 (paths and series of 100,000)
    # is the generic array cap.
    "hedge.select.solve": _rows_cols("a", _I_FACTORS, 20),
}
OPTION_ARRAY = 100
OPTION_PREFIXES = ("eq.", "vol.", "risk.vol.")
# Stage E spec B (cli-contract): their arrays (returns, prices, strip) count like any array, so
# the stage C cap of 100 does not reach them.
SERIES_PREFIXES = ("vol.garch.", "vol.varswap.", "vol.vix.")
# Stage E spec A, E1: slices at most 100, grids and points at most 10,000 (arb-free-surfaces.md,
# local-and-forward-vol.md), in place of the stage C cap.
SURFACE_GRIDS = {"vol.svi.surface_check": "log_moneyness", "vol.svi.fit_surface": "log_moneyness",
                   "vol.local.dupire": "points"}


# Ruling F-42: stage F sizes. key -> limit on that array's length, wherever the key appears; these
# keys are exempt from the generic MAX_ARRAY. "#rows"/"#cols" name the shape of a matrix key.
STAGE_F_ARRAYS: dict[str, dict[str, int]] = {
    "risk.book.ois_sensitivity": {"swaps": 10_000},
    "risk.curve.pca": {"changes": 100_000, "changes#cols": 200},
    "risk.var.historical": {"pnl": 1_000_000},
    "risk.var.filtered_historical": {"returns": 1_000_000},
    "risk.var.monte_carlo": {"mean": 100, "weights": 100, "covariance": 100},
    "risk.backtest.christoffersen": {"exceptions": 1_000_000},
    "risk.frtb.girr_delta": {"sensitivities": 100_000},
    "book.lifecycle.apply": {"events": 1_000_000, "positions": 100_000},
    "book.marks.resolve": {"instruments": 100_000, "quotes": 1_000_000},
    "usecase.factor_attribution": {"portfolio_returns": 100_000, "factor_returns": 100_000,
                                   "factor_names": 50, "factor_returns#cols": 50},
}


# Stage G sizes (ruling G-6 and the operation specs): curve pillars, payment, exposure and
# period times 10,000 each, wherever the key appears.
_G_TIMES = {"times": 10_000, "discount_factors": 10_000, "payment_times": 10_000,
            "period_times": 10_000, "swaptions": 10_000}
for _name in ("rates.shortrate.zcb", "rates.shortrate.zcb_option", "rates.shortrate.swaption",
              "rates.shortrate.capfloor", "rates.shortrate.hw_calibrate",
              "rates.shortrate.bermudan_swaption", "rates.shortrate.callable_bond",
              "rates.shortrate.bermudan_ladder", "rates.lmm.capfloor",
              "rates.lmm.swaption_rebonato", "rates.g2pp.zcb", "rates.g2pp.zcb_option"):
    STAGE_F_ARRAYS[_name] = dict(_G_TIMES)
STAGE_F_ARRAYS["xva.exposure.swap_ee_hw"] = {**_G_TIMES, "exposure_times": 10_000}
STAGE_F_ARRAYS["xva.exposure.portfolio_hw"] = {**_G_TIMES, "exposure_times": 10_000}


def _check_stage_f(raw: Raw, limits: Mapping[str, int]) -> None:
    stack: list[Any] = [raw]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            for key, value in item.items():
                if isinstance(value, list) and key in limits and len(value) > limits[key]:
                    raise _over(key, limits[key])
                cols = limits.get(f"{key}#cols")
                if cols is not None and isinstance(value, list) and any(
                        isinstance(r, list) and len(r) > cols for r in value):
                    raise _over(key, cols)
                if isinstance(value, (list, dict)):
                    stack.append(value)
        elif isinstance(item, list):
            stack.extend(v for v in item if isinstance(v, (list, dict)))


def _check_arrays(raw: Raw, exempt: Mapping[str, int] | None = None) -> None:
    stack: list[Any] = [raw]
    while stack:
        item = stack.pop()
        if isinstance(item, list):
            if len(item) > MAX_ARRAY:
                raise _over("an array", MAX_ARRAY)
            stack.extend(v for v in item if isinstance(v, (list, dict)))
        elif isinstance(item, dict):
            for key, value in item.items():
                if exempt and key in exempt and isinstance(value, list):
                    stack.extend(v for v in value if isinstance(v, (list, dict)))
                elif isinstance(value, (list, dict)):
                    stack.append(value)


def _check_curve_sizes(raw: Raw) -> None:
    stack: list[Any] = [raw]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            for key, value in item.items():
                if (
                    key in ("quotes", "pillars", "points", "ois_quotes", "term_quotes")
                    and isinstance(value, list)
                    and len(value) > MAX_QUOTES
                ):
                    raise _over(key, MAX_QUOTES)
                if isinstance(value, dict):
                    stack.append(value)


def _check_option_arrays(raw: Raw) -> None:
    """Rulings C10: 100 for any quote, strike, point, dividend or position list, and surface grid."""
    stack: list[Any] = [raw]
    while stack:
        item = stack.pop()
        if isinstance(item, list):
            if len(item) > OPTION_ARRAY:
                raise _over("an array", OPTION_ARRAY)
            stack.extend(v for v in item if isinstance(v, (list, dict)))
        elif isinstance(item, dict):
            stack.extend(
                v for k, v in item.items() if k != "pillars" and isinstance(v, (list, dict))
            )


def _check_surface_grid(raw: Raw, grid: str) -> None:
    for key, limit in (("slices", 100), ("expiry_years", 100), (grid, 10_000)):
        value = raw.get(key)
        if isinstance(value, list) and len(value) > limit:
            raise _over(key, limit)


def check_limits(operation: str, raw: Raw) -> None:
    stage_f = STAGE_F_ARRAYS.get(operation)
    _check_arrays(raw, stage_f)
    if stage_f is not None:
        _check_stage_f(raw, stage_f)
    if operation != "book.marks.resolve":  # its quotes are marks, not curve quotes
        _check_curve_sizes(raw)
    grid = SURFACE_GRIDS.get(operation)
    if grid is not None:
        _check_surface_grid(raw, grid)
    options = (operation.startswith(OPTION_PREFIXES) and grid is None
               and operation != "vol.volofvol.measure"  # ruling E-A35: 10,000
               and not operation.startswith(SERIES_PREFIXES))
    if options or operation == "usecase.vol_surface":
        _check_option_arrays(raw)
    specific = _BY_OPERATION.get(operation)
    if specific is not None:
        specific(raw)
