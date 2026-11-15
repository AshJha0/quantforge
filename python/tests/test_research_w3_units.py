"""Unit tests for the stage J wave 3 operations (scenario stress and interpolation backtests).
Expected values are derived by hand from 06-risk/scenario-stress.md and
11-research/interp-backtest.md; each error path follows rulings J-W3-1 to J-W3-9."""

import math
from datetime import date

import pytest

from quantforge_core import research_w3 as r3
from quantforge_core.errors import QfError

D = [date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3)]
T = [1.0, 2.0, 5.0]
Y = [[1.0, 2.0, 3.0], [1.5, 2.0, 2.0], [2.0, 3.0, 4.5]]


def _err(fn, code: str, field: str | None = None):
    with pytest.raises(QfError) as e:
        fn()
    assert e.value.code == code
    # the message is a readable sentence, not a placeholder or shouting (kills the
    # message-text mutants, which no code or field check can see)
    assert isinstance(e.value.message, str) and str(e.value) == e.value.message
    assert "XX" not in e.value.message and e.value.message != e.value.message.upper()
    if field is not None:
        assert e.value.field == field
    return e.value


def test_historical_shock_values() -> None:
    out = r3.scenario_historical_shock(D, T, Y, D[0], D[2])
    assert out["start_yields"] == [1.0, 2.0, 3.0]
    assert out["end_yields"] == [2.0, 3.0, 4.5]
    assert out["shift_bp"] == pytest.approx([100.0, 100.0, 150.0])
    assert out["level_bp"] == pytest.approx(350.0 / 3.0)
    assert out["slope_bp"] == pytest.approx(50.0)
    mid = r3.scenario_historical_shock(D, T, Y, D[1], D[2])
    assert mid["shift_bp"] == pytest.approx([50.0, 100.0, 250.0])
    assert mid["slope_bp"] == pytest.approx(200.0)
    adj = r3.scenario_historical_shock(D, T, Y, D[0], D[1])
    assert adj["shift_bp"] == pytest.approx([50.0, 0.0, -100.0])
    assert adj["level_bp"] == pytest.approx(-50.0 / 3.0)


def test_historical_shock_errors() -> None:
    f = r3.scenario_historical_shock
    _err(lambda: f([], T, [], D[0], D[1]), "E_INPUT", "yields")
    _err(lambda: f(D, [], [[], [], []], D[0], D[1]), "E_INPUT", "yields")
    _err(lambda: f(D, T, Y[:2], D[0], D[1]), "E_INPUT", "yields")
    _err(lambda: f(D, T, [Y[0], Y[1], [1.0, 2.0]], D[0], D[1]), "E_INPUT", "yields")
    _err(lambda: f([D[0], D[0], D[2]], T, Y, D[0], D[2]), "E_DATE_ORDER", "dates")
    _err(lambda: f([D[1], D[0], D[2]], T, Y, D[0], D[2]), "E_DATE_ORDER", "dates")
    _err(lambda: f(D, [1.0, 1.0, 5.0], Y, D[0], D[2]), "E_DOMAIN", "tenors")
    _err(lambda: f(D, [0.0, 2.0, 5.0], Y, D[0], D[2]), "E_DOMAIN", "tenors")
    _err(lambda: f(D, [-1.0, 2.0, 5.0], Y, D[0], D[2]), "E_DOMAIN", "tenors")
    _err(lambda: f(D, T, Y, D[1], D[1]), "E_DATE_ORDER", "end_date")
    _err(lambda: f(D, T, Y, D[2], D[1]), "E_DATE_ORDER", "end_date")
    _err(lambda: f(D, T, Y, date(2023, 1, 1), D[1]), "E_DOMAIN", "start_date")
    _err(lambda: f(D, T, Y, D[0], date(2025, 1, 1)), "E_DOMAIN", "end_date")


def test_flat_linear() -> None:
    x, y = [1.0, 3.0, 4.0], [10.0, 20.0, 50.0]
    assert r3._flat_linear(x, y, 0.5) == 10.0
    assert r3._flat_linear(x, y, 1.0) == 10.0
    assert r3._flat_linear(x, y, 2.0) == pytest.approx(15.0)
    assert r3._flat_linear(x, y, 3.0) == pytest.approx(20.0)
    assert r3._flat_linear(x, y, 3.5) == pytest.approx(35.0)
    assert r3._flat_linear(x, y, 4.0) == 50.0
    assert r3._flat_linear(x, y, 9.0) == 50.0


