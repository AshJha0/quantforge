"""Stage K wave 1b: SA-CCR (K-8d) and FRTB IMA backtesting (K-8e).

Specs specifications/06-risk/sa-ccr.md and specifications/06-risk/frtb-ima-backtest.md; rulings
KR-30 to KR-47. The CRE99 worked examples and the MAR99 tables are the published checks; SciPy's
binomial distribution is the independent library for the backtesting probabilities."""

import json
import math
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from scipy.stats import binom

from quantforge_core import frtb_backtest as fb
from quantforge_core import saccr
from quantforge_core.cli import registry
from quantforge_core.errors import QfError
from quantforge_core.saccr import Margin, Trade
from quantforge_core.var_risk import traffic_light

ROOT = Path(__file__).resolve().parents[2]
PARAMS = json.loads((ROOT / "specifications/06-risk/sa-ccr-parameters.json").read_text("utf-8"))
TABLES = json.loads(
    (ROOT / "specifications/06-risk/frtb-ima-backtest-tables.json").read_text("utf-8")
)


@pytest.fixture
def cli() -> Any:
    """Local registration (the committed registry is edited by the coordinator at integration)."""
    from quantforge_core.cli import ops_k_w1b  # noqa: F401 - registers the verbs

    for name in ("saccr", "frtb_backtest"):
        if not hasattr(registry.core, name):
            setattr(registry.core, name, registry._Core(name))
    return registry.execute


# CRE99.22, CRE99.41, CRE99.59 (Basel Framework PDF pages 524, 525, 529, 533)
EX1 = [
    Trade("1", "IR", 10000, 30, 10, start=0, end=10, hedging_set="USD"),
    Trade("2", "IR", 10000, -20, 4, position="SHORT", start=0, end=4, hedging_set="USD"),
    Trade(
        "3", "IR", 5000, 50, 11, kind="OPTION", position="BOUGHT", option_type="PUT",
        underlying_price=0.06, strike=0.05, exercise=1, start=1, end=11, hedging_set="EUR",
    ),
]  # fmt: skip
EX2 = [
    Trade("4", "CREDIT", 10000, 20, 3, start=0, end=3, entity="Firm A", subclass="AA"),
    Trade(
        "5",
        "CREDIT",
        10000,
        -40,
        6,
        position="SHORT",
        start=0,
        end=6,
        entity="Firm B",
        subclass="BBB",
    ),
    Trade("6", "CREDIT", 10000, 0, 5, start=0, end=5, entity="CDX.IG", subclass="IG"),
]
EX3 = [
    Trade("7", "COMMODITY", 10000, -50, 0.75, entity="CRUDE_OIL", subclass="OIL_GAS"),
    Trade(
        "8", "COMMODITY", 20000, -30, 2, position="SHORT", entity="CRUDE_OIL", subclass="OIL_GAS"
    ),
    Trade("9", "COMMODITY", 10000, 100, 5, entity="SILVER", subclass="METALS"),
]
WEEKLY = Margin(threshold=0, mta=5, nica=150, remargin_days=5)


def _ead(*a: Any, **k: Any) -> Any:
    return saccr.ead(*a, **k)


def _r(x: object) -> float:
    assert isinstance(x, float)
    return x


@pytest.mark.parametrize(
    ("trades", "kw", "printed"),
    [
        (EX1, {}, 569),
        (EX2, {}, 381),
        (EX3, {}, 5406),
        (EX1 + EX2, {}, 936),
        (EX1 + EX3, {"collateral": 200, "margin": WEEKLY}, 1879),
    ],
)
def test_cre99_printed_ead(trades: list[Trade], kw: dict[str, Any], printed: int) -> None:
    """Acceptance (KR-30): full precision, then rounded to the nearest integer as CRE99.20 prints."""
    assert round(_r(_ead(trades, **kw)["ead"])) == printed


