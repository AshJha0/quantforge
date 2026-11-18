"""H-21 paper trading: goldens pt_h-0001..0023 and acceptance tests A1-A6, A8
(specifications/10-execution/paper-trading.md)."""

import ast
import json
import pathlib
import random
from decimal import Decimal as D

import pytest

from quantforge_core import paper
from quantforge_core.errors import QfError

L = {"max_order_qty": "10", "max_notional": "1000", "max_abs_position": "5", "price_band": "0.05",
     "max_orders_per_day": 3, "kill_switch": False, "allow_short": True}


def day1():
    b = paper.Book(cash=D(10000))
    fills = [{"symbol": "BTC-USD", "side": "BUY", "quantity": "2", "price": "100", "fee": "0.20"},
             {"symbol": "BTC-USD", "side": "SELL", "quantity": "1", "price": "110", "fee": "0.11"}]
    return b, fills


def test_pt_0001_fills():
    b, fills = day1()
    for f in fills:
        b.apply_fill(f["symbol"], f["side"], f["quantity"], f["price"], f["fee"])
    p = b.pos("BTC-USD")
    assert (b.cash, p.n, p.c, b.realised, b.fees) == (D("9909.69"), 1, 100, 10, D("0.31"))


def test_pt_0002_0003_explain():
    b, fills = day1()
    r = paper.end_of_day(b, fills, {}, {"BTC-USD": "105"})
    assert (r["market"], r["trading"], r["fees"], r["financing"], r["total"], r["nav"]) == (
        0, 15, D("-0.31"), 0, D("14.69"), D("10014.69"))
    assert r["label"] == paper.LABEL
    r = paper.end_of_day(b, [], {"BTC-USD": "105"}, {"BTC-USD": "102"}, cash_rate="0.0365")
    assert (r["financing"], r["market"], r["total"], b.cash, r["nav"]) == (
        D("0.99"), -3, D("-2.01"), D("9910.68"), D("10012.68"))


def test_pt_0004_short_financing():
    f = paper.financing("10100", [("-2", "50")], 1, cash_rate="0.0365", borrow_rate="0.0730")
    assert (f["interest"], f["borrow"], f["financing"]) == (D("1.01"), D("-0.02"), D("0.99"))


def test_pt_0005_cross_zero():
    b = paper.Book(cash=D(0))
    b.apply_fill("X", "BUY", "1", "100")
    b.apply_fill("X", "SELL", "3", "90")
    p = b.pos("X")
    assert (p.n, p.c, b.realised) == (-2, 90, -10)


def test_pt_0006_debit():
    assert paper.financing("-1000", [], 3, debit_rate="0.0730")["financing"] == D("-0.60")


@pytest.mark.parametrize("case,order,kw,limits,reasons", [
    ("0010", {"side": "BUY", "type": "LIMIT", "quantity": "3", "limit_price": "101"}, {}, {}, []),
    ("0011", {"side": "BUY", "type": "LIMIT", "quantity": "11", "limit_price": "100"}, {}, {},
     ["MAX_QTY", "MAX_NOTIONAL", "MAX_POSITION"]),
    ("0012", {"side": "BUY", "type": "LIMIT", "quantity": "3", "limit_price": "106"}, {}, {}, ["PRICE_BAND"]),
    ("0013", {"side": "SELL", "type": "LIMIT", "quantity": "10", "limit_price": "100"}, {"position": "4"}, {},
     ["MAX_POSITION"]),
    ("0014", {"side": "BUY", "type": "MARKET", "quantity": "3"}, {"cash": "300"}, {}, ["INSUFFICIENT_CASH"]),
    ("0015", {"side": "BUY", "type": "LIMIT", "quantity": "3", "limit_price": "101"}, {"orders_today": 3}, {},
     ["MAX_ORDERS"]),
    ("0016", {"side": "BUY", "type": "LIMIT", "quantity": "3", "limit_price": "101"}, {}, {"kill_switch": True},
     ["KILL_SWITCH"]),
    ("0017", {"side": "SELL", "type": "LIMIT", "quantity": "2", "limit_price": "100"}, {"position": "1"},
     {"allow_short": False}, ["NO_SHORT"]),
])
def test_pretrade_goldens(case, order, kw, limits, reasons):
    args = {"ref_price": "100", "position": "0", "cash": "10000", "orders_today": 0} | kw
    r = paper.pretrade_check(order, limits=L | limits, **args)
    assert r["reasons"] == reasons and r["accepted"] == (not reasons), case


def test_pt_0018_live_refused():
    order = {"side": "BUY", "type": "LIMIT", "quantity": "3", "limit_price": "101", "mode": "live"}
    with pytest.raises(QfError) as e:
        paper.pretrade_check(order, "100", "0", "10000", 0, L)
    assert e.value.code == "E_UNSUPPORTED_OPERATION"


BODY = {"order_id": "O1", "symbol": "BTC-USD", "side": "BUY", "type": "LIMIT", "quantity": "3",
        "limit_price": "101"}
TS = "2026-11-18T00:00:01Z"


def test_pt_0020_hash():
    led = paper.Ledger()
    rec = led.append("ORDER", TS, BODY)
    assert paper.canonical(rec) == (
        b'{"body":{"limit_price":"101","order_id":"O1","quantity":"3","side":"BUY","symbol":"BTC-USD",'
        b'"type":"LIMIT"},"kind":"ORDER","label":"crypto venue; simulated","prev":"' + b"0" * 64
        + b'","seq":0,"ts":"2026-11-18T00:00:01Z"}')
    assert rec["hash"] == "72c85984abb1b7c4072c65dbba0567b3de51279645b0ad63cfd242137aed7e81"
    assert paper.verify(led.text())["ok"]