def test_replay_values() -> None:
    out = r3.scenario_replay([0.5, 2.0, 10.0], [1.0, 2.0, 3.0], [1.0, 3.0], [10.0, 30.0])
    assert out["applied_bp"] == pytest.approx([10.0, 20.0, 30.0])
    assert out["shocked_yields"] == pytest.approx([1.1, 2.2, 3.3])
    assert "pnl" not in out
    out2 = r3.scenario_replay(
        [0.5, 2.0, 10.0], [1.0, 2.0, 3.0], [1.0, 3.0], [10.0, 30.0], 2.0, [1.0, -2.0, 3.0]
    )
    assert out2["applied_bp"] == pytest.approx([20.0, 40.0, 60.0])
    assert out2["shocked_yields"] == pytest.approx([1.2, 2.4, 3.6])
    assert out2["pnl"] == pytest.approx(-(20.0 - 80.0 + 180.0))


def test_replay_errors() -> None:
    f = r3.scenario_replay
    _err(lambda: f([], [], [1.0], [1.0]), "E_INPUT", "base_yields")
    _err(lambda: f([1.0], [1.0, 2.0], [1.0], [1.0]), "E_INPUT", "base_yields")
    _err(lambda: f([1.0], [1.0], [], []), "E_INPUT", "shock_bp")
    _err(lambda: f([1.0], [1.0], [1.0], [1.0, 2.0]), "E_INPUT", "shock_bp")
    _err(lambda: f([1.0], [1.0], [1.0], [1.0], 1.0, [1.0, 2.0]), "E_INPUT", "dv01")
    _err(lambda: f([2.0, 1.0], [1.0, 1.0], [1.0], [1.0]), "E_DOMAIN", "base_tenors")
    _err(lambda: f([1.0], [1.0], [0.0], [1.0]), "E_DOMAIN", "shock_tenors")


def test_loo_linear_hand_values() -> None:
    x, y = [0.0, 1.0, 2.0, 4.0], [0.0, 1.0, 4.0, 16.0]
    out = r3.backtest_interp_loo("linear", x, y)
    # drop x=1: line (0,0)-(2,4) gives 2 -> +1; drop x=2: (1,1)-(4,16) gives 6 -> +2
    assert out["errors"] == pytest.approx([1.0, 2.0])
    assert out["max_abs_error"] == pytest.approx(2.0)
    assert out["rmse"] == pytest.approx(math.sqrt(2.5))
    neg = r3.backtest_interp_loo("linear", [0.0, 1.0, 2.0], [0.0, 5.0, 0.0])
    assert neg["errors"] == pytest.approx([-5.0])
    assert neg["max_abs_error"] == pytest.approx(5.0)
    assert neg["rmse"] == pytest.approx(5.0)


def test_loo_exact_for_reproduced_shapes() -> None:
    x = [1.0, 2.0, 3.0, 4.0, 5.0]
    lin = r3.backtest_interp_loo("cubic_natural", x, [2 * v + 1 for v in x])
    assert lin["max_abs_error"] == pytest.approx(0.0, abs=1e-12)
    ll = r3.backtest_interp_loo("log_linear", x, [math.exp(0.3 * v) for v in x])
    assert ll["errors"] == pytest.approx([0.0, 0.0, 0.0], abs=1e-12)
    pc = r3.backtest_interp_loo("monotone_pchip", x, [3.0] * 5)
    assert pc["rmse"] == pytest.approx(0.0, abs=1e-12)


def test_loo_errors() -> None:
    f = r3.backtest_interp_loo
    _err(lambda: f("linear", [0.0, 1.0, 2.0], [0.0, 1.0]), "E_INPUT", "x")
    _err(lambda: f("linear", [0.0, 1.0], [0.0, 1.0]), "E_INPUT", "x")
    _err(lambda: f("cubic_natural", [0.0, 1.0, 2.0], [0.0, 1.0, 2.0]), "E_INPUT", "x")
    assert f("cubic_natural", [0.0, 1.0, 2.0, 3.0], [0.0, 1.0, 2.0, 3.0])["errors"]
    assert f("linear", [0.0, 1.0, 2.0], [0.0, 1.0, 2.0])["errors"] == pytest.approx([0.0])
    _err(lambda: f("linear", [0.0, 1.0, 1.0], [0.0, 1.0, 2.0]), "E_INPUT", "x")
    _err(lambda: f("linear", [0.0, 2.0, 1.0], [0.0, 1.0, 2.0]), "E_INPUT", "x")


