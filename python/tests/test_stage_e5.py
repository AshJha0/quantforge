"""Stage E, E5 unit tests: identities from 04-pricing/exotics.md. The goldens run in
test_conformance.py."""
import json
import math

import pytest

from quantforge_core import exotics as ex
from quantforge_core.cli.main import run_case
from quantforge_core.errors import QfError

S, K, T, R, Q, V = 100.0, 100.0, 1.0, 0.05, 0.02, 0.25


def code(f, *args):
    with pytest.raises(QfError) as e:
        f(*args)
    return e.value.code


def vanilla(kind, s=S, k=K):
    return ex.gbs(1.0 if kind == "CALL" else -1.0, s, k, T, R, R - Q, V)


def test_digitals_add_up():
    for kind in ("CALL", "PUT"):
        cash = ex.digital(S, K, T, R, Q, V, kind, "CASH_OR_NOTHING", 1.0)
        asset = ex.digital(S, K, T, R, Q, V, kind, "ASSET_OR_NOTHING", 1.0)
        sign = 1 if kind == "CALL" else -1
        assert sign * (asset - K * cash) == pytest.approx(vanilla(kind), abs=1e-12)
    assert code(ex.digital, S, K, T, R, Q, V, "CALL", "CASH_OR_NOTHING", 0.0) == "E_DOMAIN"


@pytest.mark.parametrize("kind", ["CALL", "PUT"])
@pytest.mark.parametrize("k", [90.0, 110.0])
@pytest.mark.parametrize("h,side", [(80.0, "DOWN"), (120.0, "UP")])
def test_barrier_in_plus_out_is_vanilla(kind, k, h, side):
    knock_in = ex.barrier(S, k, T, R, Q, V, kind, h, 0.0, f"{side}_IN")
    knock_out = ex.barrier(S, k, T, R, Q, V, kind, h, 0.0, f"{side}_OUT")
    assert knock_in + knock_out == pytest.approx(vanilla(kind, k=k), abs=1e-10)
    assert ex.barrier(S, k, T, R, Q, V, kind, h, 2.0, f"{side}_OUT") > knock_out


def test_barrier_errors():
    assert code(ex.barrier, S, K, T, R, Q, V, "CALL", 100.0, 0.0, "DOWN_IN") == "E_DOMAIN"
    assert code(ex.barrier, S, K, T, R, Q, V, "CALL", 90.0, -1.0, "DOWN_IN") == "E_DOMAIN"
    assert code(ex.barrier, S, K, T, R, Q, V, "CALL", 0.0, 0.0, "DOWN_IN") == "E_DOMAIN"


def test_asian_geometric():
    cont = ex.asian_geometric(S, K, T, R, Q, V, "CALL", "CONTINUOUS", [])
    fine = ex.asian_geometric(S, K, T, R, Q, V, "CALL", "DISCRETE",
                              [i / 2000 for i in range(1, 2001)])
    assert fine == pytest.approx(cont, rel=2e-3) and cont < vanilla("CALL")
    one = ex.asian_geometric(S, K, T, R, Q, V, "PUT", "DISCRETE", [T])
    assert one == pytest.approx(vanilla("PUT"), abs=1e-12)
    f = ex.asian_geometric
    assert code(f, S, K, T, R, Q, V, "CALL", "CONTINUOUS", [0.5]) == "E_INPUT"
    assert code(f, S, K, T, R, Q, V, "CALL", "DISCRETE", []) == "E_INPUT"
    assert code(f, S, K, T, R, Q, V, "CALL", "DISCRETE", [0.5, 0.4]) == "E_INPUT"
    assert code(f, S, K, T, R, Q, V, "CALL", "DISCRETE", [0.5, 1.5]) == "E_INPUT"


