"""Unit tests for `quantforge_core.saccr` that run inside the mutation harness (stage K round 2).

test_stage_k_w1b.py reads specifications/ outside python/, so it cannot be in the mutmut tests_dir.
These tests pin the SA-CCR contract (specifications/06-risk/sa-ccr.md, CRE52) with values written out
here: hand-derived helper values (CRE52.34 supervisory duration, CRE52.50 to 52.51 MPOR floors,
CRE52.23 multiplier, CRE52.40 delta) and one mixed netting set over all five asset classes whose
full output was measured from the current code, which passes the saccr_k goldens (evidence class:
measured). Error checks pin code, field and message.
"""

import json
import math
from typing import Any

import pytest

from quantforge_core import saccr as s
from quantforge_core.errors import QfError

T = s.Trade
M = s.Margin


def _err(f: Any, *args: Any, **kw: Any) -> tuple[str, str | None, str]:
    with pytest.raises(QfError) as e:
        f(*args, **kw)
    return e.value.code, e.value.field, e.value.message


def _book() -> list[s.Trade]:
    return [
        T("1", "IR", 10000, 30, 10, start=0, end=10, hedging_set="USD"),
        T("2", "IR", 10000, -20, 4, position="SHORT", start=0, end=4, hedging_set="USD"),
        T("3", "IR", 5000, 50, 11, kind="OPTION", position="BOUGHT", option_type="PUT",
          underlying_price=0.06, strike=0.05, exercise=1, start=1, end=11, hedging_set="EUR"),
        T("4", "FX", 1000, -5, 0.5, hedging_set="EURUSD"),
        T("5", "CREDIT", 2000, 10, 3, start=0, end=3, entity="A", subclass="BBB"),
        T("6", "CREDIT", 1000, -3, 2, kind="CDO", position="SOLD", start=0, end=2, entity="I",
          subclass="IG", attachment=0.03, detachment=0.07),
        T("7", "EQUITY", 500, 1, 1, entity="X", subclass="SINGLE"),
        T("8", "EQUITY", 300, 0, 0.01, position="SHORT", entity="Y", subclass="INDEX"),
        T("9", "COMMODITY", 400, 2, 2, entity="OIL", subclass="OIL_GAS"),
        T("10", "COMMODITY", 400, 2, 2, position="SHORT", entity="POW", subclass="ELECTRICITY"),
        T("11", "COMMODITY", 100, 0, 1, treatment="BASIS", hedging_set="B1", entity="G",
          subclass="METALS"),
        T("12", "IR", 1000, 0, 3, treatment="VOLATILITY", start=0, end=3, hedging_set="USD"),
        T("13", "EQUITY", 200, 0, 1, kind="OPTION", position="SOLD", option_type="CALL",
          underlying_price=10, strike=11, exercise=0.5, entity="X", subclass="SINGLE"),
    ]


