"""Test helpers for the anchor evidence of the two daily jobs (tools/paper_daily/anchor_evidence.py).

Builds an OpenTimestamps proof and a block header by hand, so the tests can plant a block time. The header is
"mined" at the easiest target the header format allows (two tries on average); the tests pass that easy floor to
the verifier explicitly, and a separate test shows the production floor refuses such a header."""

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]
EASY_BITS = 0x207FFFFF
EASY_TARGET = 0x7FFFFF << (8 * (0x20 - 3))


def load(name: str, path: Path) -> ModuleType:
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


evidence = load("anchor_evidence", ROOT / "tools" / "paper_daily" / "anchor_evidence.py")


def _varuint(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        out.append(b | (0x80 if n else 0))
        if not n:
            return bytes(out)


def _varbytes(b: bytes) -> bytes:
    return _varuint(len(b)) + b


def proof_for(file_bytes: bytes, height: int | None) -> tuple[bytes, bytes]:
    """(proof bytes, Merkle root) for a file. The path is append, SHA-256, prepend, SHA-256, as a calendar's is.
    `height` None gives a proof with only a pending attestation, as `ots stamp` leaves it before `ots upgrade`."""
    digest = hashlib.sha256(file_bytes).digest()
    m1 = hashlib.sha256(digest + b"calendar nonce").digest()
    root = hashlib.sha256(b"left sibling" + m1).digest()
    body = (
        b"\xf0"
        + _varbytes(b"calendar nonce")
        + b"\x08"
        + b"\xf1"
        + _varbytes(b"left sibling")
        + b"\x08"
    )
    pending = b"\x00" + evidence.PENDING + _varbytes(_varbytes(b"https://calendar.test"))
    if height is None:
        return evidence.MAGIC + b"\x01\x08" + digest + body + pending, root
    bitcoin = b"\x00" + evidence.BITCOIN + _varbytes(_varuint(height))
    return evidence.MAGIC + b"\x01\x08" + digest + body + b"\xff" + bitcoin + pending, root


def header_for(root: bytes, when: int, bits: int = EASY_BITS) -> str:
    """An 80-byte header (hex) with this Merkle root and time that meets the target of `bits`."""
    exponent, mantissa = bits >> 24, bits & 0x007FFFFF
    target = mantissa << (8 * (exponent - 3))
    base = (
        (2).to_bytes(4, "little")
        + bytes(32)
        + root
        + when.to_bytes(4, "little")
        + bits.to_bytes(4, "little")
    )
    for nonce in range(1 << 20):
        h = base + nonce.to_bytes(4, "little")
        if int.from_bytes(hashlib.sha256(hashlib.sha256(h).digest()).digest(), "little") <= target:
            return h.hex()
    raise AssertionError("no nonce found")


def stamp(anchor: Path, height: int | None, when: int | None, headers: dict[str, str]) -> None:
    """Write `<anchor>.ots` beside an anchor file and, for a confirmed proof, add its header to `headers`."""
    proof, root = proof_for(anchor.read_bytes(), height)
    Path(str(anchor) + ".ots").write_bytes(proof)
    if height is not None:
        assert when is not None
        headers[str(height)] = header_for(root, when)


def write_headers(path: Path, headers: dict[str, str]) -> Path:
    path.write_text(json.dumps(headers, sort_keys=True), encoding="utf-8", newline="\n")
    return path
