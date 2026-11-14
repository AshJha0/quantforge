"""Tests for the post-hoc R3-02 dummy-controlled check (`r3_02_dummy.py`)."""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import r3_02_dummy as m
import r3_runner as r


def _bdays(start: date, n: int) -> list[date]:
    out: list[date] = []
    x = start
    while len(out) < n:
        if x.weekday() < 5:
            out.append(x)
        x += timedelta(days=1)
    return out


def test_month_end_mask_marks_last_business_day() -> None:
    days = [date(2024, 1, 30), date(2024, 1, 31), date(2024, 2, 1), date(2024, 2, 29)]
    assert m.month_end_mask(days).tolist() == [False, True, False, True]


def test_controlled_funding_skips_dropped_and_carries_accrual() -> None:
    f = np.array([1.0, 2.0, 9.0, 4.0])
    drop = np.array([False, False, True, False])
    trailing, carried = m.controlled_funding(f, drop, trail=2)
    assert np.isnan(trailing[0])
    assert trailing[1] == 1.5 and trailing[2] == 1.5 and trailing[3] == 3.0
    assert carried.tolist() == [1.0, 2.0, 2.0, 4.0]


def test_no_month_ends_matches_runner(monkeypatch: pytest.MonkeyPatch) -> None:
    rng = np.random.default_rng(0)
    days = _bdays(date(2020, 1, 1), 400)
    bill = 0.02 + rng.normal(0, 0.001, len(days))
    fund = 0.02 + rng.normal(0, 0.001, len(days))
    monkeypatch.setattr(m, "month_end_mask", lambda ds: np.zeros(len(ds), dtype=bool))
    ex1, a = m.controlled_returns(days, bill, fund, 60, 0.5)
    ex2, b = r.bill_month_returns(days, bill, fund, 60, 0.5)
    assert ex1 == ex2 and np.allclose(a, b)


def test_describe_flat() -> None:
    out = m.describe(np.zeros(5))
    assert out["sharpe_net_1x"] is None and out["months_in_position"] == 0
