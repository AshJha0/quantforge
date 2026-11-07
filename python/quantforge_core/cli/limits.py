"""Input limits (specifications/01-core/limits.md). Runs after every E_SCHEMA check has passed."""
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


_RNG = _caps(count=MAX_ARRAY, skip=MAX_SKIP)
_ROOT = _caps(max_iter=100_000)
_POINTS = _caps(n=10_000_000)
_LAGS = _caps(max_lag=1000)

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
    "vol.sabr.arbfree": _caps(cells=20_000, steps=20_000),
}
STAGE_C_ARRAY = 100
STAGE_C_PREFIXES = ("eq.", "vol.", "risk.vol.")


def _check_arrays(raw: Raw) -> None:
    stack: list[Any] = [raw]
    while stack:
        item = stack.pop()
        if isinstance(item, list):
            if len(item) > MAX_ARRAY:
                raise _over("an array", MAX_ARRAY)
            stack.extend(v for v in item if isinstance(v, (list, dict)))
        elif isinstance(item, dict):
            stack.extend(v for v in item.values() if isinstance(v, (list, dict)))


def _check_curve_sizes(raw: Raw) -> None:
    stack: list[Any] = [raw]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            for key, value in item.items():
                if (
                    key in ("quotes", "pillars", "points")
                    and isinstance(value, list)
                    and len(value) > MAX_QUOTES
                ):
                    raise _over(key, MAX_QUOTES)
                if isinstance(value, dict):
                    stack.append(value)


def _check_stage_c(raw: Raw) -> None:
    """Rulings C10: 100 for any quote, strike, point, dividend or position list, and surface grid."""
    stack: list[Any] = [raw]
    while stack:
        item = stack.pop()
        if isinstance(item, list):
            if len(item) > STAGE_C_ARRAY:
                raise _over("an array", STAGE_C_ARRAY)
            stack.extend(v for v in item if isinstance(v, (list, dict)))
        elif isinstance(item, dict):
            stack.extend(
                v for k, v in item.items() if k != "pillars" and isinstance(v, (list, dict))
            )


def check_limits(operation: str, raw: Raw) -> None:
    _check_arrays(raw)
    _check_curve_sizes(raw)
    if operation.startswith(STAGE_C_PREFIXES) or operation == "usecase.vol_surface":
        _check_stage_c(raw)
    specific = _BY_OPERATION.get(operation)
    if specific is not None:
        specific(raw)
