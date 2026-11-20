"""Unit tests for the stage K Python modules `stage_k` (wave 1 operations), `saccr` and `bermudan_k8`
that run inside the mutation harness (stage K round 2).

test_stage_k_w1.py and test_stage_k_w1b.py read datasets/ and specifications/ outside python/, which
the mutmut copy of python/ does not hold, so they cannot be in the mutmut tests_dir. These tests pin
the same contracts with values written out here. Evidence classes: closed forms (t distribution with
1 and 2 degrees of freedom, the par bootstrap recursion, Richardson extrapolation) are derived by
hand; other numbers are measured from the current code, which passes the stage K goldens
(datasets/golden/stage_k), and are pinned to catch a change. Error checks pin code, field and
message, as test_frtb_backtest_kills.py does.
"""

import math
from typing import Any

import pytest

from quantforge_core import stage_k as sk
from quantforge_core.errors import QfError

B = sk.BiRecord
_NONE: list[Any] = [None]
Z = sk.ZeroPosition


def _err(f: Any, *args: Any) -> tuple[str, str | None, str]:
    with pytest.raises(QfError) as e:
        f(*args)
    return e.value.code, e.value.field, e.value.message


# --- constants and helpers -------------------------------------------------------------------------


def test_constants() -> None:
    assert sk.LABEL == "latency-aware analytics on simulated data"
    assert sk.MAX_RECORDS == 100_000 and sk.MAX_QUOTES == 200
    assert sk.MAX_CHANGES == 100_000 and sk.MAX_POSITIONS == 100_000
    assert sk.NOISE_FLOOR == 2.0**-26 and sk.ROUNDING_FACTOR == 2.0**-49
    assert sk._UP == 2.0**500 and sk._DOWN == 2.0**-500
    assert sk._TWO_OVER_PI == pytest.approx(2 / math.pi, rel=1e-16, abs=0)
    assert sk._C_HI + sk._C_LO == pytest.approx(1 / math.sqrt(2), rel=1e-15, abs=0)


def test_error_helpers() -> None:
    e = sk._input("m", "f")
    assert (e.code, e.message, e.field) == ("E_INPUT", "m", "f")
    e = sk._domain("m", "f")
    assert (e.code, e.message, e.field) == ("E_DOMAIN", "m", "f")
    assert sk._input("m").field is None and sk._domain("m").field is None
    e = sk._limit("xs", 7)
    assert (e.code, e.message, e.field) == ("E_LIMIT", "xs is above its limit of 7", "xs")


def test_too_long() -> None:
    assert sk._too_long([1, 2, 3], 2) is True
    assert sk._too_long([1, 2], 2) is False
    assert sk._too_long(5, 0) is False


def test_limits() -> None:
    big = [0.0] * 201
    assert _err(sk._quotes_limit, big) == ("E_LIMIT", "quotes", "quotes is above its limit of 200")
    sk._quotes_limit([0.0] * 200)
    for i, field in enumerate(("previous_quotes", "previous_discount_factors", "new_quotes")):
        args = [[0.0], [0.0], [0.0]]
        args[i] = big
        assert _err(sk._update_limit, *args) == (
            "E_LIMIT",
            field,
            f"{field} is above its limit of 200",
        )
    sk._update_limit([0.0] * 200, [0.0] * 200, [0.0] * 200)
    assert _err(sk._records_limit, _NONE * 100_001)[:2] == ("E_LIMIT", "records")
    sk._records_limit(_NONE * 100_000)
    assert _err(sk._changes_limit, [0.0] * 100_001)[:2] == ("E_LIMIT", "changes")
    sk._changes_limit([0.0] * 100_000)
    assert _err(sk._positions_limit, _NONE * 100_001)[:2] == ("E_LIMIT", "positions")
    sk._positions_limit(_NONE * 100_000)
    assert sk.par_annual.__qf_limits__ is sk._quotes_limit  # type: ignore[attr-defined]
    assert sk.incremental_update.__qf_limits__ is sk._update_limit  # type: ignore[attr-defined]
    assert sk.bitemporal_query.__qf_limits__ is sk._records_limit  # type: ignore[attr-defined]
    assert sk.trigger_check.__qf_limits__ is sk._changes_limit  # type: ignore[attr-defined]
    assert sk.delta_gamma_bound.__qf_limits__ is sk._positions_limit  # type: ignore[attr-defined]


