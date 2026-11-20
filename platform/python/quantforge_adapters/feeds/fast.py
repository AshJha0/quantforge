"""QF-FAST-S: simulated stop-bit compressed quotes with a presence map (adapters.md 3.4, KR-276, KR-277).

Simulated; not a certified implementation; not connected to any venue. One template (id 1, Quote). A packet
starts with an empty dictionary. Messages are dicts {"template", "seq", "symbol", "bid_px", "bid_size",
"ask_px", "ask_size"}.
"""

from typing import Any

from quantforge_adapters.feeds.errors import FeedError

U32_MAX = 2**32 - 1
I64_MIN, I64_MAX = -(2**63), 2**63 - 1
PRICE_LIMIT = 2**62
FIELDS = ("template", "seq", "symbol", "bid_px", "bid_size", "ask_px", "ask_size")
# PMAP bit per optional field (bit 0 is the first, most significant, data bit).
BIT = {"template": 0, "seq": 1, "symbol": 2, "bid_size": 3, "ask_size": 4}
USED_BITS = 5


# ---- primitives -------------------------------------------------------------------------------------------

def enc_u(value: int) -> bytes:
    groups = []
    while True:
        groups.append(value & 0x7F)
        value >>= 7
        if not value:
            break
    groups.reverse()
    groups[-1] |= 0x80
    return bytes(groups)


def enc_i(value: int) -> bytes:
    groups = []
    while True:
        groups.append(value & 0x7F)
        value >>= 7
        if (value == 0 and not groups[-1] & 0x40) or (value == -1 and groups[-1] & 0x40):
            break
    groups.reverse()
    groups[-1] |= 0x80
    return bytes(groups)


def enc_ascii(text: str) -> bytes:
    raw = bytearray(text.encode("ascii"))
    raw[-1] |= 0x80
    return bytes(raw)


class _Reader:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.pos = 0

    def stop_bit(self, max_bytes: int, what: str, too_long: str) -> bytes:
        start = self.pos
        while True:
            if self.pos >= len(self.data):
                raise FeedError("E_TRUNCATED", f"{what} has no stop bit before the end")
            b = self.data[self.pos]
            self.pos += 1
            if b & 0x80:
                return self.data[start:self.pos]
            if self.pos - start >= max_bytes:
                raise FeedError(too_long, f"{what} longer than {max_bytes} bytes")

    def u32(self, what: str) -> int:
        raw = self.stop_bit(5, what, "E_OVERFLOW")
        if len(raw) > 1 and raw[0] == 0x00:
            raise FeedError("E_OVERLONG", f"{what} has a leading zero group")
        value = 0
        for b in raw:
            value = (value << 7) | (b & 0x7F)
        if value > U32_MAX:
            raise FeedError("E_OVERFLOW", f"{what} exceeds 2^32 - 1")
        return value

    def i64(self, what: str) -> int:
        raw = self.stop_bit(10, what, "E_OVERFLOW")
        if len(raw) > 1 and ((raw[0] == 0x00 and not raw[1] & 0x40) or (raw[0] == 0x7F and raw[1] & 0x40)):
            raise FeedError("E_OVERLONG", f"{what} has a redundant sign group")
        value = -1 if raw[0] & 0x40 else 0
        for b in raw:
            value = (value << 7) | (b & 0x7F)
        if not I64_MIN <= value <= I64_MAX:
            raise FeedError("E_OVERFLOW", f"{what} outside the 64-bit signed range")
        return value

    def ascii(self, what: str) -> str:
        raw = self.stop_bit(8, what, "E_FIELD")
        text = bytes(raw[:-1]) + bytes([raw[-1] & 0x7F])
        if not all(0x21 <= b <= 0x7E for b in text):
            raise FeedError("E_FIELD", f"{what} must be 1 to 8 characters in 0x21 to 0x7E")
        return text.decode("ascii")

    def pmap(self) -> list[bool]:
        raw = self.stop_bit(2, "presence map", "E_OVERLONG")
        if len(raw) > 1 and raw[-1] & 0x7F == 0:
            raise FeedError("E_OVERLONG", "presence map has a trailing zero byte")
        bits = [bool((b >> (6 - i)) & 1) for b in raw for i in range(7)]
        if any(bits[USED_BITS:]):
            raise FeedError("E_FIELD", "presence map sets a bit the template does not use")
        return bits[:USED_BITS]


