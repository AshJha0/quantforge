"""JSON reading with the contract's rules: no NaN, no duplicate keys, overflow reported."""
import json
import math
from typing import Any

from .errors import QfError


def parse(text: str) -> tuple[Any, bool]:
    """Returns (value, overflowed). Rejection is E_PARSE. An overflowing number is left for the
    caller, because a later syntax error must still win over it."""
    overflow = False

    def on_float(s: str) -> float:
        nonlocal overflow
        value = float(s)
        if math.isinf(value):
            overflow = True
        return value

    def on_int(s: str) -> int | float:
        nonlocal overflow
        value = float(s)
        if math.isinf(value):
            overflow = True
            return value
        return int(s)

    def on_constant(s: str) -> None:
        raise QfError("E_PARSE", f"{s} is not JSON")

    def on_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise QfError("E_PARSE", f"duplicate key {key!r}")
            result[key] = value
        return result

    try:
        value = json.loads(
            text,
            parse_float=on_float,
            parse_int=on_int,
            parse_constant=on_constant,
            object_pairs_hook=on_pairs,
        )
    except json.JSONDecodeError as e:
        raise QfError("E_PARSE", f"not valid JSON: {e}") from None
    except RecursionError:
        raise QfError("E_LIMIT", "nesting is too deep to read") from None
    return value, overflow
