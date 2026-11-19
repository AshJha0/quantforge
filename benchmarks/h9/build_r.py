#!/usr/bin/env python3
"""Build H-9 workload R (low-latency-book.md, Workloads, amended 2026-11-19) from the recorder's hourly files.

  python -I build_r.py DATA_DIR SYMBOL START END OUT_PREFIX

DATA_DIR is qf-crypto-data/kraken (read only). START/END are ISO UTC instants; rows with START <= t < END are used.
Writes OUT_PREFIX.bin (QFH9S001, the harness format) and OUT_PREFIX.msgs.jsonl (the same stream as order-book.md
messages with `t`, trades left out, for micro.book.rebuild), and prints the SHA-256 of every input file and output.

Form B: the first book row is a snapshot; each later row becomes one update holding every new or changed level and
a zero-quantity level for every price that left the row (order-book.md "Differenced stream"). Each fill of a trade
row is one Trade message (one level: price, size), which changes nothing. A gap row inside the window is an error.
Prices are integer ticks at the pair's price decimals, quantities integer lots at 8 decimals (HR-20).
"""
import gzip
import hashlib
import json
import struct
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

PRICE_DECIMALS = {"BTC-USD": 1, "ETH-USD": 2}
QTY_DECIMALS = 8
SNAPSHOT, UPDATE, TRADE = 0, 1, 3
K_SNAPSHOT, K_UPDATE, K_TRADE = 0, 2, 4  # harness kind slots: snapshot, "modify" (form B update), trade


def ts(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def fixed(text):
    out = format(Decimal(text), "f")
    if Decimal(out) != Decimal(text):
        raise ValueError(text)
    return out


def to_int(text, decimals):
    v = Decimal(text).scaleb(decimals)
    if v != v.to_integral_value():
        raise ValueError(f"{text} has more than {decimals} decimals")
    return int(v)


def main(data_dir, symbol, start, end, prefix):
    start, end = ts(start), ts(end)
    pd = PRICE_DECIMALS[symbol]
    files, h = [], start.replace(minute=0, second=0, microsecond=0)
    while h < end:
        files += sorted((Path(data_dir) / symbol).glob(h.strftime("%Y%m%dT%H") + "*.jsonl.gz"))
        h += timedelta(hours=1)
    rows = []
    for f in files:
        print(f"input {symbol}/{f.name} sha256 {hashlib.sha256(f.read_bytes()).hexdigest()}")
        with gzip.open(f, "rt") as g:  # full read: a damaged member raises
            for line in g:
                d = json.loads(line)
                t = ts(d["t"])
                if start <= t < end:
                    if d["k"] == "gap":
                        raise SystemExit(f"gap row inside the window at {d['t']}")
                    rows.append((t, d))
    rows.sort(key=lambda r: r[0])
    msgs, levels, jl = [], [], []
    prev = None
    warm = None
    for t, d in rows:
        if warm is None and t >= start + timedelta(hours=1):
            warm = len(msgs)
        if d["k"] == "trade":
            for fill in d["d"]:
                msgs.append((TRADE, 1, 0, K_TRADE, len(levels)))
                levels.append((to_int(fill["price"], pd), to_int(fill["qty"], QTY_DECIMALS)))
            continue
        if d["k"] != "book":
            continue
        # The recorder writes some quantities in exponent form ("5.5E-7"); order-book.md inputs are plain decimal
        # strings (HR-12), so both fields are rewritten in plain form, value unchanged.
        for s in ("bids", "asks"):
            d[s] = [[fixed(p), fixed(q)] for p, q in d[s]]
        cur = {s: {p: q for p, q in d[s]} for s in ("bids", "asks")}
        if prev is None:
            if not d["bids"] or not d["asks"]:
                raise SystemExit("first row has an empty side")
            ch = {s: list(d[s]) for s in ("bids", "asks")}
            typ, kind = SNAPSHOT, K_SNAPSHOT
        else:
            ch = {}
            for s in ("bids", "asks"):
                a, b = prev[s], cur[s]
                lv = [[p, q] for p, q in b.items() if a.get(p) is None or Decimal(a[p]) != Decimal(q)]
                lv += [[p, "0"] for p in a if p not in b]
                ch[s] = lv
            typ, kind = UPDATE, K_UPDATE
        prev = cur
        first = len(levels)
        for s in ("bids", "asks"):
            levels += [(to_int(p, pd), to_int(q, QTY_DECIMALS)) for p, q in ch[s]]
        msgs.append((typ, len(ch["bids"]), len(ch["asks"]), kind, first))
        jl.append({"i": len(msgs) - 1, "t": d["t"], "type": "snapshot" if typ == SNAPSHOT else "update",
                   "bids": ch["bids"], "asks": ch["asks"]})
    with open(prefix + ".bin", "wb") as o:
        o.write(b"QFH9S001" + struct.pack("<QQ", len(msgs), len(levels)))
        for typ, nb, na, kind, first in msgs:
            o.write(struct.pack("<BBHHHII", typ, 0, nb, na, kind, 0, first))
        for px, q in levels:
            o.write(struct.pack("<qq", px, q))
    with open(prefix + ".msgs.jsonl", "w") as o:
        for m in jl:
            o.write(json.dumps(m, separators=(",", ":")) + "\n")
    print(f"{symbol}: {len(rows)} rows, {len(msgs)} messages ({len(jl)} book, {len(msgs) - len(jl)} trade fills), "
          f"{len(levels)} levels; warm-up (first hour) {warm} messages; "
          f"span {rows[0][0].isoformat()} .. {rows[-1][0].isoformat()}")
    for suffix in (".bin", ".msgs.jsonl"):
        p = Path(prefix + suffix)
        print(f"output {p.name} sha256 {hashlib.sha256(p.read_bytes()).hexdigest()}")


if __name__ == "__main__":
    main(*sys.argv[1:6])
