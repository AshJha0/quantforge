#!/usr/bin/env python3
"""Crypto L2 recorder (R6-23). Records a public order-book feed locally; nothing it writes goes into git.

Source: Kraken spot websocket v2, public endpoint wss://ws.kraken.com/v2, channels `book` (depth 100) and `trade`.
No account, key or card. Terms read 2026-11-12, see STAGE_H_DATA_SURVEY.md in the plan folder: use is for our own
benefit, so raw data stays on this machine and only aggregates or derived statistics may be published, each labelled
"crypto venue; not equities or rates".

Output, one gzip JSON-lines file per symbol per UTC hour under --out (default C:/Work/Claude/qf-crypto-data/kraken):
  {"t": "...Z", "k": "book", "bids": [[px, qty] x100], "asks": [[px, qty] x100], "ok": true}   once a second
  {"t": "...Z", "k": "trade", "d": [...raw trade objects...]}                              as received
  {"t": "...Z", "k": "gap", "why": "..."}                                                  on every reconnect
Raw book messages (owner 2026-11-17, ruling HR-11: needed for the message-by-message H-2 rebuild and the H-9 replay)
go to a second file per symbol per hour under <SYMBOL>-raw/, every message as received, prices and quantities as the
exact decimal strings Kraken sent:
  {"t": "...Z", "k": "msg", "type": "snapshot"|"update", "bids": [...], "asks": [...], "checksum": n, "ts": "...", "ok": b}
"t" is the local receive time, "ts" Kraken's own timestamp (updates only), "ok" whether our book matched Kraken's
checksum after applying the message. A "gap" record is written here too on every reconnect.
"ok" is the result of Kraken's CRC32 book checksum on the top 10 levels at the last update.

Robustness (2026-11-18, after the watchdog killed the recorder mid-member): a restart inside an hour never appends;
it opens <hour>-1.jsonl.gz, -2, ... Files are sync-flushed every 30 s. Every 10 s the recorder writes
<out>/../heartbeat.json (pid, age of the last websocket message, snapshot depth); the watchdog judges liveness from it.
Creating <out>/STOP makes the recorder close every file cleanly and exit within about 10 s. Each book snapshot logs the
depth Kraken actually sent, with a WARNING if it is below DEPTH. Read files with read_gz.py, which recovers every
intact gzip member and reports the compressed bytes it could not decode.

  python tools/recorder/crypto_l2.py [--symbols BTC/USD ETH/USD] [--out DIR] [--seconds N] [--heartbeat FILE]

Needs the `websockets` package (pip). Standard library otherwise. Runs until stopped; reconnects with backoff.
"""
import argparse
import asyncio
import gzip
import json
import os
import time
import zlib
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

URL = "wss://ws.kraken.com/v2"
DEPTH = 100  # Kraken offers 10, 25, 100, 500, 1000; 100 covers walk-the-book cost curves for large orders (H-1(b)); owner 2026-11-17
KEEP = 100


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
    """One gzip JSON-lines file per UTC hour. Never appends to an existing file: a restart inside an hour opens
    <hour>-1.jsonl.gz, -2, ... so a member cut short by a hard kill stays at the end of its own file. Flushes
    (zlib sync flush) at most every FLUSH_S seconds, so a hard kill loses at most that much, and every byte before
    the last flush decodes (see read_gz.py)."""

    FLUSH_S = 30.0

    def __init__(self, out, symbol, clock=None):
        self.dir = Path(out) / symbol.replace("/", "-")
        self.dir.mkdir(parents=True, exist_ok=True)
        self.hour, self.fh, self.path, self.last_flush = None, None, None, time.monotonic()
        self.clock = clock or now

    def _open(self, h):
        p, n = self.dir / f"{h}.jsonl.gz", 0
        while p.exists():
            n += 1
            p = self.dir / f"{h}-{n}.jsonl.gz"
        self.path = p
        self.fh = gzip.open(p, "xt", encoding="utf-8")  # "x": fail rather than ever touch an existing file
        self.hour = h

    def write(self, rec):
        t = self.clock()
        h = t.strftime("%Y%m%dT%H")
        if h != self.hour:
            self.close()
            self._open(h)
        rec = {"t": stamp(t), **rec}
        self.fh.write(json.dumps(rec, separators=(",", ":"), default=str) + "\n")
        if time.monotonic() - self.last_flush >= self.FLUSH_S:
            self.flush()

    def flush(self):
        if self.fh:
            self.fh.flush()
        self.last_flush = time.monotonic()

    def close(self):
        if self.fh:
            self.fh.close()
            self.fh, self.hour = None, None


class NullSink:
    def write(self, rec):
        pass

    def flush(self):
        pass

    def close(self):
        pass


