"""Unit tests for quantforge_core.joint.joint_solve and outputs (02-curves/joint-solve-and-funding.md,
rulings F-24 to F-27).

Independent checks: the solved curves are rebuilt from `outputs` with curves.Curve and
steps.StepCurve and must reprice every OIS quote through ois.par_rate and the future by hand
(sigma = 0, so the futures rate is (100 - price) / 100 with no convexity); the Jacobian is checked
column by column against re-solving with the quote bumped both ways; the turn sensitivity against
a central difference of the par rate in the turn log-factor on the rebuilt curve."""

import math
from datetime import date
from typing import Any

import pytest

from quantforge_core import curves, joint, ois
from quantforge_core.curves import CurveData
from quantforge_core.errors import QfError
from quantforge_core.joint import CurveSpec, InstrumentSpec
from quantforge_core.steps import StepCurve

AS_OF = date(2026, 1, 5)
TURN = date(2026, 3, 31)
STEP = date(2026, 4, 1)
FUT_S, FUT_E = date(2026, 6, 17), date(2026, 9, 16)


def _specs() -> list[CurveSpec]:
    return [
        CurveSpec("SOFR", "OIS", convention="SOFR", interpolation="LOG_LINEAR_DF", turns=(TURN,)),
        CurveSpec("TERM", "PROJECTION", index="USD-TERM-3M", discount="SOFR"),
        CurveSpec("ESTR", "OIS_STEPS", convention="ESTR", step_dates=(STEP,)),
    ]


def _insts(bump: str = "", h: float = 0.0) -> list[InstrumentSpec]:
    def q(i: str, v: float) -> float:
        return v + (h if i == bump else 0.0)

    return [
        InstrumentSpec("S1M", "SOFR", "OIS", tenor="1M", rate=q("S1M", 0.043)),
        InstrumentSpec("S6M", "SOFR", "OIS", tenor="6M", rate=q("S6M", 0.042), turn=True),
        InstrumentSpec("S1Y", "SOFR", "OIS", tenor="1Y", rate=q("S1Y", 0.040)),
        InstrumentSpec("S2Y", "SOFR", "OIS", tenor="2Y", rate=q("S2Y", 0.038)),
        InstrumentSpec("D3", "TERM", "DEPOSIT", months=3, rate=q("D3", 0.045)),
        InstrumentSpec("F3", "TERM", "FRA", start_months=3, rate=q("F3", 0.044)),
        InstrumentSpec("W2", "TERM", "SWAP", months=24, rate=q("W2", 0.040)),
        InstrumentSpec("E1Y", "ESTR", "OIS", tenor="1Y", rate=q("E1Y", 0.02)),
        InstrumentSpec("FUT", "ESTR", "FUTURE", start=FUT_S, end=FUT_E, price=q("FUT", 97.9)),
    ]


@pytest.fixture(scope="module")
def solved() -> Any:
    r = joint.joint_solve(AS_OF, _specs(), _insts())
    return r, joint.outputs(AS_OF, r)


def _sofr(out: dict[str, Any], turn_log: float | None = None) -> curves.Curve:
    c = out["curves"][0]
    factor = out["turn_factors"][0]["factor"] if turn_log is None else math.exp(turn_log)
    data = CurveData(
        AS_OF,
        "LOG_LINEAR_DF",
        tuple(date.fromisoformat(p["date"]) for p in c["pillars"]),
        tuple(p["discount_factor"] for p in c["pillars"]),
        ((TURN, factor),),
    )
    return curves.Curve(data)


