"""Stage H wave 2 execution: adaptive algorithms (H-14) and TCA pre-trade / attribution (H-17).

Every golden row of datasets/golden/stage_h/alg_h.json and tcx_h.json through the CLI, then the
acceptance tests exactly as fixed in specifications/10-execution/adaptive-algos.md and
tca-pretrade.md (2026-11-18, before the build): schedule identities on 1,000 random inputs per
operation, the pair cash-imbalance bounds, the simulated-book method test for liquidity seeking
(200 planted books, seed 20261118, 5 to 20 levels, tick 0.01, replayed through the lit engine
`exec.sim.lit.run`) and the attribution identity (1,000 random inputs, seed 20261118)."""

import itertools
import json
import math
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from quantforge_core import adaptive_exec as ax
from quantforge_core import execution as ex
from quantforge_core import lit_matching
from quantforge_core.cli.main import run_case
from quantforge_core.errors import QfError
from quantforge_core.rng import Xoshiro256

GOLD = Path(__file__).resolve().parents[2] / "datasets" / "golden" / "stage_h"
SEED = 20261118


def _cases(name: str) -> list[dict[str, Any]]:
    text = (GOLD / f"{name}.json").read_text(encoding="utf-8")
    cases: list[dict[str, Any]] = json.loads(text)["cases"]
    return cases


def _run(operation: str, inputs: dict[str, Any]) -> dict[str, Any]:
    doc = {"schema_version": "1.0", "case_id": "w2", "operation": operation, "inputs": inputs}
    return run_case(json.dumps(doc))


def _close(got: Any, exp: Any, path: str = "") -> None:
    """simple_analytic: 1e-12 absolute + 1e-10 relative; null and shape exact."""
    if isinstance(exp, dict):
        assert set(got) == set(exp), path
        for k in exp:
            _close(got[k], exp[k], f"{path}.{k}")
    elif isinstance(exp, list):
        assert isinstance(got, list) and len(got) == len(exp), path
        for k, (g, e) in enumerate(zip(got, exp, strict=True)):
            _close(g, e, f"{path}[{k}]")
    elif exp is None:
        assert got is None, path
    else:
        assert abs(got - exp) <= 1e-12 + 1e-10 * abs(exp), (path, got, exp)


@pytest.mark.parametrize("case", _cases("alg_h") + _cases("tcx_h"), ids=lambda c: c["case_id"])
def test_golden(case: dict[str, Any]) -> None:
    r = _run(case["operation"], case["inputs"])
    exp = case["expected"]
    if exp["status"] == "error":
        assert r["error"]["code"] == exp["error_code"], r
    else:
        assert "outputs" in r, r
        _close(r["outputs"], {k: v for k, v in exp.items() if k != "status"})


def test_units_outputs_are_integers() -> None:
    r = _run(
        "exec.algo.arrival", {"quantity": 1001, "n_buckets": 2, "urgency": 0.5, "mode": "UNITS"}
    )
    assert all(type(x) is int for x in r["outputs"]["slices"])
    i = {
        "leg_a": {"side": "BUY", "quantity": 1000, "price": 30},
        "leg_b": {"side": "SELL", "price": 70},
    }
    r = _run("exec.algo.pair", {**i, "pair_mode": "CASH_BALANCED", "n_buckets": 3, "mode": "UNITS"})
    o = r["outputs"]
    assert type(o["quantity_b"]) is int and all(type(x) is int for x in o["slices_b"])


# ------------------------------------------------------------------ error precedence (HR-66)