EXPECTED = json.loads(r"""{"ead": 1175.2625494186414, "rc": 67.0, "pfe": 772.4732495847438, "multiplier": 1.0, "addon_aggregate": 772.4732495847438, "addon": {"IR": 416.4103981712895, "FX": 28.284271247461902, "CREDIT": 38.27926274408058, "EQUITY": 115.8858307326372, "COMMODITY": 173.61348668927465}, "v": 67.0, "c": 0.0, "margined": false, "mpor_days": null, "ead_unmargined": null, "capped": false, "hedging_sets": [{"asset_class": "IR", "treatment": "NORMAL", "key": "EUR", "addon": 50.414569065266406}, {"asset_class": "IR", "treatment": "NORMAL", "key": "USD", "addon": 296.349817318552}, {"asset_class": "IR", "treatment": "VOLATILITY", "key": "USD", "addon": 69.6460117874711}, {"asset_class": "FX", "treatment": "NORMAL", "key": "EURUSD", "addon": 28.284271247461902}, {"asset_class": "CREDIT", "treatment": "NORMAL", "key": "", "addon": 38.27926274408058}, {"asset_class": "EQUITY", "treatment": "NORMAL", "key": "", "addon": 115.8858307326372}, {"asset_class": "COMMODITY", "treatment": "NORMAL", "key": "ENERGY", "addon": 164.61348668927465}, {"asset_class": "COMMODITY", "treatment": "BASIS", "key": "B1", "addon": 9.0}], "trades": [{"id": "1", "supervisory_duration": 7.8693868057473315, "adjusted_notional": 78693.86805747332, "maturity_factor": 1.0, "delta": 1.0, "effective_notional": 78693.86805747332, "supervisory_factor": 0.005}, {"id": "2", "supervisory_duration": 3.6253849384403636, "adjusted_notional": 36253.849384403635, "maturity_factor": 1.0, "delta": -1.0, "effective_notional": -36253.849384403635, "supervisory_factor": 0.005}, {"id": "3", "supervisory_duration": 7.485592282404547, "adjusted_notional": 37427.961412022734, "maturity_factor": 1.0, "delta": -0.2693952177105327, "effective_notional": -10082.913813053281, "supervisory_factor": 0.005}, {"id": "4", "supervisory_duration": null, "adjusted_notional": 1000, "maturity_factor": 0.7071067811865476, "delta": 1.0, "effective_notional": 707.1067811865476, "supervisory_factor": 0.04}, {"id": "5", "supervisory_duration": 2.785840471498844, "adjusted_notional": 5571.680942997687, "maturity_factor": 1.0, "delta": 1.0, "effective_notional": 5571.680942997687, "supervisory_factor": 0.0054}, {"id": "6", "supervisory_duration": 1.9032516392808096, "adjusted_notional": 1903.2516392808097, "maturity_factor": 1.0, "delta": -5.335040546308152, "effective_notional": -10153.924665390578, "supervisory_factor": 0.0038}, {"id": "7", "supervisory_duration": null, "adjusted_notional": 500, "maturity_factor": 1.0, "delta": 1.0, "effective_notional": 500.0, "supervisory_factor": 0.32}, {"id": "8", "supervisory_duration": null, "adjusted_notional": 300, "maturity_factor": 0.2, "delta": -1.0, "effective_notional": -60.0, "supervisory_factor": 0.2}, {"id": "9", "supervisory_duration": null, "adjusted_notional": 400, "maturity_factor": 1.0, "delta": 1.0, "effective_notional": 400.0, "supervisory_factor": 0.18}, {"id": "10", "supervisory_duration": null, "adjusted_notional": 400, "maturity_factor": 1.0, "delta": -1.0, "effective_notional": -400.0, "supervisory_factor": 0.4}, {"id": "11", "supervisory_duration": null, "adjusted_notional": 100, "maturity_factor": 1.0, "delta": 1.0, "effective_notional": 100.0, "supervisory_factor": 0.09}, {"id": "12", "supervisory_duration": 2.785840471498844, "adjusted_notional": 2785.8404714988437, "maturity_factor": 1.0, "delta": 1.0, "effective_notional": 2785.8404714988437, "supervisory_factor": 0.025}, {"id": "13", "supervisory_duration": null, "adjusted_notional": 200, "maturity_factor": 1.0, "delta": -0.6224569176795118, "effective_notional": -124.49138353590237, "supervisory_factor": 0.32}]}""")


def _close(a: Any, b: Any) -> None:
    if isinstance(b, dict):
        assert isinstance(a, dict) and list(a) == list(b)
        for k in b:
            _close(a[k], b[k])
    elif isinstance(b, list):
        assert isinstance(a, list) and len(a) == len(b)
        for x, y in zip(a, b, strict=True):
            _close(x, y)
    elif isinstance(b, float):
        assert not isinstance(a, bool) and a == pytest.approx(b, rel=1e-13, abs=1e-300)
    else:
        assert a == b and type(a) is type(b)


def test_mixed_book_unmargined() -> None:
    _close(s.ead(_book()), EXPECTED)


