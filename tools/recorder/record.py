#!/usr/bin/env python3
"""Daily public-data recorder. Neutral tooling: standard library, no financial logic.

Fetches each enabled source in sources.json, keeps the raw bytes under data/recorder/ (ignored by git, so no
source's data is ever committed), and writes the hash, size and time to the forward log. Identical bytes
are still logged, because "nothing new today" is evidence too. Run it once a day:

  python tools/recorder/record.py [--sources FILE] [--data DIR] [--log FILE]

Exit status: 0 all fetched, 1 any source failed. A failure is logged too, so that gaps are visible.
"""
import argparse
import hashlib
import importlib.util
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
spec = importlib.util.spec_from_file_location("forward_log", ROOT / "tools" / "forward-log" / "forward_log.py")
fl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fl)

USER_AGENT = "Mozilla/5.0 (compatible; quantforge-recorder/0.1)"
REQUIRED = ("id", "url", "licence", "licence_url", "terms_checked", "attribution", "redistribute_raw", "enabled")


def fetch(url, timeout):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def load_sources(path):
    sources = json.loads(Path(path).read_text(encoding="utf-8"))["sources"]
    for s in sources:
        missing = [k for k in REQUIRED if k not in s]
        if missing:
            raise ValueError(f"source {s.get('id')} lacks {missing}: no source runs without a recorded licence")
    return sources


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sources", default=str(HERE / "sources.json"))
    ap.add_argument("--data", default=str(ROOT / "data" / "recorder"))
    ap.add_argument("--log", default=str(fl.DEFAULT_LOG))
    ap.add_argument("--timeout", type=float, default=60)
    a = ap.parse_args()
    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    failed = 0
    for s in load_sources(a.sources):
        if not s["enabled"]:
            continue
        url = s["url"].replace("{year}", str(now.year))
        try:
            raw = fetch(url, a.timeout)
            digest = hashlib.sha256(raw).hexdigest()
            out = Path(a.data) / s["id"] / f"{now:%Y-%m-%d}-{digest[:12]}.raw"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(raw)
            value = {"kind": "recording", "url": url, "sha256": digest, "bytes": len(raw), "licence": s["licence"]}
            print(f"{s['id']}: {len(raw)} bytes {digest[:12]}")
        except (OSError, ValueError) as e:
            failed += 1
            value = {"kind": "recording_failed", "url": url, "error": str(e)[:200], "licence": s["licence"]}
            print(f"{s['id']}: FAILED {e}", file=sys.stderr)
        fl.append(a.log, f"recorder/{s['id']}", stamp, value)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
