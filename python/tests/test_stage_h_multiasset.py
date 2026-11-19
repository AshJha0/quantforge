"""Stage H multi-asset H-22, H-23, H-24: every golden row of auc_h, eqc_h, fxc_h, fxv_h, rtc_h, fut_h
and e1_h4 replayed against the core functions, then acceptance A1 (Python part), A3 (properties) and
A4 (labels) of specifications/09-microstructure/asset-conventions.md as fixed (HR-95). A2 and A5
are records, not tests (program/STAGE_H_BLIND_MULTIASSET.md; HR-98 source tags)."""

import json
import random
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from quantforge_core import dark_pool, lit_matching, sor
from quantforge_core import multiasset as ma
from quantforge_core.errors import QfError

GOLD = Path(__file__).resolve().parents[2] / "datasets" / "golden" / "stage_h"
SUITES = ("auc_h", "eqc_h", "fxc_h", "fxv_h", "rtc_h", "fut_h", "ses_h", "acls_h", "e1_h4")
FN = {
    "micro.eq.round_price": ma.eq_round_price,
    "micro.eq.fee_check": ma.eq_fee_check,
    "micro.eq.round_lot": ma.eq_round_lot,
    "micro.eq.settle_date": ma.eq_settle_date,
    "exec.sim.auction.uncross": ma.auction_uncross,
    "micro.fx.pip_value": ma.fx_pip_value,
    "micro.fx.spot_date": ma.fx_spot_date,
    "exec.sim.fx.stream": ma.fx_stream,
    "exec.sim.fx.request": ma.fx_request,
    "micro.rates.parse_32nds": ma.rates_parse_32nds,
    "micro.rates.format_32nds": ma.rates_format_32nds,
    "micro.rates.tick_value": ma.rates_tick_value,
    "micro.rates.bond_price": ma.rates_bond_price,
    "micro.rates.bill_price": ma.rates_bill_price,
    "exec.sim.fut.to_ticks": ma.fut_to_ticks,
    "exec.sim.fut.to_text": ma.fut_to_text,
    "exec.sim.fut.pnl": ma.fut_pnl,
    "exec.sim.fut.variation": ma.fut_variation,
    "exec.sim.fut.run": ma.fut_run,
    "micro.rates.bond_yield": ma.rates_bond_yield,
    "exec.sim.lit.run": lambda i: lit_matching.run(
        i["tick_size"], i["lot_size"], i["events"], i["fee_schedule"], i.get("session")
    ),
    "exec.sor.allocate": sor.allocate,
    "exec.sim.dark.run": lambda i: dark_pool.run(i["config"], i["events"]),
}
CASES = [
    c for s in SUITES for c in json.loads((GOLD / f"{s}.json").read_text(encoding="utf-8"))["cases"]
]
LABELS = {ma.EQ_LABEL, ma.IEX_LABEL, ma.FX_LABEL, ma.RATES_LABEL}


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["case_id"])
def test_golden(case: dict[str, Any]) -> None:
    """A1 (Python part) and A4: every golden row, every success output carries its label."""
    fn, exp = FN[case["operation"]], case["expected"]
    if exp["status"] == "error":
        with pytest.raises(QfError) as e:
            fn(case["inputs"])
        assert e.value.code == exp["error_code"]
    else:
        out = fn(case["inputs"])
        if case["operation"] == "micro.rates.bond_yield":
            assert out["yield"] == pytest.approx(exp["outputs"]["yield"], abs=1e-10)
        else:
            assert out == exp["outputs"]
        # A4 as ruled 2026-11-18: venue and simulator outputs carry a label, pure conventions none
        venue = case["operation"].startswith("exec.") and case["operation"] != "exec.sor.allocate"
        assert (out.get("label") in LABELS) if venue else ("label" not in out)


def test_cli_registered() -> None:
    from quantforge_core.cli.operations import OPERATIONS

    assert set(FN) <= set(OPERATIONS)


# ------------------------------------------------------------------ A3 properties


def test_a3_rounding_never_more_aggressive() -> None:
    rng = random.Random(20261118)
    for tier in ("PENNY", "HALF_PENNY"):
        for _ in range(2000):
            p = Decimal(rng.randrange(1, 10**8)) / 10**5
            for side in ("BUY", "SELL"):
                r = Decimal(
                    ma.eq_round_price({"price": str(p), "side": side, "tick_tier": tier})["price"]
                )
                assert (r <= p) if side == "BUY" else (r >= p)
                tick = (
                    Decimal("0.0001")
                    if r < 1
                    else Decimal("0.005" if tier == "HALF_PENNY" else "0.01")
                )
                assert r % tick == 0 or r == 1


def test_a3_32nds_round_trip_on_1_128_grid() -> None:
    """A3 as amended by HR-109: CME quarter-32nds, so the round trip holds on the 1/128 grid."""
    for n in range(0, 128 * 130, 7):
        x = Decimal(n) / 128
        text = ma.rates_format_32nds({"resolution": 128, "value": str(x)})["text"]
        assert Decimal(ma.rates_parse_32nds({"text": text})["value"]) == x