def test_cre99_intermediates() -> None:
    r1 = _ead(EX1)
    t = r1["trades"]
    assert isinstance(t, list)
    assert [round(x["adjusted_notional"]) for x in t] == [78694, 36254, 37428]
    assert [round(x["supervisory_duration"], 2) for x in t] == [7.87, 3.63, 7.49]
    assert round(t[2]["delta"], 4) == -0.2694
    assert [round(x["effective_notional"]) for x in t] == [78694, -36254, -10083]
    hs = {h["key"]: h["addon"] for h in r1["hedging_sets"]}
    assert round(hs["USD"], 2) == 296.35 and round(hs["EUR"], 3) == 50.415
    assert round(_r(r1["addon_aggregate"])) == 347 and r1["rc"] == 60.0
    r2 = _ead(EX2)
    assert [round(x["adjusted_notional"]) for x in r2["trades"]] == [27858, 51836, 44240]
    assert round(_r(r2["addon_aggregate"])) == 282 and round(_r(r2["multiplier"]), 3) == 0.965
    r3 = _ead(EX3)
    assert round(r3["trades"][0]["effective_notional"]) == 8660
    hs3 = {h["key"]: h["addon"] for h in r3["hedging_sets"]}
    assert round(hs3["ENERGY"]) == 2041 and round(hs3["METALS"]) == 1800
    r5 = _ead(EX1 + EX3, collateral=200, margin=WEEKLY)
    assert r5["mpor_days"] == 14 and r5["rc"] == 0.0 and r5["v"] == 80.0
    eff5 = [x["effective_notional"] for x in r5["trades"]]
    # CRE99.90 prints -7,100 for trade 2, which is 2 x the rounded 3,550; full precision is
    # -7,099.30 (KR-31 records this printed value as a source rounding, not a nearest-integer one).
    assert [round(x) for x in eff5] == [27934, -12869, -3579, 3550, -7099, 3550]
    assert abs(eff5[4] - (-7100)) < 1.0
    assert round(eff5[3] + eff5[4]) == -3550  # CRE99.91 EN crude oil
    a = [0.0038 * 27858.405, -0.0054 * 51836.356, 0.0038 * 44239.843]  # CRE99.52, to printed d
    assert [round(x) for x in a] == [106, -280, 168]
    assert round(_r(r5["addon"]["IR"])) == 123 and round(_r(r5["addon"]["COMMODITY"])) == 1278
    assert round(_r(r5["addon_aggregate"])) == 1401 and round(_r(r5["multiplier"]), 3) == 0.958
    assert r5["capped"] is False and _r(r5["ead_unmargined"]) > _r(r5["ead"])


def test_cre99_54_table() -> None:
    """CRE99.54 printed table (PDF pages 531-532) from the entity add-ons at full precision."""
    r = _ead(EX2)
    eff = [x["effective_notional"] for x in r["trades"]]
    a = [0.0038 * eff[0], 0.0054 * eff[1], 0.0038 * eff[2]]
    rho = [0.5, 0.5, 0.8]
    assert [round(r_ * x_, 1) for r_, x_ in zip(rho, a, strict=True)] == [52.9, -140.0, 134.5]
    assert [round(x * x) for x in a] == [11207, 78353, 28261]
    assert [round((1 - r_ * r_) * x * x) for r_, x in zip(rho, a, strict=True)] == [
        8405,
        58765,
        10174,
    ]
    s = sum(r_ * x for r_, x in zip(rho, a, strict=True))
    assert round(s, 1) == 47.5 and round(s * s) == 2253
    assert round(sum((1 - r_ * r_) * x * x for r_, x in zip(rho, a, strict=True))) == 77344


def test_parameter_json_matches_code() -> None:
    rows = {(r["asset_class"], r["subclass"] or ""): r for r in PARAMS["table2"]}
    assert set(rows) == set(saccr.TABLE2)
    for key, (sf, rho, vol) in saccr.TABLE2.items():
        assert (
            rows[key]["supervisory_factor"],
            rows[key]["correlation"],
            rows[key]["option_volatility"],
        ) == (sf, rho, vol)
        if key[0] == "COMMODITY":
            assert rows[key]["hedging_set"] == saccr.COMMODITY_SET[key[1]]
    assert PARAMS["alpha"] == saccr.ALPHA and PARAMS["multiplier_floor"] == saccr.FLOOR
    assert PARAMS["treatment_scale"] == saccr.TREATMENT_SCALE
    assert TABLES["multiplier_250"] == list(fb.MULTIPLIER_250)
    assert (TABLES["desk_limit_99"], TABLES["desk_limit_975"]) == (
        fb.DESK_LIMIT_99,
        fb.DESK_LIMIT_975,
    )


