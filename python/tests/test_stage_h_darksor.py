"""Stage H wave 2: simulated dark pool (H-12) and smart order router (H-13).

Every golden row of datasets/golden/stage_h/dark_h.json and sor_h.json is replayed against the core
functions; then the paths the goldens do not reach, and the planted-parameter acceptance tests of
specifications/10-execution/dark-pool.md (seeds 20261118 and 20261119, fixed in the spec)."""

import json
import math
from pathlib import Path
from typing import Any

import pytest

from quantforge_core import dark_pool, sor
from quantforge_core.errors import QfError
from quantforge_core.rng import Xoshiro256

ROOT = Path(__file__).resolve().parents[2]
GOLD = ROOT / "datasets" / "golden" / "stage_h"


def _cases(name: str) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = json.loads((GOLD / f"{name}.json").read_text(encoding="utf-8"))["cases"]
    return cases


def _dark(inp: dict[str, Any]) -> dict[str, Any]:
    if "scenarios" in inp:
        return {"scenarios": [dark_pool.run(s["config"], s["events"]) for s in inp["scenarios"]]}
    if "config" in inp:
        return dark_pool.run(inp["config"], inp["events"])
    return dark_pool.markouts(inp["fills"])


def _check(fn: Any, case: dict[str, Any]) -> None:
    exp = case["expected"]
    if exp["status"] == "error":
        with pytest.raises(QfError) as e:
            fn(case["inputs"])
        assert e.value.code == exp["error_code"]
    else:
        assert fn(case["inputs"]) == exp["outputs"]


@pytest.mark.parametrize("case", _cases("dark_h"), ids=lambda c: c["case_id"])
def test_dark_golden(case: dict[str, Any]) -> None:
    _check(_dark, case)


@pytest.mark.parametrize("case", _cases("sor_h"), ids=lambda c: c["case_id"])
def test_sor_golden(case: dict[str, Any]) -> None:
    _check(sor.allocate, case)


# ------------------------------------------------------------------ dark pool paths

CFG = {
    "firm_delay": 0,
    "lot_size": "1",
    "p_firm": "1",
    "penalty_events": 2,
    "seed": 1,
    "tick_size": "0.01",
}
BOOK = {"op": "BOOK", "bid": "100.00", "ask": "100.10"}


def new(oid: str, side: str, qty: str, kind: str = "FIRM", **kw: Any) -> dict[str, Any]:
    return {"op": "NEW", "id": oid, "side": side, "qty": qty, "kind": kind, **kw}


def test_min_qty_equal_qty_crosses_only_on_exact_size() -> None:
    ev = [BOOK, new("B", "BUY", "50", min_qty="50"), new("S", "SELL", "40", min_qty="40")]
    assert dark_pool.run(CFG, ev)["fills"] == []
    ev = [BOOK, new("B", "BUY", "50", min_qty="50"), new("S", "SELL", "50", min_qty="50")]
    assert dark_pool.run(CFG, ev)["fills"][0]["qty"] == "50"


def test_locked_book_and_missing_side_give_no_mid() -> None:
    for book in ({"op": "BOOK", "bid": "100.00", "ask": "100.00"}, {"op": "BOOK", "bid": "100.00"}):
        assert (
            dark_pool.run(CFG, [book, new("B", "BUY", "5"), new("S", "SELL", "5")])["fills"] == []
        )


def test_cancel_removes_and_time_priority() -> None:
    ev = [
        BOOK,
        new("B1", "BUY", "5"),
        new("B2", "BUY", "5"),
        {"op": "CANCEL", "id": "B1"},
        new("S", "SELL", "5"),
    ]
    assert dark_pool.run(CFG, ev)["fills"][0]["buy_id"] == "B2"


def test_firm_delay_holds_then_fills_at_later_mid() -> None:
    cfg = dict(CFG, firm_delay=2)
    ev = [
        BOOK,
        new("C", "BUY", "5", "CONDITIONAL"),
        new("S", "SELL", "5"),
        {"op": "BOOK", "bid": "100.00", "ask": "100.20"},
        {"op": "BOOK", "bid": "100.00", "ask": "100.30"},
    ]
    out = dark_pool.run(cfg, ev)
    assert out["invitations"] == [{"id": "C", "contra_id": "S", "event": 5, "result": "FIRMED"}]
    assert out["fills"][0]["price"] == "100.15"


def test_p_firm_draw_is_seeded_and_deterministic() -> None:
    cfg = dict(CFG, p_firm="0.5", penalty_events=0, seed=7)
    ev = [BOOK, new("C", "BUY", "5", "CONDITIONAL"), new("S", "SELL", "5")] + [BOOK] * 20
    a, b = dark_pool.run(cfg, ev), dark_pool.run(cfg, ev)
    assert a == b and len(a["fills"]) == 1 and a["invitations"][-1]["result"] == "FIRMED"


def test_both_sides_conditional_both_invited() -> None:
    ev = [BOOK, new("C1", "BUY", "5", "CONDITIONAL"), new("C2", "SELL", "5", "CONDITIONAL")]
    out = dark_pool.run(CFG, ev)
    assert [i["id"] for i in out["invitations"]] == ["C1", "C2"] and len(out["fills"]) == 1


@pytest.mark.parametrize(
    "events,code",
    [
        ([{"op": "BOOK", "bid": "100.005", "ask": "100.10"}], "E_DOMAIN"),
        ([new("B", "BUY", "5"), new("B", "BUY", "5")], "E_INPUT"),
        ([{"op": "CANCEL", "id": "X"}], "E_INPUT"),
        ([{"op": "AMEND"}], "E_SCHEMA"),
        ([new("B", "HOLD", "5")], "E_SCHEMA"),
    ],
)
def test_dark_errors(events: list[Any], code: str) -> None:
    with pytest.raises(QfError) as e:
        dark_pool.run(CFG, events)
    assert e.value.code == code


