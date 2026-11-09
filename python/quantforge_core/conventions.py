"""The convention registry (specifications/01-core/conventions.md)."""
from typing import Any

from .finite import guard

_MF = "MODIFIED_FOLLOWING"

REGISTRY: dict[str, dict[str, Any]] = {
    "SONIA": {
        "kind": "OVERNIGHT", "currency": "GBP", "day_count": "ACT_365F", "calendar": "GBLO",
        "spot_lag": 0, "payment_lag": 0, "fixed_months": 12, "fixed_day_count": "ACT_365F",
        "business_day_convention": _MF,
    },
    "SOFR": {
        "kind": "OVERNIGHT", "currency": "USD", "day_count": "ACT_360", "calendar": "USGS",
        "spot_lag": 2, "payment_lag": 2, "fixed_months": 12, "fixed_day_count": "ACT_360",
        "business_day_convention": _MF,
    },
    "ESTR": {
        "kind": "OVERNIGHT", "currency": "EUR", "day_count": "ACT_360", "calendar": "EUTA",
        "spot_lag": 2, "payment_lag": 2, "fixed_months": 12, "fixed_day_count": "ACT_360",
        "business_day_convention": _MF,
    },
    "USD-TERM-3M": {
        "kind": "TERM", "currency": "USD", "day_count": "ACT_360", "calendar": "USGS",
        "spot_lag": 2, "months": 3, "fixed_months": 12, "fixed_day_count": "THIRTY_360_BOND",
        "business_day_convention": _MF,
    },
    "GBPUSD": {
        "kind": "FX", "base": "GBP", "quote": "USD", "spot_lag": 2,
        "calendars": ["GBLO", "USGS"], "pip": 0.0001,
    },
    "EURUSD": {
        "kind": "FX", "base": "EUR", "quote": "USD", "spot_lag": 2,
        "calendars": ["EUTA", "USGS"], "pip": 0.0001,
    },
}
OVERNIGHT = tuple(k for k, v in REGISTRY.items() if v["kind"] == "OVERNIGHT")
TERM = tuple(k for k, v in REGISTRY.items() if v["kind"] == "TERM")
PAIRS = tuple(k for k, v in REGISTRY.items() if v["kind"] == "FX")


def lookup(convention_id: str) -> dict[str, Any]:
    return dict(REGISTRY[convention_id])


guard(globals())
