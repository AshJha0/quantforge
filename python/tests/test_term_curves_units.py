"""Unit tests for the stage J curves lane: the financing term structure and the liquidity cost
curve. Expected values are derived by hand from 02-curves/financing-term-structure.md and
10-execution/liquidity-curve.md; error paths follow rulings J-C-1 to J-C-9."""

import math

import pytest

from quantforge_core import term_curves as tc
from quantforge_core.errors import QfError


def _err(fn, code: str, field: str | None = None) -> None:
    with pytest.raises(QfError) as e:
        fn()
    assert e.value.code == code
    # the message is a readable sentence, not a placeholder or shouting (kills the
    # message-text mutants, which no code or field check can see)
    assert isinstance(e.value.message, str) and str(e.value) == e.value.message
    assert "XX" not in e.value.message and e.value.message != e.value.message.upper()
    if field is not None:
        assert e.value.field == field


def _curve(borrow: bool = True) -> tc.FinancingCurve:
    return tc.build_financing_curve(
        [1.0, 2.0],
        [0.02, 0.03],
        [1.0, 2.0],
        [0.05, 0.04],
        [2.0] if borrow else [],
        [0.01] if borrow else [],
    )


S1 = math.log(1.05) - 0.02
S2 = math.log(1.08) - 0.06


def test_lin_and_helpers() -> None:
    assert tc._lin([1.0, 3.0], [2.0, 4.0], 0.5) == pytest.approx(1.0)
    assert tc._lin([1.0, 3.0], [2.0, 4.0], 1.0) == pytest.approx(2.0)
    assert tc._lin([1.0, 3.0], [2.0, 4.0], 2.0) == pytest.approx(3.0)
    assert tc._lin([1.0, 3.0], [2.0, 4.0], 3.0) == pytest.approx(4.0)
    with pytest.raises(AssertionError):
        tc._lin([1.0], [1.0], 2.0)
    assert tc._increasing_positive([0.5, 1.0])
    assert tc._increasing_positive([])
    assert not tc._increasing_positive([0.0, 1.0])
    assert not tc._increasing_positive([1.0, 1.0])
    assert not tc._increasing_positive([2.0, 1.0])


def test_build_bootstrap() -> None:
    c = _curve()
    assert c.funding_cum == pytest.approx([0.02, 0.06])
    assert c.spread_cum == pytest.approx([S1, S2])
    assert c.borrow_cum == pytest.approx([0.02])
    assert c.cover == 2.0
    assert c.zt(1.5) == pytest.approx(0.04)
    assert c.s(0.5) == pytest.approx(S1 / 2)
    assert c.b(1.0) == pytest.approx(0.01)
    assert c.financing_df(2.0) == pytest.approx(1 / 1.08)
    nb = _curve(False)
    assert nb.b(1.0) == 0.0
    assert nb.cover == 2.0
    # cover is the minimum of the three ends
    c2 = tc.build_financing_curve([1.0, 3.0], [0.02, 0.02], [2.0], [0.03], [1.5], [0.0])
    assert c2.cover == 1.5
    c3 = tc.build_financing_curve([1.0, 3.0], [0.02, 0.02], [2.0], [0.03], [], [])
    assert c3.cover == 2.0
    c4 = tc.build_financing_curve([1.0], [0.02], [1.0], [0.03], [5.0], [0.0])
    assert c4.cover == 1.0
    # a quote exactly at the funding end is allowed
    assert tc.build_financing_curve([1.0], [0.0], [1.0], [0.0], [], []).spread_cum == [0.0]


def test_build_errors() -> None:
    f = tc.build_financing_curve
    _err(lambda: f([1.0], [0.0, 0.1], [1.0], [0.0], [], []), "E_INPUT", "quote_times")
    _err(lambda: f([1.0], [0.0], [1.0], [0.0, 0.1], [], []), "E_INPUT", "quote_times")
    _err(lambda: f([1.0], [0.0], [1.0], [0.0], [1.0], []), "E_INPUT", "quote_times")
    _err(lambda: f([], [], [1.0], [0.0], [], []), "E_INPUT", "quote_times")
    _err(lambda: f([1.0], [0.0], [], [], [], []), "E_INPUT", "quote_times")
    _err(lambda: f([0.0], [0.0], [1.0], [0.0], [], []), "E_INPUT", "funding_times")
    _err(lambda: f([1.0], [0.0], [1.0, 1.0], [0.0, 0.0], [], []), "E_INPUT", "quote_times")
    _err(lambda: f([1.0], [0.0], [1.0], [0.0], [-1.0], [0.0]), "E_INPUT", "borrow_times")
    _err(lambda: f([1.0], [0.0], [1.0], [-1.0], [], []), "E_DOMAIN", "repo_rates")
    _err(lambda: f([1.0], [0.0], [1.0], [-2.0], [], []), "E_DOMAIN", "repo_rates")
    _err(lambda: f([1.0], [0.0], [1.0], [0.0], [1.0], [-0.01]), "E_DOMAIN", "borrow_fees")
    assert f([1.0], [0.0], [1.0], [0.0], [1.0], [0.0]).borrow_cum == [0.0]
    _err(lambda: f([1.0], [0.0], [1.0], [0.0], [1.0, 2.0], [0.03, 0.01]), "E_DOMAIN", "borrow_fees")
    assert f([1.0], [0.0], [1.0], [0.0], [1.0, 2.0], [0.02, 0.01]).borrow_cum == [0.02, 0.02]
    _err(lambda: f([1.0], [0.0], [0.5, 1.5], [0.0, 0.0], [], []), "E_DOMAIN", "quote_times")


