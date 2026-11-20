"""AD2: hand fixtures, malformed inputs, round-trip properties and random-byte fuzzing for the five simulated
feed codecs (adapters.md section 3). Simulated; not a certified implementation; not connected to any venue."""

import json
import random
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from quantforge_adapters import LABEL
from quantforge_adapters.feeds import FeedError, fast, fix, itch, mold, ouch

FEEDS = Path(__file__).resolve().parents[3] / "datasets" / "feeds"
FIXTURES = sorted(p for p in FEEDS.rglob("*.bin"))


def _decode(fmt: str, data: bytes) -> Any:
    if fmt == "QF-FIX-S":
        return fix.decode(data)
    if fmt == "QF-ITCH-S":
        return itch.decode(data)
    if fmt == "QF-OUCH-S":
        return ouch.decode_stream(data) if data[:1] == b"\x00" else ouch.decode(data)
    if fmt == "QF-FAST-S":
        return fast.decode_packet(data)
    pkt = mold.decode(data)
    return {**pkt, "blocks": [b.hex() for b in pkt["blocks"]]}


def _encode(fmt: str, fields: dict[str, Any]) -> bytes:
    if fmt == "QF-FIX-S":
        return fix.encode(fields)
    if fmt == "QF-ITCH-S":
        return itch.encode(fields)
    if fmt == "QF-OUCH-S":
        return ouch.encode_stream(fields["messages"]) if "messages" in fields else ouch.encode(fields)
    if fmt == "QF-FAST-S":
        return fast.encode_packet(fields["messages"])
    return mold.encode({**fields, "blocks": [bytes.fromhex(b) for b in fields["blocks"]]})


def test_fixture_set_is_complete() -> None:
    assert len(FIXTURES) == 17
    assert {p.parent.name for p in FIXTURES} == {"fix", "itch", "ouch", "fast", "mold"}


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: f"{p.parent.name}/{p.stem}")
def test_fixture_decodes_and_encodes_byte_exact(path: Path) -> None:
    side = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
    data = path.read_bytes()
    assert side["label"] == LABEL
    assert data.hex() == side["hex"]
    decoded = _decode(side["format"], data)
    expected = side["fields"]["messages"] if "messages" in side["fields"] else side["fields"]
    assert decoded == expected
    assert _encode(side["format"], side["fields"]) == data


