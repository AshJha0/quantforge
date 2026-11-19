"""Stage H wave 1 (rulings HR-1 to HR-10): every golden row of schedules.md, almgren-chriss.md,
impact.md, tca.md and avellaneda-stoikov.md, the property tests those specs list, and the CLI
wiring (operation names, E_LIMIT sizes of HR-9, error codes)."""

import itertools
import json
import math
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from quantforge_core import execution as ex
from quantforge_core.cli.main import run_case
from quantforge_core.cli.operations import OPERATIONS
from quantforge_core.errors import QfError

P = {"quantity": 1e6, "horizon": 5.0, "sigma": 0.95, "epsilon": 0.0625, "eta": 2.5e-6}
G = 2.5e-7


def _err(fn, code: str) -> None:
    with pytest.raises(QfError) as e:
        fn()
    assert e.value.code == code
    assert e.value.message and e.value.message != e.value.message.upper()


def _case(operation: str, inputs: dict[str, Any]) -> dict[str, Any]:
    return run_case(
        json.dumps(
            {"schema_version": "1.0", "case_id": "h", "operation": operation, "inputs": inputs}
        )
    )


def _traj(n: int, lam: float, gamma: float = G) -> dict[str, Any]:
    return ex.ac_trajectory(
        P["quantity"], P["horizon"], n, P["sigma"], P["epsilon"], P["eta"], gamma, lam
    )


# schedules.md


def test_sched_h_0001_0002_twap() -> None:
    assert ex.schedule_twap(1000.0, 3, "UNITS")["slices"] == [334, 333, 333]
    assert ex.schedule_twap(1000.0, 4, "CONTINUOUS")["slices"] == [250.0] * 4


def test_sched_h_0003_0004_vwap() -> None:
    got = ex.schedule_vwap(1000.0, [1.0, 2.0, 3.0, 4.0], "CONTINUOUS")["slices"]
    assert got == pytest.approx([100.0, 200.0, 300.0, 400.0], rel=1e-15)
    assert ex.schedule_vwap(10.0, [1.0, 1.0, 1.0], "UNITS")["slices"] == [4, 3, 3]


def test_sched_h_0005_0006_pov() -> None:
    r = ex.schedule_pov(1000.0, 0.2, [1000.0, 2000.0, 4000.0], "UNITS")
    assert r == {"slices": [250, 500, 250], "filled": 1000, "residual": 0}
    r = ex.schedule_pov(1000.0, 0.1, [900.0, 900.0], "CONTINUOUS")
    assert r["slices"] == pytest.approx([100.0, 100.0], rel=1e-14)
    assert r["residual"] == pytest.approx(800.0, rel=1e-14)


def test_sched_h_0007_0008_errors() -> None:
    _err(lambda: ex.schedule_pov(1000.0, 1.0, [1.0], "UNITS"), "E_DOMAIN")
    _err(lambda: ex.schedule_pov(1000.0, 0.0, [1.0], "UNITS"), "E_DOMAIN")
    _err(lambda: ex.schedule_vwap(1000.0, [0.0, 0.0], "UNITS"), "E_DOMAIN")


def test_schedule_input_rules() -> None:
    _err(lambda: ex.schedule_twap(0.0, 3, "UNITS"), "E_INPUT")
    _err(lambda: ex.schedule_twap(10.5, 3, "UNITS"), "E_INPUT")
    _err(lambda: ex.schedule_twap(10.0, 0, "CONTINUOUS"), "E_INPUT")
    _err(lambda: ex.schedule_vwap(10.0, [], "UNITS"), "E_INPUT")
    _err(lambda: ex.schedule_vwap(10.0, [1.0, -1.0], "UNITS"), "E_DOMAIN")
    _err(lambda: ex.schedule_pov(10.0, 0.5, [], "UNITS"), "E_INPUT")
    _err(lambda: ex.schedule_pov(10.0, 0.5, [-1.0], "UNITS"), "E_DOMAIN")
    _err(lambda: ex.schedule_pov(-1.0, 0.5, [1.0], "CONTINUOUS"), "E_INPUT")
    assert ex.schedule_vwap(5.0, [0.0, 1.0], "UNITS")["slices"] == [0, 5]


