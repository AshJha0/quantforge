"""Kill tests for `quantforge_core.var_risk` mutants that survived the H-0 Actions run 44317826833
(conformance/mutation/python-h0-2026-11-18.md).

The GIRR delta checks use a reference written out here from MAR21.44 to MAR21.49 and MAR21.4(5)
(specifications/06-risk/frtb-sa-*.md): risk weights by tenor, the 1/sqrt(2) reduction for the
listed currencies, rho = max(exp(-3% |Tk - Tl| / min(Tk, Tl)), 40%) times 99.9% across curves,
99.9% between two inflation factors, 40% between inflation and a tenor, 0 for cross-currency basis,
gamma = 50%, and the three correlation scenarios. Error checks pin code and field.
"""

import math
from typing import Any

import pytest

from quantforge_core import var_risk
from quantforge_core.errors import QfError

TENOR = {"0.25Y": 0.25, "0.5Y": 0.5, "1Y": 1.0, "2Y": 2.0, "3Y": 3.0, "5Y": 5.0, "10Y": 10.0}
WEIGHT = {0.25: 0.017, 0.5: 0.017, 1.0: 0.016, 2.0: 0.013, 3.0: 0.012}
REDUCED = {"EUR", "USD", "GBP", "AUD", "JPY", "SEK", "CAD"}


def _rw(factor: str) -> float:
    if factor in ("INFLATION", "XCCY_BASIS"):
        return 0.016
    return WEIGHT.get(TENOR[factor], 0.011)


def _rho(a: tuple[str, str], b: tuple[str, str]) -> float:
    if "XCCY_BASIS" in (a[1], b[1]):
        return 0.0
    if a[1] == b[1] == "INFLATION":
        return 0.999
    if "INFLATION" in (a[1], b[1]):
        return 0.4
    ta, tb = TENOR[a[1]], TENOR[b[1]]
    r = max(math.exp(-0.03 * abs(ta - tb) / min(ta, tb)), 0.4)
    return r if a[0] == b[0] else 0.999 * r


def _scale(x: float, sc: str) -> float:
    return min(1.25 * x, 1.0) if sc == "high" else max(2 * x - 1, 0.75 * x) if sc == "low" else x


def _reference(sens: list[tuple[str, str, str, float]], reduction: bool, sc: str) -> dict[str, Any]:
    buckets: dict[str, list[tuple[tuple[str, str], float]]] = {}
    for ccy, curve, f, s in sens:
        w = _rw(f) / (math.sqrt(2) if reduction and ccy in REDUCED else 1.0)
        buckets.setdefault(ccy, []).append(((curve, f), w * s))
    ks, ss = [], []
    for ccy in sorted(buckets):
        it = buckets[ccy]
        tot = sum(
            (w * w if i == j else _scale(_rho(a, b), sc) * w * v)
            for i, (a, w) in enumerate(it)
            for j, (b, v) in enumerate(it)
        )
        ks.append(math.sqrt(max(tot, 0.0)))
        ss.append(sum(w for _, w in it))
    g = _scale(0.5, sc)

    def under(s: list[float]) -> float:
        return sum(k * k for k in ks) + sum(
            g * s[b] * s[c] for b in range(len(s)) for c in range(len(s)) if b != c
        )

    used, alt = ss, False
    if under(ss) < 0:
        used, alt = [max(min(s, k), -k) for s, k in zip(ss, ks)], True
    return {"k": ks, "s": ss, "s_used": used, "delta": math.sqrt(max(under(used), 0.0)), "alt": alt}


def _check(sens: list[tuple[str, str, str, float]], reduction: bool) -> dict[str, Any]:
    out: dict[str, Any] = var_risk.girr_delta(sens, reduction, None)
    for sc in ("high", "medium", "low"):
        ref = _reference(sens, reduction, sc)
        got = out["scenarios"][sc]
        assert got["alternative_used"] is ref["alt"]
        assert got["delta"] == pytest.approx(ref["delta"], rel=1e-12)
        for key in ("k", "s", "s_used"):
            assert [b[key] for b in got["buckets"]] == pytest.approx(ref[key], rel=1e-12)
    return out


@pytest.mark.parametrize("reduction", [False, True])
def test_girr_delta_within_bucket_correlations(reduction: bool) -> None:
    sens = [
        ("USD", "SOFR", "1Y", 2e6),
        ("USD", "SOFR", "5Y", -1e6),
        ("USD", "FF", "5Y", 1.5e6),
        ("USD", "CPI1", "INFLATION", 4e5),
        ("USD", "CPI2", "INFLATION", 3e5),
        ("USD", "SOFR", "XCCY_BASIS", 1e5),
        ("BRL", "DI", "2Y", -8e5),
        ("BRL", "DI", "10Y", 6e5),
    ]
    _check(sens, reduction)


def test_girr_delta_alternative_specification_clips_s() -> None:
    """Uncorrelated basis factors: K_b = |S_b| / 2 in each bucket, opposite signs, so
    sum K^2 + gamma sum S_b S_c < 0 and S_b is clipped to [-K_b, K_b]."""
    sens = [("EUR", f"C{i}", "XCCY_BASIS", 1e6) for i in range(4)]
    sens += [("BRL", f"C{i}", "XCCY_BASIS", -1e6) for i in range(4)]
    out = _check(sens, False)
    assert out["scenarios"]["medium"]["alternative_used"] is True


def test_traffic_light_single_observation() -> None:
    out: dict[str, Any] = var_risk.traffic_light(1, 0, 0.99)
    assert out["cumulative_probability"] == pytest.approx(0.99, rel=1e-14)
    assert out["zone"] == "YELLOW"  # 0.95 <= cumulative < 0.9999


def test_filtered_historical_error_codes_and_fields() -> None:
    def err(*args: Any) -> tuple[str, str | None]:
        with pytest.raises(QfError) as e:
            var_risk.filtered_historical(*args)
        return e.value.code, e.value.field

    assert err([], 1.0, 0.94, 0.99) == ("E_INPUT", "returns")
    assert err([0.0, 0.0, 0.0], 1.0, 0.94, 0.99) == ("E_DOMAIN", "returns")
