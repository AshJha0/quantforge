"""Stage H H-4b microstructure estimators and H-16 venue analytics.

Every golden row of datasets/golden/stage_h/mest_h.json and venue_h.json is replayed through the CLI
operation table; then the paths the goldens do not reach, the venue property tests, and the seven
planted-recovery tests and the 200-seed coverage run exactly as
specifications/09-microstructure/micro-estimators.md fixes them (seeds 20261118 + j and
70000..70199, 3 SE, at most 4 misses; HR-70, HR-71). Seeds and bounds are never changed after a run."""

import json
import math
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from quantforge_core import micro_est, venue_analytics
from quantforge_core.cli.operations import execute
from quantforge_core.errors import QfError

ROOT = Path(__file__).resolve().parents[2]
GOLD = ROOT / "datasets" / "golden" / "stage_h"


def _cases(name: str) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = json.loads((GOLD / f"{name}.json").read_text(encoding="utf-8"))[
        "cases"
    ]
    return cases


def _close(a: Any, e: Any, path: str, ab: float = 1e-15) -> None:
    if isinstance(e, dict):
        assert set(a) == set(e), path
        for k in e:
            _close(a[k], e[k], f"{path}.{k}", ab)
    elif isinstance(e, list):
        assert len(a) == len(e), path
        for k, (x, y) in enumerate(zip(a, e, strict=True)):
            _close(x, y, f"{path}[{k}]", ab)
    elif isinstance(e, float):
        assert abs(a - e) <= ab + 1e-12 * max(abs(a), abs(e)), (path, a, e)
    else:
        assert a == e, path


@pytest.mark.parametrize("case", _cases("mest_h") + _cases("venue_h"), ids=lambda c: c["case_id"])
def test_golden(case: dict[str, Any]) -> None:
    exp = case["expected"]
    inputs = json.loads(json.dumps(case["inputs"]))
    if exp["status"] == "error":
        with pytest.raises(QfError) as e:
            execute(case["operation"], inputs)
        assert e.value.code == exp["error_code"]
    else:
        ab = case.get("tolerance_limit", {}).get("absolute", 1e-15)
        _close(execute(case["operation"], inputs), exp["outputs"], case["case_id"], ab)


# ------------------------------------------------------------------ paths the goldens miss


def _code(fn: Callable[[], Any]) -> str:
    with pytest.raises(QfError) as e:
        fn()
    return e.value.code


def test_estimator_errors() -> None:
    me = micro_est
    assert _code(lambda: me.arrival_rate(-1, 1.0)) == "E_DOMAIN"
    assert me.arrival_rate(0, 2.0) == {"lambda": 0.0, "se": 0.0}
    assert _code(lambda: me.cancel_rate([(0.0, "CANCEL")])) == "E_DOMAIN"
    assert _code(lambda: me.resilience(1.0, [(0, 2.0), (0, 3.0), (0, 4.0)])) == "E_INPUT"
    assert _code(lambda: me.resilience(1.0, [(0, 2.0), (1, 0.5), (2, 4.0)])) == "E_DOMAIN"
    assert _code(lambda: me.liquidity_decay([(0, 1.0), (1, 0.0), (2, 1.0)])) == "E_DOMAIN"
    assert _code(lambda: me.liquidity_decay([(0, 1.0), (1, 0.0)])) == "E_INPUT"  # HR-66
    assert _code(lambda: me.adverse_selection([1.0], [1.0, 2.0])) == "E_INPUT"
    assert _code(lambda: me.adverse_selection([0.0, 0.0], [1.0, 2.0])) == "E_INPUT"
    good = ([1.0, 2.0], [1.0, 2.0])
    assert _code(lambda: me.regime_impact({"calm": good})) == "E_INPUT"
    assert _code(lambda: me.regime_impact({"calm": good, "stressed": ([1.0], [1.0])})) == "E_INPUT"
    zero = ([1.0, -1.0], [1.0, 1.0])
    assert _code(lambda: me.regime_impact({"calm": zero, "stressed": good})) == "E_DOMAIN"
    assert _code(lambda: me.passive_vs_aggressive([1.0, 2.0], [1.0])) == "E_INPUT"


def test_cli_schema_and_nonfinite() -> None:
    assert (
        _code(lambda: execute("micro.est.arrival_rate", {"count": 1.5, "window": 1.0}))
        == "E_SCHEMA"
    )
    bad = {"orders": [{"lifetime": 1.0, "outcome": "EXPIRE"}]}
    assert _code(lambda: execute("micro.est.cancel_rate", bad)) == "E_SCHEMA"
    assert (
        _code(
            lambda: execute(
                "micro.est.passive_vs_aggressive",
                {"passive": [1.0, "Infinity"], "aggressive": [1.0, 2.0]},
            )
        )
        == "E_DOMAIN"
    )
    with pytest.raises(QfError) as e:
        micro_est.adverse_selection([math.nan, 1.0], [1.0, 1.0])
    assert e.value.code == "E_DOMAIN"


BASE = _cases("venue_h")[0]["inputs"]