@settings(max_examples=200, deadline=None)
@given(st.integers(1, 10**9), st.integers(1, 500))
def test_twap_units_sum_exactly(x: int, n: int) -> None:
    s = ex.schedule_twap(float(x), n, "UNITS")["slices"]
    assert sum(s) == x and max(s) - min(s) <= 1 and s == sorted(s, reverse=True)


@settings(max_examples=200, deadline=None)
@given(st.integers(1, 10**9), st.lists(st.floats(0, 1e6), min_size=1, max_size=60))
def test_vwap_units_sum_exactly(x: int, w: list[float]) -> None:
    if sum(w) == 0:
        return
    s = ex.schedule_vwap(float(x), w, "UNITS")["slices"]
    assert sum(s) == x and all(isinstance(v, int) and v >= 0 for v in s)
    exact = [x * v / sum(w) for v in w]
    assert all(abs(a - b) < 1 + 1e-6 for a, b in zip(s, exact, strict=True))


@settings(max_examples=200, deadline=None)
@given(st.floats(1e-3, 1e9), st.lists(st.floats(0, 1e6), min_size=1, max_size=60))
def test_vwap_continuous_sums_to_1e12(x: float, w: list[float]) -> None:
    if sum(w) == 0:
        return
    s = ex.schedule_vwap(x, w, "CONTINUOUS")["slices"]
    assert math.fsum(s) == pytest.approx(x, rel=1e-12)


def test_largest_remainder_takes_back_on_rounding_excess() -> None:
    # floors summing above x (only rounding can do that) lose units from the smallest remainders
    assert ex._largest_remainder(3.0, [2.0, 1.0, 1.0]) == [2, 1, 0]
    assert ex._largest_remainder(4.0, [1.5, 1.2, 1.3]) == [2, 1, 1]


@settings(max_examples=200, deadline=None)
@given(
    st.integers(1, 10**7),
    st.floats(0.01, 0.99),
    st.lists(st.floats(0, 1e7), min_size=1, max_size=40),
    st.sampled_from(["UNITS", "CONTINUOUS"]),
)
def test_pov_participation_and_conservation(x: int, p: float, v: list[float], mode: str) -> None:
    r = ex.schedule_pov(float(x), p, v, mode)
    assert r["filled"] + r["residual"] == pytest.approx(x, rel=1e-12)
    assert r["residual"] >= 0 and math.fsum(r["slices"]) == pytest.approx(r["filled"], rel=1e-12)
    remaining = float(x)
    for s, vol in zip(r["slices"], v, strict=True):
        uncapped = p * vol / (1 - p)
        if mode == "CONTINUOUS" and s < remaining and vol > 1e-6:
            assert s / (s + vol) == pytest.approx(p, rel=1e-12)  # realised participation
        if mode == "UNITS":
            assert isinstance(s, int) and 0 <= s <= min(remaining, uncapped * (1 + 1e-12))
            assert s >= math.floor(min(remaining, uncapped))
        remaining -= s


# almgren-chriss.md


def test_ac_h_0001_linear() -> None:
    r = _traj(5, 0.0)
    assert r["holdings"] == [1e6, 8e5, 6e5, 4e5, 2e5, 0.0] and r["kappa"] == 0.0
    assert r["expected_cost"] == pytest.approx(662_500.0, rel=1e-14)
    assert r["variance"] == pytest.approx(1.083e12, rel=1e-14)
    assert r["objective"] == r["expected_cost"]


def test_ac_h_0002_optimal() -> None:
    r = _traj(5, 1e-6)
    assert r["kappa"] == pytest.approx(0.6070761632, rel=1e-9)
    want = [1e6, 541955.5544, 289854.2194, 147897.4878, 62141.8016, 0.0]
    assert r["holdings"] == pytest.approx(want, rel=1e-9, abs=1e-12)
    assert r["expected_cost"] == pytest.approx(911_226.986, rel=1e-9)
    assert r["variance"] == pytest.approx(3.641285721e11, rel=1e-9)
    assert r["objective"] == pytest.approx(1_275_355.558, rel=1e-9)


def test_ac_h_0003_eta_tilde_zero() -> None:
    _err(lambda: _traj(5, 1e-6, gamma=2 * 2.5e-6), "E_DOMAIN")