@pytest.mark.parametrize(
    ("operation", "inputs", "code"),
    [
        # structural E_INPUT before E_DOMAIN
        ("exec.algo.arrival", {"quantity": 10, "n_buckets": 0, "urgency": -1}, "E_INPUT"),
        (
            "exec.algo.close",
            {"quantity": 10, "close_volume": -1, "auction_participation": 2, "profile": []},
            "E_INPUT",
        ),
        (
            "exec.algo.liquidity_seek",
            {
                "side": "BUY",
                "quantity": 10,
                "limit_price": -1,
                "take_fraction": 0,
                "books": [[[2, 1], [1, 1]]],
            },
            "E_INPUT",
        ),
        (
            "exec.algo.liquidity_seek",
            {"side": "BUY", "quantity": 10, "limit_price": 1, "take_fraction": 0, "books": []},
            "E_INPUT",
        ),
        (
            "exec.algo.pair",
            {
                "leg_a": {"side": "BUY", "quantity": 10, "price": -1},
                "leg_b": {"side": "BUY", "price": 1},
                "pair_mode": "CASH_BALANCED",
                "n_buckets": 2,
            },
            "E_INPUT",
        ),
        (
            "exec.algo.basket",
            {"legs": [{"side": "BUY", "quantity": 0, "price": -1}], "n_buckets": 2},
            "E_INPUT",
        ),
        (
            "exec.tca.attribution",
            {
                "side": "BUY",
                "decision_price": -1,
                "arrival_mid": 1,
                "end_price": 1,
                "order_quantity": 1,
                "fills": [{"quantity": 2, "price": 1, "mid": 1}],
                "fees": 0,
            },
            "E_INPUT",
        ),
        (
            "exec.tca.pretrade",
            {
                "quantity": 0,
                "adv": -1,
                "daily_vol": 0.1,
                "participation": 0.5,
                "half_spread_bps": 0,
                "params": {"a1": 1, "a2": 1, "a3": 1, "a4": 1, "b1": 1},
            },
            "E_INPUT",
        ),
        # E_SCHEMA before everything
        (
            "exec.algo.pair",
            {
                "leg_a": {"side": "BUY", "quantity": 0, "price": 1},
                "leg_b": {"side": "SELL", "price": 1},
                "pair_mode": "OTHER",
                "n_buckets": 2,
            },
            "E_SCHEMA",
        ),
        (
            "exec.algo.liquidity_seek",
            {
                "side": "BUY",
                "quantity": 10,
                "limit_price": 1,
                "take_fraction": 1,
                "books": [[[1, 1, 1]]],
            },
            "E_SCHEMA",
        ),
        (
            "exec.algo.arrival",
            {"quantity": 10, "n_buckets": 2, "urgency": 0, "mode": "LOTS"},
            "E_SCHEMA",
        ),
        # E_DOMAIN paths the goldens do not reach
        (
            "exec.algo.close",
            {"quantity": 10, "close_volume": -1, "auction_participation": 0.5, "profile": [1]},
            "E_DOMAIN",
        ),
        (
            "exec.algo.liquidity_seek",
            {
                "side": "SELL",
                "quantity": 10,
                "limit_price": 1,
                "take_fraction": 1,
                "books": [[[2, 1], [-1, 1]]],
            },
            "E_DOMAIN",
        ),
        (
            "exec.tca.pretrade",
            {
                "quantity": 1,
                "adv": 1,
                "daily_vol": 0,
                "participation": 0.5,
                "half_spread_bps": 0,
                "params": {"a1": 1, "a2": 1, "a3": 0, "a4": 1, "b1": 1},
            },
            "E_DOMAIN",
        ),
        (
            "exec.algo.pair",
            {
                "leg_a": {"side": "BUY", "quantity": 10, "price": 1},
                "leg_b": {"side": "SELL", "price": 1},
                "pair_mode": "HEDGED",
                "n_buckets": 2,
            },
            "E_INPUT",
        ),
        ("exec.algo.arrival", {"quantity": 10, "n_buckets": 100_001, "urgency": 0}, "E_LIMIT"),
    ],
)
def test_error_precedence(operation: str, inputs: dict[str, Any], code: str) -> None:
    assert _run(operation, inputs)["error"]["code"] == code


def test_non_finite_is_rejected() -> None:
    with pytest.raises(QfError) as e:
        ax.algo_arrival(10.0, 2, math.nan, "CONTINUOUS")
    assert e.value.code == "E_DOMAIN"


# ------------------------------------------------------------------ random inputs


class _U:
    def __init__(self, seed: int) -> None:
        self.g = Xoshiro256.seeded(seed)

    def u(self, a: float = 0.0, b: float = 1.0) -> float:
        return a + (b - a) * ((self.g.next_u64() >> 11) * 2.0**-53)

    def i(self, a: int, b: int) -> int:
        return a + self.g.next_u64() % (b - a + 1)

    def side(self) -> str:
        return "BUY" if self.g.next_u64() & 1 else "SELL"


