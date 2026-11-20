"""Unit tests for `quantforge_core.bermudan_k8` that run inside the mutation harness (stage K round 2).

The k8_k goldens compare the ladder at the `aad_sensitivity` tolerance, which a small change in the
scheme can pass. These tests pin the scheme on small grids that run in well under a second: the dual
arithmetic helpers against hand values, the tangent ladder against central finite differences of
the price (the ladder is the exact derivative of the discrete scheme, so the two agree to the
bump error), and prices and ladders measured from the current code, which passes the k8_k and e2_k
goldens (evidence class: measured), at a relative 1e-11.
"""

import math
from typing import Any

import numpy as np
import pytest

from quantforge_core import bermudan_k8 as b

T = [0.5, 1.0, 2.0, 3.0, 5.0, 7.0]
D = [0.985, 0.97, 0.93, 0.89, 0.82, 0.76]
BASE: dict[str, Any] = {
    "a": 0.05,
    "sigma": 0.01,
    "rate_given": False,
    "start": 1.0,
    "payment_times": [2.0, 3.0, 4.0, 5.0],
    "fixed_rate": 0.035,
    "notional": 1e6,
    "exercise_times": [1.0, 2.0, 3.0, 4.0],
    "nx": 41,
    "steps_per_year": 12,
    "width": 6.0,
}
REL = 1e-11


def _d(*xs: float) -> Any:
    return np.array(xs, dtype=float)


def _ladder_close(r: dict[str, Any], e: dict[str, Any]) -> None:
    assert list(r) == list(e)
    scale = max(abs(x) for x in e["d_price_d_discount_factors"])
    assert r["price"] == pytest.approx(e["price"], rel=REL)
    for x, y in zip(r["d_price_d_discount_factors"], e["d_price_d_discount_factors"], strict=True):
        assert x == pytest.approx(y, rel=REL, abs=REL * scale)
    assert r["d_price_d_mean_reversion"] == pytest.approx(e["d_price_d_mean_reversion"], rel=REL)
    assert r["d_price_d_sigma"] == pytest.approx(e["d_price_d_sigma"], rel=REL)


def test_dual_arithmetic() -> None:
    u, v = _d(2.0, 1.0, 3.0), _d(5.0, -2.0, 0.5)
    assert b._mul(u, v).tolist() == [10.0, 2.0 * -2.0 + 5.0 * 1.0, 2.0 * 0.5 + 5.0 * 3.0]
    q = b._div(u, v)
    assert q[0] == 0.4
    assert q[1] == pytest.approx((1.0 - 0.4 * -2.0) / 5.0, rel=1e-15)
    assert q[2] == pytest.approx((3.0 - 0.4 * 0.5) / 5.0, rel=1e-15)
    e = b._exp(_d(0.5, 2.0))
    assert e.tolist() == [math.exp(0.5), 2.0 * math.exp(0.5)]
    m = b._expm1(_d(0.5, 2.0))
    assert m.tolist() == [math.expm1(0.5), 2.0 * math.exp(0.5)]
    s = b._sqrt(_d(4.0, 3.0))
    assert s.tolist() == [2.0, 3.0 * 0.25]
    f = b._func(_d(1.0, 2.0, -1.0), np.array(7.0), np.array(3.0))
    assert f.tolist() == [7.0, 6.0, -3.0]
    p = b._plus(_d(1.0, 2.0), 3.0)
    assert p.tolist() == [4.0, 2.0]
    two = np.array([[1.0, 1.0], [2.0, 0.0]])
    assert b._mul(two, two).tolist() == [[1.0, 2.0], [4.0, 0.0]]
    assert b.METHOD == "CN_RANNACHER_SMOOTHED" and b.START_UP_STEPS == 2


def test_curve_and_model() -> None:
    logs = np.array([[0.0, 0.0], [math.log(0.9), 1.0], [math.log(0.8), 0.0]])
    c = b._Curve((0.0, 1.0, 3.0), logs)
    assert c.log_discount(0.0).tolist() == [0.0, 0.0]
    assert c.log_discount(-1.0).tolist() == [0.0, 0.0]
    assert c.log_discount(1.0).tolist() == pytest.approx([math.log(0.9), 1.0], rel=1e-15)
    assert c.log_discount(0.5).tolist() == pytest.approx([0.5 * math.log(0.9), 0.5], rel=1e-15)
    mid = c.log_discount(2.0).tolist()
    assert mid == pytest.approx([0.5 * (math.log(0.9) + math.log(0.8)), 0.5], rel=1e-15)
    far = c.log_discount(5.0).tolist()  # flat-forward extrapolation on the last segment
    assert far == pytest.approx(
        [math.log(0.8) + 1.0 * (math.log(0.8) - math.log(0.9)), -1.0], rel=1e-14
    )
    m = b._Model(c, _d(0.1, 1.0), _d(0.02, 0.0))
    assert m.s2.tolist() == pytest.approx([0.0004, 0.0], rel=1e-15)
    bb = m.big_b(2.0)
    assert bb[0] == pytest.approx((1 - math.exp(-0.2)) / 0.1, rel=1e-14)
    # d/da (1 - exp(-a t)) / a = (t exp(-a t) a - (1 - exp(-a t))) / a^2
    da = (2.0 * math.exp(-0.2) * 0.1 - (1 - math.exp(-0.2))) / 0.01
    assert bb[1] == pytest.approx(da, rel=1e-12)


