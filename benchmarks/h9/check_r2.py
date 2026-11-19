#!/usr/bin/env python3
"""Python reference for the form A correctness of workload R2 (low-latency-targets.md (g), L6; order-book.md form A).

  python check_r2.py PREFIX [--chunk N] [--jobs J] [--out FILE.json]

PREFIX is an OUT_PREFIX of build_r2.py (PREFIX.msgs.jsonl, PREFIX.rows.jsonl, PREFIX.meta.json). The engine is
micro.book.rebuild itself (the L6 reference), at depth 100 with the pair's decimals:
  - after every book message, rebuild's CRC32 of its top 10 against the venue `checksum` (checksum_checked/failed);
  - every per-second recorder row against the book "as it stood at the last raw message received before the row's
    t". Receive times are stamped to the millisecond, and many messages can share the row's millisecond (one
    websocket frame), so the order inside that millisecond is not recorded. The candidates are therefore the book
    after the last message with t < row t ("lo", the strict reading) and after each later message with t equal to
    the row's t, up to "hi" (micro.book.rebuild's own checkpoint rule, ties before the row). A row passes if the
    book equals it, full 100 levels a side, at one candidate. The counts of rows matched at lo, matched at hi and
    matched only inside the tie are published, and the count that would fail under the strict "before t" reading
    (checkpoint_failed_strict_reading). Ruling HR-132 (specifications/stage-h-rulings-audit.md) fixes this reading.
A failed row is "top 10" if no candidate matches even the row's first 10 levels a side, else "below level 10".

How rebuild is driven: messages get synthetic, strictly increasing times (one second apart; real times are used only
to place the candidates), and each candidate is a rebuild checkpoint half a second after its message, so rebuild
compares it after exactly that message; a CHECKPOINT_FAIL event's index names the candidate. Two candidates at one
message (two rows with no message between them) go to separate passes. The stream is replayed in chunks of N
(default 100,000) to bound memory; a chunk is split only between messages with different times, and chunk k > 0
starts with a snapshot of the book after chunk k-1 (checksum null; its own counts are taken off), so a candidate at
the last message of chunk k-1 is that snapshot. That starting book comes from a plain pre-pass (dict per side), so
the chunks can run in J worker processes; rebuild's own final book of chunk k-1 must equal it (chunk_start_mismatches,
which fails the check), and a wrong start would also fail the venue checksums.

Exit status: 0 = no failure of any kind; 1 = a checksum, top-10 or chunk-start failure (the run fails); 2 = only
below-level-10 failures (published; whether they fail the run is the targets (g) rule, for the coordinator).
"""
import json
import sys
from collections import Counter, deque
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from quantforge_core.order_book import rebuild

BASE = datetime(2000, 1, 1, tzinfo=timezone.utc)
BOOK_COUNTERS = ("messages", "updates", "snapshots", "level_changes", "deletes_of_absent_level", "truncated_levels",
                 "checksum_checked", "checksum_failed", "crossed", "locked", "gaps")


