"""Stage E, E4 unit tests (rates-vol-cube.md). The cube and strip cases take their curves from the
first golden case of datasets/golden/stage_e_b/ratesvol_e.json; the goldens run in
test_conformance.py."""
import copy
import json
import math
from pathlib import Path

import pytest

from quantforge_core import black, rates_vol
from quantforge_core.cli.main import run_case
from quantforge_core.errors import QfError

GOLDEN = Path(__file__).resolve().parents[2] / "datasets/golden/stage_e_b/ratesvol_e.json"


def _base(operation):
    cases = json.loads(GOLDEN.read_text(encoding="utf-8"))["cases"]
    case = next(c for c in cases if c["operation"] == operation
                and c["expected"]["status"] == "ok")
    return copy.deepcopy(case["inputs"])


def run(operation, inputs):
    return run_case(json.dumps({"schema_version": "1.0", "case_id": "t", "operation": operation,
                                "inputs": inputs}))


def error(operation, inputs):
    r = run(operation, inputs)
    assert r["status"] == "error", r
    return r["error"]["code"]


def code(f, *args):
    with pytest.raises(QfError) as e:
        f(*args)
    return e.value.code


def test_cube_node_and_between():
    inputs = _base("rates.swaption.price_cube")
    out = run("rates.swaption.price_cube", inputs)["outputs"]
    assert out["sabr"]["rho"] == pytest.approx(-0.27)
    inputs["trade"]["expiry_months"] = 18
    between = run("rates.swaption.price_cube", inputs)["outputs"]["sabr"]["rho"]
    assert -0.29 < between < -0.27
    inputs["trade"]["type"] = "RECEIVER"
    assert run("rates.swaption.price_cube", inputs)["status"] == "ok"


@pytest.mark.parametrize("change,expected", [
    (lambda i: i["trade"].update(expiry_months=3), "E_INPUT"),
    (lambda i: i["trade"].update(tenor_months=240), "E_INPUT"),
    (lambda i: i["trade"].update(expiry_months=0), "E_INPUT"),
    (lambda i: i["cube"]["alpha"].pop(), "E_INPUT"),
    (lambda i: i["cube"].update(expiries_months=[6, 6, 24, 60]), "E_INPUT"),
    (lambda i: i["cube"]["alpha"][0].__setitem__(0, 0.0), "E_DOMAIN"),
    (lambda i: i["cube"]["beta"][0].__setitem__(0, 1.5), "E_DOMAIN"),
    (lambda i: i["cube"]["rho"][3].__setitem__(2, 1.0), "E_DOMAIN"),
    (lambda i: i["cube"]["nu"][0].__setitem__(0, -0.1), "E_DOMAIN"),
    (lambda i: i["trade"].update(strike=0.0), "E_DOMAIN"),
    (lambda i: i["cube"].update(alpha="x"), "E_SCHEMA"),
])
def test_cube_errors(change, expected):
    inputs = _base("rates.swaption.price_cube")
    change(inputs)
    assert error("rates.swaption.price_cube", inputs) == expected


def test_locate_single_node():
    assert rates_vol._locate([1.0], 1.0, "x") == (0, 0.0)
    assert code(rates_vol._locate, [1.0], 1.5, "x") == "E_INPUT"


def test_strip_reprices_every_cap():
    inputs = _base("rates.cap.strip")
    out = run("rates.cap.strip", inputs)["outputs"]
    vols = out["caplet_vols"]
    assert vols[0] == pytest.approx(inputs["flat_vols"][0], rel=1e-12)
    assert vols[3] == vols[0] and vols[4] < vols[0]
    for model in ("BACHELIER",):
        bach = dict(inputs, model=model, flat_vols=[0.0085, 0.0084, 0.0082, 0.0081, 0.008])
        assert run("rates.cap.strip", bach)["status"] == "ok"


