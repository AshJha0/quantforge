"""Stage K wave 2 lane A: FRTB DRC and RRAO (K-8a) and FRTB IMA (K-8f).

Specs specifications/06-risk/frtb-drc-rrao.md and specifications/06-risk/frtb-ima.md; rulings KR-50 to
KR-69 and KR-112 to KR-122 (specifications/stage-k-rulings-w2.md). Goldens datasets/golden/stage_k/drc_k.json
and ima_k.json (oracle/python/gen_stage_k_w2a.py). SciPy is an independent cross-check of the PLA
statistics and the normal ES (reported, not counted: D6 precedent)."""

import importlib.util
import json
import math
import random
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from scipy import stats

from quantforge_core import frtb_drc as drc
from quantforge_core import frtb_ima as ima
from quantforge_core.cli import limits, limits_k_w2a, registry
from quantforge_core.cli.main import run_case
from quantforge_core.errors import QfError
from quantforge_core.frtb_drc import CtpPosition, Instrument, Position, SecPosition

ROOT = Path(__file__).resolve().parents[2]
TABLES = {
    k: {e["key"]: e["value"] for e in json.loads((ROOT / f"specifications/tables/stage_k/{k}.json").read_text("utf-8"))["entries"]}
    for k in ("mar22_drc", "mar23_rrao", "mar31_rfet", "mar32_pla", "mar33_ima")
}  # fmt: skip


