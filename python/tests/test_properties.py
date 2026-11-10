"""Property tests (review item G6): put-call parity, discount factor monotonicity and the implied
vol round trip, over generated inputs."""
import itertools
import math
from datetime import date, timedelta

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from quantforge_core import black, curves
from quantforge_core.errors import QfError

SETTINGS = settings(max_examples=300, deadline=None)
MODELS = (black.BLACK_SCHOLES, black.BLACK_76, black.BACHELIER)
spot = st.floats(min_value=1.0, max_value=1000.0)
moneyness = st.floats(min_value=0.5, max_value=2.0)
expiry = st.floats(min_value=0.01, max_value=10.0)
rate = st.floats(min_value=-0.02, max_value=0.10)
vol = st.floats(min_value=0.01, max_value=1.5)


def _option(model, kind, s, m, t, r, q):
    if model == black.BLACK_SCHOLES:
        return black.Option(model, kind, s * m, t, s, r, q)
    return black.Option(model, kind, s * m, t, s, discount_factor=math.exp(-r * t))


@SETTINGS
@given(st.sampled_from(MODELS), spot, moneyness, expiry, rate, rate, vol)
def test_put_call_parity(model, s, m, t, r, q, v):
    if model == black.BACHELIER:
        v *= s  # a normal vol is in price units
    call = black.price(_option(model, "CALL", s, m, t, r, q), v)
    put = black.price(_option(model, "PUT", s, m, t, r, q), v)
    o = _option(model, "CALL", s, m, t, r, q)
    parity = o.discount * (o.forward - o.strike)
    assert call - put == pytest.approx(parity, abs=1e-10 * s, rel=1e-10)


@SETTINGS
@given(st.sampled_from(MODELS), st.sampled_from(("CALL", "PUT")), spot, moneyness, expiry, rate,
       rate, vol)
def test_implied_vol_round_trip(model, kind, s, m, t, r, q, v):
    if model == black.BACHELIER:
        v *= s
    o = _option(model, kind, s, m, t, r, q)
    target = black.price(o, v)
    intrinsic = o.discount * max(o.phi * (o.forward - o.strike), 0.0)
    # Far from the money the time value sits below the price's rounding: no vol is identifiable.
    assume(target - intrinsic > 1e-8 * max(1.0, target))
    try:
        found = black.implied(o, target)
    except QfError as e:
        assert e.code in ("E_DOMAIN", "E_NO_CONVERGENCE")
        return
    assert black.price(o, found) == pytest.approx(target, rel=1e-9, abs=1e-12 * s)


AS_OF = date(2026, 1, 2)
forwards = st.lists(st.floats(min_value=0.0, max_value=0.15), min_size=1, max_size=12)


def _curve(rates, gaps, interpolation):
    dates, dfs, d, df = [], [], AS_OF, 1.0
    for f, gap in zip(rates, gaps, strict=False):
        nd = d + timedelta(days=gap)
        df *= math.exp(-f * gap / 365.0)
        dates.append(nd)
        dfs.append(df)
        d = nd
    return curves.CurveData(AS_OF, interpolation, tuple(dates), tuple(dfs))


# Log-linear DF interpolation keeps each segment's forward equal to the pillar forward, so the
# property is exact. Linear zero rates need not be monotone between pillars, and are left out.
@SETTINGS
@given(forwards, st.lists(st.integers(min_value=1, max_value=2000), min_size=12, max_size=12),
       st.just("LOG_LINEAR_DF"),
       st.lists(st.integers(min_value=0, max_value=20000), min_size=2, max_size=20))
def test_discount_factors_never_rise_when_forwards_are_not_negative(rates, gaps, interp, offsets):
    data = _curve(rates, gaps, interp)
    last = data.dates[-1]
    days = sorted({min(o, (last - AS_OF).days) for o in offsets})
    factors, _ = curves.discount(data, [AS_OF + timedelta(days=k) for k in days])
    assert factors[0] <= 1.0 + 1e-15
    for a, b in itertools.pairwise(factors):
        assert b <= a * (1 + 1e-14)


@SETTINGS
@given(st.floats(min_value=0.0005, max_value=0.08), st.floats(min_value=0.0005, max_value=0.05),
       st.sampled_from((0.01, 0.05)), st.floats(min_value=0.0, max_value=1.2),
       st.floats(min_value=0.0, max_value=0.6), st.integers(min_value=30, max_value=360))
def test_cds_index_option_parity(hazard, strike, coupon, v, recovery, days):
    from quantforge_core import credit_options

    as_of = date(2026, 11, 9)
    args = (as_of, as_of + timedelta(days=days), date(2031, 12, 20), 0.03, hazard, recovery)
    try:
        payer = credit_options.cds_index_option_price(*args, "PAYER", strike, coupon, 1e7, v)
    except QfError as e:
        assert e.code == "E_DOMAIN"  # K_adj <= 0 far below a large coupon (ruling F-10)
        return
    receiver = credit_options.cds_index_option_price(*args, "RECEIVER", strike, coupon, 1e7, v)
    parity = 1e7 * payer["risky_annuity"] * (payer["adjusted_forward"] - payer["adjusted_strike"])
    assert payer["price"] - receiver["price"] == pytest.approx(parity, rel=1e-10, abs=1e-6)
