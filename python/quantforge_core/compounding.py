"""Discount factors and rate conversion (specifications/01-core/compounding.md)."""
import math
from dataclasses import dataclass

from .errors import QfError

FREQUENCIES = (1, 2, 3, 4, 6, 12)
KINDS = ("SIMPLE", "PERIODIC", "CONTINUOUS")


@dataclass(frozen=True)
class Compounding:
    kind: str
    frequency: int | None = None

    def validate(self) -> None:
        if self.kind not in KINDS:
            raise QfError("E_SCHEMA", f"unknown compounding {self.kind}", "compounding")
        if self.kind == "PERIODIC" and self.frequency is None:
            raise QfError("E_SCHEMA", "PERIODIC needs frequency", "frequency")
        if self.kind == "PERIODIC" and self.frequency not in FREQUENCIES:
            raise QfError("E_SCHEMA", f"frequency {self.frequency} is not listed", "frequency")


def _check_rate(rate: float, t: float, c: Compounding) -> None:
    if c.kind == "SIMPLE" and 1 + rate * t <= 0:
        raise QfError("E_DOMAIN", "1 + r t must be positive", "rate")
    if c.kind == "PERIODIC" and 1 + rate / c.frequency <= 0:
        raise QfError("E_DOMAIN", "1 + r/n must be positive", "rate")


def _discount(rate: float, t: float, c: Compounding) -> float:
    if c.kind == "SIMPLE":
        return 1 / (1 + rate * t)
    if c.kind == "PERIODIC":
        return (1 + rate / c.frequency) ** (-c.frequency * t)
    return math.exp(-rate * t)


def _rate(d: float, t: float, c: Compounding) -> float:
    if c.kind == "SIMPLE":
        return (1 / d - 1) / t
    if c.kind == "PERIODIC":
        n = c.frequency
        return n * (d ** (-1 / (n * t)) - 1)
    return -math.log(d) / t


def discount_factor(rate: float, t: float, c: Compounding) -> float:
    c.validate()
    if t < 0:
        raise QfError("E_DOMAIN", "t is negative", "t")
    _check_rate(rate, t, c)
    return 1.0 if t == 0 else _discount(rate, t, c)


def convert(rate: float, t: float, source: Compounding, target: Compounding) -> float:
    source.validate()
    target.validate()
    if t <= 0:
        raise QfError("E_DOMAIN", "t must be positive to define a rate", "t")
    _check_rate(rate, t, source)
    return _rate(_discount(rate, t, source), t, target)