def test_solved_curves_reprice_every_quote(solved: Any) -> None:
    r, out = solved
    assert r.max_error <= joint.TOLERANCE
    sofr = _sofr(out)
    for tenor, rate in (("1M", 0.043), ("6M", 0.042), ("1Y", 0.040), ("2Y", 0.038)):
        ps = ois.periods("SOFR", AS_OF, tenor)
        assert ois.par_rate("SOFR", ps, sofr) == pytest.approx(rate, abs=1e-13)
    e = out["curves"][2]
    assert e["name"] == "ESTR" and len(e["step_rates"]) == 1
    estr = StepCurve(AS_OF, e["base_rate"], [(STEP, e["step_rates"][0])], ())
    assert ois.par_rate("ESTR", ois.periods("ESTR", AS_OF, "1Y"), estr) == pytest.approx(
        0.02, abs=1e-13
    )
    # the future: simple ACT/360 forward over [s, e] equals (100 - 97.9) / 100 at sigma = 0
    fwd = (estr.discount(FUT_S) / estr.discount(FUT_E) - 1) / ((FUT_E - FUT_S).days / 360)
    assert fwd == pytest.approx(0.021, abs=1e-13)
    # pillars are the payment dates of the non-turn instruments, discount factors exp(x)
    pillars = [date.fromisoformat(p["date"]) for p in out["curves"][0]["pillars"]]
    assert pillars == [ois.periods("SOFR", AS_OF, t)[-1].payment for t in ("1M", "1Y", "2Y")]
    assert [p["discount_factor"] for p in out["curves"][0]["pillars"]] == [
        math.exp(v) for v in r.x[:3]
    ]
    assert out["turn_factors"] == [
        {"curve": "SOFR", "date": "2026-03-31", "factor": math.exp(r.x[3])}
    ]
    assert out["curves"][1]["name"] == "TERM" and len(out["curves"][1]["pillars"]) == 3


def test_outputs_labels_and_quotes(solved: Any) -> None:
    _, out = solved
    jac = out["jacobian"]
    assert jac["quotes"] == [i.id for i in _insts()]
    assert jac["unknowns"][:4] == [
        "SOFR:pillar:" + str(ois.periods("SOFR", AS_OF, "1M")[-1].payment),
        "SOFR:pillar:" + str(ois.periods("SOFR", AS_OF, "1Y")[-1].payment),
        "SOFR:pillar:" + str(ois.periods("SOFR", AS_OF, "2Y")[-1].payment),
        "SOFR:turn:2026-03-31",
    ]
    assert jac["unknowns"][7:] == ["ESTR:base", "ESTR:step:2026-04-01"]
    assert len(jac["matrix"]) == 9 and all(len(row) == 9 for row in jac["matrix"])


@pytest.mark.parametrize("qid", ["S1M", "S6M", "S2Y", "D3", "W2", "E1Y", "FUT"])
def test_jacobian_matches_bump_and_resolve(solved: Any, qid: str) -> None:
    r, _ = solved
    h = 1e-2 if qid == "FUT" else 1e-6
    up = joint.joint_solve(AS_OF, _specs(), _insts(qid, h)).x
    down = joint.joint_solve(AS_OF, _specs(), _insts(qid, -h)).x
    col = r.quote_ids.index(qid)
    for i in range(len(r.x)):
        fd = (up[i] - down[i]) / (2 * h)
        assert r.jacobian[i][col] == pytest.approx(fd, rel=1e-4, abs=1e-7)


def test_turn_sensitivity_matches_par_rate_differences(solved: Any) -> None:
    r, out = solved
    sens = r.turn_sensitivity
    assert len(sens) == 1 and len(sens[0]) == 9
    v, h = r.x[3], 1e-6
    for col, tenor in ((0, "1M"), (1, "6M"), (2, "1Y"), (3, "2Y")):
        ps = ois.periods("SOFR", AS_OF, tenor)
        fd = (
            ois.par_rate("SOFR", ps, _sofr(out, v + h))
            - ois.par_rate("SOFR", ps, _sofr(out, v - h))
        ) / (2 * h)
        assert sens[0][col] == pytest.approx(fd, rel=1e-5, abs=1e-9)
    assert sens[0][0] == 0.0  # the 1M swap ends before the turn
    assert sens[0][7] == 0.0 and sens[0][8] == 0.0  # the ESTR curve has no SOFR turn in it


