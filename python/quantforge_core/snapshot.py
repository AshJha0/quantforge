"""Canonical form and hash of a snapshot (specifications/01-core/snapshot-hash.md)."""

import struct
from collections.abc import Iterator
from typing import Any

from . import strictjson
from .errors import QfError

MAX_DEPTH = 64


def _walk(value: Any) -> Iterator[tuple[Any, int]]:
    """Every value inside value, with its nesting depth. Not recursive: depth is not yet known."""
    stack = [(value, 0)]
    while stack:
        item, depth = stack.pop()
        yield item, depth
        if isinstance(item, list):
            stack.extend((v, depth + 1) for v in item)
        elif isinstance(item, dict):
            stack.extend((k, depth + 1) for k in item)
            stack.extend((v, depth + 1) for v in item.values())


def has_lone_surrogate(value: Any) -> bool:
    return any(
        isinstance(item, str) and any(0xD800 <= ord(ch) <= 0xDFFF for ch in item)
        for item, _ in _walk(value)
    )


def nesting_depth(value: Any) -> int:
    """An object or array is one level. Scalars add none."""
    return max(
        (depth + 1 for item, depth in _walk(value) if isinstance(item, (list, dict))), default=0
    )


def _string(s: str) -> str:
    out = ['"']
    for ch in s:
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


def _number(value: float) -> str:
    x = float(value)
    if x == 0:
        x = 0.0
    return "#" + struct.pack(">d", x).hex()


def canonical(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, (int, float)):
        return _number(value)
    if isinstance(value, str):
        return _string(value)
    if isinstance(value, list):
        return "[" + ",".join(canonical(v) for v in value) + "]"
    keys = sorted(value, key=lambda k: k.encode("utf-8"))
    return "{" + ",".join(_string(k) + ":" + canonical(value[k]) for k in keys) + "}"


def hash_value(value: Any) -> tuple[str, str]:
    form = canonical(value)
    import hashlib

    return form, "sha256:" + hashlib.sha256(form.encode("utf-8")).hexdigest()


def hash_document(text: str) -> tuple[str, str]:
    """Returns (canonical, snapshot_id). Both exclude a top-level snapshot_id."""
    strictjson.check_depth(text, MAX_DEPTH)
    document, overflowed = strictjson.parse(text)
    if overflowed:
        raise QfError("E_SCHEMA", "a number overflows binary64", "document_text")
    if has_lone_surrogate(document):
        raise QfError("E_SCHEMA", "lone surrogate in a string", "document_text")
    if not isinstance(document, dict):
        raise QfError("E_SCHEMA", "the top level is not an object", "document_text")
    return hash_value({k: v for k, v in document.items() if k != "snapshot_id"})