def _rel(got: float, exp: float, tol: float = 1e-12) -> bool:
    return abs(got - exp) <= tol * max(1.0, abs(exp))


# Acceptance 1 and 2 (adaptive-algos.md)


def test_arrival_identities() -> None:
    r = _U(SEED)
    for _ in range(1000):
        n, k = r.i(1, 60), r.u(0.0, 2.0)
        x = float(r.i(1, 10**9))
        c = ax.algo_arrival(x, n, k, "CONTINUOUS")["slices"]
        assert _rel(math.fsum(c), x)
        assert all(a > b for a, b in itertools.pairwise(c)), (n, k)
        u = ax.algo_arrival(x, n, k, "UNITS")["slices"]
        assert sum(u) == x and all(type(v) is int for v in u)
        cum = 0.0
        for j, v in enumerate(u, 1):  # HR-59: within 1/2 of the continuous cumulative
            cum += v
            assert abs(cum - math.fsum(c[:j])) <= 0.5 + 1e-9 * x


def test_arrival_kappa_zero_is_twap_continuous() -> None:
    r = _U(SEED + 1)
    for _ in range(1000):
        n, x = r.i(1, 500), r.u(1.0, 1e9)
        assert ax.algo_arrival(x, n, 0.0, "CONTINUOUS") == ex.schedule_twap(x, n, "CONTINUOUS")


@pytest.mark.xfail(
    strict=True,
    reason="finding: HR-59 half-up cumulative rounding at kappa = 0 gives e.g. [333, 334, 333] "
    "for X = 1000, N = 3, while exec.schedule.twap UNITS (HR-3) gives [334, 333, 333]; the spec "
    "identity 'kappa = 0 equals exec.schedule.twap' does not hold in UNITS",
)
def test_arrival_kappa_zero_is_twap_units() -> None:
    assert ax.algo_arrival(1000.0, 3, 0.0, "UNITS") == ex.schedule_twap(1000.0, 3, "UNITS")


def test_close_identity() -> None:
    r = _U(SEED + 2)
    for _ in range(1000):
        m = r.i(1, 30)
        w = [r.u(0.0, 5.0) for _ in range(m)]
        x, v, p = float(r.i(1, 10**7)), r.u(0.0, 1e7), r.u()
        c = ax.algo_close(x, v, p, w, "CONTINUOUS")
        assert _rel(c["auction_quantity"] + math.fsum(c["slices"]), x)
        u = ax.algo_close(x, v, p, w, "UNITS")
        assert u["auction_quantity"] + sum(u["slices"]) == x


def test_basket_identities() -> None:
    r = _U(SEED + 3)
    for _ in range(1000):
        n = r.i(1, 40)
        legs = [(r.side(), float(r.i(1, 10**6)), r.u(1.0, 1000.0)) for _ in range(r.i(1, 8))]
        c = ax.algo_basket(legs, n, "CONTINUOUS")
        gross = c["gross_notional"]
        for (_, q, _), s in zip(legs, c["slices"], strict=True):
            assert _rel(math.fsum(s), q)
        last = c["cash_imbalance"][-1]
        for j, ci in enumerate(c["cash_imbalance"], 1):
            assert abs(ci - j / n * last) <= 1e-12 * gross
        u = ax.algo_basket(legs, n, "UNITS")
        for (_, q, _), s in zip(legs, u["slices"], strict=True):
            assert sum(s) == q


def test_basket_zero_net_cash_every_bucket() -> None:
    legs = [("BUY", 300.0, 10.0), ("BUY", 200.0, 20.0), ("SELL", 700.0, 10.0)]
    assert ax.algo_basket(legs, 7, "CONTINUOUS")["cash_imbalance"] == pytest.approx(
        [0.0] * 7, abs=1e-9
    )


# Acceptance 1 and 3 (pair)