def test_lookback():
    call = ex.lookback(S, T, R, Q, V, "CALL", S)
    put = ex.lookback(S, T, R, Q, V, "PUT", S)
    assert call > vanilla("CALL") and put > vanilla("PUT")
    assert code(ex.lookback, S, T, R, Q, V, "CALL", 101.0) == "E_DOMAIN"
    assert code(ex.lookback, S, T, R, Q, V, "PUT", 99.0) == "E_DOMAIN"
    assert code(ex.lookback, S, T, R, R, V, "CALL", 90.0) == "E_DOMAIN"


def test_quanto_chooser_kirk_basket():
    assert ex.quanto(S, K, T, R, 0.03, Q, V, 0.1, 0.0, "CALL") == pytest.approx(
        ex.gbs(1.0, S, K, T, R, 0.03 - Q, V))
    assert code(ex.quanto, S, K, T, R, 0.03, Q, V, 0.1, 1.5, "CALL") == "E_DOMAIN"
    at_expiry = ex.chooser(S, K, T, R, Q, V, T)
    assert at_expiry == pytest.approx(vanilla("CALL") + vanilla("PUT"), abs=1e-12)
    assert ex.chooser(S, K, T, R, Q, V, 0.25) < at_expiry
    assert code(ex.chooser, S, K, T, R, Q, V, 1.5) == "E_INPUT"
    margrabe = ex.kirk(100.0, 95.0, 0.0, T, R, 0.3, 0.2, 0.5)
    sv = math.sqrt(0.09 - 2 * 0.5 * 0.06 + 0.04)
    assert margrabe == pytest.approx(math.exp(-R) * ex.gbs(1.0, 100.0, 95.0, T, 0.0, 0.0, sv))
    assert code(ex.kirk, 100.0, 5.0, -6.0, T, R, 0.3, 0.2, 0.5) == "E_DOMAIN"
    assert code(ex.kirk, 100.0, 95.0, 0.0, T, R, 0.3, 0.2, 1.5) == "E_DOMAIN"
    single = ex.basket([100.0], [1.0], [0.2], [[1.0]], 100.0, T, R, "CALL")
    assert single["basket_vol"] == pytest.approx(0.2)
    pair = ex.basket([100.0, 50.0], [0.5, 1.0], [0.2, 0.3], [[1.0, 0.4], [0.4, 1.0]], 100.0, T,
                     R, "PUT")
    assert pair["basket_forward"] == 100.0 and pair["price"] > 0
    f = ex.basket
    assert code(f, [100.0], [1.0, 1.0], [0.2], [[1.0]], K, T, R, "CALL") == "E_INPUT"
    assert code(f, [100.0, 50.0], [1, 1], [0.2, 0.2], [[1, 0.4], [0.3, 1]], K, T, R,
                "CALL") == "E_INPUT"
    assert code(f, [100.0], [-1.0], [0.2], [[1.0]], K, T, R, "CALL") == "E_DOMAIN"
    assert code(f, [0.0], [1.0], [0.2], [[1.0]], K, T, R, "CALL") == "E_DOMAIN"
    assert code(f, [100.0], [1.0], [0.0], [[1.0]], K, T, R, "CALL") == "E_DOMAIN"


