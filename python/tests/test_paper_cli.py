"""Paper trading over the CLI (cli-contract.md, "Stage H paper trading operations"): the paths the pt_h
goldens do not reach, and live mode (spec pt_h-0018), which the runner cannot pin (acceptance test A5)."""

import json
from typing import Any

import pytest

from quantforge_core.cli.main import run_case

LSTAR = {
    "max_order_qty": "10",
    "max_notional": "1000",
    "max_abs_position": "5",
    "price_band": "0.05",
    "max_orders_per_day": 3,
}
LIT = {"tick_size": "0.5", "lot_size": "1", "fee_schedule": {"maker_rebate": "0", "taker_fee": "0"}}
SNAP = {"bids": [["99.5", "4"]], "asks": [["100.5", "2"]]}
ORDER = {"order_id": "O1", "symbol": "X", "side": "BUY", "type": "LIMIT", "quantity": "3"}


def call(op: str, inputs: dict[str, Any]) -> dict[str, Any]:
    doc = {"schema_version": "1.0", "case_id": "t", "operation": op, "inputs": inputs}
    out: dict[str, Any] = json.loads(json.dumps(run_case(json.dumps(doc))))
    return out


def code(op: str, inputs: dict[str, Any]) -> str:
    r = call(op, inputs)
    assert r["status"] == "error", r
    return str(r["error"]["code"])


def ok(op: str, inputs: dict[str, Any]) -> dict[str, Any]:
    r = call(op, inputs)
    assert r["status"] == "ok", r
    out: dict[str, Any] = r["outputs"]
    assert out["label"] == "crypto venue; simulated"
    return out


def pre(**order: Any) -> dict[str, Any]:
    o = {"side": "BUY", "type": "LIMIT", "quantity": "3", "limit_price": "101", **order}
    return {"order": o, "ref_price": "100", "cash": "10000", "limits": LSTAR}


def session(*steps: dict[str, Any], **kw: Any) -> dict[str, Any]:
    return {"cash": "10000", "limits": LSTAR, "lit": LIT, "script": list(steps), **kw}


def submit(**order: Any) -> dict[str, Any]:
    return {"op": "SUBMIT", "ts": "T1", "order": {**ORDER, **order}, "snapshot": SNAP}


def test_live_mode_is_refused_everywhere() -> None:  # pt_h-0018, HR-42
    assert code("paper.pretrade.check", pre(mode="live")) == "E_UNSUPPORTED_OPERATION"
    live = session(submit(limit_price="101", mode="live"))
    assert code("paper.session.run", live) == "E_UNSUPPORTED_OPERATION"
    assert ok("paper.pretrade.check", pre(mode="simulated"))["accepted"]


def test_pretrade_schema_and_domain() -> None:
    assert code("paper.pretrade.check", {**pre(), "ref_price": 100}) == "E_SCHEMA"
    assert code("paper.pretrade.check", pre(limit_price=101)) == "E_SCHEMA"
    assert code("paper.pretrade.check", pre(type="STOP")) == "E_INPUT"
    assert code("paper.pretrade.check", pre(limit_price="0")) == "E_DOMAIN"
    lim = {k: v for k, v in LSTAR.items() if k != "price_band"}
    assert code("paper.pretrade.check", {**pre(), "limits": lim}) == "E_SCHEMA"
    for bad in ({**LSTAR, "max_orders_per_day": "3"}, {**LSTAR, "kill_switch": "no"}):
        assert code("paper.pretrade.check", {**pre(), "limits": bad}) == "E_SCHEMA"
    market = pre(type="MARKET", side="SELL")
    assert ok("paper.pretrade.check", market)["reasons"] == []


