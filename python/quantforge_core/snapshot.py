"""Canonical form and hash of a snapshot (specifications/01-core/snapshot-hash.md)."""
import hashlib
import struct
from typing import Any

from . import strictjson
from .errors import QfError


def _has_lone_surrogate(value: Any) -> bool:
    if isinstance(value, str):
        return any(0xD800 <= ord(ch) <= 0xDFFF for ch in value)
    if isinstance(value, list):
        return any(_has_lone_surrogate(v) for v in value)
    if isinstance(value, dict):
        return any(_has_lone_surrogate(k) or _has_lone_surrogate(v) for k, v in value.items())
    return False


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


def hash_document(text: str) -> tuple[str, str]:
    """Returns (canonical, snapshot_id). Both exclude a top-level snapshot_id."""
    document, overflowed = strictjson.parse(text)
    if overflowed:
        raise QfError("E_SCHEMA", "a number overflows binary64", "document_text")
    if _has_lone_surrogate(document):
        raise QfError("E_SCHEMA", "lone surrogate in a string", "document_text")
    if not isinstance(document, dict):
        raise QfError("E_SCHEMA", "the top level is not an object", "document_text")
    body = {k: v for k, v in document.items() if k != "snapshot_id"}
    form = canonical(body)
    return form, "sha256:" + hashlib.sha256(form.encode("utf-8")).hexdigest()
