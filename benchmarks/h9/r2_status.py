#!/usr/bin/env python3
"""H-9 R2: read-only session status and raw-file cleanup under ruling HR-134 (safe while the recorder runs).

  python -I r2_status.py status  DATA_DIR [--log FILE] [--after ISO] [--now ISO]
  python -I r2_status.py cleanup DATA_DIR [--log FILE] [--after ISO] [--now ISO] [--delete]

DATA_DIR is qf-crypto-data/kraken; --log defaults to DATA_DIR/../recorder.log (the recorder's printed lines);
--after defaults to 2026-11-19T11:41:24Z (raw recording switched on); --now defaults to the wall clock.

What this tool reads, and nothing else:
  1. the recorder log, as text: lines "<t> recording ...", "<t> snapshot depth <SYM>: ...", "<t> reconnect after: ...",
     "<t> STOP file seen ..." and "<t> files closed cleanly" (tools/recorder/crypto_l2.py prints them);
  2. the names, sizes and modification times of the files in DATA_DIR/<SYM>-raw/ and DATA_DIR/<SYM>/;
  3. the per-second files DATA_DIR/<SYM>/<hour>*.jsonl.gz from the --after hour on, decompressed in memory only to find
     gap rows: a line is parsed only if it contains '"k":"gap"' (its "t" and "why"); every other line is dropped unread,
     and whether each gzip member has its end-of-stream marker is noted.
The raw message files (DATA_DIR/<SYM>-raw/) are never opened. `build_r2.py window` stays the deciding check (HR-134:
"sessions are examined in time order with build_r2.py's window mode"); this tool tells when it is worth running.

Sessions (item 2a, HR-132, HR-134): a session starts at the first "snapshot depth" line after a recorder start or a
reconnect, and ends at the first gap row or "reconnect after" line, a clean stop, or a new "recording" line (a restart;
a killed or shut-down recorder writes no gap row, and its end is estimated from the last modification time of the
data files before the restart). Sessions are examined in time order; the first that runs 6 hours is the window, taken
as exactly its first 6 hours, whatever its content; no later session is examined.

`cleanup` lists the raw hour files that belong ONLY to rejected sessions (dry run); with --delete it deletes exactly
those. A file is treated as covering its whole UTC hour. Never touched: the per-second folders, the 2026-11-17 sample
(20261117T20*), files before the --after hour, any file whose hour overlaps the qualifying session, an open session
(one that could still qualify), a session not examined, or no known session, each widened by 5 minutes.
Exit codes: status 0 = a session qualifies, 3 = none yet; cleanup 0.
"""
import json
import sys
import zlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

AFTER_DEFAULT = "2026-11-19T11:41:24Z"
SYMBOLS = ("BTC-USD", "ETH-USD")
WINDOW = timedelta(hours=6)  # HR-134: exactly 6 hours from the session's first raw snapshot
MARGIN = timedelta(minutes=5)  # protected intervals are widened by this much in `cleanup`
SAMPLE_KEEP = "20261117T20"  # the old development sample: never deleted here


def ts(text):
    return datetime.fromisoformat(text)  # Python 3.11+ reads the trailing Z


def iso(t):
    return t.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def hms(d):
    s = int(d.total_seconds())
    return f"{s // 3600}:{s // 60 % 60:02d}:{s % 60:02d}"


def file_hour(name):
    try:
        return datetime.strptime(name[:11], "%Y%m%dT%H").replace(tzinfo=UTC)
    except ValueError:
        return None


# ---------------------------------------------------------------- inputs
def parse_log(text):
    """Recorder log lines as events (t, kind, detail); kind is start, snap, gap, stop or closed."""
    out = []
    for line in text.splitlines():
        head, _, rest = line.partition(" ")
        if not head.endswith("Z"):
            continue
        try:
            t = ts(head)
        except ValueError:
            continue
        if rest.startswith("recording "):
            out.append((t, "start", ""))
        elif rest.startswith("snapshot depth "):
            out.append((t, "snap", rest[len("snapshot depth "):].split(":")[0]))
        elif rest.startswith("reconnect after: "):
            out.append((t, "gap", "log: reconnect after " + rest[len("reconnect after: "):]))
        elif rest.startswith("STOP file seen"):
            out.append((t, "stop", "recorder stopped by its STOP file"))
        elif rest.startswith("files closed cleanly"):
            out.append((t, "closed", "recorder files closed cleanly"))
    return out