def test_book_and_day_errors() -> None:
    fill = {"side": "BUY", "quantity": "1", "price": "100"}
    assert ok("paper.book.apply_fill", {"fills": [fill]})["cash_delta"] == "-100"
    assert code("paper.book.apply_fill", {"fills": [1]}) == "E_SCHEMA"
    assert code("paper.book.apply_fill", {"fills": [{**fill, "side": "HOLD"}]}) == "E_INPUT"
    assert code("paper.book.apply_fill", {"fills": [{"side": "BUY", "price": "1"}]}) == "E_SCHEMA"
    assert code("paper.book.end_of_day", {"cash_open": "1", "fills": [fill]}) == "E_SCHEMA"
    neg = {"cash_open": "1", "position_open": "1", "prev_close": "-1", "close": "1"}
    assert code("paper.book.end_of_day", neg) == "E_DOMAIN"
    assert code("paper.book.end_of_day", {"cash_open": 1}) == "E_SCHEMA"


def test_ledger_append_and_verify() -> None:
    rec = ok("paper.ledger.append", {"seq": 0, "ts": "T", "kind": "EOD", "body": {"x": "é"}})
    assert rec["canonical_bytes"].endswith('"seq":0,"ts":"T"}')
    assert "\\u00e9" in rec["canonical_bytes"]
    line = json.dumps(rec["record"], sort_keys=True, separators=(",", ":"))
    good = ok("paper.ledger.verify", {"text": line + "\n"})
    assert good["ok"] and good["head"] == rec["hash"] and good["records"] == 1
    empty = ok("paper.ledger.verify", {"text": ""})
    assert empty["ok"] and empty["records"] == 0 and empty["head"] == "0" * 64
    assert ok("paper.ledger.verify", {"text": "[1]\n"})["reason"] == "PARSE"
    assert (
        code("paper.ledger.append", {"seq": -1, "ts": "T", "kind": "EOD", "body": {}}) == "E_DOMAIN"
    )
    body = {"seq": 0, "ts": "T", "kind": "EOD", "body": {"n": 1}}
    assert code("paper.ledger.append", body) == "E_INPUT"


def test_session_cancel_resting_and_close() -> None:
    ioc = submit(type="IOC", limit_price="100.5")
    rest = submit(order_id="O2", limit_price="99", quantity="1")
    close = {"op": "CLOSE", "ts": "T2", "prev_marks": {}, "marks": {"X": "100"}}
    out = ok("paper.session.run", session(ioc, rest, close))
    kinds = [r["kind"] for r in out["records"]]
    assert kinds == ["ORDER", "FILL", "CANCEL", "ORDER", "TCA", "CANCEL", "TCA", "EOD"]
    assert out["results"][0] == {"status": "DONE", "filled": "2"}
    assert out["results"][1] == {"status": "OPEN", "filled": "0"}
    assert out["positions"] == {"X": "2"} and out["head"] == out["records"][-1]["hash"]
    text = "".join(
        json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n" for r in out["records"]
    )
    assert ok("paper.ledger.verify", {"text": text})["ok"]


@pytest.mark.parametrize(
    ("inputs", "want"),
    [
        (session({"op": "WAIT", "ts": "T"}), "E_SCHEMA"),
        (session({"op": "SUBMIT"}), "E_SCHEMA"),
        (session({"op": "SUBMIT", "ts": "T", "order": ORDER}), "E_SCHEMA"),
        (session(submit(order_id=None, limit_price="101")), "E_SCHEMA"),
        (session({"op": "CLOSE", "ts": "T", "days": "1"}), "E_SCHEMA"),
        (session(submit(venue="DARK", limit_price="101")), "E_SCHEMA"),
        (session(submit(venue="SOR", limit_price="101")), "E_SCHEMA"),
        (session(submit(limit_price="101"), submit(limit_price="101")), "E_INPUT"),
        ({**session(), "cash": 10000}, "E_SCHEMA"),
        ({**session(), "lit": {"tick_size": "1"}}, "E_SCHEMA"),
    ],
)
def test_session_errors(inputs: dict[str, Any], want: str) -> None:
    assert code("paper.session.run", inputs) == want