def test_term_curve_values() -> None:
    c = _curve()
    out = tc.term_curve(c, [1.0, 2.0])
    assert out["pillar_spreads"] == pytest.approx([S1, S2 / 2])
    assert out["spread"] == pytest.approx([S1, S2 / 2])
    assert out["financing_df"] == pytest.approx([1 / 1.05, 1 / 1.08])
    assert out["financing_rate"] == pytest.approx([0.05, 0.04])
    assert out["forward_financing"] == pytest.approx([0.05, 1.08 / 1.05 - 1.0])
    assert out["borrow_fee"] == pytest.approx([0.01, 0.01])
    half = tc.term_curve(c, [0.5])
    df = math.exp(-0.01 - S1 / 2)
    assert half["financing_df"] == pytest.approx([df])
    assert half["forward_financing"] == pytest.approx([(1 / df - 1) / 0.5])
    assert half["financing_rate"] == pytest.approx([(1 / df - 1) / 0.5])
    assert tc.term_curve(_curve(False), [1.0])["borrow_fee"] is None


def test_term_curve_errors() -> None:
    c = _curve()
    _err(lambda: tc.term_curve(c, []), "E_INPUT", "query_times")
    _err(lambda: tc.term_curve(c, [0.0]), "E_INPUT", "query_times")
    _err(lambda: tc.term_curve(c, [1.0, 1.0]), "E_INPUT", "query_times")
    _err(lambda: tc.term_curve(c, [2.5]), "E_DOMAIN", "query_times")


def test_forward_term_financed() -> None:
    c = _curve()
    cf = math.exp(-math.log(1.08) + 0.02)
    out = tc.forward_term_financed(c, 100.0, 2.0, [], [])
    assert out["carry_factor"] == pytest.approx(cf)
    assert out["forward"] == pytest.approx(100.0 / cf)
    assert out["carry"] == pytest.approx(100.0 / cf - 100.0)
    assert out["financing_df"] == pytest.approx(1 / 1.08)
    assert out["pv_dividends"] == 0.0
    c1 = math.exp(-0.02 - S1 + 0.01)
    d = tc.forward_term_financed(c, 100.0, 2.0, [1.0, 2.0, 3.0], [5.0, 2.0, 7.0])
    assert d["pv_dividends"] == pytest.approx(5.0 * c1 + 2.0 * cf)
    assert d["forward"] == pytest.approx((100.0 - 5.0 * c1 - 2.0 * cf) / cf)
    z = tc.forward_term_financed(c, 100.0, 1.0, [0.0, 1.5], [5.0, 5.0])
    assert z["pv_dividends"] == 0.0
    assert tc.forward_term_financed(c, 1.0, 1.0, [1.0], [0.0])["forward"] > 0


def test_forward_term_financed_errors() -> None:
    c = _curve()
    f = tc.forward_term_financed
    _err(lambda: f(c, 100.0, 1.0, [1.0], []), "E_INPUT", "dividend_amounts")
    _err(lambda: f(c, 100.0, 1.0, [1.0, 1.0], [1.0, 1.0]), "E_INPUT", "dividend_times")
    _err(lambda: f(c, 0.0, 1.0, [], []), "E_DOMAIN", "spot")
    _err(lambda: f(c, 100.0, 0.0, [], []), "E_DOMAIN", "maturity_years")
    _err(lambda: f(c, 100.0, 2.5, [], []), "E_DOMAIN", "maturity_years")
    _err(lambda: f(c, 100.0, 1.0, [0.5], [-1.0]), "E_DOMAIN", "dividend_amounts")
    _err(lambda: f(c, 1.0, 1.0, [0.5], [5.0]), "E_DOMAIN", "dividend_amounts")
    cpv = math.exp(-tc._lin([1.0, 2.0], [0.02, 0.06], 1.0) - S1 + 0.01)
    _err(lambda: f(c, cpv, 1.0, [1.0], [1.0]), "E_DOMAIN", "dividend_amounts")