def test_step_curve_turn_zeroes_instruments_that_do_not_span_it() -> None:
    # ruling F-26 on an OIS_STEPS curve: a turn moves only instruments whose dates straddle it
    specs = [CurveSpec("E", "OIS_STEPS", convention="ESTR", step_dates=(STEP,), turns=(TURN,))]
    insts = [
        InstrumentSpec("E1M", "E", "OIS", tenor="1M", rate=0.020),
        InstrumentSpec("E6M", "E", "OIS", tenor="6M", rate=0.021, turn=True),
        InstrumentSpec("FUT", "E", "FUTURE", start=FUT_S, end=FUT_E, price=97.8),
    ]
    r = joint.joint_solve(AS_OF, specs, insts)
    assert r.turn_sensitivity[0][0] == 0.0 and r.turn_sensitivity[0][2] == 0.0
    assert r.turn_sensitivity[0][1] != 0.0
    out = joint.outputs(AS_OF, r)
    c = out["curves"][0]
    jumps = ((TURN, out["turn_factors"][0]["factor"]),)
    sc = StepCurve(AS_OF, c["base_rate"], [(STEP, c["step_rates"][0])], jumps)
    for tenor, rate in (("1M", 0.020), ("6M", 0.021)):
        assert ois.par_rate("ESTR", ois.periods("ESTR", AS_OF, tenor), sc) == pytest.approx(
            rate, abs=1e-13
        )
    fwd = (sc.discount(FUT_S) / sc.discount(FUT_E) - 1) / ((FUT_E - FUT_S).days / 360)
    assert fwd == pytest.approx(0.022, abs=1e-13)


def _err(fn: Any, code: str, field: str | None) -> None:
    with pytest.raises(QfError) as e:
        fn()
    assert e.value.code == code and e.value.field == field
    assert isinstance(e.value.message, str) and str(e.value) == e.value.message
    assert "XX" not in e.value.message and e.value.message != e.value.message.upper()


def test_joint_solve_errors() -> None:
    ois_c = [CurveSpec("S", "OIS", convention="SOFR")]
    same = [
        InstrumentSpec("A", "S", "OIS", tenor="1Y", rate=0.04),
        InstrumentSpec("B", "S", "OIS", tenor="1Y", rate=0.041),
    ]
    _err(lambda: joint.joint_solve(AS_OF, ois_c, same), "E_INPUT", "instruments")
    back = [CurveSpec("E", "OIS_STEPS", convention="ESTR", step_dates=(STEP,))]
    bad_fut = [
        InstrumentSpec("E1Y", "E", "OIS", tenor="1Y", rate=0.02),
        InstrumentSpec("F", "E", "FUTURE", start=FUT_E, end=FUT_S, price=98.0),
    ]
    _err(lambda: joint.joint_solve(AS_OF, back, bad_fut), "E_INPUT", "instruments")
    xc = [
        CurveSpec("S", "OIS", convention="SOFR"),
        CurveSpec("E", "OIS", convention="ESTR"),
        CurveSpec(
            "X",
            "XCCY",
            domestic="S",
            foreign_projection="E",
            domestic_convention="SOFR",
            foreign_convention="ESTR",
            start=date(2026, 1, 2),
        ),
    ]
    xi = [
        InstrumentSpec("S1", "S", "OIS", tenor="1Y", rate=0.04),
        InstrumentSpec("E1", "E", "OIS", tenor="1Y", rate=0.02),
        InstrumentSpec("X1", "X", "XCCY", months=12, spread=0.001),
    ]
    _err(lambda: joint.joint_solve(AS_OF, xc, xi), "E_OUT_OF_RANGE", "start")


def test_xccy_block_jacobian_and_spread_slope() -> None:
    def build(h: float) -> Any:
        specs = [
            CurveSpec("S", "OIS", convention="SOFR"),
            CurveSpec("E", "OIS", convention="ESTR"),
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
        insts = [
            InstrumentSpec("S1", "S", "OIS", tenor="1Y", rate=0.04),
            InstrumentSpec("S2", "S", "OIS", tenor="2Y", rate=0.038),
            InstrumentSpec("E1", "E", "OIS", tenor="1Y", rate=0.02),
            InstrumentSpec("E2", "E", "OIS", tenor="2Y", rate=0.021),
            InstrumentSpec("X1", "X", "XCCY", months=12, spread=0.001 + h),
            InstrumentSpec("X2", "X", "XCCY", months=24, spread=0.0012),
        ]
        return joint.joint_solve(AS_OF, specs, insts)

    r = build(0.0)
    assert r.max_error <= joint.TOLERANCE
    h = 1e-6
    up, down = build(h).x, build(-h).x
    col = r.quote_ids.index("X1")
    for i in range(len(r.x)):
        assert r.jacobian[i][col] == pytest.approx((up[i] - down[i]) / (2 * h), rel=1e-4, abs=1e-7)
    assert all(r.jacobian[i][col] == 0.0 for i in range(4))  # a spread cannot move S or E