def test_pt_0021_0022_0023_tamper():
    led = paper.Ledger()
    led.append("ORDER", TS, BODY)
    assert paper.verify(led.text().replace('"101"', '"102"'))["reason"] == "HASH"
    led.append("FILL", TS, {"order_id": "O1", "quantity": "3", "price": "101"})
    rec = json.loads(led.lines[1])
    rec["prev"] = paper.GENESIS
    rec["hash"] = paper.record_hash(rec)
    r = paper.verify(led.lines[0] + "\n" + json.dumps(rec) + "\n")
    assert (r["ok"], r["first_bad_seq"], r["reason"]) == (False, 1, "LINK")
    rec = json.loads(led.lines[0])
    del rec["label"]
    rec["hash"] = paper.record_hash(rec)
    r = paper.verify(json.dumps(rec) + "\n")
    assert (r["first_bad_seq"], r["reason"]) == (0, "LABEL")


def test_a1_any_byte_flip_detected():
    rng = random.Random(21)
    led = paper.Ledger()
    for i in range(300):
        led.append(rng.choice(paper.KINDS), TS, {"i": str(i), "px": str(rng.randint(1, 9999))})
    text = led.text()
    assert paper.verify(text)["records"] == 300
    for _ in range(200):
        k = rng.randrange(len(led.lines))
        line = led.lines[k]
        j = rng.randrange(len(line))
        flipped = line[:j] + chr(ord(line[j]) ^ 1) + line[j + 1:]
        lines = led.lines[:k] + [flipped] + led.lines[k + 1:]
        r = paper.verify("\n".join(lines))
        assert not r["ok"] and r["first_bad_seq"] <= k
    trunc = paper.verify("\n".join(led.lines[:-1]))
    assert trunc["ok"] and trunc["head"] != led.head  # truncation shows only against the head (HR-46)


def test_a1_floats_refused():
    with pytest.raises(QfError):
        paper.Ledger().append("FILL", TS, {"price": 1.5})
    with pytest.raises(QfError):
        paper.Ledger().append("NOPE", TS, {})


def test_a2_a3_random_reconcile_and_explain():
    rng = random.Random(7)
    for _ in range(50):
        b = paper.Book(cash=D(100000))
        prev: dict[str, str] = {}
        for _day in range(5):
            marks = {"A": str(rng.randint(50, 150)), "B": str(D(rng.randint(100, 900)) / 10)}
            fills = [{"symbol": rng.choice("AB"), "side": rng.choice(["BUY", "SELL"]),
                      "quantity": str(rng.randint(1, 7)), "price": str(D(rng.randint(500, 1500)) / 10),
                      "fee": str(D(rng.randint(0, 50)) / 100)} for _ in range(rng.randint(0, 6))]
            nav0 = b.nav(prev) if any(p.n for p in b.positions.values()) else b.cash
            r = paper.end_of_day(b, fills, prev, marks, cash_rate="0.03", debit_rate="0.08",
                                 borrow_rate="0.05")
            assert r["total"] == b.nav(marks) - nav0
            prev = marks


def test_a4_accepted_never_breaches_position():
    rng = random.Random(3)
    for _ in range(2000):
        pos = D(rng.randint(-5, 5))
        order = {"side": rng.choice(["BUY", "SELL"]), "type": "LIMIT",
                 "quantity": str(rng.randint(1, 12)), "limit_price": str(rng.randint(90, 110))}
        r = paper.pretrade_check(order, "100", pos, "100000", 0, L)
        if r["accepted"]:
            assert abs(pos + paper.SIDES[order["side"]] * D(order["quantity"])) <= 5


def test_a5_no_network_imports():
    src = pathlib.Path(paper.__file__).read_text(encoding="utf-8")
    names = {a.name.split(".")[0] for n in ast.walk(ast.parse(src))
             if isinstance(n, (ast.Import, ast.ImportFrom)) for a in n.names}
    mods = {n.module.split(".")[0] for n in ast.walk(ast.parse(src))
            if isinstance(n, ast.ImportFrom) and n.module}
    banned = {"socket", "http", "urllib", "requests", "httpx", "aiohttp", "websocket", "websockets", "ssl"}
    assert not (names | mods) & banned


def test_a8_deterministic():
    def build():
        led = paper.Ledger()
        for i in range(20):
            led.append("ORDER", TS, {"order_id": f"O{i}", "quantity": str(i + 1)})
        return led.text()
    assert build() == build()


def test_input_errors():
    with pytest.raises(QfError) as e:
        paper.Book(cash=D(0)).apply_fill("X", "BUY", "0", "1")
    assert e.value.code == "E_DOMAIN"
    with pytest.raises(QfError) as e:
        paper.pretrade_check({"side": "HOLD", "type": "LIMIT", "quantity": "1"}, "1", "0", "1", 0, L)
    assert e.value.code == "E_INPUT"
    with pytest.raises(QfError) as e:
        paper.pretrade_check({"side": "BUY", "type": "LIMIT", "quantity": "1"}, "1", "0", "1", 0, L)
    assert e.value.code == "E_SCHEMA"
    assert paper.verify("not json\n")["reason"] == "PARSE"
    assert paper.verify("")["ok"]
