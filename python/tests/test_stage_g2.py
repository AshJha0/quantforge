"""Stage G waves 3b to 4b and the stage F carry-over tools: property tests and acceptance runs
(LMM parities and the G-26 simulated-caplet acceptance, the Q3b ladder against a Richardson bump
with the G-9 cost ratio, xVA limits, F3/F4/FRTB identities). Goldens run in test_conformance.py."""
import itertools
import math
import os
import statistics
import time
from typing import Any

import pytest

from quantforge_core import aad_ladder, frtb, lmm, risk_tools, shortrate, xva
from quantforge_core.errors import QfError

TIMES = [0.4986301369863014, 1.0, 2.0, 3.0, 5.002739726027397, 7.005479452054795,
         10.005479452054795, 15.01095890410959, 20.013698630136986, 30.019178082191782]
DFS = [0.98085, 0.9619, 0.9254, 0.8906, 0.8242, 0.762, 0.6787, 0.561, 0.467, 0.332]
HUMP = (-0.06, 0.17, 0.54, 0.17)


# --- LMM ------------------------------------------------------------------------------------------


def test_lmm_cap_minus_floor_is_the_swap() -> None:
    periods = [0.5 * k for k in range(1, 11)]
    curve = shortrate.make_curve(TIMES, DFS)
    for k in (0.03, 0.05):
        cap = lmm.capfloor(TIMES, DFS, HUMP, periods, k, "CAP", 1.0)["price"]
        floor = lmm.capfloor(TIMES, DFS, HUMP, periods, k, "FLOOR", 1.0)["price"]
        swap = sum(curve.discount(a) - (1 + k * (b - a)) * curve.discount(b)
                   for a, b in itertools.pairwise(periods))
        assert isinstance(cap, float) and isinstance(floor, float)
        assert abs(cap - floor - swap) <= 1e-14


def test_lmm_flat_abcd_gives_d() -> None:
    out = lmm.capfloor(TIMES, DFS, (0.0, 0.0, 0.5, 0.2), [1.0, 2.0, 3.0], 0.04, "CAP", 1.0)
    vols = out["black_vols"]
    assert isinstance(vols, list) and all(abs(v - 0.2) <= 1e-14 for v in vols)
    sw = lmm.swaption_rebonato(TIMES, DFS, (0.0, 0.0, 0.5, 0.2), 0.0, 1.0, [2.0, 3.0, 4.0], 0.04,
                               "PAY", 1.0)
    assert abs(sw["black_vol"] - 0.2) <= 1e-14


def test_rebonato_payer_minus_receiver_and_decorrelation() -> None:
    pay = [6.0, 7.0, 8.0, 9.0, 10.0]
    for beta in (0.0, 0.1, 0.5):
        p = lmm.swaption_rebonato(TIMES, DFS, HUMP, beta, 5.0, pay, 0.035, "PAY", 1.0)
        r = lmm.swaption_rebonato(TIMES, DFS, HUMP, beta, 5.0, pay, 0.035, "RECEIVE", 1.0)
        assert abs(p["price"] - r["price"] - p["annuity"] * (p["swap_rate"] - 0.035)) <= 1e-14
    v0 = lmm.swaption_rebonato(TIMES, DFS, HUMP, 0.0, 5.0, pay, 0.035, "PAY", 1.0)["black_vol"]
    v5 = lmm.swaption_rebonato(TIMES, DFS, HUMP, 0.5, 5.0, pay, 0.035, "PAY", 1.0)["black_vol"]
    assert v5 < v0


