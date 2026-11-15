"""Stage J curves lane property tests (rulings J-C-1 to J-C-9): quote round trip, forward and
spot consistency, flat-rate reduction to ruling D22, liquidity-curve monotonicity and the
closed-form optimal horizon."""
import itertools
import math

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from quantforge_core.errors import QfError
from quantforge_core.term_curves import (
    build_financing_curve,
    forward_term_financed,
    liquidity_cost,
    term_curve,
)

FT, FZ = [0.25, 0.5, 1.0, 2.0], [0.040, 0.041, 0.0415, 0.042]
QT, QR = [1 / 12, 0.25, 0.5, 1.0], [0.0425, 0.0430, 0.0435, 0.0440]


def _curve(bt: list[float] | None = None, bf: list[float] | None = None):  # type: ignore[no-untyped-def]
    return build_financing_curve(FT, FZ, QT, QR, bt or [], bf or [])


@settings(max_examples=60, deadline=None)
@given(st.lists(st.floats(-0.01, 0.10), min_size=1, max_size=6))
def test_quotes_round_trip(rates: list[float]) -> None:
    qt = [0.1 * (k + 1) for k in range(len(rates))]
    c = build_financing_curve([1.0], [0.03], qt, rates, [], [])
    out = term_curve(c, qt)
    for r, got in zip(rates, out["financing_rate"], strict=True):
        assert got == pytest.approx(r, abs=1e-13)


def test_forwards_chain_to_term_rates() -> None:
    q = [0.1, 0.3, 0.5, 0.8, 1.0]
    out = term_curve(_curve(), q)
    growth, prev = 1.0, 0.0
    for t, f, p in zip(q, out["forward_financing"], out["financing_df"], strict=True):
        growth *= 1.0 + f * (t - prev)
        prev = t
        assert growth == pytest.approx(1.0 / p, rel=1e-14)


def test_flat_inputs_reduce_to_ruling_d22() -> None:
    """Flat funding r, flat spread s and flat borrow b give F = S exp((r + s - b) T) (D22)."""
    r, s, b, t = 0.03, 0.004, 0.002, 0.75
    repo = [(math.exp((r + s) * x) - 1) / x for x in (0.25, 1.0)]
    c = build_financing_curve([1.0], [r], [0.25, 1.0], repo, [1.0], [b])
    out = forward_term_financed(c, 100.0, t, [], [])
    assert out["forward"] == pytest.approx(100.0 * math.exp((r + s - b) * t), rel=1e-14)
    assert term_curve(c, [0.5])["spread"][0] == pytest.approx(s, abs=1e-15)


def test_borrow_lowers_forward_and_dividends_lower_forward() -> None:
    base = forward_term_financed(_curve(), 50.0, 0.75, [], [])["forward"]
    assert forward_term_financed(_curve([1.0], [0.01]), 50.0, 0.75, [], [])["forward"] < base
    assert forward_term_financed(_curve(), 50.0, 0.75, [0.5], [1.0])["forward"] < base


def test_errors() -> None:
    with pytest.raises(QfError) as e:
        term_curve(_curve(), [1.5])
    assert e.value.code == "E_DOMAIN"
    with pytest.raises(QfError) as e:
        build_financing_curve(FT, FZ, QT, QR, [0.5, 1.0], [0.02, 0.001])
    assert e.value.code == "E_DOMAIN"
    with pytest.raises(QfError) as e:
        build_financing_curve(FT, FZ, [0.5, 0.5], [0.04, 0.04], [], [])
    assert e.value.code == "E_INPUT"
    with pytest.raises(QfError) as e:
        liquidity_cost(1.0, 1e7, 0.02, 1.0, 0.0, 0.0, [1e5], [1.0])
    assert e.value.code == "E_DOMAIN"


def test_liquidity_matches_stage_h_square_root_at_one_day() -> None:
    out = liquidity_cost(0.0, 1e7, 0.02, 1.0, 0.5, 0.0, [1e5], [1.0])
    assert out["impact"][0][0] == pytest.approx(0.02 * math.sqrt(0.01), rel=1e-15)
    assert out["optimal_horizon"] is None


@settings(max_examples=60, deadline=None)
@given(st.floats(0.1, 1.0), st.floats(1e3, 1e7), st.floats(0.1, 3.0))
def test_optimal_horizon_is_a_minimum(delta: float, q: float, z: float) -> None:
    out = liquidity_cost(2.0, 1e7, 0.02, 1.0, delta, z, [q], [1.0])
    h, c = out["optimal_horizon"][0], out["min_cost"][0]
    for k in (0.9, 1.1):
        other = liquidity_cost(2.0, 1e7, 0.02, 1.0, delta, z, [q], [h * k])["total_cost"][0][0]
        assert other >= c - 1e-15


@settings(max_examples=60, deadline=None)
@given(st.lists(st.floats(0.0, 1e7), min_size=2, max_size=5, unique=True))
def test_impact_increases_in_size(sizes: list[float]) -> None:
    sizes = sorted(sizes)
    imp = [r[0] for r in liquidity_cost(0.0, 1e7, 0.02, 1.0, 0.5, 0.0, sizes, [2.0])["impact"]]
    assert all(b >= a for a, b in itertools.pairwise(imp))
