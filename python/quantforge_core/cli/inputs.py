"""Typed reading of a case's inputs. Everything here fails with E_SCHEMA."""
import re
from collections.abc import Mapping
from datetime import date
from typing import Any, overload

from ..errors import QfError
from ..timezones import DAY, date_seconds, to_date

Date = date  # Inputs.date shadows the type inside the class
_DATE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_TIME = r"(\d{2}):(\d{2}):(\d{2})"
_LOCAL = re.compile(r"(\d{4}-\d{2}-\d{2})T" + _TIME)
_INSTANT = re.compile(r"(\d{4}-\d{2}-\d{2})T" + _TIME + r"(Z|[+-]\d{2}:\d{2})")
_CUTOFF = re.compile(r"(\d{2}):(\d{2})")
_U64 = re.compile(r"[0-9]+")
MAX_INTEGER = 2**53
MAX_U64 = 2**64 - 1


def _bad(key: str, why: str) -> QfError:
    return QfError("E_SCHEMA", f"{key}: {why}", key)


def _is_real(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def parse_date(text: Any, key: str) -> date:
    m = _DATE.fullmatch(text) if isinstance(text, str) else None
    if m is None:
        raise _bad(key, "not a date")
    try:
        return date(int(m[1]), int(m[2]), int(m[3]))
    except ValueError:
        raise _bad(key, "not a date") from None


def _seconds_of_day(hour: str, minute: str, second: str, key: str) -> int:
    h, m, s = int(hour), int(minute), int(second)
    if h > 23 or m > 59 or s > 59:
        raise _bad(key, "not a time")
    return h * 3600 + m * 60 + s


def parse_instant(text: Any, key: str) -> int:
    m = _INSTANT.fullmatch(text) if isinstance(text, str) else None
    if m is None:
        raise _bad(key, "not an instant")
    seconds = date_seconds(parse_date(m[1], key)) + _seconds_of_day(m[2], m[3], m[4], key)
    zone = m[5]
    if zone == "Z":
        return seconds
    hours, minutes = int(zone[1:3]), int(zone[4:6])
    if hours > 23 or minutes > 59:
        raise _bad(key, "not an instant")
    offset = hours * 3600 + minutes * 60
    return seconds - offset if zone[0] == "+" else seconds + offset


def format_seconds(seconds: int, suffix: str = "") -> str:
    rest = seconds % DAY
    clock = f"{rest // 3600:02d}:{rest % 3600 // 60:02d}:{rest % 60:02d}"
    return f"{to_date(seconds).isoformat()}T{clock}{suffix}"


class Inputs:
    """A view of one JSON object. A null counts as absent."""

    def __init__(self, raw: Mapping[str, Any], prefix: str = ""):
        self.raw = raw
        self.prefix = prefix

    def has(self, key: str) -> bool:
        return self.raw.get(key) is not None

    def _get(self, key: str) -> Any:
        if not self.has(key):
            raise _bad(self.prefix + key, "missing")
        return self.raw[key]

    def real(self, key: str) -> float:
        v = self._get(key)
        if not _is_real(v):
            raise _bad(key, "not a number")
        return float(v)

    @overload
    def opt_real(self, key: str) -> float | None: ...
    @overload
    def opt_real(self, key: str, default: float) -> float: ...

    def opt_real(self, key: str, default: float | None = None) -> float | None:
        return self.real(key) if self.has(key) else default

    def integer(self, key: str) -> int:
        v = self._get(key)
        if isinstance(v, bool) or not isinstance(v, int) or abs(v) > MAX_INTEGER:
            raise _bad(key, "not an integer")
        return v

    @overload
    def opt_integer(self, key: str) -> int | None: ...
    @overload
    def opt_integer(self, key: str, default: int) -> int: ...

    def opt_integer(self, key: str, default: int | None = None) -> int | None:
        return self.integer(key) if self.has(key) else default

    def string(self, key: str) -> str:
        v = self._get(key)
        if not isinstance(v, str):
            raise _bad(key, "not a string")
        return v

    def opt_string(self, key: str) -> str | None:
        return self.string(key) if self.has(key) else None

    def boolean(self, key: str) -> bool:
        v = self._get(key)
        if not isinstance(v, bool):
            raise _bad(key, "not a boolean")
        return v

    def opt_boolean(self, key: str, default: bool) -> bool:
        return self.boolean(key) if self.has(key) else default

    def enum(self, key: str, allowed: tuple[str, ...]) -> str:
        v = self.string(key)
        if v not in allowed:
            raise _bad(key, f"{v} is not listed")
        return v

    def date(self, key: str) -> date:
        return parse_date(self._get(key), key)

    def opt_instant(self, key: str) -> int | None:
        return self.instant(key) if self.has(key) else None

    def opt_date(self, key: str) -> Date | None:
        return self.date(key) if self.has(key) else None

    def instant(self, key: str) -> int:
        return parse_instant(self._get(key), key)

    def local(self, key: str) -> int:
        text = self.string(key)
        m = _LOCAL.fullmatch(text)
        if m is None:
            raise _bad(key, "not a local time")
        return date_seconds(parse_date(m[1], key)) + _seconds_of_day(m[2], m[3], m[4], key)

    def cutoff(self, key: str) -> int:
        m = _CUTOFF.fullmatch(self.string(key))
        if m is None:
            raise _bad(key, "not HH:MM")
        return _seconds_of_day(m[1], m[2], "00", key)

    def u64(self, key: str) -> int:
        return parse_u64(self._get(key), key)

    def array(self, key: str) -> list[Any]:
        v = self._get(key)
        if not isinstance(v, list):
            raise _bad(key, "not an array")
        return v

    def reals(self, key: str) -> list[float]:
        v = self.array(key)
        if not all(_is_real(e) for e in v):
            raise _bad(key, "not an array of numbers")
        return [float(e) for e in v]

    def nullable_reals(self, key: str) -> list[float | None]:
        v = self.array(key)
        if not all(e is None or _is_real(e) for e in v):
            raise _bad(key, "not an array of numbers and nulls")
        return [None if e is None else float(e) for e in v]

    def dates(self, key: str) -> list[Date]:
        return [parse_date(e, key) for e in self.array(key)]

    def matrix(self, key: str) -> list[list[float]]:
        """Shape is not checked here: a ragged matrix is E_INPUT, for the operation to report."""
        rows = self.array(key)
        if not all(isinstance(r, list) and all(_is_real(e) for e in r) for r in rows):
            raise _bad(key, "not an array of rows of numbers")
        return [[float(e) for e in r] for r in rows]

    def object(self, key: str) -> Inputs:
        v = self._get(key)
        if not isinstance(v, dict):
            raise _bad(key, "not an object")
        return Inputs(v, f"{self.prefix}{key}.")


def parse_u64(text: Any, key: str) -> int:
    if not isinstance(text, str) or _U64.fullmatch(text) is None:
        raise _bad(key, "not a decimal u64 string")
    digits = text.lstrip("0")
    if len(digits) > 20 or int(digits or "0") > MAX_U64:
        raise _bad(key, "not a decimal u64 string")
    return int(digits or "0")
