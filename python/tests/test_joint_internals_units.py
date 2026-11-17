"""Unit tests for the internals of quantforge_core.joint: the start point, the finite-difference
columns, the conditioning check, the futures instrument, the output layout, the turn zeroing of
ruling F-26 and the funding-curve extrapolation (02-curves/joint-solve-and-funding.md, rulings F-24
to F-27 and F-40).

The full mutation run of this module (2026-11-16, 84 % killed) showed that these pieces were only
seen through a converged solve, where a different start, a lost stencil or a wrong key in an
unused branch changes nothing a repricing test can see. Expected values here come from closed
forms worked by hand (the Ho-Lee futures convexity at zero mean reversion, flat-curve start
points, 1-norm condition numbers of small matrices), from rebuilding the solved curves with
curves.Curve and steps.StepCurve and repricing with ois.par_rate and xccy.leg, or from re-solving
with a bumped quote; never from re-running the code under test."""

import math
import warnings
from datetime import date, timedelta
from types import SimpleNamespace
from typing import Any

import pytest

from quantforge_core import curves, joint, ois, xccy
from quantforge_core.curves import CurveData
from quantforge_core.errors import QfError
from quantforge_core.joint import CurveSpec, InstrumentSpec
from quantforge_core.steps import StepCurve

AS_OF = date(2026, 1, 5)
P1, P2 = date(2027, 1, 5), date(2028, 1, 5)
TURN = date(2026, 3, 31)
STEP = date(2026, 4, 1)
FUT_S, FUT_E = date(2026, 6, 17), date(2026, 9, 16)


def _err(fn: Any, code: str, field: str | None) -> str:
    with pytest.raises(QfError) as e:
        fn()
    assert e.value.code == code and e.value.field == field
    assert isinstance(e.value.message, str) and str(e.value) == e.value.message
    return e.value.message


# --------------------------------------------------------------------------------------------
# outputs: the exact layout


def test_outputs_layout_with_a_turn_on_each_curve_type() -> None:
    t1, t2, sd = date(2026, 6, 30), date(2026, 12, 31), date(2026, 9, 1)
    b0 = joint._Block(
        CurveSpec("P", "OIS", turns=(t1,)),
        pillars=[P1, P2],
        labels=["P:pillar:2027-01-05", "P:pillar:2028-01-05", "P:turn:2026-06-30"],
        offset=0,
    )
    b1 = joint._Block(
        CurveSpec("S", "OIS_STEPS", step_dates=(sd,), turns=(t2,)),
        labels=["S:base", "S:step:2026-09-01", "S:turn:2026-12-31"],
        offset=3,
    )
    x = [math.log(0.99), math.log(0.97), math.log(1.001), 0.02, 0.025, math.log(0.999)]
    jac = [[0.5, 0.25], [1.0, -1.0], [0.0, 2.0], [3.0, 0.0], [0.0, 4.0], [5.0, 6.0]]
    sens = [[0.1, 0.2], [0.3, 0.4]]
    r = joint.JointResult([b0, b1], x, jac, ["qa", "qb"], sens, 0.0)
    assert joint.outputs(AS_OF, r) == {
        "curves": [
            {
                "name": "P",
                "pillars": [
                    {"date": "2027-01-05", "discount_factor": math.exp(x[0])},
                    {"date": "2028-01-05", "discount_factor": math.exp(x[1])},
                ],
            },
            {"name": "S", "base_rate": 0.02, "step_rates": [0.025]},
        ],
        "turn_factors": [
            {"curve": "P", "date": "2026-06-30", "factor": math.exp(x[2])},
            {"curve": "S", "date": "2026-12-31", "factor": math.exp(x[5])},
        ],
        "jacobian": {
            "unknowns": [*b0.labels, *b1.labels],
            "quotes": ["qa", "qb"],
            "matrix": jac,
        },
        "turn_sensitivity": sens,
    }


# --------------------------------------------------------------------------------------------
# ruling F-40: the conditioning check