# ---- messages ---------------------------------------------------------------------------------------------

def _check(msg: Any) -> None:
    if not isinstance(msg, dict) or set(msg) != set(FIELDS):
        raise FeedError("E_FIELD", f"a quote has exactly the fields {FIELDS}")
    if msg["template"] != 1 or type(msg["template"]) is not int:
        raise FeedError("E_TYPE", f"unknown template {msg['template']!r}")
    for name in ("seq", "bid_size", "ask_size"):
        if type(msg[name]) is not int or not 0 <= msg[name] <= U32_MAX:
            raise FeedError("E_OVERFLOW", f"{name} must be an unsigned 32-bit integer")
    for name in ("bid_px", "ask_px"):
        if type(msg[name]) is not int or not 0 <= msg[name] < PRICE_LIMIT:
            raise FeedError("E_FIELD", f"{name} must be in [0, 2^62)")
    sym = msg["symbol"]
    if not isinstance(sym, str) or not 1 <= len(sym) <= 8 or not all(0x21 <= ord(c) <= 0x7E for c in sym):
        raise FeedError("E_FIELD", "symbol must be 1 to 8 characters in 0x21 to 0x7E")


def encode_packet(messages: list[dict[str, Any]]) -> bytes:
    """Encode quotes with a dictionary that starts empty (KR-277)."""
    prev: dict[str, Any] = {"bid_px": 0, "ask_px": 0}
    out = bytearray()
    for msg in messages:
        _check(msg)
        bits = [False] * USED_BITS
        body = bytearray()
        for name in FIELDS:
            value = msg[name]
            if name in ("bid_px", "ask_px"):
                body += enc_i(value - prev[name])
            else:
                expected = prev[name] + 1 if name == "seq" and name in prev else prev.get(name)
                if expected != value:
                    bits[BIT[name]] = True
                    body += enc_ascii(value) if name == "symbol" else enc_u(value)
            prev[name] = value
        pmap = sum(1 << (6 - i) for i, b in enumerate(bits) if b) | 0x80
        out.append(pmap)
        out += body
    return bytes(out)


def decode_packet(data: bytes) -> list[dict[str, Any]]:
    prev: dict[str, Any] = {"bid_px": 0, "ask_px": 0}
    r = _Reader(data)
    out = []
    while r.pos < len(data):
        bits = r.pmap()
        msg: dict[str, Any] = {}
        for name in FIELDS:
            if name in ("bid_px", "ask_px"):
                value: Any = prev[name] + r.i64(name)
                if not 0 <= value < PRICE_LIMIT:
                    raise FeedError("E_FIELD", f"{name} outside [0, 2^62)")
            elif bits[BIT[name]]:
                value = r.ascii(name) if name == "symbol" else r.u32(name)
                if name == "template" and value != 1:
                    raise FeedError("E_TYPE", f"unknown template {value}")
                implied = prev[name] + 1 if name == "seq" and name in prev else prev.get(name)
                if value == implied:
                    raise FeedError("E_OVERLONG", f"{name} sent although its operator gives the same value")
            elif name not in prev:
                raise FeedError("E_FIELD", f"{name} absent and the dictionary is empty")
            elif name == "seq":
                value = prev[name] + 1
                if value > U32_MAX:
                    raise FeedError("E_OVERFLOW", "seq increment exceeds 2^32 - 1")
            else:
                value = prev[name]
            prev[name] = value
            msg[name] = value
        out.append(msg)
    return out
