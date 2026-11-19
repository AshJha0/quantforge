"""Stage K wave 2b: CVA capital (K-8g) and the simplified leverage ratio and large exposures (K-8i).

Specs specifications/06-risk/cva-capital.md and leverage-large-exposures.md; rulings KR-50 to KR-69 and
KR-120 to KR-135. The goldens (oracle/python/gen_stage_k_w2b.py, an independent mpmath oracle that asserts
the 27 blind-matched expected values) are replayed here through the CLI with the verbs registered
locally; the properties are the A2 lists of both specs."""

import importlib.util
import json
import math
import sys
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from quantforge_core import cva, frtb, leverage
from quantforge_core._k_w2b_tables import LEV, LEX, MAR50
from quantforge_core.cli import registry
from quantforge_core.cva import (
    Constituent,
    Counterparty,
    CreditFactor,
    IndexHedge,
    NettingSet,
    Sensitivity,
    SingleNameHedge,
)
from quantforge_core.errors import QfError
from quantforge_core.leverage import (
    BankingBookExposure,
    DerivativeSet,
    LeCounterparty,
    OffBalance,
    OffBalanceExposure,
    Protection,
    Sft,
    TradingPosition,
    WrittenCreditDerivative,
)

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "datasets" / "golden" / "stage_k"
SUITES = ("cva_k", "df_k", "sacva_k", "cva_ke", "sacva_ke", "lev_k", "lex_k", "lev_ke", "lex_ke")


def _load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


RUNNER = _load("qf_runner_w2b", ROOT / "conformance" / "runner" / "runner.py")
CLASSES = RUNNER.load_policy(ROOT / "conformance" / "tolerances" / "policy.yaml")


@pytest.fixture
def cli() -> Any:
    """Local registration (the committed registry is edited by the coordinator at integration)."""
    from quantforge_core.cli import ops_k_w2b  # noqa: F401 - registers the verbs

    for name in ("cva", "leverage"):
        if not hasattr(registry.core, name):
            setattr(registry.core, name, registry._Core(name))
    return registry.execute


def _cases() -> list[dict[str, Any]]:
    out = []
    for name in SUITES:
        out += json.loads((GOLDEN / f"{name}.json").read_text("utf-8"))["cases"]
    return out


CASES = _cases()


def _run(cli: Any, case: dict[str, Any]) -> dict[str, Any]:
    try:
        outputs = json.loads(json.dumps(cli(case["operation"], case["inputs"])))
    except QfError as e:
        return {"case_id": case["case_id"], "status": "error", "error": {"code": e.code}}
    return {"case_id": case["case_id"], "status": "ok", "outputs": outputs}


@pytest.mark.parametrize("case", CASES, ids=[c["case_id"] for c in CASES])
def test_golden(cli: Any, case: dict[str, Any]) -> None:
    status, messages = RUNNER.judge(case, _run(cli, case), CLASSES)
    assert status == "pass", messages


def test_golden_counts_and_provenance() -> None:
    """The 27 blind-matched cases carry the DR-H2 record; every operation has an E1 golden."""
    blind = [c for c in CASES if any("STAGE_K_BLIND_W2.md" in v for v in c["verified_by"])]
    assert len(blind) == 27
    e1 = {c["operation"] for c in CASES if "e1" in c["tags"]}
    assert e1 == {
        "risk.cva.ba",
        "risk.cva.sa",
        "risk.capital.leverage",
        "risk.capital.large_exposures",
    }
    reviewer = {json.loads((GOLDEN / f"{n}.json").read_text("utf-8"))["reviewer"] for n in SUITES}
    assert reviewer == {"none: self-assessment; no second review (owner decision 2026-11-18)"}


def test_tables_equal_json() -> None:
    gen = _load("qf_gen_k_w2b_tables", ROOT / "tools" / "gen_k_w2b_tables.py")
    assert gen.main(["--check"]) == 0
    assert MAR50 == gen.entries("MAR50") and LEV == gen.entries("LEV") and LEX == gen.entries("LEX")


# --- BA-CVA -----------------------------------------------------------------------------------------


def _cp(id_: str, ead: float, m: float, sector: str = "financials", q: str = "IG") -> Counterparty:
    return Counterparty(id_, sector, q, (NettingSet(ead, m),))


