"""The operation registry. Each handler module registers its verbs with `op`; the verb table
(`quantforge operations`, OPERATIONS) is generated from REGISTRY, never written by hand.

Reading inputs is the E_SCHEMA stage, and the first call into the core ends it. So each core
module is reached through a gate, which applies limits.md at exactly that point."""
from collections.abc import Callable
from importlib import import_module
from types import FunctionType, ModuleType, SimpleNamespace
from typing import Any

from ..errors import QfError
from .inputs import NONFINITE, Inputs
from .limits import check_limits

Handler = Callable[[Inputs], Any]
REGISTRY: dict[str, Handler] = {}
CORE_MODULES = (
    "arb_surface", "black", "bonds", "calendars", "calibration", "caps_swaptions", "commodity",
    "compounding", "conventions", "correlation", "cos", "credit", "credit_options", "csa",
    "curve_fits", "curves", "data_checks", "daycount", "equity", "equity_curves", "exotics",
    "futures", "fx", "fx_smile", "hedging", "heston", "inflation", "integrate", "interp", "joint", "linalg", "book_risk", "var_risk", "book",
    "mbs", "money", "monte_carlo", "ois", "overnight", "pde", "projection", "rates_vol",
    "risk_curve", "rng", "roots", "sabr", "schedules", "shortrate", "mc_greeks", "lmm", "xva", "risk_tools", "aad_ladder", "sensitivities", "smile", "snapshot",
    "sobol", "stats", "steps", "store", "timezones", "usecases", "variance", "vol_usecase", "xccy",
)


def op(name: str) -> Callable[[Handler], Handler]:
    """Registers a handler for one verb; a verb registered twice is a bug."""
    def register(f: Handler) -> Handler:
        if name in REGISTRY:
            raise RuntimeError(f"{name} is registered twice")
        REGISTRY[name] = f
        return f

    return register


_pending: tuple[str, Inputs] | None = None


def _pass_gate() -> None:
    """Ends the E_SCHEMA stage: E_LIMIT, then the finite rule (F-2), then the core's own checks."""
    global _pending
    if _pending is not None:
        name, i = _pending
        _pending = None
        check_limits(name, i.raw)
        if NONFINITE:
            first = NONFINITE[0]
            raise QfError("E_DOMAIN", f"{first} is not finite", first)


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


core = SimpleNamespace(**{m: _Core(m) for m in CORE_MODULES})


# Stage G operations whose E_LIMIT sizes are checked on the raw document before the typed reads:
# two r5 goldens (shortrate_g-0082 without short_rate, mcgreeks_g-0022 with an integer seed)
# expect E_LIMIT although a field is malformed (SPEC_QUESTIONS G-Q3).
EARLY_LIMITS = frozenset({
    "rates.shortrate.zcb", "rates.shortrate.zcb_option", "rates.shortrate.swaption",
    "rates.shortrate.capfloor", "rates.shortrate.hw_calibrate",
    "rates.shortrate.bermudan_swaption", "rates.shortrate.callable_bond",
    "rates.shortrate.bermudan_ladder", "rates.g2pp.zcb", "rates.g2pp.zcb_option",
    "rates.lmm.capfloor", "rates.lmm.swaption_rebonato", "xva.exposure.swap_ee_hw",
    "risk.mc.greeks", "exotic.barrier.price",
})


def execute(operation: str, raw: dict[str, Any]) -> Any:
    global _pending
    NONFINITE.clear()
    if operation in EARLY_LIMITS:
        try:
            check_limits(operation, raw)
        except (TypeError, AttributeError, KeyError):
            pass  # a malformed field: the typed reads report it as E_SCHEMA
    i = Inputs(raw)
    _pending = (operation, i)
    result = REGISTRY[operation](i)
    _pass_gate()
    return result
