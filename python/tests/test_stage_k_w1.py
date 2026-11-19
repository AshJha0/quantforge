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
from collections import Counter
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


def _evidence(key: str, value: Any) -> None:
    """Acceptance evidence: when QF_K_EVIDENCE names a file, the acceptance tests record their results there
    (program/stage_k_w1/acceptance_python.json is written this way)."""
    path = os.environ.get("QF_K_EVIDENCE")
    if not path:
        return
    p = Path(path)
    doc = json.loads(p.read_text("utf-8")) if p.exists() else {}
    doc[key] = value
    p.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", "utf-8", newline="\n")


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
    _evidence(
        "kr4_correction_property",
        {
            "logs": 10_000,
            "queries_compared": checked,
            "failures": 0,
            "seed": "random.Random(20261118)",
        },
    )


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
    worst, bit_equal = 0.0, 0
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
        worst = max(
            [worst] + [_rel(a, b) for a, b in zip(up["discount_factors"], full, strict=True)]
        )
        bit_equal += up["discount_factors"] == full
    _evidence(
        "incremental_property",
        {
            "vectors": 10_000,
            "max_relative_difference": worst,
            "bit_identical_to_full_rebuild": bit_equal,
            "copied_pillars_bit_identical": True,
            "seed": "numpy default_rng(20261118)",
        },
    )


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
            # quotes are in maturity order, one pillar per quote, so quote j is pillar j: a change at j
            # leaves pillars 0..j-1 bit-identical and moves pillar j (K-4 on the production bootstrap)
            assert len(old) == len(quotes) and [d for d, _ in old] == sorted(d for d, _ in old)
            changed = [k for k, (a, b) in enumerate(zip(old, new, strict=True)) if a != b]
            assert changed and changed[0] == j, (c["case_id"], j, changed)
            assert old[:j] == new[:j]
            tried += 1
    assert tried >= 10
    _evidence(
        "incremental_property_stage_b",
        {
            "stage_b_cases": len(cases),
            "quote_changes_checked": tried,
            "earlier_pillars_bit_identical": True,
            "rebuild_deterministic": True,
        },
    )


# --- K-4b on the stage B production bootstrap: patched against rebuilt ----------------------------

_SEQ = ("LOG_LINEAR_DF", "LINEAR_ZERO")


def _stage_b_sets() -> list[tuple[str, dict[str, Any]]]:
    """Every sequential stage B bootstrap instrument set: the SEQUENTIAL OIS goldens of stage B (rate
    and bid/ask quotes, both stage B interpolations), the SEQUENTIAL OIS goldens with jumps of stage D
    (ois_d), and the projection goldens (deposits, FRAs, swaps) in both stage B interpolations."""
    out = []
    for folder, name in (
        ("stage_b", "ois"),
        ("stage_b", "projection"),
        ("stage_b", "projection_deep"),
        ("stage_d", "ois_d"),
    ):
        doc = json.loads((ROOT / "datasets/golden" / folder / f"{name}.json").read_text("utf-8"))
        for c in doc["cases"]:
            i = c["inputs"]
            if not (c["operation"].endswith(".bootstrap") and c["expected"]["status"] == "ok"):
                continue
            if i.get("method", "SEQUENTIAL") != "SEQUENTIAL" or i.get("interpolation") not in _SEQ:
                continue
            if any(k in i for k in ("tension", "step_end")):
                continue
            out.append((c["case_id"], i))
            if c["operation"] == "rates.projection.bootstrap":
                out.append((c["case_id"] + "/LINEAR_ZERO", dict(i, interpolation="LINEAR_ZERO")))
    return out


def _op_of(i: dict[str, Any]) -> str:
    return "rates.ois.bootstrap" if "convention" in i else "rates.projection.bootstrap"


def _b_quotes(i: dict[str, Any], raw: list[dict[str, Any]]) -> list[Any]:
    from quantforge_core.cli.inputs import Inputs
    from quantforge_core.cli.ops_rates import projection_quote
    from quantforge_core.cli.readers import _objects, _quotes

    v = Inputs(dict(i, quotes=raw))
    if _op_of(i) == "rates.ois.bootstrap":
        return _quotes(v)
    return [projection_quote(q) for q in _objects(v, "quotes")]