def test_discount_factor() -> None:
    assert cva.discount_factor(5) == 0.8847968677143805
    assert cva.discount_factor(2.5, imm=True) == 1.0
    with pytest.raises(QfError) as e:
        cva.discount_factor(0.0)
    assert e.value.code == "E_DOMAIN"


@pytest.mark.parametrize(
    ("kwargs", "field"),
    [
        ({"version": "BASIC"}, "version"),
        ({"counterparties": [Counterparty("A", "space", "IG")]}, "sector"),
        ({"counterparties": [Counterparty("A", "other", "AAA")]}, "quality"),
        ({"single": [SingleNameHedge("A", "COUSIN", "other", "IG", 1, 1)]}, "relation"),
        ({"single": [SingleNameHedge("A", "DIRECT", "space", "IG", 1, 1)]}, "sector"),
        ({"single": [SingleNameHedge("A", "DIRECT", "other", "AAA", 1, 1)]}, "quality"),
        ({"index": [IndexHedge(1, 1, (Constituent("space", "IG", 1),))]}, "sector"),
        ({"index": [IndexHedge(1, 1, (Constituent("other", "AAA", 1),))]}, "quality"),
    ],
)
def test_ba_core_enums(kwargs: dict[str, Any], field: str) -> None:
    """Direct callers of the core get E_SCHEMA for unlisted enums, as the CLI does."""
    with pytest.raises(QfError) as e:
        cva.ba_cva(
            kwargs.get("counterparties", [_cp("A", 1, 1)]),
            kwargs.get("version", "FULL"),
            kwargs.get("single", ()),
            kwargs.get("index", ()),
        )
    assert (e.value.code, e.value.field) == ("E_SCHEMA", field)


finite = st.floats(min_value=0, max_value=1e9, allow_nan=False)
maturity = st.floats(min_value=0.01, max_value=40, allow_nan=False)
sectors = st.sampled_from(cva.SECTORS)
qualities = st.sampled_from(cva.QUALITIES)
netting = st.builds(NettingSet, finite, maturity, st.booleans())
counterparty_lists = st.lists(
    st.tuples(sectors, qualities, st.lists(netting, min_size=1, max_size=3)), min_size=1, max_size=5
).map(lambda xs: [Counterparty(f"C{n}", s, q, tuple(ns)) for n, (s, q, ns) in enumerate(xs)])


def _f(x: object) -> float:
    assert isinstance(x, float)
    return x


def _close(a: float, b: float, rel: float = 1e-12) -> bool:
    return abs(a - b) <= rel * max(abs(a), abs(b), 1.0)


@settings(max_examples=200, deadline=None)
@given(counterparty_lists, st.integers(0, 4), st.floats(1.0, 10.0))
def test_ba_monotone_in_exposure(cps: list[Counterparty], who: int, factor: float) -> None:
    base = cva.ba_cva(cps)
    c = cps[who % len(cps)]
    grown = Counterparty(
        c.id,
        c.sector,
        c.quality,
        tuple(NettingSet(n.ead * factor, n.m, n.imm) for n in c.netting_sets),
    )
    more = cva.ba_cva([grown if x is c else x for x in cps])
    assert _f(more["capital"]) >= _f(base["capital"]) * (1 - 1e-12)


@settings(max_examples=200, deadline=None)
@given(counterparty_lists)
def test_reduced_equals_full_without_hedges(cps: list[Counterparty]) -> None:
    red, full = cva.ba_cva(cps, "REDUCED"), cva.ba_cva(cps, "FULL")
    k = _f(red["k_reduced"])
    assert _close(_f(full["k_hedged"]), k)
    assert _close(_f(full["capital"]), _f(red["capital"]))
    assert full["ih"] == 0.0
    if len(cps) == 1:
        row = red["counterparties"]
        assert isinstance(row, list)
        assert _close(k, row[0]["scva"])


@settings(max_examples=200, deadline=None)
@given(
    counterparty_lists,
    st.lists(st.tuples(st.integers(0, 4), st.sampled_from(tuple(cva.RELATIONS)), sectors,
                       qualities, maturity, finite), max_size=4),
    st.lists(st.tuples(maturity, finite, sectors, qualities), max_size=2),
)  # fmt: skip
def test_full_never_below_beta_floor(
    cps: list[Counterparty], hs: list[Any], ihs: list[Any]
) -> None:
    """K_full >= 0.25 K_reduced (MAR50.20) whatever the hedges, even when an index hedge raises
    K_hedged above K_reduced (A2: K_full <= K_reduced is not asserted)."""
    single = [SingleNameHedge(cps[i % len(cps)].id, r, s, q, m, b) for i, r, s, q, m, b in hs]
    index = [IndexHedge(m, b, (Constituent(s, q, 1.0),)) for m, b, s, q in ihs]
    out = cva.ba_cva(cps, "FULL", single, index)
    k_full, k_red = _f(out["k_full"]), _f(out["k_reduced"])
    assert k_full >= cva.BETA * k_red * (1 - 1e-12)