def test_rules_and_edges() -> None:
    assert saccr.supervisory_duration(0, 0) == 10 / 250  # floor
    m = Margin(0, 0, 0, remargin_days=1)
    assert saccr.mpor_floor(m, 10) == 10 and saccr.mpor_floor(m, 5001) == 20
    assert saccr.mpor_floor(Margin(0, 0, 0, 30), 1) == 39
    assert saccr.mpor_floor(Margin(0, 0, 0, 1, illiquid=True, disputes=True), 1) == 40
    assert saccr.multiplier(5.0, 0.0) == 1.0 and saccr.multiplier(-5.0, 0.0) == 0.05
    assert saccr.multiplier(1e6, 1e-300) == 1.0  # no overflow (found by the property test)
    cdo = Trade("c", "CREDIT", 100, 0, 5, kind="CDO", position="SOLD", start=0, end=5,
                entity="T", subclass="IG", attachment=0.03, detachment=0.07)  # fmt: skip
    assert saccr.supervisory_delta(cdo) == pytest.approx(-15 / (1.42 * 1.98))
    call = Trade("o", "EQUITY", 100, 0, 1, kind="OPTION", position="SOLD", option_type="CALL",
                 underlying_price=100, strike=100, exercise=1, entity="X", subclass="SINGLE")  # fmt: skip
    d1 = 0.5 * 1.2
    assert saccr.supervisory_delta(call) == pytest.approx(-0.5 * math.erfc(-d1 / math.sqrt(2)))
    shifted = Trade("s", "IR", 100, 0, 2, kind="OPTION", position="BOUGHT", option_type="CALL",
                    underlying_price=-0.001, strike=0.0, exercise=1, shift=0.01, start=1, end=2,
                    hedging_set="EUR")  # fmt: skip
    assert 0 < saccr.supervisory_delta(shifted) < 1
    # FX: full offset in a pair; mf below one year; maturity floor
    fx = [Trade("a", "FX", 1000, 0, 0.5, hedging_set="EURUSD"),
          Trade("b", "FX", 400, 0, 0.001, position="SHORT", hedging_set="EURUSD")]  # fmt: skip
    r = _ead(fx)
    expect = 0.04 * abs(1000 * math.sqrt(0.5) - 400 * math.sqrt(10 / 250))
    assert r["addon"]["FX"] == pytest.approx(expect)
    # basis halves and volatility multiplies by five the supervisory factor
    base = Trade("x", "EQUITY", 1000, 0, 1, entity="X", subclass="INDEX")
    basis = Trade(
        "x",
        "EQUITY",
        1000,
        0,
        1,
        entity="X",
        subclass="INDEX",
        treatment="BASIS",
        hedging_set="X/Y",
    )
    vol = Trade(
        "x",
        "EQUITY",
        1000,
        0,
        1,
        entity="X",
        subclass="INDEX",
        treatment="VOLATILITY",
        hedging_set="X",
    )
    a0 = _r(_ead([base])["addon_aggregate"])
    assert _r(_ead([basis])["addon_aggregate"]) == pytest.approx(0.5 * a0)
    assert _r(_ead([vol])["addon_aggregate"]) == pytest.approx(5 * a0)
    # no-offset IR formula
    r_no = _ead(EX1, ir_offset=False)
    assert _r(r_no["addon"]["IR"]) == pytest.approx(
        0.005 * (78693.868 + 36253.849 + 10082.914), rel=1e-6
    )
    # margined EAD capped at the unmargined EAD (CRE52.2): short trade, large threshold
    t = [Trade("s", "IR", 1000, 0, 0.02, start=0, end=0.02, hedging_set="USD")]
    rm = _ead(t, margin=Margin(threshold=1e6, mta=0, nica=0, remargin_days=1))
    assert rm["capped"] is True and rm["ead"] == rm["ead_unmargined"]
    # electricity is energy with its own factor; two commodity types partly offset
    e = [Trade("p", "COMMODITY", 100, 0, 1, entity="POWER", subclass="ELECTRICITY"),
         Trade("g", "COMMODITY", 100, 0, 1, position="SHORT", entity="GAS", subclass="OIL_GAS")]  # fmt: skip
    a, b = 40.0, -18.0
    assert _r(_ead(e)["addon_aggregate"]) == pytest.approx(
        math.sqrt((0.4 * (a + b)) ** 2 + 0.84 * (a * a + b * b))
    )


def _err(code: str, fn: Any, *a: Any, **k: Any) -> None:
    with pytest.raises(QfError) as e:
        fn(*a, **k)
    assert e.value.code == code


