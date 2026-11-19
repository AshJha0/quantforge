#!/usr/bin/env python3
"""Check a harness's fast book against micro.book.rebuild at every non-trade message of workload R.

  python check_r.py PREFIX DUMP PRICE_DECIMALS

PREFIX.msgs.jsonl comes from build_r.py; DUMP is the harness's QF_H9_DUMP file (fast book top(100) after every
non-trade message). Every dump line becomes a rebuild checkpoint placed just after its message, so rebuild compares
its own book after that message with the fast book's top(100), level by level, exact decimals. Also checks that the
dump has a line for every book message and that the last line equals rebuild's final book in full.
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from quantforge_core.order_book import rebuild


def fmt(v, d):
    return format(Decimal(v).scaleb(-d), "f")


def main(prefix, dump, pd):
    pd = int(pd)
    msgs = [json.loads(line) for line in open(prefix + ".msgs.jsonl")]
    books = {}
    for line in open(dump):
        f = line.split()
        i, out, k = int(f[0]), {}, 1
        while k < len(f):
            side, n = f[k], int(f[k + 1])
            vals = f[k + 2 : k + 2 + 2 * n]
            out["bids" if side == "b" else "asks"] = [[fmt(vals[2 * j], pd), fmt(vals[2 * j + 1], 8)] for j in range(n)]
            k += 2 + 2 * n
        books[i] = out
    assert sorted(books) == [m["i"] for m in msgs], "dump lines do not match the book messages"
    # Recorded row times can repeat (two rows in the same millisecond), so rebuild gets synthetic, strictly
    # increasing times (one second per book message); they only order the checkpoints between messages.
    base = datetime(2000, 1, 1, tzinfo=timezone.utc)
    times = [base + timedelta(seconds=k) for k in range(len(msgs))]
    cps = [{"t": (t + timedelta(microseconds=1)).isoformat(), **books[m["i"]]} for m, t in zip(msgs, times)]
    rows = [{"type": m["type"], "t": t.isoformat(), "bids": m["bids"], "asks": m["asks"]} for m, t in zip(msgs, times)]
    r = rebuild(rows, 100, pd, 8, checkpoints=cps)
    st = r["stats"]
    last = books[msgs[-1]["i"]]
    final_eq = all(
        len(r["book"][s]) == len(last[s])
        and all(Decimal(a[0]) == Decimal(b[0]) and Decimal(a[1]) == Decimal(b[1]) for a, b in zip(r["book"][s], last[s]))
        for s in ("bids", "asks")
    )
    short = sum(1 for b in books.values() if len(b["bids"]) != 100 or len(b["asks"]) != 100)
    print(json.dumps({"book_messages": len(msgs), "checkpoint_checked": st["checkpoint_checked"],
                      "checkpoint_failed": st["checkpoint_failed"], "final_book_equal": final_eq,
                      "checkpoints_not_100_a_side": short, "crossed": st["crossed"], "locked": st["locked"],
                      "deletes_of_absent_level": st["deletes_of_absent_level"]}))
    ok = st["checkpoint_failed"] == 0 and st["checkpoint_checked"] == len(msgs) and final_eq
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:4]))
