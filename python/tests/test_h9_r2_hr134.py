"""H-9 R2 window rule of ruling HR-134 (build_r2.py window/auto), the read-only status and the raw cleanup helper
(benchmarks/h9/r2_status.py), on synthetic recorder folders only.

No recorded rows: every file below is written here. Sessions are sparse (one raw update and one per-second row every
30 minutes), enough for the window rule, which reads only times, row kinds and gap rows.
"""

import gzip
import importlib.util
import json
import os
import sys
import zlib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

H9 = Path(__file__).resolve().parents[2] / "benchmarks" / "h9"


def _load(name: str) -> Any:
    sys.path.insert(0, str(H9))
    spec = importlib.util.spec_from_file_location(name, H9 / f"{name}.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


build_r2 = _load("build_r2")
r2_status = _load("r2_status")

D19 = datetime(2026, 11, 19, tzinfo=UTC)
D20 = datetime(2026, 11, 20, tzinfo=UTC)
AFTER = datetime(2026, 11, 19, 11, 41, 24, tzinfo=UTC)
SYMS = ("BTC-USD", "ETH-USD")
H6 = timedelta(hours=6)


def at(day: datetime, h: int, m: int = 0, s: int = 0) -> datetime:
    return day.replace(hour=h, minute=m, second=s)


# The four sessions of 2026-11-19 (HR-134), then a fifth cut by the night's shutdown (no gap row: a kill).
TODAY = [
    (at(D19, 11, 41, 24), at(D19, 15, 1, 58), "gap"),
    (at(D19, 15, 2, 28), at(D19, 15, 29, 49), "gap"),
    (at(D19, 15, 30, 22), at(D19, 17, 17, 40), "gap"),
    (at(D19, 17, 18, 41), at(D19, 17, 36, 24), "gap"),
    (at(D19, 17, 37), at(D19, 23, 30), "kill"),
]


def _stamp(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _gz(path: Path, rows: list[dict[str, Any]], closed: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(r, separators=(",", ":")) + "\n" for r in rows).encode()
    if closed:
        with gzip.open(path, "wb") as g:
            g.write(text)
    else:  # still being written: sync-flushed, no end-of-stream marker (tools/recorder/crypto_l2.py Sink)
        c = zlib.compressobj(6, zlib.DEFLATED, 31)
        path.write_bytes(c.compress(text) + c.flush(zlib.Z_SYNC_FLUSH))


def make(
    root: Path, sessions: list[tuple[datetime, datetime, str]], open_last: bool = False
) -> Path:
    """Recorder folders and recorder.log for `sessions` (start, end, how); how is "gap" (a gap row at end), "kill"
    (rows stop; the next session follows with no gap row, or nothing follows) or "stop" (clean STOP at end).
    open_last: the newest file of each stream has no gzip end marker (the recorder is still writing it)."""
    data = root / "kraken"
    log: list[tuple[datetime, str]] = []
    prev_how = None
    for k, (s0, s1, how) in enumerate(sessions):
        if k == 0 or prev_how in ("kill", "stop"):
            log.append((s0 - timedelta(seconds=5), "recording ['BTC/USD', 'ETH/USD'] to X"))
        for j, sym in enumerate(SYMS):
            log.append(
                (
                    s0 + timedelta(milliseconds=j),
                    f"snapshot depth {sym.replace('-', '/')}: 100 bids, 100 asks",
                )
            )
        if how == "gap":
            log.append(
                (s1 + timedelta(milliseconds=500), "reconnect after: TimeoutError: synthetic")
            )
        elif how == "stop":
            log += [
                (s1, "STOP file seen: stopping cleanly"),
                (s1 + timedelta(seconds=1), "files closed cleanly"),
            ]
        prev_how = how
    store: dict[tuple[str, str], list[dict[str, Any]]] = {}

    def put(sub: str, t: datetime, row: dict[str, Any]) -> None:
        store.setdefault((sub, t.strftime("%Y%m%dT%H")), []).append({"t": _stamp(t), **row})

    for s0, s1, how in sessions:
        for j, sym in enumerate(SYMS):
            put(
                sym + "-raw",
                s0 + timedelta(milliseconds=j),
                {"k": "msg", "type": "snapshot", "bids": [], "asks": [], "checksum": 0, "ok": True},
            )
            t = s0 + timedelta(seconds=1)
            while t < s1:
                put(
                    sym + "-raw",
                    t,
                    {
                        "k": "msg",
                        "type": "update",
                        "bids": [],
                        "asks": [],
                        "checksum": 0,
                        "ok": True,
                    },
                )
                put(sym, t, {"k": "book", "bids": [], "asks": [], "ok": True})
                t += timedelta(minutes=30)
            if how == "gap":
                for sub in (sym + "-raw", sym):
                    put(sub, s1, {"k": "gap", "why": "TimeoutError: synthetic"})
    newest = {sub: max(h for s, h in store if s == sub) for sub, _ in store}
    for (sub, h), rows in store.items():
        f = data / sub / f"{h}.jsonl.gz"
        _gz(f, rows, closed=not (open_last and h == newest[sub]))
        last = datetime.fromisoformat(rows[-1]["t"]).timestamp()
        if open_last and h == newest[sub]:
            last = sessions[-1][
                1
            ].timestamp()  # being written: modified at the session's last instant
        os.utime(f, (last, last))
    log.sort()
    (root / "recorder.log").write_text(
        "".join(f"{_stamp(t)} {m}\n" for t, m in log), encoding="utf-8"
    )
    return data


def _poison_raw(data: Path) -> None:
    """Replace every raw file by bytes that are not gzip (same name, size order and time): proves a reader that
    still works never opened them."""
    for f in data.glob("*-raw/*.jsonl.gz"):
        st = f.stat()
        f.write_bytes(b"NOT GZIP: raw content must not be read" * 3)
        os.utime(f, (st.st_mtime, st.st_mtime))


# ---------------------------------------------------------------- build_r2.py window mode (HR-134)
def test_four_rejected_sessions_then_a_shutdown_then_a_qualifying_one_next_day(
    tmp_path: Path,
) -> None:
    later = [(at(D20, 8), at(D20, 15), "gap"), (at(D20, 15, 1), at(D20, 16), "stop")]
    data = make(tmp_path, TODAY + later)
    start, end, log = build_r2.choose_window(data, AFTER)
    assert (start, end) == (
        at(D20, 8),
        at(D20, 14),
    )  # exactly 6 hours, not to the session's end at 15:00
    ss = log["sessions"]
    assert (
        len(ss) == 6 and "window" in ss[5]
    )  # the session after the qualifying one is not examined
    assert [s["start"][:19] for s in ss[:4]] == [
        "2026-11-19T11:41:24",
        "2026-11-19T15:02:28",
        "2026-11-19T15:30:22",
        "2026-11-19T17:18:41",
    ]
    assert all(s["rejected"].startswith("gap row before hour 6") for s in ss[:4])
    assert ss[0]["end"].startswith("2026-11-19T15:01:58") and ss[0]["length"] == "3:20:34"
    assert ss[4]["rejected"].startswith(
        "restart before hour 6"
    )  # the shutdown: no gap row, a restart next day
    lines: list[str] = []
    build_r2.print_sessions(log, lines.append)
    assert (
        len(lines) == 6
        and "QUALIFIES" in lines[5]
        and "length 3:20:34: rejected: gap row" in lines[0]
    )


def test_window_mode_prints_none_yet_while_no_session_qualifies(
    tmp_path: Path, capsys: Any
) -> None:
    data = make(tmp_path, TODAY)
    assert build_r2.main(["window", str(data)]) == 3
    out = capsys.readouterr().out
    # The last session (cut by the shutdown, no restart yet) cannot be told from one still recording: not complete.
    assert out.count("rejected: ") == 4 and "not complete: recording ends before hour 6" in out
    assert "window: none yet" in out


def test_a_session_spanning_midnight_qualifies(tmp_path: Path) -> None:
    data = make(tmp_path, [*TODAY[:4], (at(D20, 21), at(D20 + timedelta(days=1), 4), "gap")])
    start, end, log = build_r2.choose_window(data, AFTER)
    assert (start, end) == (at(D20, 21), at(D20 + timedelta(days=1), 3))
    assert log["sessions"][-1]["window"][1].startswith("2026-11-21T03:00:00")


def test_two_qualifying_sessions_the_first_is_chosen(tmp_path: Path) -> None:
    first = (at(D20, 8), at(D20, 15), "gap")
    second = (at(D20, 15, 1), at(D20, 23, 30), "gap")  # longer, yet never preferred
    data = make(tmp_path, [*TODAY[:4], first, second])
    start, end, log = build_r2.choose_window(data, AFTER)
    assert (start, end) == (at(D20, 8), at(D20, 14))
    assert len(log["sessions"]) == 5


def test_an_explicit_window_that_is_not_the_first_qualifying_one_is_refused(
    tmp_path: Path, capsys: Any
) -> None:
    data = make(
        tmp_path,
        [*TODAY[:4], (at(D20, 8), at(D20, 15), "gap"), (at(D20, 15, 1), at(D20, 23, 30), "gap")],
    )
    ok, msg = build_r2.explicit_window_allowed(data, at(D20, 15, 1), at(D20, 21, 1))
    assert not ok and "not the first qualifying session" in msg
    ok, _ = build_r2.explicit_window_allowed(data, at(D20, 8), at(D20, 14))
    assert ok
    ok, _ = build_r2.explicit_window_allowed(
        data, at(D20, 8), at(D20, 15)
    )  # the right start, but not 6 hours
    assert not ok
    out = str(tmp_path / "R2_BTC-USD")
    rc = build_r2.main([str(data), "BTC-USD", _stamp(at(D20, 15, 1)), _stamp(at(D20, 21, 1)), out])
    assert rc == 4 and "REFUSED" in capsys.readouterr().out
    assert not Path(out + ".bin").exists()


def test_an_explicit_window_is_refused_while_none_qualifies(tmp_path: Path) -> None:
    data = make(tmp_path, TODAY)
    ok, msg = build_r2.explicit_window_allowed(data, at(D19, 11, 41, 24), at(D19, 17, 41, 24))
    assert not ok and "no session qualifies yet" in msg


@pytest.mark.parametrize(
    "opts",
    [
        ["--min-hours", "0.5"],
        ["--max-hours", "8"],
        ["--after", "2026-11-20T00:00:00Z"],
        ["--until", "2026-11-20T00:00:00Z"],
        ["--tolerant"],
    ],
)
def test_sample_overrides_need_the_sample_only_flag(
    tmp_path: Path, opts: list[str], capsys: Any
) -> None:
    data = make(tmp_path, TODAY)
    assert build_r2.main(["window", str(data), *opts]) == 4
    assert "REFUSED" in capsys.readouterr().out
    assert build_r2.main(["window", str(data), *opts, "--sample-only"]) in (0, 3)


def test_a_sample_override_can_change_the_window_only_with_the_flag(tmp_path: Path) -> None:
    data = make(tmp_path, TODAY)
    start, _, _ = build_r2.choose_window(data, AFTER, min_hours=3.0, max_hours=3.0)
    assert start == at(D19, 11, 41, 24)
    assert build_r2.main(["window", str(data), "--min-hours", "3", "--max-hours", "3"]) == 4


def test_open_newest_file_is_not_a_gap_and_auto_waits_for_a_clean_stop(
    tmp_path: Path, capsys: Any
) -> None:
    data = make(tmp_path, [*TODAY[:4], (at(D20, 8, 0, 5), at(D20, 14, 40), "kill")], open_last=True)
    start, end, log = build_r2.choose_window(data, AFTER)
    assert (start, end) == (
        at(D20, 8, 0, 5),
        at(D20, 14, 0, 5),
    )  # the window ends inside the open 14:00 file
    assert log["sessions"][-1]["open_files_in_window"] == ["20261120T14.jsonl.gz"] * 4
    assert not any("20261120T14" in g[2] for g in log["gaps"])
    assert build_r2.main(["window", str(data)]) == 0
    assert (
        "window complete at 14:00:05; stop the recorder cleanly before building"
        in capsys.readouterr().out
    )
    assert build_r2.main(["auto", str(data), str(tmp_path / "out")]) == 5
    assert not (tmp_path / "out" / "R2_window.json").exists()


def test_open_session_shorter_than_six_hours_may_still_qualify(tmp_path: Path) -> None:
    data = make(tmp_path, [*TODAY[:4], (at(D20, 8), at(D20, 12, 40), "kill")], open_last=True)
    start, _, log = build_r2.choose_window(data, AFTER)
    assert start is None and log["result"].startswith("none yet")
    assert "may still qualify" in log["sessions"][-1]["rejected"]


def test_a_file_cut_by_a_kill_inside_a_session_is_a_gap(tmp_path: Path) -> None:
    data = make(tmp_path, [(at(D20, 8), at(D20, 15), "gap"), (at(D20, 15, 1), at(D20, 16), "stop")])
    f = (
        data / "BTC-USD" / "20261120T10.jsonl.gz"
    )  # not the newest file: no end marker means a broken file
    f.write_bytes(gzip.compress(f.read_bytes())[:-8])
    start, _, log = build_r2.choose_window(data, AFTER)
    assert start is None or start != at(D20, 8)
    assert log["sessions"][0]["rejected"].startswith("gap row before hour 6 at 2026-11-20T10:00:00")


# ---------------------------------------------------------------- r2_status.py status (read-only)
def _status(
    tmp_path: Path, data: Path, now: datetime
) -> tuple[int, list[dict[str, Any]], dict[str, Any], str]:
    lines: list[str] = []
    rc, found, verdict = r2_status.status(data, tmp_path / "recorder.log", AFTER, now, lines.append)
    return rc, found, verdict, "\n".join(lines)


def test_status_lists_sessions_without_opening_raw_files(tmp_path: Path) -> None:
    later = [(at(D20, 8), at(D20, 15), "gap"), (at(D20, 15, 1), at(D20, 16), "stop")]
    data = make(tmp_path, TODAY + later)
    _poison_raw(data)
    rc, found, verdict, text = _status(tmp_path, data, at(D20, 17))
    assert rc == 0 and verdict["window"] == (at(D20, 8), at(D20, 14))
    assert [s["status"].split(":")[0] for s in found] == ["rejected"] * 5 + [
        "QUALIFIES",
        "not examined",
    ]
    assert found[0]["end"] == at(D19, 15, 1, 58) and "gap row (" in found[0]["end_reason"]
    assert "recorder restart with no clean stop" in found[4]["end_reason"]
    assert found[4]["end"] < at(D19, 23, 30)  # estimated from the last file time before the restart
    assert "raw message files not opened" in text and "recorder files closed" in text


def test_status_says_stop_the_recorder_when_the_window_is_complete_while_recording(
    tmp_path: Path,
) -> None:
    data = make(tmp_path, [*TODAY[:4], (at(D20, 8), at(D20, 14, 40), "kill")], open_last=True)
    _poison_raw(data)
    rc, _, verdict, text = _status(tmp_path, data, at(D20, 14, 41))
    assert rc == 0 and verdict["recorder_writing"]
    assert (
        "window complete at 14:00:00 (2026-11-20T14:00:00.000Z); stop the recorder cleanly before building"
        in text
    )


def test_status_none_yet_while_the_open_session_is_short(tmp_path: Path) -> None:
    data = make(tmp_path, [*TODAY[:4], (at(D20, 8), at(D20, 12, 40), "kill")], open_last=True)
    _poison_raw(data)
    rc, found, _, text = _status(tmp_path, data, at(D20, 12, 41))
    assert rc == 3 and text.endswith("window: none yet")
    assert found[-1]["status"].startswith("open: may still qualify; 6 hours at 2026-11-20T14:00:00")


def test_status_main_reads_the_default_log_next_to_the_data(tmp_path: Path, capsys: Any) -> None:
    data = make(tmp_path, TODAY)
    _poison_raw(data)
    # The night's session has no end line and no restart yet: its files stopped at about 23:00, so it ended there.
    assert r2_status.main(["status", str(data), "--now", "2026-11-20T07:00:00Z"]) == 3
    out = capsys.readouterr().out
    assert (
        "present" in out
        and "no recorder output since 2026-11-19T23:07" in out
        and "window: none yet" in out
    )


# ---------------------------------------------------------------- r2_status.py cleanup
def _plan(tmp_path: Path, data: Path, now: datetime) -> tuple[set[str], dict[str, str]]:
    _, found, verdict, _ = _status(tmp_path, data, now)
    delete, keep = r2_status.cleanup_plan(data, found, verdict, AFTER)
    return {f"{f.parent.name}/{f.name}" for f, _, _ in delete}, {
        f"{f.parent.name}/{f.name}": w for f, _, w in keep
    }


def test_cleanup_lists_only_raw_files_of_rejected_sessions(tmp_path: Path) -> None:
    later = [(at(D20, 8), at(D20, 15), "gap"), (at(D20, 15, 1), at(D20, 16), "stop")]
    data = make(tmp_path, TODAY + later)
    sample = data / "BTC-USD-raw" / "20261117T20.jsonl.gz"
    _gz(sample, [])
    delete, keep = _plan(tmp_path, data, at(D20, 17))
    want = {f"{s}-raw/20261119T{h:02d}.jsonl.gz" for s in SYMS for h in range(11, 24)}
    assert (
        delete == want
    )  # hour 15 is shared by three rejected sessions, hour 17 by three: all rejected
    assert all(not d.split("/")[0] in SYMS for d in delete)  # never a per-second folder
    assert keep["BTC-USD-raw/20261117T20.jsonl.gz"].startswith("2026-11-17 sample")
    assert "qualifying" in keep["BTC-USD-raw/20261120T14.jsonl.gz"]
    assert (
        "BTC-USD-raw/20261120T15.jsonl.gz" in keep
    )  # shared by the qualifying session and the one after it


def test_cleanup_keeps_a_file_shared_by_a_rejected_session_and_the_qualifying_one(
    tmp_path: Path,
) -> None:
    sessions = [
        (at(D20, 7, 30), at(D20, 8, 10), "gap"),
        (at(D20, 8, 20), at(D20, 15), "gap"),
        (at(D20, 15, 1), at(D20, 16), "stop"),
    ]
    data = make(tmp_path, sessions)
    delete, keep = _plan(tmp_path, data, at(D20, 17))
    assert delete == {f"{s}-raw/20261120T07.jsonl.gz" for s in SYMS}
    assert "BTC-USD-raw/20261120T08.jsonl.gz" in keep and "ETH-USD-raw/20261120T08.jsonl.gz" in keep


def test_cleanup_margin_keeps_the_hour_just_before_the_qualifying_session(tmp_path: Path) -> None:
    sessions = [(at(D20, 8, 10), at(D20, 8, 58), "gap"), (at(D20, 9, 2), at(D20, 16), "stop")]
    data = make(tmp_path, sessions)
    delete, keep = _plan(tmp_path, data, at(D20, 17))
    assert delete == set() and "BTC-USD-raw/20261120T08.jsonl.gz" in keep


def test_cleanup_never_touches_a_session_that_could_still_qualify(tmp_path: Path) -> None:
    sessions = [
        *TODAY[:4],
        (at(D20, 8), at(D20, 9, 40), "gap"),
        (at(D20, 9, 50), at(D20, 12, 40), "kill"),
    ]
    data = make(tmp_path, sessions, open_last=True)
    delete, keep = _plan(tmp_path, data, at(D20, 12, 41))
    assert (
        "BTC-USD-raw/20261120T09.jsonl.gz" in keep
    )  # rejected 08:00 session shares hour 9 with the open one
    assert "BTC-USD-raw/20261120T08.jsonl.gz" in delete
    assert all(
        not d.startswith(("BTC-USD-raw/20261120T1", "ETH-USD-raw/20261120T1")) for d in delete
    )


def test_cleanup_dry_run_deletes_nothing_and_delete_flag_deletes_exactly_the_list(
    tmp_path: Path, capsys: Any
) -> None:
    later = [(at(D20, 8), at(D20, 15), "gap"), (at(D20, 15, 1), at(D20, 16), "stop")]
    data = make(tmp_path, TODAY + later)
    before = sorted(p.relative_to(data).as_posix() for p in data.rglob("*.jsonl.gz"))
    assert r2_status.main(["cleanup", str(data), "--now", "2026-11-20T17:00:00Z"]) == 0
    assert sorted(p.relative_to(data).as_posix() for p in data.rglob("*.jsonl.gz")) == before
    assert "would delete" in capsys.readouterr().out
    delete, _ = _plan(tmp_path, data, at(D20, 17))
    assert r2_status.main(["cleanup", str(data), "--now", "2026-11-20T17:00:00Z", "--delete"]) == 0
    after = sorted(p.relative_to(data).as_posix() for p in data.rglob("*.jsonl.gz"))
    assert set(before) - set(after) == delete
    assert any(p.startswith("BTC-USD/20261119T11") for p in after)  # per-second files untouched


# ---------------------------------------------------------------- HR-135 (audit B: KA-B4, KA-B6, KA-B16, KA-B17)
check_r2 = _load("check_r2")
r2_meta = _load("r2_meta")


def _tools() -> Any:
    spec = importlib.util.spec_from_file_location(
        "h9_tools", Path(__file__).with_name("test_h9_r2_tools.py")
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


T1 = datetime(2026, 11, 20, 12, 0, 10, tzinfo=UTC)

# True message stream: deep changes (bid levels 11 and 12) at 0.5 s and inside the tie at 1.0 s, a touch change
# ending the tie, a deep change at 1.5 s. Entries: (time, bid changes, ask changes).
_TRUE: list[tuple[float, list[Any], list[Any]]] = [
    (0.0, [[100 - k, "1.0"] for k in range(12)], [[101, "1.0"], [102, "1.0"]]),
    (0.5, [[90, "2.0"]], []),
    (1.0, [[89, "3.0"]], []),
    (1.0, [[90, "4.0"]], []),
    (1.0, [], [[102, "5.0"]]),
    (1.5, [[89, "6.0"]], []),
]
# The same stream as a wrong book applies it: every below-level-10 change one message late (top 10 unchanged).
_LAGGED: list[tuple[float, list[Any], list[Any]]] = [
    _TRUE[0],
    (0.5, [], []),
    (1.0, [[90, "2.0"]], []),
    (1.0, [[89, "3.0"]], []),
    (1.0, [[90, "4.0"]], [[102, "5.0"]]),
    (1.5, [], []),
]


def _tie_data(root: Path, stream: list[tuple[float, list[Any], list[Any]]]) -> Path:
    """Raw files from `stream`, with the venue checksums and per-second rows of the TRUE stream: row 1 at 1.0 s is
    the true book after message 2 (inside the tie: lo = 1, hi = 4), row 2 at 2.0 s (no tie) after message 5."""
    tools_mod = _tools()
    out = root / "kraken"
    for sym in SYMS:
        dec = tools_mod.DEC[sym]

        def lv(xs: list[Any], dec: int = dec) -> list[list[str]]:
            return [[f"{p:.{dec}f}", build_r2.fixed(q)] for p, q in xs]

        true_books, crcs = [], []
        so_far: list[dict[str, Any]] = []
        for k, (_, b, a) in enumerate(_TRUE):
            typ = "snapshot" if k == 0 else "update"
            so_far.append({"type": typ, "bids": lv(b), "asks": lv(a), "checksum": None})
            res = tools_mod.rebuild(so_far, 100, dec, 8)
            true_books.append(res["book"])
            crcs.append(res["crc32"])
        raw = [
            {
                "t": _stamp(T1 + timedelta(seconds=dt)),
                "k": "msg",
                "type": "snapshot" if k == 0 else "update",
                "bids": [{"price": p, "qty": q} for p, q in lv(b)],
                "asks": [{"price": p, "qty": q} for p, q in lv(a)],
                "checksum": crcs[k],
                "ok": True,
            }
            for k, (dt, b, a) in enumerate(stream)
        ]
        rows = [
            {"t": _stamp(T1 + timedelta(seconds=1.0)), "k": "book", **true_books[2], "ok": True},
            {"t": _stamp(T1 + timedelta(seconds=2.0)), "k": "book", **true_books[5], "ok": True},
        ]
        _gz(out / f"{sym}-raw" / "20261120T12.jsonl.gz", raw)
        _gz(out / sym / "20261120T12.jsonl.gz", rows)
    return out


def _tie_check(
    tmp_path: Path, name: str, stream: list[tuple[float, list[Any], list[Any]]]
) -> dict[str, Any]:
    data = _tie_data(tmp_path / name, stream)
    out = tmp_path / f"{name}_out"
    out.mkdir()
    prefix = str(out / "R2_BTC-USD")
    build_r2.build(data, "BTC-USD", T1, T1 + timedelta(seconds=3), prefix, sample_only=True)
    res: dict[str, Any] = check_r2.check(prefix)
    return res


def test_tie_rule_admits_a_one_message_lag_only_inside_a_tie(tmp_path: Path) -> None:
    """HR-135 (KA-B4, KA-B16): a wrong book (deep changes one message late) passes the venue checksum at every
    message and passes the tied row, which it equals at a later message of the tie than the true book does; the
    next row with no tie (lo = hi, compared exactly) catches it as a below-level-10 failure."""
    good = _tie_check(tmp_path, "true", _TRUE)
    assert good["checksum_failed"] == 0 and good["checkpoint_checked"] == 2
    assert good["checkpoint_failed_top10"] == 0 and good["checkpoint_failed_below10"] == 0
    assert good["checkpoint_rows_with_tie"] == 1 and good["checkpoint_matched_only_inside_tie"] == 1
    bad = _tie_check(tmp_path, "lagged", _LAGGED)
    assert bad["checksum_failed"] == 0  # the top 10 never differs: the checksum cannot see this bug
    assert bad["checkpoint_failed_top10"] == 0
    assert (
        bad["checkpoint_matched_only_inside_tie"] == 1
    )  # the tied row passed, one message later than the truth
    assert bad["checkpoint_failed_below10"] == 1  # the row at 2.0 s, no tie: caught
    # On this two-row sample the tie guard trips too (one row of two matched only inside the tie).
    assert r2_meta.tie_guard(good)


def test_tie_guard_limits() -> None:
    ok = {
        "checkpoint_checked": 1000,
        "checkpoint_rows_with_tie": 750,
        "checkpoint_matched_only_inside_tie": 60,
    }
    assert r2_meta.tie_guard(ok) == []
    assert r2_meta.tie_guard({**ok, "checkpoint_rows_with_tie": 751})  # 249 without a tie < 25 %
    assert r2_meta.tie_guard({**ok, "checkpoint_matched_only_inside_tie": 61})  # > 6 %
    assert r2_meta.tie_guard({**ok, "checkpoint_checked": 0})
    for n, tie, inside in (
        (846, 292, 16),
        (895, 218, 19),
    ):  # the 2026-11-17 sample (README_R2.md) passes
        sample = {
            "checkpoint_checked": n,
            "checkpoint_rows_with_tie": tie,
            "checkpoint_matched_only_inside_tie": inside,
        }
        assert r2_meta.tie_guard(sample) == []


def test_tie_guard_fails_compare(tmp_path: Path, capsys: Any) -> None:
    ref: dict[str, Any] = dict.fromkeys(r2_meta.FIELDS, 0)
    ref.update(
        checkpoint_checked=10,
        checkpoint_rows_with_tie=9,
        checkpoint_matched_at_lo=10,
        checkpoint_matched_at_hi=10,
        book_messages=5,
        chunk_start_mismatches=0,
    )
    py = tmp_path / "py.json"
    py.write_text(json.dumps(ref))
    h = tmp_path / "cpp.json"
    h.write_text(
        json.dumps({"form_a": {f: ref[f] for f in r2_meta.FIELDS}, "correctness_mismatches": 0})
    )
    assert r2_meta.compare("BTC-USD", py, h) == 1
    assert "TIE GUARD (HR-135)" in capsys.readouterr().out


def test_a_missing_hour_file_inside_a_session_is_a_gap(tmp_path: Path) -> None:
    data = make(tmp_path, [(at(D20, 8), at(D20, 15), "gap"), (at(D20, 15, 1), at(D20, 16), "stop")])
    (data / "ETH-USD-raw" / "20261120T11.jsonl.gz").unlink()
    start, _, log = build_r2.choose_window(data, AFTER)
    assert start != at(D20, 8)
    rejected = log["sessions"][0]["rejected"]
    assert rejected.startswith("gap row before hour 6 at 2026-11-20T11:00:00")
    assert "missing hour file 20261120T11.jsonl.gz" in rejected


def _clean_inputs(d: Path) -> Path:
    """An input folder as `build_r2.py auto` writes it under the rule (no option given)."""
    d.mkdir(parents=True, exist_ok=True)
    opts = {
        "after": "2026-11-19T11:41:24.000000Z",
        "until": None,
        "min_hours": None,
        "max_hours": None,
        "tolerant": False,
        "sample_only": False,
        "argv": ["auto", "X", "Y"],
    }
    (d / "R2_window.json").write_text(json.dumps({"start": "s", "end": "e", "options": opts}))
    for s in SYMS:
        (d / f"R2_{s}.meta.json").write_text(json.dumps({"tolerant": False, "sample_only": False}))
    (d / "R2_replay.sha256").write_text("ab  R2_BTC-USD.bin\ncd  R2_window.json\n")
    return d


@pytest.mark.parametrize(
    ("where", "key", "value", "expect"),
    [
        ("options", "sample_only", True, "--sample-only"),
        ("options", "tolerant", True, "--tolerant"),
        ("options", "after", "2026-11-20T00:00:00.000000Z", "--after"),
        ("options", "until", "2026-11-20T00:00:00.000000Z", "--until"),
        ("options", "min_hours", 3.0, "--min-hours"),
        ("options", "max_hours", 8.0, "--max-hours"),
        ("meta", "sample_only", True, "sample-only build"),
        ("meta", "tolerant", True, "tolerant build"),
        ("nolist", None, None, "not listed in R2_replay.sha256"),
        ("nooptions", None, None, "no options block"),
    ],
)
def test_inputs_check_refuses_each_planted_option(
    tmp_path: Path, where: str, key: str | None, value: Any, expect: str
) -> None:
    d = _clean_inputs(tmp_path / "r2")
    assert r2_meta.input_problems(d) == []
    w = json.loads((d / "R2_window.json").read_text())
    if where == "options":
        w["options"][key] = value
    elif where == "nooptions":
        del w["options"]
    elif where == "meta":
        meta = {"tolerant": False, "sample_only": False, str(key): value}
        (d / "R2_ETH-USD.meta.json").write_text(json.dumps(meta))
    else:
        (d / "R2_replay.sha256").write_text("ab  R2_BTC-USD.bin\n")
    (d / "R2_window.json").write_text(json.dumps(w))
    bad = r2_meta.input_problems(d)
    assert any(expect in b for b in bad), bad
    assert r2_meta.main(["inputs", str(d)]) == 1


def _sample_build(tmp_path: Path) -> Path:
    tools_mod = _tools()
    data = tools_mod.make_data(tmp_path / "kraken")
    out = tmp_path / "r2"
    argv = [
        "auto",
        str(data),
        str(out),
        "--after",
        _stamp(tools_mod.T0 - timedelta(seconds=20)),
        "--min-hours",
        "0.0005",
        "--max-hours",
        "1",
        "--sample-only",
    ]
    assert build_r2.main(argv) == 0
    w = json.loads((out / "R2_window.json").read_text())
    assert w["options"]["argv"] == argv
    return out


def test_a_real_sample_build_stamps_its_options_and_is_refused(tmp_path: Path) -> None:
    out = _sample_build(tmp_path)
    w = json.loads((out / "R2_window.json").read_text())
    assert w["options"]["sample_only"] is True and w["options"]["min_hours"] == 0.0005
    assert "  R2_window.json\n" in (out / "R2_replay.sha256").read_text()
    bad = r2_meta.input_problems(out)
    assert {
        "built with --sample-only",
        "built with --min-hours 0.0005",
        "built with --max-hours 1.0",
    } <= set(bad)
    assert any(b.startswith("built with --after") for b in bad)


def _git_bash() -> str | None:
    import shutil

    b = shutil.which("bash")
    if b is None or (os.name == "nt" and "git" not in b.lower()):
        return None  # never WSL's bash.exe (lane rule: no WSL from tests)
    return b


@pytest.mark.skipif(_git_bash() is None, reason="needs a POSIX bash (Git Bash on Windows)")
def test_run_r2_refuses_a_sample_build_before_correctness_or_timing(tmp_path: Path) -> None:
    import subprocess

    out = _sample_build(tmp_path)
    bash = _git_bash()
    assert bash is not None
    res = tmp_path / "res"
    env = {**os.environ, "R2DIR": out.as_posix(), "OUT": res.as_posix(), "SMOKE": "0"}
    for mode in ("correct", "time"):
        p = subprocess.run(
            [bash, (H9 / "run_r2.sh").as_posix(), mode],
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert p.returncode == 3, p.stdout + p.stderr
        assert "built with --sample-only" in p.stderr and "REFUSED" in p.stderr
    assert not (res / "correct" / "R2_correctness.ok").exists()
    assert not (res / "timing").exists()