@settings(max_examples=200, deadline=None)
@given(netting, st.lists(st.tuples(maturity, finite), max_size=3))
def test_direct_hedges_one_counterparty(ns: NettingSet, hs: list[tuple[float, float]]) -> None:
    """One counterparty, IH = 0, only DIRECT hedges: K_hedged = |SCVA - SNH|."""
    c = Counterparty("C", "other", "IG", (ns,))
    single = [SingleNameHedge("C", "DIRECT", "other", "IG", m, b) for m, b in hs]
    out = cva.ba_cva([c], "FULL", single)
    rows = out["counterparties"]
    assert isinstance(rows, list)
    want = abs(rows[0]["scva"] - rows[0]["snh"])
    assert rows[0]["hma"] == 0.0
    assert abs(_f(out["k_hedged"]) - want) <= 1e-9 * max(1.0, rows[0]["scva"])


# --- SA-CVA -----------------------------------------------------------------------------------------


def _ir(bucket: str, tenor: str, c: float, h: float = 0.0) -> Sensitivity:
    return Sensitivity(bucket, tenor, c, h)


def test_sa_core_schema_checks() -> None:
    def code(classes: dict[str, list[Sensitivity]], **kw: Any) -> str:
        with pytest.raises(QfError) as e:
            cva.sa_cva(classes, kw.get("rep", "USD"), kw.get("m", 1.0))
        return e.value.code

    assert code({"IR.GAMMA": []}) == "E_SCHEMA"
    assert code({"IR.DELTA": [_ir("USD", "7Y", 1)]}) == "E_SCHEMA"
    assert code({"CCS.DELTA": [Sensitivity("2", "X", 1, 0)]}) == "E_SCHEMA"
    assert (
        code({"FX.DELTA": [Sensitivity("EUR", CreditFactor("X", "1Y", "IG"), 1, 0)]}) == "E_SCHEMA"
    )
    assert (
        code({"CCS.DELTA": [Sensitivity("2", CreditFactor("X", "1Y", "AA"), 1, 0)]}) == "E_SCHEMA"
    )
    assert (
        code({"CCS.DELTA": [Sensitivity("2", CreditFactor("X", "2Y", "IG"), 1, 0)]}) == "E_SCHEMA"
    )
    assert code({"CCS.VEGA": []}) == "E_INPUT"
    assert code({"IR.DELTA": [_ir("USD", "1Y", 1)]}, m=0.5) == "E_DOMAIN"


def test_sa_empty_and_floored_flag() -> None:
    out = cva.sa_cva({}, "USD")
    assert out["total"] == 0.0 and out["classes"] == {}
    # an IR bucket whose correlation form is negative cannot occur with Table 4, so the flag is
    # checked on the shared radicand directly: KR-62 floors it at 0
    assert frtb.bucket_radicand([(("a",), 1.0), (("b",), -1.0)], lambda a, b: 1.5) < 0


ir_tenors = st.sampled_from(cva.IR_TENORS)
amount = st.floats(-1e7, 1e7, allow_nan=False)


@st.composite
def ir_book(draw: Any) -> dict[str, list[Sensitivity]]:
    out = []
    for ccy in draw(st.lists(st.sampled_from(("USD", "EUR", "JPY", "GBP")), min_size=1,
                             max_size=3, unique=True)):  # fmt: skip
        for t in draw(st.lists(ir_tenors, min_size=1, max_size=4, unique=True)):
            out.append(_ir(ccy, t, draw(amount), draw(amount)))
    return {"IR.DELTA": out}


