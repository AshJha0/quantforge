#!/usr/bin/env python3
"""Append-only forward log. Neutral tooling: standard library, no financial logic.

Each line of the log is {"record": ..., "hash": ...}. A record has the shape in
specifications/01-core/asof-store.md, and the hash is that spec's chain, so the log can be read by
core.store.* operations. Results cannot be chosen afterwards: changing an old line breaks every later hash.

  forward_log.py add --series ID --event-time INSTANT --value JSON [--log FILE]
  forward_log.py verify [--log FILE]
"""
import argparse
import hashlib
import json
import struct
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_LOG = HERE / "log.jsonl"
ZERO = "0" * 64


def canon(v):
    """Canonical form from specifications/01-core/snapshot-hash.md."""
    if v is None:
        return "null"
    if v is True:
        return "true"
    if v is False:
        return "false"
    if isinstance(v, (int, float)):
        return "#" + struct.pack(">d", float(v) + 0.0 if v else 0.0).hex()
    if isinstance(v, str):
        out = []
        for ch in v:
            if ch in '"\\':
                out.append("\\" + ch)
            elif ord(ch) < 0x20:
                out.append(f"\\u{ord(ch):04x}")
            else:
                out.append(ch)
        return '"' + "".join(out) + '"'
    if isinstance(v, list):
        return "[" + ",".join(canon(x) for x in v) + "]"
    keys = sorted(v, key=lambda k: k.encode("utf-8"))
    return "{" + ",".join(canon(k) + ":" + canon(v[k]) for k in keys) + "}"


def link(prev, record):
    return hashlib.sha256((prev + canon(record)).encode("utf-8")).hexdigest()


def read(path):
    p = Path(path)
    if not p.exists():
        return []
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def verify(path):
    """Returns (count, head). Raises ValueError at the first broken line."""
    head, seq, known = ZERO, 0, ""
    lines = read(path)
    for i, e in enumerate(lines, 1):
        r = e["record"]
        if r["sequence"] <= seq:
            raise ValueError(f"line {i}: sequence does not increase")
        if r["knowledge_time"] < known:
            raise ValueError(f"line {i}: knowledge_time goes backwards")
        head = link(head, r)
        if head != e["hash"]:
            raise ValueError(f"line {i}: hash does not match; the log was changed")
        seq, known = r["sequence"], r["knowledge_time"]
    return len(lines), head


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def commit():
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=HERE, capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def append(path, series_id, event_time, value, knowledge_time=None):
    """Verifies the existing log first, so that nothing is added to a broken one."""
    count, head = verify(path)
    seq = read(path)[-1]["record"]["sequence"] + 1 if count else 1
    rec = {"sequence": seq, "series_id": series_id, "event_time": event_time, "knowledge_time": knowledge_time or now(),
           "value": {"commit": commit(), "payload": value}}
    line = json.dumps({"record": rec, "hash": link(head, rec)}, ensure_ascii=False, sort_keys=True)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        f.write(line + "\n")
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["add", "verify"])
    ap.add_argument("--log", default=str(DEFAULT_LOG))
    ap.add_argument("--series")
    ap.add_argument("--event-time")
    ap.add_argument("--value")
    a = ap.parse_args()
    if a.command == "verify":
        try:
            n, h = verify(a.log)
        except ValueError as e:
            print(e, file=sys.stderr)
            return 1
        print(f"{n} entries, head {h}")
        return 0
    if not (a.series and a.event_time and a.value):
        ap.error("add needs --series, --event-time and --value")
    print(json.dumps(append(a.log, a.series, a.event_time, json.loads(a.value))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
