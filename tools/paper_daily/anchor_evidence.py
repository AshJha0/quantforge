"""Outside time evidence for an anchor file (rulings KR-200 to KR-202; used by both daily jobs).

Standard library only, and no network: this file reads an OpenTimestamps proof (`<anchor>.json.ots`) and a
Bitcoin block header that the person verifying supplies, and answers one question: what is the earliest
outside time by which this anchor file provably existed?

Plain idea. `ots stamp` hashes the anchor file and sends the hash to public calendar servers; a few hours later
the calendars commit a Merkle root that covers it into a Bitcoin transaction, and `ots upgrade` writes the
path from the file's hash up to that block's Merkle root into the proof. The block header holds that Merkle
root and the block's time, and it carries proof of work, so nobody can make one up afterwards. So:

  file bytes --SHA-256--> digest --(operations in the proof)--> Merkle root == bytes 36..68 of the header
  header time (bytes 68..72) is then an upper bound on when the file was written.

What is checked here: the path (every operation recomputed), the Merkle root against the header, the header's
proof of work against its own stated target, and that the stated target is at least as hard as `MAX_TARGET`
(so a header from a low-difficulty chain or a home-made one is refused). What is not checked: that the header
is on the main Bitcoin chain at the stated height. The height in the proof is used only to look the header up.
"""
import hashlib
import json
from pathlib import Path

MAGIC = b"\x00OpenTimestamps\x00\x00Proof\x00\xbf\x89\xe2\xe8\x84\xe8\x92\x94"
BITCOIN = bytes.fromhex("0588960d73d71901")
PENDING = bytes.fromhex("83dfe30d2ef90c8e")
# A header counts only if its stated target is at or below this (KR-201). 2**180 is a difficulty of about
# 1.8e13; the Bitcoin headers of 2026-11 read for the tests have targets near 2**176 (measured, see the test).
MAX_TARGET = 1 << 180
MAX_OPS = 10_000  # a proof read from a public branch is untrusted input: bound the walk


class EvidenceError(Exception):
    """The proof or header is malformed or does not match. Never a pass."""


class _Reader:
    def __init__(self, data):
        self.data, self.pos = data, 0

    def take(self, n):
        if n < 0 or self.pos + n > len(self.data):
            raise EvidenceError("proof ends early")
        out = self.data[self.pos:self.pos + n]
        self.pos += n
        return out

    def varuint(self):
        value = shift = 0
        while True:
            b = self.take(1)[0]
            value |= (b & 0x7F) << shift
            if not b & 0x80:
                return value
            shift += 7
            if shift > 63:
                raise EvidenceError("varuint too long")

    def varbytes(self, limit):
        n = self.varuint()
        if n > limit:
            raise EvidenceError("field too long")
        return self.take(n)


# Operations of the proof format that a path to a Bitcoin block does not use (SHA-1, RIPEMD-160, Keccak-256,
# reverse, hexlify). They take no argument, so the walk can pass through them; what lies under one is not
# recomputed and is never evidence.
NOT_RECOMPUTED = (0x02, 0x03, 0x67, 0xF2, 0xF3)


def _apply(tag, msg, r):
    """One OpenTimestamps operation. SHA-256, append and prepend are recomputed. `msg` None means the path
    passed through an operation that is not recomputed: its length is still read, its content is unknown."""
    if tag == 0x08:
        return None if msg is None else hashlib.sha256(msg).digest()
    if tag == 0xF0:
        arg = r.varbytes(4096)
        return None if msg is None else msg + arg
    if tag == 0xF1:
        arg = r.varbytes(4096)
        return None if msg is None else arg + msg
    if tag in NOT_RECOMPUTED:
        return None
    raise EvidenceError(f"operation 0x{tag:02x} is not known")


def attestations(proof, file_bytes):
    """Every attestation in a proof for `file_bytes`: a list of ("bitcoin", height, merkle root bytes) and
    ("pending", calendar url, b""). Raises EvidenceError if the proof is not for this file or is malformed."""
    r = _Reader(proof)
    if r.take(len(MAGIC)) != MAGIC:
        raise EvidenceError("not an OpenTimestamps proof")
    if r.varuint() != 1:
        raise EvidenceError("unknown proof version")
    if r.take(1) != b"\x08":
        raise EvidenceError("the file hash is not SHA-256")
    digest = r.take(32)
    if digest != hashlib.sha256(file_bytes).digest():
        raise EvidenceError("the proof is for a different file")
    out = []
    budget = [MAX_OPS]

    def one(tag, msg):
        budget[0] -= 1
        if budget[0] < 0:
            raise EvidenceError("proof too large")
        if tag == 0x00:
            kind = r.take(8)
            payload = _Reader(r.varbytes(8192))
            if kind == BITCOIN:
                height = payload.varuint()
                if msg is not None:  # under an operation that is not recomputed there is nothing to compare
                    out.append(("bitcoin", height, msg))
            elif kind == PENDING:
                out.append(("pending", payload.varbytes(1000).decode("utf-8", "replace"), b""))
            return  # any other attestation kind is ignored: it is not evidence here
        walk(_apply(tag, msg, r))

    def walk(msg):
        tag = r.take(1)[0]
        while tag == 0xFF:  # a fork: this branch, then more
            one(r.take(1)[0], msg)
            tag = r.take(1)[0]
        one(tag, msg)

    try:
        walk(digest)
    except RecursionError as e:
        raise EvidenceError("proof too deep") from e
    if r.pos != len(proof):
        raise EvidenceError("bytes after the end of the proof")
    return out


