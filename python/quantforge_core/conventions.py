from dataclasses import dataclass
from datetime import date

@dataclass(frozen=True)
class YearFraction:
    value: float
    convention: str

def act_360(start: date, end: date) -> YearFraction:
    if end < start:
        raise ValueError("end date must not precede start date")
    return YearFraction((end - start).days / 360.0, "ACT/360")

def act_365f(start: date, end: date) -> YearFraction:
    if end < start:
        raise ValueError("end date must not precede start date")
    return YearFraction((end - start).days / 365.0, "ACT/365F")