def test_a3_spot_date_good_and_at_least_t_plus_1() -> None:
    rng = random.Random(7)
    start = date(2026, 1, 1)
    for _ in range(500):
        hol = {
            c: [(start + timedelta(days=rng.randrange(400))).isoformat() for _ in range(15)]
            for c in ("EUR", "USD", "JPY", "CAD")
        }
        t = start + timedelta(days=rng.randrange(365))
        for pair in ("EURUSD", "USDJPY", "EURJPY", "USDCAD"):
            s = date.fromisoformat(
                ma.fx_spot_date({"holidays": hol, "pair": pair, "trade_date": t.isoformat()})[
                    "spot_date"
                ]
            )
            assert s >= t + timedelta(days=1)
            for c in {pair[:3], pair[3:], "USD"}:
                assert s.weekday() < 5 and s.isoformat() not in hol[c]


def test_a3_auction_volume_maximal() -> None:
    rng = random.Random(11)
    for _ in range(300):
        orders = [
            {
                "limit": "MARKET"
                if rng.random() < 0.1
                else f"{rng.randrange(990, 1011) / 100:.2f}",
                "qty": rng.randrange(1, 500),
                "side": rng.choice(("BUY", "SELL")),
            }
            for _ in range(rng.randrange(1, 12))
        ]
        tie = rng.choice(("CBOE", "IEX"))
        out = ma.auction_uncross(
            {
                "orders": orders,
                "phase": "OPEN",
                "ref_price": "10.00",
                "tick_size": "0.01",
                "tie_break": tie,
            }
        )
        best = 0
        for k in range(990, 1011):
            p = Decimal(k) / 100
            b = sum(
                o["qty"]
                for o in orders
                if o["side"] == "BUY" and (o["limit"] == "MARKET" or Decimal(o["limit"]) >= p)
            )
            s = sum(
                o["qty"]
                for o in orders
                if o["side"] == "SELL" and (o["limit"] == "MARKET" or Decimal(o["limit"]) <= p)
            )
            best = max(best, min(b, s))
        has_limit = any(o["limit"] != "MARKET" for o in orders)
        assert out["volume"] == (best if has_limit else 0)
        filled = sum(f["qty"] for f in out["fills"])
        assert filled == 2 * out["volume"]
        rest = sum(r["qty"] for r in out["residual"])
        cancelled = sum(
            o["qty"] - sum(f["qty"] for f in out["fills"] if f["id"] == oid)
            for oid, o in _ids(orders).items()
            if oid in out["cancelled"]
        )
        assert filled + rest + cancelled == sum(o["qty"] for o in orders)  # quantity conserved
        for fl in out["fills"]:  # no fill worse than its limit
            o = _ids(orders)[fl["id"]]
            if o["limit"] != "MARKET":
                lim = Decimal(o["limit"])
                assert (
                    Decimal(fl["price"]) <= lim
                    if o["side"] == "BUY"
                    else Decimal(fl["price"]) >= lim
                )