MALFORMED = json.loads((FEEDS / "malformed.json").read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize("case", MALFORMED, ids=lambda c: f"{c['format']}:{c['name']}")
def test_malformed_gives_its_code(case: dict[str, str]) -> None:
    data = bytes.fromhex(case["hex"])
    with pytest.raises(FeedError) as err:
        if case["format"] == "QF-OUCH-S" and case["name"].startswith("stream"):
            ouch.decode_stream(data)
        else:
            _decode(case["format"], data)
    assert err.value.code == case["code"], err.value.detail


# ---- round-trip properties ---------------------------------------------------------------------------------

alpha = st.text(alphabet=st.characters(min_codepoint=0x20, max_codepoint=0x7E), min_size=1, max_size=1)
u = lambda bits: st.integers(0, 2**bits - 1)
u1 = lambda bits: st.integers(1, 2**bits - 1)


def fixed(n: int) -> st.SearchStrategy[str]:
    return st.text(alphabet=st.characters(min_codepoint=0x20, max_codepoint=0x7E), min_size=n, max_size=n)


itch_msgs = st.one_of(
    st.fixed_dictionaries(
        {
            "type": st.just("S"),
            "locate": u(16),
            "tracking": u(16),
            "timestamp": u(48),
            "event": st.sampled_from("OSQMEC"),
        }
    ),
    st.fixed_dictionaries(
        {
            "type": st.just("A"),
            "locate": u(16),
            "tracking": u(16),
            "timestamp": u(48),
            "order_ref": u(64),
            "side": st.sampled_from("BS"),
            "shares": u1(32),
            "stock": fixed(8),
            "price": u(32),
        }
    ),
    st.fixed_dictionaries(
        {
            "type": st.just("E"),
            "locate": u(16),
            "tracking": u(16),
            "timestamp": u(48),
            "order_ref": u(64),
            "shares": u1(32),
            "match": u(64),
        }
    ),
    st.fixed_dictionaries(
        {
            "type": st.just("X"),
            "locate": u(16),
            "tracking": u(16),
            "timestamp": u(48),
            "order_ref": u(64),
            "shares": u1(32),
        }
    ),
    st.fixed_dictionaries(
        {"type": st.just("D"), "locate": u(16), "tracking": u(16), "timestamp": u(48), "order_ref": u(64)}
    ),
)

ouch_msgs = st.one_of(
    st.fixed_dictionaries(
        {
            "type": st.just("O"),
            "token": fixed(14),
            "side": st.sampled_from("BS"),
            "shares": u1(32),
            "stock": fixed(8),
            "price": u(32),
            "time_in_force": u(32),
            "firm": fixed(4),
            "display": st.sampled_from("YN"),
            "capacity": st.sampled_from("APRO"),
            "sweep": st.sampled_from("YN"),
            "min_qty": u(32),
            "cross_type": st.sampled_from("NOC"),
            "customer_type": st.sampled_from("RN "),
        }
    ),
    st.fixed_dictionaries({"type": st.just("X"), "token": fixed(14), "shares": u(32)}),
    st.fixed_dictionaries({"type": st.just("A"), "timestamp": u(64), "token": fixed(14), "order_ref": u(64)}),
    st.fixed_dictionaries(
        {
            "type": st.just("C"),
            "timestamp": u(64),
            "token": fixed(14),
            "shares": u(32),
            "reason": st.sampled_from("ABCDEFGHIJKLMNOPQRSTUVWXYZ"),
        }
    ),
)

printable = st.text(alphabet=st.characters(min_codepoint=0x20, max_codepoint=0x7E), min_size=1, max_size=16)
fix_msgs = st.one_of(
    st.fixed_dictionaries(
        {
            "msg_type": st.just("0"),
            "seq": st.integers(1, 2**31 - 1),
            "sender": printable,
            "target": printable,
            "body": st.just([]),
        }
    ),
    st.builds(
        lambda seq, s, t, cl, sym, side, qty, px: {
            "msg_type": "D",
            "seq": seq,
            "sender": s,
            "target": t,
            "body": [[11, cl], [55, sym], [54, side], [38, str(qty)], [40, "2"], [44, px]],
        },
        st.integers(1, 2**31 - 1),
        printable,
        printable,
        st.text(alphabet=st.characters(min_codepoint=0x20, max_codepoint=0x7E), min_size=1, max_size=20),
        st.text(alphabet=st.characters(min_codepoint=0x20, max_codepoint=0x7E), min_size=1, max_size=8),
        st.sampled_from("12"),
        st.integers(1, 999_999_999),
        st.builds(
            lambda i, f: str(i) + f,
            st.integers(0, 10**9),
            st.one_of(st.just(""), st.from_regex(r"\.[0-9]{1,4}", fullmatch=True)),
        ),
    ),
)

symbol = st.text(alphabet=st.characters(min_codepoint=0x21, max_codepoint=0x7E), min_size=1, max_size=8)
quote = st.fixed_dictionaries(
    {
        "template": st.just(1),
        "seq": u(32),
        "symbol": symbol,
        "bid_px": st.integers(0, 2**62 - 1),
        "bid_size": u(32),
        "ask_px": st.integers(0, 2**62 - 1),
        "ask_size": u(32),
    }
)
# Runs of nearly identical quotes exercise the omit paths of copy and increment.
quote_runs = (
    st.lists(quote, min_size=1, max_size=6)
    .flatmap(lambda qs: st.lists(st.sampled_from(qs), min_size=1, max_size=12))
    .map(lambda qs: [{**q, "seq": (qs[0]["seq"] + i) % 2**32} for i, q in enumerate(qs)])
)


@settings(max_examples=300)
@given(itch_msgs)
def test_itch_round_trip(msg: dict[str, Any]) -> None:
    data = itch.encode(msg)
    assert len(data) == itch.LENGTHS[msg["type"]]
    assert itch.decode(data) == msg


@settings(max_examples=300)
@given(st.lists(ouch_msgs, max_size=5))
def test_ouch_stream_round_trip(msgs: list[dict[str, Any]]) -> None:
    data = ouch.encode_stream(msgs)
    assert ouch.decode_stream(data) == msgs
    assert ouch.encode_stream(ouch.decode_stream(data)) == data


@settings(max_examples=300)
@given(fix_msgs)
def test_fix_round_trip(msg: dict[str, Any]) -> None:
    data = fix.encode(msg)
    assert fix.decode(data) == msg


@settings(max_examples=300)
@given(st.one_of(quote_runs, st.lists(quote, max_size=8)))
def test_fast_round_trip(msgs: list[dict[str, Any]]) -> None:
    data = fast.encode_packet(msgs)
    assert fast.decode_packet(data) == msgs
    assert fast.encode_packet(fast.decode_packet(data)) == data


@settings(max_examples=300)
@given(st.integers(-(2**63), 2**63 - 1))
def test_fast_signed_primitive(x: int) -> None:
    r = fast._Reader(fast.enc_i(x))
    assert r.i64("x") == x and r.pos == len(r.data)


@settings(max_examples=300)
@given(st.integers(0, 2**32 - 1))
def test_fast_unsigned_primitive(x: int) -> None:
    r = fast._Reader(fast.enc_u(x))
    assert r.u32("x") == x and r.pos == len(r.data)


@settings(max_examples=300)
@given(
    fixed(10).filter(lambda s: s != " " * 10),
    u(64),
    st.lists(st.binary(min_size=1, max_size=40), max_size=10),
)
def test_mold_round_trip(session: str, seq: int, blocks: list[bytes]) -> None:
    pkt = {"session": session, "sequence": seq, "count": len(blocks), "blocks": blocks}
    data = mold.encode(pkt)
    assert mold.decode(data) == pkt


# ---- canonical encodings: anything that decodes re-encodes to the same bytes (KR-276) ---------------------


def _reencode(fmt: str, data: bytes) -> bytes | None:
    try:
        if fmt == "fix":
            return fix.encode(fix.decode(data))
        if fmt == "itch":
            return itch.encode(itch.decode(data))
        if fmt == "ouch":
            return ouch.encode_stream(ouch.decode_stream(data))
        if fmt == "fast":
            return fast.encode_packet(fast.decode_packet(data))
        return mold.encode(mold.decode(data))
    except FeedError:
        return None


def _mutations(seed: int) -> list[tuple[str, bytes]]:
    """Fixture bytes with random single-byte edits, cuts and extensions, plus pure random bytes."""
    rnd = random.Random(seed)
    base = [(p.parent.name, p.read_bytes()) for p in FIXTURES]
    out = []
    for _ in range(4000):
        fmt, data = rnd.choice(base)
        b = bytearray(data)
        op = rnd.randrange(4)
        if op == 0 and b:
            b[rnd.randrange(len(b))] = rnd.randrange(256)
        elif op == 1:
            del b[rnd.randrange(len(b) + 1) :]
        elif op == 2:
            b += bytes(rnd.randrange(256) for _ in range(rnd.randrange(1, 8)))
        else:
            b = bytearray(rnd.randrange(256) for _ in range(rnd.randrange(0, 80)))
        out.append((fmt, bytes(b)))
    return out


@pytest.mark.parametrize("seed", [20261109, 1, 2])
def test_fuzz_never_crashes_and_valid_inputs_are_canonical(seed: int) -> None:
    for fmt, data in _mutations(seed):
        for name in ("fix", "itch", "ouch", "fast", "mold"):
            again = _reencode(name, data)  # any exception other than FeedError fails the test here
            if again is not None:
                assert again == data, (name, fmt, data.hex())
        if fmt == "ouch":
            try:
                ouch.decode(data)
            except FeedError:
                pass


@settings(max_examples=1000)
@given(st.binary(max_size=120))
def test_hypothesis_random_bytes(data: bytes) -> None:
    for name in ("fix", "itch", "ouch", "fast", "mold"):
        again = _reencode(name, data)
        if again is not None:
            assert again == data


# ---- encoders validate ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "call",
    [
        lambda: itch.encode({"type": "Z"}),
        lambda: itch.encode({"type": "D", "locate": 1, "tracking": 0, "timestamp": 2**48, "order_ref": 1}),
        lambda: itch.encode(
            {"type": "D", "locate": 1, "tracking": 0, "timestamp": 0, "order_ref": 1, "x": 1}
        ),
        lambda: itch.encode({"type": "S", "locate": 1, "tracking": 0, "timestamp": 0, "event": "Z"}),
        lambda: ouch.encode({"type": "X", "token": "short", "shares": 1}),
        lambda: ouch.encode({"type": "X", "token": "é" * 14, "shares": 1}),
        lambda: fix.encode({"msg_type": "0", "seq": 0, "sender": "A", "target": "B", "body": []}),
        lambda: fix.encode({"msg_type": "0", "seq": 1, "sender": "A\x01", "target": "B", "body": []}),
        lambda: fix.encode({"msg_type": "Q", "seq": 1, "sender": "A", "target": "B", "body": []}),
        lambda: fast.encode_packet(
            [{"template": 2, "seq": 1, "symbol": "Q", "bid_px": 0, "bid_size": 0, "ask_px": 0, "ask_size": 0}]
        ),
        lambda: fast.encode_packet(
            [
                {
                    "template": 1,
                    "seq": 2**32,
                    "symbol": "Q",
                    "bid_px": 0,
                    "bid_size": 0,
                    "ask_px": 0,
                    "ask_size": 0,
                }
            ]
        ),
        lambda: fast.encode_packet(
            [{"template": 1, "seq": 1, "symbol": "", "bid_px": 0, "bid_size": 0, "ask_px": 0, "ask_size": 0}]
        ),
        lambda: mold.encode({"session": "QFSIM00001", "sequence": 1, "count": 2, "blocks": [b"x"]}),
        lambda: mold.encode({"session": "QFSIM00001", "sequence": 1, "count": 65535, "blocks": [b"x"]}),
        lambda: mold.encode({"session": "short", "sequence": 1, "count": 0, "blocks": []}),
    ],
)
def test_encoders_reject_invalid_input(call: Any) -> None:
    with pytest.raises(FeedError):
        call()


