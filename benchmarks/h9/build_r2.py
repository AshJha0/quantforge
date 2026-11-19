#!/usr/bin/env python3
"""Build H-9 workload R2 (low-latency-book.md item 2a, ruling HR-130) and the form B input of the same window (item 2b).

  python -I build_r2.py DATA_DIR SYMBOL START END OUT_PREFIX [--tolerant]
  python -I build_r2.py window DATA_DIR [--after ISO] [--min-hours 6] [--max-hours 8] [--tolerant]
  python -I build_r2.py auto DATA_DIR OUT_DIR [--after ISO] [--min-hours 6] [--max-hours 8] [--tolerant]

DATA_DIR is qf-crypto-data/kraken (read only). START/END are ISO UTC instants; raw messages, trades and per-second rows
with START <= t < END are used. `window` applies the window rule of item 2a and prints START and END; `auto` does that
and then builds both symbols into OUT_DIR. --after defaults to 2026-11-19T11:41:24Z (raw recording switched on);
--min-hours/--max-hours default to the rule's 6 and 8 and are changed only to exercise the code on a short sample.
--until ISO stops the scan at that hour (files of later hours are not opened).
--tolerant reads damaged gzip files with tools/recorder/read_gz.py and skips undecodable lines: development on the
2026-11-17 sample only; such a build is marked "tolerant" and is never a workload input.

Outputs per symbol (OUT_PREFIX = OUT_DIR/R2_<SYMBOL> under `auto`):
  OUT_PREFIX.bin          QFH9S001 (the harness format): the venue's raw snapshot and update messages in file order,
                          one Trade per fill of the per-second trade rows, merged by receive time `t`. Book messages
                          carry the venue `checksum` with flag bit 4 (FLAG_VENUE_CHECKSUM), which `apply` ignores, so
                          the checksum is compared by the harness outside the timed region (low-latency-targets.md (g)).
  OUT_PREFIX.cps.bin      QFH9C001: per-second recorder rows as form A checkpoints. Each holds the range of bin
                          messages after which it may be compared: from "lo", the last book message with t < row t,
                          to "hi", the last with t <= row t (micro.book.rebuild's rule). Receive times are in
                          milliseconds and one websocket frame can carry many messages, so the order inside the
                          row's millisecond is unknown; a row passes if the book equals it after one message in
                          [lo, hi]. Both ends are reported (check_r2.py).
  OUT_PREFIX.msgs.jsonl   the book messages as order-book.md messages (t, type, bids, asks, checksum; "i" = bin index)
  OUT_PREFIX.rows.jsonl   the checkpoint rows (t, bids, asks), plain decimal strings, for check_r2.py
  OUT_PREFIX.meta.json    window, counts, warm-up (first hour), decimals, SHA-256 of every input and output
  L7_<SYMBOL>.*           the form B stream of the same window, built by build_r.py (imported, not copied)
`auto` also writes OUT_DIR/R2_inputs.sha256 (recorder files) and OUT_DIR/R2_replay.sha256 (built files) in sha256sum
format; the second is the file run_r2.sh verifies before any run.

Record layouts (little endian). Header "QFH9S001", u64 messages, u64 levels; message records "<BBHHHII" (type, flags,
n_bids, n_asks, kind slot, checksum, first level); levels "<qq" (price ticks, quantity lots), bids first. Header
"QFH9C001", u64 checkpoints, u64 levels; checkpoint records "<IHHII" (lo: bin message index, n_bids, n_asks, first
level, hi: bin message index); then levels "<qq", bids descending then asks ascending. Prices are integer ticks at the pair's price
decimals, quantities integer lots at 8 decimals (HR-20).
"""
import gzip
import hashlib
import json
import struct
import sys
from array import array
from collections import deque
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))  # `python -I` does not put the script's folder on sys.path
import build_r  # noqa: E402  (form B builder; reused, not duplicated)