@settings(max_examples=200, deadline=None)
@given(ir_book(), st.floats(-5, 5, allow_nan=False).filter(lambda c: abs(c) > 1e-3))
def test_sa_bucket_bounds_and_scaling(book: dict[str, list[Sensitivity]], c: float) -> None:
    out = cva.sa_cva(book, "USD")
    cls = out["classes"]
    assert isinstance(cls, dict)
    rows = cls["IR.DELTA"]["buckets"]
    for row in rows:
        members = [s for s in book["IR.DELTA"] if s.bucket == row["bucket"]]
        wsh = [float(MAR50["ir.rw_specified"][s.factor]) * s.s_hdg for s in members]
        assert row["k_b"] >= math.sqrt(cva.R_HEDGE * math.fsum(h * h for h in wsh)) * (1 - 1e-12)
        assert -row["k_b"] <= row["s_b"] <= row["k_b"]
        assert not row["floored"]
    scaled = {"IR.DELTA": [Sensitivity(s.bucket, s.factor, c * s.s_cva, c * s.s_hdg)
                           for s in book["IR.DELTA"]]}  # fmt: skip
    k1, k2 = _f(out["total"]), _f(cva.sa_cva(scaled, "USD")["total"])
    assert abs(k2 - abs(c) * k1) <= 1e-9 * max(1.0, abs(c) * k1)


@settings(max_examples=200, deadline=None)
@given(ir_book(), st.randoms(use_true_random=False))
def test_sa_order_invariance(book: dict[str, list[Sensitivity]], rnd: Any) -> None:
    """Shared with the SBM aggregation: the input order of sensitivities does not change K."""
    items = list(book["IR.DELTA"])
    rnd.shuffle(items)
    a = _f(cva.sa_cva(book, "USD")["total"])
    b = _f(cva.sa_cva({"IR.DELTA": items}, "USD")["total"])
    assert abs(a - b) <= 1e-9 * max(1.0, a)


@settings(max_examples=200, deadline=None)
@given(st.lists(st.tuples(st.sampled_from(("1Y", "5Y", "10Y")), amount), min_size=1, max_size=3,
                unique_by=lambda x: x[0]))  # fmt: skip
def test_sa_bucket_matches_sbm_aggregation(items: list[tuple[str, float]]) -> None:
    """With no hedge, SA-CVA K_b is the SBM K_b of the same weighted sensitivities under the
    medium scenario (one shared radicand, frtb.bucket_radicand)."""
    rw = {t: float(MAR50["ir.rw_specified"][t]) for t, _ in items}
    book = {"IR.DELTA": [_ir("USD", t, s) for t, s in items]}
    k_cva = cva.sa_cva(book, "USD")["classes"]["IR.DELTA"]["buckets"][0]["k_b"]  # type: ignore[index]
    ws: list[tuple[frtb.Factor, float]] = [((t,), rw[t] * s) for t, s in items]
    sbm = frtb.aggregate(
        {"USD": ws},
        lambda b, f, g: cva._ir_rho(str(f[0]), str(g[0])),
        lambda b, c: 0.5,
    )
    k_sbm = sbm["scenarios"]["medium"]["buckets"][0]["k"]  # type: ignore[index]
    assert abs(k_cva - k_sbm) <= 1e-9 * max(1.0, k_sbm)


def test_sa_more_classes_direct() -> None:
    """The one-factor classes and the CCS details, through the core."""
    book = {
        "RCS.DELTA": [Sensitivity("1", "r", 1e5, 0), Sensitivity("8", "r", 1e5, 0)],
        "EQ.VEGA": [Sensitivity("13", "e", 1e3, 0), Sensitivity("4", "e", 1e3, 0)],
        "COM.DELTA": [Sensitivity("11", "c", 1e4, 0), Sensitivity("1", "c", 1e4, 0)],
        "EQ.DELTA": [Sensitivity("12", "e", 1e4, 0), Sensitivity("13", "e", 1e4, 0)],
        "CCS.DELTA": [
            Sensitivity("8", CreditFactor("I", "1Y", "IG", index="CDX", series="S1"), 1e5, 0),
            Sensitivity("8", CreditFactor("I", "5Y", "IG", index="CDX", series="S1"), 1e5, 0),
        ],
    }
    out = cva.sa_cva(book, "USD")
    cls = out["classes"]
    assert isinstance(cls, dict)
    # RCS 1 and 8 share Table 9 row 1/8 with gamma 1, halved across quality: 0.5
    k = cls["RCS.DELTA"]["k"]
    ws = 0.005 * 1e5, 0.02 * 1e5
    assert _close(k, math.sqrt(ws[0] ** 2 + ws[1] ** 2 + 2 * 0.5 * ws[0] * ws[1]))
    # COM 11 with anything: gamma 0
    assert _close(cls["COM.DELTA"]["k"], math.hypot(0.5 * 1e4, 0.3 * 1e4))
    # EQ vega: bucket 4 large cap 78%, bucket 13 other 100%, gamma 45%
    a, b = 0.78 * 1e3, 1e3
    assert _close(cls["EQ.VEGA"]["k"], math.sqrt(a * a + b * b + 2 * 0.45 * a * b))
    # EQ 12 and 13: gamma 75%
    a, b = 0.15 * 1e4, 0.25 * 1e4
    assert _close(cls["EQ.DELTA"]["k"], math.sqrt(a * a + b * b + 2 * 0.75 * a * b))
    # CCS bucket 8, same index and series, two tenors: rho = 0.9 x 1 x 1
    w = 0.015 * 1e5
    assert _close(cls["CCS.DELTA"]["k"], math.sqrt(2 * w * w + 2 * 0.9 * w * w))