def test_saccr_errors() -> None:
    T = Trade
    _err("E_INPUT", _ead, [])
    _err("E_INPUT", _ead, [EX1[0], EX1[0]])
    _err("E_INPUT", _ead, [T("a", "IR", 1, 0, 1, hedging_set="USD")])  # no start/end
    _err("E_INPUT", _ead, [T("a", "FX", 1, 0, 1)])  # no pair
    _err("E_INPUT", _ead, [T("a", "EQUITY", 1, 0, 1, subclass="SINGLE")])  # no entity
    _err("E_INPUT", _ead, [T("a", "EQUITY", 1, 0, 1, entity="X", subclass="IG")])
    _err("E_INPUT", _ead, [T("a", "FX", 1, 0, 1, hedging_set="P", subclass="IG")])
    _err("E_INPUT", _ead, [T("a", "FX", 1, 0, 1, hedging_set="P", position="BOUGHT")])
    _err(
        "E_INPUT",
        _ead,
        [T("a", "FX", 1, 0, 1, hedging_set="P", kind="OPTION", position="BOUGHT")],
    )
    _err(
        "E_INPUT",
        _ead,
        [T("a", "EQUITY", 1, 0, 1, entity="X", subclass="SINGLE", kind="CDO", position="BOUGHT")],
    )
    _err(
        "E_INPUT",
        _ead,
        [
            T(
                "a",
                "CREDIT",
                1,
                0,
                1,
                start=0,
                end=1,
                entity="X",
                subclass="IG",
                kind="CDO",
                position="BOUGHT",
            )
        ],
    )
    _err("E_INPUT", _ead, [T("a", "EQUITY", 1, 0, 1, entity="X", subclass="SINGLE"),
                                T("b", "EQUITY", 1, 0, 1, entity="X", subclass="INDEX")])  # fmt: skip
    _err("E_DOMAIN", _ead, [T("a", "FX", 0, 0, 1, hedging_set="P")])
    _err("E_DOMAIN", _ead, [T("a", "FX", 1, 0, 0, hedging_set="P")])
    _err("E_DOMAIN", _ead, [T("a", "IR", 1, 0, 1, start=2, end=1, hedging_set="USD")])
    opt: dict[str, Any] = {
        "kind": "OPTION",
        "position": "BOUGHT",
        "option_type": "CALL",
        "hedging_set": "P",
    }
    _err(
        "E_DOMAIN",
        _ead,
        [T("a", "FX", 1, 0, 1, underlying_price=1, strike=-1, exercise=1, **opt)],
    )
    _err(
        "E_DOMAIN",
        _ead,
        [T("a", "FX", 1, 0, 1, underlying_price=1, strike=1, exercise=0, **opt)],
    )
    cdo: dict[str, Any] = {
        "kind": "CDO",
        "position": "BOUGHT",
        "start": 0,
        "end": 1,
        "entity": "X",
        "subclass": "IG",
    }
    _err("E_DOMAIN", _ead, [T("a", "CREDIT", 1, 0, 1, attachment=0.5, detachment=0.5, **cdo)])
    ok = [T("a", "FX", 1, 0, 1, hedging_set="P")]
    for m in (
        Margin(-1, 0, 0, 1),
        Margin(0, -1, 0, 1),
        Margin(0, 0, 0, 0),
        Margin(0, 0, 0, 1, mpor_days=0),
    ):
        _err("E_DOMAIN", _ead, ok, margin=m)
    # two errors: structural E_INPUT wins over E_DOMAIN
    _err("E_INPUT", _ead, [T("a", "FX", -1, 0, 1)])


_amount = st.floats(min_value=1.0, max_value=1e7, allow_nan=False)
_mv = st.floats(min_value=-1e5, max_value=1e5, allow_nan=False)
_mat = st.floats(min_value=0.01, max_value=30.0, allow_nan=False)