def test_pair_identities_and_bounds() -> None:
    r = _U(SEED + 4)
    for _ in range(1000):
        n, qa = r.i(1, 40), float(r.i(1, 10**6))
        pa, pb = r.u(1.0, 1000.0), r.u(1.0, 1000.0)
        sa = r.side()
        sb = "SELL" if sa == "BUY" else "BUY"
        a, b = (sa, qa, pa), (sb, pb)
        c = ax.algo_pair(a, b, "CASH_BALANCED", None, n, "CONTINUOUS")
        assert _rel(math.fsum(c["slices_a"]), qa)
        assert _rel(math.fsum(c["slices_b"]), c["quantity_b"])
        assert all(abs(x) <= 1e-12 * qa * pa for x in c["cash_imbalance"])  # 0 every bucket
        u = ax.algo_pair(a, b, "CASH_BALANCED", None, n, "UNITS")
        assert sum(u["slices_a"]) == qa and sum(u["slices_b"]) == u["quantity_b"]
        assert u["quantity_b"] == math.floor(pa / pb * qa + 0.5)
        assert all(abs(x) <= pb / 2 * (1 + 1e-12) for x in u["cash_imbalance"])
        h = r.u(0.01, 5.0)
        hd = ax.algo_pair(a, (r.side(), pb), "HEDGED", h, n, "CONTINUOUS")
        assert _rel(hd["quantity_b"], h * qa)


# Acceptance 4: simulated-book method test through the lit engine


def _lit_fills(
    side: str, book: list[tuple[int, int]], limit: int, child: float
) -> tuple[Decimal, Decimal, list[Decimal]]:
    """Rests `book` (ticks, size) on the opposite side of a fresh lit book, sends the child as an
    IOC limit at L, and returns the engine's filled quantity, notional and fill prices."""
    opp = "SELL" if side == "BUY" else "BUY"
    events = [
        {
            "op": "NEW",
            "id": f"M{k}",
            "trader": "MM",
            "side": opp,
            "type": "LIMIT",
            "price": str(Decimal(t) / 100),
            "qty": str(s),
        }
        for k, (t, s) in enumerate(book)
    ]
    if child > 0:
        events.append(
            {
                "op": "NEW",
                "id": "C",
                "trader": "US",
                "side": side,
                "type": "IOC",
                "price": str(Decimal(limit) / 100),
                "qty": str(Decimal(child)),
            }
        )
    out = lit_matching.run("0.01", "0.125", events, {"taker_fee": "0", "maker_rebate": "0"})
    fills = [f for f in out["fills"] if f["taker_id"] == "C"]
    q = sum((Decimal(f["qty"]) for f in fills), Decimal(0))
    notional = sum((Decimal(f["qty"]) * Decimal(f["price"]) for f in fills), Decimal(0))
    return q, notional, [Decimal(f["price"]) for f in fills]


def test_liquidity_seek_simulated_book() -> None:
    r = _U(SEED)
    for _ in range(200):
        side = r.side()
        buy = side == "BUY"
        k_buckets = r.i(1, 5)
        x = float(r.i(1, 20_000))
        alpha = r.i(1, 8) / 8  # dyadic, so alpha A and the remainders are exact in binary64
        limit = r.i(9_000, 11_000)  # ticks of 0.01
        books_t: list[list[tuple[int, int]]] = []
        for _b in range(k_buckets):
            n_lv = r.i(5, 20)
            start = limit - r.i(0, 40) if buy else limit + r.i(0, 40)
            step = 1 if buy else -1
            ticks, t = [], start
            for _l in range(n_lv):
                ticks.append(t)
                t += step * r.i(1, 5)
            books_t.append([(tt, r.i(1, 2_000)) for tt in ticks])
        books = [[(t / 100, float(s)) for t, s in b] for b in books_t]
        res = ax.algo_liquidity_seek(side, x, limit / 100, alpha, books)
        remaining = x
        for b, bt, c, avg in zip(books, books_t, res["slices"], res["avg_prices"], strict=True):
            depth = sum(s for p, s in b if (p <= limit / 100 if buy else p >= limit / 100))
            planted = sum(s for t, s in bt if (t <= limit if buy else t >= limit))
            assert depth == planted  # known depth inside L
            want = min(remaining, alpha * depth)
            assert _rel(c, want)
            q, notional, prices = _lit_fills(side, bt, limit, c)
            assert _rel(float(q), want)  # recovered fills equal min(R, alpha A_i)
            lim_d = Decimal(limit) / 100
            assert all((p <= lim_d) if buy else (p >= lim_d) for p in prices)  # none outside L
            if c > 0:
                assert avg is not None
                assert _rel(avg, float(notional / q))
                best = b[0][0]
                lo, hi = (best, limit / 100) if buy else (limit / 100, best)
                assert lo - 1e-12 <= avg <= hi + 1e-12
            else:
                assert avg is None
            remaining -= c
        assert _rel(res["filled"] + res["residual"], x)