# ---- gap detector (adapters.md 3.5 worked example) --------------------------------------------------------


def _pkt(seq: int, n: int, count: int | None = None, session: str = "QFSIM00001") -> dict[str, Any]:
    blocks = [bytes([seq + i]) for i in range(n)]
    return {
        "session": session,
        "sequence": seq,
        "count": len(blocks) if count is None else count,
        "blocks": blocks,
    }


def test_gap_detector_worked_example() -> None:
    g = mold.GapDetector()
    got = []
    for p in (_pkt(1, 3), _pkt(4, 2), _pkt(8, 1), _pkt(9, 0), _pkt(1, 3)):
        got += [s for s, _ in g.feed(p)]
    assert got == [1, 2, 3, 4, 5, 8]
    assert g.gaps == [(6, 7)] and g.duplicates == 1 and g.expected == 9


def test_gap_detector_partial_overlap_heartbeat_gap_and_session() -> None:
    g = mold.GapDetector()
    g.feed(_pkt(1, 3))
    assert [s for s, _ in g.feed(_pkt(2, 4))] == [4, 5]
    g.feed(_pkt(9, 0))
    assert g.gaps == [(6, 8)] and g.expected == 9
    with pytest.raises(FeedError) as err:
        g.feed(_pkt(9, 1, session="QFSIM00002"))
    assert err.value.code == "E_SESSION"
    g.feed(_pkt(9, 0, count=0xFFFF))
    assert g.ended
    with pytest.raises(FeedError) as err:
        g.feed(_pkt(9, 0))
    assert err.value.code == "E_SESSION"
