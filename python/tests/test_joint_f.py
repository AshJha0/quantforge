"""Stage F Q4 properties (joint-solve-and-funding.md): limit cases, structure, turns."""
import json
import math
from datetime import date
from pathlib import Path

import pytest

from quantforge_core import joint, ois
from quantforge_core.cli import ops_rates
from quantforge_core.cli.inputs import Inputs
from quantforge_core.curves import CurveData
from quantforge_core.ois import Quote

GOLDEN = Path(__file__).resolve().parents[2] / "datasets/golden/stage_f/joint_f.json"


def _case(n: int) -> dict:
    """1: the steps-with-turn system; 2: SOFR + term log-linear (found by description, since
    case ids move when spec adds cases)."""
    words = {1: "meeting steps", 2: "log-linear"}[n]
    cases = json.loads(GOLDEN.read_text())["cases"]
    return next(c["inputs"] for c in cases if words in c.get("description", ""))


def _solve(inputs: dict) -> dict:
    out, _ = ops_rates._joint_solve(Inputs(inputs))
    return out


def test_one_curve_equals_ois_bootstrap() -> None:
    inputs = _case(2)
    inputs["curves"] = inputs["curves"][:1]
    inputs["instruments"] = [x for x in inputs["instruments"] if x["curve"] == "USD-SOFR"]
    out = _solve(inputs)
    quotes = [Quote(x["tenor"], x["rate"]) for x in inputs["instruments"]]
    data, _ = ois.bootstrap("SOFR", date(2026, 11, 9), quotes, "LOG_LINEAR_DF")
    for p, v in zip(out["curves"][0]["pillars"], data.discount_factors, strict=True):
        assert abs(p["discount_factor"] - v) < 1e-14


def test_block_zeros_are_exact() -> None:
    out = _solve(_case(2))
    jac = out["jacobian"]
    for r, label in enumerate(jac["unknowns"]):
        for q, qid in enumerate(jac["quotes"]):
            if label.startswith("USD-SOFR:") and qid.startswith("T-"):
                assert jac["matrix"][r][q] == 0.0


def test_turn_sensitivity_zero_off_the_turn() -> None:
    out = _solve(_case(1))
    row = out["turn_sensitivity"][0]
    quotes = out["jacobian"]["quotes"]
    spans = {"SOFR-2M", "SR3-Z6"}
    for qid, v in zip(quotes, row, strict=True):
        assert (v != 0.0) == (qid in spans), qid


def test_turn_factor_one_at_no_turn_par_rate() -> None:
    inputs = _case(1)
    base = _solve(inputs)
    # Quote the turn instrument at the par rate of the curve solved with the turn removed.
    no_turn = json.loads(json.dumps(inputs))
    no_turn["curves"][0].pop("turns")
    turn_inst = next(x for x in no_turn["instruments"] if x.get("turn"))
    no_turn["instruments"] = [x for x in no_turn["instruments"] if not x.get("turn")]
    flat = _solve(no_turn)["curves"][0]
    curve = joint.StepCurve(date(2026, 11, 9), flat["base_rate"],
                            list(zip([date.fromisoformat(d) for d in inputs["curves"][0]["step_dates"]],
                                     flat["step_rates"], strict=True)), ())
    ps = ois.periods("SOFR", date(2026, 11, 9), turn_inst["tenor"])
    turn_inst_in = next(x for x in inputs["instruments"] if x.get("turn"))
    turn_inst_in["rate"] = ois.par_rate("SOFR", ps, curve)
    out = _solve(inputs)
    assert abs(out["turn_factors"][0]["factor"] - 1) < 1e-12
    assert base["turn_factors"][0]["factor"] != 1


def test_funding_zero_spread_limit() -> None:
    as_of = date(2026, 11, 9)
    disc = CurveData(as_of, "LOG_LINEAR_DF", (date(2027, 11, 9), date(2031, 11, 10)),
                     (0.96, 0.84))
    from quantforge_core import curves
    curve = curves.build(disc)
    ends = [date(2027, 2, 8), date(2029, 11, 9)]
    quotes = [(e, (1 / curve.discount(e) - 1) * 360 / (e - as_of).days) for e in ends]
    spreads, pillars, _ = joint.funding_curve(disc, quotes, [])
    assert all(abs(s) < 1e-15 for s in spreads)
    for (e, v) in pillars:
        assert abs(v - curve.discount(e)) < 1e-15


def test_bad_counts() -> None:
    inputs = _case(1)
    inputs["instruments"] = inputs["instruments"][:-1]
    with pytest.raises(Exception) as e:
        _solve(inputs)
    assert getattr(e.value, "code", None) == "E_INPUT"


def test_steps_reprice() -> None:
    inputs = _case(1)
    out, diag = ops_rates._joint_solve(Inputs(inputs))
    assert diag["max_repricing_error"] <= 1e-13
    assert math.isfinite(out["curves"][0]["base_rate"])
