"""The test function registry (specifications/01-core/test-functions.md). CLI layer only."""
import math
from collections.abc import Callable

from ..errors import QfError

Fn = Callable[[float], float]
_INV_SQRT_2PI = 1 / math.sqrt(2 * math.pi)


def _big_n(x: float) -> float:
    return math.erfc(-x / math.sqrt(2)) / 2


def _d1(x: float) -> float:
    return (math.log(100 / 100) + (0.01 + x * x / 2) * 1) / (x * math.sqrt(1))


def _bs_vol_atm(x: float) -> float:
    d1 = _d1(x)
    d2 = d1 - x * math.sqrt(1)
    return 100 * _big_n(d1) - 100 * math.exp(-0.01 * 1) * _big_n(d2) - 10


def _bs_vega(x: float) -> float:
    d1 = _d1(x)
    return 100 * (math.exp(-d1 * d1 / 2) * _INV_SQRT_2PI) * math.sqrt(1)


ROOT_FUNCTIONS: dict[str, tuple[Fn, Fn]] = {
    "cubic_wallis": (lambda x: x**3 - 2 * x - 5, lambda x: 3 * x**2 - 2),
    "cos_minus_x": (lambda x: math.cos(x) - x, lambda x: -math.sin(x) - 1),
    "exp_minus_two": (lambda x: math.exp(x) - 2, math.exp),
    "triple_root": (lambda x: (x - 1) ** 3, lambda x: 3 * (x - 1) ** 2),
    "square": (lambda x: x**2, lambda x: 2 * x),
    "no_real_root": (lambda x: x**2 + 1, lambda x: 2 * x),
    "steep_atan": (
        lambda x: math.atan(1000 * (x - 0.3)),
        lambda x: 1000 / (1 + 10**6 * (x - 0.3) ** 2),
    ),
    "bs_vol_atm": (_bs_vol_atm, _bs_vega),
}

REAL_FUNCTIONS: dict[str, Fn] = {
    "exp": math.exp,
    "sin": math.sin,
    "runge": lambda x: 1 / (1 + 25 * x**2),
    "sqrt": math.sqrt,
    "inv_sqrt": lambda x: 1 / math.sqrt(x),
    "normal_pdf": lambda x: math.exp(-(x**2) / 2) / math.sqrt(2 * math.pi),
    "oscillatory": lambda x: math.cos(50 * x) * math.exp(-x),
    "poly5": lambda x: x**5 - 3 * x**2 + 1,
}


def root_function(name: str) -> tuple[Fn, Fn]:
    if name not in ROOT_FUNCTIONS:
        raise QfError("E_SCHEMA", f"unknown function {name}", "function")
    return ROOT_FUNCTIONS[name]


def real_function(name: str) -> Fn:
    if name not in REAL_FUNCTIONS:
        raise QfError("E_SCHEMA", f"unknown function {name}", "function")
    return REAL_FUNCTIONS[name]
