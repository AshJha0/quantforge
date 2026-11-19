#!/usr/bin/env python3
"""Python reference for the form A correctness of workload R2 (low-latency-targets.md (g), L6; order-book.md form A).

  python check_r2.py PREFIX [--chunk N] [--out FILE.json]

PREFIX is an OUT_PREFIX of build_r2.py (PREFIX.msgs.jsonl, PREFIX.rows.jsonl, PREFIX.meta.json). The check is
micro.book.rebuild itself (the L6 reference), at depth 100 with the pair's decimals:
  - after every book message, rebuild's CRC32 of its top 10 against the venue `checksum` (checksum_checked/failed);
  - every per-second recorder row is a rebuild checkpoint (rebuild's rule: compared before the first later message
    whose t is greater than the row's t), full 100 levels a side.
A failed checkpoint is "top 10" if the row's first 10 levels a side already differ from the book (a second rebuild
over the same messages with the rows cut to 10 levels finds these), else "below level 10".

The messages are replayed in chunks of N (default 200,000) to bound memory: chunk k > 0 starts with a snapshot equal
to rebuild's final book of chunk k-1 (checksum null, so it is not counted), and that snapshot's own message count
and crossed/locked count are taken off again. Each row goes to the chunk that holds the message before which rebuild
would compare it, so the comparison is the one a single rebuild over the whole stream makes.

Exit status: 0 = no failure of any kind; 1 = a checksum or top-10 checkpoint failure (the run fails); 2 = only
below-level-10 checkpoint failures (published; whether they fail the run is the targets (g) rule).
"""
import json
import sys
from decimal import Decimal
from pathlib import Path

from quantforge_core.order_book import rebuild

COUNTERS = ("messages", "snapshots", "updates", "level_changes", "deletes_of_absent_level", "truncated_levels",
            "checksum_checked", "checksum_failed", "checkpoint_checked", "checkpoint_failed", "crossed", "locked",
            "gaps", "resyncs")


def _cross_state(book):
    if not book["bids"] or not book["asks"]:
        return None
    bb, ba = Decimal(book["bids"][0][0]), Decimal(book["asks"][0][0])
    return "crossed" if bb > ba else "locked" if bb == ba else None


def run_chunk(msgs, rows, pd, qd, start_book, start_t, top10_only=False):
    """rebuild over one chunk; returns (stats with the synthetic snapshot taken off, final book)."""
    lead = []
    if start_book is not None:
        lead = [{"type": "snapshot", "t": start_t, "bids": start_book["bids"], "asks": start_book["asks"], "checksum": None}]
    cps = [{"t": r["t"], "bids": r["bids"][:10], "asks": r["asks"][:10]} if top10_only else r for r in rows]
    out = rebuild(lead + msgs, 100, pd, qd, checkpoints=cps)
    st = dict(out["stats"])
    if lead:
        st["messages"] -= 1
        st["snapshots"] -= 1
        cross = _cross_state(start_book)
        if cross:
            st[cross] -= 1
    return st, out["book"]


def check(prefix, chunk=200_000):
    meta = json.loads(Path(prefix + ".meta.json").read_text(encoding="utf-8"))
    pd, qd = meta["price_decimals"], meta["qty_decimals"]
    total = dict.fromkeys(COUNTERS, 0)
    total["checkpoint_failed_top10"] = 0
    rows_f = open(prefix + ".rows.jsonl", encoding="utf-8")
    pending = None  # next row not yet assigned

    def next_row():
        line = rows_f.readline()
        return json.loads(line) if line.strip() else None

    pending = next_row()
    book, book_t = None, None
    cur_msgs, cur_rows = [], []

    def finish(final):
        nonlocal book, book_t, cur_msgs, cur_rows
        if not cur_msgs and not cur_rows:
            return
        st, new_book = run_chunk(cur_msgs, cur_rows, pd, qd, book, book_t)
        for k in COUNTERS:
            total[k] += st[k]
        if st["checkpoint_failed"]:
            st10, _ = run_chunk(cur_msgs, cur_rows, pd, qd, book, book_t, top10_only=True)
            total["checkpoint_failed_top10"] += st10["checkpoint_failed"]
        book, book_t = new_book, (cur_msgs[-1]["t"] if cur_msgs else book_t)
        cur_msgs, cur_rows = [], []

    with open(prefix + ".msgs.jsonl", encoding="utf-8") as mf:
        for line in mf:
            m = json.loads(line)
            if len(cur_msgs) >= chunk:
                finish(False)
            t = m["t"]
            from_t = _instant(t)
            while pending is not None and _instant(pending["t"]) < from_t:
                cur_rows.append(pending)
                pending = next_row()
            cur_msgs.append({"type": m["type"], "t": t, "bids": m["bids"], "asks": m["asks"], "checksum": m["checksum"]})
    while pending is not None:
        cur_rows.append(pending)
        pending = next_row()
    finish(True)
    rows_f.close()
    res = {
        "symbol": meta["symbol"], "workload": "R2", "reference": "micro.book.rebuild (python/quantforge_core/order_book.py)",
        "book_messages": total["messages"], "checksum_checked": total["checksum_checked"],
        "checksum_failed": total["checksum_failed"], "checkpoint_checked": total["checkpoint_checked"],
        "checkpoint_failed": total["checkpoint_failed"], "checkpoint_failed_top10": total["checkpoint_failed_top10"],
        "checkpoint_failed_below10": total["checkpoint_failed"] - total["checkpoint_failed_top10"],
        "crossed": total["crossed"], "locked": total["locked"], "truncated_levels": total["truncated_levels"],
        "deletes_of_absent_level": total["deletes_of_absent_level"], "level_changes": total["level_changes"],
        "gaps": total["gaps"], "chunk": chunk,
    }
    return res


def _instant(text):
    from datetime import datetime

    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def main(argv):
    args, opts, k = [], {}, 0
    while k < len(argv):
        if argv[k] in ("--chunk", "--out"):
            opts[argv[k]] = argv[k + 1]
            k += 2
        else:
            args.append(argv[k])
            k += 1
    if len(args) != 1:
        print(__doc__)
        return 64
    res = check(args[0], int(opts.get("--chunk", 200_000)))
    text = json.dumps(res, sort_keys=True)
    print(text)
    if "--out" in opts:
        Path(opts["--out"]).write_text(text + "\n", encoding="utf-8")
    if res["checksum_failed"] or res["checkpoint_failed_top10"] or res["book_messages"] == 0:
        return 1
    return 2 if res["checkpoint_failed_below10"] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
