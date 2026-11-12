"""R6 wave 3 hedge rulings: iteration caps (R6-6.1), Jacobi scaling (R6-6.2), minvar pivots
(R6-11.7), empty eq_matrix (R6-11.13), use case 6 (R6-11.20). Expected values are hand-derived."""
from collections.abc import Callable
from typing import Any

import pytest

from quantforge_core import hedge_solvers as H
from quantforge_core.errors import QfError

A = [[1.0, 0.5], [0.3, 1.2], [0.1, 0.6]]
B = [-2.0, 1.5, -0.7]
W = [1.0, 1.0, 1.0]


def _code(f: Callable[..., object], *args: Any, **kw: Any) -> str:
    with pytest.raises(QfError) as e:
        f(*args, **kw)
    return e.value.code


def test_active_set_cap_of_one_is_no_convergence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(H, "_ITER_SLOPE", 0)
    monkeypatch.setattr(H, "_ITER_BASE", 1)
    assert _code(H.qp_solve, A, B, W, lower=[0.5, 0.5], upper=[0.6, 0.6]) == "E_NO_CONVERGENCE"


def test_integer_cap_of_one_is_no_convergence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(H, "_MAX_ENUMERATED", 1)
    assert _code(H.integer_solve, A, B, W, [0.1, 0.1]) == "E_NO_CONVERGENCE"


def test_mixed_units_are_regular_after_scaling() -> None:
    # Column 2 is column 1's unit times 1e9 apart from a rotation: x2 = 1e-9 * hand value.
    a = [[1.0, 0.0], [0.0, 1e9]]
    out = H.qp_solve(a, [-2.0, -3e9], [1.0, 1.0])
    assert out["x"][0] == pytest.approx(2.0, rel=1e-12)
    assert out["x"][1] == pytest.approx(3.0, rel=1e-12)


def test_minvar_indefinite_and_singular() -> None:
    assert _code(H.minvar_ratio, [[1.0, 0.1, 0.1], [0.1, 1.0, 1.2], [0.1, 1.2, 1.0]]) \
        == "E_NOT_POSITIVE_DEFINITE"
    assert _code(H.minvar_ratio, [[1.0, 0.5, 0.5], [0.5, 1.0, 1.0], [0.5, 1.0, 1.0]]) \
        == "E_SINGULAR"
    # One hedge: h = -cov / var = -0.3 / 0.5; after = 1 - 0.3^2 / 0.5.
    out = H.minvar_ratio([[1.0, 0.3], [0.3, 0.5]])
    assert out["hedge"][0] == pytest.approx(-0.6, rel=1e-14)
    assert out["variance_after"] == pytest.approx(1 - 0.18, rel=1e-14)


def test_empty_eq_matrix_is_input_error() -> None:
    assert _code(H.qp_solve, A, B, W, eq_matrix=[], eq_rhs=[]) == "E_INPUT"


def test_use_case_6_underlying_lots() -> None:
    # Book: 1,000 shares long (delta 1,000). Hedge: underlying in lots of 100 -> -10 lots.
    out = H.option_hedge_lots(100.0, 0.03, 0.0, 0.2, [("UNDERLYING", None, None, 1000.0)],
                              [("UNDERLYING", None, None, 100.0, 0.01)], ["DELTA"], 50)
    assert out["lots"] == [-10]
    assert out["greeks_after"]["delta"] == 0.0
    assert out["hedge_cost"] == pytest.approx(10 * 100 * 0.01, rel=1e-15)
    # The lot bound binds at 4 lots: 1,000 - 400 = 600 left.
    bound = H.option_hedge_lots(100.0, 0.03, 0.0, 0.2, [("UNDERLYING", None, None, 1000.0)],
                                [("UNDERLYING", None, None, 100.0, 0.01)], ["DELTA"], 4)
    assert bound["lots"] == [-4]
    assert bound["greeks_after"]["delta"] == pytest.approx(600.0, rel=1e-15)
