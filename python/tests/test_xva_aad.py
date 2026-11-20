"""`xva.sens.aad` on `xva.adjustments.value` (06-risk/xva-aad-adjustments.md, rulings KR-262 to KR-268).

A2 of the spec: on 1,000 seeded random requests every gradient entry equals the 50-digit Richardson central bump
(Python `decimal`, the KR-265 rule) within 1e-12 + 1e-10 max(|AAD|, |ref|), which implies the plan's
|AAD - bump| <= 1e-8 max(1, |bump|). The goldens (A1) are checked here too, with the CLI's error order."""

import json
import random
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Any

import pytest

from quantforge_core import xva_aad
from quantforge_core.cli.limits import check_limits
from quantforge_core.cli.operations import OPERATIONS
from quantforge_core.cli.registry import execute
from quantforge_core.errors import QfError
from quantforge_core.xva import Name

ROOT = Path(__file__).resolve().parents[2]
GOLD = json.loads((ROOT / "datasets/golden/stage_k/aadadj_k.json").read_text("utf-8"))["cases"]
VALUE = [c for c in GOLD if c["expected"]["status"] == "ok"]
ERRORS = [c for c in GOLD if c["expected"]["status"] == "error"]
ABS, REL = 1e-12, 1e-10


def _close(a: float, e: float) -> bool:
    return abs(a - e) <= ABS + REL * max(abs(a), abs(e))


def _flat(g: dict[str, Any]) -> dict[tuple[str, str, int], float]:
    out = {}
    for o, row in g.items():
        for k, v in row.items():
            for i, x in enumerate(v if isinstance(v, list) else [v]):
                out[(o, k, i)] = x
    return out


def _run(inputs: dict[str, Any]) -> Any:
    return execute("xva.sens.aad", json.loads(json.dumps(inputs)))


# ---------------------------------------------------------------- goldens (A1)


@pytest.mark.parametrize("case", VALUE, ids=lambda c: c["case_id"])
def test_value_goldens(case: dict[str, Any]) -> None:
    got, exp = _run(case["inputs"]), case["expected"]["outputs"]
    assert set(got) == set(exp)
    for k in exp:
        if k != "gradient":
            assert _close(got[k], exp[k]), k
    a, e = _flat(got["gradient"]), _flat(exp["gradient"])
    assert set(a) == set(e)
    bad = [(k, a[k], e[k]) for k in e if not _close(a[k], e[k])]
    assert not bad, bad[:3]


@pytest.mark.parametrize("case", ERRORS, ids=lambda c: c["case_id"])
def test_error_goldens(case: dict[str, Any]) -> None:
    with pytest.raises(QfError) as info:
        _run(case["inputs"])
    assert info.value.code == case["expected"]["error_code"]


def test_values_are_those_of_the_wrapped_operation() -> None:
    for case in VALUE:
        inner = case["inputs"]["inputs"]
        plain = execute("xva.adjustments.value", json.loads(json.dumps(inner)))
        got = _run(case["inputs"])
        assert {k: got[k] for k in plain} == plain


# ---------------------------------------------------------------- the 50-digit reference (KR-265)

D = Decimal


def _forward_dec(p: dict[str, Any], branch: bool | None) -> dict[str, Decimal]:
    """G-41 at 50 digits with bucket hazards (KR-263); written apart from the adjoint."""
    t, n = p["t"], len(p["t"])
    dt = [t[0]] + [t[i] - t[i - 1] for i in range(1, n)]

    def surv(h: list[Decimal]) -> list[Decimal]:
        s, acc = [D(1)], D(0)
        for hj, d in zip(h, dt, strict=True):
            acc += hj * d
            s.append((-acc).exp())
        return s

    sc, sb = surv(p["hc"]), surv(p["hb"])
    w = [p["df"][i] * sc[i] * sb[i] * dt[i] for i in range(n)]
    if branch is None:
        sl = [p["sl"]] * n
    elif branch:
        sl = [p["sl"] - p["hb"][i] * (1 - p["rb"]) for i in range(n)]
    else:
        sl = [D(0)] * n
    cva = (1 - p["rc"]) * sum(
        (p["df"][i] * p["ee"][i] * (sc[i] - sc[i + 1]) * sb[i] for i in range(n)), D(0)
    )
    dva = (1 - p["rb"]) * sum(
        (p["df"][i] * -p["ene"][i] * (sb[i] - sb[i + 1]) * sc[i] for i in range(n)), D(0)
    )
    fca = p["sb"] * sum((w[i] * p["ee"][i] for i in range(n)), D(0))
    fba = sum((sl[i] * w[i] * -p["ene"][i] for i in range(n)), D(0))
    out = {"cva": cva, "dva": dva, "fca": fca, "fba": fba, "fva": fca - fba}
    if "im" in p:
        out["mva"] = p["sim"] * sum((w[i] * p["im"][i] for i in range(n)), D(0))
    if "capital" in p:
        out["kva"] = p["hur"] * sum((w[i] * p["capital"][i] for i in range(n)), D(0))
    return out