def test_check_conditioned_threshold_is_the_reciprocal_one_norm_condition() -> None:
    joint._check_conditioned([[1.0, 0.0], [0.0, 1.0]])
    joint._check_conditioned([[2.0, 1.0], [1.0, 3.0]])
    # diag(1, e): ||A||_1 = 1, ||A^-1||_1 = 1/e, so rcond = e. 2e-14 passes, 0.7e-14 does not.
    joint._check_conditioned([[1.0, 0.0], [0.0, 2e-14]])
    for a in ([[1.0, 0.0], [0.0, 0.7e-14]], [[1.0, 2.0], [2.0, 4.0]], [[0.0, 0.0], [0.0, 0.0]]):
        msg = _err(lambda a=a: joint._check_conditioned(a), "E_NO_CONVERGENCE", "instruments")
        assert msg == "dR/dx is singular at an iterate"
    # A = [[1, 1, 1], [0, e, 0], [0, 0, e]]: ||A||_1 = 1 + e, A^-1 = [[1, -1/e, -1/e], [0, 1/e, 0],
    # [0, 0, 1/e]] so ||A^-1||_1 = 2/e and cond_1 = 2 (1 + e) / e. The 2-norm condition is about
    # 3/e (sigma_max ~ sqrt 3, sigma_min ~ e / sqrt 3). With e = 2.5e-14 the 1-norm passes
    # (rcond 1.25e-14) where the 2-norm would not (rcond 0.83e-14): the ruling names the 1-norm.
    e = 2.5e-14
    joint._check_conditioned([[1.0, 1.0, 1.0], [0.0, e, 0.0], [0.0, 0.0, e]])


def test_check_conditioned_is_silent_on_a_singular_matrix() -> None:
    # the check reports through QfError only: numpy's divide and invalid warnings are suppressed
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        for a in (
            [[1.0, 2.0], [2.0, 4.0]],
            [[0.0, 0.0], [0.0, 0.0]],
            [[math.nan, 0.0], [0.0, 1.0]],
        ):
            _err(lambda a=a: joint._check_conditioned(a), "E_NO_CONVERGENCE", "instruments")


# --------------------------------------------------------------------------------------------
# the joint residual check, reached by skipping the Newton solve


