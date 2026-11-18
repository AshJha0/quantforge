"""H-5 (library-interfaces.md 2.5): the typed execution layer returns the kernel's numbers bit for
bit, validates its value types when built, rejects strings where an enum is required, and every
public type states its thread safety (ADR-0011 rule 5)."""

import dataclasses
import inspect
import math

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from quantforge_core import exec_api as api
from quantforge_core import execution as ex
from quantforge_core.errors import QfError

AC = {
    "quantity": 1e6,
    "horizon": 5.0,
    "n_steps": 5,
    "sigma": 0.95,
    "epsilon": 0.0625,
    "eta": 2.5e-6,
    "gamma": 2.5e-7,
}


def _code(fn, code: str) -> None:
    with pytest.raises(QfError) as e:
        fn()
    assert e.value.code == code


def test_enums_parse_and_reject() -> None:
    assert api.Side.parse("BUY") is api.Side.BUY
    assert api.FillMode.parse("CONTINUOUS") is api.FillMode.CONTINUOUS
    _code(lambda: api.Side.parse("buy"), "E_SCHEMA")
    _code(lambda: api.FillMode.parse("LOTS"), "E_SCHEMA")


def test_string_where_enum_required_is_schema() -> None:
    _code(lambda: api.twap(10, 2, "UNITS"), "E_SCHEMA")  # type: ignore[arg-type]
    _code(lambda: api.shortfall("BUY", 1, 1, 1, 1, [], 0), "E_SCHEMA")  # type: ignore[arg-type]
    _code(lambda: api.shortfall(api.Side.BUY, 1, 1, 1, 1, [(1, 1)], 0), "E_SCHEMA")  # type: ignore[list-item]


def test_schedules_match_kernel() -> None:
    t = api.twap(1_000_003, 100, api.FillMode.UNITS)
    assert list(t.slices) == ex.schedule_twap(1_000_003, 100, "UNITS")["slices"]
    assert t.filled == 1_000_003 and t.residual == 0
    prof = [1.0, 3.0, 2.0, 0.5]
    v = api.vwap(1000.5, prof, api.FillMode.CONTINUOUS)
    assert list(v.slices) == ex.schedule_vwap(1000.5, prof, "CONTINUOUS")["slices"]
    p = api.pov(1000, 0.2, [100, 500, 900], api.FillMode.UNITS)
    k = ex.schedule_pov(1000, 0.2, [100, 500, 900], "UNITS")
    assert (list(p.slices), p.filled, p.residual) == (k["slices"], k["filled"], k["residual"])


def test_ac_matches_kernel() -> None:
    prm = api.AcParams(**AC)
    tr = api.ac_trajectory(prm, 1e-6)
    k = ex.ac_trajectory(*AC.values(), 1e-6)
    assert list(tr.holdings) == k["holdings"] and list(tr.trades) == k["trades"]
    assert (tr.kappa, tr.expected_cost, tr.variance, tr.objective) == (
        k["kappa"],
        k["expected_cost"],
        k["variance"],
        k["objective"],
    )
    fr = api.ac_frontier(prm, [0.0, 1e-6])
    kf = ex.ac_frontier(*AC.values(), [0.0, 1e-6])
    assert list(fr.expected_costs) == kf["expected_costs"] and list(fr.variances) == kf["variances"]


def test_impact_tca_quotes_match_kernel() -> None:
    assert api.impact_sqrt(1e5, 1e7, 0.02, 0.5) == ex.impact_sqrt(1e5, 1e7, 0.02, 0.5)["impact"]
    o = api.ow_optimal(1000, 2.0, 3.0)
    assert dataclasses.asdict(o) == ex.impact_ow_optimal(1000, 2.0, 3.0)
    fills = [api.Fill(100, 10.1), api.Fill(50, 10.2)]
    s = api.shortfall(api.Side.SELL, 10.0, 10.05, 10.3, 200, fills, 1.5, 10.12)
    k = ex.tca_shortfall("SELL", 10.0, 10.05, 10.3, 200, [(100, 10.1), (50, 10.2)], 1.5, 10.12)
    assert dataclasses.asdict(s) == k
    assert api.shortfall(api.Side.BUY, 10, 10, 10, 1, [], 0).vwap_slippage is None
    q = api.as_quotes(100.0, 3.0, 0.1, 2.0, 0.5, 1.5)
    assert dataclasses.asdict(q) == ex.as_quotes(100.0, 3.0, 0.1, 2.0, 0.5, 1.5)


def test_validated_constructors() -> None:
    _code(lambda: api.AcParams(**{**AC, "quantity": 0.0}), "E_INPUT")
    _code(lambda: api.AcParams(**{**AC, "n_steps": 0}), "E_INPUT")
    _code(lambda: api.AcParams(**{**AC, "sigma": -1.0}), "E_DOMAIN")
    _code(lambda: api.AcParams(**{**AC, "eta": 1e-9}), "E_DOMAIN")
    _code(lambda: api.AcParams(**{**AC, "sigma": math.nan}), "E_DOMAIN")
    _code(lambda: api.Fill(0, 10), "E_INPUT")
    _code(lambda: api.Fill(1, -1), "E_DOMAIN")
    _code(lambda: api.Fill(1, math.inf), "E_DOMAIN")
    _code(lambda: api.Quotes(1, 1, 2.0, 1.0), "E_DOMAIN")
    _code(lambda: api.impact_sqrt(math.nan, 1, 1, 1), "E_DOMAIN")
    with pytest.raises(dataclasses.FrozenInstanceError):
        api.Fill(1, 1).price = 2  # type: ignore[misc]


def test_every_public_type_states_thread_safety() -> None:
    types = [v for _, v in inspect.getmembers(api, inspect.isclass) if v.__module__ == api.__name__]
    assert len(types) == 10
    for t in types:
        assert "Thread safety:" in (t.__doc__ or ""), t.__name__
    assert "Thread safety:" in (api.__doc__ or "")


@settings(max_examples=200, deadline=None)
@given(
    lam=st.floats(0, 1e-3),
    n=st.integers(1, 50),
    sigma=st.floats(0, 2),
    mid=st.floats(1, 1e4),
    inv=st.floats(-100, 100),
)
def test_property_bit_equal(lam: float, n: int, sigma: float, mid: float, inv: float) -> None:
    a = {**AC, "n_steps": n, "sigma": sigma}
    tr = api.ac_trajectory(api.AcParams(**a), lam)
    assert list(tr.trades) == ex.ac_trajectory(*a.values(), lam)["trades"]
    q = api.as_quotes(mid, inv, 0.1, sigma, 0.5, 1.5)
    assert dataclasses.asdict(q) == ex.as_quotes(mid, inv, 0.1, sigma, 0.5, 1.5)
