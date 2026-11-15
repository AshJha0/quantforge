"""Unit tests for quantforge_core.joint (02-curves/joint-solve-and-funding.md, rulings F-24 to
F-27): the structure checks of the joint solve, the turn merge and the funding curve. The funding
curve reprices each quote by construction, P_f(e) = 1 / (1 + r alpha), which is the independent
check used below."""

import math
from datetime import date

import pytest

from quantforge_core import curves, joint
from quantforge_core.curves import CurveData
from quantforge_core.errors import QfError
from quantforge_core.joint import CurveSpec, InstrumentSpec

AS_OF = date(2026, 1, 5)


def _err(fn, code: str, field: str | None) -> None:
    with pytest.raises(QfError) as e:
        fn()
    assert e.value.code == code and e.value.field == field


def _ok(specs: list[CurveSpec], insts: list[InstrumentSpec]) -> None:
    joint._check_structure(AS_OF, specs, insts)


def test_check_structure_curves() -> None:
    ois_c = CurveSpec("OIS", "OIS")
    _err(lambda: _ok([CurveSpec("X", "LIBOR")], []), "E_SCHEMA", "curves")
    _err(lambda: _ok([CurveSpec("P", "PROJECTION", discount="OIS")], []), "E_INPUT", "curves")
    proj = CurveSpec("P", "PROJECTION", discount="OIS")
    _ok([ois_c, proj], [])
    _err(
        lambda: _ok([ois_c, proj, CurveSpec("Q", "PROJECTION", discount="P")], []),
        "E_INPUT",
        "curves",
    )
    _ok(
        [
            CurveSpec("S", "OIS_STEPS", step_dates=(date(2026, 3, 1),)),
            CurveSpec("P", "PROJECTION", discount="S"),
        ],
        [InstrumentSpec("a", "S", "OIS"), InstrumentSpec("b", "S", "FUTURE")],
    )
    x_ok = CurveSpec("X", "XCCY", domestic="OIS", foreign_projection="F")
    _err(lambda: _ok([ois_c, x_ok], []), "E_INPUT", "curves")
    _ok([ois_c, CurveSpec("F", "OIS"), x_ok], [])
    _err(lambda: _ok([ois_c, CurveSpec("OIS", "OIS")], []), "E_INPUT", "curves")


def test_check_structure_instruments() -> None:
    ois_c = CurveSpec("OIS", "OIS")
    _err(
        lambda: _ok(
            [ois_c], [InstrumentSpec("a", "OIS", "OIS"), InstrumentSpec("a", "OIS", "OIS")]
        ),
        "E_INPUT",
        "instruments",
    )
    _err(lambda: _ok([ois_c], [InstrumentSpec("a", "NOPE", "OIS")]), "E_INPUT", "instruments")
    _err(lambda: _ok([ois_c], [InstrumentSpec("a", "OIS", "SWAP")]), "E_INPUT", "instruments")
    _ok([ois_c], [InstrumentSpec("a", "OIS", "OIS"), InstrumentSpec("b", "OIS", "FUTURE")])
    p = CurveSpec("P", "PROJECTION", discount="OIS")
    _ok(
        [ois_c, p],
        [InstrumentSpec(i, "P", t) for i, t in (("d", "DEPOSIT"), ("f", "FRA"), ("s", "SWAP"))],
    )
    _err(lambda: _ok([ois_c, p], [InstrumentSpec("a", "P", "OIS")]), "E_INPUT", "instruments")


def test_check_structure_dates_and_counts() -> None:
    d1, d2 = date(2026, 3, 1), date(2026, 6, 1)
    _err(
        lambda: _ok(
            [CurveSpec("O", "OIS", turns=(AS_OF,))], [InstrumentSpec("a", "O", "OIS", turn=True)]
        ),
        "E_INPUT",
        "turns",
    )
    _err(lambda: _ok([CurveSpec("O", "OIS", turns=(d2, d1))], []), "E_INPUT", "turns")
    _err(lambda: _ok([CurveSpec("O", "OIS", step_dates=(d1, d1))], []), "E_INPUT", "step_dates")
    _err(
        lambda: _ok([CurveSpec("O", "OIS", turns=(d1,))], [InstrumentSpec("a", "O", "OIS")]),
        "E_INPUT",
        "instruments",
    )
    _err(
        lambda: _ok([CurveSpec("O", "OIS")], [InstrumentSpec("a", "O", "OIS", turn=True)]),
        "E_INPUT",
        "instruments",
    )
    _ok([CurveSpec("O", "OIS", turns=(d1,))], [InstrumentSpec("a", "O", "OIS", turn=True)])
    steps = CurveSpec("S", "OIS_STEPS", step_dates=(d1,), turns=(d2,))
    three = [
        InstrumentSpec("a", "S", "OIS"),
        InstrumentSpec("b", "S", "OIS"),
        InstrumentSpec("c", "S", "OIS", turn=True),
    ]
    _ok([steps], three)
    _err(lambda: _ok([steps], three[:1] + three[2:]), "E_INPUT", "instruments")
    _err(lambda: _ok([steps], [*three, InstrumentSpec("d", "S", "OIS")]), "E_INPUT", "instruments")
    _err(
        lambda: _ok([CurveSpec("S", "OIS_STEPS")], [InstrumentSpec("a", "S", "OIS")]),
        "E_INPUT",
        "step_dates",
    )


