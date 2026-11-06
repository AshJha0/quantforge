from datetime import date
import pytest
from quantforge_core.conventions import act_360, act_365f

def test_act_360():
    assert act_360(date(2025, 1, 1), date(2025, 1, 31)).value == pytest.approx(30 / 360)

def test_act_365f():
    assert act_365f(date(2024, 1, 1), date(2025, 1, 1)).value == pytest.approx(366 / 365)

def test_rejects_reversed_dates():
    with pytest.raises(ValueError):
        act_360(date(2025, 2, 1), date(2025, 1, 1))