def test_mixed_book_margined() -> None:
    r = s.ead(_book(), collateral=200.0, margin=M(10, 5, 2, 1))
    assert r["ead"] == pytest.approx(264.96126166083457, rel=1e-13)
    assert r["rc"] == 13 and r["mpor_days"] == 10 and r["margined"] is True
    assert r["pfe"] == pytest.approx(176.25804404345328, rel=1e-13)
    assert r["multiplier"] == pytest.approx(0.7541300172784287, rel=1e-13)
    assert r["ead_unmargined"] == pytest.approx(992.4562364338797, rel=1e-13)
    assert r["capped"] is False and r["c"] == 200.0 and r["v"] == 67.0
    mf = 1.5 * math.sqrt(10 / 250)
    assert all(t["maturity_factor"] == mf for t in r["trades"])


def test_margined_cap_and_mpor() -> None:
    one = [T("1", "FX", 1000, 0, 0.04, hedging_set="P")]  # MF = sqrt(10/250) unmargined
    r = s.ead(one, margin=M(0, 0, 0, 30))
    assert r["mpor_days"] == 39  # 9 + remargin days
    un = 1.4 * 0.04 * 1000 * math.sqrt(10 / 250)
    assert r["ead_unmargined"] == pytest.approx(un, rel=1e-14)
    assert r["capped"] is True and r["ead"] == r["ead_unmargined"]
    assert s.ead(one, margin=M(0, 0, 0, 1, mpor_days=50))["mpor_days"] == 50
    assert s.ead(one, margin=M(0, 0, 0, 1, mpor_days=3))["mpor_days"] == 10
    assert s.ead(one, margin=M(100, 20, 30, 1))["rc"] == 90.0
    assert s.ead(one, collateral=-50.0, margin=M(10, 5, 30, 1))["rc"] == 50.0
    assert s.ead(one, collateral=-50.0)["rc"] == 50.0
    assert s.ead(one, collateral=50.0)["rc"] == 0.0


def test_ir_without_offset() -> None:
    r = s.ead(_book()[:3], ir_offset=False)
    assert r["ead"] == pytest.approx(959.2144187845115, rel=1e-13)
    assert r["addon"]["IR"] == pytest.approx(625.1531562746511, rel=1e-13)


def test_ir_buckets_and_offset_formula() -> None:
    # one trade per maturity bucket (CRE52.57): end < 1, 1 <= end <= 5, end > 5
    tr = [T("a", "IR", 1000, 0, 1, start=0, end=0.5, hedging_set="USD"),
          T("b", "IR", 1000, 0, 1, start=0, end=5, hedging_set="USD", position="SHORT"),
          T("c", "IR", 1000, 0, 1, start=0, end=6, hedging_set="USD")]
    d = [1000 * s.supervisory_duration(0, e) for e in (0.5, 5, 6)]
    d1, d2, d3 = d[0], -d[1], d[2]
    en = math.sqrt(d1 * d1 + d2 * d2 + d3 * d3 + 1.4 * d1 * d2 + 1.4 * d2 * d3 + 0.6 * d1 * d3)
    assert s.ead(tr)["addon"]["IR"] == pytest.approx(0.005 * en, rel=1e-14)
    assert s.ead(tr, ir_offset=False)["addon"]["IR"] == pytest.approx(
        0.005 * (abs(d1) + abs(d2) + abs(d3)), rel=1e-14)
    assert [s._bucket(x) for x in (0.0, 0.99, 1.0, 5.0, 5.01)] == [1, 1, 2, 2, 3]


def test_helpers() -> None:
    assert s.supervisory_duration(0, 10) == pytest.approx((1 - math.exp(-0.5)) / 0.05, rel=1e-15)
    assert s.supervisory_duration(1, 2) == pytest.approx(
        (math.exp(-0.05) - math.exp(-0.1)) / 0.05, rel=1e-15)
    assert s.supervisory_duration(0, 0) == 10 / 250
    assert s.supervisory_duration(0, 0.01) == 10 / 250
    assert s.MIN_YEARS == 0.04 and s.ALPHA == 1.4 and s.FLOOR == 0.05 and s.SD_RATE == 0.05
    assert s.YEAR_DAYS == 250
    assert s.TREATMENT_SCALE == {"NORMAL": 1.0, "BASIS": 0.5, "VOLATILITY": 5.0}
    assert s.CLASSES == ("IR", "FX", "CREDIT", "EQUITY", "COMMODITY")
    assert s.TREATMENTS == ("NORMAL", "BASIS", "VOLATILITY")
    assert s.KINDS == ("LINEAR", "OPTION", "CDO")
    assert s.POSITIONS == ("LONG", "SHORT", "BOUGHT", "SOLD") and s.OPTION_TYPES == ("CALL", "PUT")
    assert s.SUBCLASSES == tuple(sorted(s.SUBCLASSES)) and len(s.SUBCLASSES) == 16
    assert s.COMMODITY_SET == {"ELECTRICITY": "ENERGY", "OIL_GAS": "ENERGY", "METALS": "METALS",
                               "AGRICULTURAL": "AGRICULTURAL", "OTHER": "OTHER"}
    assert s._phi(0.0) == 0.5 and s._phi(1.0) == pytest.approx(0.8413447460685429, rel=1e-15)