def test_ac_h_0004_single_trade() -> None:
    r = _traj(1, 1e-6)
    assert r["holdings"] == [1e6, 0.0] and r["trades"] == [1e6]
    assert r["expected_cost"] == pytest.approx(562_500.0, rel=1e-14)


def test_ac_h_0005_printed_kappa() -> None:
    r = _traj(5, 1e-6)
    assert abs(r["kappa"] - 0.6) <= 0.05 and abs(r["kappa"] * 5 - 3) <= 0.25
    assert r["kappa"] * 5 == pytest.approx(3.0353808, rel=1e-7)


def test_ac_errors_in_spec_order() -> None:
    x, t, s, e, n = P["quantity"], P["horizon"], P["sigma"], P["epsilon"], P["eta"]
    _err(lambda: ex.ac_trajectory(x, t, 5, -1.0, e, n, G, 0.0), "E_DOMAIN")
    _err(lambda: ex.ac_trajectory(x, 0.0, 5, s, e, n, G, 0.0), "E_DOMAIN")
    _err(lambda: ex.ac_trajectory(x, t, 0, s, e, n, G, 0.0), "E_INPUT")
    # Two errors at once: the structural E_INPUT comes before every E_DOMAIN (HR-66, HR-122).
    _err(lambda: ex.ac_trajectory(x, t, 0, -1.0, e, n, G, 0.0), "E_INPUT")
    _err(lambda: ex.ac_trajectory(0.0, 0.0, 5, s, e, n, G, 0.0), "E_INPUT")
    _err(lambda: ex.ac_frontier(x, t, 5, -1.0, e, n, G, []), "E_INPUT")
    _err(lambda: ex.ac_frontier(x, t, 0, s, e, n, G, []), "E_INPUT")
    _err(lambda: ex.schedule_pov(1000.0, 1.5, [], "CONTINUOUS"), "E_INPUT")
    _err(lambda: ex.ac_trajectory(0.0, t, 5, s, e, n, G, 0.0), "E_INPUT")
    _err(lambda: ex.ac_trajectory(x, t, 5, s, -1.0, n, G, 0.0), "E_DOMAIN")
    _err(lambda: ex.ac_trajectory(x, t, 5, s, e, n, -G, 0.0), "E_DOMAIN")
    _err(lambda: ex.ac_trajectory(x, t, 5, s, e, n, G, -1e-6), "E_DOMAIN")
    _err(lambda: ex.ac_frontier(x, t, 5, s, e, n, G, []), "E_INPUT")
    _err(lambda: ex.ac_frontier(x, t, 5, s, e, n, G, [1e-6, -1.0]), "E_DOMAIN")


@settings(max_examples=100, deadline=None)
@given(st.integers(1, 200), st.floats(0, 1e-4))
def test_ac_trades_sum_and_below_linear(n: int, lam: float) -> None:
    r = _traj(n, lam)
    assert math.fsum(r["trades"]) == pytest.approx(1e6, rel=1e-12)
    assert r["holdings"][0] == 1e6 and r["holdings"][-1] == 0.0
    h = r["holdings"]
    assert all(b <= a for a, b in itertools.pairwise(h))
    if lam > 1e-9:  # below that, strictness is lost in rounding
        assert all(h[j] < 1e6 * (n - j) / n for j in range(1, n))


def test_ac_lambda_tiny_is_close_to_linear() -> None:
    r, lin = _traj(5, 1e-15), _traj(5, 0.0)
    # kappa^2 T^2 / 6 = 1.6e-9 at P: the model itself moves this far, so 2e-9 (spec: 1e-9)
    assert r["holdings"] == pytest.approx(lin["holdings"], rel=2e-9, abs=1e-9)


def test_ac_kappa_tends_to_continuous_limit() -> None:
    lam, sig, eta, t = 1e-6, P["sigma"], P["eta"], P["horizon"]
    limit = math.sqrt(lam * sig * sig / eta)
    errs = []
    for n in (10, 100, 1000):
        errs.append(abs(_traj(n, lam)["kappa"] - limit))
    assert errs[0] > errs[1] > errs[2] and errs[2] < 1e-3 * t
    assert errs[1] / errs[2] == pytest.approx(10, rel=0.2)  # falls like tau