# ------------------------------------------------------------------ tca-pretrade.md


def test_attribution_identity_and_shortfall() -> None:
    r = _U(SEED)
    for _ in range(1000):
        side = r.side()
        s = 1.0 if side == "BUY" else -1.0
        pd, m0, pc = r.u(1, 1000), r.u(1, 1000), r.u(1, 1000)
        fills = [(r.u(1, 1000), r.u(1, 1000), r.u(1, 1000)) for _ in range(r.i(1, 50))]
        x = math.fsum(q for q, _, _ in fills) * r.u(1.0, 2.0)
        fees = r.u(0, 100)
        a = ax.tca_attribution(side, pd, m0, pc, x, fills, fees)
        bound = 1e-10 * max(1.0, abs(a["total"]))
        direct = s * math.fsum(q * (p - pd) for q, p, _ in fills)
        assert abs(a["delay"] + a["impact"] + a["spread"] - direct) <= bound
        sf = ex.tca_shortfall(side, pd, m0, pc, x, [(q, p) for q, p, _ in fills], fees, None)
        assert abs(a["total"] - sf["total"]) <= bound
        assert abs(a["execution"] - sf["execution"]) <= bound


@pytest.mark.parametrize(
    "case",
    [
        c
        for c in _cases("tcx_h")
        if c["operation"] == "exec.tca.attribution" and c["expected"]["status"] == "ok"
    ],
    ids=lambda c: c["case_id"],
)
def test_attribution_identity_goldens(case: dict[str, Any]) -> None:
    i = case["inputs"]
    fills = [(f["quantity"], f["price"], f["mid"]) for f in i["fills"]]
    args = (i["side"], i["decision_price"], i["arrival_mid"], i["end_price"], i["order_quantity"])
    a = ax.tca_attribution(*args, fills, i["fees"])
    s = 1.0 if i["side"] == "BUY" else -1.0
    bound = 1e-10 * max(1.0, abs(a["total"]))
    direct = s * math.fsum(q * (p - i["decision_price"]) for q, p, _ in fills)
    assert abs(a["delay"] + a["impact"] + a["spread"] - direct) <= bound
    sf = ex.tca_shortfall(*args, [(q, p) for q, p, _ in fills], i["fees"], None)
    assert abs(a["total"] - sf["total"]) <= bound


def test_pretrade_monotonicity() -> None:
    r = _U(SEED + 5)
    for _ in range(1000):
        adv, sig = r.u(1e5, 1e8), r.u(0.001, 0.1)
        prm = (r.u(1, 1000), r.u(0, 2), r.u(0.1, 2), r.u(0, 2), r.u())
        x1, x2 = sorted((r.u(1, 1e6), r.u(1, 1e6)))
        p1, p2 = sorted((r.u(0.01, 0.99), r.u(0.01, 0.99)))
        f = ax.tca_pretrade
        assert f(x1, adv, sig, p1, 1.0, prm, None)["impact_bps"] <= f(
            x2, adv, sig, p1, 1.0, prm, None
        )["impact_bps"] * (1 + 1e-14)
        lo, hi = f(x1, adv, sig, p1, 1.0, prm, None), f(x1, adv, sig, p2, 1.0, prm, None)
        assert lo["impact_bps"] <= hi["impact_bps"] * (1 + 1e-14)
        assert lo["timing_risk_bps"] >= hi["timing_risk_bps"] * (1 - 1e-14)