def _b_solve(i: dict[str, Any], quotes: list[Any]) -> tuple[Any, float]:
    from quantforge_core import ois, projection
    from quantforge_core.cli.inputs import Inputs
    from quantforge_core.cli.ops_rates import index
    from quantforge_core.cli.readers import _curve, jumps

    v = Inputs(i)
    interp = v.string("interpolation")
    if _op_of(i) == "rates.ois.bootstrap":
        conv = v.string("convention")
        return ois.bootstrap(conv, v.date("as_of"), quotes, interp, "SEQUENTIAL", jumps(v))
    return projection.bootstrap(_curve(v, "discount"), index(v), v.date("as_of"), quotes, interp)


def _b_incremental(i: dict[str, Any], prev: list[Any], factors: Any, new: list[Any]) -> Any:
    from quantforge_core import ois, projection
    from quantforge_core.cli.inputs import Inputs
    from quantforge_core.cli.ops_rates import index
    from quantforge_core.cli.readers import _curve, jumps

    v = Inputs(i)
    interp, as_of = v.string("interpolation"), v.date("as_of")
    if _op_of(i) == "rates.ois.bootstrap":
        conv = v.string("convention")
        return ois.bootstrap_incremental(conv, as_of, prev, factors, new, interp, jumps(v))
    disc = _curve(v, "discount")
    return projection.bootstrap_incremental(disc, index(v), as_of, prev, factors, new, interp)


def _shift(q: dict[str, Any], d: float) -> dict[str, Any]:
    q = dict(q)
    if "rate" in q:
        q["rate"] += d
    else:
        q["bid"] += d
        q["ask"] += d
    return q


Move = tuple[str, str, list[dict[str, Any]], list[dict[str, Any]]]


def _b_moves(n_total: int, seed: int) -> list[Move]:
    """(set id, kind, previous quotes, new quotes). Fixed part per set: no change, every single
    pillar (the first, each middle one, the last), first and last together, all pillars. Random
    part up to n_total: a random previous vector (each quote moved by up to 50 bp with probability
    1/2), then 1 to n quotes moved by up to 25 bp each; the kind names how many quotes moved and
    where the first change falls."""
    sets = _stage_b_sets()
    rnd = random.Random(seed)
    out: list[Move] = []
    bp = 1e-4
    for sid, i in sets:
        base = i["quotes"]
        n = len(base)
        out.append((sid, "none", base, base))
        for j in range(n):
            kind = "single_first" if j == 0 else "single_last" if j == n - 1 else "single_middle"
            out.append(
                (sid, kind, base, [_shift(q, bp) if k == j else q for k, q in enumerate(base)])
            )
        both = [_shift(q, -bp) if k in (0, n - 1) else q for k, q in enumerate(base)]
        out.append((sid, "multi_first_and_last", base, both))
        out.append((sid, "multi_all", base, [_shift(q, 2 * bp) for q in base]))
    while len(out) < n_total:
        sid, i = sets[rnd.randrange(len(sets))]
        base = i["quotes"]
        n = len(base)
        prev = [
            _shift(q, rnd.uniform(-50 * bp, 50 * bp)) if rnd.random() < 0.5 else q for q in base
        ]
        idx = sorted(rnd.sample(range(n), rnd.randint(1, n)))
        new = list(prev)
        for k in idx:
            new[k] = _shift(prev[k], rnd.choice((-1, 1)) * rnd.uniform(0.01 * bp, 25 * bp))
        where = "first" if idx[0] == 0 else "last" if idx[0] == n - 1 else "middle"
        out.append((sid, ("multi_" if len(idx) > 1 else "single_") + where, prev, new))
    return out


