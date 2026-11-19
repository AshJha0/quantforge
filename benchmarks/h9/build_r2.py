#!/usr/bin/env python3
"""Build H-9 workload R2 (low-latency-book.md item 2a, ruling HR-130) and the form B input of the same window (item 2b).

  python -I build_r2.py window DATA_DIR
  python -I build_r2.py auto DATA_DIR OUT_DIR
  python -I build_r2.py DATA_DIR SYMBOL START END OUT_PREFIX
  sample only: add --sample-only, then any of --after ISO, --until ISO, --min-hours H, --max-hours H, --tolerant

DATA_DIR is qf-crypto-data/kraken (read only). START/END are ISO UTC instants; raw messages, trades and per-second rows
with START <= t < END are used.

Window rule (ruling HR-134, owner decision 2026-11-19, amending item 2a and HR-133): the R2 window is the FIRST
recorder session, on any day from 2026-11-19 11:41:24 UTC on, that runs 6 hours from its first raw snapshot with no
gap row or restart in either symbol's raw or per-second files (HR-132: a raw snapshot that does not follow a gap row
ends the session too), taken as exactly those 6 hours. Sessions are examined in time order and the first that
qualifies is used whatever its content; a session may cross midnight; a session cut by a shutdown before hour 6 does
not qualify. `window` prints every session it examined (start, end, length, why it was rejected) and the window or
"none yet"; `auto` does that and then builds both symbols into OUT_DIR. The explicit START END form is refused unless
START and END are exactly the window `window` finds.

--sample-only is the one switch that lets the rule be bypassed, for development on a short sample: --after (default
2026-11-19T11:41:24Z), --until (stop the scan at that hour), --min-hours/--max-hours (session length needed and window
length, both 6 by rule), --tolerant (read damaged gzip files with tools/recorder/read_gz.py, skipping undecodable
lines), and an explicit START END that is not the window. Every such build is marked "sample_only": true (and
"tolerant" when given) in its meta file, and run_r2.sh refuses it outside SMOKE=1: it is never a workload input.

If the newest hour file of a stream has no gzip end marker (the recorder still has it open), it is not counted as a
gap; a window that reaches into such a file is reported as complete, and `auto` refuses to build until the recorder
has been stopped cleanly (its STOP file closes every file). benchmarks/h9/r2_status.py is the read-only check to run
while recording.

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
import zlib
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

    Returns gap times (every stream; a file that fails the full read counts as a gap at its hour, except the newest
    file of a stream when it only lacks its gzip end marker: that one is still open, or was cut by a kill not yet
    followed by a restart, and is listed in `open_files`), raw snapshot times per symbol, the last row time of each
    stream, the count of skipped lines and the open files."""
    rd = Reader(tolerant)
    gaps, snaps, last, open_files = [], {s: [] for s in SYMBOLS}, {}, []
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
            newest_of_folder = max(folder.glob("*.jsonl.gz"), key=_order, default=None)
            for f in files:
                newest = f == newest_of_folder
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
                except (OSError, EOFError, ValueError, zlib.error) as e:
                    h = datetime.strptime(f.name[:11], "%Y%m%dT%H").replace(tzinfo=timezone.utc)
                    if newest and isinstance(e, EOFError):
                        open_files.append((h, sub, f.name))
                    else:
                        gaps.append((h, sub, f"failed full gzip read of {f.name}: {type(e).__name__}"))
    gaps.sort()
    return gaps, snaps, last, rd.skipped, open_files


def _order(f):
    rest = f.name[11 : -len(".jsonl.gz")]
    return (f.name[:11], int(rest[1:]) if rest.startswith("-") and rest[1:].isdigit() else 0)


WINDOW_HOURS = 6.0  # HR-134: exactly 6 hours from the session's first raw snapshot


def _hms(d):
    s = int(d.total_seconds())
    return f"{s // 3600}:{s // 60 % 60:02d}:{s % 60:02d}"


