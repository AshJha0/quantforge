"""JSON reading with the contract's rules: no NaN, no duplicate keys, overflow reported."""
import json
import math
import re
from typing import Any

from .errors import QfError
from .finite import guard

_STRINGS = re.compile(r'"(?:[^"\\]|\\.)*"?', re.DOTALL)
_BRACKETS = re.compile(r"[\[\]{}]")


def check_depth(text: str, limit: int) -> None:
    """The lexical scan of limits.md B2: no syntax is checked, and strings are skipped.

    Strings are removed first, in C. A bracket never starts or ends a string, so these are the
    strings that one left-to-right scan of strings and brackets would skip."""
    if text.count("[") + text.count("{") <= limit:
        return  # the depth cannot exceed the number of openers
    depth = 0
    for ch in _BRACKETS.findall(_STRINGS.sub("", text)):
        if ch in "[{":
            depth += 1
            if depth > limit:
                raise QfError("E_LIMIT", f"nesting beyond {limit} levels")
        elif ch in "]}":
            depth -= 1


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
        if len(s) < 300:  # an integer below 10^299 cannot overflow binary64
            return int(s)
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
    return value, overflow


guard(globals())