def test_hat_part() -> None:
    p = np.array([[1.0, 0.0], [1.0, 0.0], [-1.0, 0.0], [-1.0, 0.0]])
    q = np.array([[2.0, 0.0], [-1.0, 0.0], [1.0, 0.0], [-2.0, 0.0]])
    h = b._hat_part(p, q)[:, 0]
    # both >= 0: p/3 + q/6; a crossing at u = 1/2; both negative: 0
    assert h[0] == pytest.approx(1 / 3 + 2 / 6, rel=1e-15)
    assert h[1] == pytest.approx(0.5 - 0.375 + 1 / 12, rel=1e-15)  # int_0^.5 (1-u)(1-2u) du
    assert h[2] == pytest.approx(1 / 24, rel=1e-15)  # int_.5^1 (1-u)(2u-1) du
    assert h[3] == 0.0
    zero = b._hat_part(np.array([[0.0, 1.0]]), np.array([[0.0, 1.0]]))
    assert zero.tolist() == [[0.0, 0.5]]
    up = b._hat_part(np.array([[-1.0, 1.0]]), np.array([[3.0, 0.0]]))
    r = 3.0 / 4.0
    assert up[0, 0] == pytest.approx(3.0 * r * r / 6, rel=1e-15)


def test_smoothed_max() -> None:
    xs = np.linspace(-2.0, 2.0, 9)
    v = np.stack([xs, np.ones(9)], axis=1)
    e = np.zeros((9, 2))
    out = b._smoothed_max(v, e)
    # far from the kink the hat average of a linear positive part is the value itself
    assert out[-1, 0] == pytest.approx(2.0, rel=1e-14)
    assert out[-2, 0] == pytest.approx(1.5, rel=1e-14)
    # the 1 - delta^2/6 stencil dips below zero next to the kink
    assert out[0, 0] == pytest.approx(0.0, abs=1e-15)
    assert out[1, 0] == pytest.approx(0.0, abs=1e-15)
    measured = [
        0.0,
        0.0,
        0.0,
        -0.013888888888888888,
        0.02777777777777777,
        0.4861111111111111,
        1.0,
        1.5,
        2.0,
    ]
    assert out[:, 0].tolist() == pytest.approx(measured, rel=1e-13, abs=1e-15)
    # a crossing inside a cell takes the third-order correction
    v2 = np.stack([xs + 0.1, np.ones(9)], axis=1)
    out2 = b._smoothed_max(v2, e)
    assert out2[:, 0].tolist() == pytest.approx(
        [
            0.0,
            0.0,
            -0.00011111111111111113,
            -0.02288888888888889,
            0.09011111111111111,
            0.5928888888888888,
            1.1,
            1.6,
            2.1,
        ],
        rel=1e-12,
        abs=1e-15,
    )
    assert out2[:, 1].tolist() == pytest.approx(
        [
            0.0,
            0.0,
            -0.003333333333333334,
            -0.08666666666666664,
            0.7366666666666666,
            1.0533333333333332,
            1.0,
            1.0,
            1.0,
        ],
        rel=1e-12,
        abs=1e-15,
    )


