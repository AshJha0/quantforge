"""The 50-digit bump reference of KR-265 for `xva.sens.aad` (06-risk/xva-aad-adjustments.md), in Python's
`decimal`, written apart from the hand-written adjoint. Shared by test_xva_aad.py and test_xva_aad_kills.py; reads
no file, so the mutation runs can use it."""

import random
from decimal import Decimal, localcontext
from typing import Any

from quantforge_core import xva_aad

ABS, REL = 1e-12, 1e-10


def close(a: float, e: float) -> bool:
    return abs(a - e) <= ABS + REL * max(abs(a), abs(e))


def flat(g: dict[str, Any]) -> dict[tuple[str, str, int], float]:
    out = {}
    for o, row in g.items():
        for k, v in row.items():
            for i, x in enumerate(v if isinstance(v, list) else [v]):
                out[(o, k, i)] = x
    return out


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


def random_request(rng: random.Random) -> dict[str, Any]:
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
