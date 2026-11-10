#!/usr/bin/env python3
"""Daily public-data recorder. Neutral tooling: standard library, no financial logic.

Fetches each enabled source in sources.json, keeps the raw bytes and the source's notice under data/recorder/ (ignored by git, so no
source's data is ever committed), and writes the hash, size and time to the forward log. Identical bytes
are logged but stored once, because "nothing new today" is evidence too.

Public-domain sources with a "parse" entry also keep their parsed values in the log itself: each row carries the
observations that are new or changed since the previous row, and state_sha256, the hash of the whole parsed state
after this row, so anyone can replay the log and recheck the hash (gap_monitor.py recheck). A changed past value is
written as its own row under revision/<source id>. After the sources, one row per study in studies.json is written
under study/<study id>, even when the study has no position yet. Every row carries sources_sha256, the hash of the
sources.json the run used. Run it once a day:

  python tools/recorder/record.py [--sources FILE] [--studies FILE] [--data DIR] [--log FILE]

Exit status: 0 all fetched, 1 any source failed. A failure is logged too, so that gaps are visible.
"""
import argparse
import csv
import hashlib
import importlib.util
import io
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
spec = importlib.util.spec_from_file_location("forward_log", ROOT / "tools" / "forward-log" / "forward_log.py")
fl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fl)

USER_AGENT = "Mozilla/5.0 (compatible; quantforge-recorder/0.2)"
REQUIRED = ("id", "url", "licence", "licence_url", "terms_checked", "attribution", "redistribute_raw", "notice", "enabled")


RETRY_STATUS = (429, 500, 502, 503, 504)


def fetch(url, timeout, attempts=4, backoff=15.0, sleep=time.sleep):
    """GET url. Transient failures (HTTP 429/5xx, timeouts, connection resets) are retried with
    linear backoff, because public statistics APIs (the ECB data API in particular) return
    occasional 504s. Other errors, and the last failed attempt, are raised to the caller."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code not in RETRY_STATUS or attempt == attempts:
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if attempt == attempts:
                raise
        sleep(backoff * attempt)


def parse_treasury_csv(raw, fields):
    """Treasury daily rates CSV to {"YYYY-MM-DD|field": value}. Blank and N/A cells are left out."""
    out = {}
    for row in csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))):
        m, d, y = row["Date"].split("/")
        for f in fields:
            v = (row.get(f) or "").strip()
            if v and v.upper() != "N/A":
                out[f"{y}-{m}-{d}|{f}"] = float(v)
    if not out:
        raise ValueError("parsed no values: the feed format may have changed")
    return out


def parse_bls_v1(raw, fields=None):
    """BLS public API v1 JSON to {"YYYY-MM|series": value}. Monthly periods only (M13 is the annual average)."""
    doc = json.loads(raw.decode("utf-8"))
    if doc.get("status") != "REQUEST_SUCCEEDED":
        raise ValueError(f"BLS status {doc.get('status')}: {doc.get('message')}")
    out = {}
    for series in doc["Results"]["series"]:
        for o in series["data"]:
            if o["period"].startswith("M") and o["period"] != "M13" and o["value"] not in ("", "-"):
                out[f"{o['year']}-{o['period'][1:]}|{series['seriesID']}"] = float(o["value"])
    if not out:
        raise ValueError("parsed no values: the feed format may have changed")
    return out


PARSERS = {"treasury_csv": parse_treasury_csv, "bls_v1": parse_bls_v1}


def state_hash(state):
    return hashlib.sha256(fl.canon(state).encode("utf-8")).hexdigest()


def replay(log, source_id):
    """Parsed state of one source rebuilt from the log: later observations replace earlier ones."""
    state = {}
    for e in fl.read(log):
        r = e["record"]
        if r["series_id"] == f"recorder/{source_id}":
            state.update(r["value"]["payload"].get("observations", {}))
    return state


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
    ap.add_argument("--studies", default=str(HERE / "studies.json"))
    ap.add_argument("--data", default=str(ROOT / "data" / "recorder"))
    ap.add_argument("--log", default=str(fl.DEFAULT_LOG))
    ap.add_argument("--timeout", type=float, default=60)
    a = ap.parse_args()
    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    sources_sha = hashlib.sha256(Path(a.sources).read_bytes()).hexdigest()
    failed = 0
    today = {}
    for s in load_sources(a.sources):
        if not s["enabled"]:
            continue
        url = s["url"].replace("{year}", str(now.year))
        try:
            raw = fetch(url, a.timeout)
            digest = hashlib.sha256(raw).hexdigest()
            out = Path(a.data) / s["id"] / f"{now:%Y-%m-%d}-{digest[:12]}.raw"
            out.parent.mkdir(parents=True, exist_ok=True)
            if not any(out.parent.glob(f"*-{digest[:12]}.raw")):  # same bytes are stored once, but still logged
                out.write_bytes(raw)
            (out.parent / "NOTICE.txt").write_text(s["notice"] + "\n", encoding="utf-8")
            value = {"kind": "recording", "url": url, "sha256": digest, "bytes": len(raw), "licence": s["licence"]}
            today[s["id"]] = digest
            if s.get("parse"):
                parsed = PARSERS[s["parse"]["format"]](raw, s["parse"].get("fields"))
                old = replay(a.log, s["id"])
                changed = {k: v for k, v in sorted(parsed.items()) if old.get(k) != v}
                for k in sorted(changed):
                    if k in old:
                        fl.append(a.log, f"revision/{s['id']}", stamp, {"kind": "revision", "key": k, "old": old[k],
                                  "new": changed[k], "sources_sha256": sources_sha})
                old.update(changed)
                value["observations"] = changed
                value["state_sha256"] = today[s["id"]] = state_hash(old)
            print(f"{s['id']}: {len(raw)} bytes {digest[:12]}")
        except (OSError, ValueError, KeyError) as e:
            failed += 1
            today.pop(s["id"], None)
            value = {"kind": "recording_failed", "url": url, "error": str(e)[:200], "licence": s["licence"]}
            print(f"{s['id']}: FAILED {e}", file=sys.stderr)
        value["sources_sha256"] = sources_sha
        fl.append(a.log, f"recorder/{s['id']}", stamp, value)
    if Path(a.studies).exists():
        for st in json.loads(Path(a.studies).read_text(encoding="utf-8"))["studies"]:
            # Computed from recorded inputs only. Until a study runs, its row says "no position", but it is written every day.
            fl.append(a.log, f"study/{st['id']}", stamp, {
                "kind": "study_position", "position": None, "signal": None, "status": st["status"],
                "inputs": {i: today.get(i) for i in st["inputs"]}, "sources_sha256": sources_sha})
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
