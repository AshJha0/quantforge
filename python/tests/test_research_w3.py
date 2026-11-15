"""Stage J wave 3 property tests (spec pages 06-risk/scenario-stress.md, 11-research/interp-backtest.md,
11-research/drift-detectors.md): replay linearity, LOO invariances, detector null behaviour, KS symmetry."""
import math
import random
from datetime import date

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from quantforge_core import drift
from quantforge_core.errors import QfError
from quantforge_core.research_w3 import (
    backtest_interp_loo,
    backtest_surface_holdout,
    scenario_historical_shock,
    scenario_replay,
)

TEN = [0.25, 2.0, 5.0, 10.0, 30.0]
finite = st.floats(-50, 50, allow_nan=False)


@given(st.lists(finite, min_size=5, max_size=5), st.floats(0.1, 5))
@settings(max_examples=50, deadline=None)
def test_replay_scales_linearly_and_zero_shock_is_identity(shock: list[float], scale: float) -> None:
    base = [4.0, 4.1, 4.2, 4.3, 4.4]
    dv = [1.0, -2.0, 3.0, 0.5, 10.0]
    one = scenario_replay(TEN, base, TEN, shock, 1.0, dv)
    two = scenario_replay(TEN, base, TEN, shock, scale, dv)
    assert two["pnl"] == pytest.approx(scale * one["pnl"], rel=1e-12, abs=1e-9)
    assert scenario_replay(TEN, base, TEN, [0.0] * 5)["shocked_yields"] == base


def test_replay_of_historical_shock_returns_end_curve() -> None:
    d = [date(2020, 2, 19), date(2020, 3, 9)]
    rows = [[1.58, 1.43, 1.42, 1.56, 2.00], [0.57, 0.46, 0.50, 0.54, 0.99]]
    s = scenario_historical_shock(d, TEN, rows, d[0], d[1])
    r = scenario_replay(TEN, s["start_yields"], TEN, s["shift_bp"])
    assert r["shocked_yields"] == pytest.approx(rows[1], abs=1e-12)
    with pytest.raises(QfError) as e:
        scenario_historical_shock(d, TEN, rows, date(2020, 2, 20), d[1])
    assert e.value.code == "E_DOMAIN"


@pytest.mark.parametrize("method", ["linear", "cubic_natural", "monotone_pchip"])
def test_loo_exact_on_linear_data_and_shift_invariant(method: str) -> None:
    x = [0.0, 0.7, 1.5, 3.0, 4.2, 6.0]
    assert backtest_interp_loo(method, x, [2 * v + 1 for v in x])["max_abs_error"] < 1e-12
    y = [math.sin(v) for v in x]
    a = backtest_interp_loo(method, x, y)["errors"]
    b = backtest_interp_loo(method, x, [v + 3.0 for v in y])["errors"]
    assert a == pytest.approx(b, abs=1e-12)


def test_surface_holdout_flat_smile_is_exact() -> None:
    k = [-0.2, -0.1, 0.0, 0.1, 0.2]
    out = backtest_surface_holdout("cubic_natural", [0.5, 1.0], k, [[0.2] * 5, [0.25] * 5], [1, 3])
    assert out["max_abs_error"] < 1e-14


def test_detectors_null_behaviour() -> None:
    assert drift.cusum([0.0] * 100, 0.5, 5.0)["alarms"] == []
    assert drift.page_hinkley([3.0] * 100, 0.1, 1.0)["alarms"] == []
    r = [random.Random(1).gauss(0, 1) for _ in range(200)]
    assert drift.psi(r, r)["psi"] == 0.0


@given(st.lists(st.floats(-5, 5, allow_nan=False), min_size=1, max_size=15),
       st.lists(st.floats(-5, 5, allow_nan=False), min_size=1, max_size=15))
@settings(max_examples=60, deadline=None)
def test_ks_symmetric_and_bounded(a: list[float], b: list[float]) -> None:
    x, y = drift.ks(a, b), drift.ks(b, a)
    assert x["statistic"] == y["statistic"] and x["p_value"] == pytest.approx(y["p_value"], abs=1e-15)
    assert 0.0 <= x["p_value"] <= 1.0
    assert drift.ks(a, a)["p_value"] == 1.0


def test_ks_equal_size_matches_alternating_formula() -> None:
    # P(D >= k/n) for n = m: 2 sum_j (-1)^(j+1) C(2n, n - j k) / C(2n, n) [Gnedenko-Korolyuk]
    n = 12
    rng = random.Random(7)
    a = [rng.gauss(0, 1) for _ in range(n)]
    b = [rng.gauss(0.8, 1) for _ in range(n)]
    out = drift.ks(a, b)
    k = round(out["statistic"] * n)
    p = 2 * sum((-1) ** (j + 1) * math.comb(2 * n, n - j * k) for j in range(1, n // k + 1)) / math.comb(2 * n, n)
    assert out["p_value"] == pytest.approx(p, rel=1e-13)