@pytest.mark.parametrize("change,expected", [
    ({"flat_vols": [0.24, 0.10, 0.05, 0.02, 0.01]}, "E_ARBITRAGE"),
    ({"cap_tenors_months": [12, 24, 36, 48, 61]}, "E_INPUT"),
    ({"cap_tenors_months": [12, 36, 24, 48, 60]}, "E_INPUT"),
    ({"flat_vols": [0.24]}, "E_INPUT"),
    ({"flat_vols": [0.24, 0.0, 0.2, 0.2, 0.2]}, "E_DOMAIN"),
    ({"start_months": 0}, "E_INPUT"),
    ({"strike": -0.01}, "E_DOMAIN"),
    ({"cap_tenors_months": [12.5]}, "E_SCHEMA"),
])
def test_strip_errors(change, expected):
    assert error("rates.cap.strip", {**_base("rates.cap.strip"), **change}) == expected


def test_bond_futures_round_trip():
    price, value = rates_vol.bondfut_price("PUT", 111.25, 112.0, 0.1, 0.9962, 0.055, 1e5)
    assert value == pytest.approx(price * 1000)
    vol, yield_vol = rates_vol.bondfut_implied("PUT", 111.25, 112.0, 0.1, 0.9962, price, 0.0425,
                                               6.4)
    assert vol == pytest.approx(0.055, rel=1e-12)
    assert yield_vol == pytest.approx(0.055 / (6.4 * 0.0425), rel=1e-12)
    f = rates_vol.bondfut_implied
    assert code(f, "CALL", 111.25, 100.0, 0.1, 0.99, 11.0, 0.04, 6.0) == "E_DOMAIN"
    assert code(f, "CALL", 111.25, 100.0, 0.1, 0.99, 111.0, 0.04, 6.0) == "E_DOMAIN"
    for bad in ((0.0, 100.0, 0.1, 0.99), (100.0, 0.0, 0.1, 0.99), (100.0, 100.0, 0.0, 0.99),
                (100.0, 100.0, 0.1, 0.0)):
        fp, k, t, df = bad
        assert code(rates_vol.bondfut_price, "CALL", fp, k, t, df, 0.05, 1e5) == "E_DOMAIN"


def test_yoy_and_zc():
    periods = [(1.0, 0.96, 0.0285, 0.75, 0.35), (1.0, 0.93, 0.0262, 1.75, 0.33)]
    caplets, price = rates_vol.yoy_price("BLACK_76", "CAP", 0.03, 1e7, periods)
    assert price == caplets[0] + caplets[1]
    one = 1e7 * 0.96 * black.price(black.Option("BLACK_76", "CALL", 0.03, 0.75, 0.0285), 0.35)
    assert caplets[0] == pytest.approx(one, rel=1e-14)
    floors = rates_vol.yoy_price("BACHELIER", "FLOOR", -0.01, 1e7,
                                 [(1.0, 0.96, -0.005, 0.75, 0.01)])[1]
    assert floors > 0
    assert code(rates_vol.yoy_price, "BLACK_76", "CAP", 0.03, 1e7, []) == "E_INPUT"
    assert code(rates_vol.yoy_price, "BLACK_76", "CAP", 0.0, 1e7, periods) == "E_DOMAIN"
    assert code(rates_vol.yoy_price, "BACHELIER", "CAP", 0.03, 1e7,
                [(1.0, 0.96, 0.03, 0.0, 0.01)]) == "E_DOMAIN"
    price, ratio = rates_vol.zc_price("BLACK_76", "CAP", 1.1268, 5.0, 0.025, 0.8305, 0.028, 1e7)
    assert ratio == pytest.approx(1.025**5) and price > 0
    f = rates_vol.zc_price
    assert code(f, "BLACK_76", "CAP", 0.0, 5.0, 0.025, 0.83, 0.028, 1e7) == "E_DOMAIN"
    assert code(f, "BACHELIER", "CAP", 1.1, 5.0, -1.5, 0.83, 0.028, 1e7) == "E_DOMAIN"
    assert code(f, "BLACK_76", "FLOOR", 1.1, 0.0, 0.025, 0.83, 0.028, 1e7) == "E_DOMAIN"
    assert math.isfinite(f("BACHELIER", "FLOOR", 1.1, 2.5, 0.02, 0.9, 0.03, 1e7)[0])


@pytest.mark.parametrize("operation", ["rates.bondfut.option_price", "rates.bondfut.implied_vol",
                                       "infl.cap.yoy_price", "infl.cap.zc_price"])
def test_cli(operation):
    assert run(operation, _base(operation))["status"] == "ok"
