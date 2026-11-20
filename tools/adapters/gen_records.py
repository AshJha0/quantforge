#!/usr/bin/env python3
"""Generate (or check) datasets/adapters/records-10000.jsonl, the K-3 round-trip records (KR-270).

Numbers come from quantforge_core.rng.next_u64(20261109, seq, 4); the record rules are in
platform/python/quantforge_adapters/records.py (adapters.md 1.1). Run with the library environment:

    cd python && uv run python ../tools/adapters/gen_records.py [--check]
"""

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "python"), str(ROOT / "platform" / "python")]

from quantforge_core import rng

from quantforge_adapters import records

OUT = ROOT / "datasets" / "adapters" / "records-10000.jsonl"
SUM = OUT.with_suffix(".sha256")


def main(argv: list[str]) -> int:
    rows = records.make_records(rng.next_u64)
    text = "".join(json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n" for r in rows).encode()
    longest = max(len(records.canon(r)) for r in rows)
    digest = hashlib.sha256(text).hexdigest()
    line = f"{digest}  records-10000.jsonl\ncontent_hash {records.content_hash(rows)}\n"
    if "--check" in argv:
        ok = OUT.read_bytes() == text and SUM.read_text(encoding="utf-8") == line
        print("records file", "current" if ok else "STALE")
        return 0 if ok else 1
    if longest > 512:
        print(f"a canonical record is {longest} bytes, over 512")
        return 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(text)
    SUM.write_text(line, encoding="utf-8", newline="\n")
    print(f"wrote {len(rows)} records, file sha256 {digest}, longest canonical record {longest} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
