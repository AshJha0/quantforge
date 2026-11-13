#!/usr/bin/env python3
"""Crypto L2 recorder (R6-23). Records a public order-book feed locally; nothing it writes goes into git.

Source: Kraken spot websocket v2, public endpoint wss://ws.kraken.com/v2, channels `book` (depth 25) and `trade`.
No account, key or card. Terms read 2026-11-12, see STAGE_H_DATA_SURVEY.md in the plan folder: use is for our own
benefit, so raw data stays on this machine and only aggregates or derived statistics may be published, each labelled
"crypto venue; not equities or rates".

Output, one gzip JSON-lines file per symbol per UTC hour under --out (default C:/Work/Claude/qf-crypto-data/kraken):
  {"t": "...Z", "k": "book", "bids": [[px, qty] x20], "asks": [[px, qty] x20], "ok": true}   once a second
  {"t": "...Z", "k": "trade", "d": [...raw trade objects...]}                              as received
  {"t": "...Z", "k": "gap", "why": "..."}                                                  on every reconnect
"ok" is the result of Kraken's CRC32 book checksum on the top 10 levels at the last update.

  python tools/recorder/crypto_l2.py [--symbols BTC/USD ETH/USD] [--out DIR] [--seconds N]

Needs the `websockets` package (pip). Standard library otherwise. Runs until stopped; reconnects with backoff.
"""
import argparse
import asyncio
import gzip
import json
import time
import zlib
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

URL = "wss://ws.kraken.com/v2"
DEPTH = 25   # Kraken offers 10, 25, 100, 500, 1000; 25 is the smallest that covers top 20
KEEP = 20


def now():
    return datetime.now(timezone.utc)


def stamp(t):
    return t.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


PRECISION = {}  # symbol -> (price decimals, qty decimals), from the public AssetPairs REST call at start


def load_precision(symbols):
    import urllib.request
    with urllib.request.urlopen("https://api.kraken.com/0/public/AssetPairs", timeout=30) as r:
        res = json.loads(r.read())["result"]
    by_ws = {v.get("wsname", "").replace("XBT/", "BTC/"): (v["pair_decimals"], v["lot_decimals"]) for v in res.values()}
    for s in symbols:
        PRECISION[s] = by_ws[s]


def _fmt(x, dp):
    """Kraken checksum string: value at the pair's precision, decimal point and leading zeros removed."""
    s = format(Decimal(x).quantize(Decimal(1).scaleb(-dp)), "f").replace(".", "").lstrip("0")
    return s or "0"


def checksum(bids, asks, pdp=1, qdp=8):
    """CRC32 over the top 10 asks (ascending) then top 10 bids (descending), per Kraken's book checksum guide."""
    s = "".join(_fmt(p, pdp) + _fmt(q, qdp) for p, q in asks[:10]) + "".join(_fmt(p, pdp) + _fmt(q, qdp) for p, q in bids[:10])
    return zlib.crc32(s.encode()) & 0xFFFFFFFF


class Book:
    def __init__(self):
        self.bids, self.asks, self.ok = {}, {}, False

    def apply(self, side, levels):
        book = self.bids if side == "bids" else self.asks
        for lv in levels:
            p, q = Decimal(lv["price"]), Decimal(lv["qty"])
            if q == 0:
                book.pop(p, None)
            else:
                book[p] = q
        # keep only DEPTH levels, as the venue does
        keys = sorted(book, reverse=(side == "bids"))
        for p in keys[DEPTH:]:
            del book[p]

    def top(self, n):
        b = sorted(self.bids.items(), key=lambda kv: -kv[0])[:n]
        a = sorted(self.asks.items(), key=lambda kv: kv[0])[:n]
        return b, a


class Sink:
    def __init__(self, out, symbol):
        self.dir = Path(out) / symbol.replace("/", "-")
        self.dir.mkdir(parents=True, exist_ok=True)
        self.hour, self.fh = None, None

    def write(self, rec):
        t = now()
        h = t.strftime("%Y%m%dT%H")
        if h != self.hour:
            if self.fh:
                self.fh.close()
            self.fh = gzip.open(self.dir / f"{h}.jsonl.gz", "at", encoding="utf-8")
            self.hour = h
        rec = {"t": stamp(t), **rec}
        self.fh.write(json.dumps(rec, separators=(",", ":"), default=str) + "\n")

    def close(self):
        if self.fh:
            self.fh.close()


async def session(symbols, books, sinks):
    import websockets
    async with websockets.connect(URL, ping_interval=20, max_size=2**24) as ws:
        await ws.send(json.dumps({"method": "subscribe", "params": {"channel": "book", "symbol": symbols, "depth": DEPTH}}))
        await ws.send(json.dumps({"method": "subscribe", "params": {"channel": "trade", "symbol": symbols, "snapshot": False}}))
        async for raw in ws:
            m = json.loads(raw, parse_float=Decimal)
            ch = m.get("channel")
            if ch == "book":
                for d in m.get("data", []):
                    b = books[d["symbol"]]
                    if m.get("type") == "snapshot":
                        b.bids, b.asks = {}, {}
                    b.apply("bids", d.get("bids", []))
                    b.apply("asks", d.get("asks", []))
                    bb, aa = b.top(10)
                    b.ok = checksum(bb, aa, *PRECISION[d["symbol"]]) == d.get("checksum")
            elif ch == "trade":
                by = {}
                for d in m.get("data", []):
                    by.setdefault(d["symbol"], []).append(d)
                for s, ds in by.items():
                    sinks[s].write({"k": "trade", "d": ds})


async def ticker(books, sinks):
    while True:
        await asyncio.sleep(1.0 - (time.time() % 1.0))
        for s, b in books.items():
            if b.bids or b.asks:
                bb, aa = b.top(KEEP)
                sinks[s].write({"k": "book", "bids": [[str(p), str(q)] for p, q in bb],
                                "asks": [[str(p), str(q)] for p, q in aa], "ok": b.ok})


async def main_async(a):
    load_precision(a.symbols)
    books = {s: Book() for s in a.symbols}
    sinks = {s: Sink(a.out, s) for s in a.symbols}
    tick = asyncio.create_task(ticker(books, sinks))
    end = time.time() + a.seconds if a.seconds else None
    backoff = 1
    try:
        while end is None or time.time() < end:
            try:
                left = None if end is None else max(1, end - time.time())
                await asyncio.wait_for(session(a.symbols, books, sinks), timeout=left)
                why = "server closed"
            except asyncio.TimeoutError:
                break
            except Exception as e:  # network errors of any kind: log a gap and reconnect
                why = f"{type(e).__name__}: {e}"[:200]
            for s in a.symbols:
                books[s].bids, books[s].asks, books[s].ok = {}, {}, False
                sinks[s].write({"k": "gap", "why": why})
            print(f"{stamp(now())} reconnect after: {why}", flush=True)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)
    finally:
        tick.cancel()
        for s in sinks.values():
            s.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", nargs="+", default=["BTC/USD", "ETH/USD"])
    ap.add_argument("--out", default="C:/Work/Claude/qf-crypto-data/kraken")
    ap.add_argument("--seconds", type=float, default=0, help="stop after N seconds (0 = run until stopped)")
    a = ap.parse_args()
    print(f"{stamp(now())} recording {a.symbols} to {a.out}", flush=True)
    asyncio.run(main_async(a))


if __name__ == "__main__":
    main()