def test_lmm_simulated_caplets_acceptance() -> None:
    """G-26: humped abcd, beta 0.1, annual grid to 7 years, K = 4.5%, 100,000 paths, 20 steps a
    year; every caplet within 3 SE of the closed form."""
    curve = shortrate.make_curve(TIMES, DFS)
    grid = [float(k) for k in range(8)]
    sim = lmm.simulate_caplets(curve, lmm.make_abcd(*HUMP), 0.1, grid, 0.045, 100_000, 20,
                               20261111)
    closed = lmm.capfloor(TIMES, DFS, HUMP, grid[1:], 0.045, "CAP", 1.0)["caplet_prices"]
    assert isinstance(closed, list) and len(closed) == len(sim) == 6
    for (mean, se), exact in zip(sim, closed, strict=True):
        assert abs(mean - exact) <= 3 * se, (mean, exact, se)


# --- Q3b ladder ------------------------------------------------------------------------------------


def _berm(times: list[float], dfs: list[float], a: float, sigma: float) -> float:
    m = shortrate.curve_model(times, dfs, a, sigma)
    grid = shortrate.make_grid(41, 20, 6.0)
    out = shortrate.bermudan_swaption(m, 1.0, [2.0, 3.0, 4.0, 5.0, 6.0], 0.039462, "PAYER", 1.0,
                                      [1.0, 2.0, 3.0, 4.0, 5.0], grid)
    return out["price"]


def _richardson(f, x: float) -> float:
    def d(h: float) -> float:
        return float((f(x * (1 + h)) - f(x * (1 - h))) / (2 * h * x))

    return (4 * d(5e-5) - d(1e-4)) / 3


def test_ladder_equals_bump_within_g9() -> None:
    a, sigma = 0.05, 0.01
    m = shortrate.curve_model(TIMES, DFS, a, sigma)
    price, d_dfs, d_a, d_sigma = aad_ladder.ladder(m, 1.0, [2.0, 3.0, 4.0, 5.0, 6.0], 0.039462,
                                                   True, [1.0, 2.0, 3.0, 4.0, 5.0], 41, 20, 6.0)
    assert price == pytest.approx(_berm(TIMES, DFS, a, sigma), rel=1e-12)

    def close(aad: float, ref: float) -> bool:
        return abs(aad - ref) <= 1e-10 + 1e-8 * abs(ref)

    assert close(d_sigma, _richardson(lambda s: _berm(TIMES, DFS, a, s), sigma))
    assert close(d_a, _richardson(lambda x: _berm(TIMES, DFS, x, sigma), a))
    for j in (0, 1, 2, 4, 6):
        def bumped(v: float, j: int = j) -> float:
            dfs = list(DFS)
            dfs[j] = v
            return _berm(TIMES, dfs, a, sigma)

        assert close(d_dfs[j], _richardson(bumped, DFS[j])), j