def choose_window(data_dir, after, min_hours=None, max_hours=None, tolerant=False, until=None):
    """HR-134: sessions in time order; the first whose first raw snapshot, on or after `after`, then runs min_hours
    (6) with no gap row or restart in either symbol's raw or per-second files is the window, START = that snapshot,
    END = START + max_hours (6). min_hours/max_hours other than 6 are for samples only (main() needs --sample-only).
    Returns (start, end, log); log["sessions"] lists every session examined with start, end, length and why it was
    rejected; log["result"] is "window chosen" or starts with "none yet"."""
    gaps, snaps, last, skipped, open_files = scan(data_dir, after, tolerant, until)
    lo_h = WINDOW_HOURS if min_hours is None else min_hours
    hi_h = WINDOW_HOURS if max_hours is None else max_hours
    log = {"rule": f"HR-134: first session from --after that runs {lo_h:g} h with no gap row or restart; "
                   f"window exactly {hi_h:g} h",
           "gaps": [[iso(t), sub, why] for t, sub, why in gaps], "streams_last_t": {k: iso(v) for k, v in last.items()},
           "open_files": [[iso(h), sub, name] for h, sub, name in open_files],
           "skipped_lines": skipped, "sessions": []}
    if len(last) < 2 * len(SYMBOLS):
        log["result"] = "none yet: a stream has no rows at or after --after"
        return None, None, log
    data_end = min(last.values()) + timedelta(milliseconds=1)
    starts = sorted(t for s in SYMBOLS for t in snaps[s] if t >= after)
    min_d, max_d = timedelta(hours=lo_h), timedelta(hours=hi_h)
    tried = set()
    for s0 in starts:
        prev_gap = max((g for g, _, _ in gaps if g <= s0), default=None)
        if prev_gap in tried:
            continue  # only the first snapshot of each session is a candidate
        tried.add(prev_gap)
        nxt = min((g for g in gaps if g[0] > s0), default=None)
        limit = min(nxt[0], data_end) if nxt is not None else data_end
        sess = {"start": iso(s0), "end": iso(limit), "length": _hms(limit - s0)}
        log["sessions"].append(sess)
        if limit - s0 < min_d:
            if nxt is not None and nxt[0] <= data_end:
                what = "restart" if "recorder restart" in nxt[2] else "gap row"
                sess["rejected"] = f"{what} before hour {lo_h:g} at {iso(nxt[0])} in {nxt[1]}: {nxt[2]}"
            else:
                sess["rejected"] = f"recording ends before hour {lo_h:g}: the last session, may still qualify"
            continue
        end = min(s0 + max_d, limit)  # = s0 + 6 h under the rule (limit >= s0 + min_hours = s0 + 6 h)
        sess["window"] = [iso(s0), iso(end)]
        touching = [name for h, _, name in open_files if h < end]
        if touching:
            sess["open_files_in_window"] = touching
        log["result"] = "window chosen"
        return s0, end, log
    log["result"] = "none yet: no session qualifies"
    return None, None, log


def print_sessions(log, show=print):
    """One line per session examined: start, end, length, and why it was rejected or the window it gives."""
    for k, s in enumerate(log["sessions"], 1):
        if "window" in s:
            tail = f"QUALIFIES (the first; HR-134): window {s['window'][0]} to {s['window'][1]}"
        elif s["rejected"].startswith("recording ends"):
            tail = "not complete: " + s["rejected"]
        else:
            tail = "rejected: " + s["rejected"]
        show(f"session {k}: start {s['start']} end {s['end']} length {s['length']}: {tail}")
    for h, sub, name in log["open_files"]:
        show(f"open file (no gzip end marker; newest of its stream): {sub}/{name} (hour {h})")


# ---------------------------------------------------------------- R2 builder
def build(data_dir, symbol, start, end, prefix, tolerant=False, sample_only=False):
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
        **counts, "tolerant": tolerant, "sample_only": bool(sample_only or tolerant), "skipped_lines": rd.skipped, "inputs_sha256": inputs, "outputs_sha256": outputs,
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
    if sample_only or tolerant:
        print("WARNING: sample-only build (HR-134 rule bypassed); never a workload input")
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
        elif argv[k] in ("--tolerant", "--sample-only"):
            out[argv[k]] = True
            k += 1
        else:
            rest.append(argv[k])
            k += 1
    return out, rest