def test_incremental_update_on_stage_b_bootstrap_equals_rebuild() -> None:
    """K-4b acceptance on the stage B production bootstrap (incremental-update.md, Acceptance, third
    line; KR-5): on 10,000 quote moves over every sequential stage B instrument set, the incremental
    path equals a full rebuild to 1e-12 relative, and copied pillars are bit-identical to the cache."""
    sets = dict(_stage_b_sets())
    moves = _b_moves(10_000, 20261119)
    assert len(moves) == 10_000
    worst, bit_equal, kinds = 0.0, 0, Counter[str]()
    for sid, kind, prev_raw, new_raw in moves:
        i = sets[sid]
        prev, new = _b_quotes(i, prev_raw), _b_quotes(i, new_raw)
        cache, _ = _b_solve(i, prev)
        patched, err, first, recomputed = _b_incremental(i, prev, cache.discount_factors, new)
        full, full_err = _b_solve(i, new)
        n = len(new_raw)
        want = next((k for k in range(n) if prev_raw[k] != new_raw[k]), None)
        assert first == want and recomputed == (0 if want is None else n - want), (sid, kind)
        j = n if want is None else want
        assert patched.discount_factors[:j] == cache.discount_factors[:j], (sid, kind)
        assert patched.dates == full.dates
        for a, b in zip(patched.discount_factors, full.discount_factors, strict=True):
            rel = _rel(a, b)
            worst = max(worst, rel)
            assert rel <= 1e-12, (sid, kind, a, b)
        bit_equal += patched.discount_factors == full.discount_factors and err == full_err
        kinds[kind] += 1
    _evidence(
        "incremental_property_stage_b_patched",
        {
            "cases": len(moves),
            "instrument_sets": sorted(sets),
            "kinds": dict(sorted(kinds.items())),
            "max_relative_difference": worst,
            "bit_identical_to_full_rebuild": bit_equal,
            "copied_pillars_bit_identical": True,
            "seed": "random.Random(20261119)",
        },
    )
    assert bit_equal == len(moves)


def test_incremental_stage_b_errors_and_tenor_change() -> None:
    import dataclasses

    from quantforge_core import ois
    from quantforge_core.errors import QfError

    sets = _stage_b_sets()
    i = next(i for _, i in sets if _op_of(i) == "rates.ois.bootstrap")
    q = _b_quotes(i, i["quotes"])
    cache, _ = _b_solve(i, q)
    f = list(cache.discount_factors)
    stale = [*f[:-1], math.nextafter(f[-1], 1.0)]
    for bad in (
        lambda: _b_incremental(i, q, stale, q),
        lambda: _b_incremental(i, q, f, q[:-1]),
        lambda: _b_incremental(i, q, f[:-1], q),
        lambda: ois.bootstrap_incremental(i["convention"], cache.as_of, q, f, q, "MONOTONE_CONVEX"),
    ):
        with pytest.raises(QfError) as e:
            bad()
        assert e.value.code == "E_INPUT"
    # a changed tenor is a changed instrument: its pillar and every later one are solved again
    assert q[-1].tenor == "30Y"
    longer = [*q[:-1], dataclasses.replace(q[-1], tenor="25Y")]
    _, _, first, recomputed = _b_incremental(i, q, f, longer)
    assert (first, recomputed) == (len(q) - 1, 1)
    p = next(i for _, i in sets if _op_of(i) == "rates.projection.bootstrap")
    pq = _b_quotes(p, p["quotes"])
    pc, _ = _b_solve(p, pq)
    with pytest.raises(QfError) as e:
        _b_incremental(p, pq, [*pc.discount_factors[:-1], 0.5], pq)
    assert e.value.code == "E_INPUT"
    swapped = [pq[1], pq[0], *pq[2:]]
    with pytest.raises(QfError) as e:
        _b_incremental(p, pq, pc.discount_factors, swapped)
    assert e.value.code == "E_INPUT"


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


def test_false_alarm_rate_is_twice_the_normal_tail() -> None:
    """KR-6 states 2 (1 - Phi(k)); at k = 30 a bare erfc(k / sqrt 2) is 1.2e-13 off (trig_k-0009, mpmath)."""
    far = sk.trigger_check([1.0, -1.0, 1.0, -1.0], 100.0, 105.0, 1.0, 30.0)["false_alarm_rate"]
    assert _rel(far, 9.813427854296374e-198) <= 1e-14
    # the form not used: a bare erfc(k / sqrt 2)
    assert _rel(math.erfc(30.0 / math.sqrt(2.0)), 9.813427854296374e-198) > 1e-14
    assert sk.two_sided_normal_tail(3.0) == pytest.approx(0.002699796063260189, rel=1e-15)


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
    _evidence(
        "trigger_simulation",
        {
            "paths": n,
            "window": w,
            "k": k,
            "fires": fires,
            "centre_rate": centre,
            "binomial_99_interval": [lo, hi],
            "planted_6_sigma_fires": planted,
            "planted_rate": planted / n,
            "seed": "numpy default_rng(20261118)",
            "pass": bool(lo <= fires <= hi and planted >= 0.999 * n),
        },
    )
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
    moves = []
    for h in rng.uniform(-0.02, 0.02, 1000):
        r = sk.delta_gamma_bound(book, float(h))
        full = sk.zero_revalue(book, float(h))
        err = abs(r["estimate_pnl"] - full)
        moves.append([float(h), r["estimate_pnl"], full, r["bound"]])
        assert err <= r["bound"], (h, err, r["bound"])
        worst = max(worst, err / r["bound"])
    _evidence(
        "intraday_bound_1000_moves",
        {
            "book": [[p.notional, p.maturity, p.yield_] for p in book],
            "seed": "numpy default_rng(20261118)",
            "columns": ["h", "estimate_pnl", "full_revaluation", "bound"],
            "moves": moves,
            "violations": 0,
            "worst_error_over_bound": worst,
            "min_abs_h": min(abs(m[0]) for m in moves),
        },
    )
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