def test_public_limits_raise() -> None:
    assert _err(sk.par_annual, [0.01] * 201)[:2] == ("E_LIMIT", "quotes")
    assert _err(sk.trigger_check, [0.0] * 100_001, 0.0, 0.0, 1.0, 1.0)[:2] == ("E_LIMIT", "changes")
    p = Z(1.0, 1.0, 0.0)
    assert _err(sk.delta_gamma_bound, [p] * 100_001, 0.0)[:2] == ("E_LIMIT", "positions")
    q = [0.01] * 201
    assert _err(sk.incremental_update, q, q, q)[:2] == ("E_LIMIT", "previous_quotes")


# --- bitemporal store ------------------------------------------------------------------------------


def _log() -> list[sk.BiRecord]:
    return [
        B(1, "S", 0, None, 10, "a", False),
        B(2, "S", 5, 20, 20, "b", False),
        B(3, "T", 0, None, 30, "t", False),
        B(4, "S", 5, 20, 40, None, True),
        B(5, "S", 0, 5, 50, "c", False),
    ]


def test_bitemporal_query() -> None:
    log = _log()
    assert sk.bitemporal_query(log, "S", 9, 0) == ("NONE", None)
    assert sk.bitemporal_query(log, "S", 10, 0) == ("FOUND", log[0])  # K inclusive
    assert sk.bitemporal_query(log, "S", 20, 5) == ("FOUND", log[1])  # valid_from inclusive
    assert sk.bitemporal_query(log, "S", 20, 4) == ("FOUND", log[0])
    assert sk.bitemporal_query(log, "S", 20, 20) == ("FOUND", log[0])  # valid_to exclusive
    assert sk.bitemporal_query(log, "S", 20, 19) == ("FOUND", log[1])
    assert sk.bitemporal_query(log, "S", 40, 10) == ("WITHDRAWN", None)
    assert sk.bitemporal_query(log, "S", 40, 25) == ("FOUND", log[0])
    assert sk.bitemporal_query(log, "S", 50, 0) == ("FOUND", log[4])
    assert sk.bitemporal_query(log, "T", 30, 100) == ("FOUND", log[2])
    assert sk.bitemporal_query(log, "U", 99, 0) == ("NONE", None)
    # the highest sequence wins even when listed in increasing order with equal knowledge times
    tie = [B(1, "S", 0, None, 10, "x", False), B(2, "S", 0, None, 10, "y", False)]
    assert sk.bitemporal_query(tie, "S", 10, 0) == ("FOUND", tie[1])
    assert sk.bitemporal_query([], "S", 0, 0) == ("NONE", None)


def test_bitemporal_log_errors() -> None:
    seq = [B(2, "S", 0, None, 1, 1, False), B(2, "S", 0, None, 2, 1, False)]
    assert _err(sk.bitemporal_query, seq, "S", 0, 0) == (
        "E_INPUT",
        "records",
        "sequence must be strictly increasing",
    )
    kt = [B(1, "S", 0, None, 5, 1, False), B(2, "S", 0, None, 4, 1, False)]
    assert _err(sk.bitemporal_query, kt, "S", 0, 0) == (
        "E_INPUT",
        "records",
        "knowledge_time went backwards",
    )
    sk.bitemporal_query(
        [B(1, "S", 0, None, 5, 1, False), B(2, "S", 0, None, 5, 1, False)], "S", 0, 0
    )
    vt = [B(1, "S", 3, 3, 5, 1, False)]
    assert _err(sk.bitemporal_query, vt, "S", 0, 0) == (
        "E_INPUT",
        "records",
        "valid_to must be after valid_from",
    )
    sk.bitemporal_query([B(1, "S", 3, 4, 5, 1, False)], "S", 0, 0)
    # sequence is checked over the whole log before knowledge time (spec order)
    both = [
        B(1, "S", 0, None, 5, 1, False),
        B(2, "S", 0, None, 4, 1, False),
        B(2, "S", 0, None, 6, 1, False),
    ]
    assert _err(sk.bitemporal_query, both, "S", 0, 0)[2] == "sequence must be strictly increasing"
    order = [B(1, "S", 3, 3, 5, 1, False), B(2, "S", 0, None, 4, 1, False)]
    assert _err(sk.bitemporal_query, order, "S", 0, 0)[2] == "knowledge_time went backwards"


