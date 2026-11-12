"""Stage E, E6 unit tests: worked examples from 06-risk/correlation.md. The goldens run in
test_conformance.py."""
import json
import math

import pytest

from quantforge_core import correlation as corr
from quantforge_core.cli.main import run_case
from quantforge_core.errors import QfError

HIGHAM = [[1.0, 1.0, 0.0], [1.0, 1.0, 1.0], [0.0, 1.0, 1.0]]


def code(f, *args):
    with pytest.raises(QfError) as e:
        f(*args)
    return e.value.code


def test_validate_higham_example() -> None:
    out = corr.validate(HIGHAM)
    assert out["min_eigenvalue"] == pytest.approx(1 - math.sqrt(2), abs=1e-12)
    assert (out["symmetric"], out["unit_diagonal"], out["in_range"]) == (True, True, True)
    assert out["psd"] is False and out["valid"] is False
    assert corr.validate([[1.0, 0.5], [0.4, 1.0]])["symmetric"] is False
    assert corr.validate([[2.0]])["unit_diagonal"] is False
    assert code(corr.validate, []) == "E_INPUT"
    assert code(corr.validate, [[1.0, 0.0]]) == "E_INPUT"


def test_nearest_higham_example() -> None:
    x, distance = corr.nearest(HIGHAM)
    assert x[0][1] == pytest.approx(0.760690, abs=2e-6)
    assert x[0][2] == pytest.approx(0.157298, abs=2e-6)
    assert x[1][1] == 1.0 and distance > 0
    valid = [[1.0, 0.3], [0.3, 1.0]]
    same, zero = corr.nearest(valid)
    assert same[0] == pytest.approx(valid[0]) and zero == pytest.approx(0.0, abs=1e-12)
    assert corr.nearest([[0.5]])[0] == [[1.0]]
    assert code(corr.nearest, [[1.0, 0.5], [0.4, 1.0]]) == "E_INPUT"


def test_implied_and_dispersion_examples() -> None:
    assert corr.implied([0.5, 0.5], [0.2, 0.3], 0.22) == pytest.approx(0.53, rel=1e-12)
    assert corr.implied([0.5, 0.5], [0.2, 0.3], 0.30) > 1  # not clipped (E-B20)
    assert code(corr.implied, [1.0], [0.2], 0.2) == "E_INPUT"
    assert code(corr.implied, [0.5, 0.5], [0.2], 0.2) == "E_INPUT"
    assert code(corr.implied, [0.5, 0.5], [0.2, 0.0], 0.2) == "E_DOMAIN"
    out = corr.dispersion([0.5, 0.5], [0.25, 0.30], 0.24, [0.28, 0.35], 0.22, 1e5)
    assert out["pnl"] == pytest.approx(6215.0, rel=1e-12)
    assert out["constituent_variance_notionals"] == pytest.approx([1e5, 83333.333333333])
    assert out["implied_correlation"] == pytest.approx(0.519, abs=1e-3)
    f = corr.dispersion
    assert code(f, [0.5, 0.5], [0.25], 0.24, [0.28, 0.35], 0.22, 1e5) == "E_INPUT"
    assert code(f, [0.5, 0.5], [0.25, 0.0], 0.24, [0.28, 0.35], 0.22, 1e5) == "E_DOMAIN"
    assert code(f, [0.5, 0.5], [0.25, 0.3], 0.24, [0.28, 0.35], 0.0, 1e5) == "E_DOMAIN"


@pytest.mark.parametrize("operation,inputs,key", [
    ("risk.corr.validate", {"matrix": HIGHAM}, "psd"),
    ("risk.corr.nearest", {"matrix": HIGHAM}, "frobenius_distance"),
    ("risk.corr.implied", {"weights": [0.5, 0.5], "vols": [0.2, 0.3], "index_vol": 0.22},
     "correlation"),
    ("risk.corr.dispersion", {"weights": [0.5, 0.5], "vol_strikes": [0.25, 0.3],
                              "index_vol_strike": 0.24, "realized_vols": [0.28, 0.35],
                              "index_realized_vol": 0.22, "vega_notional": 1e5}, "pnl"),
])
def test_cli(operation, inputs, key) -> None:
    r = run_case(json.dumps({"schema_version": "1.0", "case_id": "t", "operation": operation,
                             "inputs": inputs}))
    assert r["status"] == "ok" and key in r["outputs"], r


def test_implied_weights_rule() -> None:  # ruling E-B33
    three = corr.implied([0.5, 0.0, 0.5], [0.2, 0.9, 0.3], 0.22)
    assert three == pytest.approx(corr.implied([0.5, 0.5], [0.2, 0.3], 0.22), rel=1e-15)
    assert code(corr.implied, [0.5, -0.1], [0.2, 0.3], 0.22) == "E_DOMAIN"
    assert code(corr.implied, [1.0, 0.0], [0.2, 0.3], 0.22) == "E_DOMAIN"