def test_ac_kappa_small_y_series() -> None:
    y = 1e-14
    k = ex.ac_kappa(2.0 * y, 1.0, 1.0, 1.0)  # y = lambda sigma^2 tau^2 / (2 eta_tilde)
    assert k == pytest.approx(math.sqrt(2 * y), rel=1e-12)


def test_ac_large_kappa_t_is_finite() -> None:
    # kappa T about 1000 with tau = 1: cosh(kappa) - 1 = y, kappa = 200
    lam = (math.cosh(200.0) - 1) * 2 * 2.375e-6 / (0.95**2)
    r = _traj(5, lam)
    h = r["holdings"]
    assert all(math.isfinite(v) for v in h) and all(b <= a for a, b in itertools.pairwise(h))
    assert r["kappa"] * 5 == pytest.approx(1000.0, rel=1e-9)
    assert ex._sinh_ratio(800.0, 1000.0) == pytest.approx(math.exp(-200.0), rel=1e-12)


def test_ac_frontier_monotone_and_matches_trajectory() -> None:
    lams = [0.0, 1e-8, 1e-7, 1e-6, 2e-6, 1e-5, 1e-4]
    x, t, s, e, n = P["quantity"], P["horizon"], P["sigma"], P["epsilon"], P["eta"]
    f = ex.ac_frontier(x, t, 5, s, e, n, G, lams)
    assert f["risk_aversions"] == lams
    ec, var = f["expected_costs"], f["variances"]
    assert all(b >= a for a, b in itertools.pairwise(ec))
    assert all(b <= a for a, b in itertools.pairwise(var))
    assert ec[3] == _traj(5, 1e-6)["expected_cost"] and var[0] == _traj(5, 0.0)["variance"]


@settings(max_examples=50, deadline=None)
@given(st.lists(st.floats(0, 1e-3), min_size=2, max_size=8), st.integers(1, 50))
def test_ac_frontier_monotone_property(lams: list[float], n: int) -> None:
    lams = sorted(lams)
    x, t, s, e, eta = P["quantity"], P["horizon"], P["sigma"], P["epsilon"], P["eta"]
    f = ex.ac_frontier(x, t, n, s, e, eta, G, lams)
    ec, var = f["expected_costs"], f["variances"]
    assert all(b >= a * (1 - 1e-12) for a, b in itertools.pairwise(ec))
    assert all(b <= a * (1 + 1e-12) for a, b in itertools.pairwise(var))


# impact.md


def test_imp_h_goldens() -> None:
    assert ex.impact_sqrt(1e5, 1e7, 0.02, 1.0)["impact"] == pytest.approx(0.002, rel=1e-15)
    assert ex.impact_sqrt(4e5, 1e7, 0.02, 1.0)["impact"] == pytest.approx(0.004, rel=1e-15)
    assert ex.impact_ow_optimal(1000.0, 1.0, 8.0) == {
        "initial_block": 100.0,
        "rate": 800.0,
        "final_block": 100.0,
    }
    r = ex.impact_ow_optimal(1e5, 1.0, 2.231)
    assert r["initial_block"] == pytest.approx(23635.0744504845, rel=1e-13)
    assert r["final_block"] == r["initial_block"]
    assert r["rate"] == pytest.approx(52729.8510990310, rel=1e-13)


def test_impact_errors_and_limits() -> None:
    _err(lambda: ex.impact_sqrt(-1.0, 1e7, 0.02, 1.0), "E_DOMAIN")
    _err(lambda: ex.impact_sqrt(1.0, 0.0, 0.02, 1.0), "E_DOMAIN")
    _err(lambda: ex.impact_sqrt(1.0, 1.0, -0.02, 1.0), "E_DOMAIN")
    _err(lambda: ex.impact_sqrt(1.0, 1.0, 0.02, -1.0), "E_DOMAIN")
    _err(lambda: ex.impact_ow_optimal(0.0, 1.0, 1.0), "E_INPUT")
    _err(lambda: ex.impact_ow_optimal(1.0, 0.0, 1.0), "E_DOMAIN")
    _err(lambda: ex.impact_ow_optimal(1.0, 1.0, 0.0), "E_DOMAIN")
    r = ex.impact_ow_optimal(1000.0, 1.0, 1e-12)
    assert r["initial_block"] == pytest.approx(500.0, rel=1e-11)


