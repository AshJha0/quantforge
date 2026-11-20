#!/usr/bin/env python3
"""Tests for the end-of-day rehearsal (plan item K-6):

  uv run --project python python tools/eod/test_rehearse.py

A synthetic recorded day passes all eight steps; each planted fault fails its own step, the steps before it pass
and the steps after it are recorded as not run (plan 14.10 rule 1). No network, no ledger branch, no market data:
the synthetic values are invented from a hash of the date."""

import datetime as dt
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("eod_rehearse", HERE / "rehearse.py")
assert spec is not None and spec.loader is not None
rh = importlib.util.module_from_spec(spec)
sys.modules["eod_rehearse"] = rh
spec.loader.exec_module(rh)
HAVE_LIBRARY = importlib.util.find_spec("quantforge_core") is not None
DATE = dt.date(2026, 11, 19)
STEPS = ["E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8"]


@unittest.skipUnless(HAVE_LIBRARY, "needs quantforge_core: run with uv run --project python")
class Rehearsal(unittest.TestCase):
    def run_one(self, plant=None):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "eod.json"
            doc = rh.run(DATE, "synthetic", plant, out, host="test")
            self.assertEqual(json.loads(out.read_text(encoding="utf-8")), doc)
        return doc

    def test_synthetic_day_passes_all_eight(self):
        doc = self.run_one()
        self.assertEqual([s["step"] for s in doc["steps"]], STEPS)
        self.assertEqual([s["status"] for s in doc["steps"]], ["pass"] * 8, doc["steps"])
        self.assertEqual((doc["result"], doc["failed_step"], doc["source"]), ("pass", "", "synthetic"))
        self.assertEqual(doc["data_label"], rh.SYNTHETIC_LABEL)
        self.assertTrue(doc["inputs_sha256"] and doc["outputs_sha256"])
        self.assertTrue(all(len(h) == 64 for h in {**doc["inputs_sha256"], **doc["outputs_sha256"]}.values()))

    def test_each_planted_fault_fails_its_step_and_stops_the_run(self):
        for plant, step in rh.FAULTS.items():
            with self.subTest(plant=plant):
                doc = self.run_one(plant)
                k = STEPS.index(step)
                status = [s["status"] for s in doc["steps"]]
                self.assertEqual(status, ["pass"] * k + ["fail"] + ["not run"] * (7 - k), doc["steps"][k])
                self.assertEqual((doc["result"], doc["failed_step"], doc["plant"]), ("fail", step, plant))
                self.assertIn("planted", doc["steps"][k]["evidence"])

    def test_planted_codes(self):
        want = {
            "GAP": "CHAIN",
            "HOLDOUT": "HOLDOUT",
            "HASH": "INPUT_HASH",
            "EXPLAIN": "EXPLAIN",
            "DOMAIN": "E_PARSE",
            "LABEL": "LABEL",
            "WIDTH": "WIDTH",
        }
        for plant, code in want.items():
            with self.subTest(plant=plant):
                doc = self.run_one(plant)
                self.assertEqual(doc["steps"][STEPS.index(rh.FAULTS[plant])]["reason"], code)

    def test_holdout_plant_does_not_write_the_window_date(self):
        doc = self.run_one("HOLDOUT")
        hi = rh.hs.windows()["R3-01"][1]
        self.assertNotIn(hi, json.dumps(doc))


class Pieces(unittest.TestCase):
    def test_markdown_table_and_code(self):
        out = rh.md_to_html("## T\n\n| a | b |\n|---|---|\n| `x` | **y** |\n\ntext <b>")
        self.assertIn("<h2>T</h2>", out)
        self.assertIn("<td><code>x</code></td><td><b>y</b></td>", out)
        self.assertIn("<p>text &lt;b&gt;</p>", out)

    def test_site_template_is_read_from_build_site(self):
        css, page = rh.site_template()
        self.assertIn("{body}", page)
        self.assertIn("prefers-color-scheme:dark", css)

    def test_synthetic_values_repeat(self):
        self.assertEqual(rh.synthetic_value(DATE, 10.0), rh.synthetic_value(DATE, 10.0))


if __name__ == "__main__":
    unittest.main()