@st.composite
def _trades(draw: Any) -> list[Trade]:
    out = []
    for k in range(draw(st.integers(1, 6))):
        cls = draw(st.sampled_from(saccr.CLASSES))
        pos = draw(st.sampled_from(("LONG", "SHORT")))
        n, v, m = draw(_amount), draw(_mv), draw(_mat)
        if cls == "IR":
            s = draw(st.floats(0, 5))
            out.append(
                Trade(
                    str(k),
                    cls,
                    n,
                    v,
                    m,
                    position=pos,
                    start=s,
                    end=s + m,
                    hedging_set=draw(st.sampled_from(("USD", "EUR"))),
                )
            )
        elif cls == "FX":
            out.append(
                Trade(
                    str(k),
                    cls,
                    n,
                    v,
                    m,
                    position=pos,
                    hedging_set=draw(st.sampled_from(("EURUSD", "USDJPY"))),
                )
            )
        else:
            sub = draw(st.sampled_from([s for (c, s) in saccr.TABLE2 if c == cls]))
            ent = f"{sub}-{draw(st.integers(0, 2))}"
            se: dict[str, Any] = {"start": 0.0, "end": m} if cls == "CREDIT" else {}
            out.append(Trade(str(k), cls, n, v, m, position=pos, entity=ent, subclass=sub, **se))
    return out


@settings(max_examples=150, deadline=None)
@given(_trades(), st.floats(min_value=-1e5, max_value=1e5))
def test_properties(trades: list[Trade], c: float) -> None:
    r = _ead(trades, collateral=c)
    m = _r(r["multiplier"])
    assert 0.05 <= m <= 1.0  # (0.05, 1] in exact arithmetic; exp underflow can reach 0.05
    # netting never increases the add-on beyond the sum of the trades' own add-ons
    alone = math.fsum(_r(_ead([t])["addon_aggregate"]) for t in trades)
    assert _r(r["addon_aggregate"]) <= alone * (1 + 1e-12) + 1e-9
    # EAD is monotone in notional (all notionals scaled up by the same factor)
    bigger = [Trade(**{**t.__dict__, "notional": t.notional * 1.5}) for t in trades]
    assert _r(_ead(bigger, collateral=c)["ead"]) >= _r(r["ead"]) * (1 - 1e-12)
    # collateral never increases EAD
    assert _r(_ead(trades, collateral=c + 100.0)["ead"]) <= _r(r["ead"]) * (1 + 1e-12) + 1e-9


def test_cli_saccr(cli: Any) -> None:
    raw: dict[str, Any] = {
        "collateral": 200,
        "margin": {"threshold": 0, "mta": 5, "nica": 150, "remargin_days": 5},
        "trades": [
            {"id": "1", "asset_class": "IR", "notional": 10000, "market_value": 30, "maturity": 10,
             "start": 0, "end": 10, "hedging_set": "USD", "position": "LONG"},
            {"id": "9", "asset_class": "COMMODITY", "notional": 10000, "market_value": 100, "maturity": 5,
             "entity": "SILVER", "subclass": "METALS", "position": "LONG", "kind": "LINEAR", "treatment": "NORMAL"},
            {"id": "3", "asset_class": "IR", "notional": 5000, "market_value": 50, "maturity": 11, "kind": "OPTION",
             "position": "BOUGHT", "option_type": "PUT", "underlying_price": 0.06, "strike": 0.05, "exercise": 1,
             "start": 1, "end": 11, "hedging_set": "EUR", "shift": 0},
        ],
    }  # fmt: skip
    out = cli("risk.saccr.ead", raw)
    assert out["margined"] is True and out["mpor_days"] == 14
    with pytest.raises(QfError) as e:
        cli("risk.saccr.ead", {**raw, "trades": [{**raw["trades"][0], "asset_class": "RATES"}]})
    assert e.value.code == "E_SCHEMA"
    with pytest.raises(QfError) as e:
        cli("risk.saccr.ead", {**raw, "trades": [{**raw["trades"][0], "notional": float("nan")}]})
    assert e.value.code == "E_DOMAIN"
    z = cli(
        "risk.frtb.backtest.zone",
        {"observations": 250, "exceptions_actual": 5, "exceptions_hypothetical": 3},
    )
    assert z["zone"] == "AMBER" and z["multiplier"] == 1.70
    d = cli("risk.frtb.backtest.desk", {"observations": 250, "exceptions_99_actual": 13, "exceptions_99_hypothetical": 0,
                                         "exceptions_975_actual": 0, "exceptions_975_hypothetical": 30})  # fmt: skip
    assert d["eligible"] is False and d["breach_975"] is False
    c = cli(
        "risk.frtb.backtest.count",
        {"var": [1.0, None, 2.0], "actual": [-1.5, 0.0, None], "hypothetical": [0.0, 0.0, -2.0]},
    )
    assert c["exceptions"] == 3 and c["days_hypothetical"] == [1]