SAMPLE_OPTS = ("--after", "--until", "--min-hours", "--max-hours", "--tolerant")


def explicit_window_allowed(data_dir, start, end):
    """(ok, message): an explicit START END is allowed only if it is exactly the HR-134 window."""
    w0, w1, log = choose_window(data_dir, ts(AFTER_DEFAULT))
    if w0 is None:
        return False, f"no session qualifies yet ({log['result']}); an explicit window needs --sample-only"
    if (start, end) != (w0, w1):
        return False, (f"{iso(start)} to {iso(end)} is not the first qualifying session's window "
                       f"({iso(w0)} to {iso(w1)}, HR-134); give --sample-only for a development build")
    return True, "the explicit window is the HR-134 window"


def main(argv):
    o, rest = _opts(argv, ("--after", "--min-hours", "--max-hours", "--until"))
    sample = bool(o.get("--sample-only"))
    used = [k for k in SAMPLE_OPTS if k in o]
    if used and not sample:
        print(f"REFUSED: {', '.join(used)} bypass the HR-134 window rule; give --sample-only (never a workload input)")
        return 4
    until = ts(o["--until"]) if "--until" in o else None
    tolerant = bool(o.get("--tolerant"))
    after = ts(o.get("--after", AFTER_DEFAULT))
    lo = float(o["--min-hours"]) if "--min-hours" in o else None
    hi = float(o["--max-hours"]) if "--max-hours" in o else None
    if rest and rest[0] in ("window", "auto"):
        if len(rest) != (2 if rest[0] == "window" else 3):
            print(__doc__)
            return 2
        start, end, log = choose_window(rest[1], after, lo, hi, tolerant, until)
        print(f"rule: {log['rule']}; sessions from {iso(after)}")
        print_sessions(log)
        if sample:
            print("WARNING: --sample-only: not the HR-134 rule as fixed; never a workload input")
        if start is None:
            print(f"window: {log['result']}")
            return 3
        print(f"START {iso(start)} END {iso(end)}")
        sess = log["sessions"][-1]
        if sess.get("open_files_in_window"):
            print(f"window complete at {end.strftime('%H:%M:%S')}; stop the recorder cleanly before building "
                  f"(open: {', '.join(sess['open_files_in_window'])})")
            return 0 if rest[0] == "window" else 5
        if rest[0] == "window":
            return 0
        out = Path(rest[2])
        out.mkdir(parents=True, exist_ok=True)
        (out / "R2_window.json").write_text(json.dumps({"start": iso(start), "end": iso(end), "after": iso(after),
                                                        "min_hours": lo, "max_hours": hi, "sample_only": sample,
                                                        **log}, indent=1) + "\n")
        ins, outs = [], []
        for s in SYMBOLS:
            m = build(rest[1], s, start, end, str(out / f"R2_{s}"), tolerant, sample)
            ins += [f"{v}  {k}\n" for k, v in m["inputs_sha256"].items()]
            outs += [f"{v}  {k}\n" for k, v in m["outputs_sha256"].items()]
            outs.append(f"{sha(out / f'R2_{s}.meta.json')}  R2_{s}.meta.json\n")
        (out / "R2_inputs.sha256").write_bytes("".join(ins).encode())
        (out / "R2_replay.sha256").write_bytes("".join(outs).encode())
        print(f"wrote {out / 'R2_inputs.sha256'} and {out / 'R2_replay.sha256'}")
        return 0
    if len(rest) != 5:
        print(__doc__)
        return 2
    if not sample:
        ok, msg = explicit_window_allowed(rest[0], ts(rest[2]), ts(rest[3]))
        if not ok:
            print("REFUSED: " + msg)
            return 4
    build(*rest, tolerant=tolerant, sample_only=sample)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
