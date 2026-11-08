"""Stage E, E2 unit tests: identities and limits from heston-family.md. The goldens run in
test_conformance.py."""
import json
import math

import pytest

from quantforge_core import heston as hm
from quantforge_core import vol_e1
from quantforge_core.cli.main import run_case
from quantforge_core.errors import QfError
from quantforge_core.smile import Svi

H = hm.Heston(0.04, 1.5, 0.04, 0.5, -0.7)
KS = [70.0, 90.0, 100.0, 110.0, 140.0]


def code(f, *args):
    with pytest.raises(QfError) as e:
        f(*args)
    return e.value.code


def _bs(phi, s, k, t, r, q, v):
    return hm._bs(phi, s, k, t, r, q, v)


def test_cf_martingale_and_errors():
    assert hm.heston_phi(H, 1.0)(-1j) == pytest.approx(1.0, abs=1e-14)
    re, im = hm.heston_cf(1.0, H, [0.0, 1.0])
    assert (re[0], im[0]) == (1.0, 0.0)
    assert code(hm.heston_cf, 1.0, H, []) == "E_INPUT"
    assert code(hm.heston_cf, 0.0, H, [1.0]) == "E_DOMAIN"
    assert code(hm.heston_cf, 1.0, H, [-1.0]) == "E_DOMAIN"


def test_heston_parity_and_small_xi_limit():
    calls = hm.heston_price(100.0, KS, 1.0, 0.03, 0.01, H, "CALL")
    puts = hm.heston_price(100.0, KS, 1.0, 0.03, 0.01, H, "PUT")
    for k, c, p in zip(KS, calls, puts, strict=True):
        assert c - p == pytest.approx(100 * math.exp(-0.01) - k * math.exp(-0.03), abs=1e-10)
    small = hm.Heston(0.06, 2.0, 0.03, 1e-3, -0.5)
    vbar = 0.03 + (0.06 - 0.03) * (1 - math.exp(-2.0)) / 2.0
    price = hm.heston_price(100.0, [100.0], 1.0, 0.02, 0.0, small, "CALL")[0]
    assert price == pytest.approx(_bs(1.0, 100.0, 100.0, 1.0, 0.02, 0.0, math.sqrt(vbar)),
                                  abs=1e-3)


@pytest.mark.parametrize("field,value", [("v0", 0.0), ("kappa", 0.0), ("theta", 0.0),
                                         ("xi", 0.0), ("rho", 1.0)])
def test_heston_domain(field, value):
    bad = hm.Heston(**{**H.__dict__, field: value})
    assert code(hm.heston_price, 100.0, KS, 1.0, 0.0, 0.0, bad, "CALL") == "E_DOMAIN"


def test_common_checks():
    f = hm.heston_price
    assert code(f, 100.0, [], 1.0, 0.0, 0.0, H, "CALL") == "E_INPUT"
    assert code(f, 0.0, KS, 1.0, 0.0, 0.0, H, "CALL") == "E_DOMAIN"
    assert code(f, 100.0, [0.0], 1.0, 0.0, 0.0, H, "CALL") == "E_DOMAIN"
    assert code(f, 100.0, KS, 0.0, 0.0, 0.0, H, "CALL") == "E_DOMAIN"


def test_bates_without_jumps_is_heston_and_merton_matches_lewis():
    none = hm.Jumps(0.0, -0.1, 0.15)
    assert hm.bates_price(100.0, KS, 1.0, 0.03, 0.01, H, none, "PUT") == pytest.approx(
        hm.heston_price(100.0, KS, 1.0, 0.03, 0.01, H, "PUT"), abs=1e-12)
    jumps = hm.Jumps(0.5, -0.1, 0.2)
    series = hm.merton_price(100.0, KS, 1.0, 0.03, 0.01, 0.2, jumps, "CALL")

    def phi(u):
        import cmath
        return cmath.exp(-0.04 * (u * u + 1j * u) / 2) * hm._jump_phi(jumps, 1.0)(u)

    lewis = hm._lewis(phi, 100.0, KS, 1.0, 0.03, 0.01, True)
    assert series == pytest.approx(lewis, abs=1e-9)
    flat = hm.merton_price(100.0, [100.0], 1.0, 0.03, 0.01, 0.2, none, "PUT")[0]
    assert flat == pytest.approx(_bs(-1.0, 100.0, 100.0, 1.0, 0.03, 0.01, 0.2), abs=1e-14)
    assert code(hm.bates_price, 100.0, KS, 1.0, 0, 0, H, hm.Jumps(-1, 0, 0.1), "CALL") \
        == "E_DOMAIN"
    assert code(hm.merton_price, 100.0, KS, 1.0, 0, 0, 0.2, hm.Jumps(1, 0, -0.1), "CALL") \
        == "E_DOMAIN"
    assert code(hm.merton_price, 100.0, KS, 1.0, 0, 0, 0.0, none, "CALL") == "E_DOMAIN"


