"""Stage H wave 2: MBP book rebuild and the simulated lit matching engine (unit and property tests).
The golden value cases run in test_conformance.py; these cover the paths the goldens do not."""

import zlib
from decimal import Decimal
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from quantforge_core.errors import QfError
from quantforge_core.lit_matching import LABEL, fmt, run
from quantforge_core.order_book import rebuild

NOFEE = {"maker_rebate": "0", "taker_fee": "0"}


def snap(bids: Any, asks: Any, checksum: int | None = None, **kw: Any) -> dict[str, Any]:
    return {"type": "snapshot", "bids": bids, "asks": asks, "checksum": checksum, **kw}


def upd(bids: Any, asks: Any, checksum: int | None = None, **kw: Any) -> dict[str, Any]:
    return {"type": "update", "bids": bids, "asks": asks, "checksum": checksum, **kw}


# ------------------------------------------------------------------ order book


def test_checksum_match_and_fail_are_counted_not_raised() -> None:
    good = zlib.crc32(b"1010210001")  # asks ascending then bids descending, [KR-CRC]
    m0 = snap([["100.0", "1"]], [["101.0", "2"]], checksum=good)
    out = rebuild([m0, upd([], [], checksum=(good + 1) % 2**32)], 10, 1, 0)
    assert out["crc32"] == good
    assert out["stats"]["checksum_checked"] == 2
    assert out["stats"]["checksum_failed"] == 1
    assert out["events"] == [{"i": 1, "kind": "CHECKSUM_FAIL"}]


def test_resync_counts_only_a_marked_resubscribe_after_failure() -> None:
    m0 = snap([["100.0", "1"]], [], checksum=0)
    assert (
        rebuild([m0, snap([["100.0", "1"]], [], resubscribe=True)], 10, 1, 0)["stats"]["resyncs"]
        == 1
    )
    assert rebuild([m0, snap([["100.0", "1"]], [])], 10, 1, 0)["stats"]["resyncs"] == 0


def test_snapshot_skips_zero_levels_and_truncates() -> None:
    bids = [[f"{100 - k}.0", "1"] for k in range(12)] + [["50.0", "0"]]
    out = rebuild([snap(bids, [])], 10, 1, 0)
    assert len(out["book"]["bids"]) == 10
    assert out["stats"]["truncated_levels"] == 2


def test_checkpoints_compare_top_levels() -> None:
    msgs = [
        snap([["100.0", "1"]], [["101.0", "1"]], t="2026-01-01T00:00:00Z"),
        upd([["100.0", "2"]], [], t="2026-01-01T00:00:02Z"),
    ]
    cps = [
        {"t": "2026-01-01T00:00:01Z", "bids": [["100.0", "1.0"]], "asks": [["101.0", "1"]]},
        {"t": "2026-01-01T00:00:03Z", "bids": [["100.0", "1"]], "asks": []},
    ]
    out = rebuild(msgs, 10, 1, 0, cps)
    assert out["stats"]["checkpoint_checked"] == 2
    assert out["stats"]["checkpoint_failed"] == 1
    assert out["events"] == [{"i": 1, "kind": "CHECKPOINT_FAIL"}]


def test_decimals_beyond_precision_are_domain_errors() -> None:
    with pytest.raises(QfError) as e:
        rebuild([snap([["100.05", "1"]], [])], 10, 1, 0)
    assert e.value.code == "E_DOMAIN"


# ------------------------------------------------------------------ lit engine


def new(
    i: str, side: str, typ: str, qty: Any, price: str | None = None, trader: str = "T", **kw: Any
) -> dict[str, Any]:
    e = {"op": "NEW", "id": i, "trader": trader, "side": side, "type": typ, "qty": qty, **kw}
    if price is not None:
        e["price"] = price
    return e


def test_label_and_decimal_format() -> None:
    assert run("1", "1", [], NOFEE)["label"] == LABEL == "simulated venue; not a real exchange"
    assert fmt(Decimal("2.6240")) == "2.624"
    assert fmt(Decimal("-0.0")) == "0"
    assert fmt(Decimal("1E+2")) == "100"


