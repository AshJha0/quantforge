"""Fixed-width big-endian field layouts shared by the QF-ITCH-S and QF-OUCH-S codecs (adapters.md 3.2, 3.3).

A layout is a list of (name, kind, width, allowed) where kind is "u" (unsigned big-endian integer), "a"
(alpha: ASCII 0x20 to 0x7E, space padded) or "c" (one ASCII character from `allowed`). The type byte is
handled by the caller.
"""

from typing import Any

from quantforge_adapters.feeds.errors import FeedError

Field = tuple[str, str, int, str | None]
Message = dict[str, Any]

MIN_ONE = "min1"  # marker in `allowed` for an unsigned field that must be at least 1


def _alpha_ok(raw: bytes) -> bool:
    return all(0x20 <= b <= 0x7E for b in raw)


def decode_fields(data: bytes, offset: int, layout: list[Field], out: Message) -> None:
    for name, kind, width, allowed in layout:
        raw = data[offset:offset + width]
        if kind == "u":
            value = int.from_bytes(raw, "big")
            if allowed == MIN_ONE and value < 1:
                raise FeedError("E_FIELD", f"{name} must be at least 1")
            out[name] = value
        elif kind == "a":
            if not _alpha_ok(raw):
                raise FeedError("E_FIELD", f"{name} has a byte outside 0x20 to 0x7E")
            out[name] = raw.decode("ascii")
        else:
            ch = chr(raw[0])
            if allowed is None or ch not in allowed:
                raise FeedError("E_FIELD", f"{name} {ch!r} not in {allowed!r}")
            out[name] = ch
        offset += width


def encode_fields(msg: Message, layout: list[Field]) -> bytes:
    parts: list[bytes] = []
    for name, kind, width, allowed in layout:
        if name not in msg:
            raise FeedError("E_FIELD", f"missing field {name}")
        value = msg[name]
        if kind == "u":
            if type(value) is not int or not 0 <= value < (1 << (8 * width)):
                raise FeedError("E_FIELD", f"{name} is not an unsigned {8 * width}-bit integer")
            if allowed == MIN_ONE and value < 1:
                raise FeedError("E_FIELD", f"{name} must be at least 1")
            parts.append(value.to_bytes(width, "big"))
        else:
            if not isinstance(value, str) or len(value) != (width if kind == "a" else 1):
                raise FeedError("E_FIELD", f"{name} must be a string of length {width}")
            raw = value.encode("ascii", errors="replace") if value.isascii() else b"\x00"
            if kind == "a" and not _alpha_ok(raw):
                raise FeedError("E_FIELD", f"{name} has a character outside 0x20 to 0x7E")
            if kind == "c" and (allowed is None or value not in allowed):
                raise FeedError("E_FIELD", f"{name} {value!r} not in {allowed!r}")
            parts.append(raw)
    return b"".join(parts)


def layout_length(layout: list[Field]) -> int:
    return sum(width for _, _, width, _ in layout)