async def session(symbols, books, sinks, raws):
    import websockets
    async with websockets.connect(URL, ping_interval=20, max_size=2**24) as ws:
        await ws.send(json.dumps({"method": "subscribe", "params": {"channel": "book", "symbol": symbols, "depth": DEPTH}}))
        await ws.send(json.dumps({"method": "subscribe", "params": {"channel": "trade", "symbol": symbols, "snapshot": False}}))
        async for raw in ws:
            STATE["last_msg"] = time.time()
            m = json.loads(raw, parse_float=Decimal)
            ch = m.get("channel")
            if ch == "book":
                for d in m.get("data", []):
                    b = books[d["symbol"]]
                    if m.get("type") == "snapshot":
                        b.bids, b.asks = {}, {}
                        nb, na = len(d.get("bids", [])), len(d.get("asks", []))
                        STATE["depth"][d["symbol"]] = [nb, na]
                        warn = "" if nb >= DEPTH and na >= DEPTH else f" WARNING: asked for {DEPTH}"
                        print(f"{stamp(now())} snapshot depth {d['symbol']}: {nb} bids, {na} asks{warn}", flush=True)
                    b.apply("bids", d.get("bids", []))
                    b.apply("asks", d.get("asks", []))
                    bb, aa = b.top(10)
                    b.ok = checksum(bb, aa, *PRECISION[d["symbol"]]) == d.get("checksum")
                    raws[d["symbol"]].write({"k": "msg", "type": m.get("type"), "bids": d.get("bids", []),
                                             "asks": d.get("asks", []), "checksum": d.get("checksum"),
                                             "ts": d.get("timestamp"), "ok": b.ok})
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


STATE = {"last_msg": 0.0, "depth": {}}
HEARTBEAT_S = 10.0


def write_heartbeat(path, extra=None):
    """Atomic small JSON file the watchdog reads: wall time, pid, age of the last websocket message, snapshot depth."""
    path = Path(path)
    tmp = path.with_suffix(".tmp")
    last = STATE["last_msg"]
    rec = {"t": stamp(now()), "epoch": time.time(), "pid": os.getpid(),
           "last_msg_age_s": round(time.time() - last, 1) if last else None, "depth": STATE["depth"], **(extra or {})}
    tmp.write_text(json.dumps(rec), encoding="utf-8")
    os.replace(tmp, path)


async def housekeeping(a, all_sinks, stop):
    """Every HEARTBEAT_S: heartbeat file, flush idle sinks, and honour a STOP file (graceful stop from the watchdog)."""
    stop_file = Path(a.out) / "STOP"
    while True:
        write_heartbeat(a.heartbeat)
        for s in all_sinks:
            if isinstance(s, Sink) and time.monotonic() - s.last_flush >= Sink.FLUSH_S:
                s.flush()
        if stop_file.exists():
            try:
                stop_file.unlink()
            except OSError:
                pass
            print(f"{stamp(now())} STOP file seen: stopping cleanly", flush=True)
            stop.set()
            return
        await asyncio.sleep(HEARTBEAT_S)


async def main_async(a):
    (Path(a.out) / "STOP").unlink(missing_ok=True)  # a STOP left from an earlier stop must not end this run
    load_precision(a.symbols)
    books = {s: Book() for s in a.symbols}
    sinks = {s: Sink(a.out, s) for s in a.symbols}
    # Raw messages are about 0.25 GB a day per symbol (2026-11-17). The watchdog creates NO_RAW in --out when the
    # disk runs low; the recorder then keeps the per-second snapshots and trades but stops writing raw messages.
    raws = {s: (NullSink() if (Path(a.out) / "NO_RAW").exists() else Sink(a.out, s + "-raw")) for s in a.symbols}
    tick = asyncio.create_task(ticker(books, sinks))
    stop = asyncio.Event()
    house = asyncio.create_task(housekeeping(a, [*sinks.values(), *raws.values()], stop))
    end = time.time() + a.seconds if a.seconds else None
    backoff = 1
    try:
        while (end is None or time.time() < end) and not stop.is_set():
            try:
                left = None if end is None else max(1, end - time.time())
                sess = asyncio.create_task(session(a.symbols, books, sinks, raws))
                waiter = asyncio.create_task(stop.wait())
                done, _ = await asyncio.wait({sess, waiter}, timeout=left, return_when=asyncio.FIRST_COMPLETED)
                waiter.cancel()
                if sess not in done:  # time limit or STOP file
                    sess.cancel()
                    await asyncio.gather(sess, return_exceptions=True)
                    break
                sess.result()
                why = "server closed"
            except Exception as e:  # network errors of any kind: log a gap and reconnect
                why = f"{type(e).__name__}: {e}"[:200]
            for s in a.symbols:
                books[s].bids, books[s].asks, books[s].ok = {}, {}, False
                sinks[s].write({"k": "gap", "why": why})
                raws[s].write({"k": "gap", "why": why})
            print(f"{stamp(now())} reconnect after: {why}", flush=True)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)
    finally:
        tick.cancel()
        house.cancel()
        for s in [*sinks.values(), *raws.values()]:
            s.close()
        write_heartbeat(a.heartbeat, {"stopped": True})
        print(f"{stamp(now())} files closed cleanly", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", nargs="+", default=["BTC/USD", "ETH/USD"])
    ap.add_argument("--out", default="C:/Work/Claude/qf-crypto-data/kraken")
    ap.add_argument("--seconds", type=float, default=0, help="stop after N seconds (0 = run until stopped)")
    ap.add_argument("--heartbeat", default=None, help="heartbeat file (default <out>/../heartbeat.json)")
    a = ap.parse_args()
    a.heartbeat = a.heartbeat or str(Path(a.out).parent / "heartbeat.json")
    print(f"{stamp(now())} recording {a.symbols} to {a.out}", flush=True)
    try:
        asyncio.run(main_async(a))  # Ctrl-C / Ctrl-Break also unwind through the finally that closes every file
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
