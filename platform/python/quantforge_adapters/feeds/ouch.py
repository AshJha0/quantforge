"""QF-OUCH-S: simulated binary order entry messages and their stream framing (adapters.md 3.3).

Simulated; not a certified implementation; not connected to any venue.
"""

from quantforge_adapters.feeds._binary import MIN_ONE, Field, Message, decode_fields, encode_fields, layout_length
from quantforge_adapters.feeds.errors import FeedError

BODIES: dict[str, list[Field]] = {
    "O": [("token", "a", 14, None), ("side", "c", 1, "BS"), ("shares", "u", 4, MIN_ONE), ("stock", "a", 8, None),
          ("price", "u", 4, None), ("time_in_force", "u", 4, None), ("firm", "a", 4, None),
          ("display", "c", 1, "YN"), ("capacity", "c", 1, "APRO"), ("sweep", "c", 1, "YN"),
          ("min_qty", "u", 4, None), ("cross_type", "c", 1, "NOC"), ("customer_type", "c", 1, "RN ")],
    "X": [("token", "a", 14, None), ("shares", "u", 4, None)],
    "A": [("timestamp", "u", 8, None), ("token", "a", 14, None), ("order_ref", "u", 8, None)],
    "C": [("timestamp", "u", 8, None), ("token", "a", 14, None), ("shares", "u", 4, None),
          ("reason", "c", 1, "ABCDEFGHIJKLMNOPQRSTUVWXYZ")],
}
LENGTHS = {t: 1 + layout_length(b) for t, b in BODIES.items()}


def _type_of(data: bytes) -> str:
    if not data:
        raise FeedError("E_TRUNCATED", "empty input")
    kind = chr(data[0])
    if kind not in BODIES:
        raise FeedError("E_TYPE", f"unknown type byte 0x{data[0]:02x}")
    return kind


def _fields(kind: str, data: bytes) -> Message:
    out: Message = {"type": kind}
    decode_fields(data, 1, BODIES[kind], out)
    return out


def decode(data: bytes) -> Message:
    kind = _type_of(data)
    need = LENGTHS[kind]
    if len(data) < need:
        raise FeedError("E_TRUNCATED", f"type {kind} needs {need} bytes, got {len(data)}")
    if len(data) > need:
        raise FeedError("E_LENGTH", f"type {kind} is {need} bytes, got {len(data)}")
    return _fields(kind, data)


def encode(msg: Message) -> bytes:
    kind = msg.get("type")
    if not isinstance(kind, str) or kind not in BODIES:
        raise FeedError("E_TYPE", f"unknown type {kind!r}")
    extra = set(msg) - {"type"} - {name for name, _, _, _ in BODIES[kind]}
    if extra:
        raise FeedError("E_FIELD", f"unknown fields {sorted(extra)}")
    return kind.encode("ascii") + encode_fields(msg, BODIES[kind])


def decode_stream(data: bytes) -> list[Message]:
    out: list[Message] = []
    pos = 0
    while pos < len(data):
        if len(data) - pos < 2:
            raise FeedError("E_TRUNCATED", f"length field cut at offset {pos}")
        length = int.from_bytes(data[pos:pos + 2], "big")
        pos += 2
        if length == 0:
            raise FeedError("E_LENGTH", f"zero frame length at offset {pos - 2}")
        if len(data) - pos < length:
            raise FeedError("E_TRUNCATED", f"frame of {length} bytes cut at offset {pos}")
        frame = data[pos:pos + length]
        kind = _type_of(frame)
        if length != LENGTHS[kind]:
            raise FeedError("E_LENGTH", f"frame length {length} for type {kind} of {LENGTHS[kind]} bytes")
        out.append(_fields(kind, frame))
        pos += length
    return out


def encode_stream(messages: list[Message]) -> bytes:
    parts = []
    for msg in messages:
        body = encode(msg)
        parts.append(len(body).to_bytes(2, "big") + body)
    return b"".join(parts)