def _ids(orders: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out, nb, ns = {}, 0, 0
    for o in orders:
        if o["side"] == "BUY":
            nb += 1
            out[f"b{nb}"] = o
        else:
            ns += 1
            out[f"a{ns}"] = o
    return out


# ------------------------------------------------------------------ paths the goldens do not reach


def test_fut_run_reuses_lit_engine() -> None:
    ev = [
        {
            "id": "S1",
            "op": "NEW",
            "price": "110-16",
            "qty": "3",
            "side": "SELL",
            "trader": "M",
            "type": "LIMIT",
        },
        {
            "id": "B1",
            "op": "NEW",
            "price": "110-16",
            "qty": "3",
            "side": "BUY",
            "trader": "P",
            "type": "LIMIT",
        },
        {
            "id": "S2",
            "op": "NEW",
            "price": "110-17+",
            "qty": "3",
            "side": "SELL",
            "trader": "P",
            "type": "LIMIT",
        },
        {
            "id": "B2",
            "op": "NEW",
            "price": "110-17+",
            "qty": "3",
            "side": "BUY",
            "trader": "N",
            "type": "LIMIT",
        },
    ]
    out = ma.fut_run({"contract": {"symbol": "ZN"}, "events": ev, "fee_per_contract": "1.00"})
    assert out["label"] == ma.RATES_LABEL
    assert out["pnl"]["P"] == "134.625"  # HR-102 round trip, same as fut_h-0005
    assert out["fills"][0]["price"] == "110.5"
    with pytest.raises(QfError) as e:
        ma.fut_run({"events": [dict(ev[0], price="110-162")]})
    assert e.value.code == "E_DOMAIN"


def test_more_paths() -> None:
    assert "label" not in ma.eq_round_price({"price": "5", "side": "BUY"})
    assert (
        ma.auction_uncross(
            {
                "orders": [],
                "phase": "OPEN",
                "ref_price": "1",
                "tick_size": "0.01",
                "data_source": "IEX",
            }
        )["label"]
        == ma.IEX_LABEL
    )
    assert (
        ma.eq_fee_check({"price": "20", "taker_fee": "0.01", "cap_check": False})["cap"] == "0.001"
    )
    assert (
        ma.rates_bond_price({"coupon": "0", "frequency": 1, "periods": 1, "yield": "0"})["price"]
        == "100"
    )
    assert ma.fut_variation(
        {"price": "110-00", "qty": 2, "settlements": ["110-01", "110-00"], "side": "SELL"}
    )["variation_margin"] == ["-62.5", "62.5"]
    assert (
        ma.fx_spot_date(
            {"pair": "USDCAD", "trade_date": "2026-11-25", "holidays": {"USD": ["2026-11-26"]}}
        )["spot_date"]
        == "2026-11-27"
    )
    for bad, code in (
        ({"price": "1", "side": "BUY", "tick_table": [["1", "0.01"]]}, "E_INPUT"),
        ({"price": "1", "side": "BUY", "tick_table": [["0", "0"]]}, "E_DOMAIN"),
        ({"price": "1", "side": "BUY", "tick_tier": "X"}, "E_SCHEMA"),
        ({"price": 1, "side": "BUY"}, "E_SCHEMA"),
    ):
        with pytest.raises(QfError) as e:
            ma.eq_round_price(bad)
        assert e.value.code == code
    with pytest.raises(QfError) as e:
        ma.eq_settle_date({"trade_date": "2026-13-01"})
    assert e.value.code == "E_SCHEMA"


def test_hr93_asset_class_dark_and_sor() -> None:
    cfg = {"lot_size": "1", "tick_size": "0.01", "p_firm": "1", "seed": 1}
    for cls in ("FX", "RATES"):
        with pytest.raises(QfError) as e:
            dark_pool.run(dict(cfg, asset_class=cls), [])
        assert e.value.code == "E_INPUT"
    assert dark_pool.run(dict(cfg, asset_class="EQUITY"), [])["label"]
    base = {
        "S": "4",
        "f": "0.3",
        "h": "0.5",
        "lambda_o": "1",
        "lambda_u": "1",
        "theta": "0",
        "lit_samples": [["0"], ["4"]],
        "asset_class": "FX",
        "venues": [
            {"Q": "0", "as": "0", "kind": "LIT", "r": "0.2", "asset_class": "FX"},
            {"as": "0.1", "kind": "DARK", "r": "0", "tail": ["0.5", "0"], "asset_class": "FX"},
        ],
    }
    with pytest.raises(QfError) as e:
        sor.allocate(base)
    assert e.value.code == "E_INPUT"


def test_last_look_draw_reproducible() -> None:
    from quantforge_core.rng import Xoshiro256

    inp = {
        "mid_after": "1.0852",
        "p_random_reject": "0.5",
        "pair": "EURUSD",
        "qty": "1",
        "quote": {"ask": "1.0852", "bid": "1.0850", "quote_mid": "1.0851"},
        "side": "BUY",
        "threshold_pips": "2",
        "seed": 7,
        "request_index": 5,
    }
    out = ma.fx_request(inp)
    assert out["u"] == Xoshiro256.seeded(7, 5).uniform()
    assert out == ma.fx_request(inp)
    with pytest.raises(QfError) as e:
        ma.fx_request(dict(inp, request_index=-1))
    assert e.value.code == "E_LIMIT"


def test_session_conservation_and_phase_order() -> None:
    ev = [
        {
            "id": "B1",
            "op": "NEW",
            "qty": "5",
            "side": "BUY",
            "trader": "A",
            "type": "LIMIT",
            "price": "1.00",
        },
        {
            "id": "S1",
            "op": "NEW",
            "qty": "5",
            "side": "SELL",
            "trader": "B",
            "type": "LIMIT",
            "price": "1.01",
        },
        {"id": "S1", "op": "CANCEL"},
    ]
    out = lit_matching.run(
        "0.01", "1", ev, {"maker_rebate": "0", "taker_fee": "0"}, {"ref_price": "1"}
    )
    assert out["phase"] == "PRE_OPEN" and out["auctions"] == []
    assert out["conservation"]["B1"]["resting"] == "5"
    assert out["conservation"]["S1"]["cancelled"] == "5"
    ev2 = ev[:2] + [{"op": "PHASE", "phase": "CONTINUOUS"}]
    out = lit_matching.run(
        "0.01", "1", ev2, {"maker_rebate": "0", "taker_fee": "0"}, {"ref_price": "1"}
    )
    assert out["auctions"][0]["price"] is None and len(out["book"]["bids"]) == 1