def test_mpor_floor() -> None:
    assert s.mpor_floor(M(0, 0, 0, 1), 1) == 10
    assert s.mpor_floor(M(0, 0, 0, 2), 1) == 11
    assert s.mpor_floor(M(0, 0, 0, 1), 5000) == 10
    assert s.mpor_floor(M(0, 0, 0, 1), 5001) == 20
    assert s.mpor_floor(M(0, 0, 0, 30), 5001) == 39
    assert s.mpor_floor(M(0, 0, 0, 1, illiquid=True), 1) == 20
    assert s.mpor_floor(M(0, 0, 0, 1, disputes=True), 1) == 20
    assert s.mpor_floor(M(0, 0, 0, 1, illiquid=True, disputes=True), 1) == 40


def test_multiplier() -> None:
    assert s.multiplier(0.0, 1.0) == 1.0
    assert s.multiplier(5.0, 0.0) == 1.0
    assert s.multiplier(-1.0, 0.0) == 0.05
    assert s.multiplier(-10.0, 10.0) == pytest.approx(0.05 + 0.95 * math.exp(-10 / 19), rel=1e-15)
    assert s.multiplier(-1e-300, 1e300) == pytest.approx(1.0, rel=1e-15)


def test_supervisory_delta() -> None:
    assert s.supervisory_delta(T("a", "FX", 1, 0, 1)) == 1.0
    assert s.supervisory_delta(T("a", "FX", 1, 0, 1, position="SHORT")) == -1.0
    cdo: dict[str, Any] = dict(asset_class="CREDIT", notional=1, market_value=0, maturity=1,
                               kind="CDO", attachment=0.0, detachment=1.0)
    assert s.supervisory_delta(T("a", position="BOUGHT", **cdo)) == pytest.approx(1.0, rel=1e-15)
    assert s.supervisory_delta(T("a", position="SOLD", **cdo)) == pytest.approx(-1.0, rel=1e-15)
    t2 = T("a", position="SOLD", **{**cdo, "attachment": 0.1, "detachment": 0.2})
    assert s.supervisory_delta(t2) == pytest.approx(-15 / (2.4 * 3.8), rel=1e-15)
    opt: dict[str, Any] = dict(asset_class="FX", notional=1, market_value=0, maturity=1,
                               kind="OPTION", underlying_price=1.0, strike=1.0, exercise=1.0)
    sig = 0.15
    d1 = 0.5 * sig
    phi = s._phi
    assert s.supervisory_delta(T("a", position="BOUGHT", option_type="CALL", **opt)) == pytest.approx(phi(d1))
    assert s.supervisory_delta(T("a", position="SOLD", option_type="CALL", **opt)) == pytest.approx(-phi(d1))
    assert s.supervisory_delta(T("a", position="BOUGHT", option_type="PUT", **opt)) == pytest.approx(-phi(-d1))
    assert s.supervisory_delta(T("a", position="SOLD", option_type="PUT", **opt)) == pytest.approx(phi(-d1))
    sh = T("a", position="BOUGHT", option_type="CALL", shift=0.02,
           **{**opt, "underlying_price": -0.01, "strike": -0.005})
    d1 = (math.log(0.01 / 0.015) + 0.5 * sig * sig * 1.0) / sig
    assert s.supervisory_delta(sh) == pytest.approx(phi(d1), rel=1e-14)
    lt = T("a", position="BOUGHT", option_type="CALL", **{**opt, "exercise": 4.0, "strike": 1.2})
    d1 = (math.log(1 / 1.2) + 0.5 * sig * sig * 4.0) / (sig * 2.0)
    assert s.supervisory_delta(lt) == pytest.approx(phi(d1), rel=1e-14)


