"""The 10,000 round-trip records and the one content hash (adapters.md 1.1, 1.2; KR-270, KR-271).

`canon` is the canonical form of specifications/01-core/snapshot-hash.md, written again here so the adapter
services need no library import (KR-283); tests/test_records.py checks it byte for byte against
quantforge_core.snapshot.canonical over every record.
"""

import hashlib
import json
import struct
from collections import Counter
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

SEED = 20261109
N = 10_000
KINDS = ("quote", "trade", "curve_point", "risk_row")
TENORS = ("1M", "3M", "6M", "1Y", "2Y", "5Y", "10Y", "30Y")
Record = dict[str, Any]


def dec(x: int, d: int) -> str:
    """The integer x as a decimal string with d digits after the point (dec(-5, 2) = "-0.05")."""
    sign = "-" if x < 0 else ""
    digits = str(abs(x)).rjust(d + 1, "0")
    return f"{sign}{digits[:-d]}.{digits[-d:]}"


def make_record(seq: int, u: list[int]) -> Record:
    u0, u1, u2, u3 = u
    kind = KINDS[seq % 4]
    body: dict[str, Any] = {"value": (u3 >> 11) * 2.0**-53}
    if kind == "quote":
        t = 1_000_000 + u0 % 1_000_000
        body.update(bid=dec(t, 4), ask=dec(t + 1 + u1 % 10, 4))
    elif kind == "trade":
        body.update(
            price=dec(1_000_000 + u0 % 1_000_000, 4), qty=str(1 + u1 % 10_000), side="B" if u2 % 2 else "S"
        )
    elif kind == "curve_point":
        body.update(tenor=TENORS[u0 % 8], rate=dec(u1 % 100_000 - 20_000, 6))
    else:
        body.update(book=f"B{u0 % 16}", dv01=dec(u1 % 10_000_000 - 5_000_000, 2))
    return {"seq": seq, "kind": kind, "body": body}


def make_records(next_u64: Callable[[int, int, int], list[int]], n: int = N) -> list[Record]:
    return [make_record(seq, next_u64(SEED, seq, 4)) for seq in range(1, n + 1)]


# ---- canonical form (01-core/snapshot-hash.md) -----------------------------------------------------------


def _string(text: str) -> str:
    out = ['"']
    for ch in text:
        if ch == '"':
            out.append('\\"')
        elif ch == "\\":
            out.append("\\\\")
        elif ord(ch) < 0x20:
            out.append(f"\\u{ord(ch):04x}")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def canonical(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, (int, float)):
        x = float(value)
        return "#" + struct.pack(">d", 0.0 if x == 0 else x).hex()
    if isinstance(value, str):
        return _string(value)
    if isinstance(value, list):
        return "[" + ",".join(canonical(v) for v in value) + "]"
    if isinstance(value, dict):
        keys = sorted(value, key=lambda k: k.encode("utf-8"))
        return "{" + ",".join(_string(k) + ":" + canonical(value[k]) for k in keys) + "}"
    raise TypeError(f"not a JSON value: {type(value).__name__}")


def canon(record: Record) -> bytes:
    return canonical(record).encode("utf-8")


def snapshot_id(record: Record) -> str:
    return "sha256:" + hashlib.sha256(canon(record)).hexdigest()


# ---- the content hash and the verdict ---------------------------------------------------------------------


class Verdict(Exception):
    """COUNT, HASH or BYPASS (adapters.md 1.2, 1.4)."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code


def count_check(records: Iterable[Record], n: int = N) -> list[Record]:
    rows = list(records)
    seqs = Counter(r.get("seq") for r in rows)
    missing = [s for s in range(1, n + 1) if s not in seqs]
    dupes = [s for s, c in seqs.items() if c > 1]
    extra = [s for s in seqs if not (isinstance(s, int) and 1 <= s <= n)]
    if missing or dupes or extra or len(rows) != n:
        raise Verdict(
            "COUNT", f"{len(rows)} rows; missing {missing[:3]}, duplicated {dupes[:3]}, extra {extra[:3]}"
        )
    return sorted(rows, key=lambda r: int(r["seq"]))


def content_hash(records: Iterable[Record], n: int = N) -> str:
    h = hashlib.sha256()
    for r in count_check(records, n):
        h.update(canon(r) + b"\n")
    return h.hexdigest()


def verdict(sent: list[Record], read: list[Record], store_count: int | None = None, n: int = N) -> str:
    """PASS, or raise Verdict(COUNT | BYPASS | HASH)."""
    h_sent = content_hash(sent, n)
    h_read = content_hash(read, n)
    if store_count is not None and store_count != n:
        raise Verdict("BYPASS", f"the store's own count is {store_count}, not {n}")
    if h_sent != h_read:
        raise Verdict("HASH", f"sent {h_sent[:16]}, read {h_read[:16]}")
    return "PASS"


def load(path: Path) -> list[Record]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def from_canon(raw: bytes | str) -> Record:
    """Map canonical bytes back to a record: numbers come back from their binary64 hex form."""
    text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
    pos = 0

    def value() -> Any:
        nonlocal pos
        c = text[pos]
        if c == "#":
            bits = bytes.fromhex(text[pos + 1 : pos + 17])
            pos += 17
            x = struct.unpack(">d", bits)[0]
            return int(x) if x.is_integer() and abs(x) < 2**53 else x
        if c == '"':
            end = pos + 1
            out = []
            while text[end] != '"':
                if text[end] == "\\":
                    nxt = text[end + 1]
                    if nxt == "u":
                        out.append(chr(int(text[end + 2 : end + 6], 16)))
                        end += 6
                    else:
                        out.append(nxt)
                        end += 2
                else:
                    out.append(text[end])
                    end += 1
            pos = end + 1
            return "".join(out)
        if c == "{":
            pos += 1
            obj: dict[str, Any] = {}
            while text[pos] != "}":
                key = value()
                pos += 1  # ':'
                obj[key] = value()
                if text[pos] == ",":
                    pos += 1
            pos += 1
            return obj
        if c == "[":
            pos += 1
            arr = []
            while text[pos] != "]":
                arr.append(value())
                if text[pos] == ",":
                    pos += 1
            pos += 1
            return arr
        for lit, v in (("null", None), ("true", True), ("false", False)):
            if text.startswith(lit, pos):
                pos += len(lit)
                return v
        raise ValueError(f"not canonical at {pos}")

    out = value()
    if pos != len(text) or not isinstance(out, dict):
        raise ValueError("trailing bytes or not an object")
    return out