def test_american_crr_baw_fd_agree():
    tree = ex.crr(S, K, T, R, Q, V, "PUT", 500)
    assert tree["european"] == pytest.approx(vanilla("PUT"), abs=2e-2)
    assert tree["early_exercise_premium"] > 0
    assert ex.baw(S, K, T, R, Q, V, "PUT") == pytest.approx(tree["american"], abs=5e-2)
    fd = ex.fd(S, K, T, R, Q, V, "PUT", "AMERICAN", 201, 200, 5.0)
    assert fd["price"] == pytest.approx(tree["american"], abs=2e-2) and fd["delta"] < 0
    euro = ex.fd(S, K, T, R, Q, V, "CALL", "EUROPEAN", 201, 200, 5.0)
    assert euro["price"] == pytest.approx(vanilla("CALL"), abs=2e-2)
    call = ex.baw(S, K, T, R, 0.08, V, "CALL")
    assert call >= ex.gbs(1.0, S, K, T, R, R - 0.08, V)  # carry below r: early exercise pays
    assert ex.baw(S, K, T, R, 0.0, V, "CALL") == pytest.approx(ex.gbs(1.0, S, K, T, R, R, V))
    assert ex.baw(200.0, K, T, R, 0.08, V, "CALL") == pytest.approx(100.0)
    assert ex.baw(40.0, K, T, R, Q, V, "PUT") == pytest.approx(60.0)
    assert code(ex.baw, S, K, T, 0.0, Q, V, "PUT") == "E_DOMAIN"
    assert code(ex.crr, S, K, T, R, Q, V, "PUT", 0) == "E_INPUT"
    assert code(ex.crr, S, K, T, 5.0, Q, 0.01, "PUT", 1) == "E_DOMAIN"
    assert code(ex.fd, S, K, T, R, Q, V, "PUT", "AMERICAN", 200, 10, 5.0) == "E_INPUT"
    assert code(ex.fd, S, K, T, R, Q, V, "PUT", "AMERICAN", 201, 0, 5.0) == "E_INPUT"
    assert code(ex.fd, S, K, T, R, Q, V, "PUT", "AMERICAN", 201, 10, 0.0) == "E_DOMAIN"


COMMON = {"spot": S, "strike": K, "expiry_years": T, "rate": R, "dividend_yield": Q, "vol": V,
          "option_type": "CALL"}


@pytest.mark.parametrize("operation,extra", [
    ("exotic.digital.price", {"payoff": "CASH_OR_NOTHING", "cash": 1.0}),
    ("exotic.barrier.price", {"barrier": 80.0, "rebate": 0.0, "barrier_type": "DOWN_OUT"}),
    ("exotic.asian.geometric", {"averaging": "CONTINUOUS", "fixing_years": []}),
    ("exotic.chooser.price", {"choose_years": 0.5}),
    ("exotic.american.crr", {"steps": 50}),
    ("exotic.american.baw", {}),
    ("exotic.american.fd", {"exercise": "AMERICAN", "grid": {"nx": 51, "nt": 20, "width": 4.0}}),
])
def test_cli(operation, extra):
    r = run_case(json.dumps({"schema_version": "1.0", "case_id": "t", "operation": operation,
                             "inputs": {**COMMON, **extra}}))
    assert r["status"] == "ok", r


@pytest.mark.parametrize("operation,inputs", [
    ("exotic.lookback.floating", {"spot": S, "expiry_years": T, "rate": R, "dividend_yield": Q,
                                  "vol": V, "option_type": "PUT", "running_extreme": 110.0}),
    ("exotic.quanto.price", {"spot": S, "strike": K, "expiry_years": T, "domestic_rate": R,
                             "foreign_rate": 0.03, "dividend_yield": Q, "vol": V, "fx_vol": 0.1,
                             "correlation": 0.3, "option_type": "PUT"}),
    ("exotic.spread.kirk", {"forward_1": 100.0, "forward_2": 95.0, "strike": 2.0,
                            "expiry_years": T, "rate": R, "vol_1": 0.3, "vol_2": 0.2,
                            "correlation": 0.5}),
    ("exotic.basket.moment", {"forwards": [100.0, 50.0], "weights": [0.5, 1.0],
                              "vols": [0.2, 0.3], "correlation": [[1.0, 0.4], [0.4, 1.0]],
                              "strike": 100.0, "expiry_years": T, "rate": R,
                              "option_type": "CALL"}),
    ("exotic.american.crr", {**COMMON, "steps": 20_001}),
])
def test_cli_other(operation, inputs):
    r = run_case(json.dumps({"schema_version": "1.0", "case_id": "t", "operation": operation,
                             "inputs": inputs}))
    expected = "error" if inputs.get("steps") == 20_001 else "ok"
    assert r["status"] == expected, r