def test_k8_smoothing_worked_example() -> None:
    """bermudan-ladder-k8.md step 5, worked example: f = (-1, 0, 1)."""
    v = np.array([[0.0], [0.0], [0.0]])
    e = np.array([[1.0], [0.0], [-1.0]])
    got = k8._smoothed_max(v, e)[:, 0]
    assert got[0] == 1.0 and got[2] == 0.0  # E where f < 0 around the node, V where f > 0
    assert abs(got[1] - 1 / 18) <= 1e-16


def test_k8_smoothing_keeps_the_pointwise_max_away_from_the_crossing() -> None:
    """Step 5: with a cubic V and E = 0, nodes two or more cells inside V > 0 keep V (the stencil
    cancels the hat average of a cubic exactly), nodes inside V < 0 get E, and the end correction
    acts only on the two nodes of the crossing cell."""
    x = np.linspace(-1.0, 1.0, 41)
    f = (x - 0.013) * (1 + 0.3 * x + 0.2 * x * x)
    got = k8._smoothed_max(f[:, None].copy(), np.zeros((41, 1)))[:, 0]
    j = int(np.nonzero(f > 0)[0][0])
    assert np.allclose(got[j + 2 : -2], f[j + 2 : -2], rtol=0, atol=1e-14)
    assert np.all(got[: j - 2] == 0.0)
    assert np.all(got[j - 2 : j + 2] != np.maximum(f, 0)[j - 2 : j + 2])


def test_k8_hat_part_closed_form() -> None:
    """`M(p, q)` against a fine midpoint sum, on the four branches and at their joins."""
    u = (np.arange(200_000) + 0.5) / 200_000
    for p, q in (
        (1.0, 2.0),
        (1.0, -0.5),
        (-0.5, 1.0),
        (-1.0, -2.0),
        (0.0, 1.0),
        (1.0, 0.0),
        (0.0, -1.0),
    ):
        want = float(np.mean((1 - u) * np.maximum(p + (q - p) * u, 0.0)))
        got = float(k8._hat_part(np.array([[p]]), np.array([[q]]))[0, 0])
        assert abs(got - want) <= 1e-9, (p, q, got, want)


def test_k8_curve_nodes_the_price_does_not_depend_on_give_exact_zeros() -> None:
    """KR-18 a: the node at 0.4986 years sits inside a time step and before the first exercise date
    (1.0, itself a node); the model price does not depend on it and neither does the scheme. The
    version 0.1.0 scheme gave -337 here at 201/100."""
    for index in range(3):
        lad = k8.bermudan_ladder(*_args(_ladder_inputs(index), 41, 20))
        d = lad["d_price_d_discount_factors"]
        assert d[0] == 0.0 and d[6:] == [0.0, 0.0, 0.0, 0.0]
        assert all(x != 0.0 for x in d[1:6])


def _row(i: dict[str, Any], nx: int, spy: int) -> list[float]:
    r = k8.bermudan_ladder(*_args(i, nx, spy))
    return [
        r["price"],
        *r["d_price_d_discount_factors"],
        r["d_price_d_mean_reversion"],
        r["d_price_d_sigma"],
    ]


K8_JUDGED = (0, 2, 3, 4, 5, 6, 11, 12)


def test_k8_time_order_is_two_on_every_entry() -> None:
    """Time-only refinement (41 nodes; 10, 20, 40 steps a year): observed order 2 on the price and
    every ladder entry. Version 0.1.0 gave order 1.00 on the two entries next to the 0.4986 node."""
    i = _ladder_inputs(0)
    rows = [_row(i, 41, spy) for spy in (10, 20, 40)]
    for k in K8_JUDGED:
        rc = sk.richardson_check([r[k] for r in rows], 2.0, 2.0)
        assert rc["status"] == "OK" and abs(rc["observed_order"] - 2.0) <= 0.1, (k, rc)