def test_set_keys_and_entities() -> None:
    assert s._set_key(T("a", "IR", 1, 0, 1, hedging_set="USD")) == "USD"
    assert s._set_key(T("a", "FX", 1, 0, 1, hedging_set="EURUSD")) == "EURUSD"
    assert s._set_key(T("a", "EQUITY", 1, 0, 1, entity="E", subclass="INDEX")) == ""
    assert s._set_key(T("a", "COMMODITY", 1, 0, 1, entity="E", subclass="AGRICULTURAL")) == "AGRICULTURAL"
    assert s._set_key(T("a", "EQUITY", 1, 0, 1, treatment="BASIS", hedging_set="H", entity="E",
                        subclass="INDEX")) == "H"
    assert s._factor(T("a", "EQUITY", 1, 0, 1, treatment="VOLATILITY", entity="E", subclass="INDEX")) == 1.0
    assert s._option_vol(T("a", "CREDIT", 1, 0, 1, subclass="SG")) == 0.80
    # two names in one hedging set: rho 0.5 (single names), systematic and idiosyncratic parts
    tr = [T("a", "EQUITY", 100, 0, 1, entity="E1", subclass="SINGLE"),
          T("b", "EQUITY", 100, 0, 1, entity="E2", subclass="SINGLE", position="SHORT")]
    a = 0.32 * 100
    assert s.ead(tr)["addon"]["EQUITY"] == pytest.approx(math.sqrt(2 * 0.75 * a * a), rel=1e-14)
    assert s._single_factor([(0.5, 10.0), (0.5, -10.0)]) == pytest.approx(math.sqrt(150.0), rel=1e-15)
    assert s._single_factor([(1.0, 3.0), (1.0, 4.0)]) == pytest.approx(7.0, rel=1e-15)
    # FX: one pair nets; two pairs add
    fx = [T("a", "FX", 100, 0, 1, hedging_set="P"),
          T("b", "FX", 60, 0, 1, hedging_set="P", position="SHORT"),
          T("c", "FX", 10, 0, 1, hedging_set="Q", position="SHORT")]
    assert s.ead(fx)["addon"]["FX"] == pytest.approx(0.04 * 40 + 0.04 * 10, rel=1e-14)
    # the same entity in two commodity categories is two hedging sets
    cm = [T("a", "COMMODITY", 100, 0, 1, entity="Z", subclass="METALS"),
          T("b", "COMMODITY", 100, 0, 1, entity="Z", subclass="OTHER")]
    rows = s.ead(cm)["hedging_sets"]
    assert [r["key"] for r in rows] == ["METALS", "OTHER"]  # type: ignore[index]
    assert rows[0]["addon"] == pytest.approx(18.0, rel=1e-14)  # type: ignore[index]