# ---------- K-8e ----------


def test_mar99_table2_new_operation() -> None:
    """Acceptance (KR-41): zones, multipliers and printed cumulative probabilities of MAR99 Table 2."""
    for x in range(16):
        r = fb.backtest_zone(250, x, 0)
        printed = TABLES["printed_table2_cumulative_percent"][min(x, 10)]
        if x <= 10:
            assert round(100 * _r(r["cumulative_probability"]), 2) == printed
        assert r["zone"] == TABLES["printed_table2_zone"][min(x, 10)]
        assert r["multiplier"] == (TABLES["multiplier_250"][x] if x < 10 else 2.0)
        assert (r["amber_from"], r["red_from"]) == (5, 10)
        assert _r(r["cumulative_probability"]) == pytest.approx(
            binom.cdf(x, 250, 0.01), rel=1e-12, abs=1e-15
        )


def test_mar99_table2_existing_traffic_light() -> None:
    """Outside check of risk.backtest.traffic_light (stage F) against MAR99 Table 2 (KR-43)."""
    for x in range(11):
        r = traffic_light(250, x, 0.99)
        assert (
            round(100 * _r(r["cumulative_probability"]), 2)
            == TABLES["printed_table2_cumulative_percent"][x]
        )
        assert (
            r["zone"]
            == {"GREEN": "GREEN", "AMBER": "YELLOW", "RED": "RED"}[TABLES["printed_table2_zone"][x]]
        )


def test_mar99_table1_against_scipy() -> None:
    for cov, row in TABLES["printed_table1_exact_percent_250"].items():
        p = 1 - float(cov.split("_")[1])
        for k, v in enumerate(row):
            assert round(100 * binom.pmf(k, 250, p), 1) == v
            exact = fb.binomial_cdf(250, k, p) - fb.binomial_cdf(250, k - 1, p)
            assert exact == pytest.approx(binom.pmf(k, 250, p), abs=1e-12)


@pytest.mark.parametrize("n", [1, 5, 6, 100, 250, 260, 500, 1000, 10_000])
def test_general_rule_other_sizes(n: int) -> None:
    r = fb.backtest_zone(n, 0, 0)
    a, red = r["amber_from"], r["red_from"]
    assert isinstance(a, int) and isinstance(red, int)
    assert binom.cdf(a, n, 0.01) >= 0.95 and (a == 0 or binom.cdf(a - 1, n, 0.01) < 0.95)
    assert binom.cdf(red, n, 0.01) >= 0.9999 and (red == 0 or binom.cdf(red - 1, n, 0.01) < 0.9999)
    assert (r["multiplier"] is None) == (n != 250)


def test_desk_and_errors() -> None:
    d = fb.backtest_desk(250, 12, 11, 30, 29)
    assert d["eligible"] is True and d["exceptions_99"] == 12 and d["exceptions_975"] == 30
    assert _r(d["cumulative_probability_975"]) == pytest.approx(
        binom.cdf(30, 250, 0.025), rel=1e-12
    )
    assert fb.backtest_desk(250, 0, 13, 0, 0)["breach_99"] is True
    assert fb.backtest_desk(250, 0, 0, 31, 0)["breach_975"] is True
    assert fb.binomial_cdf(10, -1, 0.1) == 0.0 and fb.binomial_cdf(10, 10, 0.1) == 1.0
    _err("E_LIMIT", fb.backtest_zone, 1_000_001, -1, 0)  # two errors: limit first
    _err("E_DOMAIN", fb.backtest_zone, 0, 0, 0)
    _err("E_DOMAIN", fb.backtest_zone, 10, 11, 0)
    _err("E_DOMAIN", fb.backtest_zone, 10, 0, -1)
    _err("E_DOMAIN", fb.backtest_desk, 10, 0, 0, 0, 11)
    _err("E_INPUT", fb.count_exceptions, [], [], [])
    _err("E_INPUT", fb.count_exceptions, [1.0], [], [1.0])
    _err("E_INPUT", fb.count_exceptions, [1.0], [1.0], [])
    c = fb.count_exceptions([1.0, 1.0], [-1.0, -1.0000001], [None, 0.0])
    assert (c["exceptions_actual"], c["exceptions_hypothetical"], c["days_actual"]) == (1, 1, [1])