def test_tridiagonal_solve() -> None:
    lower = np.array([[0.0, 0.0], [1.0, 0.5], [1.0, 0.0]])
    diag = np.array([[4.0, 1.0], [4.0, 0.0], [4.0, 0.0]])
    upper = np.array([[1.0, 0.0], [1.0, 0.0], [0.0, 0.0]])
    rhs = np.array([[5.0, 0.0], [6.0, 1.0], [5.0, 0.0]])
    y = b._solve(lower, diag, upper, rhs)
    a0 = np.array([[4.0, 1.0, 0.0], [1.0, 4.0, 1.0], [0.0, 1.0, 4.0]])
    y0 = np.linalg.solve(a0, rhs[:, 0])
    assert y[:, 0].tolist() == pytest.approx(y0.tolist(), rel=1e-14)
    da = np.array([[1.0, 0.0, 0.0], [0.5, 0.0, 0.0], [0.0, 0.0, 0.0]])
    dy = np.linalg.solve(a0, rhs[:, 1] - da @ y0)
    assert y[:, 1].tolist() == pytest.approx(dy.tolist(), rel=1e-13, abs=1e-15)
    c, den = b._thomas_value(lower[:, 0], diag[:, 0], upper[:, 0])
    assert den[0] == 4.0 and c[0] == 0.25 and den[1] == 3.75


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        (
            "PAYER",
            {
                "price": 33548.709660858076,
                "d_price_d_discount_factors": [
                    0.0, 600217.2648216091, 121916.14534858963, 39798.93182098962,
                    -850567.1972085021, 0.0,
                ],
                "d_price_d_mean_reversion": -25170.541629156807,
                "d_price_d_sigma": 1338058.8025616794,
            },
        ),
        (
            "RECEIVER",
            {
                "price": 7993.020275911403,
                "d_price_d_discount_factors": [
                    0.0, -59846.713695931176, -107477.76561273652, -179084.87438483545,
                    396809.9911991625, 0.0,
                ],
                "d_price_d_mean_reversion": -29530.246284734774,
                "d_price_d_sigma": 1416305.3145329908,
            },
        ),
    ],
)  # fmt: skip
def test_ladder_pinned(kind: str, expected: dict[str, Any]) -> None:
    r = b.bermudan_ladder(T, D, swaption_type=kind, **BASE)
    _ladder_close(r, expected)
    p = b.bermudan_price(T, D, swaption_type=kind, **BASE)
    assert p == {"price": r["price"]}


def test_coarse_grids_pinned() -> None:
    r = b.bermudan_ladder(T, D, 0.08, 0.012, False, 0.75, [1.25, 1.6, 2.5], 0.03, "RECEIVER", 100.0,
                          [0.75, 1.6], 9, 2, 5.0)  # fmt: skip
    _ladder_close(r, {
        "price": 0.06944939839477977,
        "d_price_d_discount_factors": [-1.533408304123373, -6.330879792514468, 0.39558838032580335,
                                       8.26169975617117, 0.0, 0.0],
        "d_price_d_mean_reversion": -0.305845280175501,
        "d_price_d_sigma": 22.65790257269163,
    })  # fmt: skip
    r = b.bermudan_ladder(T, D, 0.08, 0.012, False, 0.75, [1.25, 1.6, 2.5], 0.03, "PAYER", 100.0,
                          [0.75, 1.6], 7, 1, 4.0)  # fmt: skip
    _ladder_close(r, {
        "price": 1.9300508078662202,
        "d_price_d_discount_factors": [40.52530862398161, 44.18624165607973, -40.54055197095063,
                                       -48.47788680917856, 0.0, 0.0],
        "d_price_d_mean_reversion": -0.2558059037743948,
        "d_price_d_sigma": 22.56645598452309,
    })  # fmt: skip


def test_ladder_matches_finite_differences() -> None:
    r = b.bermudan_ladder(T, D, swaption_type="PAYER", **BASE)

    def price(dfs: list[float], a: float, sigma: float) -> float:
        args = {**BASE, "a": a, "sigma": sigma}
        out: float = b.bermudan_price(T, dfs, swaption_type="PAYER", **args)["price"]
        return out

    h = 1e-6
    for j in (1, 2, 4):
        up = [d * (1 + h) if i == j else d for i, d in enumerate(D)]
        dn = [d * (1 - h) if i == j else d for i, d in enumerate(D)]
        fd = (price(up, 0.05, 0.01) - price(dn, 0.05, 0.01)) / (2 * h * D[j])
        assert r["d_price_d_discount_factors"][j] == pytest.approx(fd, rel=1e-5)
    fd_a = (price(D, 0.05 + 1e-6, 0.01) - price(D, 0.05 - 1e-6, 0.01)) / 2e-6
    assert r["d_price_d_mean_reversion"] == pytest.approx(fd_a, rel=1e-5)
    fd_s = (price(D, 0.05, 0.01 + 1e-7) - price(D, 0.05, 0.01 - 1e-7)) / 2e-7
    assert r["d_price_d_sigma"] == pytest.approx(fd_s, rel=1e-5)


def test_scheme_value_only_matches_tangent_column() -> None:
    args = (T, D, 0.05, 0.01, [2.0, 3.0, 4.0, 5.0], 0.035, True, [1.0, 2.0, 3.0, 4.0], 41, 12, 6.0)
    v = b.scheme(*args, False)
    t = b.scheme(*args, True)
    assert v.shape == (1,) and t.shape == (len(T) + 3,)
    assert v[0] == t[0] == pytest.approx(0.033548709660858076, rel=REL)