def test_structure_errors() -> None:
    ir: dict[str, Any] = dict(asset_class="IR", notional=1, market_value=0, maturity=1, start=0, end=1,
                              hedging_set="U")
    assert _err(s.ead, []) == ("E_INPUT", "trades", "trades is empty")
    assert _err(s.ead, [T("a", **ir), T("a", **ir)]) == ("E_INPUT", "id", "duplicate trade id a")
    assert _err(s.ead, [T("a", **{**ir, "start": None})]) == (
        "E_INPUT", "start", "trade a: start is required for IR and CREDIT trades")
    assert _err(s.ead, [T("a", **{**ir, "end": None})]) == (
        "E_INPUT", "end", "trade a: end is required for IR and CREDIT trades")
    assert _err(s.ead, [T("a", "CREDIT", 1, 0, 1, entity="E", subclass="A")]) == (
        "E_INPUT", "start", "trade a: start is required for IR and CREDIT trades")
    hs = "is required for IR, FX and basis trades"
    assert _err(s.ead, [T("a", **{**ir, "hedging_set": None})]) == (
        "E_INPUT", "hedging_set", f"trade a: hedging_set {hs}")
    assert _err(s.ead, [T("a", "FX", 1, 0, 1)]) == ("E_INPUT", "hedging_set", f"trade a: hedging_set {hs}")
    assert _err(s.ead, [T("a", "EQUITY", 1, 0, 1, treatment="BASIS", entity="E", subclass="INDEX")]) == (
        "E_INPUT", "hedging_set", f"trade a: hedging_set {hs}")
    ecc = "is required for CREDIT, EQUITY and COMMODITY trades"
    assert _err(s.ead, [T("a", "EQUITY", 1, 0, 1, subclass="INDEX")]) == (
        "E_INPUT", "entity", f"trade a: entity {ecc}")
    assert _err(s.ead, [T("a", "COMMODITY", 1, 0, 1, entity="E")]) == (
        "E_INPUT", "subclass", f"trade a: subclass {ecc}")
    assert _err(s.ead, [T("a", "EQUITY", 1, 0, 1, entity="E", subclass="AAA")]) == (
        "E_INPUT", "subclass", "trade a: subclass AAA is not a EQUITY subclass")
    assert _err(s.ead, [T("a", "FX", 1, 0, 1, hedging_set="P", subclass="AAA")]) == (
        "E_INPUT", "subclass", "trade a: FX trades take no subclass")
    assert _err(s.ead, [T("a", "FX", 1, 0, 1, hedging_set="P", position="BOUGHT")]) == (
        "E_INPUT", "position", "trade a: position BOUGHT does not fit kind LINEAR")
    assert _err(s.ead, [T("a", "FX", 1, 0, 1, hedging_set="P", kind="OPTION", position="SHORT")]) == (
        "E_INPUT", "position", "trade a: position SHORT does not fit kind OPTION")
    opt: dict[str, Any] = dict(asset_class="FX", notional=1, market_value=0, maturity=1, hedging_set="P",
                               kind="OPTION", position="BOUGHT", option_type="CALL",
                               underlying_price=1.0, strike=1.0, exercise=1.0)
    for field in ("option_type", "underlying_price", "strike", "exercise"):
        assert _err(s.ead, [T("a", **{**opt, field: None})]) == (
            "E_INPUT", field, f"trade a: {field} is required for OPTION trades")
    assert _err(s.ead, [T("a", "EQUITY", 1, 0, 1, kind="CDO", position="BOUGHT", entity="E",
                          subclass="INDEX")]) == ("E_INPUT", "kind", "trade a: CDO tranches are CREDIT trades")
    cdo: dict[str, Any] = dict(asset_class="CREDIT", notional=1, market_value=0, maturity=1, start=0,
                               end=1, entity="E", subclass="IG", kind="CDO", position="BOUGHT",
                               attachment=0.1, detachment=0.2)
    assert _err(s.ead, [T("a", **{**cdo, "attachment": None})]) == (
        "E_INPUT", "attachment", "trade a: attachment is required for CDO trades")
    assert _err(s.ead, [T("a", **{**cdo, "detachment": None})]) == (
        "E_INPUT", "detachment", "trade a: detachment is required for CDO trades")
    two = [T("a", "EQUITY", 1, 0, 1, entity="E", subclass="INDEX"),
           T("b", "EQUITY", 1, 0, 1, entity="E", subclass="SINGLE")]
    assert _err(s.ead, two) == ("E_INPUT", "subclass", "entity E has two subclasses")
    # the same entity under another treatment or category may carry another subclass
    s.ead([T("a", "EQUITY", 1, 0, 1, entity="E", subclass="INDEX"),
           T("b", "EQUITY", 1, 0, 1, entity="E", subclass="SINGLE", treatment="VOLATILITY")])
    s.ead([T("a", "COMMODITY", 1, 0, 1, entity="E", subclass="METALS"),
           T("b", "COMMODITY", 1, 0, 1, entity="E", subclass="OTHER")])
    # structure before domain (HR-122)
    assert _err(s.ead, [T("a", "FX", -1, 0, 1)])[1] == "hedging_set"


