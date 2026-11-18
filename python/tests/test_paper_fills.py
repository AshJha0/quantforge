"""H-21 paper fills (HR-47), routing and per-order TCA (HR-55): acceptance test A7 and the
fill paths (specifications/10-execution/paper-trading.md). Synthetic books only."""

import ast
import json
import pathlib
from decimal import Decimal as D
from typing import Any

import pytest

from quantforge_core import paper, paper_fills
from quantforge_core.errors import QfError

GOLD = pathlib.Path(__file__).resolve().parents[2] / "datasets" / "golden" / "stage_h"
TS = "2026-11-18T10:00:00Z"
LIMITS = {
    "max_order_qty": "20",
    "max_notional": "10000",
    "max_abs_position": "50",
    "price_band": "0.05",
    "max_orders_per_day": 10,
    "kill_switch": False,
    "allow_short": True,
}
LIT = {
    "tick_size": "0.5",
    "lot_size": "1",
    "fee_schedule": {"taker_fee": "0.001", "maker_rebate": "0.0002"},
}
DARK = {"tick_size": "0.5", "lot_size": "1", "p_firm": "1", "firm_delay": 0, "seed": 1}
SNAP = {"ts": TS, "symbol": "BTC-USD", "bids": [["99", "5"]], "asks": [["101", "2"], ["102", "3"]]}


