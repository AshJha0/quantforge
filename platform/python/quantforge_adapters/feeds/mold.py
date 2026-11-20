"""QF-MOLD-S: simulated multicast packets and a sequence gap detector (adapters.md 3.5, KR-278).

Simulated; not a certified implementation; not connected to any venue. Packets are dicts {"session",
"sequence", "count", "blocks"} with blocks as bytes; count 0 is a heartbeat and 0xFFFF end of session.
"""

from dataclasses import dataclass, field
from typing import Any

from quantforge_adapters.feeds.errors import FeedError

HEADER = 20
END_OF_SESSION = 0xFFFF


def _check_session(raw: bytes) -> None:
    if len(raw) != 10 or not all(0x20 <= b <= 0x7E for b in raw) or raw == b" " * 10:
        raise FeedError("E_FIELD", "session must be 10 printable ASCII bytes, not all spaces")


def decode(data: bytes) -> dict[str, Any]:
    if len(data) < HEADER:
        raise FeedError("E_TRUNCATED", f"header needs {HEADER} bytes, got {len(data)}")
    _check_session(data[:10])
    sequence = int.from_bytes(data[10:18], "big")
    count = int.from_bytes(data[18:20], "big")
    blocks: list[bytes] = []
    pos = HEADER
    if count == END_OF_SESSION:
        if len(data) > HEADER:
            raise FeedError("E_LENGTH", "bytes after an end-of-session header")
    else:
        for _ in range(count):
            if len(data) - pos < 2:
                raise FeedError("E_TRUNCATED", f"block length cut at offset {pos}")
            length = int.from_bytes(data[pos:pos + 2], "big")
            pos += 2
            if length == 0:
                raise FeedError("E_LENGTH", f"zero block length at offset {pos - 2}")
            if len(data) - pos < length:
                raise FeedError("E_TRUNCATED", f"block of {length} bytes cut at offset {pos}")
            blocks.append(data[pos:pos + length])
            pos += length
        if pos != len(data):
            raise FeedError("E_LENGTH", f"{len(data) - pos} bytes after the last block")
    return {"session": data[:10].decode("ascii"), "sequence": sequence, "count": count, "blocks": blocks}


def encode(packet: dict[str, Any]) -> bytes:
    if set(packet) != {"session", "sequence", "count", "blocks"}:
        raise FeedError("E_FIELD", "a packet has exactly session, sequence, count, blocks")
    session = packet["session"]
    raw = session.encode("ascii", errors="replace") if isinstance(session, str) and session.isascii() else b""
    _check_session(raw)
    seq, count, blocks = packet["sequence"], packet["count"], packet["blocks"]
    if type(seq) is not int or not 0 <= seq < 2**64:
        raise FeedError("E_FIELD", "sequence must be an unsigned 64-bit integer")
    if not isinstance(blocks, list) or not all(isinstance(b, (bytes, bytearray)) for b in blocks):
        raise FeedError("E_FIELD", "blocks must be a list of bytes")
    if count == END_OF_SESSION:
        if blocks:
            raise FeedError("E_LENGTH", "end of session carries no blocks")
    elif type(count) is not int or count != len(blocks):
        raise FeedError("E_LENGTH", "count must equal the number of blocks")
    out = bytearray(raw + seq.to_bytes(8, "big") + count.to_bytes(2, "big"))
    for b in blocks:
        if not 1 <= len(b) <= 0xFFFF:
            raise FeedError("E_LENGTH", "a block is 1 to 65535 bytes")
        out += len(b).to_bytes(2, "big") + bytes(b)
    return bytes(out)


@dataclass
class GapDetector:
    """Receiver state of adapters.md 3.5: delivers each sequence number at most once and records gaps."""

    session: str | None = None
    expected: int = 1
    ended: bool = False
    gaps: list[tuple[int, int]] = field(default_factory=list)
    duplicates: int = 0

    def feed(self, packet: dict[str, Any]) -> list[tuple[int, bytes]]:
        """Returns the newly delivered (sequence number, block) pairs."""
        if self.ended:
            raise FeedError("E_SESSION", "packet after end of session")
        if self.session is None:
            self.session = packet["session"]
        elif packet["session"] != self.session:
            raise FeedError("E_SESSION", f"session {packet['session']!r}, expected {self.session!r}")
        s = packet["sequence"]
        blocks: list[bytes] = packet["blocks"]
        n = len(blocks)
        if packet["count"] == END_OF_SESSION:
            self.ended = True
        delivered: list[tuple[int, bytes]] = []
        if s > self.expected:
            self.gaps.append((self.expected, s - 1))
            delivered = [(s + i, b) for i, b in enumerate(blocks)]
        elif s + n <= self.expected:
            if n:
                self.duplicates += 1
        else:
            first = self.expected - s
            delivered = [(s + i, blocks[i]) for i in range(first, n)]
        self.expected = max(self.expected, s + n)
        return delivered
