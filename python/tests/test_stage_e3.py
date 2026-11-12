"""Stage E, E3 FX smile unit tests: identities from fx-smile.md. The goldens run in
test_conformance.py."""
import math

import pytest

from quantforge_core import fx_smile as fx
from quantforge_core.errors import QfError

EUR = (1.085, 0.25, 0.043, 0.031)  # spot, T, rd, rf
MXN = (18.4, 1.0, 0.105, 0.043)


def code(f, *args):
    with pytest.raises(QfError) as e:
        f(*args)
    return e.value.code


def test_price_parity_and_greeks() -> None:
    call = fx.option_price(*EUR[:1], 1.1, *EUR[1:], 0.075, "CALL", 1e6)
    put = fx.option_price(*EUR[:1], 1.1, *EUR[1:], 0.075, "PUT", 1e6)
    s, t, rd, rf = EUR
    parity = 1e6 * (s * math.exp(-rf * t) - 1.1 * math.exp(-rd * t))
    assert call["price"] - put["price"] == pytest.approx(parity, rel=1e-12)
    assert call["delta"] - put["delta"] == pytest.approx(1e6 * math.exp(-rf * t), rel=1e-12)
    assert call["gamma"] == put["gamma"] and call["vega"] == put["vega"]
    assert call["premium_pct_foreign"] == pytest.approx(call["price"] / 1e6 / s)
    h = 1e-4
    up = fx.option_price(*EUR[:1], 1.1, *EUR[1:], 0.075 + h, "CALL", 1e6)["price"]
    down = fx.option_price(*EUR[:1], 1.1, *EUR[1:], 0.075 - h, "CALL", 1e6)["price"]
    assert call["vega"] == pytest.approx((up - down) / (2 * h), rel=1e-6)


@pytest.mark.parametrize("bad", [(0.0, 1.1, 0.25, 0.075, 1.0), (1.0, 0.0, 0.25, 0.075, 1.0),
                                 (1.0, 1.1, 0.0, 0.075, 1.0), (1.0, 1.1, 0.25, 0.0, 1.0),
                                 (1.0, 1.1, 0.25, 0.075, 0.0)])
def test_price_domain(bad) -> None:
    s, k, t, v, n = bad
    assert code(fx.option_price, s, k, t, 0.0, 0.0, v, "CALL", n) == "E_DOMAIN"


@pytest.mark.parametrize("market", [EUR, MXN])
@pytest.mark.parametrize("option", ["CALL", "PUT"])
@pytest.mark.parametrize("kind", fx.DELTA_TYPES)
def test_to_strike_inverts_from_strike(market, option, kind) -> None:
    s, t, rd, rf = market
    strike = s * (1.04 if option == "CALL" else 0.96)
    delta = fx.delta_from_strike(s, strike, t, rd, rf, 0.16, option)[kind]
    back = fx.delta_to_strike(s, t, rd, rf, 0.16, option, delta, kind)
    assert back == pytest.approx(strike, rel=1e-11)


def test_pa_call_upper_root_and_maximum() -> None:
    s, t, rd, rf = MXN
    m = fx._Market(s, t, rd, rf, 0.16)
    peak = m.forward * math.exp(fx._pa_call_peak(m))
    top = m.delta("FORWARD_PA", 1.0, peak)
    for k in (peak * 0.99, peak * 1.01):
        assert m.delta("FORWARD_PA", 1.0, k) < top
    low_strike = peak * 0.8
    delta = m.delta("FORWARD_PA", 1.0, low_strike)
    upper = fx.delta_to_strike(s, t, rd, rf, 0.16, "CALL", delta, "FORWARD_PA")
    assert upper > peak and m.delta("FORWARD_PA", 1.0, upper) == pytest.approx(delta)
    assert code(fx.delta_to_strike, s, t, rd, rf, 0.16, "CALL", top * 1.0001,
                "FORWARD_PA") == "E_DOMAIN"