K = [80.0, 90.0, 100.0, 110.0, 120.0]


def test_surface_holdout_linear_total_variance() -> None:
    vols = [[0.3, 0.25, 0.2, 0.25, 0.3], [0.2, 0.2, 0.2, 0.2, 0.2]]
    out = r3.backtest_surface_holdout("linear", [1.0, 2.0], K, vols, [2])
    # row 1: w at 90 and 110 are 0.0625 each -> sqrt(0.0625) - 0.2 = 0.05
    assert out["errors"][0] == pytest.approx([0.05])
    assert out["errors"][1] == pytest.approx([0.0], abs=1e-12)
    assert out["max_abs_error"] == pytest.approx(0.05)
    assert out["rmse"] == pytest.approx(0.05 / math.sqrt(2.0))
    # two holdouts, total variance linear in strike between 80 and 110 with t = 4
    v = [math.sqrt((0.04 + 0.001 * (k - 80.0)) / 4.0) for k in K]
    two = r3.backtest_surface_holdout("linear", [4.0], K, [v], [1, 2])
    assert two["errors"][0] == pytest.approx([0.0, 0.0], abs=1e-12)
    asym = r3.backtest_surface_holdout("linear", [1.0], K, [[0.1, 0.5, 0.2, 0.2, 0.2]], [1])
    assert asym["errors"][0] == pytest.approx([math.sqrt(0.025) - 0.5])


def test_surface_holdout_errors() -> None:
    f = r3.backtest_surface_holdout
    good = [[0.2] * 5]
    _err(lambda: f("linear", [], K, [], [2]), "E_INPUT", "vols")
    _err(lambda: f("linear", [1.0], K, [[0.2] * 5, [0.2] * 5], [2]), "E_INPUT", "vols")
    _err(lambda: f("linear", [1.0], K, [[0.2] * 4], [2]), "E_INPUT", "vols")
    _err(lambda: f("linear", [1.0], [80.0, 90.0, 90.0, 110.0, 120.0], good, [2]), "E_INPUT")
    _err(lambda: f("linear", [1.0], K, good, []), "E_INPUT", "holdout")
    _err(lambda: f("linear", [1.0], K, good, [0]), "E_INPUT", "holdout")
    _err(lambda: f("linear", [1.0], K, good, [4]), "E_INPUT", "holdout")
    _err(lambda: f("linear", [1.0], K, good, [2, 2]), "E_INPUT", "holdout")
    _err(lambda: f("linear", [1.0], K, good, [3, 2]), "E_INPUT", "holdout")
    assert f("linear", [1.0], K, good, [1, 3])["max_abs_error"] == pytest.approx(0.0, abs=1e-12)
    _err(lambda: f("cubic_natural", [1.0], K, good, [1, 2, 3]), "E_INPUT", "holdout")
    _err(lambda: f("cubic_natural", [1.0], K[:4], [[0.2] * 4], [1, 2]), "E_INPUT", "holdout")
    assert f("cubic_natural", [1.0], K, good, [1, 3])["rmse"] == pytest.approx(0.0, abs=1e-12)
    _err(lambda: f("linear", [0.0], K, good, [2]), "E_DOMAIN", "expiries")
    _err(lambda: f("linear", [1.0], K, [[0.2, 0.2, 0.2, 0.0, 0.2]], [2]), "E_DOMAIN", "vols")
    _err(lambda: f("linear", [1.0], K, [[0.2, 0.2, -0.1, 0.2, 0.2]], [2]), "E_DOMAIN", "vols")


def test_surface_holdout_nonpositive_fit() -> None:
    # Spike at 5 with 3 held out: the natural cubic between 2 and 4 dips to about -2.66.
    k = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
    vols = [[0.01, 0.01, 0.01, 0.01, 3.0, 0.01]]
    with pytest.raises(QfError) as e:
        r3.backtest_surface_holdout("cubic_natural", [1.0], k, vols, [2])
    assert e.value.code == "E_DOMAIN" and e.value.field == "vols"
