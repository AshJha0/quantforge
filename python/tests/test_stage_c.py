"""Stage C checks that the golden suites do not make on their own."""
import json
import math

import pytest

from quantforge_core import black, equity, sabr, smile
from quantforge_core.black import BACHELIER, BLACK_76, BLACK_SCHOLES, Option
from quantforge_core.cli.main import run_case
from quantforge_core.errors import QfError


def _run(operation, inputs):
    document = {
        "schema_version": "1.0", "case_id": "t", "operation": operation, "inputs": inputs,
    }
    return run_case(json.dumps(document))


def test_flat_forward_carries_dividends_on_the_carry_factor():
    assert equity.flat(100, 0.04, 0.05, 1, [(0.5, 2)]) == pytest.approx(97.0149584, abs=1e-7)


def test_parity_fits_discount_factor_and_forward_from_exact_quotes():
    quotes = [
        equity.ParityQuote(k, c - 0.1, c + 0.1, p - 0.1, p + 0.1)
        for k, c, p in ((90, 15.0, 15.0 - 0.97 * 12.5), (110, 5.0, 5.0 + 0.97 * 7.5))
    ]
    f, d, residual, outside = equity.parity(quotes, None)
    assert (f, d) == (pytest.approx(102.5), pytest.approx(0.97))
    assert residual < 1e-12 and outside == []


@pytest.mark.parametrize("option_type", ["CALL", "PUT"])
def test_put_call_parity_and_implied_round_trip(option_type):
    o = Option(BLACK_76, option_type, 110, 1.5, 100, discount_factor=0.95, shift=5)
    assert black.implied(o, black.price(o, 0.3)) == pytest.approx(0.3, abs=1e-11)
    call = black.price(Option(BLACK_76, "CALL", 110, 1.5, 100, discount_factor=0.95), 0.3)
    put = black.price(Option(BLACK_76, "PUT", 110, 1.5, 100, discount_factor=0.95), 0.3)
    assert call - put == pytest.approx(0.95 * (100 - 110), abs=1e-12)


def test_bachelier_implied_survives_a_vanishing_start_vega():
    o = Option(BACHELIER, "CALL", 130, 0.5, 100, discount_factor=0.985)
    assert black.implied(o, black.price(o, 25.0)) == pytest.approx(25.0, abs=1e-9)


@pytest.mark.parametrize(
    "o",
    [
        Option(BLACK_SCHOLES, "CALL", 95, 0.8, 100, rate=0.03, dividend_yield=0.01),
        Option(BLACK_76, "PUT", 105, 0.8, 100, discount_factor=0.97, shift=2),
        Option(BACHELIER, "CALL", 95, 0.8, 100, discount_factor=0.97),
    ],
)
def test_analytic_greeks_agree_with_bumps(o):
    vol = 20.0 if o.model == BACHELIER else 0.25
    analytic, bumped = black.greeks(o, vol), black.bump_greeks(o, vol)
    for name, value in bumped.items():
        assert analytic[name] == pytest.approx(value, abs=2e-4, rel=1e-4)


def test_spot_delta_round_trip():
    strike = smile.delta_to_strike(100, 0.2, 1, "PUT", -0.2, "SPOT", 0.98)
    assert smile.delta_from_strike(100, 0.2, 1, "PUT", strike, "SPOT", 0.98) == pytest.approx(-0.2)


def test_svi_fit_recovers_known_parameters_with_weights():
    truth = smile.Svi(0.03, 0.12, -0.35, 0.02, 0.15)
    ks = [-0.5, -0.3, -0.1, 0.0, 0.1, 0.3, 0.5]
    fit, rmse = smile.svi_calibrate(ks, [truth.total_variance(k) for k in ks], [2.0] * 7)
    assert rmse < 1e-9 and fit.rho == pytest.approx(truth.rho, abs=1e-6)


def test_surface_is_flat_in_vol_beyond_both_ends():
    s = smile.Surface([0.5, 1.0], [-0.1, 0.1], [[0.2, 0.2], [0.25, 0.25]])
    _, vols = smile.surface_query(s, [(0.1, 0.0), (3.0, 5.0)])
    assert vols == [pytest.approx(0.2), pytest.approx(0.25)]


def test_arbfree_conserves_mass_and_mean_and_stays_non_negative():
    p = sabr.Sabr(1.0, 1.0, 0.3, 0.5, -0.3, 0.4)
    r = sabr.arbfree(p, 200, 50, 50, [0.8, 1.0, 1.2])
    assert r["mass"] == pytest.approx(1.0, abs=1e-11)
    assert r["mean"] == pytest.approx(1.0, abs=1e-10)
    assert r["min_density"] >= 0


def test_density_reject_is_arbitrage_error():
    p = sabr.Sabr(0.02, 20.0, 0.03, 0.5, -0.3, 0.5)
    with pytest.raises(QfError) as e:
        sabr.density(p, [0.001, 0.02], 0.0002, "REJECT")
    assert e.value.code == "E_ARBITRAGE"


@pytest.mark.parametrize(
    "operation, inputs",
    [
        (
            "vol.option.price",
            {"model": "BLACK_76", "option_type": "CALL", "strike": 1.0, "expiry_years": 1.0,
             "forward": 1.0, "discount_factor": 1.0, "vol": 0.2, "shift": None},
        ),
        (
            "vol.option.price",
            {"model": "BACHELIER", "option_type": "CALL", "strike": 1.0, "expiry_years": 1.0,
             "forward": 1.0, "discount_factor": 1.0, "vol": 0.2, "shift": 0.0},
        ),
        (
            "vol.delta.to_strike",
            {"forward": 100.0, "vol": 0.2, "expiry_years": 1.0, "option_type": "CALL",
             "delta": 0.25, "convention": "FORWARD"},
        ),
        ("eq.forward.parity", {"quotes": []}),
    ],
)
def test_ruling_c8_c9_schema_errors(operation, inputs):
    assert _run(operation, inputs)["error"]["code"] == "E_SCHEMA"


def test_small_values_use_the_lower_tail():
    assert black.big_n(-30) > 0 and math.isclose(black.big_n(0), 0.5)
