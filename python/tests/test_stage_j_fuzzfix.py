"""Stage J lane J-0b: rulings J-0b.1 (horizon limit), J-0b.2 (overflowing squared return), J-0b.3 (ragged rows)."""

import json

import pytest

from quantforge_core.cli.main import run_case


def status(op: str, inputs: str) -> str:
    r = run_case(
        json.dumps(
            {"schema_version": "1.0", "case_id": "c", "operation": op, "inputs": json.loads(inputs)}
        )
    )
    return "ok" if r["status"] == "ok" else str(r["error"]["code"])


CASES = [
    (
        "vol.garch.forecast",
        '{"omega":5e-06,"alpha":0.12,"beta":0.82,"next_variance":0.0003,"horizon":100001,"periods_per_year":252.0}',
        "E_LIMIT",
    ),
    (
        "vol.garch.forecast",
        '{"omega":5e-06,"alpha":0.12,"beta":0.82,"next_variance":0.0003,"horizon":2147483648,"periods_per_year":252.0}',
        "E_LIMIT",
    ),
    (
        "vol.garch.estimate",
        '{"returns":[0.01,-0.012,0.01,-0.012,0.01,-2.6755826e+297,0.01,-0.012,0.01,-0.012,0.01,-0.012,0.01,-0.012,0.01,-0.012,0.01,-0.012,0.01,-0.012,0.01,-0.012,0.01,-0.012,0.01,-0.012,0.01,-0.012,0.01,-0.012,0.01,-0.012,0.01,-0.012,0.01,-0.012,0.01,-0.012,0.01,-0.012],"initial_variance":1e-4,"distribution":"NORMAL","demean":true}',
        "E_NON_FINITE",
    ),
    (
        "exotic.basket.moment",
        '{"forwards":[100.0,100.0],"weights":[0.5,0.5],"vols":[0.2,0.2],"correlation":[[1.0,1.0],[]],"strike":100.0,"expiry_years":1.0,"rate":0.03,"option_type":"CALL"}',
        "E_INPUT",
    ),
    (
        "exotic.basket.moment",
        '{"forwards":[100.0,100.0],"weights":[0.5,0.5],"vols":[0.2,0.2],"correlation":[[1.0],[0.0,1.0]],"strike":100.0,"expiry_years":1.0,"rate":0.03,"option_type":"CALL"}',
        "E_INPUT",
    ),
    (
        "exotic.basket.moment",
        '{"forwards":[100.0,100.0],"weights":[0.5,0.5],"vols":[0.2,0.2],"correlation":[[1.0,0.0],[0.0,1.0,0.0]],"strike":100.0,"expiry_years":1.0,"rate":0.03,"option_type":"CALL"}',
        "E_INPUT",
    ),
]


@pytest.mark.parametrize(("op", "inputs", "expected"), CASES)
def test_j0b_rulings(op: str, inputs: str, expected: str) -> None:
    assert status(op, inputs) == expected


def test_horizon_at_the_limit_is_accepted() -> None:
    assert (
        status(
            "vol.garch.forecast",
            '{"omega":5e-06,"alpha":0.12,"beta":0.82,"next_variance":0.0003,"horizon":100000,"periods_per_year":252.0}',
        )
        == "ok"
    )


# J-W3-18 to J-W3-20: fuzz run 43858847696 (seed 4).
HEDGE_OVERFLOW = (
    '{"a":[[1.0,9.5e+299],[0.95,1.0]],"b":[-1.265,-1.27],"weights":[1.0,1.0],"lot_sizes":[1.0,1.0]}'
)
CAP_DENORMAL = '{"model":"CIR","mean_reversion":0.25,"long_term_mean":0.04,"sigma":0.08,"short_rate":0.03,"period_times":[5e-324,2.0,3.0,4.0,5.0,6.0,7.0],"strike":0.03,"cap_floor":"CAP","notional":1000000.0}'
CAP_TINY = '{"model":"CIR","mean_reversion":0.25,"long_term_mean":0.04,"sigma":0.08,"short_rate":0.03,"period_times":[1e-200,2.0,3.0,4.0,5.0,6.0,7.0],"strike":0.03,"cap_floor":"CAP","notional":1000000.0}'
MV_HUGE_LOWER = '{"expected_returns":[0.06771,0.098313,0.028432,0.05484,0.045746,0.009556,0.108223,0.055019],"covariance":[[0.048331,0.004555,-0.017935,0.016324,-0.006755,0.004188,0.012427,-0.006854],[0.004555,0.032681,-0.003512,-0.000217,-0.010136,0.022911,0.013417,-0.001925],[-0.017935,-0.003512,0.034533,-0.005937,0.014412,-0.007383,-0.004539,0.001099],[0.016324,-0.000217,-0.005937,0.036879,0.00083,-0.002874,-0.011025,-0.005214],[-0.006755,-0.010136,0.014412,0.00083,0.042148,-0.007134,-0.006968,-0.002897],[0.004188,0.022911,-0.007383,-0.002874,-0.007134,0.045017,0.009949,0.000445],[0.012427,0.013417,-0.004539,-0.011025,-0.006968,0.009949,0.055737,-0.002087],[-0.006854,-0.001925,0.001099,-0.005214,-0.002897,0.000445,-0.002087,0.030976]],"risk_aversion":3.0,"lower":[-9007199254740992.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0],"upper":[0.2375,0.2375,0.2375,0.2375,0.2375,0.2375,0.2375,0.2375]}'