# --- par bootstrap and incremental update ----------------------------------------------------------


def _boot(quotes: list[float]) -> list[float]:
    out: list[float] = []
    for s in quotes:
        out.append((1.0 - s * sum(out)) / (1.0 + s))
    return out


def test_par_annual() -> None:
    q = [0.01, 0.02, 0.03]
    dfs = sk.par_annual(q)["discount_factors"]
    assert dfs == [0.9900990099009901, 0.9609784507862551, 0.9140462875527987]
    assert dfs == pytest.approx(_boot(q), rel=1e-15, abs=0)
    assert sk.par_annual([0.0])["discount_factors"] == [1.0]
    assert sk.par_annual([-0.5])["discount_factors"] == [2.0]
    assert sk._bootstrap_from([0.01, 0.02], [0.5]) == [0.5, (1.0 - 0.02 * 0.5) / 1.02]
    assert sk._bootstrap_from([0.1, 0.2, 0.3], [0.5, 0.25]) == [0.5, 0.25, (1.0 - 0.3 * 0.75) / 1.3]


def test_par_annual_errors() -> None:
    assert _err(sk.par_annual, []) == ("E_INPUT", "quotes", "quotes must hold at least one quote")
    assert _err(sk.par_annual, [0.01, -1.0]) == (
        "E_DOMAIN",
        "quotes",
        "every quote must be above -1",
    )
    sk.check_quotes_shape(1)
    assert _err(sk._check_quotes, [-1.5], "x") == ("E_DOMAIN", "x", "every quote must be above -1")
    sk._check_quotes([-0.999], "x")


def test_incremental_update() -> None:
    q = [0.01, 0.02, 0.03]
    dfs = sk.par_annual(q)["discount_factors"]
    out = sk.incremental_update(q, dfs, [0.01, 0.025, 0.03])
    assert out == {
        "discount_factors": [0.9900990099009901, 0.9514609997585125, 0.9143234948642862],
        "first_changed_index": 1,
        "recomputed": 2,
    }
    assert out["discount_factors"] == sk.par_annual([0.01, 0.025, 0.03])["discount_factors"]
    first = sk.incremental_update(q, dfs, [0.02, 0.02, 0.03])
    assert first["first_changed_index"] == 0 and first["recomputed"] == 3
    last = sk.incremental_update(q, dfs, [0.01, 0.02, 0.04])
    assert last["first_changed_index"] == 2 and last["recomputed"] == 1
    assert last["discount_factors"][:2] == dfs[:2]
    same = sk.incremental_update(q, dfs, list(q))
    assert same == {"discount_factors": dfs, "first_changed_index": None, "recomputed": 0}


def test_incremental_update_errors() -> None:
    q = [0.01, 0.02]
    dfs = sk.par_annual(q)["discount_factors"]
    msg = (
        "previous_quotes, previous_discount_factors and new_quotes must have one equal, "
        "non-zero length"
    )
    assert _err(sk.incremental_update, [], [], []) == ("E_INPUT", "new_quotes", msg)
    assert _err(sk.incremental_update, q, dfs, [0.01]) == ("E_INPUT", "new_quotes", msg)
    assert _err(sk.incremental_update, q, dfs[:1], q) == ("E_INPUT", "new_quotes", msg)
    sk.check_update_shape(1, 1, 1)
    assert _err(sk.incremental_update, [0.01, -2.0], dfs, q) == (
        "E_DOMAIN",
        "previous_quotes",
        "every quote must be above -1",
    )
    assert _err(sk.incremental_update, q, dfs, [0.01, -2.0]) == (
        "E_DOMAIN",
        "new_quotes",
        "every quote must be above -1",
    )
    stale = "previous_discount_factors is not the bootstrap of previous_quotes"
    bad = [dfs[0], dfs[1] + 1e-16]
    assert _err(sk.incremental_update, q, bad, q) == ("E_INPUT", "previous_discount_factors", stale)
    # a signed zero in the cache differs from the bootstrap's +0.0
    zq = [0.0, 1.0]
    zd = sk.par_annual(zq)["discount_factors"]
    assert zd == [1.0, 0.0] and math.copysign(1.0, zd[1]) == 1.0
    neg = [zd[0], -0.0]
    assert _err(sk.incremental_update, zq, neg, zq) == (
        "E_INPUT",
        "previous_discount_factors",
        stale,
    )