def header_fields(header_hex, max_target=MAX_TARGET):
    """(merkle root bytes, time as integer seconds) of an 80-byte block header, after checking its proof of
    work against its own target and the target against `max_target`."""
    try:
        h = bytes.fromhex(header_hex)
    except (ValueError, TypeError) as e:
        raise EvidenceError("header is not hex") from e
    if len(h) != 80:
        raise EvidenceError("a block header is 80 bytes")
    bits = int.from_bytes(h[72:76], "little")
    exponent, mantissa = bits >> 24, bits & 0x007FFFFF
    if bits & 0x00800000 or mantissa == 0 or exponent < 3 or exponent > 32:
        raise EvidenceError("header target is malformed")
    target = mantissa << (8 * (exponent - 3))
    if target > max_target:
        raise EvidenceError("header target is easier than the accepted floor")
    work = int.from_bytes(hashlib.sha256(hashlib.sha256(h).digest()).digest(), "little")
    if work > target:
        raise EvidenceError("header does not meet its own proof-of-work target")
    return h[36:68], int.from_bytes(h[68:72], "little")


def attested_time(proof, file_bytes, headers, max_target=MAX_TARGET):
    """Earliest block time (integer seconds, UTC) among the proof's Bitcoin attestations whose header is in
    `headers` ({height as string: 160 hex characters}) and matches, or None if the proof has no Bitcoin
    attestation with a supplied header. A supplied header that does not match its attestation is an error,
    not a miss."""
    best = None
    for kind, height, root in attestations(proof, file_bytes):
        if kind != "bitcoin" or str(height) not in headers:
            continue
        merkle, when = header_fields(headers[str(height)], max_target)
        if merkle != root:
            raise EvidenceError(f"block {height}: the header's Merkle root is not the one the proof reaches")
        best = when if best is None else min(best, when)
    return best


def heights(proof, file_bytes):
    """Block heights the proof names (the headers a verifier has to supply)."""
    return sorted({h for kind, h, _ in attestations(proof, file_bytes) if kind == "bitcoin"})


def load_headers(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not all(isinstance(v, str) for v in data.values()):
        raise EvidenceError("headers file must be an object {height: header hex}")
    return {str(k): v for k, v in data.items()}


def anchor_times(anchors_dir, headers, max_target=MAX_TARGET):
    """{anchor file name: attested block time or None} for every `*.json` in a folder. An anchor without a proof,
    with a pending proof, or with no supplied header gives None: it is no evidence of time."""
    out = {}
    for p in sorted(Path(anchors_dir).glob("*.json")):
        proof = Path(str(p) + ".ots")
        out[p.name] = attested_time(proof.read_bytes(), p.read_bytes(), headers, max_target) if proof.exists() else None
    return out


def needed_heights(anchors_dir):
    """Every block height named by the proofs in a folder, and the anchors still pending."""
    need, pending = set(), []
    for p in sorted(Path(anchors_dir).glob("*.json")):
        proof = Path(str(p) + ".ots")
        hs = heights(proof.read_bytes(), p.read_bytes()) if proof.exists() else []
        need.update(hs)
        if not hs:
            pending.append(p.name)
    return sorted(need), pending


# A block's time is written by its miner: it must be later than the median of the previous eleven blocks and
# nodes refuse a block more than two hours ahead of their clock. Two hours is taken off every bound for a block
# stamped earlier than it was mined (KR-201).
MARGIN_SECONDS = 7200


def proven_before(seq, bound, anchors, times, margin=MARGIN_SECONDS):
    """Was ledger line `seq` provably written before `bound` (integer seconds, UTC)?

    `anchors` is a list of (file name, count): an anchor covers line `seq` when its count is above `seq` (the
    caller has already checked that line `count - 1` has the anchor's head, so every earlier line is fixed by the
    chain). `times` is `anchor_times()`. Returns (True, name, block time) for the earliest covering anchor whose
    block time plus the margin is before the bound, else (False, reason, None)."""
    covering = [(times.get(name), name) for name, count in anchors if count > seq]
    if not covering:
        return False, "no anchor covers this row", None
    dated = sorted((t, name) for t, name in covering if t is not None)
    if not dated:
        return False, "every anchor that covers this row is still pending, or its block header was not supplied", None
    t, name = dated[0]
    if t + margin < bound:
        return True, name, t
    return False, f"the earliest block time over this row ({t}, anchor {name}) plus {margin} s is not before {bound}", t