def test_jw3_18_integer_normal_equations_overflow() -> None:
    assert status("hedge.integer.solve", HEDGE_OVERFLOW) == "E_NON_FINITE"


def test_jw3_20_cir_cap_at_a_denormal_first_time() -> None:
    assert status("rates.shortrate.capfloor", CAP_DENORMAL) == "E_NON_FINITE"
    assert status("rates.shortrate.capfloor", CAP_TINY) == "E_NON_FINITE"


def test_jw3_19_mean_variance_start_meets_the_budget() -> None:
    request = {
        "schema_version": "1.0",
        "case_id": "c",
        "operation": "research.portfolio.mean_variance",
    }
    r = run_case(json.dumps({**request, "inputs": json.loads(MV_HUGE_LOWER)}))
    assert r["status"] == "ok"
    w = r["outputs"]["weights"]
    assert abs(sum(w) - 1.0) < 1e-12
    assert w[0] == pytest.approx(
        0.062395242276264584, abs=1e-12
    )  # optim_j-0015: the bound is not active


def test_jw3_19_repair_moves_the_shortfall_in_index_order() -> None:
    from quantforge_core.research_w2 import _repair_budget

    assert _repair_budget([0.25, 0.0, 0.0], [-1.0, 0.0, 0.0], [0.25, 0.5, 0.5]) == [0.25, 0.5, 0.25]
    assert _repair_budget([0.5, 0.75, 0.0], [0.0, 0.0, 0.0], [1.0, 1.0, 1.0]) == [0.25, 0.75, 0.0]
    w = [0.5, 0.5 + 1e-13]
    assert _repair_budget(w, [0.0, 0.0], [1.0, 1.0]) is w
    assert w == [0.5, 0.5 + 1e-13]


# J-W3-21: CIR at a tiny but representable first time, noncentrality about 1.9e11.
CAP_1E10 = CAP_TINY.replace("1e-200", "1e-10")


def _caplets(inputs: str) -> list[float]:
    r = run_case(
        json.dumps(
            {
                "schema_version": "1.0",
                "case_id": "c",
                "operation": "rates.shortrate.capfloor",
                "inputs": json.loads(inputs),
            }
        )
    )
    assert r["status"] == "ok", r
    return r["outputs"]["caplet_prices"]


def test_jw3_21_cir_cap_at_a_tiny_first_time() -> None:
    # N (P(0, t_0) - (1 + K tau_1) P(0, 2)): both chi-square CDFs are below e^-7e8 (C++ gave 3690.6).
    assert _caplets(CAP_1E10)[0] == pytest.approx(5790.068868782696, rel=1e-12)
    assert _caplets(CAP_1E10.replace('"CAP"', '"FLOOR"'))[0] == 0.0
    near = CAP_1E10.replace('"short_rate":0.03', '"short_rate":0.0263').replace("1e-10", "1e-06")
    assert status("rates.shortrate.capfloor", near) == "E_LIMIT"


def test_jw3_21_chernoff_settles_only_negligible_tails() -> None:
    from quantforge_core.shortrate import _ncx2_chernoff, ncx2_cdf

    lam = 1.87e11
    assert _ncx2_chernoff(0.877 * lam, 2.5, lam) == 0.0
    assert _ncx2_chernoff(1.2 * lam, 2.5, lam) == 1.0
    assert _ncx2_chernoff(lam, 2.5, lam) is None  # at the mean: not settled
    # The largest golden noncentrality (lambda/2 = 2,110, 26 standard deviations out) stays on the series.
    lam, k = 4220.0, 2.5
    x = k + lam + 26.2 * (2 * (k + 2 * lam)) ** 0.5
    assert _ncx2_chernoff(x, k, lam) is None
    assert _ncx2_chernoff(k + lam - 26.2 * (2 * (k + 2 * lam)) ** 0.5, k, lam) is None
    # Settled tails agree with the series where both run (lambda/2 = 1e4, 60 standard deviations out).
    lam = 2e4
    lo = k + lam - 60 * (2 * (k + 2 * lam)) ** 0.5
    assert _ncx2_chernoff(lo, k, lam) == 0.0
    with pytest.raises(Exception, match="too large"):
        ncx2_cdf(4e5 + 2.5, 2.5, 4e5)  # lambda/2 = 2e5 at the mean: E_LIMIT