def test_markout_errors() -> None:
    with pytest.raises(QfError):
        dark_pool.markouts([{"side": "BUY", "fill_price": "0", "mid_at": {}}])
    with pytest.raises(QfError):
        dark_pool.markouts([{"side": "BUY", "fill_price": "1", "mid_at": []}])


def test_km_without_censoring_is_the_empirical_tail() -> None:
    obs = [(10, r) for r in (0, 1, 1, 2, 3, 5)]
    est = [t for t, _ in dark_pool.km_tail(obs, 6)]
    emp = [sum(1 for _, r in obs if r >= s) / len(obs) for s in range(1, 7)]
    assert est == pytest.approx(emp)


def test_km_all_censored_above_s_stays_one() -> None:
    assert [t for t, _ in dark_pool.km_tail([(5, 5), (7, 7)], 4)] == [1.0] * 4


# ------------------------------------------------------------------ router paths

SOR3 = _cases("sor_h")[2]["inputs"]  # sor_h-0003, interior case


@pytest.mark.parametrize("k", [0, 1, 2])
def test_closed_form_agrees_with_sample_average(k: int) -> None:
    inp = _cases("sor_h")[k]["inputs"]
    assert sor.allocate(dict(inp, method="CLOSED_FORM")) == sor.allocate(inp)


def test_stochastic_approx_approaches_sample_average() -> None:
    best = sor.allocate(SOR3)
    got = sor.allocate(dict(SOR3, method="STOCHASTIC_APPROX", iterations=20_000, step=1.0, seed=5))
    assert got == best


def test_report_se_adds_se_and_label() -> None:
    out = sor.allocate(dict(SOR3, report_se=True))
    assert out["label"] == sor.LABEL and float(out["expected_cost_se"]) > 0


def test_coordinate_descent_on_large_grid_matches_exhaustive_small() -> None:
    p = sor.Problem(SOR3)
    assert p._descent() == p.sample_average(False)[0]


@pytest.mark.parametrize(
    "patch,code",
    [
        ({"S": "1.5"}, "E_DOMAIN"),
        ({"venues": []}, "E_INPUT"),
        ({"venues": [{"kind": "LIT", "Q": "0", "r": "0", "as": "0"}] * 65}, "E_LIMIT"),
        ({"method": "GREEDY"}, "E_SCHEMA"),
        ({"lit_samples": [["1", "2"]]}, "E_INPUT"),
        ({"venues": [{"kind": "DARK", "r": "0", "as": "0", "tail": ["0.2", "0.5"]}]}, "E_DOMAIN"),
        (
            {
                "method": "CLOSED_FORM",
                "lit_samples": [],
                "venues": [{"kind": "DARK", "r": "0", "as": "0", "tail": []}],
            },
            "E_DOMAIN",
        ),
    ],
)
def test_sor_errors(patch: dict[str, Any], code: str) -> None:
    with pytest.raises(QfError) as e:
        sor.allocate(dict(SOR3, **patch))
    assert e.value.code == code


# ------------------------------------------------------------------ planted recovery (H-4)


def test_planted_fill_probability_recovered_within_3_se() -> None:
    rng = Xoshiro256.seeded(20261118)
    obs = []
    for _ in range(20_000):
        s = min(int(rng.uniform() * 10), 9)
        v = 1 + min(int(rng.uniform() * 10), 9)
        obs.append((v, min(s, v)))
    for s, (est, se) in enumerate(dark_pool.km_tail(obs, 8), start=1):
        assert abs(est - (1 - 0.1 * s)) <= 3 * se, (s, est, se)


def test_planted_leakage_recovered_within_3_se() -> None:
    rng = Xoshiro256.seeded(20261119)
    alpha, jump = 0.3, 0.20
    cfg = dict(CFG, seed=20261119)
    adverse = []
    for _ in range(4_000):
        ours = "BUY" if rng.uniform() < 0.5 else "SELL"
        up = rng.uniform() < 0.5
        informed = rng.uniform() < alpha
        contra = (
            ("BUY" if up else "SELL") if informed else ("BUY" if rng.uniform() < 0.5 else "SELL")
        )
        out = dark_pool.run(cfg, [BOOK, new("U", ours, "100"), new("X", contra, "100")])
        if not out["fills"]:
            continue
        px = out["fills"][0]["price"]
        mid = f"{float(px) + (jump if up else -jump):.3f}"
        bp = dark_pool.markouts([{"side": ours, "fill_price": px, "mid_at": {"1": mid}}])
        adverse.append(-float(bp["fills"][0]["markouts_bp"]["1"]) * float(px) / 10_000)
    n = len(adverse)
    mean = sum(adverse) / n
    se = math.sqrt(sum((a - mean) ** 2 for a in adverse) / (n - 1) / n)
    assert abs(mean - alpha * jump) <= 3 * se, (mean, se, n)


@pytest.mark.parametrize("k", [0, 1, 2, 3, 4])
def test_stochastic_approx_reaches_sample_average_optimum_on_every_golden(k: int) -> None:
    """Spec convergence row: the averaged iterate approaches the SAMPLE_AVERAGE optimum. sor_h-0002
    has a flat cost region in L (theta = 0); before the polish the iterate stopped at L = 5,
    cost 8.15 against 8."""
    inp = {key: v for key, v in _cases("sor_h")[k]["inputs"].items() if key != "ranking"}
    best = sor.allocate(inp)
    for n in (1_000, 10_000):
        got = sor.allocate(dict(inp, method="STOCHASTIC_APPROX", iterations=n, step=1.0, seed=3))
        assert got == best, (k, n)