def test_unsolved_system_is_reported_with_its_residual(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(joint, "_solve_block", lambda *args: None)
    specs = [CurveSpec("S", "OIS", convention="SOFR")]
    insts = [InstrumentSpec("S1", "S", "OIS", tenor="1Y", rate=0.04)]
    msg = _err(lambda: joint.joint_solve(AS_OF, specs, insts), "E_NO_CONVERGENCE", None)
    assert msg.startswith("joint solve residual ")
    assert float(msg.removeprefix("joint solve residual ")) > joint.TOLERANCE


# --------------------------------------------------------------------------------------------
# the futures instrument


def test_future_instrument_by_hand_at_zero_mean_reversion() -> None:
    sigma, price = 0.012, 97.75
    c = CurveSpec("E", "OIS_STEPS", convention="ESTR", step_dates=(STEP,))
    spec = InstrumentSpec("F", "E", "FUTURE", start=FUT_S, end=FUT_E, price=price, sigma=sigma)
    inst = joint._ois_instrument(AS_OF, c, spec)
    t = (FUT_S - AS_OF).days / 365
    big_t = (FUT_E - AS_OF).days / 365
    d = big_t - t
    # Hull-White at a = 0 (Ho-Lee): B(0, x) = x, so z = sigma^2 / 2 (2 t d^2 + d t^2)
    z = sigma * sigma / 2 * (2 * t * d * d + d * t * t)
    rate = (100 - price) / 100
    bias = (1 - math.exp(-z)) * (rate + 1 / d)
    assert inst.target == pytest.approx(rate - bias, rel=1e-13)
    assert bias > 1e-6  # the convexity is not negligible here, so its sign is seen
    assert inst.d_quote == pytest.approx(0.01 * math.exp(-z), rel=1e-14)
    assert inst.dates == [FUT_S, FUT_E] and inst.pillar == FUT_E and inst.spread_slope is None
    flat = SimpleNamespace(discount=lambda day: math.exp(-0.03 * (day - AS_OF).days / 365))
    alpha = (FUT_E - FUT_S).days / 360
    expect = (math.exp(0.03 * (FUT_E - FUT_S).days / 365) - 1) / alpha
    assert inst.model({"E": flat}) == pytest.approx(expect, rel=1e-13)


def test_future_with_end_equal_to_start_is_refused() -> None:
    c = CurveSpec("E", "OIS_STEPS", convention="ESTR", step_dates=(STEP,))
    spec = InstrumentSpec("F", "E", "FUTURE", start=FUT_S, end=FUT_S, price=98.0)
    msg = _err(lambda: joint._ois_instrument(AS_OF, c, spec), "E_INPUT", "instruments")
    assert msg == "F: end is not after start"


# --------------------------------------------------------------------------------------------
# the start point


def _four_curves(turn_on_steps: bool = True) -> tuple[list[CurveSpec], list[InstrumentSpec]]:
    specs = [
        CurveSpec("S", "OIS", convention="SOFR"),
        CurveSpec("T", "PROJECTION", index="USD-TERM-3M", discount="S"),
        CurveSpec(
            "E",
            "OIS_STEPS",
            convention="ESTR",
            step_dates=(STEP,),
            turns=(TURN,) if turn_on_steps else (),
        ),
        CurveSpec(
            "X",
            "XCCY",
            domestic="S",
            foreign_projection="E",
            domestic_convention="SOFR",
            foreign_convention="ESTR",
            start=date(2026, 1, 7),
        ),
    ]
    e_id, e_tenor = ("E1M", "1M") if turn_on_steps else ("E1", "1Y")
    insts = [
        InstrumentSpec("S1", "S", "OIS", tenor="1Y", rate=0.040),
        InstrumentSpec("S2", "S", "OIS", tenor="2Y", rate=0.038),
        InstrumentSpec("W1", "T", "SWAP", months=12, rate=0.045),
        InstrumentSpec("W2", "T", "SWAP", months=24, rate=0.041),
        InstrumentSpec(e_id, "E", "OIS", tenor=e_tenor, rate=0.020),
        InstrumentSpec("E2", "E", "OIS", tenor="2Y", rate=0.022),
        InstrumentSpec("X1", "X", "XCCY", months=12, spread=0.0010),
        InstrumentSpec("X2", "X", "XCCY", months=24, spread=0.0013),
    ]
    if turn_on_steps:  # 1M ends before the turn, so base and turn are told apart
        insts.insert(6, InstrumentSpec("E6", "E", "OIS", tenor="6M", rate=0.021, turn=True))
    return specs, insts


def test_start_is_flat_at_the_first_quote_steps_at_it_and_turns_at_one() -> None:
    specs, insts = _four_curves()
    blocks = joint._blocks(AS_OF, specs, insts)
    assert [b.offset for b in blocks] == [0, 2, 4, 7]
    x = [9.0] * 9
    joint._start(AS_OF, blocks, x)
    s, t = blocks[0].pillars, blocks[1].pillars
    # flat continuously compounded curves at the first quote, ln D = -r t
    assert x[0:2] == [-0.040 * (d - AS_OF).days / 365 for d in s]
    assert x[2:4] == [-0.045 * (d - AS_OF).days / 365 for d in t]
    # the step curve: base and step at the first quote, turn log-factor 0
    assert x[4:7] == [0.020, 0.020, 0.0]
    # XCCY: ln of the foreign projection curve as started, a flat 2 % step curve
    e_curve = StepCurve(AS_OF, 0.020, [(STEP, 0.020)], ((TURN, 1.0),))
    assert x[7:9] == pytest.approx(
        [math.log(e_curve.discount(d)) for d in blocks[3].pillars], abs=1e-15
    )
    assert x[7] != x[8]


def test_start_only_touches_the_named_block() -> None:
    specs, insts = _four_curves()
    blocks = joint._blocks(AS_OF, specs, insts)
    x = [9.0] * 9
    joint._start(AS_OF, blocks, x, only=2)
    assert x == [9.0, 9.0, 9.0, 9.0, 0.020, 0.020, 0.0, 9.0, 9.0]
    y = [9.0] * 9
    joint._start(AS_OF, blocks, y, only=1)
    t = blocks[1].pillars
    assert y == [9.0, 9.0, *(-0.045 * (d - AS_OF).days / 365 for d in t), 9.0, 9.0, 9.0, 9.0, 9.0]


# --------------------------------------------------------------------------------------------
# the finite-difference columns, on hand-made blocks whose residual is a known function of x


def _block(name: str, g: Any, offset: int) -> Any:
    def model(cs: dict[str, Any]) -> float:
        return float(g(math.log(cs[name].discount(P1))))

    spec = InstrumentSpec(name.lower(), name, "OIS")
    inst = joint._Instrument(spec, model, 0.0, -1.0, [P1], P1)
    return joint._Block(CurveSpec(name, "OIS"), [inst], [P1], [f"{name}:pillar"], offset)


def _boom(u: float) -> float:
    raise RuntimeError("a later block is evaluated")


def test_central_difference_reads_only_blocks_up_to_k() -> None:
    blocks = [_block("A", lambda u: u * u * u, 0), _block("B", _boom, 1)]
    x = [0.5, 0.0]
    col = joint._central(AS_OF, blocks, x, 0, 0, 1e-3)
    # (u+h)^3 - (u-h)^3 = 6 u^2 h + 2 h^3, over 2h: 3 u^2 + h^2
    assert col == [pytest.approx(3 * 0.25 + 1e-6, rel=1e-9)]
    assert x == [0.5, 0.0]
    adaptive = joint._column(AS_OF, blocks, x, 0, 0, True)
    assert adaptive == [pytest.approx(0.75, rel=1e-12)]
    assert x == [0.5, 0.0]


def test_column_newton_uses_one_central_difference_at_h() -> None:
    # g = u^3: the central difference at h is 3 u^2 + h^2 exactly; Richardson removes the h^2
    blocks = [_block("A", lambda u: u * u * u, 0)]
    x = [0.0]
    plain = joint._column(AS_OF, blocks, x, 0, 0, False)
    assert plain == [pytest.approx(joint._H**2, rel=1e-6)]
    assert joint._column(AS_OF, blocks, x, 0, 0, True) == [pytest.approx(0.0, abs=1e-14)]


def test_column_richardson_shrinks_until_two_estimates_agree() -> None:
    # g = exp(a u) at u = 0: g' = a. With a = 600 the relative error of the first Richardson
    # estimate, (a h)^4 / 480 ~ 3e-8 at h = 1e-4, is above the 1e-9 asked here, so the stencil must
    # shrink; the converged estimate is within 1e-9 of the derivative.
    for a in (600.0, 450.0, -500.0):
        blocks = [_block("A", lambda u, a=a: math.exp(a * u), 0)]
        got = joint._column(AS_OF, blocks, [0.0], 0, 0, True)[0]
        assert got == pytest.approx(a, rel=1e-9)
    # a smooth, slowly varying residual agrees at once and keeps the Richardson value at 1e-4,
    # which is exact for a polynomial of degree four or less
    quartic = [_block("A", lambda u: u**4 - 2 * u**3 + u, 0)]
    got = joint._column(AS_OF, quartic, [0.25], 0, 0, True)[0]
    assert got == pytest.approx(4 * 0.25**3 - 6 * 0.25**2 + 1, rel=1e-12)


# --------------------------------------------------------------------------------------------
# full solves that reach the branches a single-curve solve does not


def _reprice_all(specs: list[CurveSpec], insts: list[InstrumentSpec], r: Any) -> None:
    out = joint.outputs(AS_OF, r)
    built: dict[str, Any] = {}
    turns = {(t["curve"], t["date"]): t["factor"] for t in out["turn_factors"]}
    for c, oc in zip(specs, out["curves"], strict=True):
        jumps = tuple((d, turns[(c.name, d.isoformat())]) for d in c.turns)
        if c.type == "OIS_STEPS":
            built[c.name] = StepCurve(
                AS_OF,
                oc["base_rate"],
                list(zip(c.step_dates, oc["step_rates"], strict=True)),
                jumps,
            )
        else:
            built[c.name] = curves.Curve(
                CurveData(
                    AS_OF,
                    c.interpolation,
                    tuple(date.fromisoformat(p["date"]) for p in oc["pillars"]),
                    tuple(p["discount_factor"] for p in oc["pillars"]),
                    jumps,
                    c.tension,
                    c.step_end,
                )
            )
    by = {c.name: c for c in specs}
    for i in insts:
        c = by[i.curve]
        if i.type == "OIS":
            ps = ois.periods(c.convention, AS_OF, i.tenor)
            assert ois.par_rate(c.convention, ps, built[c.name]) == pytest.approx(i.rate, abs=1e-12)
        elif i.type == "XCCY":
            assert c.start is not None
            ends = xccy.schedule((c.domestic_convention, c.foreign_convention), c.start, i.months)
            pv = xccy.leg(1.0, c.start, ends, built[c.foreign_projection], built[c.name], i.spread)
            assert pv == pytest.approx(0.0, abs=1e-12)  # a par basis swap: the foreign leg is 0


def test_four_curve_solve_reprices_every_quote_and_zeroes_cross_turns() -> None:
    specs, insts = _four_curves()
    r = joint.joint_solve(AS_OF, specs, insts)
    _reprice_all(specs, insts, r)
    out = joint.outputs(AS_OF, r)
    x_c = out["curves"][3]
    ends = [xccy.schedule(("SOFR", "ESTR"), date(2026, 1, 7), m)[-1] for m in (12, 24)]
    assert [p["date"] for p in x_c["pillars"]] == [d.isoformat() for d in ends]
    # the E turn cannot move the S and T quotes: those rows sit in earlier blocks
    ids = r.quote_ids
    sens = dict(zip(ids, r.turn_sensitivity[0], strict=True))
    for q in ("S1", "S2", "W1", "W2"):
        assert sens[q] == 0.0
    assert sens["E6"] != 0.0 and sens["E2"] != 0.0
    assert sens["E1M"] == 0.0  # ends before the turn: ruling F-26


@pytest.mark.parametrize("qid", ["S1", "S2", "E1", "W2"])
def test_four_curve_jacobian_columns_match_bump_and_resolve(qid: str) -> None:
    # blocks S, E, T, X: an S quote leaves E unmoved (an all-zero right-hand side, skipped) and
    # then moves T, whose discount curve is S
    specs, insts = _four_curves(turn_on_steps=False)
    specs = [specs[0], specs[2], specs[1], specs[3]]
    r = joint.joint_solve(AS_OF, specs, insts)
    h = 1e-6

    def bumped(sign: float) -> list[float]:
        moved = [
            InstrumentSpec(
                i.id,
                i.curve,
                i.type,
                tenor=i.tenor,
                months=i.months,
                rate=i.rate + (sign * h if i.id == qid else 0.0),
                spread=i.spread,
            )
            for i in insts
        ]
        return joint.joint_solve(AS_OF, specs, moved).x

    up, down = bumped(1.0), bumped(-1.0)
    col = r.quote_ids.index(qid)
    for i in range(len(r.x)):
        assert r.jacobian[i][col] == pytest.approx((up[i] - down[i]) / (2 * h), rel=1e-4, abs=1e-7)
    # a later block that a quote moves is solved; one it cannot move stays an exact zero
    if qid in ("S1", "S2"):
        assert all(r.jacobian[i][col] == 0.0 for i in (2, 3))
        assert r.jacobian[5][col] != 0.0  # the 2Y swap discounts on S out to 2Y
    if qid == "S1":
        assert r.jacobian[4][col] != 0.0  # so does the 1Y swap; S2 cannot move it
    if qid == "E1":
        assert all(r.jacobian[i][col] == 0.0 for i in (0, 1, 4, 5))


def test_xccy_may_start_on_the_curve_date() -> None:
    specs, insts = _four_curves(turn_on_steps=False)
    specs[3] = CurveSpec(
        "X",
        "XCCY",
        domestic="S",
        foreign_projection="E",
        domestic_convention="SOFR",
        foreign_convention="ESTR",
        start=AS_OF,
    )
    r = joint.joint_solve(AS_OF, specs, insts)
    _reprice_all(specs, insts, r)


@pytest.mark.parametrize(
    ("interpolation", "tension", "step_end"),
    [("TENSION_SPLINE", 5.0, None), ("HYBRID", None, date(2027, 1, 11))],
)
def test_pillar_curve_options_reach_the_curve(
    interpolation: str, tension: float | None, step_end: date | None
) -> None:
    specs = [
        CurveSpec(
            "S",
            "OIS",
            convention="SOFR",
            interpolation=interpolation,
            tension=tension,
            step_end=step_end,
        )
    ]
    insts = [
        InstrumentSpec("S6", "S", "OIS", tenor="6M", rate=0.041),
        InstrumentSpec("S1", "S", "OIS", tenor="1Y", rate=0.040),
        InstrumentSpec("S2", "S", "OIS", tenor="2Y", rate=0.038),
        InstrumentSpec("S5", "S", "OIS", tenor="5Y", rate=0.036),
    ]
    if step_end is not None:
        assert step_end == ois.periods("SOFR", AS_OF, "1Y")[-1].payment
    r = joint.joint_solve(AS_OF, specs, insts)
    _reprice_all(specs, insts, r)


def test_pillar_curve_options_are_checked() -> None:
    insts = [InstrumentSpec("S1", "S", "OIS", tenor="1Y", rate=0.040)]
    no_tension = [CurveSpec("S", "OIS", convention="SOFR", interpolation="TENSION_SPLINE")]
    _err(lambda: joint.joint_solve(AS_OF, no_tension, insts), "E_INPUT", "tension")
    bad_end = [CurveSpec("S", "OIS", convention="SOFR", interpolation="HYBRID", step_end=P1)]
    _err(lambda: joint.joint_solve(AS_OF, bad_end, insts), "E_INPUT", "step_end")


def test_pillar_curve_turn_moves_a_later_future_and_is_not_zeroed() -> None:
    # F-26 zeroing applies to OIS_STEPS curves only. On a pillar curve the unknowns are ln D at the
    # pillars, so the turn factor changes the log-linear slope of the section it sits in: a
    # future whose dates are all after the turn still moves (SPEC_QUESTIONS F-Q5).
    specs = [CurveSpec("S", "OIS", convention="SOFR", turns=(TURN,))]
    insts = [
        InstrumentSpec("S1M", "S", "OIS", tenor="1M", rate=0.043),
        InstrumentSpec("FUT", "S", "FUTURE", start=FUT_S, end=FUT_E, price=95.9, turn=True),
        InstrumentSpec("S1", "S", "OIS", tenor="1Y", rate=0.040),
        InstrumentSpec("S2", "S", "OIS", tenor="2Y", rate=0.038),
    ]
    r = joint.joint_solve(AS_OF, specs, insts)
    assert TURN < FUT_S
    assert r.turn_sensitivity[0][1] != 0.0
    _reprice_all(specs, insts, r)


def test_two_turns_on_a_step_curve_have_their_own_columns() -> None:
    t1, t2 = date(2026, 3, 31), date(2026, 12, 31)
    specs = [CurveSpec("E", "OIS_STEPS", convention="ESTR", step_dates=(STEP,), turns=(t1, t2))]
    insts = [
        InstrumentSpec("E1M", "E", "OIS", tenor="1M", rate=0.020),
        InstrumentSpec("E6M", "E", "OIS", tenor="6M", rate=0.021, turn=True),
        InstrumentSpec("E2Y", "E", "OIS", tenor="2Y", rate=0.023, turn=True),
        InstrumentSpec("E1Y", "E", "OIS", tenor="1Y", rate=0.022),
    ]
    r = joint.joint_solve(AS_OF, specs, insts)
    _reprice_all(specs, insts, r)
    out = joint.outputs(AS_OF, r)
    c = out["curves"][0]
    f1, f2 = (t["factor"] for t in out["turn_factors"])

    def par(tenor: str, l1: float, l2: float) -> float:
        sc = StepCurve(
            AS_OF,
            c["base_rate"],
            [(STEP, c["step_rates"][0])],
            ((t1, math.exp(l1)), (t2, math.exp(l2))),
        )
        return ois.par_rate("ESTR", ois.periods("ESTR", AS_OF, tenor), sc)

    h, l1, l2 = 1e-6, math.log(f1), math.log(f2)
    for q, tenor in enumerate(("1M", "6M", "2Y", "1Y")):
        d1 = (par(tenor, l1 + h, l2) - par(tenor, l1 - h, l2)) / (2 * h)
        d2 = (par(tenor, l1, l2 + h) - par(tenor, l1, l2 - h)) / (2 * h)
        assert r.turn_sensitivity[0][q] == pytest.approx(d1, rel=1e-5, abs=1e-9)
        assert r.turn_sensitivity[1][q] == pytest.approx(d2, rel=1e-5, abs=1e-9)
    assert r.turn_sensitivity[0][0] == 0.0  # 1M ends before the first turn
    assert r.turn_sensitivity[1][1] == 0.0  # 6M ends before the second turn
    assert r.turn_sensitivity[1][2] != 0.0


# --------------------------------------------------------------------------------------------
# funding curve


DISC = CurveData(AS_OF, "LOG_LINEAR_DF", (date(2027, 1, 5), date(2031, 1, 6)), (0.96, 0.84))


def test_funding_curve_three_quotes_extrapolate_with_the_last_spread() -> None:
    e1, e2, e3 = date(2026, 10, 5), date(2028, 1, 5), date(2030, 1, 7)
    quotes = [(e1, 0.05), (e2, -0.002), (e3, 0.055)]
    curve = curves.build(DISC)
    logs = [
        math.log(curve.discount(e)) + math.log(1 + r * (e - AS_OF).days / 360) for e, r in quotes
    ]
    ts = [(e - AS_OF).days / 365 for e, _ in quotes]
    spreads, pillars, dfs = joint.funding_curve(DISC, quotes, [date(2032, 1, 5)])
    assert ts[0] != 1.0
    assert spreads == pytest.approx(
        [
            logs[0] / ts[0],
            (logs[1] - logs[0]) / (ts[1] - ts[0]),
            (logs[2] - logs[1]) / (ts[2] - ts[1]),
        ],
        rel=1e-13,
    )
    assert spreads[1] != spreads[2]
    for (e, r), (d, p) in zip(quotes, pillars, strict=True):
        assert d == e and p == pytest.approx(1 / (1 + r * (e - AS_OF).days / 360), rel=1e-13)
    tf = (date(2032, 1, 5) - AS_OF).days / 365
    expect = curve.discount(date(2032, 1, 5)) * math.exp(-(logs[2] + spreads[2] * (tf - ts[2])))
    assert dfs[0] == pytest.approx(expect, rel=1e-13)


def test_funding_curve_growth_of_exactly_zero_is_refused() -> None:
    e = AS_OF + timedelta(days=360)  # alpha = 1, so 1 + (-1) * 1 = 0 exactly
    msg = _err(lambda: joint.funding_curve(DISC, [(e, -1.0)], []), "E_DOMAIN", "quotes")
    assert msg == "1 + rate * alpha must be positive"


# --------------------------------------------------------------------------------------------
# added after the first recheck: the rest of the reachable branches


def test_check_conditioned_refuses_an_empty_matrix() -> None:
    # numpy.linalg.cond raises LinAlgError on an empty array; the check maps it to rcond 0
    _err(lambda: joint._check_conditioned([]), "E_NO_CONVERGENCE", "instruments")


def test_newton_backtracks_out_of_a_region_where_the_model_fails() -> None:
    # r(u) = atan(u) from u = 2: the full Newton step, 2 - atan(2) (1 + 4) = -3.54, lands where the
    # model raises OverflowError (u < -3 here); the failure counts as an infinite residual and the
    # step is halved to u = -0.77, |atan| = 0.66 < atan(2), and Newton goes on to the root u = 0.
    def g(u: float) -> float:
        if u < -3:
            raise OverflowError("outside the model")
        return math.atan(u)

    blocks = [_block("A", g, 0)]
    x = [2.0]
    joint._solve_block(AS_OF, blocks, x, 0)
    assert abs(x[0]) < 1e-12


def test_step_curve_turn_zeroes_a_later_future_exactly() -> None:
    # ruling F-26: a future whose dates are both after the turn does not move with it (both
    # discount factors carry the same factor). The finite difference leaves rounding noise of
    # about 1e-11 here; the ruling sets the entry to an exact zero. The OIS block in front makes
    # the zeroing loop pass a pillar curve before it reaches the step curve.
    turn = AS_OF + timedelta(days=37)
    s = turn + timedelta(days=5)
    specs = [
        CurveSpec("S", "OIS", convention="SOFR"),
        CurveSpec("E", "OIS_STEPS", convention="ESTR", step_dates=(STEP,), turns=(turn,)),
    ]
    insts = [
        InstrumentSpec("S1", "S", "OIS", tenor="1Y", rate=0.04),
        InstrumentSpec("E1M", "E", "OIS", tenor="1M", rate=0.02),
        InstrumentSpec("E2Y", "E", "OIS", tenor="2Y", rate=0.023, turn=True),
        InstrumentSpec("F", "E", "FUTURE", start=s, end=s + timedelta(days=91), price=97.6),
    ]
    r = joint.joint_solve(AS_OF, specs, insts)
    assert r.turn_sensitivity[0] == [0.0, 0.0, r.turn_sensitivity[0][2], 0.0]
    assert r.turn_sensitivity[0][2] != 0.0
    _reprice_all(specs, insts, r)


def test_step_curve_future_starting_on_the_turn_day_moves_with_it() -> None:
    # A jump on day d multiplies D(t) for t > d only, so a future from the turn day itself has
    # D(start) without the factor and D(end) with it: it spans the turn and is not zeroed.
    end = TURN + timedelta(days=91)
    specs = [CurveSpec("E", "OIS_STEPS", convention="ESTR", step_dates=(STEP,), turns=(TURN,))]
    insts = [
        InstrumentSpec("E1M", "E", "OIS", tenor="1M", rate=0.020),
        InstrumentSpec("F", "E", "FUTURE", start=TURN, end=end, price=97.7, turn=True),
        InstrumentSpec("E1Y", "E", "OIS", tenor="1Y", rate=0.022),
    ]
    r = joint.joint_solve(AS_OF, specs, insts)
    out = joint.outputs(AS_OF, r)
    c = out["curves"][0]
    lf = math.log(out["turn_factors"][0]["factor"])
    alpha = (end - TURN).days / 360

    def fwd(lj: float) -> float:
        sc = StepCurve(AS_OF, c["base_rate"], [(STEP, c["step_rates"][0])], ((TURN, math.exp(lj)),))
        return (sc.discount(TURN) / sc.discount(end) - 1) / alpha

    h = 1e-6
    fd = (fwd(lf + h) - fwd(lf - h)) / (2 * h)
    assert r.turn_sensitivity[0][1] == pytest.approx(fd, rel=1e-6)
    assert abs(fd) > 1.0


def test_two_turn_step_curve_jacobian_matches_bump_and_resolve() -> None:
    t1, t2 = date(2026, 3, 31), date(2026, 12, 31)
    specs = [CurveSpec("E", "OIS_STEPS", convention="ESTR", step_dates=(STEP,), turns=(t1, t2))]

    rates = {"E1M": 0.020, "E6M": 0.021, "E2Y": 0.023, "E1Y": 0.022}
    tenors = {"E1M": "1M", "E6M": "6M", "E2Y": "2Y", "E1Y": "1Y"}

    def insts(bump: str, h: float) -> list[InstrumentSpec]:
        return [
            InstrumentSpec(
                q,
                "E",
                "OIS",
                tenor=tenors[q],
                rate=rates[q] + (h if q == bump else 0.0),
                turn=q in ("E6M", "E2Y"),
            )
            for q in rates
        ]

    r = joint.joint_solve(AS_OF, specs, insts("", 0.0))
    h = 1e-6
    for col, q in enumerate(rates):
        up = joint.joint_solve(AS_OF, specs, insts(q, h)).x
        down = joint.joint_solve(AS_OF, specs, insts(q, -h)).x
        for i in range(4):
            fd = (up[i] - down[i]) / (2 * h)
            assert r.jacobian[i][col] == pytest.approx(fd, rel=1e-5, abs=1e-8)


def test_start_resets_every_turn_of_a_two_turn_curve() -> None:
    t1, t2 = date(2026, 3, 31), date(2026, 12, 31)
    specs = [CurveSpec("E", "OIS_STEPS", convention="ESTR", step_dates=(STEP,), turns=(t1, t2))]
    insts = [
        InstrumentSpec("E1M", "E", "OIS", tenor="1M", rate=0.020),
        InstrumentSpec("E6M", "E", "OIS", tenor="6M", rate=0.021, turn=True),
        InstrumentSpec("E2Y", "E", "OIS", tenor="2Y", rate=0.023, turn=True),
        InstrumentSpec("E1Y", "E", "OIS", tenor="1Y", rate=0.022),
    ]
    blocks = joint._blocks(AS_OF, specs, insts)
    x = [9.0] * 4
    joint._start(AS_OF, blocks, x)
    assert x == [0.020, 0.020, 0.0, 0.0]