def test_domain_errors() -> None:
    fx: dict[str, Any] = dict(asset_class="FX", market_value=0, hedging_set="P")
    assert _err(s.ead, [T("a", notional=0, maturity=1, **fx)]) == (
        "E_DOMAIN", "notional", "trade a: notional must be positive")
    s.ead([T("a", notional=0.5, maturity=1, **fx)])
    assert _err(s.ead, [T("a", notional=1, maturity=0, **fx)]) == (
        "E_DOMAIN", "maturity", "trade a: maturity must be positive")
    s.ead([T("a", notional=1, maturity=0.5, **fx)])
    ir: dict[str, Any] = dict(asset_class="IR", notional=1, market_value=0, maturity=1, hedging_set="U")
    se = ("E_DOMAIN", "start", "trade a: need 0 <= start <= end")
    assert _err(s.ead, [T("a", start=-0.1, end=1, **ir)]) == se
    assert _err(s.ead, [T("a", start=2, end=1, **ir)]) == se
    s.ead([T("a", start=0, end=0, **ir)])
    s.ead([T("a", start=0.5, end=0.5, **ir)])
    s.ead([T("a", start=0.5, end=1, **ir)])
    opt: dict[str, Any] = dict(asset_class="FX", notional=1, market_value=0, maturity=1, hedging_set="P",
                               kind="OPTION", position="BOUGHT", option_type="CALL",
                               underlying_price=1.0, strike=1.0, exercise=1.0)
    pk = ("E_DOMAIN", "strike", "trade a: shifted price and strike must be positive")
    assert _err(s.ead, [T("a", **{**opt, "underlying_price": 0.0})]) == pk
    assert _err(s.ead, [T("a", **{**opt, "strike": 0.0})]) == pk
    assert _err(s.ead, [T("a", **{**opt, "strike": -0.01})]) == pk
    assert _err(s.ead, [T("a", **{**opt, "underlying_price": -0.01, "strike": 0.5})]) == pk
    assert _err(s.ead, [T("a", shift=0.015, **{**opt, "underlying_price": 0.01, "strike": -0.02})]) == pk
    s.ead([T("a", **{**opt, "underlying_price": 0.5, "strike": 0.5})])
    s.ead([T("a", shift=0.02, **{**opt, "underlying_price": -0.01, "strike": -0.01})])
    s.ead([T("a", shift=-0.005, **{**opt, "underlying_price": 0.01, "strike": 0.01})])
    assert _err(s.ead, [T("a", **{**opt, "exercise": 0.0})]) == (
        "E_DOMAIN", "exercise", "trade a: exercise must be positive")
    s.ead([T("a", **{**opt, "exercise": 0.5})])
    cdo: dict[str, Any] = dict(asset_class="CREDIT", notional=1, market_value=0, maturity=1, start=0,
                               end=1, entity="E", subclass="IG", kind="CDO", position="BOUGHT")
    ad = ("E_DOMAIN", "attachment", "trade a: need 0 <= attachment < detachment <= 1")
    assert _err(s.ead, [T("a", attachment=0.2, detachment=0.2, **cdo)]) == ad
    assert _err(s.ead, [T("a", attachment=-0.1, detachment=0.2, **cdo)]) == ad
    assert _err(s.ead, [T("a", attachment=0.1, detachment=1.1, **cdo)]) == ad
    s.ead([T("a", attachment=0.0, detachment=1.0, **cdo)])
    one = [T("a", notional=1, maturity=1, **fx)]
    assert _err(s.ead, one, margin=M(-1, 0, 0, 1)) == ("E_DOMAIN", "threshold", "threshold must not be negative")
    assert _err(s.ead, one, margin=M(0, -1, 0, 1)) == ("E_DOMAIN", "mta", "mta must not be negative")
    assert _err(s.ead, one, margin=M(0, 0, 0, 0)) == (
        "E_DOMAIN", "remargin_days", "remargin_days must be at least 1")
    assert _err(s.ead, one, margin=M(0, 0, 0, 1, mpor_days=0)) == (
        "E_DOMAIN", "mpor_days", "mpor_days must be at least 1")
    s.ead(one, margin=M(0, 0, -5, 1, mpor_days=1))
