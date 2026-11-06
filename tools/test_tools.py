#!/usr/bin/env python3
"""Tests for the recorder and forward log: python tools/test_tools.py"""
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("forward_log", ROOT / "tools/forward-log/forward_log.py")
fl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fl)
RECORD = ROOT / "tools/recorder/record.py"


class ForwardLog(unittest.TestCase):
    def test_chain_and_canon_match_golden_store_cases(self):
        cases = json.loads((ROOT / "datasets/golden/core/store.json").read_text(encoding="utf-8"))["cases"]
        c = next(x for x in cases if x["operation"] == "core.store.chain" and x["inputs"]["records"])
        h = fl.ZERO
        for r, want in zip(c["inputs"]["records"], c["expected"]["outputs"]["hashes"]):
            h = fl.link(h, r)
            self.assertEqual(h, want)

    def test_append_verify_and_tamper(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "log.jsonl"
            fl.append(p, "a", "2026-01-01T00:00:00Z", 1.5)
            fl.append(p, "a", "2026-01-02T00:00:00Z", {"x": None})
            self.assertEqual(fl.verify(p)[0], 2)
            lines = p.read_text(encoding="utf-8").splitlines()
            p.write_text(lines[0].replace("1.5", "1.6") + "\n" + lines[1] + "\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                fl.verify(p)
            with self.assertRaises(ValueError):
                fl.append(p, "a", "2026-01-03T00:00:00Z", 2)

    def test_deleted_line_is_caught(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "log.jsonl"
            for i in range(3):
                fl.append(p, "a", "2026-01-01T00:00:00Z", i)
            lines = p.read_text(encoding="utf-8").splitlines()
            p.write_text(lines[0] + "\n" + lines[2] + "\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                fl.verify(p)


class Recorder(unittest.TestCase):
    def run_with(self, d, sources):
        cfg = Path(d) / "s.json"
        cfg.write_text(json.dumps({"sources": sources}))
        log = Path(d) / "log.jsonl"
        p = subprocess.run([sys.executable, str(RECORD), "--sources", str(cfg), "--data", str(Path(d) / "data"), "--log", str(log)], capture_output=True, text=True)
        return p, log

    def source(self, url, **kw):
        return {"id": "t", "url": url, "licence": "x", "licence_url": "x", "terms_checked": "x", "attribution": "x", "redistribute_raw": "no", "enabled": True, **kw}

    def test_records_hash_not_data(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "in.txt"
            src.write_text("secret-quote")
            p, log = self.run_with(d, [self.source(src.as_uri())])
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertEqual(fl.verify(log)[0], 1)
            text = log.read_text(encoding="utf-8")
            self.assertNotIn("secret-quote", text)
            self.assertEqual(len(list((Path(d) / "data/t").iterdir())), 1)

    def test_failure_is_logged_and_exit_is_1(self):
        with tempfile.TemporaryDirectory() as d:
            p, log = self.run_with(d, [self.source((Path(d) / "absent").as_uri())])
            self.assertEqual(p.returncode, 1)
            self.assertIn("recording_failed", log.read_text(encoding="utf-8"))

    def test_source_without_licence_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            s = self.source("file:///x")
            del s["licence"]
            p, _ = self.run_with(d, [s])
            self.assertNotEqual(p.returncode, 0)

    def test_disabled_source_is_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            p, log = self.run_with(d, [self.source("file:///x", enabled=False)])
            self.assertEqual(p.returncode, 0)
            self.assertFalse(log.exists())


if __name__ == "__main__":
    unittest.main()
