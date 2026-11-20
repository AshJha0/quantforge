"""Tests for the crypto L2 recorder's file handling and the tolerant reader (2026-11-18). Run: python -I -m pytest
tools/recorder/test_crypto_recorder.py, or python -I tools/recorder/test_crypto_recorder.py."""
import gzip
import sys
import tempfile
import unittest
import zlib
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import crypto_l2  # noqa: E402
import read_gz  # noqa: E402


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


def member(lines, flush_only=False):
    """A gzip member; flush_only=True leaves it without a trailer, as a hard kill after a sync flush does."""
    c = zlib.compressobj(6, zlib.DEFLATED, 31)
    body = c.compress("".join(l + "\n" for l in lines).encode())
    return body + (c.flush(zlib.Z_SYNC_FLUSH) if flush_only else c.flush())


class ReaderTests(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())

    def put(self, data):
        p = self.d / "f.jsonl.gz"
        p.write_bytes(data)
        return p

    def test_clean_multi_member(self):
        lines, r = read_gz.read_lines(self.put(member(["a", "b"]) + member(["c"])))
        self.assertEqual(lines, ["a", "b", "c"])
        self.assertEqual((r["members"], r["broken"], r["bytes_lost"]), (2, 0, 0))

    def test_truncated_member_then_appended_member(self):
        """The 2026-11-17/18 failure: killed mid-member, restart appended a new member."""
        a = member([f"x{i}" for i in range(500)], flush_only=True)
        cut = a + b"\xff" * 40  # bytes written after the last flush but never completed
        lines, r = read_gz.read_lines(self.put(cut + member(["after"])))
        self.assertEqual(lines[:500], [f"x{i}" for i in range(500)])
        self.assertEqual(lines[-1], "after")
        self.assertEqual(r["broken"], 1)
        self.assertGreater(r["bytes_lost"], 0)
        self.assertEqual(r["members"], 2)

    def test_mid_line_truncation_drops_partial_line(self):
        full = member(["one"], flush_only=True) + member(["two-long-line" * 50])[10:]  # second part: no header
        lines, r = read_gz.read_lines(self.put(full[: len(full) - 30]))
        self.assertEqual(lines[0], "one")
        self.assertTrue(all(l in ("one", "two-long-line" * 50) for l in lines))
        self.assertEqual(r["broken"], 1)

    def test_stdlib_gzip_fails_where_reader_recovers(self):
        p = self.put(member(["a"], flush_only=True) + member(["b"]))
        with self.assertRaises(Exception):
            with gzip.open(p, "rt") as f:
                f.read()
        self.assertEqual(read_gz.read_lines(p)[0], ["a", "b"])


class SinkTests(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.clock = Clock(datetime(2026, 11, 18, 15, 59, 59, tzinfo=timezone.utc))

    def test_hourly_rotation_and_clean_close(self):
        s = crypto_l2.Sink(self.d, "BTC/USD", clock=self.clock)
        s.write({"k": "book"})
        self.clock.t = datetime(2026, 11, 18, 16, 0, 0, tzinfo=timezone.utc)
        s.write({"k": "book"})
        s.close()
        files = sorted(p.name for p in (self.d / "BTC-USD").iterdir())
        self.assertEqual(files, ["20261118T15.jsonl.gz", "20261118T16.jsonl.gz"])
        for f in files:  # each a single intact member readable by the standard library
            with gzip.open(self.d / "BTC-USD" / f, "rt") as fh:
                self.assertEqual(len(fh.read().splitlines()), 1)

    def test_restart_never_appends(self):
        for _ in range(3):
            s = crypto_l2.Sink(self.d, "BTC/USD", clock=self.clock)
            s.write({"k": "book"})
            s.close()
        files = sorted(p.name for p in (self.d / "BTC-USD").iterdir())
        self.assertEqual(files, ["20261118T15-1.jsonl.gz", "20261118T15-2.jsonl.gz", "20261118T15.jsonl.gz"])

    def test_flush_makes_data_readable_before_close(self):
        s = crypto_l2.Sink(self.d, "BTC/USD", clock=self.clock)
        for i in range(100):
            s.write({"k": "book", "i": i})
        s.flush()
        lines, r = read_gz.read_lines(s.path)  # file still open: no trailer yet
        self.assertEqual(len(lines), 100)
        self.assertEqual(r["broken"], 1)
        s.close()
        lines, r = read_gz.read_lines(s.path)
        self.assertEqual((len(lines), r["broken"], r["bytes_lost"]), (100, 0, 0))

    def test_heartbeat(self):
        hb = self.d / "heartbeat.json"
        crypto_l2.write_heartbeat(hb, {"stopped": True})
        import json
        rec = json.loads(hb.read_text())
        self.assertTrue(rec["stopped"])
        self.assertIn("epoch", rec)


if __name__ == "__main__":
    unittest.main()