def test_liquidity_cost_values() -> None:
    out = tc.liquidity_cost(5.0, 1000.0, 0.02, 0.5, 0.5, 1.0, [100.0, 0.0], [1.0, 3.0])
    assert out["spread_cost"] == pytest.approx(0.0005)
    imp1 = 0.5 * 0.02 * math.sqrt(0.1)
    imp3 = 0.5 * 0.02 * math.sqrt(100.0 / 3000.0)
    assert out["impact"][0] == pytest.approx([imp1, imp3])
    assert out["impact"][1] == pytest.approx([0.0, 0.0])
    risk = [0.02 * math.sqrt(1 / 3), 0.02]
    assert out["timing_risk"] == pytest.approx(risk)
    assert out["total_cost"][0] == pytest.approx([0.0005 + imp1 + risk[0], 0.0005 + imp3 + 0.02])
    assert out["total_cost"][1] == pytest.approx([0.0005 + risk[0], 0.0005 + 0.02])
    a = 0.5 * 0.02 * math.sqrt(0.1)
    b = 0.02 / math.sqrt(3.0)
    h = (a / b) ** 1.0
    assert out["optimal_horizon"] == pytest.approx([h, 0.0])
    assert out["min_cost"] == pytest.approx([0.0005 + a / math.sqrt(h) + b * math.sqrt(h), 0.0005])
    # exponent 1: h* = (2 a / b)^(2/3)
    o1 = tc.liquidity_cost(0.0, 100.0, 0.1, 2.0, 1.0, 3.0, [10.0], [2.0])
    a1, b1 = 2.0 * 0.1 * 0.1, 3.0 * 0.1 / math.sqrt(3.0)
    h1 = (2 * a1 / b1) ** (2.0 / 3.0)
    assert o1["impact"][0] == pytest.approx([2.0 * 0.1 * 10.0 / 200.0])
    assert o1["optimal_horizon"] == pytest.approx([h1])
    assert o1["min_cost"] == pytest.approx([a1 / h1 + b1 * math.sqrt(h1)])
    for z, y in ((0.0, 0.5), (1.0, 0.0)):
        o = tc.liquidity_cost(1.0, 100.0, 0.1, y, 0.5, z, [10.0], [1.0])
        assert o["optimal_horizon"] is None and o["min_cost"] is None
    o0 = tc.liquidity_cost(1.0, 100.0, 0.0, 1.0, 0.5, 1.0, [10.0], [1.0])
    assert o0["optimal_horizon"] is None
    assert o0["total_cost"][0] == pytest.approx([0.0001])


def test_liquidity_cost_errors() -> None:
    f = tc.liquidity_cost
    base = {
        "half_spread_bps": 1.0,
        "daily_volume": 100.0,
        "daily_vol": 0.1,
        "coefficient": 1.0,
        "exponent": 0.5,
        "risk_multiplier": 1.0,
        "sizes": [1.0],
        "horizons": [1.0],
    }
    _err(lambda: f(**{**base, "sizes": []}), "E_INPUT", "sizes")  # type: ignore[arg-type]
    _err(lambda: f(**{**base, "horizons": []}), "E_INPUT", "sizes")  # type: ignore[arg-type]
    for key, bad, field in (
        ("half_spread_bps", -0.1, "half_spread_bps"),
        ("daily_volume", 0.0, "daily_volume"),
        ("daily_vol", -0.1, "daily_vol"),
        ("coefficient", -0.1, "coefficient"),
        ("risk_multiplier", -0.1, "risk_multiplier"),
        ("exponent", 0.0, "exponent"),
        ("exponent", 1.01, "exponent"),
        ("sizes", [-1.0], "sizes"),
        ("horizons", [0.0], "horizons_days"),
    ):
        _err(lambda k=key, v=bad: f(**{**base, k: v}), "E_DOMAIN", field)
    for key, ok in (
        ("half_spread_bps", 0.0),
        ("daily_vol", 0.0),
        ("coefficient", 0.0),
        ("risk_multiplier", 0.0),
        ("exponent", 1.0),
        ("sizes", [0.0]),
    ):
        f(**{**base, key: ok})  # type: ignore[arg-type]