def gap_rows(path):
    """Gap rows of one per-second file and whether every gzip member ended with its end marker.

    Returns (gaps, complete, error). Lines without '"k":"gap"' are dropped without being parsed."""
    gaps, buf, complete, error = [], b"", False, None
    d = zlib.decompressobj(31)
    try:
        with open(path, "rb") as f:
            while True:
                chunk = f.read(1 << 20)
                if not chunk:
                    break
                while chunk:
                    buf += d.decompress(chunk)
                    *lines, buf = buf.split(b"\n")
                    for ln in lines:
                        if b'"k":"gap"' in ln:
                            r = json.loads(ln)
                            gaps.append((ts(r["t"]), r.get("why", "")))
                    if d.eof:
                        complete, chunk = True, d.unused_data
                        if chunk:
                            d, complete = zlib.decompressobj(31), False
                    else:
                        chunk = b""
    except (zlib.error, ValueError, KeyError) as e:
        error = f"{type(e).__name__}"
    return gaps, complete and not error, error


def listing(data_dir):
    """{folder: [(path, hour, size, mtime)]} for the four recorder folders, newest file last."""
    out = {}
    for s in SYMBOLS:
        for sub in (s + "-raw", s):
            files = []
            for f in sorted(Path(data_dir, sub).glob("*.jsonl.gz"), key=_order):
                st = f.stat()
                files.append((f, file_hour(f.name), st.st_size,
                              datetime.fromtimestamp(st.st_mtime, UTC)))
            out[sub] = files
    return out


def _order(f):
    rest = f.name[11:-len(".jsonl.gz")]
    return (f.name[:11], int(rest[1:]) if rest.startswith("-") and rest[1:].isdigit() else 0)


# ---------------------------------------------------------------- sessions
def sessions(log_events, files, per_second, after, now):
    """Sessions in time order, each a dict (start, end, end_reason, open, status), and the verdict dict.

    per_second: {path: (gaps, complete, error)} for the per-second files read."""
    ev = list(log_events)
    for path, (gaps, _, error) in per_second.items():
        sym = Path(path).parent.name
        ev += [(t, "gap", f"gap row ({sym}): {why}") for t, why in gaps]
        if error:
            h = file_hour(Path(path).name)
            ev.append((h, "gap", f"{Path(path).name} ({sym}) failed to decompress: {error}"))
    rank = {"start": 0, "closed": 1, "stop": 1, "gap": 1, "snap": 2}
    ev.sort(key=lambda e: (e[0], rank[e[1]]))
    mtimes = sorted(m for fs in files.values() for _, _, _, m in fs)
    out, cur = [], None

    def end(t, why):
        nonlocal cur
        if cur is not None:
            cur.update(end=t, end_reason=why, open=False)
            out.append(cur)
            cur = None

    for t, kind, detail in ev:
        if kind == "start":
            if cur is not None:  # a restart with no gap row, stop line or close line before it: killed
                before = [m for m in mtimes if cur["start"] <= m < t]
                end(max(before, default=cur["start"]),
                    "recorder restart with no clean stop (killed, crashed or shut down); end estimated from file times")
        elif kind == "snap":
            if cur is None:
                cur = {"start": t, "end": None, "end_reason": None, "open": True}
        elif kind in ("gap", "stop") or kind == "closed":
            end(t, detail)
    if cur is not None:
        cur["end"] = now
        out.append(cur)

    newest_open = []  # per-second files still being written (newest of their folder, no end marker)
    for s in SYMBOLS:
        fs = files.get(s, [])
        if fs and fs[-1][0] in per_second and not per_second[fs[-1][0]][1] and not per_second[fs[-1][0]][2]:
            newest_open.append(fs[-1][0].name)
    unterminated = {Path(p).name for p, (_, c, e) in per_second.items() if not c and not e}

    verdict = {"window": None, "recorder_writing": bool(newest_open), "open_files": newest_open}
    for x in out:
        if x["start"] < after:
            x["status"] = "before --after: not examined"
            continue
        if verdict["window"] is not None:
            x["status"] = "not examined: an earlier session qualified (HR-134)"
            continue
        length = x["end"] - x["start"]
        if length < WINDOW:
            if x["open"]:
                x["status"] = (f"open: may still qualify; 6 hours at {iso(x['start'] + WINDOW)} "
                               "if no gap row or restart comes first")
            else:
                x["status"] = f"rejected: ended before hour 6 ({x['end_reason']})"
            continue
        w0, w1 = x["start"], x["start"] + WINDOW
        broken = [n for n in sorted(unterminated - set(newest_open))
                  if file_hour(n) is not None and w0 - timedelta(hours=1) < file_hour(n) < w1]
        if broken:
            x["status"] = ("rejected: per-second file(s) in the window lack the gzip end marker (killed recorder; "
                           "item 2a full read): " + ", ".join(broken))
            continue
        x["status"] = f"QUALIFIES: window {iso(w0)} to {iso(w1)}"
        verdict["window"] = (w0, w1)
    return out, verdict