# --- recalibration trigger -------------------------------------------------------------------------


def test_sample_sd() -> None:
    assert sk._sample_sd([1.0, 3.0]) == math.sqrt(2.0)
    assert sk._sample_sd([1.0, 2.0, 3.0, 4.0]) == math.sqrt(5.0 / 3.0)


def test_trigger_check() -> None:
    out = sk.trigger_check([0.1, -0.2, 0.3, 0.05], 1.0, 1.9, 4.0, 2.0)
    assert out == {
        "fire": True,
        "sigma": 0.2056493779875511,
        "threshold": 0.8225975119502044,
        "false_alarm_rate": 0.1393259685588432,
        "nominal_rate": 0.04550026389635841,
    }
    assert out["threshold"] == 2.0 * out["sigma"] * 2.0
    assert out["false_alarm_rate"] == sk.student_t_two_sided_tail(3, 2.0)
    # strict: equality does not fire; days_since = 1 is allowed
    c = [1.0, 3.0]
    sigma = math.sqrt(2.0)
    eq = sk.trigger_check(c, 0.0, 1.0 * sigma, 1.0, 1.0)
    assert eq["fire"] is False and eq["threshold"] == sigma
    assert sk.trigger_check(c, 0.0, -1.5, 1.0, 1.0)["fire"] is True
    assert sk.trigger_check(c, 0.0, -1.4, 1.0, 1.0)["fire"] is False
    assert sk.trigger_check(c, 2.0, 0.5, 1.0, 1.0)["fire"] is True


def test_trigger_check_errors() -> None:
    assert _err(sk.trigger_check, [1.0], 0.0, 0.0, 1.0, 1.0) == (
        "E_INPUT",
        "changes",
        "changes must hold at least two one-day changes",
    )
    sk.check_changes_shape(2)
    assert _err(sk.trigger_check, [1.0, 2.0], 0.0, 0.0, 1.0, 0.0) == (
        "E_DOMAIN",
        "k",
        "k must be above 0",
    )
    assert _err(sk.trigger_check, [1.0, 2.0], 0.0, 0.0, 0.999, 1.0) == (
        "E_DOMAIN",
        "days_since",
        "days_since must be at least 1",
    )
    assert _err(sk.trigger_check, [1.0, 2.0], 0.0, 0.0, 0.0, 0.0)[1] == "k"
    flat = "the changes have no noise scale (sigma at or below 2^-26 max|c|)"
    assert _err(sk.trigger_check, [1.0, 1.0, 1.0], 0.0, 0.0, 1.0, 1.0) == (
        "E_DOMAIN",
        "changes",
        flat,
    )
    # sigma just above and at the floor, scaled by max |c| (a negative change counts by its size)
    tiny = 2.0**-26
    assert _err(sk.trigger_check, [-1.0, -1.0 + tiny * math.sqrt(2.0) * 0.5], 0.0, 0.0, 1.0, 1.0)[
        1
    ] == ("changes")
    sk.trigger_check([-1.0, -1.0 + 4 * tiny], 0.0, 0.0, 1.0, 1.0)
    assert _err(sk.trigger_check, [0.0, 0.0], 0.0, 0.0, 1.0, 1.0)[1] == "changes"


@pytest.mark.parametrize("k", [0.25, 0.5, 1.0, 1.7, 3.0, 10.0, 100.0])
def test_t_tail_closed_forms(k: float) -> None:
    # nu = 1 (Cauchy): 1 - (2/pi) atan(k); nu = 2: 1 - k / sqrt(2 + k^2)
    assert sk.student_t_two_sided_tail(1, k) == pytest.approx(
        1 - 2 / math.pi * math.atan(k), rel=1e-13
    )
    assert sk.student_t_two_sided_tail(2, k) == pytest.approx(
        1 - k / math.sqrt(2 + k * k), rel=1e-12
    )


