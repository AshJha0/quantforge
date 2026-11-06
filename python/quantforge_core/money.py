"""Units and exact money (specifications/01-core/units-and-money.md).

Amounts are held as integers in units of 1e-8, so no binary rounding can reach them.
"""
import re

from .errors import QfError

UNITS = {"DECIMAL": 1.0, "PERCENT": 100.0, "BP": 10000.0}
MINOR_UNITS = {"GBP": 2, "USD": 2, "EUR": 2, "JPY": 0}
AMOUNT_FORM = re.compile(r"-?[0-9]+(\.[0-9]+)?")
_PLACES = 8
_SCALE = 10**_PLACES


def convert(value: float, source: str, target: str) -> float:
    return value / UNITS[source] * UNITS[target]


def _parse(amount: str) -> int:
    negative = amount.startswith("-")
    whole, _, fraction = amount.lstrip("-").partition(".")
    if len(whole) > 18 or len(fraction) > _PLACES:
        raise QfError("E_LIMIT", "an amount has more digits than allowed", "amount")
    units = int(whole) * _SCALE + int(fraction.ljust(_PLACES, "0"))
    return -units if negative else units


def _format(units: int, places: int | None = None) -> str:
    sign = "-" if units < 0 else ""
    whole, fraction = divmod(abs(units), _SCALE)
    digits = f"{fraction:0{_PLACES}d}"
    digits = digits.rstrip("0") if places is None else digits[:places]
    return f"{sign}{whole}.{digits}" if digits else f"{sign}{whole}"


def add_money(a: str, a_currency: str, b: str, b_currency: str) -> tuple[str, str]:
    x, y = _parse(a), _parse(b)
    if a_currency != b_currency:
        raise QfError("E_CURRENCY_MISMATCH", f"{a_currency} and {b_currency} cannot be added")
    return _format(x + y), a_currency


def round_money(amount: str, currency: str) -> tuple[str, str]:
    units = _parse(amount)
    places = MINOR_UNITS[currency]
    step = 10 ** (_PLACES - places)
    quotient, remainder = divmod(abs(units), step)
    if remainder * 2 > step or (remainder * 2 == step and quotient % 2):
        quotient += 1
    rounded = quotient * step
    return _format(-rounded if units < 0 else rounded, places), currency
