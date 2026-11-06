"""Market-data checks (specifications/01-core/data-checks.md)."""
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .errors import QfError


@dataclass(frozen=True)
class Quote:
    instrument_id: str
    event_time: int
    bid: float | None
    ask: float | None
    quote_status: str


def _median(values: Sequence[float]) -> float:
    s = sorted(values)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def _is_outlier(mid: float, history: Sequence[float], threshold: float) -> bool:
    med = _median(history)
    mad = _median([abs(h - med) for h in history])
    return mad != 0 and abs(mid - med) / (1.4826 * mad) > threshold


def _check_one(
    q: Quote,
    as_of: int,
    stale_after: int,
    max_spread: float | None,
    positive_only: bool,
    threshold: float,
    min_history: int,
    history: Mapping[str, Sequence[float]],
) -> dict[str, object]:
    non_positive = positive_only and any(s is not None and s <= 0 for s in (q.bid, q.ask))
    if q.bid is None or q.ask is None:
        flags = []
        if q.bid is None:
            flags.append("MISSING_BID")
        if q.ask is None:
            flags.append("MISSING_ASK")
        if non_positive:
            flags.append("NON_POSITIVE")
        return {"instrument_id": q.instrument_id, "quote_status": "MISSING",
                "quality_flags": flags}

    crossed = q.bid > q.ask
    stale = as_of - q.event_time > stale_after
    mid = (q.bid + q.ask) / 2
    past = history.get(q.instrument_id, ())
    flags = []
    if crossed:
        flags.append("CROSSED")
    if q.bid == q.ask:
        flags.append("LOCKED")
    if stale:
        flags.append("STALE")
    if (
        max_spread is not None and not crossed and mid != 0
        and (q.ask - q.bid) / abs(mid) > max_spread
    ):
        flags.append("WIDE_SPREAD")
    if non_positive:
        flags.append("NON_POSITIVE")
    if not crossed and len(past) >= min_history and _is_outlier(mid, past, threshold):
        flags.append("OUTLIER")

    status = "CROSSED" if crossed else "STALE" if stale else q.quote_status
    return {"instrument_id": q.instrument_id, "quote_status": status, "quality_flags": flags}


def check_quotes(
    as_of: int,
    quotes: Sequence[Quote],
    stale_after_seconds: int,
    max_relative_spread: float | None = None,
    positive_only: bool = False,
    outlier_threshold: float = 5.0,
    outlier_min_history: int = 5,
    history: Mapping[str, Sequence[float]] | None = None,
) -> list[dict[str, object]]:
    for q in quotes:
        if q.quote_status not in ("FIRM", "INDICATIVE"):
            raise QfError("E_SCHEMA", f"bad quote_status {q.quote_status}", "quote_status")
    if stale_after_seconds <= 0:
        raise QfError("E_INPUT", "stale_after_seconds must be positive", "stale_after_seconds")
    if max_relative_spread is not None and max_relative_spread <= 0:
        raise QfError("E_INPUT", "max_relative_spread must be positive", "max_relative_spread")
    if outlier_threshold <= 0:
        raise QfError("E_INPUT", "outlier_threshold must be positive", "outlier_threshold")
    if outlier_min_history < 3:
        raise QfError("E_INPUT", "outlier_min_history must be at least 3", "outlier_min_history")
    if any(q.event_time > as_of for q in quotes):
        raise QfError("E_INPUT", "event_time is after as_of", "quotes")
    return [
        _check_one(
            q, as_of, stale_after_seconds, max_relative_spread, positive_only,
            outlier_threshold, outlier_min_history, history or {},
        )
        for q in quotes
    ]
