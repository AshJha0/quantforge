"""Stage D wave 3 (D7 to D9): checks the golden suites do not make on their own."""
import math
from datetime import date

import pytest

from quantforge_core import stage_d3
from quantforge_core.curves import CurveData
from quantforge_core.errors import QfError

AS_OF = date(2026, 11, 6)


def _flat(rate=0.035):
    ds = (date(2027, 11, 8), date(2031, 11, 6), date(2046, 11, 6))
    return CurveData(AS_OF, "LOG_LINEAR_DF", ds,
                     tuple(math.exp(-rate * (d - AS_OF).days / 365) for d in ds))


def _code_of(f, *args):
    with pytest.raises(QfError) as e:
        f(*args)
    return e.value.code


# D7

@pytest.mark.parametrize("model,strike", [("BLACK_76", 0.035), ("BACHELIER", 0.035)])
def test_cap_minus_floor_is_swaplet_sum(model, strike):
    args = (_flat(), _flat(0.036), model, 0.2 if model == "BLACK_76" else 0.008)
    caps, cap = stage_d3.cap_price(*args, "CAP", 3, 12, strike, 1.0)
    floors, floor = stage_d3.cap_price(*args, "FLOOR", 3, 12, strike, 1.0)
    zero = stage_d3.cap_price(*args[:3], 0.0, "CAP", 3, 12, strike, 1.0)[0]
    assert len(caps) == 4
    assert [c - f for c, f in zip(caps, floors, strict=True)] == pytest.approx(
        [z - stage_d3.cap_price(*args[:3], 0.0, "FLOOR", 3, 12, strike, 1.0)[0][j]
         for j, z in enumerate(zero)], abs=1e-15)
    assert cap - floor == pytest.approx(sum(caps) - sum(floors))


def test_swaption_parity():
    args = (_flat(), _flat(0.036), "BLACK_76", 0.2)
    payer, f, a = stage_d3.swaption_price(*args, "PAYER", 12, 60, 0.035, 1.0)
    receiver, _, _ = stage_d3.swaption_price(*args, "RECEIVER", 12, 60, 0.035, 1.0)
    assert payer - receiver == pytest.approx(a * (f - 0.035), abs=1e-15)


@pytest.mark.parametrize("vol,start,strike,code", [
    (0.2, 0, 0.03, "E_INPUT"), ([0.2, 0.2], 3, 0.03, "E_INPUT"),
    (-0.1, 3, 0.03, "E_DOMAIN"), (0.2, 3, 0.0, "E_DOMAIN"),
])
def test_cap_checks(vol, start, strike, code):
    assert _code_of(stage_d3.cap_price, _flat(), _flat(), "BLACK_76", vol, "CAP", start, 12,
                    strike, 1.0) == code


def test_swaption_checks():
    args = (_flat(), _flat(), "BLACK_76")
    assert _code_of(stage_d3.swaption_price, *args, 0.2, "PAYER", 0, 60, 0.03, 1.0) == "E_INPUT"
    assert _code_of(stage_d3.swaption_price, *args, -0.2, "PAYER", 12, 60, 0.03,
                    1.0) == "E_DOMAIN"
    assert _code_of(stage_d3.swaption_price, *args, 0.2, "PAYER", 12, 60, -0.01,
                    1.0) == "E_DOMAIN"


# D8

Q = [(100, 3.0), (103, 3.5), (106, 3.2)]


def test_commodity_quotes_reprice_with_seasonality():
    season = [0.01 * k for k in range(12)]
    out = stage_d3.commodity_forwards(Q, season, [100, 103, 106, 101])
    assert out[:3] == pytest.approx([3.0, 3.5, 3.2], rel=1e-15)
    assert stage_d3.commodity_forwards([(100, 3.0)], None, [100]) == pytest.approx([3.0])


@pytest.mark.parametrize("quotes,season,months,code", [
    (Q[::-1], None, [101], "E_INPUT"), ([(100, 0.0), (101, 1.0)], None, [100], "E_DOMAIN"),
    (Q, [0.0] * 6, [101], "E_INPUT"), (Q, None, [99], "E_OUT_OF_RANGE"),
    (Q, None, [107], "E_OUT_OF_RANGE"), ([], None, [100], "E_INPUT"),
])
def test_commodity_checks(quotes, season, months, code):
    assert _code_of(stage_d3.commodity_forwards, quotes, season, months) == code


def test_storage_carry_identity_and_checks():
    fw = [(date(2027, 1, 1), 70.0), (date(2027, 7, 1), 72.0)]
    ys, values, flags = stage_d3.storage_carry(_flat(), fw, 0.02)
    dt = 181 / 365
    assert ys[0] == pytest.approx(0.035 + 0.02 - math.log(72 / 70) / dt, abs=1e-12)
    assert flags == [values[0] > 0]
    assert _code_of(stage_d3.storage_carry, _flat(), fw[:1], 0.0) == "E_INPUT"
    assert _code_of(stage_d3.storage_carry, _flat(), fw[::-1], 0.0) == "E_INPUT"
    assert _code_of(stage_d3.storage_carry, _flat(), fw, -0.01) == "E_DOMAIN"


# D9

POOL = (1e6, 0.06, 0.055, 120, 0, "PSA", 150.0)


def test_mbs_retires_balance_and_zero_prepay_is_level_pay():
    flows = stage_d3.mbs_cashflows(POOL)
    total = sum(flows["scheduled_principal"]) + sum(flows["prepayment"])
    assert total == pytest.approx(1e6, rel=1e-12)
    level = stage_d3.mbs_cashflows((1e6, 0.06, 0.06, 12, 0, "CPR", 0.0))
    r = 0.005
    payment = 1e6 * r / (1 - (1 + r) ** -12)
    assert level["interest"][0] + level["scheduled_principal"][0] == pytest.approx(payment)


def test_mbs_par_price_at_coupon_yield_without_delay():
    price, duration, wal = stage_d3.mbs_price((1e6, 0.06, 0.06, 60, 0, "CPR", 0.1), 0.06, 0)
    assert price == pytest.approx(100, abs=1e-10) and 0 < duration < wal


@pytest.mark.parametrize("pool,code", [
    ((1e6, 0.06, 0.07, 60, 0, "PSA", 100.0), "E_INPUT"),
    ((1e6, 0.06, 0.05, 0, 0, "PSA", 100.0), "E_INPUT"),
    ((1e6, 0.06, 0.05, 60, -1, "PSA", 100.0), "E_INPUT"),
    ((1e6, 0.0, 0.05, 60, 0, "PSA", 100.0), "E_DOMAIN"),
    ((0.0, 0.06, 0.05, 60, 0, "PSA", 100.0), "E_DOMAIN"),
    ((1e6, 0.06, 0.05, 60, 0, "CPR", 1.0), "E_DOMAIN"),
    ((1e6, 0.06, 0.05, 60, 0, "PSA", -1.0), "E_DOMAIN"),
])
def test_mbs_checks(pool, code):
    assert _code_of(stage_d3.mbs_cashflows, pool) == code


def test_mbs_delay_check():
    assert _code_of(stage_d3.mbs_price, POOL, 0.05, -1) == "E_INPUT"
