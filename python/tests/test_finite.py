"""E1: NaN and infinity at every public numeric input are E_DOMAIN; -0.0 is a number like 0.0."""
import importlib
import inspect
import math
import pkgutil
from dataclasses import dataclass
from typing import Any, NamedTuple

import numpy as np
import pytest

import quantforge_core
from quantforge_core import black, finite
from quantforge_core.errors import QfError

BAD = (math.nan, math.inf, -math.inf)
# Modules with no public numeric entry points: data tables, the error type, the guard itself.
# strictjson parses text and takes no numeric input; it stays off the start-up path of `version`.
SKIP = {"errors", "finite", "strictjson", "_legendre_1024", "_sobol_data", "_cal"}


def _core_modules():
    for info in pkgutil.iter_modules(quantforge_core.__path__):
        if not info.ispkg and info.name not in SKIP:
            yield importlib.import_module(f"quantforge_core.{info.name}")


def _public_functions():
    for module in _core_modules():
        for name, f in vars(module).items():
            if (not name.startswith("_") and inspect.isfunction(f)
                    and getattr(f, "__module__", None) == module.__name__):
                yield module.__name__, name, f


PUBLIC = sorted(_public_functions(), key=lambda t: (t[0], t[1]))


def test_there_are_public_functions_to_check() -> None:
    assert len(PUBLIC) > 150


@pytest.mark.parametrize(("module", "name", "f"), PUBLIC, ids=[f"{m}.{n}" for m, n, _ in PUBLIC])
def test_every_public_function_is_guarded(module, name, f) -> None:
    assert hasattr(f, "__wrapped__"), f"{module}.{name} is not guarded"


@pytest.mark.parametrize(("module", "name", "f"), PUBLIC, ids=[f"{m}.{n}" for m, n, _ in PUBLIC])
def test_each_input_rejects_nan_and_infinity_first(module, name, f) -> None:
    params = [p for p in inspect.signature(f).parameters.values()
              if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
    for k, p in enumerate(params):
        for bad in BAD:
            args: list[object] = [None] * len(params)
            args[k] = bad
            with pytest.raises(QfError) as e:
                f(*args)
            assert (e.value.code, e.value.field) == ("E_DOMAIN", p.name)


def test_nested_values_are_walked() -> None:
    @dataclass
    class Box:
        x: float

    class Pair(NamedTuple):
        a: float
        b: float

    assert finite.is_bad([1.0, [2.0, (3.0, math.nan)]])
    assert finite.is_bad({"k": [math.inf]})
    assert finite.is_bad(Box(-math.inf))
    assert finite.is_bad(Pair(0.0, math.nan))
    assert finite.is_bad(np.array([1.0, math.nan]))
    assert finite.is_bad(np.float64(math.inf))
    assert finite.is_bad([("a", math.nan)])
    assert not finite.is_bad([1, 2**2000, "x", None, True, (0.0, -0.0)])
    assert not finite.is_bad(np.array([1, 2]))
    assert not finite.is_bad(np.array([0.0, -0.0]))
    assert not finite.is_bad({"k": 1.0e308})
    assert not finite.is_bad(Box)  # a class, not an instance
    assert not finite.is_bad(object())
    assert finite.bad_field(Pair(0.0, math.nan)) == "b"
    assert finite.bad_field({"k": [1.0, math.nan]}) == "k"
    assert finite.bad_field([Box(math.inf)]) == "x"
    assert finite.bad_field([1.0, math.nan]) == ""
    assert finite.bad_field([1.0, 2.0]) is None


def test_negative_zero_is_a_number() -> None:
    option = black.Option(black.BLACK_SCHOLES, "CALL", 100.0, 1.0, 100.0, 0.0, -0.0)
    assert black.price(option, 0.2) == black.price(
        black.Option(black.BLACK_SCHOLES, "CALL", 100.0, 1.0, 100.0, 0.0, 0.0), 0.2)


@pytest.mark.parametrize("bad", BAD)
def test_dataclass_input_field(bad) -> None:
    option = black.Option(black.BLACK_SCHOLES, "CALL", bad, 1.0, 100.0)
    with pytest.raises(QfError) as e:
        black.price(option, 0.2)
    assert (e.value.code, e.value.field) == ("E_DOMAIN", "strike")


def test_keyword_inputs_and_var_positional():
    def f(a, *rest, k=0.0):
        return a

    f.__module__ = "m"
    namespace: dict[str, Any] = {"__name__": "m", "f": f, "_private": f}
    finite.guard(namespace)
    g = namespace["f"]
    assert namespace["_private"] is f
    assert g(1.0, 2.0, k=3.0) == 1.0
    for call, field in ((lambda: g(math.nan), "a"), (lambda: g(1.0, math.inf), "rest"),
                        (lambda: g(1.0, k=-math.inf), "k")):
        with pytest.raises(QfError) as e:
            call()
        assert (e.value.code, e.value.field) == ("E_DOMAIN", field)


def test_inner_calls_are_not_checked_again():
    seen = []

    def inner(x):
        seen.append(x)
        return x

    def outer(x):
        return namespace["inner"](math.inf) + x

    inner.__module__ = outer.__module__ = "m"
    namespace: dict[str, Any] = {"__name__": "m", "inner": inner, "outer": outer}
    finite.guard(namespace)
    assert namespace["outer"](1.0) == math.inf
    assert seen == [math.inf]
    with pytest.raises(QfError):  # and the flag is cleared afterwards
        namespace["inner"](math.nan)


def test_flag_cleared_after_an_error() -> None:
    def boom(x) -> None:
        raise QfError("E_INPUT", "no")

    boom.__module__ = "m"
    namespace: dict[str, Any] = {"__name__": "m", "boom": boom}
    finite.guard(namespace)
    with pytest.raises(QfError):
        namespace["boom"](1.0)
    with pytest.raises(QfError) as e:
        namespace["boom"](math.nan)
    assert e.value.code == "E_DOMAIN"

