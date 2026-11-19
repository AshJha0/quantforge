#!/usr/bin/env python3
"""Tolerant reader for the crypto L2 recorder's gzip JSON-lines files (2026-11-18).

Files written before the 2026-11-18 fix can hold several gzip members, some cut short by a hard kill and followed by
a new member appended on restart. gzip.open stops at the first broken member. This reader decodes every member it
can: on a truncated or corrupt member it keeps every complete line decoded so far, skips to the next gzip header
(1f 8b 08) and carries on. It reports how many compressed bytes it could not decode.

  python -I tools/recorder/read_gz.py FILE [FILE ...]      prints a per-file summary (lines, members, bytes lost)

Library use: `lines, report = read_lines(path)`; `report` is a dict with members, broken, bytes_lost, lines.
"""
import sys
import zlib
from pathlib import Path

MAGIC = b"\x1f\x8b\x08"


CHUNK = 256


def _is_member_start(data, pos):
    """True if a gzip member plausibly starts at pos: the header parses and output decodes before any error."""
    if data[pos:pos + 3] != MAGIC:
        return False
    d = zlib.decompressobj(31)
    for p in range(pos, min(len(data), pos + 65536), CHUNK):
        d, o, ok, _ = _feed(d, data[p:p + CHUNK])
        if o or d.eof:
            return True
        if not ok:
            return False
    return False


def _next_start(data, pos):
    """Offset of the next plausible member start after pos, or len(data)."""
    nxt = data.find(MAGIC, pos + 1)
    while nxt >= 0 and not _is_member_start(data, nxt):
        nxt = data.find(MAGIC, nxt + 1)
    return len(data) if nxt < 0 else nxt


def _feed(d, piece):
    """Decompress piece; on a decode error, redo it byte by byte from the state before it, keeping every byte of
    output produced before the error. Returns (decompressor, output, ok, used) where used is the number of bytes of
    piece up to the last one that produced output (all of it when ok)."""
    snap = d.copy()
    try:
        return d, d.decompress(piece), True, len(piece)
    except zlib.error:
        d, out, used = snap, [], 0
        for i in range(len(piece)):
            try:
                o = d.decompress(piece[i:i + 1])
            except zlib.error:
                break
            if o:
                out.append(o)
                used = i + 1
        return d, b"".join(out), False, used


def _decode_member(data, start):
    """Decode one gzip member at data[start:]. Returns (output, end_offset, intact, bytes_lost).

    Intact members end at their trailer. A broken member (cut short, or followed by appended bytes) ends at the next
    plausible member start; its output is kept up to the first decode error, in CHUNK-byte steps, and the compressed
    bytes after the last chunk that produced output are counted as lost."""
    d, out, pos, good, ok = zlib.decompressobj(31), [], start, start, True
    # Candidate boundaries: every later gzip magic. Decode up to each; a member that reaches its trailer first is
    # intact whatever follows; otherwise the first candidate that is a plausible member start ends this one.
    cand = data.find(MAGIC, start + 1)
    while True:
        limit = len(data) if cand < 0 else cand
        while ok and pos < limit:
            piece = data[pos:min(pos + CHUNK, limit)]
            d, o, ok, used = _feed(d, piece)
            out.append(o)
            if d.eof:
                return b"".join(out), pos + len(piece) - len(d.unused_data), True, 0
            if o:
                good = pos + used
            pos += len(piece)
        if cand < 0 or _is_member_start(data, cand):
            return b"".join(out), limit, False, max(0, limit - good)
        cand = data.find(MAGIC, cand + 1)


def read_lines(path):
    data = Path(path).read_bytes()
    lines, members, broken, lost, pos = [], 0, 0, 0, 0
    while pos < len(data):
        if not _is_member_start(data, pos):
            nxt = _next_start(data, pos)
            lost += nxt - pos
            pos = nxt
            continue
        out, end, intact, gone = _decode_member(data, pos)
        members += 1
        lost += gone
        parts = out.split(b"\n")
        if not intact:
            broken += 1
            parts = parts[:-1]  # the partial last line of a broken member is dropped
        elif parts and parts[-1] == b"":
            parts = parts[:-1]
        lines.extend(p.decode("utf-8", "replace") for p in parts if p)
        pos = end
    return lines, {"members": members, "broken": broken, "bytes_lost": lost, "lines": len(lines), "size": len(data)}


def main(argv):
    rc = 0
    for f in argv:
        _, r = read_lines(f)
        print(f"{f}: {r['lines']} lines, {r['members']} members, {r['broken']} broken, "
              f"{r['bytes_lost']} of {r['size']} compressed bytes lost")
        rc |= 1 if r["broken"] or r["bytes_lost"] else 0
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