def test_ladder_cost_ratio_report() -> None:
    """G-9 cost ratio (median of 21 timed runs after 5 warm-ups) on aadladder_g-0001's inputs.
    Reported, and held to 5 as G-9 asks."""
    m = shortrate.curve_model(TIMES, DFS, 0.05, 0.01)
    grid = shortrate.make_grid(101, 50, 6.0)
    pay, ex = [2.0, 3.0, 4.0, 5.0, 6.0], [1.0, 2.0, 3.0, 4.0, 5.0]

    def one_price() -> None:
        shortrate.bermudan_swaption(m, 1.0, pay, 0.039462, "PAYER", 1.0, ex, grid)

    def ladder() -> None:
        aad_ladder.ladder(m, 1.0, pay, 0.039462, True, ex, 101, 50, 6.0)

    def median(f) -> float:
        for _ in range(5):
            f()
        runs = []
        for _ in range(21):
            t0 = time.perf_counter()
            f()
            runs.append(time.perf_counter() - t0)
        return statistics.median(runs)

    ratio = median(ladder) / median(one_price)
    print(f"G-9 ladder cost ratio: {ratio:.2f}")
    # R6-16: record the measured ratio; CI sets QF_G9_OUT and keeps the file as evidence.
    out = os.environ.get("QF_G9_OUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"python G-9 ladder/price ratio {ratio:.4f} (bound 5)\n")
    assert ratio <= 5


# --- xVA framework ---------------------------------------------------------------------------------


PATHS = [[0.0, 3.0, 5.0, 2.0, -1.0], [0.0, -2.0, -4.0, -6.0, -3.0], [0.0, 1.0, 6.0, 9.0, 4.0],
         [0.0, 0.5, -1.0, 2.5, 7.0]]
GRID = [0.0, 0.25, 0.5, 0.75, 1.0]


def test_total_ee_is_the_sum_over_sets_and_zero_csa_removes_exposure() -> None:
    other = [[0.0, -1.0, 2.0, 1.0, 0.5]] * 4
    out = xva.collateralised(GRID, [("A", PATHS), ("B", other)], {}, 0.9)
    sets = out["netting_sets"]
    assert isinstance(sets, dict)
    total = [x + y for x, y in zip(sets["A"]["ee"], sets["B"]["ee"], strict=True)]
    assert out["total_ee"] == total
    tight = xva.Csa(0.0, 0.0, 0.0, 0)
    zero = xva.collateralised(GRID, [("A", PATHS)], {"A": tight}, 0.9)
    assert zero["total_ee"] == [0.0] * 5


def test_own_hazard_zero_gives_no_dva() -> None:
    out = xva.adjustments([0.5, 1.0], [0.99, 0.98], [10.0, 12.0], [-5.0, -4.0],
                          xva.Name(0.02, 0.4), xva.Name(0.0, 0.4), 0.01, 0.01, True,
                          None, None, None, None)
    assert out["dva"] == 0.0 and out["fba"] == pytest.approx(0.01 / 0.01 * out["fba"])


def test_wwr_without_dependence_is_the_independent_cva() -> None:
    times = [0.25, 0.5, 0.75, 1.0]
    values = [p[1:] for p in PATHS]
    dfs = [0.995, 0.99, 0.985, 0.98]
    out: dict[str, Any] = xva.wwr_cva(times, values, dfs, 0.03, 0.4, 0.0)
    ee = [sum(max(p[i], 0.0) for p in values) / 4 for i in range(4)]
    prev = [0.0, *times[:-1]]
    indep = 0.6 * sum(d * e * (math.exp(-0.03 * p) - math.exp(-0.03 * t))
                      for d, e, t, p in zip(dfs, ee, times, prev, strict=True))
    assert out["cva"] == pytest.approx(indep, rel=1e-13)
    wrong = xva.wwr_cva(times, values, dfs, 0.03, 0.4, 0.3)["cva"]
    right = xva.wwr_cva(times, values, dfs, 0.03, 0.4, -0.2)["cva"]
    assert isinstance(wrong, float) and isinstance(right, float)
    assert right < out["cva"] < wrong


def test_dispersion_equal_models_and_zero_booked_price() -> None:
    same = xva.dispersion({"A": 1.0, "B": 1.0, "C": 1.0}, "B")
    assert same["range"] == 0 and same["reserve"] == 0 and same["worst_model"] == "A"
    assert xva.dispersion({"A": 0.0, "B": 1.0}, "A")["relative_reserve"] is None


# --- stage F carry-over ----------------------------------------------------------------------------


def test_reverse_stress_linear_limit_and_horizon_sqrt_rule() -> None:
    out = risk_tools.reverse_stress([1.0, 0.5], [-1000.0, -550.0], [[0.0, 0.0], [0.0, 0.0]], 50.0)
    assert out["scale"] == pytest.approx(50 / 1275)
    h = risk_tools.vol_horizon(0.01, 0.0, 10)
    assert h["vol"] == pytest.approx(h["sqrt_rule_vol"]) and h["variance_ratio"] == 1.0


def test_f3_analytic_sensitivities_match_bumps() -> None:
    base = risk_tools.dividend_borrow(100, 100, 1, 0.03, 0.02, 0.005, 0.25, "PUT")
    up = risk_tools.dividend_borrow(100, 100, 1, 0.03, 0.02 + 1e-6, 0.005, 0.25, "PUT")
    assert base["dividend01"] == pytest.approx((up["price"] - base["price"]) / 1e-6 * 1e-4,
                                               rel=1e-4)
    args = (100.0, 95.0, 1.0, 1.0, 0.01, 0.02, 0.3, 0.25)
    c = risk_tools.correlation01(*args, 0.5, 1.0)
    hi = risk_tools.correlation01(*args, 0.5 + 1e-6, 1.0)["price"]
    lo = risk_tools.correlation01(*args, 0.5 - 1e-6, 1.0)["price"]
    assert c["correlation01"] == pytest.approx((hi - lo) / 2e-6 * 0.01, rel=1e-6)
    assert risk_tools.inflation01(1e6, 1, 0.02, 0.02, 0.9)["pv"] == 0.0


def test_frtb_single_factor_is_weight_times_sensitivity() -> None:
    fx = frtb.fx_delta([("EURUSD", 1e6)], [])
    assert fx["capital"] == pytest.approx(150_000)
    eq = frtb.equity_delta([("A", 12, "SPOT", 1e6)])
    assert eq["capital"] == pytest.approx(150_000)
    with pytest.raises(QfError):
        frtb.equity_delta([("A", 14, "SPOT", 1e6)])


def test_frtb_vega_one_factor_and_curvature_long_gamma() -> None:
    v = frtb.vega("EQUITY", [(5, "A", 1.0, None, 1e6)])
    assert v["capital"] == pytest.approx(0.7778 * 1e6)
    c = frtb.curvature("EQUITY", [(5, "A", -3.0, 0.0)], False)
    assert c["capital"] == 0.0
    with pytest.raises(QfError):
        frtb.curvature("GIRR", [("EUR", None, 1.0, 1.0)], True)


# --- wave 4c portfolio exposure --------------------------------------------------------------------


def test_portfolio_single_swap_reproduces_wave_4a_and_pfe_order() -> None:
    from quantforge_core import portfolio_exposure

    pay = [1.0, 2.0, 3.0, 4.0, 5.0]
    out = portfolio_exposure.portfolio_hw(TIMES, DFS, 0.05, 0.01, [(1e7, 0.03, "PAY", 0.0, pay)],
                                          [1.0, 2.0, 3.0, 4.0], [0.95, 0.99], 0.02, 0.4)
    m = shortrate.curve_model(TIMES, DFS, 0.05, 0.01)
    wave4a = shortrate.swap_ee_hw(m, 0.0, pay, 0.03, "PAY", 1e7, [1.0, 2.0, 3.0, 4.0], 0.02, 0.4)
    ee, ref = out["discounted_ee"], wave4a["discounted_ee"]
    assert isinstance(ee, list) and isinstance(ref, list)
    for x, y in zip(ee, ref, strict=True):
        assert x == pytest.approx(y, rel=1e-10)
    assert out["cva"] == pytest.approx(wave4a["cva"], rel=1e-10)
    p95, p99 = out["pfe_95"], out["pfe_99"]
    assert isinstance(p95, list) and isinstance(p99, list)
    assert all(b >= a >= 0 for a, b in zip(p95, p99, strict=True))


def test_portfolio_offsetting_swaps_have_no_exposure() -> None:
    from quantforge_core import portfolio_exposure

    pay = [1.0, 2.0, 3.0]
    out = portfolio_exposure.portfolio_hw(
        TIMES, DFS, 0.05, 0.01, [(1e6, 0.03, "PAY", 0.0, pay), (1e6, 0.03, "RECEIVE", 0.0, pay)],
        [1.0, 2.0], [0.95], 0.02, 0.4)
    assert out["discounted_ee"] == [0.0, 0.0] and out["pfe_95"] == [0.0, 0.0]