FLAT = [vol_e1.Slice(1.0, Svi(0.04, 0.0, 0.0, 0.0, 0.1))]
GRID = hm.Grid(41, 20, 20, math.log(100) - 1.0, math.log(100) + 1.0, 0.25)


def test_slv_flat_vol_zero_correlation_leverage_near_one():
    h = hm.Heston(0.04, 2.0, 0.04, 0.3, 0.0)
    out = hm.slv_leverage(100.0, 1.0, 0.0, 0.0, h, FLAT, GRID)
    lev, xs = out["leverage"], out["x"]
    i = min(range(len(xs)), key=lambda n: abs(xs[n] - math.log(100)))
    assert lev[i] == pytest.approx(1.0, abs=0.03)
    assert 0.95 < out["mass"] < 1.01


def test_slv_errors():
    h = hm.Heston(0.04, 2.0, 0.04, 0.3, -0.7)
    f = hm.slv_leverage
    assert code(f, 0.0, 1.0, 0, 0, h, FLAT, GRID) == "E_DOMAIN"
    assert code(f, 100.0, 0.0, 0, 0, h, FLAT, GRID) == "E_DOMAIN"
    assert code(f, 100.0, 1.0, 0, 0, h, FLAT, hm.Grid(4, 20, 20, 3.6, 5.6, 0.25)) == "E_INPUT"
    assert code(f, 100.0, 1.0, 0, 0, h, FLAT, hm.Grid(41, 20, 20, 4.7, 5.6, 0.25)) == "E_INPUT"
    assert code(f, 100.0, 1.0, 0, 0, h, FLAT, hm.Grid(41, 20, 20, 3.6, 5.6, 0.0)) == "E_DOMAIN"


def _run(operation, inputs):
    return run_case(json.dumps({"schema_version": "1.0", "case_id": "t", "operation": operation,
                                "inputs": inputs}))


HJ = {"v0": 0.04, "kappa": 1.5, "theta": 0.04, "xi": 0.5, "rho": -0.7}
JJ = {"intensity": 0.3, "mean_log_jump": -0.1, "log_jump_vol": 0.15}
COMMON = {"spot": 100.0, "strikes": [100.0], "expiry_years": 1.0, "rate": 0.03,
          "dividend_yield": 0.01, "option_type": "CALL"}


@pytest.mark.parametrize("operation,inputs,key", [
    ("vol.heston.price", {**COMMON, "heston": HJ}, "prices"),
    ("vol.heston.cf", {"expiry_years": 1.0, "heston": HJ, "u": [1.0]}, "re"),
    ("vol.bates.price", {**COMMON, "heston": HJ, "jumps": JJ}, "prices"),
    ("vol.merton.price", {**COMMON, "vol": 0.2, "jumps": JJ}, "prices"),
    ("vol.slv.leverage", {"spot": 100.0, "expiry_years": 1.0, "rate": 0.0, "dividend_yield": 0.0,
                          "heston": {**HJ, "xi": 0.3, "kappa": 2.0},
                          "slices": [{"expiry_years": 1.0, "svi": {"a": 0.04, "b": 0.0,
                                                                   "rho": 0.0, "m": 0.0,
                                                                   "sigma": 0.1}}],
                          "grid": {"nx": 11, "nv": 6, "nt": 3, "x_min": 4.0, "x_max": 5.2,
                                   "v_max": 0.2}}, "leverage"),
])
def test_cli(operation, inputs, key):
    r = _run(operation, inputs)
    assert r["status"] == "ok" and key in r["outputs"], r


def test_cli_slv_limit():
    r = _run("vol.slv.leverage", {"spot": 100.0, "expiry_years": 1.0, "rate": 0.0,
                                  "dividend_yield": 0.0, "heston": HJ, "slices": [],
                                  "grid": {"nx": 1001, "nv": 6, "nt": 3, "x_min": 4.0,
                                           "x_max": 5.2, "v_max": 0.2}})
    assert r["error"]["code"] == "E_LIMIT"