@settings(max_examples=200, deadline=None)
@given(st.floats(1e-3, 1e9), st.floats(1e-3, 100), st.floats(1e-6, 1e3))
def test_ow_blocks_and_rate_sum_to_x(x: float, t: float, rho: float) -> None:
    r = ex.impact_ow_optimal(x, t, rho)
    assert r["initial_block"] + r["rate"] * t + r["final_block"] == pytest.approx(x, rel=1e-12)


# tca.md

FILLS = [(600.0, 100.20), (200.0, 100.30)]


def test_tca_h_0001_0002() -> None:
    r = ex.tca_shortfall("BUY", 100.0, 100.10, 101.0, 1000.0, FILLS, 5.0, None)
    want = {
        "delay": 80.0,
        "execution": 100.0,
        "opportunity": 200.0,
        "total": 385.0,
        "total_bps": 38.5,
    }
    assert r.keys() == want.keys()
    for k, v in want.items():
        assert r[k] == pytest.approx(v, rel=1e-10)
    r = ex.tca_shortfall("SELL", 100.0, 100.10, 101.0, 1000.0, FILLS, 0.0, None)
    for k, v in {
        "delay": -80.0,
        "execution": -100.0,
        "opportunity": -200.0,
        "total": -380.0,
    }.items():
        assert r[k] == pytest.approx(v, rel=1e-10)


def test_tca_h_0003_and_errors() -> None:
    over = [(600.0, 100.2), (600.0, 100.3)]
    _err(lambda: ex.tca_shortfall("BUY", 100.0, 100.1, 101.0, 1000.0, over, 0.0, None), "E_INPUT")
    _err(lambda: ex.tca_shortfall("BUY", 0.0, 100.1, 101.0, 1000.0, FILLS, 0.0, None), "E_DOMAIN")
    _err(
        lambda: ex.tca_shortfall("BUY", 100.0, 100.1, 101.0, 1000.0, [(1.0, -1.0)], 0.0, None),
        "E_DOMAIN",
    )
    _err(lambda: ex.tca_shortfall("BUY", 100.0, 100.1, 101.0, 1000.0, FILLS, 0.0, 0.0), "E_DOMAIN")
    _err(
        lambda: ex.tca_shortfall("BUY", 100.0, 100.1, 101.0, 1000.0, [(0.0, 1.0)], 0.0, None),
        "E_INPUT",
    )
    _err(lambda: ex.tca_shortfall("BUY", 100.0, 100.1, 101.0, 0.0, [], 0.0, None), "E_INPUT")
    # an overfill with a bad price is E_INPUT: tca.md lists Q > X first
    _err(lambda: ex.tca_shortfall("BUY", -1.0, 100.1, 101.0, 1000.0, over, 0.0, None), "E_INPUT")


def test_tca_vwap_slippage() -> None:
    r = ex.tca_shortfall("BUY", 100.0, 100.1, 101.0, 1000.0, FILLS, 0.0, 100.2)
    assert r["vwap_slippage"] == pytest.approx(200 * 0.1, rel=1e-9)  # 800 x (100.225 - 100.2)
    r = ex.tca_shortfall("SELL", 100.0, 100.1, 101.0, 1000.0, [], 0.0, 100.2)
    assert r["vwap_slippage"] == 0.0 and r["opportunity"] == pytest.approx(-1000.0)


@settings(max_examples=200, deadline=None)
@given(
    st.sampled_from(["BUY", "SELL"]),
    st.floats(1, 1e4),
    st.floats(1, 1e4),
    st.floats(1, 1e4),
    st.lists(st.tuples(st.floats(1, 1e4), st.floats(1, 1e4)), max_size=30),
    st.floats(-1e3, 1e3),
    st.booleans(),
)
def test_tca_decomposition_sums(side, pd, p0, pc, fills, fees, full) -> None:
    q = sum(f[0] for f in fills)
    x = q if full and q > 0 else q + 100.0
    r = ex.tca_shortfall(side, pd, p0, pc, x, fills, fees, None)
    parts = r["delay"] + r["execution"] + r["opportunity"] + fees
    scale = max(abs(r["delay"]), abs(r["execution"]), abs(r["opportunity"]), abs(fees), 1.0)
    assert abs(parts - r["total"]) <= 1e-10 * scale
    if full and q > 0:
        assert r["opportunity"] == 0.0


