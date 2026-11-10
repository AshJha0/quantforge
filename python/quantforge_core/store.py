"""As-of store and replay (specifications/01-core/asof-store.md).

Pure functions of a log. Instants are whole seconds since the epoch, as in timezones.py. The format
function is passed in, as writing instants is the CLI's business.
"""

import itertools
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from .errors import QfError
from .finite import guard
from .snapshot import canonical, hash_value
from .timezones import DAY, date_seconds

Row = dict[str, Any]
Format = Callable[[int], str]
GENESIS = "0" * 64
MIN_INSTANT = date_seconds(date.min)
MAX_INSTANT = date_seconds(date.max) + DAY - 1


def _check_year(instant: int) -> None:
    if not MIN_INSTANT <= instant <= MAX_INSTANT:
        raise QfError("E_DATE_RANGE", "an instant leaves years 1 to 9999 in UTC")


@dataclass(frozen=True)
class Record:
    sequence: int
    series_id: str
    event_time: int
    knowledge_time: int
    value: Any
    deleted: bool
    raw: dict[str, Any]


def check_log(records: Sequence[Record], *instants: int | None) -> None:
    """Log checks 2 and 3, then the Z-form year limit on records and on other input instants."""
    for a, b in itertools.pairwise(records):
        if b.sequence <= a.sequence:
            raise QfError("E_INPUT", "sequence must be strictly increasing", "records")
    for a, b in itertools.pairwise(records):
        if b.knowledge_time < a.knowledge_time:
            raise QfError("E_INPUT", "knowledge_time went backwards", "records")
    for r in records:
        _check_year(r.event_time)
        _check_year(r.knowledge_time)
    for instant in instants:
        if instant is not None:
            _check_year(instant)


def view(records: Sequence[Record], as_of: int) -> list[Record]:
    current: dict[tuple[str, int], Record] = {}
    for r in records:
        if r.knowledge_time <= as_of:
            key = (r.series_id, r.event_time)
            if key not in current or r.sequence > current[key].sequence:
                current[key] = r
    live = [r for r in current.values() if not r.deleted]
    return sorted(live, key=lambda r: (r.series_id.encode("utf-8"), r.event_time))


def row(r: Record, fmt: Format) -> Row:
    return {
        "series_id": r.series_id,
        "event_time": fmt(r.event_time),
        "knowledge_time": fmt(r.knowledge_time),
        "sequence": r.sequence,
        "value": r.value,
    }


def query_as_of(
    records: Sequence[Record],
    as_of: int,
    fmt: Format,
    series_id: str | None = None,
    event_from: int | None = None,
    event_to: int | None = None,
) -> list[Row]:
    if event_from is not None and event_to is not None and event_from > event_to:
        raise QfError("E_DATE_ORDER", "event_from is after event_to", "event_to")
    return [
        row(r, fmt)
        for r in view(records, as_of)
        if (series_id is None or r.series_id == series_id)
        and (event_from is None or r.event_time >= event_from)
        and (event_to is None or r.event_time <= event_to)
    ]


def latest(records: Sequence[Record], as_of: int, series_id: str, fmt: Format) -> Row | None:
    rows = [r for r in view(records, as_of) if r.series_id == series_id]
    return row(rows[-1], fmt) if rows else None


def snapshot(records: Sequence[Record], as_of: int, fmt: Format) -> tuple[str, str, int]:
    """Returns (canonical, snapshot_id, row count)."""
    rows = [row(r, fmt) for r in view(records, as_of)]
    form, snapshot_id = hash_value({"as_of": fmt(as_of), "rows": rows})
    return form, snapshot_id, len(rows)


def chain(records: Sequence[Record]) -> list[str]:
    hashes: list[str] = []
    previous = GENESIS
    import hashlib

    for r in records:
        previous = hashlib.sha256((previous + canonical(r.raw)).encode("utf-8")).hexdigest()
        hashes.append(previous)
    return hashes


def replay(
    records: Sequence[Record], checkpoints: Sequence[int], fmt: Format
) -> tuple[list[Row], str]:
    """Returns (snapshots, head)."""
    if any(b < a for a, b in itertools.pairwise(checkpoints)):
        raise QfError("E_INPUT", "checkpoints must be ascending", "checkpoints")
    snapshots = []
    for as_of in checkpoints:
        _, snapshot_id, count = snapshot(records, as_of, fmt)
        snapshots.append({"as_of": fmt(as_of), "row_count": count, "snapshot_id": snapshot_id})
    hashes = chain(records)
    return snapshots, hashes[-1] if hashes else GENESIS


guard(globals())