def test_iceberg_hidden_counts_for_fok_and_refreshes_at_back() -> None:
    out = run(
        "1",
        "1",
        [
            new("I", "SELL", "ICEBERG", "30", "100", display_qty="5"),
            new("L", "SELL", "LIMIT", "5", "100"),
            new("F", "BUY", "FOK", "20", "100"),
        ],
        NOFEE,
    )
    assert [(f["maker_id"], f["qty"]) for f in out["fills"]] == [
        ("I", "5"),
        ("L", "5"),
        ("I", "5"),
        ("I", "5"),
    ]
    assert out["book"]["asks"][0]["hidden_qty"] == "10"


def test_peg_mid_trades_after_displayed_at_its_price_and_post_only_sees_it() -> None:
    out = run(
        "1",
        "1",
        [
            new("B", "BUY", "LIMIT", "5", "100"),
            new("A", "SELL", "LIMIT", "5", "102"),
            new("P", "SELL", "PEG_MID", "5", "100"),  # mid 101, an ask peg rounds up: 101
            new("X", "BUY", "POST_ONLY", "1", "101"),
            new("D", "SELL", "LIMIT", "1", "101"),
            new("T", "BUY", "IOC", "3", "101"),
        ],
        NOFEE,
    )
    assert out["rejects"] == [{"id": "X", "reason": "POST_ONLY_WOULD_CROSS"}]
    assert [(f["maker_id"], f["qty"], f["price"]) for f in out["fills"]] == [
        ("D", "1", "101"),
        ("P", "2", "101"),
    ]


def test_unpriced_peg_does_not_trade_and_prices_later() -> None:
    out = run(
        "1", "1", [new("P", "BUY", "PEG_MID", "5", "200"), new("M", "SELL", "MARKET", "1")], NOFEE
    )
    assert out["fills"] == [] and out["cancelled"] == [{"id": "M", "qty": "1"}]
    assert out["book"]["bids"][0]["price"] is None
    out = run(
        "1",
        "1",
        [
            new("P", "BUY", "PEG_MID", "5", "200"),
            new("B", "BUY", "LIMIT", "1", "99"),
            new("A", "SELL", "LIMIT", "1", "104"),
        ],
        NOFEE,
    )
    assert out["book"]["bids"][0] == {
        "id": "P",
        "price": "101",
        "display_qty": "0",
        "hidden_qty": "5",
        "seq": 4,
    }


def test_cancel_and_modify_unknown_id_are_rejects() -> None:
    out = run(
        "1", "1", [{"op": "CANCEL", "id": "Q"}, {"op": "MODIFY", "id": "Q", "qty": "2"}], NOFEE
    )
    assert out["rejects"] == [{"id": "Q", "reason": "UNKNOWN_ID"}] * 2


@pytest.mark.parametrize(
    ("events", "code"),
    [
        ([new("B", "BUY", "LIMIT", "10", "100.5")], "E_DOMAIN"),
        ([new("B", "BUY", "LIMIT", "1.5", "100")], "E_DOMAIN"),
        ([new("B", "BUY", "LIMIT", 10, "100")], "E_SCHEMA"),
        ([new("B", "BUY", "STOP", "10", "100")], "E_SCHEMA"),
        ([new("B", "BUY", "MARKET", "10", "100")], "E_SCHEMA"),
        (
            [
                new("B", "BUY", "LIMIT", "10", "100"),
                {"op": "MODIFY", "id": "B", "qty": "5", "price": "99"},
            ],
            "E_SCHEMA",
        ),
    ],
)
def test_lit_errors(events: list[dict[str, Any]], code: str) -> None:
    with pytest.raises(QfError) as e:
        run("1", "1", events, NOFEE)
    assert e.value.code == code


# ------------------------------------------------------------------ property: conservation and invariants

_TYPES = ["LIMIT", "MARKET", "IOC", "FOK", "ICEBERG", "POST_ONLY", "PEG_MID", "PEG_PRIMARY"]


