"""Stage K wave 1 (PROPOSED, rulings KR-1 to KR-14): every golden row of bt_k, inc_k, trig_k, idr_k,
rich_k and e1_k against the core, the HR-66 error order and the finite rule through the CLI, the
acceptance tests the specs fixed before any run (KR-4 property, incremental-update property on the
hand set and on the stage B production bootstraps, trigger simulation, intraday bound on a seeded
book), and the K-8 method checks that fit a short run (tangent ladder against its own bumps,
G-18 default unchanged). The K-8 convergence acceptance (201/401/801) runs only with
QF_K8_ACCEPTANCE=1; its recorded result is oracle/K8_ACCEPTANCE_W1.json."""

import copy
import json
import math
import os
import random
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from scipy import stats

from quantforge_core import bermudan_k8 as k8
from quantforge_core import stage_k as sk
from quantforge_core.aad_ladder import bermudan_ladder as g18_ladder
from quantforge_core.cli.main import run_case
from quantforge_core.cli.operations import OPERATIONS
from quantforge_core.errors import QfError

ROOT = Path(__file__).resolve().parents[2]
GOLD = ROOT / "datasets" / "golden" / "stage_k"
DAY = 86400
T0 = 1_767_225_600  # 2026-01-01T00:00:00Z


def _gold(name: str) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = json.loads((GOLD / f"{name}.json").read_text("utf-8"))["cases"]
    return cases


def _cli(operation: str, inputs: dict[str, Any]) -> dict[str, Any]:
    doc = {"schema_version": "1.0", "case_id": "k", "operation": operation, "inputs": inputs}
    out: dict[str, Any] = json.loads(json.dumps(run_case(json.dumps(doc))))
    return out


def _code(operation: str, inputs: dict[str, Any]) -> str:
    r = _cli(operation, inputs)
    assert r["status"] == "error", r
    code: str = r["error"]["code"]
    return code


def _err(fn: Any, code: str) -> None:
    with pytest.raises(QfError) as e:
        fn()
    assert e.value.code == code


def _rel(a: float, b: float) -> float:
    return abs(a - b) / max(abs(a), abs(b), 1e-300)


def test_operations_registered() -> None:
    for name in (
        "core.store.bitemporal_query",
        "curve.bootstrap.par_annual",
        "curve.incremental.update",
        "calib.trigger.check",
        "risk.intraday.delta_gamma_bound",
        "num.richardson.check",
    ):
        assert name in OPERATIONS


# --- bitemporal store -----------------------------------------------------------------------------


def _iso(seconds: int) -> str:
    from quantforge_core.cli.inputs import format_seconds

    return format_seconds(seconds, "Z")


def _parse(text: str) -> int:
    from quantforge_core.cli.inputs import parse_instant

    return parse_instant(text, "t")


def _bi(r: dict[str, Any]) -> sk.BiRecord:
    vt = r["valid_to"]
    return sk.BiRecord(
        r["sequence"],
        r["series_id"],
        _parse(r["valid_from"]),
        None if vt is None else _parse(vt),
        _parse(r["knowledge_time"]),
        r["value"],
        r.get("deleted", False),
    )


@pytest.mark.parametrize("case", _gold("bt_k"), ids=lambda c: c["case_id"])
def test_bt_k_rows(case: dict[str, Any]) -> None:
    i = case["inputs"]
    log = [_bi(r) for r in i["records"]]
    k, v = _parse(i["knowledge_as_of"]), _parse(i["valid_at"])
    if case["expected"]["status"] == "error":
        _err(lambda: sk.bitemporal_query(log, i["series_id"], k, v), case["expected"]["error_code"])
        return
    want = case["expected"]["outputs"]
    status, w = sk.bitemporal_query(log, i["series_id"], k, v)
    assert status == want["status"]
    if want["row"] is None:
        assert w is None
    else:
        assert w is not None and w.sequence == want["row"]["sequence"]
        assert w.value == want["row"]["value"] and _iso(w.valid_from) == want["row"]["valid_from"]


