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
        return {"id": "t", "url": url, "licence": "x", "licence_url": "x", "terms_checked": "x", "attribution": "x", "redistribute_raw": "no", "notice": "keep me", "enabled": True, **kw}

    def test_records_hash_not_data(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "in.txt"
            src.write_text("secret-quote")
            p, log = self.run_with(d, [self.source(src.as_uri())])
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertEqual(fl.verify(log)[0], 1)
            text = log.read_text(encoding="utf-8")
            self.assertNotIn("secret-quote", text)
            self.assertEqual(len(list((Path(d) / "data/t").glob("*.raw"))), 1)
            self.assertEqual((Path(d) / "data/t/NOTICE.txt").read_text(encoding="utf-8"), "keep me\n")

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

    def test_shipped_manifest_is_complete(self):
        sources = json.loads((ROOT / "tools/recorder/sources.json").read_text(encoding="utf-8"))["sources"]
        for s in sources:
            for k in ("licence", "licence_url", "terms_checked", "attribution", "redistribute_raw", "notice"):
                self.assertTrue(s[k], (s["id"], k))
            self.assertNotIn("stlouisfed", s["url"])
            for banned in ("nasdaq", "lobster", "api.bls.gov", "api_key", "apikey"):
                self.assertNotIn(banned, s["url"].lower(), s["id"])
            self.assertTrue(s["url"].startswith("https://"), s["id"])

    def test_stage_d_sources_are_rechecked_and_wired(self):
        sources = {s["id"]: s for s in json.loads((ROOT / "tools/recorder/sources.json").read_text(encoding="utf-8"))["sources"]}
        for sid in ("nyfed-tgcr", "nyfed-bgcr", "ons-d7bt", "ons-l522", "ons-chaw", "ecb-aaa-yield-curve", "eurostat-hicp",
                    "cftc-cot-disaggregated", "eia-ng-bulk"):
            s = sources[sid]
            self.assertTrue(s["enabled"], sid)
            self.assertTrue(s["terms_checked"].startswith("2026-11-07"), sid)
            self.assertIn("held back from git", s["redistribute_raw"], sid)
        self.assertIn("TGCR data", sources["nyfed-tgcr"]["notice"])
        self.assertNotIn("SOFR", sources["nyfed-bgcr"]["notice"])
        self.assertNotIn("bankofengland.co.uk/-/media", json.dumps(sources))  # BoE curve zips: third-party inputs, not cleared

    def test_disabled_source_is_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            p, log = self.run_with(d, [self.source("file:///x", enabled=False)])
            self.assertEqual(p.returncode, 0)
            self.assertFalse(log.exists())


class GalleryVol(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sp = importlib.util.spec_from_file_location("build_gallery", ROOT / "tools/build_gallery.py")
        cls.bg = importlib.util.module_from_spec(sp)
        sp.loader.exec_module(cls.bg)

    def test_smile_renders_only_given_numbers(self):
        svg = self.bg.smile_chart("t", [{"name": "1y", "strikes": [90, 100, 110], "vols": [0.31, 0.25, 0.22]}], "c")
        self.assertIn("<polyline", svg)
        self.assertIn("</svg>", svg)

    def test_smile_refuses_empty_or_ragged(self):
        with self.assertRaises(ValueError):
            self.bg.smile_chart("t", [], "c")
        with self.assertRaises(ValueError):
            self.bg.smile_chart("t", [{"name": "x", "strikes": [1, 2], "vols": [0.2]}], "c")

    def test_surface_grid(self):
        svg = self.bg.surface_svg("t", [90, 100], ["3m", "1y"], [[0.3, 0.25], [0.28, 0.24]], "c")
        self.assertEqual(svg.count("<rect"), 4)
        with self.assertRaises(ValueError):
            self.bg.surface_svg("t", [90, 100], ["3m"], [[0.3]], "c")

    def test_stage_c_moved_from_planned_to_pages(self):
        planned = {n for n, _ in self.bg.PLANNED}
        for n in ("Implied volatility smile", "Implied volatility surface"):
            self.assertNotIn(n, planned)
        self.assertEqual(set(self.bg.VOLS), {"equity-forward", "svi-smile", "ssvi-surface", "sabr"})

    def test_stage_c_pages_have_every_section_and_label(self):
        out = ROOT / "docs/curves"
        for slug, spec in self.bg.VOLS.items():
            text = (out / f"{slug}.md").read_text(encoding="utf-8")
            for head in ("Implemented, not Validated", "## What it is", "## Inputs", "## Command", "## Charts", "## Numbers",
                         "## Four-language agreement", "## Oracle evidence and limits", "Limits:", "Synthetic inputs, not market data."):
                self.assertIn(head, text, f"{slug}: {head}")
            self.assertIn("<svg", text)
            self.assertNotIn("nterview", text)
            for v in spec["examples"].values():
                self.assertTrue((ROOT / "examples" / v).is_file())

    def test_stage_c_data_matches_inputs_and_goldens(self):
        out = ROOT / "docs/curves/data"
        for slug, spec in self.bg.VOLS.items():
            d = json.loads((out / f"{slug}.json").read_text(encoding="utf-8"))
            for v in spec["examples"].values():
                self.assertEqual(d["meta"]["example_hashes"][v], self.bg.example_hash(v))
            self.assertEqual(d["evidence"], self.bg.golden_c(spec["golden"]))
            self.assertGreater(d["evidence"]["cases"], 0)
            for r in d["agreement"]:
                self.assertIsNotNone(r["largest_difference"], r["output"])

    def test_agreement_flatten_and_flags(self):
        self.assertEqual(self.bg.flatten({"a": [[1, 2], [3]], "b": True, "c": "x"}), [1.0, 2.0, 3.0])
        same = {"python": {"r": {"v": [1.0, 2.0], "ok": True}}}
        res = {lang: same["python"] for lang in self.bg.LANGS}
        rows = self.bg.vol_agreement({**res, "python": same["python"]})
        self.assertEqual([r["largest_difference"] for r in rows], [0.0, 0.0])
        res["java"] = {"r": {"v": [1.0, 2.5], "ok": False}}
        rows = self.bg.vol_agreement({**res, "python": same["python"]})
        self.assertEqual(rows[0]["largest_difference"], 0.5)
        self.assertIsNone(rows[1]["largest_difference"])

    def test_density_chart_has_a_zero_line_and_only_given_numbers(self):
        svg = self.bg.chart("t", "x", "y", [{"name": "d", "colour": 1, "shape": "line", "pts": [(1, -2.0), (2, 3.0)]}], "c", y_zero=True, x_lo=1)
        self.assertIn(">0<", svg)


    def test_stage_d_pages_are_live_from_real_runs(self):
        out = ROOT / "docs/curves"
        self.assertEqual(set(self.bg.STAGE_D), {"ois-full", "bond-fit", "repo", "cross-currency", "cds", "dividend-borrow",
                                                "inflation", "caps-swaptions", "commodities", "mbs"})
        index = (out / "README.md").read_text(encoding="utf-8")
        for slug, spec in self.bg.STAGE_D.items():
            self.assertTrue(self.bg.is_live(spec), slug)
            d = json.loads((out / "data" / f"{slug}.json").read_text(encoding="utf-8"))
            text = (out / f"{slug}.md").read_text(encoding="utf-8")
            for head in ("Implemented, not Validated", "## Four-language agreement", "## Oracle evidence and limits", self.bg.SYNTHETIC):
                self.assertIn(head, text, f"{slug}: {head}")
            self.assertNotIn("nterview", text)
            self.assertIn(f"]({slug}.md) | Implemented, not Validated | D |", index)
            self.assertEqual(set(d["reference"]), set(spec["examples"]))
            for op, f in spec["examples"].items():
                ex = json.loads((ROOT / "examples" / f).read_text(encoding="utf-8"))
                self.assertEqual(ex["operation"], op)
                real = spec.get("real", {})
                self.assertTrue(ex["case_id"].startswith("example-real-" if f in real else "example-synthetic-"), f)
                if f in real:
                    self.assertIn(real[f], text)
                    self.assertIn("fetched", real[f])
                self.assertEqual(d["meta"]["example_hashes"][f], self.bg.example_hash(f))
            self.assertEqual(d["evidence"], self.bg.golden_d(spec["examples"]))
            self.assertTrue(all(r["largest_difference"] is not None and r["largest_difference"] < 1e-6 for r in d["agreement"]), slug)
        planned = {n for n, _ in self.bg.PLANNED}
        for gone in ("Full SOFR", "ESTR", "Cross-currency", "Credit and ISDA CDS", "Swaption cube and cap surface"):
            self.assertNotIn(gone, planned)

    def test_planned_page_has_no_numbers(self):
        spec = {"title": "T", "shows": "Something.", "kind": "none"}
        text = self.bg.planned_page("x", spec)
        self.assertIn("Planned, stage D", text)
        self.assertNotIn("<svg", text)

    def test_stage_d_renderer_hook_routes_live_entries(self):
        bg = self.bg
        saved = dict(bg.STAGE_D["repo"])
        try:
            bg.STAGE_D["repo"]["kind"] = "repo-test"
            self.assertFalse(bg.is_live(bg.STAGE_D["repo"]))
            bg.renderer("repo-test")(lambda slug, spec, d: f"LIVE {slug} {d['x']}")
            self.assertTrue(bg.is_live(bg.STAGE_D["repo"]))
            data = {s: json.loads((ROOT / "docs/curves/data" / f"{s}.json").read_text(encoding="utf-8"))
                    for s in list(bg.CURVES) + list(bg.VOLS) + list(bg.STAGE_D)}
            self.assertEqual(bg.render_all({**data, "repo": {"x": 1, "evidence": {"cases": 1}}})["repo.md"], "LIVE repo 1")
            data.pop("repo")
            self.assertIn("planned", bg.render_all(data)["repo.md"].lower())  # live but no data: planned page
        finally:
            bg.STAGE_D["repo"].clear()
            bg.STAGE_D["repo"].update(saved)
            bg.RENDERERS.pop("repo-test", None)


if __name__ == "__main__":
    unittest.main()
