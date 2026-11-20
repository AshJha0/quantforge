"""QF-FIX-S: simulated tag=value messages with a modulo-256 checksum (adapters.md 3.1).

Simulated; not a certified implementation; not connected to any venue. BeginString is `QFSIM.1`, which is
deliberately not a FIX version. Messages are dicts {"msg_type", "seq", "sender", "target", "body"} where body
is a list of [tag, value] pairs in wire order.
"""

import re
from typing import Any

from quantforge_adapters.feeds.errors import FeedError

SOH = b"\x01"
BEGIN = "QFSIM.1"
MAX_BYTES = 4096
_NUM = re.compile(r"[1-9][0-9]*\Z")
_PRICE = re.compile(r"(0|[1-9][0-9]*)(\.[0-9]{1,4})?\Z")
D_TAGS = (11, 55, 54, 38, 40, 44)


def _printable(value: str, lo: int, hi: int) -> bool:
    return lo <= len(value) <= hi and all(0x20 <= ord(c) <= 0x7E for c in value)


def _check_header(seq: Any, sender: Any, target: Any) -> None:
    if type(seq) is not int or not 1 <= seq <= 2**31 - 1:
        raise FeedError("E_FIELD", "MsgSeqNum (34) must be 1 to 2^31 - 1")
    for tag, value in ((49, sender), (56, target)):
        if not isinstance(value, str) or not _printable(value, 1, 16):
            raise FeedError("E_FIELD", f"tag {tag} must be 1 to 16 printable characters")


def _check_body(msg_type: str, body: list[tuple[int, str]]) -> None:
    if msg_type == "0":
        if body:
            raise FeedError("E_FIELD", "a heartbeat has no body fields")
        return
    if tuple(tag for tag, _ in body) != D_TAGS:
        raise FeedError("E_FIELD", f"new order body tags must be {D_TAGS}")
    v = dict(body)
    if not _printable(v[11], 1, 20):
        raise FeedError("E_FIELD", "ClOrdID (11) must be 1 to 20 printable characters")
    if not _printable(v[55], 1, 8):
        raise FeedError("E_FIELD", "Symbol (55) must be 1 to 8 printable characters")
    if v[54] not in ("1", "2"):
        raise FeedError("E_FIELD", "Side (54) must be 1 or 2")
    if not _NUM.match(v[38]) or len(v[38]) > 9:
        raise FeedError("E_FIELD", "OrderQty (38) must be 1 to 999999999 with no leading zero")
    if v[40] != "2":
        raise FeedError("E_FIELD", "OrdType (40) must be 2 (limit)")
    if not _PRICE.match(v[44]):
        raise FeedError("E_FIELD", "Price (44) must be digits[.digits], at most 4 decimals, no leading zero")


def _split(data: bytes) -> list[tuple[str, str]]:
    """Every field as (tag text, value text); E_FIELD on a malformed field."""
    out = []
    for raw in data.split(SOH)[:-1]:
        tag, eq, value = raw.partition(b"=")
        if not eq or not tag.isdigit() or not value:
            raise FeedError("E_FIELD", f"malformed field {raw[:20]!r}")
        if not all(0x20 <= b <= 0x7E for b in value):
            raise FeedError("E_FIELD", f"tag {tag.decode()} value has a byte outside 0x20 to 0x7E")
        out.append((tag.decode("ascii"), value.decode("ascii")))
    return out


def decode(data: bytes) -> dict[str, Any]:
    if len(data) > MAX_BYTES:
        raise FeedError("E_LENGTH", f"message over {MAX_BYTES} bytes")
    cut = data.rfind(SOH + b"10=")
    if not data.endswith(SOH) or cut < 0:
        raise FeedError("E_TRUNCATED", "no complete checksum field at the end")
    head = data[:cut + 1]
    trailer = data[cut + 1:]
    fields = _split(head)
    if len(fields) < 2 or fields[0] != ("8", BEGIN):
        raise FeedError("E_FIELD", f"the first field must be 8={BEGIN}")
    if fields[1][0] != "9" or not _NUM.match(fields[1][1]):
        raise FeedError("E_FIELD", "the second field must be 9=<length> with no leading zero")
    prefix = len(f"8={BEGIN}\x019={fields[1][1]}\x01")
    if int(fields[1][1]) != len(head) - prefix:
        raise FeedError("E_LENGTH", f"BodyLength {fields[1][1]} but {len(head) - prefix} body bytes")
    if len(fields) < 3 or fields[2][0] != "35":
        raise FeedError("E_FIELD", "the third field must be 35 (MsgType)")
    msg_type = fields[2][1]
    if msg_type not in ("0", "D"):
        raise FeedError("E_TYPE", f"unknown MsgType {msg_type!r}")
    check = trailer[3:-1]
    if len(check) != 3 or not check.isdigit():
        raise FeedError("E_FIELD", "CheckSum (10) must be exactly 3 digits")
    if int(check) != sum(head) % 256:
        raise FeedError("E_CHECKSUM", f"CheckSum {check.decode()} but computed {sum(head) % 256:03d}")
    rest = fields[3:]
    if [t for t, _ in rest[:3]] != ["34", "49", "56"]:
        raise FeedError("E_FIELD", "fields 34, 49, 56 must follow 35 in that order")
    if not _NUM.match(rest[0][1]):
        raise FeedError("E_FIELD", "MsgSeqNum (34) must have no leading zero")
    seq = int(rest[0][1])
    body: list[tuple[int, str]] = []
    for tag, value in rest[3:]:
        if not _NUM.match(tag):
            raise FeedError("E_FIELD", f"tag {tag!r} has a leading zero")
        body.append((int(tag), value))
    _check_header(seq, rest[1][1], rest[2][1])
    _check_body(msg_type, body)
    return {"msg_type": msg_type, "seq": seq, "sender": rest[1][1], "target": rest[2][1],
            "body": [[t, v] for t, v in body]}


def encode(msg: dict[str, Any]) -> bytes:
    if set(msg) != {"msg_type", "seq", "sender", "target", "body"}:
        raise FeedError("E_FIELD", "a message has exactly msg_type, seq, sender, target, body")
    msg_type = msg["msg_type"]
    if msg_type not in ("0", "D"):
        raise FeedError("E_TYPE", f"unknown MsgType {msg_type!r}")
    _check_header(msg["seq"], msg["sender"], msg["target"])
    body_in = msg["body"]
    if not isinstance(body_in, list):
        raise FeedError("E_FIELD", "body must be a list of [tag, value]")
    body: list[tuple[int, str]] = []
    for item in body_in:
        if (not isinstance(item, (list, tuple)) or len(item) != 2 or type(item[0]) is not int
                or not isinstance(item[1], str)):
            raise FeedError("E_FIELD", "body items are [int tag, str value]")
        body.append((item[0], item[1]))
    _check_body(msg_type, body)
    text = f"35={msg_type}\x0134={msg['seq']}\x0149={msg['sender']}\x0156={msg['target']}\x01"
    text += "".join(f"{t}={v}\x01" for t, v in body)
    head = f"8={BEGIN}\x019={len(text)}\x01{text}".encode("ascii")
    out = head + f"10={sum(head) % 256:03d}\x01".encode("ascii")
    if len(out) > MAX_BYTES:
        raise FeedError("E_LENGTH", f"message over {MAX_BYTES} bytes")
    return out