def gather(data_dir, log_path, after):
    text = Path(log_path).read_text(encoding="utf-8", errors="replace") if Path(log_path).exists() else ""
    files = listing(data_dir)
    hour0 = after.replace(minute=0, second=0, microsecond=0)
    per_second = {}
    for s in SYMBOLS:
        for f, h, _, _ in files[s]:
            if h is not None and h >= hour0:
                per_second[f] = gap_rows(f)
    return parse_log(text), files, per_second, bool(text)


def status(data_dir, log_path, after, now, show=print):
    log_events, files, per_second, have_log = gather(data_dir, log_path, after)
    found, verdict = sessions(log_events, files, per_second, after, now)
    show(f"read: {log_path} ({'present' if have_log else 'MISSING'}); names, sizes and times of "
         f"{sum(len(v) for v in files.values())} files; gap rows of {len(per_second)} per-second files "
         "(raw message files not opened)")
    for k, s in enumerate(found, 1):
        show(f"session {k}: start {iso(s['start'])} end {iso(s['end'])}{' (now)' if s['open'] else ''} "
             f"length {hms(s['end'] - s['start'])}: {s['status']}")
    if verdict["window"] is None:
        show("window: none yet")
        return 3, found, verdict
    w1 = verdict["window"][1]
    if verdict["recorder_writing"]:
        show(f"window complete at {w1.strftime('%H:%M:%S')} ({iso(w1)}); stop the recorder cleanly before building "
             f"(open: {', '.join(verdict['open_files'])})")
    else:
        show(f"window complete at {w1.strftime('%H:%M:%S')} ({iso(w1)}); recorder files closed: run build_r2.py window, "
             "then auto")
    return 0, found, verdict


def cleanup_plan(data_dir, found, verdict, after):
    """(delete, keep): lists of (path, size, reason). Only <SYM>-raw files are ever listed for deletion."""
    rejected, protected = [], []
    for s in found:
        st = s["status"]
        if st.startswith("rejected"):
            rejected.append((s["start"], s["end"]))
        elif st.startswith("before --after"):
            continue
        else:  # qualifying, open, not examined
            protected.append((s["start"] - MARGIN, s["end"] + MARGIN if not s["open"] else datetime.max.replace(tzinfo=UTC)))
    if verdict["window"] is not None:
        w0, w1 = verdict["window"]
        protected.append((w0 - MARGIN, w1 + MARGIN))
    hour0 = after.replace(minute=0, second=0, microsecond=0)
    delete, keep = [], []
    for s in SYMBOLS:
        folder = Path(data_dir) / (s + "-raw")
        for f in sorted(folder.glob("*.jsonl.gz"), key=_order):
            assert f.parent.name.endswith("-raw") and f.parent.name[:-4] in SYMBOLS
            size, h = f.stat().st_size, file_hour(f.name)
            span = (h, h + timedelta(hours=1)) if h else None

            def hits(iv, span=span):
                return span is not None and iv[0] < span[1] and span[0] < iv[1]

            if f.name.startswith(SAMPLE_KEEP):
                keep.append((f, size, "2026-11-17 sample: never deleted"))
            elif h is None or h < hour0:
                keep.append((f, size, "before the --after hour"))
            elif any(hits(iv) for iv in protected):
                keep.append((f, size, "overlaps the qualifying window or a session that could still qualify"))
            elif not any(hits(iv) for iv in rejected):
                keep.append((f, size, "no known session: kept"))
            else:
                delete.append((f, size, "only rejected sessions"))
    return delete, keep


def _opts(argv):
    o, rest, k = {}, [], 0
    while k < len(argv):
        if argv[k] in ("--log", "--after", "--now"):
            o[argv[k]] = argv[k + 1]
            k += 2
        elif argv[k] == "--delete":
            o["--delete"] = True
            k += 1
        else:
            rest.append(argv[k])
            k += 1
    return o, rest


def main(argv):
    o, rest = _opts(argv)
    if len(rest) != 2 or rest[0] not in ("status", "cleanup"):
        print(__doc__)
        return 2
    data_dir = Path(rest[1])
    log_path = Path(o.get("--log", data_dir.parent / "recorder.log"))
    after = ts(o.get("--after", AFTER_DEFAULT))
    now = ts(o["--now"]) if "--now" in o else datetime.now(UTC)
    rc, found, verdict = status(data_dir, log_path, after, now)
    if rest[0] == "status":
        return rc
    delete, keep = cleanup_plan(data_dir, found, verdict, after)
    for f, size, why in keep:
        print(f"keep   {f.parent.name}/{f.name} {size} B: {why}")
    for f, size, why in delete:
        print(f"{'DELETE' if o.get('--delete') else 'would delete'} {f.parent.name}/{f.name} {size} B: {why}")
        if o.get("--delete"):
            f.unlink()
    total = sum(size for _, size, _ in delete)
    print(f"{len(delete)} raw files, {total} B {'deleted' if o.get('--delete') else 'listed (dry run; --delete deletes)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