@pytest.mark.parametrize(
    ("nu", "k", "value"),
    [
        (1, 0.5, 0.7048327646991335),
        (1, 3.0, 0.20483276469913345),
        (2, 0.5, 0.6666666666666667),
        (2, 3.0, 0.09546596626670911),
        (3, 1.0, 0.3910022189557706),
        (3, 10.0, 0.00212839905841415),
        (4, 2.5, 0.06676654481198815),
        (5, 0.3, 0.7762490422632744),
        (10, 4.0, 0.0025183326247366932),
        (7, 50.0, 3.3512525955500453e-10),
        (30, 2.0, 0.054625044962983),
        (40, 30.0, 4.850907660590223e-29),
        (41, 30.0, 1.6054494689900398e-29),
        (9, 1e6, 5.091794074026567e-51),
        (60, 1e5, 2.2677354768709296e-248),
        (61, 1e5, 2.8843982046547086e-252),
        (16, 1e9, 8.434483200000006e-136),
        (17, 1e9, 5.484643666634028e-144),
    ],
)
def test_t_tail_values(nu: int, k: float, value: float) -> None:
    assert sk.student_t_two_sided_tail(nu, k) == pytest.approx(value, rel=1e-13, abs=0)


def test_t_tail_exact_points() -> None:
    assert sk.student_t_two_sided_tail(1, 1.0) == 0.5
    assert sk.student_t_two_sided_tail(2, math.sqrt(2.0)) == pytest.approx(
        1 - 1 / math.sqrt(2), rel=1e-15
    )
    assert sk.student_t_two_sided_tail(200, 1e3) == 0.0


def test_t_step() -> None:
    assert sk._t_step(1.0, 0, 0.5, True) == (1.0 * (2 * 0.5)) / 3
    assert sk._t_step(1.0, 1, 0.5, True) == (1.0 * (4 * 0.5)) / 5
    assert sk._t_step(1.0, 0, 0.5, False) == (1.0 * (1 * 0.5)) / 2
    assert sk._t_step(2.0, 2, 0.25, False) == (2.0 * (5 * 0.25)) / 6


@pytest.mark.parametrize(
    ("k", "value"),
    [
        (0.5, 0.6170750774519738),
        (1.0, 0.3173105078629141),
        (3.0, 0.002699796063260189),
        (30.0, 9.813427854296374e-198),
    ],
)
def test_normal_tail(k: float, value: float) -> None:
    assert sk.two_sided_normal_tail(k) == pytest.approx(value, rel=1e-15, abs=0)
    assert sk.two_sided_normal_tail(k) == pytest.approx(math.erfc(k / math.sqrt(2)), rel=1e-12)


# --- intraday delta-gamma --------------------------------------------------------------------------


PS = [Z(100.0, 2.0, 0.03), Z(-50.0, 5.0, 0.01)]


def test_position_pieces() -> None:
    expect = {
        (0, 0.01): (0.00012556860447789984, -1.8646937764968126, 7.263586091404493e-15),
        (0, -0.02): (0.0010455452515272057, 3.842399297023735, 1.51672807201456e-14),
        (1, 0.01): (0.0009908639838549108, 2.318621722220491, 9.413492686131426e-15),
        (1, -0.02): (0.008760592469800202, -4.9939544786287495, 2.0923701747466367e-14),
    }
    for (i, h), (bound, est, rnd) in expect.items():
        p = PS[i]
        assert sk.position_bound(p, h) == pytest.approx(bound, rel=1e-14, abs=0)
        assert sk.position_estimate(p, h) == pytest.approx(est, rel=1e-14, abs=0)
        assert sk.position_rounding(p, h) == pytest.approx(rnd, rel=1e-14, abs=0)
    # the bound uses min(y, y + h): exp(-T (y + h)) for a fall, exp(-T y) for a rise
    p = Z(1.0, 1.0, 0.0)
    assert sk.position_bound(p, 0.5) == pytest.approx(0.125 / 6, rel=1e-15, abs=0)
    assert sk.position_bound(p, -0.5) == pytest.approx(0.125 * math.exp(0.5) / 6, rel=1e-15, abs=0)
    assert sk.position_bound(Z(-2.0, 2.0, 0.0), 0.5) == pytest.approx(
        0.125 * 8 * 2 / 6, rel=1e-15, abs=0
    )
    assert sk.position_estimate(p, 0.5) == pytest.approx(-0.5 + 0.125, rel=1e-15, abs=0)
    assert sk.position_rounding(p, 0.0) == 0.0


