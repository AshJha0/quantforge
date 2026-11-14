"""Trial-count registry (plan 12.5 Q7; ruling J-13).

`research/trials.csv` holds one row per configuration ever tried: `study,trial_id,parameters`. The deflated Sharpe
ratio of a study uses N = the number of distinct trial ids logged for it, never a smaller number. `register` appends a
trial before it is run, so the count cannot be lowered after the fact.
"""
from __future__ import annotations

import csv
from pathlib import Path

DEFAULT = Path(__file__).resolve().parents[2] / "research" / "trials.csv"
HEADER = ["study", "trial_id", "parameters"]


def _rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        if r.fieldnames != HEADER:
            raise ValueError(f"{path}: header must be {HEADER}")
        return list(r)


def trial_count(study: str, path: Path = DEFAULT) -> int:
    """N for `research.stats.dsr` (J-13): distinct trial ids logged for `study`."""
    return len({r["trial_id"] for r in _rows(path) if r["study"] == study})


def register(study: str, trial_id: str, parameters: str, path: Path = DEFAULT) -> int:
    """Append a trial (refuses a duplicate id); returns the new count for the study."""
    rows = _rows(path)
    if any(r["study"] == study and r["trial_id"] == trial_id for r in rows):
        raise ValueError(f"trial {trial_id} already registered for {study}")
    new = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        if new:
            w.writerow(HEADER)
        w.writerow([study, trial_id, parameters])
    return trial_count(study, path)