def _instant(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def _syn(k, half=False):
    return (BASE + timedelta(seconds=k, milliseconds=500 if half else 0)).isoformat()


def _cross_state(book):
    if not book["bids"] or not book["asks"]:
        return None
    bb, ba = Decimal(book["bids"][0][0]), Decimal(book["asks"][0][0])
    return "crossed" if bb > ba else "locked" if bb == ba else None


class Chunk:
    """Book messages of one chunk plus the rows whose candidates it holds."""

    def __init__(self, g0, lead_book):
        self.g0, self.lead, self.msgs, self.rows = g0, lead_book, [], []

    def local(self, g):
        p = g - self.g0 + (1 if self.lead is not None else 0)
        if p < 0:
            raise AssertionError("candidate before the chunk")
        return p

    def stream(self):
        out = []
        if self.lead is not None:
            out.append({"type": "snapshot", "t": _syn(0), "bids": self.lead["bids"], "asks": self.lead["asks"], "checksum": None})
        off = len(out)
        for k, m in enumerate(self.msgs):
            out.append({"type": m["type"], "t": _syn(k + off), "bids": m["bids"], "asks": m["asks"], "checksum": m["checksum"]})
        return out


def evaluate(ch, stream, pd, qd, specs, on_first=None):
    """specs: list of (j, bids, asks, lo, hi). Returns {j: local positions where the book equals (bids, asks)}.

    One rebuild pass per multiplicity rank of a position (two candidates at one message never share a pass)."""
    rank = Counter()
    passes = {}
    for j, bids, asks, lo, hi in specs:
        for g in range(lo, hi + 1):
            p = ch.local(g)
            passes.setdefault(rank[p], []).append((j, p, bids, asks))
            rank[p] += 1
    if on_first is not None:
        passes.setdefault(0, [])
    ok = {j: set() for j, *_ in specs}
    for k in sorted(passes):
        cl = sorted(passes[k], key=lambda c: c[1])
        cps = [{"t": _syn(p, True), "bids": b, "asks": a} for _, p, b, a in cl]
        out = rebuild(stream, 100, pd, qd, checkpoints=cps)
        if out.get("events_omitted"):
            raise SystemExit("rebuild event cap reached: use a smaller --chunk")
        failed = {e["i"] for e in out["events"] if e["kind"] == "CHECKPOINT_FAIL"}
        for j, p, _, _ in cl:
            if p not in failed:
                ok[j].add(p)
        if k == 0 and on_first is not None:
            on_first(out)
    return ok


def run_chunk(ch, pd, qd, total, rows_out):
    """rebuild over one chunk; adds its counts to `total`, failed rows to `rows_out`; returns rebuild's final book."""
    stream = ch.stream()
    final = {}

    def first(out):  # pass 0 runs over every message: the checksum and book counts come from it
        st = dict(out["stats"])
        if ch.lead is not None:
            st["messages"] -= 1
            st["snapshots"] -= 1
            cross = _cross_state(ch.lead)
            if cross:
                st[cross] -= 1
        for key in BOOK_COUNTERS:
            total[key] += st[key]
        final["book"] = out["book"]

    specs = [(j, row["bids"], row["asks"], lo, hi) for j, (row, lo, hi) in enumerate(ch.rows)]
    full = evaluate(ch, stream, pd, qd, specs, first)
    bad = [s for s in specs if not full[s[0]]]
    top = evaluate(ch, stream, pd, qd, [(j, b[:10], a[:10], lo, hi) for j, b, a, lo, hi in bad]) if bad else {}
    top10_ok = {j for j, pos in top.items() if pos}
    for j, (row, lo, hi) in enumerate(ch.rows):
        total["checkpoint_checked"] += 1
        if full[j]:
            total["matched_at_lo"] += ch.local(lo) in full[j]
            total["matched_at_hi"] += ch.local(hi) in full[j]
            total["matched_only_inside_tie"] += ch.local(lo) not in full[j] and ch.local(hi) not in full[j]
        elif j in top10_ok:
            total["checkpoint_failed_below10"] += 1
            rows_out.append({"t": row["t"], "kind": "below10"})
        else:
            total["checkpoint_failed_top10"] += 1
            rows_out.append({"t": row["t"], "kind": "top10"})
        total["rows_with_tie"] += hi > lo
    return final["book"]


def _work(task):
    """One chunk in a worker process: read its message lines and run rebuild over it."""
    prefix, off0, off1, g0, lead, rows, pd, qd = task
    ch = Chunk(g0, lead)
    with open(prefix + ".msgs.jsonl", "rb") as f:
        f.seek(off0)
        for line in f.read(off1 - off0).decode("utf-8").splitlines():
            if line.strip():
                m = json.loads(line)
                ch.msgs.append({"type": m["type"], "t": m["t"], "bids": m["bids"], "asks": m["asks"], "checksum": m["checksum"]})
    ch.rows = rows
    total, failures = Counter(), []
    final = run_chunk(ch, pd, qd, total, failures)
    return total, failures, final


class _PrePass:
    """A plain book (dict per side, truncation to 100 after every message) that only supplies the snapshot a chunk
    starts from. It is not the reference: rebuild of chunk k-1 must end on exactly the book this gives for chunk k
    (checked), and a wrong start would fail the venue checksums of the chunk."""

    def __init__(self):
        self.side = {"bids": {}, "asks": {}}

    def apply(self, m):
        if m["type"] == "snapshot":
            self.side = {"bids": {}, "asks": {}}
        for s, rev in (("bids", True), ("asks", False)):
            d = self.side[s]
            for p, q in m[s]:
                if Decimal(q) == 0:
                    d.pop(Decimal(p), None)
                else:
                    d[Decimal(p)] = (p, q)
            if len(d) > 100:
                for k in sorted(d, reverse=rev)[100:]:
                    del d[k]

    def book(self):
        return {s: [list(self.side[s][k]) for k in sorted(self.side[s], reverse=(s == "bids"))] for s in ("bids", "asks")}


def _same_book(x, y):
    return all(len(x[s]) == len(y[s]) and all(Decimal(a[0]) == Decimal(b[0]) and Decimal(a[1]) == Decimal(b[1])
                                              for a, b in zip(x[s], y[s])) for s in ("bids", "asks"))


def _last(hist, r, strict, g):
    """Global index of the latest message seen with t < r (strict) or t <= r; -1 if none. In the usual case that is
    the message just seen; a row whose time was already passed (a repeated or late row) looks back in `hist`."""
    for t, k in reversed(hist):
        if (t < r) if strict else (t <= r):
            return k
    if len(hist) == hist.maxlen:
        raise SystemExit("a row lies further back than the message history kept")
    return -1


def tasks(prefix, chunk, pd, qd):
    """Chunk descriptors in stream order: (prefix, byte range, first global index, lead snapshot, rows, decimals).

    Rows get their candidate range [lo, hi] (global book-message indices) as rebuild walks the messages: lo is fixed
    before the first message with t >= row t, hi before the first message with t > row t."""
    rows_f = open(prefix + ".rows.jsonl", encoding="utf-8")

    def next_row():
        line = rows_f.readline()
        if not line.strip():
            return None
        r = json.loads(line)
        return [r, _instant(r["t"])]

    pre = _PrePass()
    hist = deque(maxlen=200_000)  # (t, global index) of the latest messages
    pending, lo_of = next_row(), None
    g0, lead, rows, n = 0, None, [], 0
    g, prev_t, off0, off = -1, None, 0, 0
    with open(prefix + ".msgs.jsonl", "rb") as mf:
        for raw in mf:
            m = json.loads(raw)
            t = _instant(m["t"])
            while pending is not None:
                if lo_of is None and not pending[1] > t:
                    lo_of = _last(hist, pending[1], True, g)
                if t > pending[1]:
                    if lo_of is None:
                        lo_of = _last(hist, pending[1], True, g)
                    hi = _last(hist, pending[1], False, g)
                    if hi >= 0:
                        rows.append((pending[0], max(lo_of, 0), hi))
                    pending, lo_of = next_row(), None
                else:
                    break
            if n >= chunk and t != prev_t and lo_of is None:
                yield (prefix, off0, off, g0, lead, rows, pd, qd)
                g0, lead, rows, n, off0 = g + 1, pre.book(), [], 0, off
            pre.apply(m)
            n += 1
            g += 1
            prev_t = t
            hist.append((t, g))
            off += len(raw)
    while pending is not None:  # rows after the last message: compared with the final book
        lo = _last(hist, pending[1], True, g) if lo_of is None else lo_of
        rows.append((pending[0], max(lo, 0), _last(hist, pending[1], False, g)))
        pending, lo_of = next_row(), None
    rows_f.close()
    yield (prefix, off0, off, g0, lead, rows, pd, qd)


def check(prefix, chunk=100_000, jobs=1):
    meta = json.loads(Path(prefix + ".meta.json").read_text(encoding="utf-8"))
    pd, qd = meta["price_decimals"], meta["qty_decimals"]
    total, failures, finals, leads = Counter(), [], [], []

    def gen():
        for task in tasks(prefix, chunk, pd, qd):
            leads.append(task[4])
            yield task

    if jobs > 1:
        import multiprocessing

        with multiprocessing.Pool(jobs) as pool:
            results = list(pool.imap(_work, gen()))
    else:
        results = [_work(task) for task in gen()]
    for t, f, final in results:
        total.update(t)
        failures.extend(f)
        finals.append(final)
    lead_mismatch = sum(1 for k in range(1, len(leads)) if not _same_book(finals[k - 1], leads[k]))
    return {
        "symbol": meta["symbol"], "workload": "R2", "reference": "micro.book.rebuild (python/quantforge_core/order_book.py)",
        "book_messages": total["messages"], "checksum_checked": total["checksum_checked"],
        "checksum_failed": total["checksum_failed"], "checkpoint_checked": total["checkpoint_checked"],
        "checkpoint_failed_top10": total["checkpoint_failed_top10"],
        "checkpoint_failed_below10": total["checkpoint_failed_below10"],
        "checkpoint_matched_at_lo": total["matched_at_lo"], "checkpoint_matched_at_hi": total["matched_at_hi"],
        "checkpoint_matched_only_inside_tie": total["matched_only_inside_tie"], "checkpoint_rows_with_tie": total["rows_with_tie"],
        "checkpoint_failed_strict_reading": total["checkpoint_checked"] - total["matched_at_lo"],
        "crossed": total["crossed"], "locked": total["locked"], "truncated_levels": total["truncated_levels"],
        "deletes_of_absent_level": total["deletes_of_absent_level"], "level_changes": total["level_changes"],
        "gaps": total["gaps"], "chunk": chunk, "chunks": len(leads), "chunk_start_mismatches": lead_mismatch,
        "failed_rows_first_20": failures[:20],
    }


def main(argv):
    args, opts, k = [], {}, 0
    while k < len(argv):
        if argv[k] in ("--chunk", "--out", "--jobs"):
            opts[argv[k]] = argv[k + 1]
            k += 2
        else:
            args.append(argv[k])
            k += 1
    if len(args) != 1:
        print(__doc__)
        return 64
    res = check(args[0], int(opts.get("--chunk", 100_000)), int(opts.get("--jobs", 1)))
    text = json.dumps(res, sort_keys=True)
    print(text)
    if "--out" in opts:
        Path(opts["--out"]).write_text(text + "\n", encoding="utf-8")
    bad = res["checksum_failed"] or res["checkpoint_failed_top10"] or res["chunk_start_mismatches"]
    if bad or res["book_messages"] == 0 or res["checkpoint_checked"] == 0:
        return 1
    return 2 if res["checkpoint_failed_below10"] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