def test_delta_gamma_bound() -> None:
    up = sk.delta_gamma_bound(PS, 0.01)
    assert up == {
        "estimate_pnl": 0.45392794572367823,
        "bound": 0.0011164325883494877,
        "label": "latency-aware analytics on simulated data",
    }
    down = sk.delta_gamma_bound(PS, -0.02)
    assert down["estimate_pnl"] == pytest.approx(-1.1515551816050147, rel=1e-14, abs=0)
    assert down["bound"] == pytest.approx(0.009806137721363498, rel=1e-14, abs=0)
    # the bound covers the full revaluation
    assert abs(sk.zero_revalue(PS, 0.01) - up["estimate_pnl"]) <= up["bound"]
    assert sk.zero_revalue(PS, 0.01) == pytest.approx(0.4547816034764296, rel=1e-14, abs=0)
    assert _err(sk.delta_gamma_bound, [], 0.01) == (
        "E_INPUT",
        "positions",
        "positions must not be empty",
    )
    sk.check_positions_shape(1)
    assert _err(sk.delta_gamma_bound, [Z(1.0, 0.0, 0.0)], 0.01) == (
        "E_DOMAIN",
        "positions.maturity",
        "every maturity must be above 0",
    )


# --- Richardson guard ------------------------------------------------------------------------------


def test_richardson() -> None:
    ok = sk.richardson_check([1.0, 0.75, 0.6875], 2.0, 2.0)
    assert ok == {"status": "OK", "observed_order": 2.0, "extrapolated": (4 * 0.6875 - 0.75) / 3}
    assert sk.richardson_check([1.0, 0.5, 0.25], 2.0, 2.0) == {
        "status": "ORDER_MISMATCH",
        "observed_order": 1.0,
        "extrapolated": None,
    }
    nm = {"status": "NON_MONOTONE", "observed_order": None, "extrapolated": None}
    assert sk.richardson_check([1.0, 0.5, 0.6], 2.0, 1.0) == nm
    assert sk.richardson_check([1.0, 1.0, 0.5], 2.0, 1.0) == nm
    assert sk.richardson_check([1.0, 0.5, 0.5], 2.0, 1.0) == nm
    # increasing values keep one sign too
    up = sk.richardson_check([0.0, 0.5, 0.75], 2.0, 1.0)
    assert up["status"] == "OK" and up["extrapolated"] == pytest.approx(1.0, rel=1e-15, abs=0)
    # |observed - assumed| <= 0.5 is inclusive at both ends
    assert sk.richardson_check([1.0, 0.5, 0.25], 2.0, 1.5)["status"] == "OK"
    assert sk.richardson_check([1.0, 0.5, 0.25], 2.0, 0.5)["status"] == "OK"
    assert sk.richardson_check([1.0, 0.5, 0.25], 2.0, 1.51)["status"] == "ORDER_MISMATCH"
    assert sk.richardson_check([1.0, 0.5, 0.25], 2.0, 0.49)["status"] == "ORDER_MISMATCH"
    r3 = sk.richardson_check([1.0, 1.0 / 3, 1.0 / 9], 3.0, 1.0)
    assert r3["observed_order"] == pytest.approx(1.0, rel=1e-14, abs=0)
    assert r3["extrapolated"] == pytest.approx((3 * (1 / 9) - 1 / 3) / 2, abs=1e-16)


def test_richardson_errors() -> None:
    assert _err(sk.richardson_check, [1.0, 2.0], 2.0, 1.0) == (
        "E_INPUT",
        "values",
        "values must hold exactly three grid values",
    )
    assert _err(sk.richardson_check, [1.0, 2.0, 3.0, 4.0], 2.0, 1.0)[1] == "values"
    assert _err(sk.richardson_check, [1.0, 2.0, 3.0], 1.0, 1.0) == (
        "E_DOMAIN",
        "ratio",
        "ratio must be above 1",
    )
    assert _err(sk.richardson_check, [1.0, 2.0, 3.0], 2.0, 0.0) == (
        "E_DOMAIN",
        "assumed_order",
        "assumed_order must be above 0",
    )