FIELDS = {
    "counterparty.recovery": "rc",
    "own.recovery": "rb",
    "discount_factors": "df",
    "ee": "ee",
    "ene": "ene",
    "funding.borrow_spread": "sb",
    "funding.lend_spread": "sl",
    "im": "im",
    "im_spread": "sim",
    "capital": "capital",
    "hurdle_rate": "hur",
    "counterparty.hazard_buckets": "hc",
    "own.hazard_buckets": "hb",
}


def _params(inp: dict[str, Any]) -> dict[str, Any]:
    n = len(inp["times"])
    p: dict[str, Any] = {
        "t": [D(x) for x in inp["times"]],
        "hc": [D(inp["counterparty"]["hazard_rate"])] * n,
        "hb": [D(inp["own"]["hazard_rate"])] * n,
        "rc": D(inp["counterparty"]["recovery"]),
        "rb": D(inp["own"]["recovery"]),
        "df": [D(x) for x in inp["discount_factors"]],
        "ee": [D(x) for x in inp["ee"]],
        "ene": [D(x) for x in inp["ene"]],
        "sb": D(inp["funding"]["borrow_spread"]),
        "sl": D(inp["funding"]["lend_spread"]),
    }
    if "im" in inp:
        p["im"], p["sim"] = [D(x) for x in inp["im"]], D(inp["im_spread"])
    if "capital" in inp:
        p["capital"], p["hur"] = [D(x) for x in inp["capital"]], D(inp["hurdle_rate"])
    return p


def _bumped(p: dict[str, Any], key: str, idx: int | None, eps: Decimal) -> dict[str, Any]:
    q = dict(p)
    if key.endswith(".hazard_rate"):
        f = "hc" if key.startswith("counterparty") else "hb"
        q[f] = [x + eps for x in p[f]]
    elif idx is None:
        q[FIELDS[key]] = p[FIELDS[key]] + eps
    else:
        arr = list(p[FIELDS[key]])
        arr[idx] += eps
        q[FIELDS[key]] = arr
    return q


def _base(p: dict[str, Any], key: str, idx: int | None) -> Decimal:
    if key.endswith(".hazard_rate"):
        first: Decimal = p["hc" if key.startswith("counterparty") else "hb"][0]
        return first
    v = p[FIELDS[key]]
    out: Decimal = v if idx is None else v[idx]
    return out


def reference(inp: dict[str, Any]) -> dict[tuple[str, str, int], float]:
    """KR-265: (4 D(d/2) - D(d)) / 3, d = 1e-12 max(1, |x|), at 50 digits, overlap branch held fixed."""
    f = inp["funding"]
    branch = None
    if f["exclude_dva_overlap"]:
        branch = f["lend_spread"] - inp["own"]["hazard_rate"] * (1 - inp["own"]["recovery"]) >= 0
    out: dict[tuple[str, str, int], float] = {}
    with localcontext() as ctx:
        ctx.prec = 50
        p = _params(inp)
        keys = xva_aad._keys("im" in inp, "capital" in inp)
        for key in keys:
            scalar = key not in FIELDS or not isinstance(p[FIELDS[key]], list)
            for idx in [None] if scalar else range(len(p["t"])):
                d = D("1e-12") * max(D(1), abs(_base(p, key, idx)))

                def dd(h: Decimal, key: str = key, idx: int | None = idx) -> dict[str, Decimal]:
                    up = _forward_dec(_bumped(p, key, idx, h), branch)
                    dn = _forward_dec(_bumped(p, key, idx, -h), branch)
                    return {o: (up[o] - dn[o]) / (2 * h) for o in up}

                a, b = dd(d), dd(d / 2)
                for o in a:
                    out[(o, key, idx or 0)] = float((4 * b[o] - a[o]) / 3)
    return out


def _random_request(rng: random.Random) -> dict[str, Any]:
    n = rng.randint(1, 6)
    steps = [rng.choice((0.25, 0.5, 1.0, rng.uniform(0.01, 3.0))) for _ in range(n)]
    times, acc = [], 0.0
    for s in steps:
        acc += s
        times.append(acc)

    def profile(lo: float, hi: float) -> list[float]:
        return [0.0 if rng.random() < 0.15 else rng.uniform(lo, hi) for _ in range(n)]

    scale = 10 ** rng.uniform(-3, 6)
    inp: dict[str, Any] = {
        "times": times,
        "discount_factors": [rng.uniform(0.3, 1.05) for _ in range(n)],
        "ee": [x * scale for x in profile(0, 1)],
        "ene": [-x * scale for x in profile(0, 1)],
        "counterparty": {
            "hazard_rate": rng.choice((0.0, rng.uniform(0, 0.6))),
            "recovery": rng.choice((0.0, 0.4, rng.uniform(0, 0.999999))),
        },
        "own": {
            "hazard_rate": rng.choice((0.0, rng.uniform(0, 0.1))),
            "recovery": rng.choice((0.0, 0.4, rng.uniform(0, 0.99))),
        },
        "funding": {
            "borrow_spread": rng.uniform(0, 0.03),
            "lend_spread": rng.uniform(0, 0.03),
            "exclude_dva_overlap": rng.random() < 0.5,
        },
    }
    if rng.random() < 0.4:
        inp["im"], inp["im_spread"] = profile(0, scale), rng.uniform(0, 0.02)
    if rng.random() < 0.4:
        inp["capital"], inp["hurdle_rate"] = profile(0, scale), rng.uniform(0, 0.15)
    return inp