# avellaneda-stoikov.md


def test_as_h_goldens() -> None:
    r = ex.as_quotes(100.0, 2.0, 0.1, 2.0, 1.0, 1.5)
    assert r["reservation"] == pytest.approx(99.2, rel=1e-15)
    assert r["spread"] == pytest.approx(1.6907704228, abs=1e-10)
    assert r["bid"] == pytest.approx(98.3546147886, abs=1e-10)
    assert r["ask"] == pytest.approx(100.0453852114, abs=1e-10)
    r = ex.as_quotes(100.0, 0.0, 0.1, 2.0, 1.0, 1.5)
    assert r["reservation"] == 100.0
    assert r["bid"] == pytest.approx(99.1546147886, abs=1e-10)
    assert r["ask"] == pytest.approx(100.8453852114, abs=1e-10)
    r = ex.as_quotes(100.0, 2.0, 0.1, 2.0, 0.0, 1.5)
    assert r["reservation"] == 100.0
    assert r["spread"] == pytest.approx(1.2907704228, abs=1e-10)
    _err(lambda: ex.as_quotes(100.0, 2.0, 0.0, 2.0, 1.0, 1.5), "E_DOMAIN")
    for gamma, want, printed in (
        (0.1, 1.4907704228, 1.49),
        (0.01, 1.3489085437, 1.35),
        (1.0, 3.0216512475, 3.02),
    ):
        s = ex.as_quotes(100.0, 0.0, gamma, 2.0, 0.5, 1.5)["spread"]
        assert s == pytest.approx(want, abs=1e-10) and abs(s - printed) <= 0.005


def test_as_errors_and_limits() -> None:
    _err(lambda: ex.as_quotes(100.0, 0.0, 0.1, 2.0, 1.0, 0.0), "E_DOMAIN")
    _err(lambda: ex.as_quotes(100.0, 0.0, 0.1, -2.0, 1.0, 1.5), "E_DOMAIN")
    _err(lambda: ex.as_quotes(100.0, 0.0, 0.1, 2.0, -1.0, 1.5), "E_DOMAIN")
    s = ex.as_quotes(100.0, 0.0, 1e-12, 2.0, 1.0, 1.5)["spread"]
    assert s == pytest.approx(2 / 1.5, rel=1e-9)  # gamma -> 0 gives 2 / k


@settings(max_examples=100, deadline=None)
@given(st.floats(-50, 50), st.floats(-50, 50))
def test_as_reservation_decreasing_in_inventory(q1: float, q2: float) -> None:
    r1 = ex.as_quotes(100.0, q1, 0.1, 2.0, 1.0, 1.5)
    r2 = ex.as_quotes(100.0, q2, 0.1, 2.0, 1.0, 1.5)
    if q1 < q2 - 1e-9:  # closer inventories can round to one reservation
        assert r1["reservation"] > r2["reservation"]
    assert r1["spread"] == r2["spread"]
    assert r1["ask"] - r1["bid"] == pytest.approx(r1["spread"], rel=1e-12)


# CLI wiring

NAMES = [
    "exec.ac.frontier",
    "exec.ac.trajectory",
    "exec.impact.ow_optimal",
    "exec.impact.sqrt",
    "exec.schedule.pov",
    "exec.schedule.twap",
    "exec.schedule.vwap",
    "exec.tca.shortfall",
    "micro.mm.as_quotes",
]


def test_operations_registered() -> None:
    assert set(NAMES) <= set(OPERATIONS)