def _random_log(rnd: random.Random) -> tuple[list[sk.BiRecord], int]:
    log, kt = [], 0
    for s in range(1, rnd.randint(1, 9)):
        kt += rnd.randint(0, 3) * DAY
        vf = T0 + rnd.randint(0, 20) * DAY
        vt = None if rnd.random() < 0.3 else vf + rnd.randint(1, 10) * DAY
        log.append(
            sk.BiRecord(
                s, rnd.choice("AB"), vf, vt, T0 + kt, rnd.randint(0, 99), rnd.random() < 0.15
            )
        )
    return log, kt


def test_kr4_correction_property_10000_logs() -> None:
    """KR-4 (K-4 acceptance): appending a record known after K never changes a (K, V) answer."""
    rnd = random.Random(20261118)
    checked = 0
    for _ in range(10_000):
        log, kt = _random_log(rnd)
        k = T0 + rnd.randint(0, kt // DAY + 2) * DAY + rnd.choice((0, 43200))
        later = max(T0 + kt, k + 1) + rnd.randint(0, 2) * DAY
        extra = sk.BiRecord(
            len(log) + 1, rnd.choice("AB"), T0 + rnd.randint(0, 20) * DAY, None, later, -1, False
        )
        for vd in range(25):
            v = T0 + vd * DAY
            for series in "AB":
                assert sk.bitemporal_query(log, series, k, v) == sk.bitemporal_query(
                    [*log, extra], series, k, v
                )
                checked += 1
    assert checked == 500_000


def test_bt_withdrawn_masks_and_stage_a_mapping() -> None:
    # KR-2: a deleted winner masks older versions; KR-3: a stage A record is [event, event + 1 s).
    a = sk.BiRecord(1, "A", T0, None, T0, 1, False)
    d = sk.BiRecord(2, "A", T0, None, T0 + DAY, None, True)
    assert sk.bitemporal_query([a, d], "A", T0 + DAY, T0)[0] == "WITHDRAWN"
    assert sk.bitemporal_query([a, d], "A", T0, T0) == ("FOUND", a)
    p = sk.BiRecord(1, "A", T0, T0 + 1, T0, 5, False)
    assert sk.bitemporal_query([p], "A", T0, T0 + 1)[0] == "NONE"


def test_bt_cli_schema_order_and_limit() -> None:
    base = _gold("bt_k")[0]["inputs"]
    bad = copy.deepcopy(base)
    del bad["records"][0]["valid_to"]
    assert _code("core.store.bitemporal_query", bad) == "E_SCHEMA"
    bad = copy.deepcopy(base)
    bad["records"][0]["sequence"] = 0
    assert _code("core.store.bitemporal_query", bad) == "E_SCHEMA"
    # HR-66: a structural E_INPUT (sequence order) before the finite rule's E_DOMAIN
    bad = copy.deepcopy(base)
    bad["records"][1]["sequence"] = 1
    bad["records"][0]["value"] = "NaN"
    assert _code("core.store.bitemporal_query", bad) == "E_INPUT"
    log = [sk.BiRecord(s, "A", T0, None, T0, 0, False) for s in range(1, sk.MAX_RECORDS + 2)]
    _err(lambda: sk.bitemporal_query(log, "A", T0, T0), "E_LIMIT")
    r = _cli("core.store.bitemporal_query", base)
    assert r["outputs"]["row"]["valid_to"] is None


# --- incremental update ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", _gold("inc_k"), ids=lambda c: c["case_id"])
def test_inc_k_rows(case: dict[str, Any]) -> None:
    i = case["inputs"]
    if case["operation"] == "curve.bootstrap.par_annual":
        got = sk.par_annual(i["quotes"])
    else:
        args = (i["previous_quotes"], i["previous_discount_factors"], i["new_quotes"])
        if case["expected"]["status"] == "error":
            _err(lambda: sk.incremental_update(*args), case["expected"]["error_code"])
            return
        got = sk.incremental_update(*args)
        full = sk.par_annual(i["new_quotes"])["discount_factors"]
        assert got["discount_factors"] == full  # bit-identical to a full rebuild (KR-5)
        j = got["first_changed_index"]
        prev = i["previous_discount_factors"]
        assert (
            got["discount_factors"][: len(prev) if j is None else j]
            == prev[: len(prev) if j is None else j]
        )
    want = case["expected"]["outputs"]
    for a, b in zip(got["discount_factors"], want["discount_factors"], strict=True):
        assert abs(a - b) <= 1e-15
    for key in ("first_changed_index", "recomputed"):
        if key in want:
            assert got[key] == want[key]


def test_incremental_property_10000_vectors() -> None:
    rng = np.random.default_rng(20261118)
    for _ in range(10_000):
        n = int(rng.integers(1, 41))
        old = [float(x) for x in rng.uniform(-0.01, 0.08, n)]
        new = list(old)
        for j in rng.choice(n, size=int(rng.integers(1, min(n, 4) + 1)), replace=False):
            new[int(j)] = float(old[int(j)] + rng.normal(0, 0.002))
        prev = sk.par_annual(old)["discount_factors"]
        up = sk.incremental_update(old, prev, new)
        full = sk.par_annual(new)["discount_factors"]
        j0 = up["first_changed_index"]
        assert up["discount_factors"][:j0] == prev[:j0]
        assert all(_rel(a, b) <= 1e-12 for a, b in zip(up["discount_factors"], full, strict=True))
        assert up["recomputed"] == n - j0


def _stage_b_cases() -> list[dict[str, Any]]:
    out = []
    for name in ("ois", "ois_deep", "projection", "projection_deep"):
        doc = json.loads((ROOT / "datasets/golden/stage_b" / f"{name}.json").read_text("utf-8"))
        for c in doc["cases"]:
            i = c["inputs"]
            if (
                c["operation"].endswith(".bootstrap")
                and c["expected"]["status"] == "ok"
                and i.get("method", "SEQUENTIAL") == "SEQUENTIAL"
                and i.get("interpolation", "LOG_LINEAR_DF") == "LOG_LINEAR_DF"
            ):
                out.append(c)
    return out


def _pillars(r: dict[str, Any]) -> list[tuple[str, float]]:
    return [(p["date"], p["discount_factor"]) for p in r["outputs"]["pillars"]]


def test_incremental_property_on_stage_b_bootstraps() -> None:
    """K-4 on the production sequential bootstraps: a quote change at pillar j leaves every
    earlier pillar bit-identical, and a rebuild is deterministic."""
    cases = _stage_b_cases()
    assert len(cases) >= 4
    rnd = random.Random(7)
    tried = 0
    for c in cases:
        base = _cli(c["operation"], c["inputs"])
        assert base["status"] == "ok" and _cli(c["operation"], c["inputs"]) == base
        quotes = c["inputs"]["quotes"]
        rates = [q for q in quotes if "rate" in q]
        if not rates:
            continue
        for _ in range(5):
            inp = copy.deepcopy(c["inputs"])
            j = rnd.randrange(len(inp["quotes"]))
            if "rate" not in inp["quotes"][j]:
                continue
            inp["quotes"][j]["rate"] += rnd.choice((-1, 1)) * 1e-4
            moved = _cli(c["operation"], inp)
            if moved["status"] != "ok":
                continue
            old, new = _pillars(base), _pillars(moved)
            changed = [k for k, (a, b) in enumerate(zip(old, new, strict=True)) if a != b]
            assert changed, c["case_id"]
            first = changed[0]
            assert old[:first] == new[:first]
            tried += 1
    assert tried >= 10


# --- recalibration trigger ------------------------------------------------------------------------


def _trig_args(i: dict[str, Any]) -> tuple[Any, ...]:
    return (i["changes"], i["x_ref"], i["x_now"], i["days_since"], i["k"])


@pytest.mark.parametrize("case", _gold("trig_k"), ids=lambda c: c["case_id"])
def test_trig_k_rows(case: dict[str, Any]) -> None:
    args = _trig_args(case["inputs"])
    if case["expected"]["status"] == "error":
        _err(lambda: sk.trigger_check(*args), case["expected"]["error_code"])
        return
    got, want = sk.trigger_check(*args), case["expected"]["outputs"]
    assert got["fire"] is want["fire"]
    for key in ("sigma", "threshold", "false_alarm_rate"):
        assert _rel(got[key], want[key]) <= 1e-14


def test_trigger_simulation_acceptance() -> None:
    """recalibration-triggers.md: 100,000 noise paths, window 250, k = 3, d = 1; fire rate inside
    the 99% binomial interval of the Student-t predictive rate; a 6-sigma planted move fires on at
    least 99.9% of paths."""
    rng = np.random.default_rng(20261118)
    n, w, k = 100_000, 250, 3.0
    fires = planted = 0
    for block in range(10):
        z = rng.standard_normal((n // 10, w + 1))
        sig = z[:, :w].std(axis=1, ddof=1)
        fires += int(np.sum(np.abs(z[:, w]) > k * sig))
        planted += int(np.sum(6.0 > k * sig))  # a move of exactly 6 true sigma
        if block == 0:  # the operation itself agrees with the vectorised rule on a sample
            for row in range(200):
                r = sk.trigger_check(list(z[row, :w]), 0.0, float(z[row, w]), 1.0, k)
                assert r["fire"] == bool(abs(z[row, w]) > k * sig[row])
    centre = 2 * stats.t.sf(k / math.sqrt(1 + 1 / w), w - 1)
    lo, hi = stats.binom.interval(0.99, n, centre)
    assert lo <= fires <= hi, (fires, lo, hi, centre)
    assert planted >= 0.999 * n


def test_trigger_cli_order() -> None:
    base = _gold("trig_k")[0]["inputs"]
    # HR-66: fewer than two changes (structural E_INPUT) before a non-finite x_now (E_DOMAIN)
    assert _code("calib.trigger.check", dict(base, changes=[1.0], x_now="NaN")) == "E_INPUT"
    assert _code("calib.trigger.check", dict(base, days_since=0.5)) == "E_DOMAIN"
    assert _code("calib.trigger.check", dict(base, changes=[1.0, -1.0] * 50_001)) == "E_LIMIT"
    # E_DOMAIN before E_LIMIT
    assert _code("calib.trigger.check", dict(base, k=-1.0, changes=[1.0, -1.0] * 50_001)) == (
        "E_DOMAIN"
    )


# --- intraday bound -------------------------------------------------------------------------------


def _positions(i: dict[str, Any]) -> list[sk.ZeroPosition]:
    return [sk.ZeroPosition(p["notional"], p["maturity"], p["yield"]) for p in i["positions"]]


@pytest.mark.parametrize("case", _gold("idr_k"), ids=lambda c: c["case_id"])
def test_idr_k_rows(case: dict[str, Any]) -> None:
    i = case["inputs"]
    ps = _positions(i)
    if case["expected"]["status"] == "error":
        _err(lambda: sk.delta_gamma_bound(ps, i["shift"]), case["expected"]["error_code"])
        return
    got, want = sk.delta_gamma_bound(ps, i["shift"]), case["expected"]["outputs"]
    assert got["label"] == want["label"] == sk.LABEL
    assert _rel(got["estimate_pnl"], want["estimate_pnl"]) <= 1e-9
    assert _rel(got["bound"], want["bound"]) <= 1e-9
    assert abs(got["estimate_pnl"] - sk.zero_revalue(ps, i["shift"])) <= got["bound"]


def test_intraday_bound_acceptance_1000_moves() -> None:
    """intraday-risk-bounds.md: a seeded 50-position book, 1,000 moves h ~ U[-0.02, 0.02]:
    |estimate - full revaluation| <= bound on every move."""
    rng = np.random.default_rng(20261118)
    book = [
        sk.ZeroPosition(
            float(rng.uniform(-5e6, 5e6)),
            float(rng.uniform(0.1, 30)),
            float(rng.uniform(-0.01, 0.08)),
        )
        for _ in range(50)
    ]
    worst = 0.0
    for h in rng.uniform(-0.02, 0.02, 1000):
        r = sk.delta_gamma_bound(book, float(h))
        err = abs(r["estimate_pnl"] - sk.zero_revalue(book, float(h)))
        assert err <= r["bound"], (h, err, r["bound"])
        worst = max(worst, err / r["bound"])
    print(f"intraday bound acceptance: 1000 moves, worst |error| / bound = {worst:.6f}")


def test_intraday_cli_order_and_label() -> None:
    i = {"positions": [], "shift": "NaN"}
    assert _code("risk.intraday.delta_gamma_bound", i) == "E_INPUT"  # HR-66
    pos = {"notional": 1.0, "maturity": 1.0, "yield": 0.0}
    assert _code("risk.intraday.delta_gamma_bound", {"positions": [pos], "shift": "NaN"}) == (
        "E_DOMAIN"
    )
    big: dict[str, Any] = {"positions": [pos] * 100_001, "shift": 0.01}
    assert _code("risk.intraday.delta_gamma_bound", big) == "E_LIMIT"
    big["positions"] = [*big["positions"][:-1], dict(pos, maturity=0.0)]
    assert _code("risk.intraday.delta_gamma_bound", big) == "E_DOMAIN"  # before E_LIMIT
    r = _cli("risk.intraday.delta_gamma_bound", {"positions": [pos], "shift": 0.0})
    assert r["outputs"] == {"estimate_pnl": 0.0, "bound": 0.0, "label": sk.LABEL}


# --- Richardson guard -----------------------------------------------------------------------------


@pytest.mark.parametrize("case", _gold("rich_k"), ids=lambda c: c["case_id"])
def test_rich_k_rows(case: dict[str, Any]) -> None:
    i = case["inputs"]
    args = (i["values"], i["ratio"], i["assumed_order"])
    if case["expected"]["status"] == "error":
        _err(lambda: sk.richardson_check(*args), case["expected"]["error_code"])
        return
    got, want = sk.richardson_check(*args), case["expected"]["outputs"]
    assert got["status"] == want["status"]
    for key in ("observed_order", "extrapolated"):
        if want[key] is None:
            assert got[key] is None
        else:
            assert _rel(got[key], want[key]) <= 1e-12


def test_richardson_more() -> None:
    _err(lambda: sk.richardson_check([1.0, 2.0, 3.0], 2.0, 0.0), "E_DOMAIN")
    assert sk.richardson_check([1.0, 1.0, 1.0], 2.0, 2.0)["status"] == "NON_MONOTONE"
    assert _code(
        "num.richardson.check", {"values": [1.0], "ratio": "NaN", "assumed_order": 1.0}
    ) == ("E_INPUT")


# --- E1 (F-2) and the K-8 method ----------------------------------------------------------------


@pytest.mark.parametrize("case", _gold("e1_k"), ids=lambda c: c["case_id"])
def test_e1_k_rows(case: dict[str, Any]) -> None:
    assert _code(case["operation"], case["inputs"]) == "E_DOMAIN"


def _ladder_inputs(index: int) -> dict[str, Any]:
    doc = json.loads((ROOT / "datasets/golden/stage_g/aadladder_g.json").read_text("utf-8"))
    inputs: dict[str, Any] = doc["cases"][index]["inputs"]
    return inputs


def _args(i: dict[str, Any], nx: int, spy: int) -> tuple[Any, ...]:
    c = i["curve"]
    return (
        c["times"], c["discount_factors"], i["mean_reversion"], i["sigma"], False,
        i["start_years"], i["payment_times"], i["fixed_rate"], i["swaption_type"], i["notional"],
        i["exercise_times"], nx, spy, i["grid"]["width"],
    )  # fmt: skip


def test_k8_default_method_is_g18() -> None:
    """KR-8: absent `method` and `G18_IMPLICIT` give the G-18 ladder bit for bit."""
    i = _ladder_inputs(0)
    a = _cli("rates.shortrate.bermudan_ladder", i)
    b = _cli("rates.shortrate.bermudan_ladder", dict(i, method="G18_IMPLICIT"))
    assert a == b and a["outputs"] == g18_ladder(*_args(i, 101, 50))
    assert _code("rates.shortrate.bermudan_ladder", dict(i, method="CN")) == "E_SCHEMA"
    c = _cli("rates.shortrate.bermudan_ladder", dict(i, method=k8.METHOD))
    d = _cli("rates.shortrate.bermudan_swaption", dict(i, method=k8.METHOD))
    assert c["outputs"]["price"] == d["outputs"]["price"]
    assert c["outputs"]["price"] != a["outputs"]["price"]


def test_k8_ladder_equals_its_own_bumps() -> None:
    """bermudan-ladder-k8.md acceptance 5 on a small grid: the derivative of the scheme equals a
    Richardson-extrapolated central bump of the same scheme to 1e-8 relative."""
    i = _ladder_inputs(1)
    nx, spy = 41, 20
    args = list(_args(i, nx, spy))
    lad = k8.bermudan_ladder(*args)

    def price(dfs: list[float], a: float, s: float) -> float:
        b = list(args)
        b[1], b[2], b[3] = dfs, a, s
        return float(k8.bermudan_price(*b)["price"])

    def bump(f: Any, x: float, h: float) -> float:
        d1 = (f(x + h) - f(x - h)) / (2 * h)
        d2 = (f(x + h / 2) - f(x - h / 2)) / h
        return float((4 * d2 - d1) / 3)

    dfs, a, s = list(args[1]), args[2], args[3]
    scale = max(abs(x) for x in lad["d_price_d_discount_factors"])
    for j, want in enumerate(lad["d_price_d_discount_factors"]):

        def f(x: float, j: int = j) -> float:
            d = list(dfs)
            d[j] = x
            return price(d, a, s)

        got = bump(f, dfs[j], 1e-4 * dfs[j])
        assert abs(got - want) <= 1e-8 * scale, (j, got, want)
    for key, x, f2 in (
        ("d_price_d_mean_reversion", a, lambda x: price(dfs, x, s)),
        ("d_price_d_sigma", s, lambda x: price(dfs, a, x)),
    ):
        got = bump(f2, x, 1e-3 * x)
        assert _rel(got, lad[key]) <= 1e-8, (key, got, lad[key])


def test_k8_smoothing_is_a_cell_average() -> None:
    v = np.array([[0.0], [0.0], [0.0]])
    e = np.array([[-1.0], [0.0], [1.0]])
    got = k8._smoothed_max(v, e)[:, 0]
    # node 1: cell [-0.5, 0.5] of max(x, 0) = mean 1/8; node 2: [0.5, 1.5] = 1; node 0: 0
    assert list(got) == [0.0, 0.125, 1.0]


@pytest.mark.skipif(os.environ.get("QF_K8_ACCEPTANCE") != "1", reason="long run (about 40 s)")
def test_k8_acceptance_3_observed_order() -> None:
    """bermudan-ladder-k8.md acceptance 3: on 201/401/801, `num.richardson.check` with assumed order 2
    gives status OK and an observed order in [1.5, 2.5] on the price and every ladder entry that is
    not a structural zero. Recorded result (2026-11-18): FAILS, see oracle/K8_ACCEPTANCE_W1.json."""
    record = json.loads((ROOT / "oracle/K8_ACCEPTANCE_W1.json").read_text("utf-8"))
    bad = []
    for index in range(3):
        i = _ladder_inputs(index)
        rows = []
        for nx, spy in ((201, 100), (401, 200), (801, 400)):
            r = k8.bermudan_ladder(*_args(i, nx, spy))
            rows.append(
                [
                    r["price"],
                    *r["d_price_d_discount_factors"],
                    r["d_price_d_mean_reversion"],
                    r["d_price_d_sigma"],
                ]
            )
        assert rows == record["values"][f"aadladder_g-000{index + 1}"]
        for k in range(len(rows[0])):
            vals = [row[k] for row in rows]
            if vals == [0.0, 0.0, 0.0]:
                continue
            rc = sk.richardson_check(vals, 2.0, 2.0)
            obs = rc["observed_order"]
            if rc["status"] != "OK" or not (obs is not None and 1.5 <= obs <= 2.5):
                bad.append((index, k, rc["status"], obs))
    assert bad == [tuple(b) for b in record["failures"]]
    assert not bad, f"K-8 acceptance 3 fails on {len(bad)} entries (KR-8, K-QB)"