def test_jumps_merge() -> None:
    d1, d2, d3 = date(2026, 3, 1), date(2026, 6, 1), date(2026, 12, 31)
    c = CurveSpec("O", "OIS", jumps=((d2, 0.99),), turns=(d1, d3))
    out = joint._jumps(c, [math.log(0.98), math.log(1.01)])
    assert [d for d, _ in out] == [d1, d2, d3]
    assert [f for _, f in out] == pytest.approx([0.98, 0.99, 1.01])
    assert joint._jumps(CurveSpec("O", "OIS"), []) == ()


DISC = CurveData(AS_OF, "LOG_LINEAR_DF", (date(2027, 1, 5), date(2031, 1, 6)), (0.96, 0.84))


def test_funding_curve_reprices_quotes() -> None:
    e1, e2 = date(2027, 1, 5), date(2029, 1, 5)
    quotes = [(e1, 0.05), (e2, 0.055)]
    a1, a2 = (e1 - AS_OF).days / 360, (e2 - AS_OF).days / 360
    t1, t2 = (e1 - AS_OF).days / 365, (e2 - AS_OF).days / 365
    mid, far = date(2028, 1, 5), date(2032, 1, 5)
    spreads, pillars, dfs = joint.funding_curve(DISC, quotes, [AS_OF, e1, mid, e2, far])
    curve = curves.build(DISC)
    l1 = math.log(curve.discount(e1)) + math.log(1 + 0.05 * a1)
    l2 = math.log(curve.discount(e2)) + math.log(1 + 0.055 * a2)
    assert spreads == pytest.approx([l1 / t1, (l2 - l1) / (t2 - t1)])
    assert [d for d, _ in pillars] == [e1, e2]
    assert [p for _, p in pillars] == pytest.approx([1 / (1 + 0.05 * a1), 1 / (1 + 0.055 * a2)])
    assert dfs[0] == pytest.approx(1.0)
    assert dfs[1] == pytest.approx(1 / (1 + 0.05 * a1))
    tm = (mid - AS_OF).days / 365
    assert dfs[2] == pytest.approx(curve.discount(mid) * math.exp(-(l1 + spreads[1] * (tm - t1))))
    assert dfs[3] == pytest.approx(1 / (1 + 0.055 * a2))
    tf = (far - AS_OF).days / 365
    assert dfs[4] == pytest.approx(curve.discount(far) * math.exp(-(l2 + spreads[1] * (tf - t2))))
    early = date(2026, 7, 5)
    te = (early - AS_OF).days / 365
    one = joint.funding_curve(DISC, quotes[:1], [early])[2][0]
    assert one == pytest.approx(curve.discount(early) * math.exp(-spreads[0] * te))


def test_funding_curve_errors() -> None:
    e1 = date(2027, 1, 5)
    _err(lambda: joint.funding_curve(DISC, [], []), "E_INPUT", "quotes")
    _err(lambda: joint.funding_curve(DISC, [(AS_OF, 0.05)], []), "E_INPUT", "quotes")
    _err(lambda: joint.funding_curve(DISC, [(e1, 0.05), (e1, 0.05)], []), "E_INPUT", "quotes")
    _err(lambda: joint.funding_curve(DISC, [(e1, -1.0)], []), "E_DOMAIN", "quotes")
    _err(lambda: joint.funding_curve(DISC, [(e1, -2.0)], []), "E_DOMAIN", "quotes")
    _err(
        lambda: joint.funding_curve(DISC, [(e1, 0.05)], [date(2025, 1, 1)]),
        "E_OUT_OF_RANGE",
        "dates",
    )