def _runner() -> Any:
    spec = importlib.util.spec_from_file_location(
        "qf_runner_w2a", ROOT / "conformance/runner/runner.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def cli(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Local registration and limits hook (the committed registry and limits.py are edited by the
    coordinator at integration: program/STAGE_K_W2A_HANDOVER.md)."""
    from quantforge_core.cli import ops_k_w2a  # noqa: F401 - registers the verbs

    for name in ("frtb_drc", "frtb_ima"):
        if not hasattr(registry.core, name):
            setattr(registry.core, name, registry._Core(name))
    generic = limits.check_limits

    def hook(operation: str, raw: Any) -> None:
        if not limits_k_w2a.check(operation, raw):
            generic(operation, raw)

    monkeypatch.setattr(registry, "check_limits", hook)
    return registry.execute


def _code(f: Any, *a: Any, **k: Any) -> str:
    with pytest.raises(QfError) as e:
        f(*a, **k)
    return e.value.code


# ---- goldens --------------------------------------------------------------------------------------


@pytest.mark.parametrize("suite", ["drc_k", "ima_k"])
def test_goldens(cli: Any, suite: str) -> None:
    runner = _runner()
    classes = runner.load_policy(ROOT / "conformance/tolerances/policy.yaml")
    failures = []
    doc = json.loads((ROOT / f"datasets/golden/stage_k/{suite}.json").read_text("utf-8"))
    for case in doc["cases"]:
        req = {
            "schema_version": "1.0",
            "case_id": case["case_id"],
            "operation": case["operation"],
            "inputs": case["inputs"],
        }
        result = json.loads(json.dumps(run_case(json.dumps(req))))
        status, msgs = runner.judge(case, result, classes)
        if status != "pass":
            failures.append((case["case_id"], msgs[:2], result.get("error")))
    assert not failures, failures[:5]
    assert doc["reviewer"].startswith("none: self-assessment")


# ---- KR-50: every hard-coded parameter equals the shared table ------------------------------------


def test_parameters_match_tables() -> None:
    t = TABLES["mar22_drc"]
    assert drc.LGD == {
        "COVERED": float(t["lgd.covered_bond"]),
        "SENIOR": float(t["lgd.senior_debt"]),
        "NON_SENIOR": float(t["lgd.non_senior_debt"]),
        "EQUITY": float(t["lgd.equity"]),
    }
    names = {"UNRATED": "Unrated", "DEFAULTED": "Defaulted"}
    assert drc.RISK_WEIGHT == {r: float(t["rw." + names.get(r, r)]) for r in drc.RATINGS}
    assert drc.MATURITY_FLOOR == float(t["maturity_weight_floor"])
    assert drc.CAPITAL_HORIZON == float(t["capital_horizon_years"])
    assert drc.CASH_EQUITY_SHORT == float(t["cash_equity_maturity_choices"][0])
    assert drc.CTP_CROSS_FACTOR == float(t["ctp_cross_index_factor"])
    r = TABLES["mar23_rrao"]
    assert drc.RRAO_WEIGHT == {
        "EXOTIC": float(r["rw.exotic_underlying"]),
        "OTHER": float(r["rw.other_residual_risk"]),
    }
    f = TABLES["mar31_rfet"]
    assert (ima.RFET_MIN_DAYS, ima.RFET_WINDOW_DAYS, ima.RFET_MIN_PER_WINDOW, ima.RFET_ALT_MIN_DAYS) == (
        f["rfet.min_obs_per_year"], f["rfet.window_days"], f["rfet.min_obs_per_window"], f["rfet.alt_min_obs_12m"],
    )  # fmt: skip
    assert ima.RFET_LOOKBACK_MONTHS == f["rfet.lookback_months"]
    for row, lows in ima.RFET_BUCKETS.items():
        printed = f["bucket." + row]
        assert lows == tuple(float(lo) for lo, _ in printed)
        assert [float(hi) for _, hi in printed[:-1]] == list(lows[1:])
        assert printed[-1][1] == ("1.00" if row == "D" else "inf")
    p = TABLES["mar32_pla"]
    mult = p["backtest.zone_multiplier"]
    assert ima.MULTIPLIER == tuple(float(mult[str(k)]) for k in range(10))
    assert ima.MULTIPLIER_RED == float(mult["10+"])
    assert ima.PLA_GREEN_SPEARMAN == float(p["pla.green.spearman_above"])
    assert ima.PLA_RED_SPEARMAN == float(p["pla.red.spearman_below"])
    assert ima.PLA_GREEN_KS_PERCENT / 100 == float(p["pla.green.ks_below"])
    assert ima.PLA_RED_KS_PERCENT / 100 == float(p["pla.red.ks_above"])
    assert ima.PLA_WINDOW == p["pla.window_days"]
    m = TABLES["mar33_ima"]
    assert ima.LIQUIDITY_HORIZONS == tuple(m["lh.j"][str(j)] for j in range(1, 6))
    assert ima.ES_CONFIDENCE == float(m["es.confidence"])
    assert ima.BASE_HORIZON == m["es.base_horizon_days"]
    assert ima.LH_TABLE == m["lh.table"]
    assert ima.SPECIFIED_FX_PAIRS == tuple(m["lh.specified_fx_pairs"])
    assert ima.IMCC_RHO == float(m["imcc.rho"])
    assert ima.SES_RHO == float(m["ses.rho"])
    assert abs(ima.normal_es_factor() - ima.NORMAL_ES_FACTOR_DOC) <= 1e-15  # one ulp apart


# ---- K-8a units -----------------------------------------------------------------------------------


def _p(pid: str, ob: str, sen: str, n: float, mv: float, m: float = 5.0, **kw: Any) -> Position:
    return Position(pid, ob, kw.pop("bucket", "CORPORATE"), sen, n, mv, m, **kw)


def test_jtd_and_weight_details() -> None:
    assert drc.gross_jtd(_p("a", "X", "SENIOR", 100, 100, lgd_applies=False)) == 100
    assert drc.gross_jtd(_p("a", "X", "SENIOR", 0, 0)) == 0
    assert drc.gross_jtd(_p("a", "X", "SENIOR", 100, 10)) == 0  # long floored at 0
    assert drc.gross_jtd(_p("a", "X", "SENIOR", -100, -10)) == 0  # short capped at 0
    assert (
        drc.maturity_weight(0.1) == 0.25
        and drc.maturity_weight(0.6) == 0.6
        and drc.maturity_weight(3) == 1
    )


def test_offset_greedy_kr53() -> None:
    # a junior short is served after the senior one, so the senior short gets the covered long
    assert drc.offset([(4, 10.0), (1, 10.0)], [(1, -10.0), (4, -10.0)]) == (0.0, 0.0)
    assert drc.offset([(1, 10.0)], [(3, -5.0)]) == (10.0, -5.0)
    assert drc.offset([(3, 10.0)], [(1, -4.0)]) == (6.0, 0.0)
    assert drc.offset([], []) == (0.0, 0.0)


def test_nonsec_buckets_and_errors() -> None:
    out: Any = drc.drc_nonsec(
        [_p("z", "Z", "SENIOR", 0, 0), _p("s", "S", "SENIOR", -10, -10)], {"Z": "A", "S": "B"}
    )
    assert [b["hbr"] for b in out["buckets"]] == [0.0]
    out = drc.drc_nonsec([_p("z", "Z", "SENIOR", 0, 0)], {"Z": "A"})
    assert out["buckets"] == [
        {"bucket": "CORPORATE", "hbr": None, "wtd_long": 0.0, "wtd_short": 0.0, "drc": 0.0}
    ]
    big = [_p(str(k), "X", "SENIOR", 1, 1) for k in range(drc.MAX_POSITIONS + 1)]
    assert _code(drc.drc_nonsec, big, {"X": "A"}) == "E_LIMIT"
    assert _code(drc.drc_nonsec, [_p("a", "X", "SENIOR", math.nan, 1)], {"X": "A"}) == "E_DOMAIN"


def test_sec_and_ctp_details() -> None:
    s = [
        SecPosition("a", "B1", "P", "T", 10, 0.5, 0.2),
        SecPosition("b", "B1", "P", "T", -4, 0.5, 0.2),
    ]
    out = drc.drc_sec_nonctp(s)
    assert out["buckets"][0]["wtd_long"] == pytest.approx(0.2 * 3)  # type: ignore[index]
    assert drc.drc_sec_nonctp([SecPosition("a", "B1", "P", "T", -4, 2, 0.2)])["drc"] == 0
    assert drc.drc_ctp(positions=[])["hbr_ctp"] is None
    c = [CtpPosition("a", "I", "S", "T", 100, 2, 0.1), CtpPosition("b", "I", "S", "T", -40, 2, 0.1)]
    out = drc.drc_ctp(positions=c)
    assert out["hbr_ctp"] == 1.0 and out["drc"] == pytest.approx(6.0)
    assert drc.ctp_total([-5, 3]) == pytest.approx(0.5)
    assert _code(drc.drc_ctp) == "E_INPUT"
    assert _code(drc.drc_ctp, bucket_drc=[0.0] * (drc.MAX_POSITIONS + 1)) == "E_LIMIT"
    assert (
        _code(drc.drc_sec_nonctp, [SecPosition("a", "B", "P", "T", 1, 1, math.inf)]) == "E_DOMAIN"
    )


def test_rrao_details() -> None:
    out = drc.rrao(
        [Instrument("a", 100, "EXOTIC", True, False), Instrument("b", 100, "OTHER", False, True)]
    )
    rows: Any = out["instruments"]
    assert [r["excluded"] for r in rows] == [False, True]
    assert out["rrao"] == 1.0


# ---- K-8a properties (spec A3) --------------------------------------------------------------------

_SEN = st.sampled_from(drc.SENIORITIES)
_OBL = st.sampled_from(["A", "B", "C"])
_AMT = st.integers(min_value=-1000, max_value=1000).map(float)
_MAT = st.sampled_from([0.1, 0.25, 0.5, 0.9, 1.0, 3.0])
_RAT = {"A": "BBB", "B": "BB", "C": "AA"}
_BKT = {"A": "CORPORATE", "B": "CORPORATE", "C": "SOVEREIGN"}


@st.composite
def _book(draw: Any) -> list[Position]:
    rows = draw(st.lists(st.tuples(_OBL, _SEN, _AMT, _AMT, _MAT), min_size=1, max_size=12))
    return [
        Position(f"p{k}", o, _BKT[o], s, n, mv, m)
        for k, (o, s, n, mv, m) in enumerate(rows)
        if not (n == 0 and mv != 0)
    ] or [Position("p0", "A", "CORPORATE", "SENIOR", 1.0, 1.0, 1.0)]


@settings(max_examples=300, deadline=None)
@given(
    _book(),
    st.integers(min_value=0, max_value=1000),
    st.sampled_from(["A", "B", "C"]),
    _SEN,
    st.randoms(),
)
def test_drc_properties(
    book: list[Position], extra: int, ob: str, sen: str, rnd: random.Random
) -> None:
    out = drc.drc_nonsec(book, _RAT)
    total = float(out["drc"])  # type: ignore[arg-type]
    assert total >= 0
    for b in out["buckets"]:  # type: ignore[attr-defined]
        assert b["drc"] >= 0 and (b["hbr"] is None or 0 <= b["hbr"] <= 1)
    # adding a long never lowers its bucket's DRC
    more = drc.drc_nonsec(
        [*book, Position("new", ob, _BKT[ob], sen, float(extra), float(extra), 2.0)], _RAT
    )
    before = {b["bucket"]: b["drc"] for b in out["buckets"]}  # type: ignore[attr-defined]
    after = {b["bucket"]: b["drc"] for b in more["buckets"]}  # type: ignore[attr-defined]
    assert after[_BKT[ob]] >= before.get(_BKT[ob], 0.0) - 1e-9 * (1 + after[_BKT[ob]])
    # permutation leaves every output unchanged (totals to rounding)
    shuffled = list(book)
    rnd.shuffle(shuffled)
    again = drc.drc_nonsec(shuffled, _RAT)
    assert again["positions"] == out["positions"]
    assert again["drc"] == pytest.approx(total, rel=1e-12, abs=1e-12)
    # scaling every amount by c scales DRC by c
    c = 2.5
    scaled = [
        Position(
            p.id,
            p.obligor,
            p.bucket,
            p.seniority,
            c * p.notional,
            c * p.market_value,
            p.maturity_years,
        )
        for p in book
    ]
    assert drc.drc_nonsec(scaled, _RAT)["drc"] == pytest.approx(c * total, rel=1e-12, abs=1e-12)


# ---- K-8f units -----------------------------------------------------------------------------------


def test_pla_and_pvalue_details() -> None:
    out = ima.pla([1, 2, 3, 4], [1, 2, 3, 4])
    assert out["zone"] == "GREEN" and out["spearman"] == 1 and out["ks_pvalue_asymptotic"] == 1.0
    assert out["regulatory_window"] is False
    assert ima.pla([1, 2, 3], [3, 2, 1])["spearman"] == -1
    assert ima._doubled_ranks([5, 1, 5, 5]) == [6, 2, 6, 6]
    assert ima.kolmogorov_q(0) == 1.0 and ima.kolmogorov_q(0.01) == 1.0
    assert ima.kolmogorov_q(40) == 0.0
    assert ima.pla_ks_pvalue(0, 250)["pvalue"] == 1.0
    assert _code(ima.pla, [0.0] * (ima.MAX_PNL + 1), [0.0]) == "E_LIMIT"
    assert _code(ima.pla, [1, 2, 3], [1, 1, 1]) == "E_DOMAIN"


@pytest.mark.parametrize("x", [0.05, 0.3, 0.6, 0.9, 0.99, 1.0, 1.01, 1.2, 1.8, 2.5, 4.0])
def test_kolmogorov_q_against_scipy(x: float) -> None:
    """Cross-check only (D6: same quantity, not counted)."""
    assert ima.kolmogorov_q(x) == pytest.approx(float(stats.kstwobign.sf(x)), rel=1e-12, abs=1e-15)


def test_liquidity_horizon_details() -> None:
    assert ima.fx_pair_specified("CHF/JPY")  # cross through USD
    assert not ima.fx_pair_specified("ISK/PLN")
    assert ima.liquidity_horizon(fx_pair="ISK/PLN")["n"] == 20
    assert ima.liquidity_horizon(category="EQ_large_cap", maturity_days=200)["rule"] == "table"
    assert (
        ima.liquidity_horizon(constituents=[(1.0, 120)], maturity_days=1)["rule"]
        == "index+maturity"
    )
    assert ima._next_horizon(500) == 120
    big = [(0.0, 10)] * (ima.MAX_LIST + 1)
    assert _code(ima.liquidity_horizon, constituents=big) == "E_LIMIT"


def test_es_and_capital_details() -> None:
    assert ima.horizon_weights() == (1, 1, 2, 2, 6)
    out = ima.es_lh(pnl=[[-1.0, -2.0, -3.0], [], [], [], []])
    assert out["mode"] == "pnl" and out["es"] == 3.0
    assert _code(ima.es_lh, pnl=[[0.0] * (ima.MAX_PNL + 1), [], [], [], []]) == "E_LIMIT"
    assert ima.imcc((1, 1, 1), {"CS": (1, 1, 2), "IR": (1, 2, 1)})["classes_floored"] == ["CS"]
    out = ima.capital(10, 0, 10, 0, 12, 0, [], 0, 100, qualitative_addon=0.25)
    assert out["m_c"] == 2.25 and out["k"] == 0 and out["acr_total"] == 45.0  # no desks: SA_G,A 0
    assert (
        _code(ima.capital, 1, 1, 1, 1, 0, 0, [("GREEN", 1.0)] * (ima.MAX_LIST + 1), 0, 1)
        == "E_LIMIT"
    )
    assert _code(ima.ses, [0.0] * (ima.MAX_LIST + 1), [], []) == "E_LIMIT"


def test_rfet_details() -> None:
    assert ima.months_back(date(2024, 2, 29), 12) == date(2023, 2, 28)
    assert ima.months_back(date(2026, 3, 31), 1) == date(2026, 2, 28)
    assert ima.months_back(date(2026, 1, 15), 12) == date(2025, 1, 15)
    every = [date(2025, 7, 1) + timedelta(days=k) for k in range(365)]
    out = ima.rfet(date(2026, 6, 30), every + [date(2026, 7, 1), date(2020, 1, 1)])
    assert out["distinct_days"] == 365 and out["first_failing_window_start"] is None and out["pass"]
    assert out["min_window_count"] == 90
    assert _code(ima.rfet, date(2026, 6, 30), [date(2026, 1, 1)] * (ima.MAX_LIST + 1)) == "E_LIMIT"
    assert ima.rfet_bucket("A", t=40)["upper"] is None
    assert ima.rfet_bucket("D", delta=0.99)["upper"] == 1.0
    assert ima.rfet_bucket("A", t=0)["bucket"] == 1


def test_limits_hook() -> None:
    assert limits_k_w2a.check("risk.frtb.rrao", {}) is False
    assert limits_k_w2a.check("risk.frtb.pla", {"hpl": [0.0] * 5, "rtpl": [0.0] * 5}) is True
    with pytest.raises(QfError) as e:
        limits_k_w2a.check("risk.frtb.pla", {"hpl": [0.0] * (limits_k_w2a.MAX_PNL + 1), "rtpl": []})
    assert e.value.code == "E_LIMIT"
    assert limits_k_w2a.check("risk.frtb.ima.es_lh", {"pnl": [[0.0] * 200_000, []]}) is True
    with pytest.raises(QfError):
        limits_k_w2a.check("risk.frtb.ima.es_lh", {"pnl": [[0.0] * (limits_k_w2a.MAX_PNL + 1)]})


def test_cli_limits_order(cli: Any) -> None:
    """KR-67: E_LIMIT comes before the finite rule and before E_INPUT."""
    big = [0.0] * (limits_k_w2a.MAX_PNL + 1)
    big[0] = "NaN"  # type: ignore[call-overload]
    with pytest.raises(QfError) as e:
        cli("risk.frtb.pla", {"hpl": big, "rtpl": [1.0]})
    assert e.value.code == "E_LIMIT"
    # a P&L list above the generic 100,000 cap is accepted (KR-67: 1,000,000 per list)
    pnl = [float(-k) for k in range(150_000)]
    out = cli("risk.frtb.ima.es_lh", {"pnl": [pnl, [], [], [], []]})
    assert out["es"] > 0


# ---- K-8f properties (spec A3) --------------------------------------------------------------------

_SERIES = st.lists(st.integers(min_value=-50, max_value=50), min_size=3, max_size=40)


@settings(max_examples=300, deadline=None)
@given(_SERIES, st.data())
def test_pla_invariances_and_scipy(h: list[int], data: Any) -> None:
    r = data.draw(
        st.lists(st.integers(min_value=-50, max_value=50), min_size=len(h), max_size=len(h))
    )
    if len(set(h)) < 2 or len(set(r)) < 2:
        return
    hf, rf = [float(x) for x in h], [float(x) for x in r]
    base = ima.pla(hf, rf)
    swapped = ima.pla(rf, hf)
    assert swapped["spearman"] == pytest.approx(base["spearman"], abs=1e-15)
    assert swapped["ks_count"] == base["ks_count"]

    # strictly increasing transforms: spearman invariant for either series, KS for a common one
    def g(x: float) -> float:
        return math.exp(x / 10) + 3 * x

    assert ima.spearman([g(x) for x in hf], rf) == pytest.approx(base["spearman"], abs=1e-15)
    assert ima.spearman(hf, [x**3 for x in rf]) == pytest.approx(base["spearman"], abs=1e-15)
    assert ima.ks_count([g(x) for x in hf], [g(x) for x in rf]) == base["ks_count"]
    # SciPy cross-check (independent library, reported, not counted)
    assert base["spearman"] == pytest.approx(float(stats.spearmanr(hf, rf).statistic), abs=1e-12)
    assert base["ks"] == pytest.approx(float(stats.ks_2samp(hf, rf).statistic), abs=1e-12)


@settings(max_examples=200, deadline=None)
@given(st.integers(min_value=0, max_value=4), st.floats(min_value=0, max_value=1e6))
def test_es_cascade_scaling(j: int, e: float) -> None:
    w = ima.horizon_weights()
    single = [0.0] * 5
    single[j] = e
    assert ima.es_lh(es_t=single)["es"] == pytest.approx(e * math.sqrt(w[j]), rel=1e-14)
    # every risk factor at horizon LH_j: ES_1 = ... = ES_j = E, the rest 0 -> E sqrt(LH_j / 10) (KR-122)
    nested = [e if k <= j else 0.0 for k in range(5)]
    lh = ima.LIQUIDITY_HORIZONS[j]
    assert ima.es_lh(es_t=nested)["es"] == pytest.approx(e * math.sqrt(lh / 10), rel=1e-14)


@settings(max_examples=200, deadline=None)
@given(
    st.floats(min_value=0, max_value=1e6),
    st.floats(min_value=0, max_value=1e6),
    st.floats(min_value=1e-6, max_value=1e6),
)
def test_es_stressed_floor(rs: float, fc: float, rc: float) -> None:
    es: Any = ima.es_stressed(rs, fc, rc)["es"]
    assert es >= rs


_CHARGES = st.lists(st.floats(min_value=0, max_value=1e6), max_size=20)


@settings(max_examples=200, deadline=None)
@given(
    _CHARGES,
    _CHARGES,
    _CHARGES,
    st.one_of(
        st.just(0.0), st.floats(min_value=1e-100, max_value=1e100)
    ),  # below 1e-154 squares underflow
    st.integers(min_value=0, max_value=2),
)
def test_ses_bounds(a: list[float], b: list[float], c: list[float], x: float, which: int) -> None:
    out: Any = ima.ses(a, b, c)
    rss = math.sqrt(math.fsum(v * v for v in c))
    total = math.fsum(c)
    assert rss * (1 - 1e-12) - 1e-9 <= out["other"] <= total * (1 + 1e-12) + 1e-9
    assert out["ses"] <= math.fsum(a) + math.fsum(b) + total + 1e-6
    lists: list[list[float]] = [[], [], []]
    lists[which] = [x]
    assert ima.ses(*lists)["ses"] == pytest.approx(x, rel=1e-15, abs=0)


@settings(max_examples=100, deadline=None)
@given(st.lists(st.integers(min_value=-30, max_value=400), max_size=60))
def test_rfet_counting_windows(offsets: list[int]) -> None:
    as_of = date(2026, 6, 30)
    obs = [as_of - timedelta(days=k) for k in offsets]
    out = ima.rfet(as_of, obs)
    start = date(2025, 7, 1)
    inside = {d for d in obs if start <= d <= as_of}
    assert out["distinct_days"] == len(inside)
    assert ima.rfet(as_of, obs + obs) == out  # duplicates count once
    counts = []
    s = start
    while s + timedelta(days=89) <= as_of:
        counts.append(sum(1 for d in inside if s <= d <= s + timedelta(days=89)))
        s += timedelta(days=1)
    assert out["min_window_count"] == min(counts)
    assert out["crit1"] == (len(inside) >= 24 and min(counts) >= 4)
    assert out["crit2"] == (len(inside) >= 100)