def test_to_strike_ranges() -> None:
    s, t, rd, rf = MXN
    f = fx.delta_to_strike
    assert code(f, s, t, rd, rf, 0.16, "CALL", -0.25, "SPOT") == "E_DOMAIN"
    assert code(f, s, t, rd, rf, 0.16, "PUT", 0.25, "SPOT_PA") == "E_DOMAIN"
    assert code(f, s, t, rd, rf, 0.16, "CALL", 0.97, "SPOT") == "E_DOMAIN"
    assert code(f, s, t, rd, rf, 0.16, "PUT", -1.0, "FORWARD") == "E_DOMAIN"
    assert code(f, 0.0, t, rd, rf, 0.16, "PUT", -0.25, "FORWARD") == "E_DOMAIN"
    assert f(s, t, rd, rf, 0.16, "PUT", -3.0, "SPOT_PA") > s  # PA put: any negative delta


def test_atm_strikes() -> None:
    s, t, rd, rf = EUR
    forward = s * math.exp((rd - rf) * t)
    assert fx.atm_strike(s, t, rd, rf, 0.1, "SPOT", "SPOT") == s
    assert fx.atm_strike(s, t, rd, rf, 0.1, "FORWARD", "SPOT_PA") == forward
    dns = fx.atm_strike(s, t, rd, rf, 0.1, "DNS", "FORWARD")
    assert dns == pytest.approx(forward * math.exp(0.005 * t))
    pa = fx.atm_strike(s, t, rd, rf, 0.1, "DNS", "SPOT_PA")
    assert pa == pytest.approx(forward * math.exp(-0.005 * t))
    # DNS: call and put deltas of the same type sum to zero
    for kind, k in (("SPOT", dns), ("SPOT_PA", pa)):
        d = fx.delta_from_strike(s, k, t, rd, rf, 0.1, "CALL")[kind]
        p = fx.delta_from_strike(s, k, t, rd, rf, 0.1, "PUT")[kind]
        assert d + p == pytest.approx(0.0, abs=1e-15)
    assert code(fx.atm_strike, s, t, rd, rf, 0.0, "DNS", "SPOT") == "E_DOMAIN"


def test_smile_from_quotes() -> None:
    out = fx.smile_from_quotes(*EUR, 0.075, -0.0045, 0.002, 0.25, "SPOT", "DNS")
    assert out["call_vol"] == pytest.approx(0.07475)
    assert out["put_vol"] == pytest.approx(0.07925)
    assert out["put_strike"] < out["atm_strike"] < out["call_strike"]
    f = fx.smile_from_quotes
    assert code(f, *EUR, 0.075, -0.0045, 0.002, 0.5, "SPOT", "DNS") == "E_DOMAIN"
    assert code(f, *EUR, 0.075, -0.0045, -0.2, 0.25, "SPOT", "DNS") == "E_DOMAIN"
    assert code(f, *EUR, 0.075, 0.2, 0.0, 0.25, "SPOT", "DNS") == "E_DOMAIN"


_M = {"spot": 1.085, "expiry_years": 0.25, "domestic_rate": 0.043, "foreign_rate": 0.031}


@pytest.mark.parametrize("operation,extra,key", [
    ("fx.option.price", {"strike": 1.1, "vol": 0.075, "option_type": "PUT", "notional": 1e6},
     "price"),
    ("fx.delta.from_strike", {"strike": 1.1, "vol": 0.075, "option_type": "CALL"}, "deltas"),
    ("fx.delta.to_strike", {"vol": 0.075, "option_type": "CALL", "delta": 0.25,
                            "delta_type": "SPOT_PA"}, "strike"),
    ("fx.atm.strike", {"vol": 0.075, "atm_type": "DNS", "delta_type": "FORWARD"}, "strike"),
    ("fx.smile.from_quotes", {"atm_vol": 0.075, "rr": -0.0045, "bf": 0.002, "delta": 0.25,
                              "delta_type": "FORWARD", "atm_type": "FORWARD"}, "call_strike"),
])
def test_cli(operation, extra, key) -> None:
    import json

    from quantforge_core.cli.main import run_case
    r = run_case(json.dumps({"schema_version": "1.0", "case_id": "t", "operation": operation,
                             "inputs": {**_M, **extra}}))
    assert r["status"] == "ok" and key in r["outputs"], r