# --- leverage ---------------------------------------------------------------------------------------

nonneg = st.floats(0, 1e6, allow_nan=False)
derivs = st.builds(DerivativeSet, st.floats(-1e6, 1e6, allow_nan=False), nonneg, nonneg, nonneg)
wcds = st.builds(WrittenCreditDerivative, nonneg, st.floats(-1e6, 1e6, allow_nan=False), nonneg)
sfts = st.integers(0, 3).flatmap(
    lambda n: st.builds(
        Sft, nonneg, st.booleans(), st.lists(nonneg, min_size=n, max_size=n).map(tuple),
        st.lists(nonneg, min_size=n, max_size=n).map(tuple),
    )
)  # fmt: skip
obs = st.builds(OffBalance, nonneg, st.sampled_from(tuple(leverage.CCF_CATEGORIES)))
parts = st.tuples(
    st.lists(nonneg, max_size=3), st.lists(derivs, max_size=3), st.lists(wcds, max_size=3),
    st.lists(sfts, max_size=3), st.lists(obs, max_size=3),
)  # fmt: skip


def _exposure(p: Any) -> float:
    try:
        return _f(leverage.leverage(1.0, *p)["exposure"])
    except QfError as e:
        assert e.code == "E_DOMAIN"  # exposure measure zero (KR-130)
        return 0.0


@settings(max_examples=300, deadline=None)
@given(parts, parts)
def test_leverage_non_negative_and_additive(a: Any, b: Any) -> None:
    ea, eb = _exposure(a), _exposure(b)
    both = tuple(list(x) + list(y) for x, y in zip(a, b, strict=True))
    assert ea >= 0 and eb >= 0
    assert abs(_exposure(both) - (ea + eb)) <= 1e-9 * max(1.0, ea + eb)


@settings(max_examples=300, deadline=None)
@given(parts, st.integers(0, 4), nonneg)
def test_leverage_monotone(p: Any, which: int, bump: float) -> None:
    """Raising any non-negative input never lowers the exposure measure (A2)."""
    on, ds, ws, ss, os_ = (list(x) for x in p)
    before = _exposure(p)
    if which == 0:
        on.append(bump)
    elif which == 1:
        ds.append(DerivativeSet(0.0, bump))
    elif which == 2:
        ws.append(WrittenCreditDerivative(bump, 0.0))
    elif which == 3:
        ss.append(Sft(bump, False, (bump,), (0.0,)))
    else:
        os_.append(OffBalance(bump, "COMMITMENT"))
    assert _exposure((on, ds, ws, ss, os_)) >= before * (1 - 1e-12)


def test_leverage_boundary_binary64() -> None:
    """meets_minimum is tier1 >= 0.03 x exposure in binary64 (spec)."""
    out = leverage.leverage(3.0, [100.0])
    assert out["meets_minimum"] is (3.0 >= 0.03 * 100.0)
    assert leverage.leverage(2.9, [100.0])["meets_minimum"] is False


def test_leverage_core_enum() -> None:
    with pytest.raises(QfError) as e:
        leverage.leverage(1.0, [1.0], off_balance=[OffBalance(1.0, "GUARANTEE")])
    assert e.value.code == "E_SCHEMA"


# --- large exposures --------------------------------------------------------------------------------


def _le(values: dict[str, float], tier1: float = 1000.0, **kw: Any) -> dict[str, Any]:
    cps = kw.pop("cps", [LeCounterparty(k) for k in values])
    bb = [BankingBookExposure(k, v) for k, v in values.items()]
    out = leverage.large_exposures(tier1, cps, bb, **kw)
    return {g["group"]: g for g in out["groups"]}  # type: ignore[attr-defined]


