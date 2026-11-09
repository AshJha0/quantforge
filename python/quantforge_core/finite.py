"""Every public numeric input must be finite (review item E1): NaN, +inf and -inf are E_DOMAIN,
-0.0 is accepted like 0.0.

`guard(globals())` at the end of a core module wraps its public functions. The check walks floats,
lists, tuples (named tuples too), dicts, dataclasses and NumPy float arrays. It runs once, at the
outermost public call: calls between core functions are not checked again, because intermediate
values are the core's own (an intermediate infinity is still E_NON_FINITE at the output, as the
CLI contract says). Over the CLI an input cannot be NaN or infinite, so results there do not change.
"""
import functools
import threading
from collections.abc import Callable
from math import isfinite
from types import FunctionType
from typing import Any

from .errors import QfError


class _State(threading.local):
    inside = False  # True inside an outer public call, per thread


_state = _State()


def bad_field(value: Any) -> str | None:
    """None when `value` is finite throughout; otherwise the innermost named field (a dataclass
    field or a dict key) that holds a NaN or an infinity, or "" when there is no such name."""
    t = type(value)
    if t is float:
        return None if isfinite(value) else ""
    if t is int or t is str or t is bool or value is None:
        return None
    if isinstance(value, (list, tuple)):
        try:
            if all(map(isfinite, value)):
                return None
            if not hasattr(value, "_fields"):
                return ""
        except (TypeError, OverflowError):
            pass
        names = getattr(value, "_fields", None) or ("",) * len(value)
        for name, item in zip(names, value, strict=True):
            found = bad_field(item)
            if found is not None:
                return found or name
        return None
    if isinstance(value, float):  # a float subclass
        return None if isfinite(value) else ""
    if isinstance(value, dict):
        for key, item in value.items():
            found = bad_field(item)
            if found is not None:
                return found or str(key)
        return None
    names = getattr(value, "__dataclass_fields__", None)  # no dataclasses import at start-up
    if names is not None and not isinstance(value, type):
        for name in names:
            found = bad_field(getattr(value, name))
            if found is not None:
                return found or name
        return None
    dtype = getattr(value, "dtype", None)
    if dtype is not None and getattr(dtype, "kind", "") in "fc":
        import numpy as np

        return None if bool(np.isfinite(value).all()) else ""
    return None


def is_bad(value: Any) -> bool:
    """True when `value` holds a NaN or an infinity anywhere a number can sit."""
    return bad_field(value) is not None


def _domain(name: str) -> QfError:
    return QfError("E_DOMAIN", f"{name} must be finite", name)


def _wrap[**P, R](f: Callable[P, R]) -> Callable[P, R]:
    # From the code object rather than inspect.signature: inspect costs start-up on every process.
    code = f.__code__
    positional = list(code.co_varnames[:code.co_argcount])
    rest = code.co_varnames[code.co_argcount + code.co_kwonlyargcount] if code.co_flags & 4 else "args"

    @functools.wraps(f)
    def checked(*args: P.args, **kwargs: P.kwargs) -> R:
        if _state.inside:
            return f(*args, **kwargs)
        for k, a in enumerate(args):
            found = bad_field(a)
            if found is not None:
                raise _domain(found or (positional[k] if k < len(positional) else rest))
        for key, a in kwargs.items():
            found = bad_field(a)
            if found is not None:
                raise _domain(found or key)
        _state.inside = True
        try:
            return f(*args, **kwargs)
        finally:
            _state.inside = False

    return checked


def guard(namespace: dict[str, Any]) -> None:
    """Wraps every public function defined in the module whose globals are `namespace`."""
    module = namespace["__name__"]
    for name, value in list(namespace.items()):
        if (not name.startswith("_") and isinstance(value, FunctionType)
                and value.__module__ == module):
            namespace[name] = _wrap(value)

