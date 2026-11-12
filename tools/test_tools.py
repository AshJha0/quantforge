#!/usr/bin/env python3
"""Tests for the recorder and forward log: python tools/test_tools.py"""
import hashlib
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
aspec = importlib.util.spec_from_file_location("anchor", ROOT / "tools/forward-log/anchor.py")
anchor = importlib.util.module_from_spec(aspec)
aspec.loader.exec_module(anchor)
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
        p = subprocess.run([sys.executable, str(RECORD), "--sources", str(cfg), "--studies", str(Path(d) / "no-studies.json"), "--data", str(Path(d) / "data"), "--log", str(log)], capture_output=True, text=True)
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
            if s["enabled"]:  # FRED's terms rule out storing its data: listed with the reading, never enabled
                self.assertNotIn("stlouisfed", s["url"])
            if "api.bls.gov" in s["url"]:
                self.assertIn("/publicAPI/v1/", s["url"])  # v2 needs registration
            for banned in ("nasdaq", "lobster", "api_key", "apikey", "registrationkey"):
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

    def test_stage_e_sources(self):
        sources = {s["id"]: s for s in json.loads((ROOT / "tools/recorder/sources.json").read_text(encoding="utf-8"))["sources"]}
        s = sources["fiscaldata-treasury-auctions"]
        self.assertTrue(s["enabled"])
        self.assertTrue(s["terms_checked"].startswith("2026-11-08"))
        self.assertIn("{year}", s["url"])
        self.assertNotIn("[", s["url"])  # brackets must be percent-encoded for urllib
        self.assertIn("held back from git", s["redistribute_raw"])
        # Not qualified for automated use (stage E survey): FRED scraping ban, Cboe and Deribit personal use only, DMO bot wall
        for banned in ("cboe.com", "deribit.com", "dmo.gov.uk", "treasurydirect.gov"):
            self.assertNotIn(banned, json.dumps(sources))

    def test_r3_sources_and_studies(self):
        sources = {s["id"]: s for s in json.loads((ROOT / "tools/recorder/sources.json").read_text(encoding="utf-8"))["sources"]}
        for sid in ("us-treasury-bill-rates", "us-treasury-real-yields", "bls-cpi-u-nsa"):
            self.assertTrue(sources[sid]["enabled"] and sources[sid]["parse"], sid)
            self.assertTrue(sources[sid]["terms_checked"].startswith("2026-11-09"), sid)
        for sid in ("fred-t5yie", "fred-t10yie"):
            self.assertFalse(sources[sid]["enabled"])
            self.assertIn("scraping", sources[sid]["terms_checked"])
        studies = json.loads((ROOT / "tools/recorder/studies.json").read_text(encoding="utf-8"))["studies"]
        self.assertEqual([s["id"] for s in studies], ["R3-01", "R3-02", "R3-03"])
        for st in studies:
            self.assertTrue((ROOT / st["prereg"]).exists())
            for i in st["inputs"]:
                self.assertTrue(sources[i]["enabled"], i)

    def test_parsed_values_revisions_study_rows_and_recheck(self):
        fx = ROOT / "tools/recorder/fixtures"
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            bill = d / "bill.csv"
            bill.write_bytes((fx / "treasury-bill-rates.csv").read_bytes())
            cfg = [self.source(bill.as_uri(), id="bill", parse={"format": "treasury_csv", "fields": ["13 WEEKS COUPON EQUIVALENT"]}),
                   self.source((fx / "treasury-real-yields.csv").as_uri(), id="real", parse={"format": "treasury_csv", "fields": ["5 YR", "10 YR"]}),
                   self.source((fx / "bls-cpi-v1.json").as_uri(), id="cpi", parse={"format": "bls_v1"})]
            (d / "s.json").write_text(json.dumps({"sources": cfg}))
            studies = d / "studies.json"
            studies.write_text(json.dumps({"studies": [{"id": "S1", "inputs": ["bill", "cpi"], "status": "no position", "start": "2026-01-01"}]}))
            log = d / "log.jsonl"

            def run():
                return subprocess.run([sys.executable, str(RECORD), "--sources", str(d / "s.json"), "--studies", str(studies),
                                       "--data", str(d / "data"), "--log", str(log)], capture_output=True, text=True)
            self.assertEqual(run().returncode, 0)
            # Treasury revises 2026-11-05 and adds nothing else: one revision row, one changed observation
            bill.write_bytes(bill.read_bytes().replace(b"11/05/2026,3.89,3.96,3.91,3.98,3.98,4.06,4.00,4.10",
                                                       b"11/05/2026,3.89,3.96,3.91,3.98,3.98,4.06,4.00,4.12"))
            self.assertEqual(run().returncode, 0)
            recs = [e["record"] for e in fl.read(log)]
            sha = hashlib.sha256((d / "s.json").read_bytes()).hexdigest()
            self.assertTrue(all(r["value"]["payload"]["sources_sha256"] == sha for r in recs))
            pay = lambda sid: [r["value"]["payload"] for r in recs if r["series_id"] == sid]
            bills = pay("recorder/bill")
            self.assertEqual(bills[0]["observations"]["2026-11-06|13 WEEKS COUPON EQUIVALENT"], 4.11)
            self.assertEqual(len(bills[0]["observations"]), 3)
            self.assertEqual(bills[1]["observations"], {"2026-11-05|13 WEEKS COUPON EQUIVALENT": 4.12})
            self.assertEqual([(v["old"], v["new"]) for v in pay("revision/bill")], [(4.10, 4.12)])
            cpi = pay("recorder/cpi")
            self.assertEqual(cpi[0]["observations"]["2026-09|CUUR0000SA0"], 336.94)
            self.assertEqual(cpi[1]["observations"], {})
            self.assertEqual(len(pay("recorder/real")), 2)
            study = pay("study/S1")
            self.assertEqual(len(study), 2)
            self.assertIsNone(study[0]["position"])
            self.assertEqual(study[1]["inputs"]["bill"], bills[1]["state_sha256"])
            gap = ROOT / "tools/recorder/gap_monitor.py"
            r = subprocess.run([sys.executable, str(gap), "recheck", "--log", str(log)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout)
            self.assertIn("6 parsed rows rechecked, 0 mismatched", r.stdout)
            # A kept value edited afterwards fails the recheck even with the hash chain rebuilt around it
            bad = d / "bad.jsonl"
            for e in fl.read(log):
                rec = e["record"]
                if rec["sequence"] == 1:
                    rec["value"]["payload"]["observations"]["2026-11-06|13 WEEKS COUPON EQUIVALENT"] = 4.0
                fl.append(bad, rec["series_id"], rec["event_time"], rec["value"]["payload"], rec["knowledge_time"])
            r = subprocess.run([sys.executable, str(gap), "recheck", "--log", str(bad)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 1)

    def test_bad_feed_is_a_failure_row(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "x.csv"
            src.write_text("Date,Other\n")
            p, log = self.run_with(d, [self.source(src.as_uri(), parse={"format": "treasury_csv", "fields": ["5 YR"]})])
            self.assertEqual(p.returncode, 1)
            self.assertIn("recording_failed", log.read_text(encoding="utf-8"))

    def test_disabled_source_is_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            p, log = self.run_with(d, [self.source("file:///x", enabled=False)])
            self.assertEqual(p.returncode, 0)
            self.assertFalse(log.exists())


class RecorderRetry(unittest.TestCase):
    """fetch retries transient HTTP errors (the ECB data API returned 504 twice on 2026-11-10)."""

    def setUp(self):
        import urllib.error
        import urllib.request
        self.err = urllib.error
        rspec = importlib.util.spec_from_file_location("record_retry", RECORD)
        self.rec = importlib.util.module_from_spec(rspec)
        rspec.loader.exec_module(self.rec)
        self.orig = urllib.request.urlopen
        self.addCleanup(setattr, urllib.request, "urlopen", self.orig)
        self.req = urllib.request

    def _script(self, outcomes):
        calls = []

        class Resp:
            def __init__(self, body): self.body = body
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self): return self.body

        def fake(req, timeout):
            calls.append(timeout)
            o = outcomes[len(calls) - 1]
            if isinstance(o, Exception):
                raise o
            return Resp(o)
        self.req.urlopen = fake
        return calls

    def http(self, code):
        return self.err.HTTPError("https://x", code, "err", {}, None)

    def test_retries_504_then_succeeds(self):
        calls = self._script([self.http(504), self.http(504), b"ok"])
        waits = []
        self.assertEqual(self.rec.fetch("https://x", 5, sleep=waits.append), b"ok")
        self.assertEqual(len(calls), 3)
        self.assertEqual(waits, [15.0, 30.0])

    def test_gives_up_after_last_attempt(self):
        self._script([self.http(504)] * 4)
        with self.assertRaises(self.err.HTTPError):
            self.rec.fetch("https://x", 5, sleep=lambda s: None)

    def test_does_not_retry_client_error(self):
        calls = self._script([self.http(404), b"never"])
        with self.assertRaises(self.err.HTTPError):
            self.rec.fetch("https://x", 5, sleep=lambda s: None)
        self.assertEqual(len(calls), 1)

    def test_retries_timeout(self):
        calls = self._script([TimeoutError("slow"), b"ok"])
        self.assertEqual(self.rec.fetch("https://x", 5, sleep=lambda s: None), b"ok")
        self.assertEqual(len(calls), 2)


class GapMonitor(unittest.TestCase):
    GAP = ROOT / "tools/recorder/gap_monitor.py"

    def write(self, path, days, sha="ab"):
        for d in days:
            fl.append(path, "recorder/x", f"{d}T23:30:00Z", {"kind": "recording", "sha256": sha, "bytes": 1})

    def run_gap(self, *args):
        return subprocess.run([sys.executable, str(self.GAP), *args], capture_output=True, text=True)

    def test_gap_found_and_holiday_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            log, hol = Path(d) / "a.jsonl", Path(d) / "h.txt"
            hol.write_text("2026-11-11\n", encoding="utf-8")
            self.write(log, ["2026-11-09", "2026-11-12"])  # Tue 10 missing, Wed 11 a holiday
            r = self.run_gap("gaps", "--log", str(log), "--holidays", str(hol), "--until", "2026-11-13", "--recent", "1")
            self.assertEqual(r.returncode, 1)  # Fri 13 is recent and missing
            self.assertIn("2026-11-10", r.stdout)
            self.assertNotIn("2026-11-11", r.stdout.split("Missing")[1].split("Recent")[0])
            r = self.run_gap("gaps", "--log", str(log), "--holidays", str(hol), "--until", "2026-11-12", "--recent", "1")
            self.assertEqual(r.returncode, 0)

    def test_prereg_inputs_and_study_rows_fail_on_any_missing_day(self):
        with tempfile.TemporaryDirectory() as d:
            log, studies = Path(d) / "a.jsonl", Path(d) / "s.json"
            studies.write_text(json.dumps({"studies": [{"id": "S1", "inputs": ["x"], "status": "-", "start": "2026-11-09"}]}))
            self.write(log, ["2026-11-09", "2026-11-10", "2026-11-11"])
            row = {"kind": "study_position", "position": None, "inputs": {"x": "ab"}}
            for day in ["2026-11-09", "2026-11-11"]:  # study row missing on Tue 10, an old day
                fl.append(log, "study/S1", f"{day}T23:30:00Z", row)
            r = self.run_gap("gaps", "--log", str(log), "--until", "2026-11-11", "--recent", "1", "--studies", str(studies))
            self.assertEqual(r.returncode, 1)
            self.assertIn("S1 study/S1 2026-11-10", r.stdout)
            r = self.run_gap("gaps", "--log", str(log), "--until", "2026-11-11", "--recent", "1")
            self.assertEqual(r.returncode, 0)  # without --studies only recent days count
            fl.append(log, "study/S1", "2026-11-10T23:30:00Z", row)
            r = self.run_gap("gaps", "--log", str(log), "--until", "2026-11-11", "--recent", "1", "--studies", str(studies))
            self.assertEqual(r.returncode, 0, r.stdout)
            studies.write_text(json.dumps({"studies": [{"id": "S1", "inputs": ["x", "never"], "status": "-", "start": "2026-11-09"}]}))
            r = self.run_gap("gaps", "--log", str(log), "--until", "2026-11-11", "--studies", str(studies))
            self.assertEqual(r.returncode, 1)
            self.assertIn("recorder/never 2026-11-09", r.stdout)

    def test_second_log_fills_gap_and_reconcile(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = Path(d) / "a.jsonl", Path(d) / "b.jsonl"
            self.write(a, ["2026-11-09"])
            self.write(b, ["2026-11-09", "2026-11-10"], sha="cd")
            r = self.run_gap("gaps", "--log", str(a), "--log", str(b), "--until", "2026-11-10")
            self.assertEqual(r.returncode, 0)
            r = self.run_gap("reconcile", "--log", str(a), "--log", str(b))
            self.assertIn("| recorder/x | 2026-11-09 | both | differ |", r.stdout)
            self.assertIn("| recorder/x | 2026-11-10 | second only | - |", r.stdout)


class Workflows(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(ROOT / "tools/workflows"))
        import sanity
        import sofr_check
        cls.sanity, cls.sofr = sanity, sofr_check

    class Sink:
        def __init__(self):
            self.checks = []

        def check(self, name, level, ok, detail):
            self.checks.append((name, level, ok))

    def failed(self, sink):
        return [n for n, lvl, ok in sink.checks if lvl == "fail" and not ok]

    def test_curve_bands_catch_a_unit_error(self):
        good = [{"date": "2027-11-08", "discount_factor": 0.96}, {"date": "2031-11-06", "discount_factor": 0.80}]
        s = self.Sink()
        self.sanity.check_curve(s, "c", "2026-11-06", good)
        self.assertEqual(self.failed(s), [])
        bad = [{"date": "2027-11-08", "discount_factor": 0.6}]  # a 4% rate read as 40%
        s = self.Sink()
        self.sanity.check_curve(s, "c", "2026-11-06", bad)
        self.assertIn("c zero rates in band", self.failed(s))

    def test_quote_and_fixing_bands(self):
        s = self.Sink()
        self.sanity.check_quotes(s, "q", [{"tenor": "1Y", "rate": 4.2}], [{"tenor": "1Y", "rate": 0.042}])
        self.assertIn("q quote levels", self.failed(s))
        s = self.Sink()
        self.sanity.check_fixings(s, "f", [("2026-11-05", 0.039), ("2026-11-06", 0.0392)], redact=True)
        self.assertEqual(self.failed(s), [])

    def test_sofr_window_weights_cover_the_calendar_days(self):
        fix = [("2026-10-02", 0.04), ("2026-10-05", 0.041), ("2026-10-06", 0.042)]
        c = self.sofr.window_case("x", "2026-10-07", 4, fix)  # starts Saturday 3 October: Friday's rate covers it
        self.assertEqual(c["operation"], "rates.ois.compound")
        self.assertEqual(c["inputs"]["rates"], [0.04, 0.041, 0.042])
        self.assertEqual(c["inputs"]["days"], [2, 1, 1])
        c = self.sofr.window_case("y", "2026-10-07", 2, fix)  # starts on a business day
        self.assertEqual(c["operation"], "rates.ois.compound_dated")


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
        planned = {row[0] for row in self.bg.PLANNED}
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
                                                "inflation", "caps-swaptions", "commodities", "mbs", "sector-rating", "funding"})
        index = (out / "README.md").read_text(encoding="utf-8")
        for slug, spec in self.bg.STAGE_D.items():
            self.assertTrue(self.bg.is_live(spec), slug)
            d = json.loads((out / "data" / f"{slug}.json").read_text(encoding="utf-8"))
            text = (out / f"{slug}.md").read_text(encoding="utf-8")
            for head in ("Implemented, not Validated", "## Four-language agreement", "## Oracle evidence and limits", self.bg.SYNTHETIC):
                self.assertIn(head, text, f"{slug}: {head}")
            self.assertNotIn("nterview", text)
            self.assertIn(f"]({slug}.md) | Implemented, not Validated | {spec.get('stage', 'D')} |", index)
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
            self.assertEqual(d["evidence"], self.bg.golden_d(spec["examples"], spec.get("golden", "stage_d")))
            self.assertTrue(all(r["largest_difference"] is not None and r["largest_difference"] < 1e-6 for r in d["agreement"]), slug)
        planned = {row[0] for row in self.bg.PLANNED}
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


def load(name, rel):
    sp = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(mod)
    return mod


class GalleryStageE(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bg = load("build_gallery_e", "tools/build_gallery.py")
        cls.ge = cls.bg.gallery_e

    def surface(self):
        return {"expiries": [0.25, 0.5, 1.0], "strikes": [80, 90, 100, 110, 120],
                "vols": [[0.3, 0.27, 0.25, 0.24, 0.245], [0.29, 0.265, 0.25, 0.242, 0.244], [0.28, 0.26, 0.25, 0.245, 0.246]]}

    def test_planned_pages_have_every_section_and_no_numbers(self):
        out = ROOT / "docs/curves"
        index = (out / "README.md").read_text(encoding="utf-8")
        self.assertEqual(set(self.ge.STAGE_E), {"vol-surface", "local-vol", "swaption-cube", "vol-term-structure"})
        self.assertEqual({k for k, v in self.ge.STAGE_E.items() if self.ge.is_live(v)}, set(self.ge.STAGE_E))
        for slug, spec in self.ge.STAGE_E.items():
            text = (out / f"{slug}.md").read_text(encoding="utf-8")
            for head in ("## What it is", "## Inputs", "## Command", "## Charts", "## Numbers",
                         "## Four-language agreement", "## Oracle evidence and limits", self.ge.SYNTHETIC):
                self.assertIn(head, text, f"{slug}: {head}")
            self.assertNotIn("nterview", text)
            if self.ge.is_live(spec):
                d = json.loads((out / "data" / f"{slug}.json").read_text(encoding="utf-8"))
                self.assertIn("Implemented, not Validated", text)
                self.assertIn("<svg", text)
                self.assertGreater(d["evidence"]["cases"], 0)
                self.assertTrue(all(r["largest_difference"] is not None and r["largest_difference"] < 1e-9 for r in d["agreement"]), slug)
                self.assertIn(f"]({slug}.md) | Implemented, not Validated | E |", index)
            else:
                self.assertIn("Status: Planned", text)
                self.assertNotIn("<svg", text)
                self.assertIn(f"]({slug}.md) | Planned | E |", index)

    def test_contract_accepts_good_and_names_the_broken_field(self):
        self.assertEqual(len(self.ge.check_contract("surface", self.surface())["vols"]), 3)
        bad = self.surface()
        bad["vols"][1] = bad["vols"][1][:-1]
        with self.assertRaisesRegex(ValueError, "per strike"):
            self.ge.check_contract("surface", bad)
        with self.assertRaisesRegex(ValueError, "atm_vols"):
            self.ge.check_contract("term", {"expiries": [1, 2], "atm_vols": [0.2]})
        with self.assertRaisesRegex(ValueError, "finite"):
            self.ge.check_contract("term", {"expiries": [1, float("nan")], "atm_vols": [0.2, 0.2]})
        cube = {"expiries": [1, 5], "tenors": [2, 10], "strikes": [-100, 0, 100], "vols": [[[0.01] * 3] * 2] * 2}
        self.assertEqual(self.ge.check_contract("cube", cube)["tenors"], [2.0, 10.0])
        with self.assertRaisesRegex(ValueError, "ATM"):
            self.ge.check_contract("cube", {**cube, "strikes": [-100, 50, 100]})

    def test_charts_fit_a_phone_and_follow_the_theme(self):
        import re
        ge = self.ge
        svgs = ge.charts("surface", ge.STAGE_E["vol-surface"], ge.check_contract("surface", self.surface()), "c")
        cube = {"expiries": [1, 2, 5], "tenors": [2, 10], "strikes": [-100, 0, 100], "vols": [[[0.01, 0.009, 0.011]] * 2] * 3}
        svgs += ge.charts("cube", ge.STAGE_E["swaption-cube"], ge.check_contract("cube", cube), "c")
        term = {"expiries": [0.5, 1, 2], "atm_vols": [0.2, 0.21, 0.22], "forward_vols": [0.2, 0.22, 0.23]}
        svgs += ge.charts("term", ge.STAGE_E["vol-term-structure"], ge.check_contract("term", term), "c")
        for svg in svgs:
            self.assertIn('viewBox="0 0 360 ', svg)  # 360 wide: about 12 px text at 375 px
            self.assertIsNone(re.search(r"#[0-9a-fA-F]{3,6}\b", svg))  # colours only from theme variables
            sizes = [int(x) for x in re.findall(r"font(?:-size)?:(\d+)px", svg)]
            self.assertTrue(sizes and min(sizes) >= 12, sizes)
        self.assertEqual(svgs[0].count("<rect"), 15 + 5)  # 15 cells plus the five-step key
        with self.assertRaises(ValueError):
            ge.heatmap("t", [1, 2], ["a"], [[1]], "x", "c")

    def test_label_thinning_keeps_ends(self):
        self.assertEqual(self.ge._thin(3), {0, 1, 2})
        shown = self.ge._thin(25)
        self.assertLessEqual(len(shown), 7)
        self.assertTrue({0, 24} <= shown)

    def test_live_route_renders_from_data(self):
        ge, bg = self.ge, self.bg
        spec = ge.STAGE_E["vol-surface"]
        saved, live = dict(spec), ge.is_live
        try:
            spec["cli"] = "vol.surface.grid"
            ge.is_live = lambda s: True
            op = next(iter(spec["examples"]))
            meta = {"date": "2026-11-08", "commit": "abc", "cli": {k: {"implementation_version": "0", "toolchain": "t"} for k in bg.LANGS}}
            pts = [{"expiry_years": t, "log_moneyness": k} for t in self.surface()["expiries"] for k in self.surface()["strikes"]]
            outs = {"implied_vol": [v for row in self.surface()["vols"] for v in row]}
            d = {"meta": meta, "inputs": {op: {"points": pts}}, "reference": {op: outs}, "agreement": [], "evidence": {"operations": [op], "cases": 0, "by_source": {}}}
            text = ge.page("vol-surface", spec, d, bg)
            for want in ("Implemented, not Validated", "<svg", "## Numbers", "examples/vol_dupire_grid_e.json"):
                self.assertIn(want, text)
        finally:
            ge.is_live = live
            spec.clear()
            spec.update(saved)


class QualityGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qg = load("quality_gate", "tools/quality_gate.py")
        cls.cfg = json.loads((ROOT / "conformance/quality/stage_e.json").read_text(encoding="utf-8"))

    def test_shipped_config_is_valid_and_matches_mutation_modules(self):
        bad, todo, _ = self.qg.check_config(self.cfg)
        self.assertEqual((bad, todo), ([], []))
        self.assertGreaterEqual(self.cfg["coverage_min"], 0.85)
        stages = json.loads((ROOT / "conformance/mutation/stages.json").read_text(encoding="utf-8"))
        self.assertEqual([m["module"] for m in stages["stages"]["E"]], [m["module"] for m in self.cfg["modules"]])

    def test_config_check_catches_bad_paths(self):
        cfg = {"modules": [{"module": "m", "python": "python/nowhere/*.py", "rust": "rust/Cargo.toml", "cpp": "TODO", "java": "TODO"}]}
        bad, todo, _ = self.qg.check_config(cfg)
        self.assertTrue(any("no file matches" in b for b in bad))
        self.assertTrue(any("workspace member" in b for b in bad))
        self.assertIn("m/cpp", todo)

    def test_readers_and_gate(self):
        qg = self.qg
        lcov = "SF:/home/r/quantforge/rust/crates/quantforge-core/src/heston.rs\nDA:1,1\nDA:2,0\nDA:3,4\nDA:4,2\nend_of_record\n"
        rows = qg.read_lcov(lcov)
        self.assertEqual(rows[0][1:], (3, 4))
        cfg = {"coverage_min": 0.85, "modules": [{"module": "heston", "rust": "rust/crates/*/src/heston.rs"}, {"module": "todo", "rust": "TODO"}]}
        out, fails = qg.gate(cfg, "rust", rows)
        self.assertEqual((fails, len(out)), (["heston"], 1))  # 75% is below 85%; the TODO entry is skipped
        py = json.dumps({"files": {"quantforge_core/heston.py": {"summary": {"covered_lines": 90, "num_statements": 100}}}})
        _, fails = qg.gate({"coverage_min": 0.85, "modules": [{"module": "h", "python": "python/quantforge_core/heston.py"}]},
                           "python", qg.read_coverage_py(py))
        self.assertEqual(fails, [])
        jac = '<report><package name="org/quantforge/vol"><sourcefile name="Heston.java"><counter type="LINE" missed="1" covered="9"/></sourcefile></package></report>'
        self.assertEqual(qg.read_jacoco(jac), [("java25/src/main/java/org/quantforge/vol/Heston.java", 9, 10)])
        cob = ('<coverage><packages><package><classes><class filename="cpp26/src/core/heston.cpp"><lines>'
               '<line number="1" hits="0"/><line number="2" hits="3"/></lines></class></classes></package></packages></coverage>')
        self.assertEqual(qg.read_cobertura(cob), [("cpp26/src/core/heston.cpp", 1, 2)])

    def test_missing_module_in_report_fails(self):
        _, fails = self.qg.gate({"coverage_min": 0.85, "modules": [{"module": "x", "cpp": "cpp26/src/core/x.cpp"}]}, "cpp", [])
        self.assertEqual(fails, ["x"])

    def test_language_floor(self):
        rows = [("quantforge_core/a.py", 80, 100), ("tests/test_a.py", 0, 50)]
        self.assertTrue(self.qg.floor_gate("python", rows, 0.80)[1])  # tests are not library lines
        self.assertFalse(self.qg.floor_gate("python", rows, 0.81)[1])
        self.assertFalse(self.qg.floor_gate("rust", rows, 0.5)[1])  # no rust library lines at all
        floors = json.loads((ROOT / "conformance/quality/floors.json").read_text(encoding="utf-8"))
        self.assertEqual(sorted(k for k in floors if not k.startswith("_")), ["cpp", "java", "python", "rust"])


class QualityGateFailPaths(unittest.TestCase):
    """Fail paths of tools/quality_gate.py on a synthetic tree, and its command line."""

    @classmethod
    def setUpClass(cls):
        cls.qg = load("quality_gate", "tools/quality_gate.py")

    def _tree(self, d):
        root = Path(d)
        for rel, text in {
            "rust/Cargo.toml": 'members = ["crates/core"]\n',
            "rust/crates/core/src/a.rs": "", "rust/crates/other/src/b.rs": "",
            "cpp26/CMakeLists.txt": "src/core/listed.cpp\n",
            "cpp26/src/core/listed.cpp": "", "cpp26/src/core/unlisted.cpp": "",
            "python/pyproject.toml": 'source_paths = ["quantforge_core/"]\ntests_dir = ["tests/test_a.py"]\n',
            "python/quantforge_core/x.py": "", "python/quantforge_extra/y.py": "", "python/other/z.py": "",
            "python/tests/test_b.py": "",
        }.items():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_text(text, encoding="utf-8")
        return root

    def test_config_check_reports_each_broken_path(self):
        with tempfile.TemporaryDirectory() as d:
            root = self._tree(d)
            cfg = {"modules": [{"module": "m", "rust": ["rust/crates/core/src/a.rs", "rust/crates/other/src/b.rs"],
                                "cpp": "cpp26/src/core/*.cpp",
                                "python": ["python/quantforge_core/x.py", "python/quantforge_extra/y.py", "python/other/z.py"],
                                "java": "TODO later"}],
                   "python_tests": ["python/tests/test_b.py", "python/tests/test_a.py", "TODO"]}
            bad, todo, warn = self.qg.check_config(cfg, root)
        self.assertEqual(sorted(bad), sorted([
            "m/rust: rust/crates/other/src/b.rs is not in a workspace member crate",
            "m/cpp: cpp26/src/core/unlisted.cpp is not listed in cpp26/CMakeLists.txt",
            "m/python: package quantforge_extra is not in mutmut source_paths",
            "m/python: python/other/z.py is outside the python/quantforge_* packages",
            "m/python: package other is not in mutmut source_paths",
            "python test python/tests/test_a.py does not exist"]))
        self.assertEqual(todo, ["m/java", "python_tests"])
        self.assertEqual(len(warn), 1)
        self.assertIn("test_b.py is not in mutmut tests_dir", warn[0])

    def test_filled_and_empty_lists(self):
        self.assertFalse(self.qg.filled([]))
        self.assertFalse(self.qg.filled(["a", "TODO"]))
        self.assertFalse(self.qg.filled("  "))
        self.assertTrue(self.qg.filled(["a", "b"]))

    def test_cli_coverage_gate_and_floor_breach(self):
        cfg = {"stage": "T", "coverage_min": 0.9, "modules": [{"module": "x", "python": "python/quantforge_core/heston.py"}]}
        floor = json.loads((ROOT / "conformance/quality/floors.json").read_text(encoding="utf-8"))["python"]
        good = {"files": {"quantforge_core/heston.py": {"summary": {"covered_lines": round(100 * floor) + 1, "num_statements": 100}}}}
        low = {"files": {"quantforge_core/heston.py": {"summary": {"covered_lines": 80, "num_statements": 100}}}}
        with tempfile.TemporaryDirectory() as d:
            c, g, lo = Path(d, "c.json"), Path(d, "g.json"), Path(d, "l.json")
            c.write_text(json.dumps(cfg)); g.write_text(json.dumps(good)); lo.write_text(json.dumps(low))
            run = lambda *a: self.qg.main(["--config", str(c), *a])  # noqa: E731
            self.assertEqual(run("--coverage", str(g), "--lang", "python"), 0)
            self.assertEqual(run("--coverage", str(lo), "--lang", "python"), 1)  # module below 90 %
            self.assertEqual(run("--coverage", str(g), "--lang", "python", "--floor"), 0)
            self.assertEqual(run("--coverage", str(lo), "--lang", "python", "--floor"), 1)
            with self.assertRaises(SystemExit):
                run("--coverage", str(g))  # --lang missing
            self.assertEqual(run("--check-config"), 0)  # heston.py exists in the real tree
            c.write_text("{not json")
            with self.assertRaises(json.JSONDecodeError):
                run("--check-config")

    def test_cli_check_config_fails_on_broken_module(self):
        cfg = {"stage": "T", "coverage_min": 0.9, "modules": [{"module": "x", "python": "python/nowhere.py"}]}
        with tempfile.TemporaryDirectory() as d:
            c = Path(d, "c.json")
            c.write_text(json.dumps(cfg))
            self.assertEqual(self.qg.main(["--config", str(c), "--check-config"]), 1)

    def test_floor_breach_alone_fails(self):
        rows = [("python/quantforge_core/x.py", 90, 100)]
        line, ok = self.qg.floor_gate("python", rows, 0.95)
        self.assertFalse(ok)
        self.assertIn("(BELOW)", line)

    def test_cli_dsr_needs_trials_and_baseline_round_trip(self):
        with self.assertRaises(SystemExit):
            self.qg.main(["--check-dsr"])
        with tempfile.TemporaryDirectory() as d:
            base = Path(d, "b.json")
            self.assertEqual(self.qg.main(["--write-baseline", "--baseline", str(base)]), 0)
            written = json.loads(base.read_text(encoding="utf-8"))
            self.assertEqual(sorted(written), ["register", "specs"])
            self.assertEqual(self.qg.main(["--check-register", "--check-specs", "--baseline", str(base)]), 0)
            base.write_text(json.dumps({"register": [], "specs": []}))
            expect = 1 if (written["register"] or written["specs"]) else 0
            self.assertEqual(self.qg.main(["--check-register", "--baseline", str(base)])
                             | self.qg.main(["--check-specs", "--baseline", str(base)]), expect)


class Governance(unittest.TestCase):
    """Plan 12.2 A2 (model register) and Q5b (convergence rule)."""

    @classmethod
    def setUpClass(cls):
        cls.qg = load("quality_gate", "tools/quality_gate.py")
        cls.gov = cls.qg.gov

    def test_a2_fields(self):
        full = "\n".join(f"- **{f}:** x" for f in self.gov.A2_FIELDS)
        inv = (f"## Index\n| M1 | m | `02-curves/a.md` |\n## Entries\n### M1 Curve\n{full}\n"
               "### M2 Other\n- **Tier:** 2\n- **Challenger:** TODO\n")
        gaps = self.gov.register_gaps(inv, ["02-curves/a.md", "02-curves/b.md"])
        self.assertEqual(len(gaps), 2)
        self.assertTrue(gaps[0].startswith("entry M2: missing Challenger, Monitoring thresholds"))  # TODO is not filled
        self.assertEqual(gaps[1], "spec 02-curves/b.md: no inventory entry")
        self.assertTrue(self.gov.has_field("| Data lineage hash | sha256:ab |", "Data lineage hash"))

    def test_convergence_section(self):
        g = self.gov.convergence_gap
        self.assertIsNone(g("# Day count\nNo numerics here."))
        self.assertIn("without", g("# Pricer\nSolved by Newton iteration."))
        empty = ("# P\nMonte Carlo.\n## Convergence and limit cases\n| Method | Asserted order |\n|---|---|\n"
                 "| <name> | <p> |\n## Next\n")
        self.assertIn("no filled", g(empty))
        ok = empty.replace("| <name> | <p> |", "| MC | 0.5 |")
        self.assertIsNone(g(ok))

    def test_ratchet_and_shipped_tree(self):
        self.assertEqual(self.gov.ratchet(["a", "b"], ["b", "c"]), (["a"], ["b"], ["c"]))
        base = ROOT / "conformance/quality/governance_baseline.json"
        self.assertEqual(self.qg.check_governance(True, True, base), 0)
        now = {"register": ["entry X9: missing Tier"], "specs": []}
        self.assertEqual(self.qg.check_governance(True, True, base, now), 1)  # a new gap fails


class ForwardLogAnchor(unittest.TestCase):
    def _log(self, d, n=5):
        p = Path(d) / "log.jsonl"
        for i in range(n):
            fl.append(p, "a", f"2026-01-0{i + 1}T00:00:00Z", float(i))
        return p

    def test_honest_log_and_growth_pass(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._log(d, 3)
            anchor.make(p, Path(d) / "an", "t1")
            fl.append(p, "a", "2026-02-01T00:00:00Z", 9.0)
            self.assertEqual(anchor.check_anchors(p, Path(d) / "an"), 1)

    def test_full_rewrite_with_recomputed_hashes_is_caught(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._log(d, 5)
            anchor.make(p, Path(d) / "an", "t1")
            rows = fl.read(p)
            rows[1]["record"]["value"]["payload"] = 99.0  # rewrite an old line
            head = fl.ZERO
            for r in rows:  # recompute every hash so the chain alone is consistent
                head = fl.link(head, r["record"])
                r["hash"] = head
            p.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows), encoding="utf-8")
            self.assertEqual(fl.verify(p)[0], 5)  # the chain by itself cannot see it
            with self.assertRaises(ValueError):
                anchor.check_anchors(p, Path(d) / "an")

    def test_truncation_is_caught(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._log(d, 4)
            anchor.make(p, Path(d) / "an", "t1")
            lines = p.read_text(encoding="utf-8").splitlines()
            p.write_text("\n".join(lines[:2]) + "\n",encoding="utf-8")
            with self.assertRaises(ValueError):
                anchor.check_anchors(p, Path(d) / "an")

    def test_empty_log_not_anchored(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                anchor.make(Path(d) / "none.jsonl", Path(d) / "an")


class ResearchDsrGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qg = load("quality_gate", "tools/quality_gate.py")

    def test_ledger_has_the_24_r3_trials(self):
        rows = self.qg.read_ledger()
        self.assertEqual(len(rows), 24)
        per = {s: sum(r["study"] == s for r in rows) for s in ("R3-01", "R3-02", "R3-03")}
        self.assertEqual(per, {"R3-01": 8, "R3-02": 12, "R3-03": 4})
        self.assertEqual(self.qg.check_dsr_trials(rows, 24, expect_family=24), [])

    def test_dsr_with_fewer_trials_than_the_ledger_is_rejected(self):
        rows = self.qg.read_ledger()
        self.assertTrue(self.qg.check_dsr_trials(rows, 8))  # the per-study count is not enough
        self.assertEqual(self.qg.main(["--check-dsr", "--trials", "12"]), 1)
        self.assertEqual(self.qg.main(["--check-dsr", "--trials", "24", "--expect-family", "24"]), 0)
        self.assertTrue(self.qg.check_dsr_trials(rows + rows[:1], 30))  # duplicate id


class FuzzFocus(unittest.TestCase):
    def test_focus_weights_toward_stage_and_is_a_noop_without_goldens(self):
        fz = load("fuzz_cli", "conformance/fuzz/fuzz_cli.py")
        seeds = [{"case_id": str(i)} for i in range(90)]
        with tempfile.TemporaryDirectory() as d:
            cfg = Path(d) / "q.json"
            cfg.write_text(json.dumps({"fuzz": {"golden": "datasets/golden/no_such_stage", "share": 0.5}}), encoding="utf-8")
            self.assertEqual(fz.focus_seeds(seeds, cfg), seeds)
            cfg.write_text(json.dumps({"fuzz": {"golden": "datasets/golden/r2", "share": 0.5}}), encoding="utf-8")
            out = fz.focus_seeds(seeds, cfg)
            self.assertGreater(len(out), len(seeds))
            self.assertAlmostEqual((len(out) - len(seeds)) / len(out), 0.5, delta=0.2)


class SiteHome(unittest.TestCase):
    def test_home_figures_come_from_one_place(self):
        sf = load("site_figures", "tools/site_figures.py")
        template = (ROOT / "tools/site_home.html").read_text(encoding="utf-8")
        figures = {**sf.home_figures(), "nav": "<nav></nav>"}
        self.assertNotIn("{{", sf.render_home(template, figures))
        version = figures["version"]
        import re
        found = {re.search(pattern, (ROOT / manifest).read_text(encoding="utf-8")).group(1) for manifest, pattern in (
            ("python/pyproject.toml", r'(?m)^version = "([^"]+)"'), ("rust/Cargo.toml", r'(?m)^version = "([^"]+)"'),
            ("java25/pom.xml", r"<artifactId>quantforge</artifactId><version>([^<]+)</version>"), ("cpp26/CMakeLists.txt", r"project\(\w+ VERSION (\S+)"))}
        self.assertEqual(len(found), 1, found)  # the manifests agree with each other; site_facts.json may name the release ahead of the bump
        for literal in (version, figures["golden_cases"], figures["released"]):
            self.assertNotIn(literal, template)  # no release figure hard-coded in the template
        with self.assertRaisesRegex(ValueError, "nope"):
            sf.render_home("{{nope}}", figures)

    def test_stage_table_follows_roadmap(self):
        """Plan 13.2 E7: the home stage table is generated from ROADMAP, and site_facts must agree with it."""
        sf = load("site_figures", "tools/site_figures.py")
        rows = sf.roadmap_stages()
        self.assertEqual([r[0] for r in rows][:5], ["A", "B", "C", "D", "E"])
        self.assertIn("<td>E</td>", sf.home_figures()["stage_rows"])
        self.assertEqual(sf.check_status(sf.home_figures(), rows), [])
        self.assertTrue(sf.check_status({"implemented_stages": "A to D"}, rows))  # drift fails the build
        # Stages can finish out of letter order (I before H): the span must not claim H.
        self.assertEqual(sf.stage_span(list("ABCDEFGI")), "A to G and I")
        self.assertEqual(sf.stage_span(list("ACE")), "A, C and E")
        self.assertEqual(sf.stage_span([]), "")
        self.assertNotIn("<tr><td>", (ROOT / "tools/site_home.html").read_text(encoding="utf-8"))

    def test_site_search_and_accessibility_markup(self):
        """Plan 13.2 E6 and E7: aria-current on the nav, and a search for SOFR finds the curve pages first."""
        try:
            bs = load("build_site", "tools/build_site.py")
        except ImportError:
            self.skipTest("markdown not installed; docs.yml runs this with it")
        self.assertIn('href="../LEARN.html" aria-current="page"', bs.nav("LEARN.html", "../"))
        self.assertEqual(bs.nav("x.html", "").count("aria-current"), 0)
        index = [bs.search_entry("docs/curves/sofr-ois.html", "SOFR OIS curve", "Bootstrap from SOFR quotes."),
                 bs.search_entry("LEARN.html", "Learn", "Mentions sofr once in passing."),
                 bs.search_entry("GLOSSARY.html", "Glossary", "No match here.")]
        self.assertEqual(bs.search(index, "SOFR"), ["docs/curves/sofr-ois.html", "LEARN.html"])
        for needle in ('class="skip"', '<main id="main"', "search.js"):
            self.assertIn(needle, bs.PAGE)
        self.assertIn(":focus-visible", bs.CSS)


class DoctorAndQuickstart(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(ROOT / "tools"))
        import check_quickstart
        import doctor
        cls.doctor, cls.qs = doctor, check_quickstart

    def test_expected_versions_come_from_the_repo(self):
        e = self.doctor.expected()
        self.assertEqual(e["python"], (ROOT / "python/.python-version").read_text().strip())
        self.assertIn(e["rust"], (ROOT / "rust/rust-toolchain.toml").read_text())
        self.assertTrue(e["java"].startswith("25"))

    def test_doctor_lists_every_problem_and_exits_1(self):
        e = self.doctor.expected()
        good = {"uv": "uv 0.13.6", "rustc": f"rustc {e['rust']} (x)", "java": f'openjdk version "{e["java"]}" 2026',
                "mvn": "Apache Maven 3.9.12", "cmake": "cmake version 4.0.1", "ninja": "1.13.2", "g++": e["gcc"] + ".0", "clang++": None}

        def runner(table):
            def r(cmd, cwd=None):
                if cmd[:2] == ["uv", "python"]:
                    return "/x/python" if table["uv"] else None
                return table[cmd[0]]
            return r
        self.assertEqual(self.doctor.main([], runner(good)), 0)
        bad = dict(good, rustc="rustc 1.80.0 (x)", mvn=None, cmake="cmake version 3.20.0")
        self.assertEqual(self.doctor.main([], runner(bad)), 1)
        failed = [r[1] for r in self.doctor.checks(e, runner(bad)) if not r[2]]
        self.assertEqual(len(failed), 3, failed)
        self.assertEqual(self.doctor.main(["--only", "python"], runner(bad)), 0)

    def test_quickstart_block_is_in_the_first_20_lines_and_compares_the_contract(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertLess(text.splitlines().index("<!-- quickstart:end -->"), 20)
        cmd, expected = self.qs.extract(text)
        self.assertIn("quantforge", cmd)
        printed = "\n".join(json.dumps(dict(e, diagnostics={"iterations": 99})) for e in expected)
        self.assertEqual(self.qs.compare(expected, printed), [])  # diagnostics are not contract
        changed = json.loads(json.dumps(expected))
        changed[0]["outputs"]["year_fraction"] = 0.5
        self.assertEqual(len(self.qs.compare(expected, "\n".join(json.dumps(e) for e in changed))), 1)
        self.assertTrue(self.qs.compare(expected, ""))


    def test_tutorial_has_a_block_per_language_and_one_expected_output(self):
        sys.path.insert(0, str(ROOT / "tools"))
        import check_tutorial
        self.assertGreaterEqual(len(check_tutorial.PAGES), 7)
        for page in check_tutorial.PAGES:
            text = page.read_text(encoding="utf-8")
            runs, expected = check_tutorial.blocks(text)
            self.assertEqual(set(runs), {"python", "rust", "java", "cpp"}, page.name)
            self.assertGreaterEqual(len(expected), 4, page.name)
            self.assertEqual(check_tutorial.sources(text), [], page.name)  # listings equal their scripts
        first = check_tutorial.PAGES[0]
        self.assertEqual(first.name, "tutorial-1-swap.md")
        self.assertEqual(check_tutorial.blocks(first.read_text(encoding="utf-8"))[0]["python"][0], "python")
        stale = "<!-- tutorial:source examples/tutorial_swap.py -->\n```python\nprint(1)\n```"
        self.assertEqual(check_tutorial.sources(stale), ["examples/tutorial_swap.py"])
        with self.assertRaises(ValueError):
            check_tutorial.blocks("no markers")


class StageFInfra(unittest.TestCase):
    """Plan 13.2 E11 hygiene gate and 12.2 G6 / 13.2 E10 incremental mutation planner."""

    def test_hygiene(self):
        h = load("check_hygiene", "tools/check_hygiene.py")
        big = h.LIMIT + 1
        sizes = {"a.json": big, "b.json": big, "c.txt": 5}
        bad = h.large_files(list(sizes), sizes, {"a.json": True, "c.txt": True, "gone.json": True})
        self.assertEqual(len(bad), 3)  # b.json unlisted; c.txt under the limit; gone.json untracked
        files = ["python/quantforge_x/.gitkeep", "rust/crates/a/src/lib.rs", "python/quantforge_y/__init__.py"]
        bad = h.empty_packages(files, {files[0]: 0, files[1]: 10, files[2]: 0})
        self.assertEqual(len(bad), 2)
        self.assertEqual(h.main(), 0)  # the shipped tree is clean

    def test_bench_gate_fails_on_injected_slowdown(self):
        bg = load("bench_gate", "tools/bench_gate.py")
        clean = {"py": {"implied_vol": {"ns_per_op": 25000.0, "allocs_per_op": 1.4}}}
        slow = {"py": {"implied_vol": {"ns_per_op": 225000.0, "allocs_per_op": 1.4}}}
        base = {"machine": "m", "results": clean}
        self.assertEqual(bg.compare(clean, base, "m")[1], [])
        self.assertEqual(len(bg.compare(slow, base, "m")[1]), 1)  # 9x slower fails
        self.assertEqual(bg.compare(slow, base, "other")[1], [])  # another machine class: reported, not gated
        leaky = {"py": {"implied_vol": {"ns_per_op": 25000.0, "allocs_per_op": 5.0}}}
        self.assertIn("allocs", bg.compare(leaky, base, "m")[1][0])
        self.assertEqual(bg.compare({}, base, "m")[1], ["py implied_vol: no result"])

    def test_mutation_plan(self):
        pm = load("plan_matrix", "conformance/mutation/plan_matrix.py")
        cfg = {"stages": {"E": [{"module": "m", "suite": "s", "java": "org.q.vol.Surf", "cpp": "cpp26/src/core/m.cpp",
                                 "python": "quantforge_core.m_e*", "rust": "**/m.rs"}]}}
        inc, frag = pm.plan(cfg, changed=["python/quantforge_core/m_e1.py", "README.md"])
        self.assertEqual([e["lang"] for e in inc], ["python"])
        self.assertEqual(list(frag["stages"]["PR"][0]), ["module", "suite", "python"])
        inc, _ = pm.plan(cfg, changed=["java25/src/main/java/org/q/vol/Surf.java", "rust/crates/c/src/m.rs"])
        self.assertEqual(sorted(e["lang"] for e in inc), ["java"] + ["rust"] * pm.RUST_SHARDS)
        self.assertEqual([e["shard"] for e in inc if e["lang"] == "rust"],
                         [f"{k}/{pm.RUST_SHARDS}" for k in range(pm.RUST_SHARDS)])
        self.assertEqual(pm.plan(cfg, changed=["docs/x.md"])[0], [])
        self.assertEqual(len(pm.plan(cfg, stage="E")[0]), 3 + pm.RUST_SHARDS)

    def test_mutation_report_merges_rust_shards(self):
        sr = load("stage_report", "conformance/mutation/stage_report.py")
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "rust--m.json"
            for k, (sampled, either) in enumerate([(20, 18), (20, 15)]):
                summary = {"mutants": 100, "unviable": 2, "unit_killed_all": either, "sampled": sampled,
                           "sample_unit_killed": either, "sample_golden_killed": 5, "sample_either_killed": either,
                           "sample_golden_timeouts": 0, "unit_verdicts": {"killed": either, "not run": 70}}
                (Path(tmp) / f"rust--m--s{k}.json").write_text(json.dumps({"summary": summary}), encoding="utf-8")
            self.assertEqual(len(sr.shard_files(base)), 2)
            killed, survived, note = sr.score_file("rust", base)
            self.assertEqual((killed, survived), (33, 7))
            self.assertIn("sample 40 of 100", note)


class DocsStatus(unittest.TestCase):
    """tools/check_docs_status.py: stale Planned curve rows and stale release wording fail."""

    TABLE = ("# Curves\n\n## Status of every curve in the plan\n\n| Curve | Status | Stage | Evidence |\n|---|---|---|---|\n"
             "{rows}\n## Real data\n")

    def setUp(self):
        self.c = load("check_docs_status", "tools/check_docs_status.py")
        self.ops = {"credit.curve.composite", "rates.funding.curve", "repo.forward", "rates.curve.discount"}

    def test_planned_row_naming_an_implemented_operation_fails(self):
        t = self.TABLE.format(rows="| Funding curve | Planned | F | `rates.funding.curve` |")
        self.assertEqual(len(self.c.curve_table_problems(t, self.ops)), 1)
        ok = self.TABLE.format(rows="| Liquidity curves | Planned | H | None yet |")
        self.assertEqual(self.c.curve_table_problems(ok, self.ops), [])

    def test_implemented_row_with_unknown_operation_fails(self):
        t = self.TABLE.format(rows="| [X](x.md) | Implemented, not Validated | D | 2 golden cases for `credit.curve.nope` |")
        self.assertIn("credit.curve.nope", self.c.curve_table_problems(t, self.ops)[0])

    def test_curve_operation_on_no_implemented_page_fails(self):
        # the old table: sector and funding curves done but still Planned with no operation named
        old = self.TABLE.format(rows="| [Repo](repo.md) | Implemented, not Validated | D | `repo.forward` |\n"
                                     "| Funding curve | Planned | F | None yet |")
        bad = self.c.unlisted_curve_operations({"README.md": old}, self.ops)
        self.assertEqual(bad[0].split()[2], "credit.curve.composite")
        self.assertEqual(len(bad), 2)  # rates.curve.discount reads a curve, so it is not a builder
        fixed = {"README.md": old, "f.md": "`rates.funding.curve` and `credit.curve.composite`"}
        self.assertEqual(self.c.unlisted_curve_operations(fixed, self.ops), [])

    def test_released_stage_called_pending_fails(self):
        log = "# Changelog\n\n## 0.7.0: stage G, models (unreleased)\n\n## 0.4.0: stage D, curves (2026-11-07)\n\n## v0.2: stage B, FX\n"
        rel = self.c.released_stages(log, ["v0.7.0", "v0.4", "v0.2"])
        self.assertEqual(rel, {"G": "0.7.0", "D": "0.4.0", "B": "0.2"})
        self.assertEqual(self.c.released_stages(log, ["v0.4"]), {"D": "0.4.0"})  # untagged G is not checked
        files = {"README.md": "Stage G (v0.7.0, not yet tagged) adds models.\nStage H is pending.\n",
                 "ROADMAP.md": "| G | Built, release `v0.7.0` pending |\n",
                 "CHANGELOG.md": log + "- the site facts name stage F as the pending release.\n"}
        bad = self.c.release_problems(files, rel)
        self.assertEqual(sorted(b.split(":")[0] for b in bad), ["CHANGELOG.md", "README.md", "ROADMAP.md"])
        self.assertTrue(all(":2:" not in b for b in bad if b.startswith("README")))  # stage H is not released

    def test_unknown_operation_name_fails(self):
        files = {"LEARN.md": "Use `credit.curve.composite` or `credit.curve.nope`; `core.x` and `foo.bar.baz` are not checked.\n",
                 "CHANGELOG.md": "Renamed `credit.curve.old`.\n"}
        bad = self.c.unknown_operations(files, self.ops)
        self.assertEqual(len(bad), 1)
        self.assertIn("credit.curve.nope", bad[0])

    def test_references_page_is_current_and_marks_status(self):
        r = load("build_references", "tools/build_references.py")
        found = r.collect()
        self.assertEqual((ROOT / "docs/references.md").read_text(encoding="utf-8"), r.render(found))
        page = r.render({("05-volatility", "Merton, R.C. (1976), doi:10.1016/0304-405X(76)90022-2. Status: licensed (not opened)"):
                         {"specifications/05-volatility/x.md"}})
        self.assertIn("**Not opened.** **Paywalled.**", page)
        self.assertIn("(https://doi.org/10.1016/0304-405X%2876%2990022-2)", page)
        self.assertIn("[`05-volatility/x.md`](../specifications/05-volatility/x.md)", page)

    def test_link_check_fails_only_on_gone_and_tolerates_offline(self):
        lc = load("check_links", "tools/check_links.py")
        self.assertEqual(lc.links("see <https://a.org/x>, [d](https://doi.org/10.1/a(76)b)."),
                         ["https://a.org/x", "https://doi.org/10.1/a(76)b"])
        self.assertEqual([lc.classify(c) for c in (200, 403, 404, None, 500)], ["ok", "refused", "gone", "unreachable", "error"])
        self.assertEqual(lc.run(["docs/references.md"], check=lambda u: None)[0], 0)  # offline
        self.assertEqual(lc.run(["docs/references.md"], check=lambda u: 403)[0], 0)
        self.assertEqual(lc.run(["docs/references.md"], check=lambda u: 404)[0], 1)

    def test_shipped_docs_pass(self):
        self.assertEqual(self.c.main(), 0)


if __name__ == "__main__":
    unittest.main()