def test_large_exposure_boundaries() -> None:
    """Large at exactly 10%, no breach at exactly 25% (not higher than), breach just above."""
    g = _le(
        {"A": 100.0, "B": 250.0, "C": math.nextafter(250.0, 1e9), "D": math.nextafter(100.0, 0)}
    )
    assert g["A"]["large"] and not g["A"]["breach"]
    assert g["B"]["large"] and not g["B"]["breach"]
    assert g["C"]["breach"]
    assert not g["D"]["large"]
    gs = _le({"K": 150.0, "J": 151.0}, cps=[LeCounterparty("K", gsib=True), LeCounterparty("J", gsib=True)],
             bank_gsib=True)  # fmt: skip
    assert not gs["K"]["breach"] and gs["J"]["breach"] and gs["J"]["limit"] == 150.0


group_values = st.lists(st.tuples(st.sampled_from("GHI"), nonneg), min_size=1, max_size=8)


@settings(max_examples=300, deadline=None)
@given(group_values)
def test_group_is_sum_of_members(members: list[tuple[str, float]]) -> None:
    cps = [LeCounterparty(f"c{n}", group=g) for n, (g, _) in enumerate(members)]
    bb = [BankingBookExposure(f"c{n}", v) for n, (_, v) in enumerate(members)]
    out = leverage.large_exposures(1000.0, cps, bb)
    rows = {r["id"]: r["exposure"] for r in out["counterparties"]}  # type: ignore[attr-defined]
    for g in out["groups"]:  # type: ignore[attr-defined]
        assert _close(g["exposure"], math.fsum(rows[m] for m in g["members"]))


@settings(max_examples=300, deadline=None)
@given(st.lists(nonneg, min_size=2, max_size=5), st.data())
def test_protection_moves_exposure(values: list[float], data: Any) -> None:
    """Moving protection from counterparty to provider leaves the total unchanged (A2)."""
    ids = [f"c{n}" for n in range(len(values))]
    cps = [LeCounterparty(i) for i in ids]
    bb = [BankingBookExposure(i, v) for i, v in zip(ids, values, strict=True)]
    a = data.draw(st.integers(0, len(ids) - 1))
    b = data.draw(st.integers(0, len(ids) - 1).filter(lambda x: x != a))
    amount = data.draw(st.floats(0, values[a], allow_nan=False))
    plain = leverage.large_exposures(1000.0, cps, bb)
    moved = leverage.large_exposures(1000.0, cps, bb, crm=[Protection(ids[a], ids[b], amount)])

    def total(out: dict[str, object]) -> float:
        return math.fsum(r["exposure"] for r in out["counterparties"])  # type: ignore[attr-defined]

    assert abs(total(plain) - total(moved)) <= 1e-9 * max(1.0, total(plain))


def test_offset_by_seniority() -> None:
    """KR-53: a senior short cannot use a junior long; a junior short can use a senior long."""
    assert leverage.offset_by_seniority([(1, 50.0), (3, -20.0)]) == (50.0, -20.0)
    assert leverage.offset_by_seniority([(3, 50.0), (1, -20.0)]) == (30.0, 0.0)
    assert leverage.offset_by_seniority([]) == (0.0, 0.0)
    assert leverage.offset_by_seniority([(3, 10.0), (3, 10.0), (3, -5.0)]) == (15.0, 0.0)
    assert leverage.offset_by_seniority([(2, 10.0), (4, 10.0), (3, -15.0), (1, -12.0)]) == (
        0.0,
        -7.0,
    )


def test_large_exposures_core_enum_and_jtd() -> None:
    with pytest.raises(QfError) as e:
        leverage.large_exposures(
            1.0, [LeCounterparty("A")], trading_book=[TradingPosition("p", "A", "SUPER", 1, 1)]
        )
    assert e.value.code == "E_SCHEMA"
    assert leverage.jtd(TradingPosition("p", "A", "SENIOR", -10, 5)) == 0.0
    assert leverage.jtd(TradingPosition("p", "A", "SENIOR", 10, -5)) == 0.0
    out = leverage.large_exposures(
        100.0, [LeCounterparty("A")], off_balance=[OffBalanceExposure("A", 50.0, 0.2)]
    )
    assert out["report"] == ["A"]