def _cases(name: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = json.loads((GOLD / f"{name}.json").read_text(encoding="utf-8"))[
        "cases"
    ]
    return out


GOLDEN = [
    (v, c)
    for v, n in (("LIT", "lit_h"), ("DARK", "dark_h"), ("SOR", "sor_h"))
    for c in _cases(n)
    if v != "DARK" or "config" in c["inputs"]
]


@pytest.mark.parametrize(
    ("venue", "case"), GOLDEN, ids=lambda x: x if isinstance(x, str) else x["case_id"]
)
def test_a7_venue_goldens_through_paper_path(venue: str, case: dict[str, Any]) -> None:
    exp = case["expected"]
    if exp["status"] == "error":
        with pytest.raises(QfError) as e:
            paper_fills.venue_run(venue, case["inputs"])
        assert e.value.code == exp["error_code"]
    else:
        assert paper_fills.venue_run(venue, case["inputs"]) == exp["outputs"]


def order(oid: str, **kw: Any) -> dict[str, Any]:
    o = {
        "order_id": oid,
        "symbol": "BTC-USD",
        "side": "BUY",
        "type": "IOC",
        "quantity": "4",
        "limit_price": "102",
        "venue": "LIT",
    }
    o.update(kw)
    return o


def records(s: paper_fills.Session, kind: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = [
        r["body"] for r in map(json.loads, s.ledger.lines) if r["kind"] == kind
    ]
    return out


def run_day() -> paper_fills.Session:
    s = paper_fills.Session("10000", LIMITS, LIT, DARK)
    s.submit(order("O1"), TS, SNAP)  # IOC walks two levels
    s.submit(order("O2", type="LIMIT", limit_price="100", quantity="3"), TS, SNAP)  # rests
    s.submit(
        order("O3", side="SELL", venue="DARK", type="LIMIT", limit_price="99", quantity="5"),
        TS,
        SNAP,
        contra=[{"op": "NEW", "id": "C1", "side": "BUY", "qty": "3", "kind": "FIRM"}],
    )
    router = {
        "h": "0.5",
        "f": "0.3",
        "theta": "0",
        "lambda_u": "1",
        "lambda_o": "1",
        "lit_samples": [["0"]],
        "venues": [
            {"kind": "LIT", "Q": "0", "r": "0.2", "as": "0"},
            {"kind": "DARK", "r": "0.1", "as": "0", "tail": ["1", "1"]},
        ],
    }
    s.submit(
        order("O4", venue="SOR", quantity="3"),
        TS,
        SNAP,
        contra=[{"op": "NEW", "id": "C2", "side": "SELL", "qty": "1", "kind": "FIRM"}],
        router=router,
    )
    s.submit(order("O5", quantity="999"), TS, SNAP)  # rejected
    s.close_day("2026-11-19T00:00:00Z", {}, {"BTC-USD": "103"})
    return s


def test_lit_walk_fees_dark_mid_sor_and_tca() -> None:
    s = run_day()
    fills = records(s, "FILL")
    o1 = [(f["quantity"], f["price"], f["fee"]) for f in fills if f["order_id"] == "O1"]
    assert o1 == [("2", "101", "0.202"), ("2", "102", "0.204")]
    o3 = [(f["quantity"], f["price"], f["venue"]) for f in fills if f["order_id"] == "O3"]
    assert o3 == [("3", "100", "DARK")]
    o4 = [f for f in fills if f["order_id"] == "O4"]
    assert sum(D(f["quantity"]) for f in o4) <= 3 and all(
        f["child_id"].startswith("O4.") for f in o4
    )
    assert [r["order_id"] for r in records(s, "CANCEL")] == ["O3", "O2"] or {
        r["order_id"] for r in records(s, "CANCEL")
    } >= {"O2", "O3"}
    assert records(s, "REJECT")[0]["reasons"] == [
        "MAX_QTY",
        "MAX_NOTIONAL",
        "MAX_POSITION",
        "INSUFFICIENT_CASH",
    ]
    tca = records(s, "TCA")
    assert sorted(t["order_id"] for t in tca) == ["O1", "O2", "O3", "O4"]  # one per final order
    for t in tca:
        parts = sum(float(t[k]) for k in ("delay", "execution", "opportunity"))
        fees = sum(float(f["fee"]) for f in fills if f["order_id"] == t["order_id"])
        assert abs(parts + fees - float(t["total"])) <= 1e-10
    o1t = next(t for t in tca if t["order_id"] == "O1")
    assert D(o1t["execution"]) == D(2 * 1 + 2 * 2)  # mid 100: (101-100)*2 + (102-100)*2
    assert paper.verify(s.ledger.text())["ok"]
    nav = s.book.nav({"BTC-USD": "103"})
    assert records(s, "EOD")[0]["nav"] == format(nav.normalize(), "f")


def test_a8_session_deterministic() -> None:
    assert run_day().ledger.text() == run_day().ledger.text()


def test_errors_and_live_mode() -> None:
    s = paper_fills.Session("10000", LIMITS, LIT)
    with pytest.raises(QfError) as e:
        s.submit(order("X", mode="live"), TS, SNAP)
    assert e.value.code == "E_UNSUPPORTED_OPERATION"
    with pytest.raises(QfError):
        s.submit(order("X", venue="NYSE"), TS, SNAP)
    with pytest.raises(QfError):
        s.submit(order("Y", venue="DARK"), TS, SNAP)  # no dark config
    with pytest.raises(QfError):
        s.submit(order("Z", venue="SOR"), TS, SNAP)  # no router input
    with pytest.raises(QfError):
        paper_fills.mid({"bids": [], "asks": [["1", "1"]]})
    with pytest.raises(QfError):
        paper_fills.venue_run("X", {})


def test_market_order_and_post_only_reject() -> None:
    s = paper_fills.Session("10000", LIMITS, LIT)
    assert s.submit(order("M", type="MARKET", quantity="1"), TS, SNAP)["filled"] == "1"
    r = s.submit(order("P", type="POST_ONLY", limit_price="101", quantity="1"), TS, SNAP)
    assert r == {"status": "DONE", "filled": "0"}


def test_loader_labels_local_file(tmp_path: pathlib.Path) -> None:
    p = tmp_path / "snaps.jsonl"
    p.write_text(json.dumps(SNAP) + "\n\n", encoding="utf-8")
    snaps = paper_fills.load_snapshots(p)
    assert snaps[0]["label"] == "crypto venue; simulated" and paper_fills.mid(snaps[0]) == 100
    p.write_text("[1]\n", encoding="utf-8")
    with pytest.raises(QfError):
        paper_fills.load_snapshots(p)


def test_a5_no_network_in_paper_fills() -> None:
    tree = ast.parse(pathlib.Path(paper_fills.__file__).read_text(encoding="utf-8"))
    mods = {
        a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names
    }
    mods |= {
        n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module
    }
    assert not mods & {
        "socket",
        "http",
        "urllib",
        "requests",
        "httpx",
        "aiohttp",
        "websockets",
        "ssl",
    }