@st.composite
def streams(draw: Any) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    ids: list[str] = []
    for k in range(draw(st.integers(1, 40))):
        kind = draw(st.sampled_from(["NEW"] * 6 + ["CANCEL", "MODIFY"]))
        if kind == "NEW" or not ids:
            typ = draw(st.sampled_from(_TYPES))
            qty = draw(st.integers(1, 20))
            price = None if typ == "MARKET" else str(draw(st.integers(95, 105)))
            e = new(
                f"O{k}",
                draw(st.sampled_from(["BUY", "SELL"])),
                typ,
                str(qty),
                price,
                trader=draw(st.sampled_from(["T1", "T2", "T3"])),
            )
            if typ == "ICEBERG":
                e["display_qty"] = str(draw(st.integers(1, qty)))
            ids.append(e["id"])
            events.append(e)
        elif kind == "CANCEL":
            events.append({"op": "CANCEL", "id": draw(st.sampled_from([*ids, "NOPE"]))})
        else:
            events.append(
                {
                    "op": "MODIFY",
                    "id": draw(st.sampled_from(ids)),
                    "qty": str(draw(st.integers(1, 20))),
                }
            )
    return events


@settings(max_examples=300, deadline=None)
@given(streams())
def test_conservation_and_book_invariants(events: list[dict[str, Any]]) -> None:
    fees = {"maker_rebate": "0.0002", "taker_fee": "0.001"}
    out = run("1", "1", events, fees)
    assert out == run("1", "1", events, fees)  # replay determinism
    for c in out["conservation"].values():  # filled + resting + cancelled + rejected = submitted
        parts = sum(Decimal(c[k]) for k in ("filled", "resting", "cancelled", "rejected"))
        assert parts == Decimal(c["submitted"])
    total = sum(Decimal(f["qty"]) for f in out["fills"])
    assert sum(Decimal(c["filled"]) for c in out["conservation"].values()) == 2 * total
    bids = [Decimal(o["price"]) for o in out["book"]["bids"] if o["price"] is not None]
    asks = [Decimal(o["price"]) for o in out["book"]["asks"] if o["price"] is not None]
    if bids and asks:
        assert max(bids) < min(asks)  # never crossed or locked
    types = {e["id"]: e["type"] for e in events if e["op"] == "NEW"}
    for oid, c in out["conservation"].items():
        if types[oid] == "FOK":
            assert c["filled"] in ("0", c["submitted"]) and c["resting"] == "0"
    assert not any(
        types[f["taker_id"]] in ("POST_ONLY", "PEG_MID", "PEG_PRIMARY") for f in out["fills"]
    )
    assert [f["seq"] for f in out["fills"]] == list(range(1, len(out["fills"]) + 1))
    for side in ("bids", "asks"):  # the MBP projection is the MBO book's displayed quantity
        levels: dict[str, Decimal] = {}
        for o in out["book"][side]:
            if o["price"] is not None:
                levels[o["price"]] = levels.get(o["price"], Decimal(0)) + Decimal(o["display_qty"])
        assert {p: q for p, q in levels.items() if q > 0} == {
            p: Decimal(q) for p, q in out["mbp"][side]
        }


def test_fifo_within_a_price() -> None:
    ev = [new(f"B{k}", "BUY", "LIMIT", "2", "100") for k in range(5)] + [
        new("S", "SELL", "MARKET", "7")
    ]
    out = run("1", "1", ev, NOFEE)
    assert [f["maker_id"] for f in out["fills"]] == ["B0", "B1", "B2", "B3"]
    assert out["book"]["bids"][0]["id"] == "B3" and out["book"]["bids"][0]["display_qty"] == "1"


def test_mbp_projection_equals_book_rebuild_of_engine_levels() -> None:
    out = run(
        "1",
        "1",
        [
            new("B", "BUY", "LIMIT", "3", "100"),
            new("A", "SELL", "ICEBERG", "9", "102", display_qty="2"),
        ],
        NOFEE,
    )
    msg = snap(out["mbp"]["bids"], out["mbp"]["asks"])
    assert rebuild([msg], 10, 0, 0)["book"] == out["mbp"]
