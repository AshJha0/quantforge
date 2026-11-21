"""QF-ITCH-S: simulated binary market data messages (adapters.md 3.2).

Simulated; not a certified implementation; not connected to any venue. One message per call; framing comes
from QF-MOLD-S. Messages are dicts: {"type", "locate", "tracking", "timestamp", ...type fields}.
"""

from quantforge_adapters.feeds._binary import (
    MIN_ONE,
    Field,
    Message,
    decode_fields,
    encode_fields,
    layout_length,
)
from quantforge_adapters.feeds.errors import FeedError

HEADER: list[Field] = [("locate", "u", 2, None), ("tracking", "u", 2, None), ("timestamp", "u", 6, None)]
BODIES: dict[str, list[Field]] = {
    "S": [("event", "c", 1, "OSQMEC")],
    "A": [
        ("order_ref", "u", 8, None),
        ("side", "c", 1, "BS"),
        ("shares", "u", 4, MIN_ONE),
        ("stock", "a", 8, None),
        ("price", "u", 4, None),
    ],
    "E": [("order_ref", "u", 8, None), ("shares", "u", 4, MIN_ONE), ("match", "u", 8, None)],
    "X": [("order_ref", "u", 8, None), ("shares", "u", 4, MIN_ONE)],
    "D": [("order_ref", "u", 8, None)],
}
LENGTHS = {t: 1 + layout_length(HEADER) + layout_length(b) for t, b in BODIES.items()}


def decode(data: bytes) -> Message:
    if not data:
        raise FeedError("E_TRUNCATED", "empty input")
    kind = chr(data[0])
    if kind not in BODIES:
        raise FeedError("E_TYPE", f"unknown type byte 0x{data[0]:02x}")
    need = LENGTHS[kind]
    if len(data) < need:
        raise FeedError("E_TRUNCATED", f"type {kind} needs {need} bytes, got {len(data)}")
    if len(data) > need:
        raise FeedError("E_LENGTH", f"type {kind} is {need} bytes, got {len(data)}")
    out: Message = {"type": kind}
    decode_fields(data, 1, HEADER + BODIES[kind], out)
    return out


def encode(msg: Message) -> bytes:
    kind = msg.get("type")
    if not isinstance(kind, str) or kind not in BODIES:
        raise FeedError("E_TYPE", f"unknown type {kind!r}")
    layout = HEADER + BODIES[kind]
    extra = set(msg) - {"type"} - {name for name, _, _, _ in layout}
    if extra:
        raise FeedError("E_FIELD", f"unknown fields {sorted(extra)}")
    return kind.encode("ascii") + encode_fields(msg, layout)