def _worst(inp: dict[str, Any]) -> float:
    got = _flat(_run({"operation": "xva.adjustments.value", "inputs": inp})["gradient"])
    ref = reference(inp)
    assert set(got) == set(ref)
    worst = 0.0
    for k, e in ref.items():
        a = got[k]
        assert _close(a, e), (k, a, e, inp)
        assert abs(a - e) <= 1e-8 * max(1.0, abs(e))  # the plan's form (14.8 K-8)
        worst = max(worst, abs(a - e) / max(1.0, abs(e)))
    return worst


def test_a2_aad_equals_the_50_digit_bump_on_1000_random_requests() -> None:
    rng = random.Random(20261120)
    worst = max(_worst(_random_request(rng)) for _ in range(1000))
    assert (
        worst <= 1e-8
    )  # measured 2.4e-12 (largest |AAD - ref| / max(1, |ref|)); the gate is per entry above


@pytest.mark.parametrize("case", VALUE, ids=lambda c: c["case_id"])
def test_a1_goldens_against_the_reference_computed_here(case: dict[str, Any]) -> None:
    if "wrt" not in case["inputs"]:
        _worst(case["inputs"]["inputs"])


# ---------------------------------------------------------------- properties and edges


def _base_request() -> dict[str, Any]:
    req: dict[str, Any] = json.loads(json.dumps(VALUE[0]["inputs"]))
    return req


def test_bucket_entries_sum_to_the_flat_entry_and_recovery_closed_forms() -> None:
    for case in VALUE:
        got = _run(case["inputs"])
        for o, row in got["gradient"].items():
            for name in ("counterparty", "own"):
                if f"{name}.hazard_buckets" in row:
                    flat, b = row[f"{name}.hazard_rate"], row[f"{name}.hazard_buckets"]
                    assert abs(flat - sum(b)) <= 1e-12 * max(1.0, abs(flat)), (o, name)
        g = got["gradient"]
        if "counterparty.recovery" in g["cva"]:
            r_c = case["inputs"]["inputs"]["counterparty"]["recovery"]
            assert _close(g["cva"]["counterparty.recovery"], -got["cva"] / (1 - r_c))


def test_wrt_keeps_canonical_order_and_only_listed_keys() -> None:
    req = _base_request()
    req["wrt"] = ["ee", "counterparty.hazard_rate"]
    got = _run(req)
    for row in got["gradient"].values():
        assert list(row) == ["counterparty.hazard_rate", "ee"]


def test_keys_with_im_and_capital() -> None:
    assert xva_aad._keys(True, True)[-4:] == ("im", "im_spread", "capital", "hurdle_rate")
    assert xva_aad._keys(False, False) == xva_aad.BASE_KEYS


def test_zero_branch_of_the_overlap_floor_has_exact_zeros() -> None:
    req = _base_request()
    req["inputs"]["own"]["hazard_rate"] = 0.02
    req["inputs"]["funding"]["exclude_dva_overlap"] = True
    g = _run(req)["gradient"]["fba"]
    for k, v in g.items():
        for x in v if isinstance(v, list) else [v]:
            assert x == 0.0, k


def test_kink_takes_the_linear_branch() -> None:
    req = _base_request()
    req["inputs"]["own"] = {"hazard_rate": 0.01, "recovery": 0.5}
    req["inputs"]["funding"].update(lend_spread=0.005, exclude_dva_overlap=True)
    got = _run(req)
    g = got["gradient"]["fba"]
    assert got["fba"] == 0.0
    assert g["funding.lend_spread"] > 0
    assert _close(g["own.hazard_rate"], -0.5 * g["funding.lend_spread"])
    assert _close(g["own.recovery"], 0.01 * g["funding.lend_spread"])


@pytest.mark.parametrize(
    ("wrt", "code"),
    [([], "E_INPUT"), (["ee", "ee"], "E_INPUT"), (["im"], "E_INPUT"), (["x"], "E_INPUT")],
)
def test_wrt_rules(wrt: list[str], code: str) -> None:
    n = Name(0.01, 0.4)
    with pytest.raises(QfError) as info:
        xva_aad.adjustments_aad(
            [1.0], [1.0], [1.0], [-1.0], n, n, 0.0, 0.0, False, None, None, None, None, wrt
        )
    assert info.value.code == code


def test_limit_counts_every_profile() -> None:
    for key in ("times", "discount_factors", "ee", "ene", "im", "capital"):
        inner = {key: [0.0] * 10_000}
        check_limits("xva.sens.aad", {"inputs": inner})
        inner[key].append(0.0)
        with pytest.raises(QfError) as info:
            check_limits("xva.sens.aad", {"inputs": inner})
        assert info.value.code == "E_LIMIT"
    check_limits("xva.sens.aad", {"inputs": None})


def test_registered() -> None:
    assert "xva.sens.aad" in OPERATIONS