def test_k8_space_error_is_smooth_second_order() -> None:
    """Space-only refinement on grids that are NOT nested (60, 80, 100, 130, 160 cells against 320):
    the error times `cells^2` is the same on every grid to 10% for the price and every entry. This is
    the property the cell average of version 0.1.0 lacked (the exercise boundary sits at a different
    place in its cell on each grid; there the scaled error varied by a factor of 4)."""
    i = _ladder_inputs(0)
    ref = _row(i, 321, 20)
    scaled = []
    for nx in (61, 81, 101, 131, 161):
        r = _row(i, nx, 20)
        c2 = float((nx - 1) ** 2)
        scaled.append([(r[k] - ref[k]) * c2 / (1 - c2 / 320.0**2) for k in K8_JUDGED])
    for col in zip(*scaled, strict=True):
        mean = sum(col) / len(col)
        assert max(abs(x - mean) for x in col) <= 0.1 * abs(mean), col


@pytest.mark.parametrize("case", _gold("k8_k"), ids=lambda c: c["case_id"])
def test_k8_k_rows(case: dict[str, Any]) -> None:
    """Shared goldens of the K-8 method: values at 1e-9 of the row scale, error codes exactly."""
    got = _cli(case["operation"], case["inputs"])
    want = case["expected"]
    assert got["status"] == want["status"], got
    if want["status"] == "error":
        assert got["error"]["code"] == want["error_code"]
        return
    w, g = want["outputs"], got["outputs"]
    assert w.keys() == g.keys()
    assert _rel(g["price"], w["price"]) <= 1e-9
    if "d_price_d_discount_factors" in w:
        scale = max(abs(x) for x in w["d_price_d_discount_factors"])
        for x, y in zip(
            g["d_price_d_discount_factors"], w["d_price_d_discount_factors"], strict=True
        ):
            assert abs(x - y) <= 1e-9 * scale
        for key in ("d_price_d_mean_reversion", "d_price_d_sigma"):
            assert _rel(g[key], w[key]) <= 1e-9


def test_k8_k_price_and_ladder_agree() -> None:
    rows = {c["case_id"]: c for c in _gold("k8_k")}
    a, b = rows["k8_k-0001"]["expected"]["outputs"], rows["k8_k-0004"]["expected"]["outputs"]
    assert a["price"] == b["price"]


@pytest.mark.skipif(os.environ.get("QF_K8_ACCEPTANCE") != "1", reason="long run (about 4 min)")
def test_k8_acceptance_3_observed_order() -> None:
    """bermudan-ladder-k8.md acceptance 3: on 201/401/801, `num.richardson.check` with assumed order 2
    gives status OK and an observed order in [1.5, 2.5] on the price and every ladder entry that is
    not exactly zero on all three grids. First run (version 0.1.0, 2026-11-18): FAILED on 18 entries,
    kept in oracle/K8_ACCEPTANCE_W1.json. Second run (KR-18, 2026-11-19): oracle/K8_ACCEPTANCE_W2.json."""
    first = json.loads((ROOT / "oracle/K8_ACCEPTANCE_W1.json").read_text("utf-8"))
    assert len(first["failures"]) == 18  # the recorded first run stays a recorded miss
    record = json.loads((ROOT / "oracle/K8_ACCEPTANCE_W2.json").read_text("utf-8"))
    bad = []
    for index in range(3):
        i = _ladder_inputs(index)
        rows = [_row(i, nx, spy) for nx, spy in ((201, 100), (401, 200), (801, 400))]
        want = record["values"][f"aadladder_g-000{index + 1}"]
        for got_row, want_row in zip(
            rows, [want[g] for g in ("201/100", "401/200", "801/400")], strict=True
        ):
            scale = max(abs(x) for x in want_row[1:11])
            for k, (g, w) in enumerate(zip(got_row, want_row, strict=True)):
                assert abs(g - w) <= 1e-9 * (scale if 1 <= k <= 10 else abs(w)), (index, k, g, w)
        for k in range(len(rows[0])):
            vals = [row[k] for row in rows]
            if vals == [0.0, 0.0, 0.0]:
                continue
            rc = sk.richardson_check(vals, 2.0, 2.0)
            obs = rc["observed_order"]
            if rc["status"] != "OK" or not (obs is not None and 1.5 <= obs <= 2.5):
                bad.append((index, k, rc["status"], obs))
    assert not bad, f"K-8 acceptance 3 fails on {len(bad)} entries (KR-8, K-QB)"
