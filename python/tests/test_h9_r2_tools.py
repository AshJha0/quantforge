"""H-9 workload R2 tools (benchmarks/h9/build_r2.py and check_r2.py) on hand-built recorder files.

No recorded rows: every message below is synthetic. The fixture writes the recorder's file layout
(tools/recorder/crypto_l2.py) for both symbols: a first session cut by a gap row, then a second session with a
snapshot, updates (one sharing a per-second row's millisecond), a trade and per-second rows.
"""

import gzip
import importlib.util
import json
import struct
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from quantforge_core.order_book import rebuild

H9 = Path(__file__).resolve().parents[2] / "benchmarks" / "h9"


def _load(name: str) -> Any:
    sys.path.insert(0, str(H9))
    spec = importlib.util.spec_from_file_location(name, H9 / f"{name}.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


build_r2 = _load("build_r2")
check_r2 = _load("check_r2")

T0 = datetime(2026, 11, 19, 12, 0, 10, tzinfo=UTC)
DEC = {"BTC-USD": 1, "ETH-USD": 2}


def _stamp(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _px(v: float, sym: str) -> str:
    return f"{v:.{DEC[sym]}f}"


def _write(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as g:
        for r in rows:
            g.write(json.dumps(r, separators=(",", ":")) + "\n")


def _session(sym: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Raw messages and per-second rows of the second session (times relative to T0)."""

    def p(v: float) -> str:
        return _px(v, sym)

    msgs = [
        (
            0.0,
            "snapshot",
            [[p(100 - k), "1.0"] for k in range(12)],
            [[p(101), "1.0"], [p(102), "2.0"]],
        ),
        (0.5, "update", [[p(100), "3.0"]], []),
        (1.0, "update", [], [[p(101), "0"]]),  # shares the first per-second row's millisecond
        (2.5, "update", [[p(98), "1.5"]], []),
        (3.5, "update", [], [[p(103), "5E-7"]]),  # exponent form, as the recorder sometimes writes
    ]
    raw: list[dict[str, Any]] = []
    so_far: list[dict[str, Any]] = []
    books: list[dict[str, Any]] = []
    for dt, typ, b, a in msgs:
        so_far.append(
            {
                "type": typ,
                "bids": [[x, build_r2.fixed(y)] for x, y in b],
                "asks": [[x, build_r2.fixed(y)] for x, y in a],
                "checksum": None,
            }
        )
        res = rebuild(so_far, 100, DEC[sym], 8)
        books.append(res["book"])
        raw.append(
            {
                "t": _stamp(T0 + timedelta(seconds=dt)),
                "k": "msg",
                "type": typ,
                "bids": [{"price": x, "qty": y} for x, y in b],
                "asks": [{"price": x, "qty": y} for x, y in a],
                "checksum": res["crc32"],
                "ts": "x",
                "ok": True,
            }
        )
    per_second = [
        {
            "t": _stamp(T0 + timedelta(seconds=1.0)),
            "k": "book",
            **books[2],
            "ok": True,
        },  # after the tied message
        {
            "t": _stamp(T0 + timedelta(seconds=1.5)),
            "k": "trade",
            "d": [{"price": p(101), "qty": "0.5"}],
        },
        {"t": _stamp(T0 + timedelta(seconds=2.0)), "k": "book", **books[2], "ok": True},
        {"t": _stamp(T0 + timedelta(seconds=3.0)), "k": "book", **books[3], "ok": True},
    ]
    return raw, per_second


def make_data(root: Path, restart: bool = False) -> Path:
    for sym in ("BTC-USD", "ETH-USD"):
        raw, per_second = _session(sym)
        first: list[dict[str, Any]] = [
            {
                "t": _stamp(T0 - timedelta(seconds=9)),
                "k": "msg",
                "type": "snapshot",
                "bids": [{"price": _px(90, sym), "qty": "1"}],
                "asks": [{"price": _px(91, sym), "qty": "1"}],
                "checksum": 0,
                "ok": True,
            },
            {"t": _stamp(T0 - timedelta(seconds=8)), "k": "gap", "why": "test"},
        ]
        gap = [{"t": _stamp(T0 - timedelta(seconds=8)), "k": "gap", "why": "test"}]
        if restart and sym == "ETH-USD":  # a second snapshot with no gap row: a recorder restart
            raw.append({**raw[0], "t": _stamp(T0 + timedelta(seconds=3.6))})
        _write(root / f"{sym}-raw" / "20261119T12.jsonl.gz", first + raw)
        _write(root / sym / "20261119T12.jsonl.gz", gap + per_second)
    return root


def test_hour_files_keep_recording_order(tmp_path: Path) -> None:
    for name in ("20261119T12-1", "20261119T12", "20261119T12-2", "20261119T13", "20261119T12-x"):
        _write(tmp_path / f"{name}.jsonl.gz", [])
    got = [f.name for f in build_r2.hour_files(tmp_path, T0, T0 + timedelta(hours=2))]
    assert got == [
        "20261119T12.jsonl.gz",
        "20261119T12-1.jsonl.gz",
        "20261119T12-2.jsonl.gz",
        "20261119T13.jsonl.gz",
    ]


def test_window_rule_skips_a_session_cut_by_a_gap(tmp_path: Path) -> None:
    data = make_data(tmp_path / "kraken")
    after = T0 - timedelta(seconds=20)
    start, end, log = build_r2.choose_window(data, after, min_hours=0.0005, max_hours=0.0008)
    assert log["attempts"][0]["rejected"].startswith("gap row before hour")
    assert start == T0
    assert end == T0 + timedelta(
        hours=0.0008
    )  # 2.88 s: START + max_hours comes before the end of the data
    start, end, _ = build_r2.choose_window(data, after, min_hours=0.0005, max_hours=1.0)
    # The recording ends first: just after the last row that every stream has (the per-second rows end at 3.0 s).
    assert end == T0 + timedelta(seconds=3.0, milliseconds=1)
    none, _, log = build_r2.choose_window(data, after, min_hours=1.0, max_hours=2.0)
    assert none is None and log["result"] == "no session qualifies"


def test_window_rule_treats_a_restart_as_a_gap(tmp_path: Path) -> None:
    data = make_data(tmp_path / "kraken", restart=True)
    gaps, snaps, _, _ = build_r2.scan(data, T0 - timedelta(seconds=20))
    why = [g[2] for g in gaps if g[1] == "ETH-USD-raw"]
    assert "snapshot without a gap row (recorder restart)" in why
    assert len(snaps["ETH-USD"]) == 3


def test_build_writes_the_harness_files(tmp_path: Path) -> None:
    data = make_data(tmp_path / "kraken")
    out = tmp_path / "out"
    out.mkdir()
    end = T0 + timedelta(seconds=3.5, milliseconds=1)
    meta = build_r2.build(data, "BTC-USD", T0, end, str(out / "R2_BTC-USD"))
    assert meta["snapshots"] == 1 and meta["updates"] == 4 and meta["trade_fills"] == 1
    assert meta["messages"] == 6 and meta["checkpoints"] == 3
    assert meta["warmup_messages"] == 6  # the window is shorter than the one-hour warm-up
    b = (out / "R2_BTC-USD.bin").read_bytes()
    assert b[:8] == b"QFH9S001"
    nm, nl = struct.unpack_from("<QQ", b, 8)
    assert (nm, nl) == (6, 14 + 1 + 1 + 1 + 1 + 1)
    recs = [struct.unpack_from("<BBHHHII", b, 24 + 16 * k) for k in range(nm)]
    assert [r[0] for r in recs] == [
        0,
        1,
        1,
        3,
        1,
        1,
    ]  # the trade at 1.5 s sits between the updates at 1.0 and 2.5
    assert all(r[1] == build_r2.FLAG_VENUE_CHECKSUM for r in recs if r[0] != 3)
    assert recs[3][1] == 0
    lv = struct.unpack_from("<" + "q" * (2 * nl), b, 24 + 16 * nm)
    assert lv[:4] == (1000, 100_000_000, 990, 100_000_000)  # ticks at 1 decimal, lots at 8
    assert lv[-2:] == (1030, 50)  # "5E-7" read exactly
    c = (out / "R2_BTC-USD.cps.bin").read_bytes()
    n, _ = struct.unpack_from("<QQ", c, 8)
    cps = [struct.unpack_from("<IHHII", c, 24 + 16 * k) for k in range(n)]
    # Row at 1.000 s shares message 2's millisecond: lo = 1, hi = 2. Row at 2.0: book message 2 (the trade, bin
    # message 3, does not move a row). Row at 3.0: message 4.
    assert [(r[0], r[4]) for r in cps] == [(1, 2), (2, 2), (4, 4)]
    assert meta["rows_tied_with_a_message_ms"] == 1
    for f in (
        "R2_BTC-USD.msgs.jsonl",
        "R2_BTC-USD.rows.jsonl",
        "L7_BTC-USD.bin",
        "L7_BTC-USD.msgs.jsonl",
    ):
        assert f in meta["outputs_sha256"]
        assert (out / f).exists()
    assert len(meta["inputs_sha256"]) == 2


def test_build_refuses_a_gap_or_a_window_not_starting_at_a_snapshot(tmp_path: Path) -> None:
    data = make_data(tmp_path / "kraken")
    out = str(tmp_path / "R2")
    with pytest.raises(SystemExit, match="gap row inside the window"):
        build_r2.build(data, "BTC-USD", T0 - timedelta(seconds=9), T0 + timedelta(seconds=3), out)
    with pytest.raises(SystemExit, match="not a snapshot"):
        build_r2.build(data, "BTC-USD", T0 + timedelta(seconds=0.2), T0 + timedelta(seconds=3), out)


def test_auto_writes_both_symbols_and_the_hash_files(tmp_path: Path) -> None:
    data = make_data(tmp_path / "kraken")
    out = tmp_path / "out"
    rc = build_r2.main(
        [
            "auto",
            str(data),
            str(out),
            "--after",
            _stamp(T0 - timedelta(seconds=20)),
            "--min-hours",
            "0.0005",
            "--max-hours",
            "1",
        ]
    )
    assert rc == 0
    replay = (out / "R2_replay.sha256").read_text().splitlines()
    assert any(line.endswith("  R2_ETH-USD.bin") for line in replay)
    assert any(line.endswith("  L7_BTC-USD.bin") for line in replay)
    assert len((out / "R2_inputs.sha256").read_text().splitlines()) == 4
    assert (
        build_r2.main(
            ["window", str(data), "--after", _stamp(T0 - timedelta(seconds=20)), "--min-hours", "5"]
        )
        == 3
    )


@pytest.mark.parametrize("chunk", [1, 2, 100])
def test_check_r2_passes_on_a_consistent_window(tmp_path: Path, chunk: int) -> None:
    data = make_data(tmp_path / "kraken")
    out = tmp_path / "out"
    out.mkdir()
    build_r2.build(data, "ETH-USD", T0, T0 + timedelta(seconds=4), str(out / "R2_ETH-USD"))
    res = check_r2.check(str(out / "R2_ETH-USD"), chunk=chunk)
    assert res["checksum_checked"] == 5 and res["checksum_failed"] == 0
    assert res["checkpoint_checked"] == 3
    assert res["checkpoint_failed_top10"] == 0 and res["checkpoint_failed_below10"] == 0
    assert res["checkpoint_rows_with_tie"] == 1
    assert res["checkpoint_matched_only_inside_tie"] == 0
    assert res["checkpoint_matched_at_hi"] == 3 and res["checkpoint_matched_at_lo"] == 2
    assert res["chunk_start_mismatches"] == 0


def test_check_r2_tells_top10_from_below10_failures(tmp_path: Path) -> None:
    data = make_data(tmp_path / "kraken")
    out = tmp_path / "out"
    out.mkdir()
    prefix = str(out / "R2_BTC-USD")
    build_r2.build(data, "BTC-USD", T0, T0 + timedelta(seconds=4), prefix)
    rows = [json.loads(x) for x in Path(prefix + ".rows.jsonl").read_text().splitlines()]
    # Row 3: a change at level 12 is below the top 10; row 1: a change at the touch.
    rows[2]["bids"][11][1] = "7.00000000"
    rows[0]["asks"][0][1] = "9.00000000"
    Path(prefix + ".rows.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    res = check_r2.check(prefix, chunk=2)
    assert res["checkpoint_failed_top10"] == 1
    assert res["checkpoint_failed_below10"] == 1
    assert check_r2.main([prefix, "--out", str(out / "res.json")]) == 1
    msgs = [json.loads(x) for x in Path(prefix + ".msgs.jsonl").read_text().splitlines()]
    msgs[1]["checksum"] ^= 1
    Path(prefix + ".msgs.jsonl").write_text("".join(json.dumps(m) + "\n" for m in msgs))
    assert check_r2.check(prefix)["checksum_failed"] == 1