def test_cli_cases() -> None:
    r = _case("exec.schedule.twap", {"quantity": 1000, "n_buckets": 3, "mode": "UNITS"})
    assert r["outputs"] == {"slices": [334, 333, 333]}
    r = _case("exec.schedule.twap", {"quantity": 1000, "n_buckets": 4})
    assert r["outputs"] == {"slices": [250.0] * 4}
    r = _case(
        "exec.schedule.pov",
        {"quantity": 1000, "participation": 1.0, "market_volume": [1.0], "mode": "UNITS"},
    )
    assert r["error"]["code"] == "E_DOMAIN"
    r = _case("exec.schedule.vwap", {"quantity": 10, "profile": [1, 1, 1], "mode": "LOTS"})
    assert r["error"]["code"] == "E_SCHEMA"
    ac = {**P, "n_steps": 5, "gamma": G}
    r = _case("exec.ac.trajectory", {**ac, "risk_aversion": 0})
    assert set(r["outputs"]) == {
        "holdings",
        "trades",
        "kappa",
        "expected_cost",
        "variance",
        "objective",
    }
    r = _case("exec.ac.frontier", {**ac, "risk_aversions": [0, 1e-6]})
    assert set(r["outputs"]) == {"risk_aversions", "expected_costs", "variances"}
    r = _case("exec.impact.sqrt", {"quantity": 1e5, "daily_volume": 1e7, "daily_vol": 0.02})
    assert r["outputs"]["impact"] == pytest.approx(0.002)
    assert r["outputs"]["model"] == "assumed parameters; not calibrated to any venue"
    r = _case("exec.impact.ow_optimal", {"quantity": 1000, "horizon": 1, "resilience": 8})
    assert r["outputs"] == {"initial_block": 100.0, "rate": 800.0, "final_block": 100.0}
    tca = {
        "side": "BUY",
        "decision_price": 100,
        "arrival_price": 100.1,
        "end_price": 101,
        "order_quantity": 1000,
        "fees": 5,
        "fills": [{"quantity": 600, "price": 100.2}, {"quantity": 200, "price": 100.3}],
    }
    r = _case("exec.tca.shortfall", tca)
    assert r["outputs"]["total"] == pytest.approx(385.0)
    assert (
        "vwap_slippage" in _case("exec.tca.shortfall", {**tca, "benchmark_vwap": 100.2})["outputs"]
    )
    r = _case(
        "micro.mm.as_quotes",
        {"mid": 100, "inventory": 2, "risk_aversion": 0.1, "sigma": 2, "time_left": 1, "k": 1.5},
    )
    assert r["outputs"]["reservation"] == pytest.approx(99.2)


def test_cli_limits_hr_9() -> None:
    r = _case("exec.schedule.twap", {"quantity": 1000, "n_buckets": 100_001})
    assert r["error"]["code"] == "E_LIMIT"
    ac = {**P, "gamma": G, "risk_aversion": 0}
    assert _case("exec.ac.trajectory", {**ac, "n_steps": 100_001})["error"]["code"] == "E_LIMIT"
    r = _case("exec.ac.frontier", {**ac, "n_steps": 100_001, "risk_aversions": [0]})
    assert r["error"]["code"] == "E_LIMIT"
    r = _case("exec.schedule.vwap", {"quantity": 10, "profile": [1.0] * 100_001})
    assert r["error"]["code"] == "E_LIMIT"
    fill = {"quantity": 1e-6, "price": 100.0}
    base = {
        "side": "BUY",
        "decision_price": 100,
        "arrival_price": 100,
        "end_price": 100,
        "order_quantity": 1e6,
    }
    r = _case("exec.tca.shortfall", {**base, "fills": [fill] * 100_001})
    assert r["status"] == "ok"  # fills are allowed up to 1,000,000 (HR-9)
    r = _case("exec.tca.shortfall", {**base, "fills": [fill] * 1_000_001})
    assert r["error"]["code"] == "E_LIMIT"


def test_four_build_edge_choices() -> None:
    # a full SELL has opportunity +0, never -0
    r = ex.tca_shortfall("SELL", 100.0, 100.1, 101.0, 800.0, FILLS, 0.0, None)
    assert math.copysign(1.0, r["opportunity"]) == 1.0
    # POV UNITS snaps a value within 1e-12 relative of an integer before flooring
    assert ex.schedule_pov(1000.0, 0.2, [999.9999999999999], "UNITS")["slices"] == [250]
    assert ex.schedule_pov(1000.0, 0.2, [999.0], "UNITS")["slices"] == [249]


def test_vwap_subnormal_weight_keeps_the_order() -> None:
    # found by hypothesis: X w_i underflowed (1.5 x 5e-324) and gave 2.0; ratio first (schedules.md)
    assert ex.schedule_vwap(1.5, [5e-324], "CONTINUOUS")["slices"] == [1.5]
    assert ex.schedule_vwap(3.0, [5e-324, 5e-324], "CONTINUOUS")["slices"] == [1.5, 1.5]