PRICE_DECIMALS = build_r.PRICE_DECIMALS
QTY_DECIMALS = build_r.QTY_DECIMALS
SNAPSHOT, UPDATE, TRADE = build_r.SNAPSHOT, build_r.UPDATE, build_r.TRADE
K_SNAPSHOT, K_UPDATE, K_TRADE = build_r.K_SNAPSHOT, build_r.K_UPDATE, build_r.K_TRADE
FLAG_VENUE_CHECKSUM = 4  # not FLAG_CHECKSUM (1): the book must not check inside the timed apply
AFTER_DEFAULT = "2026-11-19T11:41:24Z"
SYMBOLS = ("BTC-USD", "ETH-USD")


def ts(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def iso(t):
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def hour_files(folder, start, end):
    """Hourly files of `folder` covering [start, end), in recording order (<hour>, <hour>-1, <hour>-2, ...)."""
    out, h = [], start.replace(minute=0, second=0, microsecond=0)
    while h < end:
        stem = h.strftime("%Y%m%dT%H")
        found = []
        for f in Path(folder).glob(stem + "*.jsonl.gz"):
            rest = f.name[len(stem) : -len(".jsonl.gz")]
            if rest == "":
                found.append((0, f))
            elif rest.startswith("-") and rest[1:].isdigit():
                found.append((int(rest[1:]), f))
        out += [f for _, f in sorted(found)]
        h += timedelta(hours=1)
    return out


class Reader:
    """Lines of the recorder's gzip files. Strict: a full gzip read, and a damaged member or line is an error."""

    def __init__(self, tolerant=False):
        self.tolerant = tolerant
        self.skipped = 0

    @staticmethod
    def _strict(path):
        with gzip.open(path, "rt", encoding="utf-8") as g:  # a full read; a damaged member raises
            yield from g

    def rows(self, path):
        if self.tolerant:
            sys.path.insert(0, str(HERE.parent.parent / "tools" / "recorder"))
            import read_gz

            lines, _ = read_gz.read_lines(path)
        else:
            lines = self._strict(path)
        for line in lines:
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except ValueError:
                if not self.tolerant:
                    raise SystemExit(f"{path}: undecodable line") from None
                self.skipped += 1


def fixed(text):
    return build_r.fixed(str(text))


def level_pairs(raw):
    """Raw recorder levels ({"price", "qty"} objects as Kraken sent them) as plain decimal string pairs."""
    out = []
    for lv in raw:
        p, q = (lv["price"], lv["qty"]) if isinstance(lv, dict) else lv
        out.append([fixed(p), fixed(q)])
    return out


# ---------------------------------------------------------------- window rule (item 2a)
def scan(data_dir, after, tolerant=False, until=None):
    """One full read of every hourly file at or after `after`'s hour, both symbols, raw and per-second.

    Returns gap times (every stream; a file that fails the full read counts as a gap at its hour), raw snapshot
    times per symbol, and the last row time of each stream."""
    rd = Reader(tolerant)
    gaps, snaps, last = [], {s: [] for s in SYMBOLS}, {}
    hour0 = after.replace(minute=0, second=0, microsecond=0)
    for s in SYMBOLS:
        for sub in (s + "-raw", s):
            folder = Path(data_dir) / sub
            stems = [f.name[:11] for f in folder.glob("*.jsonl.gz") if f.name[:11] >= hour0.strftime("%Y%m%dT%H")]
            files = []
            if stems:
                top = datetime.strptime(max(stems), "%Y%m%dT%H").replace(tzinfo=timezone.utc)
                files = hour_files(folder, hour0, min(top + timedelta(hours=1), until or top + timedelta(hours=1)))
            prev = None  # previous row of this stream: (t, k)
            for f in files:
                try:
                    for d in rd.rows(f):
                        t = ts(d["t"])
                        last[sub] = max(last.get(sub, t), t)
                        if d["k"] == "gap":
                            gaps.append((t, sub, d.get("why", "")))
                        elif sub.endswith("-raw") and d.get("type") == "snapshot":
                            snaps[s].append(t)
                            if prev is not None and prev[1] != "gap":
                                # A new connection with no gap row before it: the recorder was restarted (killed
                                # processes write no gap row). The old session ended at the previous row.
                                gaps.append((prev[0] + timedelta(microseconds=1), sub,
                                             "snapshot without a gap row (recorder restart)"))
                        prev = (t, d["k"])
                except (OSError, EOFError, ValueError) as e:
                    h = datetime.strptime(f.name[:11], "%Y%m%dT%H").replace(tzinfo=timezone.utc)
                    gaps.append((h, sub, f"failed full gzip read: {type(e).__name__}"))
    gaps.sort()
    return gaps, snaps, last, rd.skipped


def choose_window(data_dir, after, min_hours=6.0, max_hours=8.0, tolerant=False, until=None):
    """Item 2a: the first session (between gap rows of any stream) whose first raw snapshot, on or after `after`,
    then runs min_hours with no gap row in either symbol's raw or per-second files. END = START + max_hours, or the
    first gap row if that comes between min_hours and max_hours, or just after the last recorded row if the
    recording ends there. Returns (start, end, log)."""
    gaps, snaps, last, skipped = scan(data_dir, after, tolerant, until)
    log = {"gaps": [[iso(t), sub, why] for t, sub, why in gaps], "streams_last_t": {k: iso(v) for k, v in last.items()},
           "skipped_lines": skipped, "attempts": []}
    if len(last) < 2 * len(SYMBOLS):
        log["result"] = "a stream has no rows at or after --after"
        return None, None, log
    data_end = min(last.values()) + timedelta(milliseconds=1)
    starts = sorted(t for s in SYMBOLS for t in snaps[s] if t >= after)
    min_d, max_d = timedelta(hours=min_hours), timedelta(hours=max_hours)
    tried = set()
    for s0 in starts:
        prev_gap = max((g for g, _, _ in gaps if g <= s0), default=None)
        if prev_gap in tried:
            continue  # only the first snapshot of each session is a candidate
        tried.add(prev_gap)
        nxt = min((g for g, _, _ in gaps if g > s0), default=None)
        limit = min(nxt, data_end) if nxt is not None else data_end
        if limit - s0 < min_d:
            why = "gap row before hour %.4g" % min_hours if nxt is not None and nxt <= data_end else "recording ends first"
            log["attempts"].append({"start": iso(s0), "rejected": why, "limit": iso(limit)})
            continue
        end = min(s0 + max_d, limit)
        log["attempts"].append({"start": iso(s0), "end": iso(end), "hours": round((end - s0).total_seconds() / 3600, 4)})
        log["result"] = "window chosen"
        return s0, end, log
    log["result"] = "no session qualifies"
    return None, None, log


# ---------------------------------------------------------------- R2 builder
def build(data_dir, symbol, start, end, prefix, tolerant=False):
    start, end = (ts(start) if isinstance(start, str) else start), (ts(end) if isinstance(end, str) else end)
    pd = PRICE_DECIMALS[symbol]
    rd = Reader(tolerant)
    inputs = {}

    # Per-second file first: trades (fills) and the checkpoint rows; a gap row in the window is an error.
    trades, rows_t, row_lv, row_hdr = [], [], array("q"), []
    rows_path = prefix + ".rows.jsonl"
    with open(rows_path, "w", encoding="utf-8") as rows_out:
        for f in hour_files(Path(data_dir) / symbol, start, end):
            inputs[f"{symbol}/{f.name}"] = sha(f)
            for d in rd.rows(f):
                t = ts(d["t"])
                if not start <= t < end:
                    continue
                if d["k"] == "gap":
                    raise SystemExit(f"{symbol}: gap row inside the window at {d['t']}")
                if d["k"] == "trade":
                    for fill in d["d"]:
                        trades.append((t, build_r.to_int(str(fill["price"]), pd), build_r.to_int(str(fill["qty"]), QTY_DECIMALS)))
                elif d["k"] == "book":
                    b = [[fixed(p), fixed(q)] for p, q in d["bids"]]
                    a = [[fixed(p), fixed(q)] for p, q in d["asks"]]
                    rows_t.append(t)
                    row_hdr.append((len(b), len(a), len(row_lv) // 2))
                    for p, q in b + a:
                        row_lv.append(build_r.to_int(p, pd))
                        row_lv.append(build_r.to_int(q, QTY_DECIMALS))
                    rows_out.write(json.dumps({"t": d["t"], "bids": b, "asks": a}, separators=(",", ":")) + "\n")

    msgs = bytearray()
    levels = array("q")
    nmsg = 0
    after = [None] * len(rows_t)
    lo_of = [None] * len(rows_t)
    hist = deque(maxlen=200_000)  # (t, bin index) of the latest book messages
    cp_next = 0
    last_book = None
    first_t = None
    warm = None
    counts = {"snapshots": 0, "updates": 0, "trade_fills": 0, "levels_in_updates": 0, "venue_ok_false": 0,
              "t_not_increasing": 0, "rows_tied_with_a_message_ms": 0}
    prev_t = None
    ti = 0
    msg_ts = set()

    def put(typ, flags, nb, na, kind, cs, lv):
        nonlocal nmsg
        msgs.extend(struct.pack("<BBHHHII", typ, flags, nb, na, kind, cs, len(levels) // 2))
        for px, q in lv:
            levels.append(px)
            levels.append(q)
        nmsg += 1

    def mark_warm(t):
        nonlocal warm
        if warm is None and t >= start + timedelta(hours=1):
            warm = nmsg

    def flush_trades(upto):
        nonlocal ti
        while ti < len(trades) and (upto is None or trades[ti][0] < upto):
            t, px, q = trades[ti]
            if first_t is not None:  # fills before the symbol's first snapshot stay out, as nothing is live yet
                mark_warm(t)
                put(TRADE, 0, 1, 0, K_TRADE, 0, [(px, q)])
                counts["trade_fills"] += 1
            ti += 1

    with open(prefix + ".msgs.jsonl", "w", encoding="utf-8") as jl:
        for f in hour_files(Path(data_dir) / (symbol + "-raw"), start, end):
            inputs[f"{symbol}-raw/{f.name}"] = sha(f)
            for d in rd.rows(f):
                t = ts(d["t"])
                if not start <= t < end:
                    continue
                if d["k"] == "gap":
                    raise SystemExit(f"{symbol}: raw gap row inside the window at {d['t']}")
                if d["k"] != "msg":
                    continue
                typ = d.get("type")
                if first_t is None:
                    if typ != "snapshot":
                        raise SystemExit(f"{symbol}: the window's first raw message is not a snapshot ({d['t']})")
                    first_t = t
                    while ti < len(trades) and trades[ti][0] < t:
                        ti += 1  # fills before the first snapshot are dropped (they change nothing)
                flush_trades(t)
                if prev_t is not None and t < prev_t:
                    counts["t_not_increasing"] += 1
                prev_t = t
                # micro.book.rebuild's checkpoint rule: before a book message with time t, compare every row with
                # time < t against the book as it stands (after the previous book message).
                # The candidates for a row run from "lo" (last book message with t < row t: fixed before the first
                # message with t >= row t) to "hi" (micro.book.rebuild's rule: fixed before the first message with
                # t > row t); messages between them share the row's millisecond (check_r2.py explains why).
                while cp_next < len(rows_t):
                    if lo_of[cp_next] is None and t >= rows_t[cp_next]:
                        lo_of[cp_next] = _last(hist, rows_t[cp_next], True)
                    if t > rows_t[cp_next]:
                        after[cp_next] = _last(hist, rows_t[cp_next], False)
                        cp_next += 1
                    else:
                        break
                b, a = level_pairs(d.get("bids", [])), level_pairs(d.get("asks", []))
                cs = d.get("checksum")
                if typ not in ("snapshot", "update") or cs is None or not 0 <= int(cs) < 2**32:
                    raise SystemExit(f"{symbol}: malformed raw message at {d['t']}")
                if len(b) > 65535 or len(a) > 65535:
                    raise SystemExit(f"{symbol}: message wider than u16 at {d['t']}")
                if d.get("ok") is False:
                    counts["venue_ok_false"] += 1
                mark_warm(t)
                last_book = nmsg
                hist.append((t, nmsg))
                msg_ts.add(d["t"])
                jl.write(json.dumps({"i": nmsg, "t": d["t"], "type": typ, "bids": b, "asks": a, "checksum": int(cs)},
                                    separators=(",", ":")) + "\n")
                lv = [(build_r.to_int(p, pd), build_r.to_int(q, QTY_DECIMALS)) for p, q in b + a]
                if typ == "snapshot":
                    counts["snapshots"] += 1
                    put(SNAPSHOT, FLAG_VENUE_CHECKSUM, len(b), len(a), K_SNAPSHOT, int(cs), lv)
                else:
                    counts["updates"] += 1
                    counts["levels_in_updates"] += len(lv)
                    put(UPDATE, FLAG_VENUE_CHECKSUM, len(b), len(a), K_UPDATE, int(cs), lv)
        flush_trades(None)
    if first_t is None:
        raise SystemExit(f"{symbol}: no raw message in the window")
    while cp_next < len(rows_t):
        after[cp_next] = _last(hist, rows_t[cp_next], False)
        if lo_of[cp_next] is None:
            lo_of[cp_next] = _last(hist, rows_t[cp_next], True)
        cp_next += 1

    # Checkpoints: rows at or after the symbol's first raw message (none can be earlier inside one session).
    cps = [(k, after[k]) for k in range(len(rows_t)) if rows_t[k] >= first_t and after[k] is not None]
    counts["rows_not_after_previous_row"] = sum(1 for k in range(1, len(rows_t)) if rows_t[k] <= rows_t[k - 1])
    counts["rows_tied_with_a_message_ms"] = sum(1 for k, _ in cps if iso(rows_t[k])[:23] + "Z" in msg_ts)
    with open(prefix + ".bin", "wb") as o:
        o.write(b"QFH9S001" + struct.pack("<QQ", nmsg, len(levels) // 2))
        o.write(msgs)
        o.write(levels.tobytes() if sys.byteorder == "little" else _swapped(levels))
    with open(prefix + ".cps.bin", "wb") as o:
        cp_lv = array("q")
        recs = bytearray()
        for k, at in cps:
            nb, na, first = row_hdr[k]
            lo = at if lo_of[k] is None else lo_of[k]  # None: the row shares the first message's millisecond
            recs.extend(struct.pack("<IHHII", lo, nb, na, len(cp_lv) // 2, at))
            cp_lv.extend(row_lv[2 * first : 2 * (first + nb + na)])
        o.write(b"QFH9C001" + struct.pack("<QQ", len(cps), len(cp_lv) // 2))
        o.write(recs)
        o.write(cp_lv.tobytes() if sys.byteorder == "little" else _swapped(cp_lv))
    if len(cps) != len(rows_t):  # keep rows.jsonl equal to the checkpoints the harnesses see
        kept = {k for k, _ in cps}
        lines = Path(rows_path).read_text(encoding="utf-8").splitlines()
        Path(rows_path).write_text("".join(lines[k] + "\n" for k in range(len(lines)) if k in kept), encoding="utf-8")

    # Form B of the same window (item 2b), by build_r.py itself.
    out_dir = Path(prefix).parent
    b_prefix = str(out_dir / f"L7_{symbol}")
    if tolerant:  # development only: let build_r.py read the damaged sample through read_gz.py too
        build_r.gzip = _TolerantGzip(rd)
    import contextlib
    import io
    import re

    printed = io.StringIO()
    try:
        with contextlib.redirect_stdout(printed):
            build_r.main(data_dir, symbol, iso(start), iso(end), b_prefix)
    finally:
        build_r.gzip = gzip
    print(printed.getvalue(), end="")
    found = re.search(r"(\d+) messages \((\d+) book, (\d+) trade fills\), (\d+) levels; warm-up \(first hour\) (\d+|None)",
                      printed.getvalue())
    if found is None:
        raise SystemExit("could not read build_r.py's summary line")
    l7 = {"messages": int(found[1]), "book_messages": int(found[2]), "trade_fills": int(found[3]),
          "levels": int(found[4]), "warmup_messages": int(found[1]) if found[5] == "None" else int(found[5])}

    outputs = {}
    for p in (prefix + ".bin", prefix + ".cps.bin", prefix + ".msgs.jsonl", rows_path,
              b_prefix + ".bin", b_prefix + ".msgs.jsonl"):
        outputs[Path(p).name] = sha(p)
    meta = {
        "workload": "R2", "symbol": symbol, "window_start": iso(start), "window_end": iso(end),
        "first_raw_message": iso(first_t), "price_decimals": pd, "qty_decimals": QTY_DECIMALS, "depth": 100,
        "messages": nmsg, "levels": len(levels) // 2, "checkpoints": len(cps), "warmup_messages": warm if warm is not None else nmsg,
        **counts, "tolerant": tolerant, "skipped_lines": rd.skipped, "inputs_sha256": inputs, "outputs_sha256": outputs,
        "form_b_prefix": Path(b_prefix).name, "form_b": l7,
    }
    Path(prefix + ".meta.json").write_text(json.dumps(meta, indent=1) + "\n", encoding="utf-8")
    print(f"{symbol}: R2 {nmsg} messages ({counts['snapshots']} snapshots, {counts['updates']} updates, "
          f"{counts['trade_fills']} trade fills), {len(levels) // 2} levels; {len(cps)} checkpoints; "
          f"warm-up (first hour) {meta['warmup_messages']} messages; ties {counts['rows_tied_with_a_message_ms']}")
    for k, v in inputs.items():
        print(f"input {k} sha256 {v}")
    for k, v in outputs.items():
        print(f"output {k} sha256 {v}")
    if tolerant:
        print("WARNING: tolerant build (damaged input read past); development only, never a workload input")
    return meta


class _TolerantGzip:
    """Stands in for the gzip module inside build_r.py under --tolerant: open() yields the recoverable lines."""

    def __init__(self, reader):
        self.reader = reader

    def open(self, path, mode="rt"):
        import io

        return io.StringIO("".join(json.dumps(d, separators=(",", ":")) + "\n" for d in self.reader.rows(path)))


def _last(hist, r, strict):
    """Bin index of the latest book message seen with t < r (strict) or t <= r, None if none. Usually the message
    just seen; a row whose time was already passed (a repeated or late row) looks back in `hist`."""
    for t, k in reversed(hist):
        if (t < r) if strict else (t <= r):
            return k
    if len(hist) == hist.maxlen:
        raise SystemExit("a row lies further back than the message history kept")
    return None


def _swapped(a):
    b = array("q", a)
    b.byteswap()
    return b.tobytes()


def _opts(argv, names):
    out, rest, k = {}, [], 0
    while k < len(argv):
        if argv[k] in names:
            out[argv[k]] = argv[k + 1]
            k += 2
        elif argv[k] == "--tolerant":
            out["--tolerant"] = True
            k += 1
        else:
            rest.append(argv[k])
            k += 1
    return out, rest


def main(argv):
    o, rest = _opts(argv, ("--after", "--min-hours", "--max-hours", "--until"))
    until = ts(o["--until"]) if "--until" in o else None
    tolerant = bool(o.get("--tolerant"))
    after = ts(o.get("--after", AFTER_DEFAULT))
    lo, hi = float(o.get("--min-hours", 6)), float(o.get("--max-hours", 8))
    if rest and rest[0] in ("window", "auto"):
        start, end, log = choose_window(rest[1], after, lo, hi, tolerant, until)
        print(json.dumps(log, indent=1))
        if start is None:
            print(f"NO WINDOW: {log['result']}")
            return 3
        print(f"START {iso(start)} END {iso(end)}")
        if rest[0] == "window":
            return 0
        out = Path(rest[2])
        out.mkdir(parents=True, exist_ok=True)
        (out / "R2_window.json").write_text(json.dumps({"start": iso(start), "end": iso(end), "after": iso(after),
                                                        "min_hours": lo, "max_hours": hi, **log}, indent=1) + "\n")
        ins, outs = [], []
        for s in SYMBOLS:
            m = build(rest[1], s, start, end, str(out / f"R2_{s}"), tolerant)
            ins += [f"{v}  {k}\n" for k, v in m["inputs_sha256"].items()]
            outs += [f"{v}  {k}\n" for k, v in m["outputs_sha256"].items()]
            outs.append(f"{sha(out / f'R2_{s}.meta.json')}  R2_{s}.meta.json\n")
        (out / "R2_inputs.sha256").write_text("".join(ins), encoding="utf-8")
        (out / "R2_replay.sha256").write_text("".join(outs), encoding="utf-8")
        print(f"wrote {out / 'R2_inputs.sha256'} and {out / 'R2_replay.sha256'}")
        return 0
    if len(rest) != 5:
        print(__doc__)
        return 2
    build(*rest, tolerant=tolerant)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