def _venue(inp: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = execute("exec.venue.analytics", json.loads(json.dumps(inp)))
    return out


def test_venue_errors() -> None:
    def code(**kw: Any) -> str:
        return _code(lambda: _venue({**BASE, **kw}))

    mids = BASE["mids"]
    assert code(mids=[mids[1], mids[0]]) == "E_INPUT"
    assert code(mids=[{"t": 0.0, "mid": 0.0}]) == "E_DOMAIN"
    f = BASE["fills"][0]
    assert code(fills=[{**f, "price": 0.0}]) == "E_DOMAIN"
    assert code(fills=[{**f, "quantity": -1.0}]) == "E_DOMAIN"
    assert code(orders=[{"venue": "A", "sent": 0.0, "filled": 0.0}]) == "E_DOMAIN"
    assert code(orders=[{"venue": "A", "sent": 1.0, "filled": -1.0}]) == "E_DOMAIN"
    assert code(fills=[{**f, "side": "HOLD"}]) == "E_SCHEMA"
    out = _venue({**BASE, "fills": [], "orders": []})
    assert out == {"fill_rates": {}, "markouts": []}


@pytest.mark.parametrize("h", [0.0, 0.5, 1.0, 4.0, 5.0, 9.0, 10.0, 100.0])
def test_venue_properties(h: float) -> None:
    out = _venue({**BASE, "horizons": [h]})
    c = 120.0
    flip = {
        **BASE,
        "horizons": [h],
        "mids": [{**m, "mid": 2 * c - m["mid"]} for m in BASE["mids"]],
        "fills": [
            {**f, "side": "SELL" if f["side"] == "BUY" else "BUY", "price": 2 * c - f["price"]}
            for f in BASE["fills"]
        ],
    }
    out2 = _venue(flip)
    for r, r2 in zip(out["markouts"], out2["markouts"], strict=True):
        assert 0.0 <= r["toxicity"] <= 1.0
        assert (
            math.copysign(1, r["markout_bps"]) == math.copysign(1, r["markout"])
            or r["markout"] == 0
        )
        assert abs(r["markout"] - r2["markout"]) <= 1e-12


# ------------------------------------------------------------------ planted recovery (HR-70, HR-71)


def _hit(est: float, se: float, truth: float) -> bool:
    return abs(est - truth) <= 3 * se


def _impact(rng: np.random.Generator, lam: float, n: int) -> tuple[list[float], list[float]]:
    x, y = [], []
    for _ in range(n):
        s = int(rng.choice([-1, 1]))
        q = int(rng.integers(1, 101))
        e = float(rng.normal(0, 0.05))
        x.append(float(s * q))
        y.append(lam * s * q + e)
    return x, y


def r1(rng: np.random.Generator) -> bool:
    lam, t = 2.5, 3600.0
    r = micro_est.arrival_rate(int(rng.poisson(lam * t)), t)
    return _hit(r["lambda"], r["se"], lam)


def r2(rng: np.random.Generator) -> bool:
    theta, fill = 0.4, 0.1
    rows = []
    for _ in range(5000):
        life = float(rng.exponential(1 / (theta + fill)))
        rows.append((life, "CANCEL" if rng.random() < theta / (theta + fill) else "FILL"))
    r = micro_est.cancel_rate(rows)
    return _hit(r["theta"], r["se"], theta)


def r3(rng: np.random.Generator) -> bool:
    kappa, s0, sinf = 0.3, 5.0, 1.0
    pts = [
        (float(t), sinf + (s0 - sinf) * math.exp(-kappa * t) * math.exp(float(rng.normal(0, 0.05))))
        for t in range(21)
    ]
    r = micro_est.resilience(sinf, pts)
    return _hit(r["kappa"], r["se"], kappa)


def r4(rng: np.random.Generator) -> bool:
    alpha, d0 = 0.15, 1000.0
    lv = [
        (float(k), d0 * math.exp(-alpha * k) * math.exp(float(rng.normal(0, 0.1))))
        for k in range(31)
    ]
    r = micro_est.liquidity_decay(lv)
    return _hit(r["alpha"], r["se"], alpha)


def r5(rng: np.random.Generator) -> bool:
    r = micro_est.adverse_selection(*_impact(rng, 0.002, 2000))
    return _hit(r["lambda_as"], r["se"], 0.002)


def r6(rng: np.random.Generator) -> bool:
    calm = _impact(rng, 0.001, 1000)
    stressed = _impact(rng, 0.004, 1000)
    r = micro_est.regime_impact({"calm": calm, "stressed": stressed})["regimes"]
    return _hit(r["calm"]["lambda_as"], r["calm"]["se"], 0.001) and _hit(
        r["stressed"]["lambda_as"], r["stressed"]["se"], 0.004
    )


def r7(rng: np.random.Generator) -> bool:
    passive = [float(rng.normal(-1, 2)) for _ in range(1000)]
    aggressive = [float(rng.normal(1.5, 2)) for _ in range(1000)]
    r = micro_est.passive_vs_aggressive(passive, aggressive)
    return _hit(r["delta"], r["se"], 2.5)


RECOVERY = [r1, r2, r3, r4, r5, r6, r7]


@pytest.mark.parametrize("j", range(1, 8))
def test_recovery_single_seed(j: int) -> None:
    assert RECOVERY[j - 1](np.random.default_rng(20261118 + j))


@pytest.mark.parametrize("j", range(1, 8))
def test_recovery_coverage(j: int) -> None:
    misses = [s for s in range(70000, 70200) if not RECOVERY[j - 1](np.random.default_rng(s))]
    assert len(misses) <= 4, misses


def test_venue_namedtuples() -> None:
    f = venue_analytics.Fill("A", "BUY", 1.0, 100.0, 0.0)
    o = venue_analytics.Order("A", 2.0, 1.0)
    r = venue_analytics.analytics([(0.0, 101.0)], [f], [o], [0.0])
    assert r == {
        "fill_rates": {"A": 0.5},
        "markouts": [
            {"venue": "A", "h": 0.0, "markout": 1.0, "markout_bps": 100.0, "toxicity": 0.0}
        ],
    }
