import hashlib
import re
import unittest
from pathlib import Path

D = Path(__file__).resolve().parent / "preregs"
MARK = b"<!-- body -->\n"


def body_sha(b):
    return hashlib.sha256(b[b.index(MARK) + len(MARK):]).hexdigest()


class PreregHashes(unittest.TestCase):
    def test_every_signed_file_matches_its_recorded_hashes(self):
        readme = body_sha((D / "README.md").read_bytes())
        files = sorted(D.glob("R3-*.md"))
        self.assertEqual(len(files), 22)
        for f in files:
            b = f.read_bytes()
            head = b[:b.index(MARK)].decode()
            self.assertIn(body_sha(b), head, f.name)
            self.assertIn(readme, head, f.name)
            m = re.search(r"amended prereg `([^`]+)` \(whole file\): `([0-9a-f]{64})`", head)
            if "amendment" in f.name:
                self.assertEqual(hashlib.sha256((D / m.group(1)).read_bytes()).hexdigest(), m.group(2), f.name)
                self.assertIn("Prior knowledge", b.decode())
            if any(f"amendment-{i}" in f.name for i in (3, 4, 5, 6, 7)):
                extra = {"amendment-4": ("-amendment-3.md",), "amendment-5": ("-amendment-3.md", "-amendment-4.md"),
                         "amendment-6": ("-amendment-3.md", "-amendment-4.md")
                         + (("-amendment-5.md",) if (D / f"{f.name[:5]}-amendment-5.md").exists() else ()),
                         "amendment-7": ("-amendment-3.md", "-amendment-4.md", "-amendment-6.md")
                         + (("-amendment-5.md",) if (D / f"{f.name[:5]}-amendment-5.md").exists() else ())}
                extra = tuple(f"{f.name[:5]}{e}" for k, v in extra.items() if k in f.name for e in v)
                for n in (f"{f.name[:5]}-amendment-1.md", f"{f.name[:5]}-amendment-2.md", "DEVIATION-2026-11-12-recorder-rule.md", *extra):
                    m = re.search(rf"`{re.escape(n)}` \(whole file\): `([0-9a-f]{{64}})`", head)
                    self.assertEqual(hashlib.sha256((D / n).read_bytes()).hexdigest(), m.group(1), f.name)
            if any(f"amendment-{i}" in f.name for i in (2, 3, 4, 5, 6, 7)):
                if "amendment-7" in f.name:
                    for rel in ("holdout_runs.csv", "r3/forward_signals.jsonl"):
                        m = re.search(rf"`research/{re.escape(rel)}` \(whole file\): `([0-9a-f]{{64}})`", head)
                        self.assertEqual(hashlib.sha256((D.parent / rel).read_bytes()).hexdigest(), m.group(1), rel)
                if "amendment-6" in f.name:
                    for rel in ("holdout_runs.csv", "r3_runner.py", "r3_in_sample.py", "r3_data.py"):
                        m = re.search(rf"`research/{re.escape(rel)}` \(whole file\): `([0-9a-f]{{64}})`", head)
                        self.assertEqual(hashlib.sha256((D.parent / rel).read_bytes()).hexdigest(), m.group(1), rel)
                m = re.search(r"`DEVIATION-2026-11-12.md` \(whole file\): `([0-9a-f]{64})`", head)
                self.assertEqual(hashlib.sha256((D / "DEVIATION-2026-11-12.md").read_bytes()).hexdigest(), m.group(1), f.name)


import json  # noqa: E402
import sys  # noqa: E402
import tempfile  # noqa: E402

sys.path.insert(0, str(D.parent))
import holdout_scan  # noqa: E402

NOTE = D / "DEVIATION-2026-11-12.md"


def listed():
    """Locations listed in the deviation note: the first backticked field of each list line."""
    return set(re.findall(r"^- `([^`]+)` \|", NOTE.read_text(encoding="utf-8"), re.M))


RULE_NOTE = D / "DEVIATION-2026-11-12-recorder-rule.md"


def rules():
    """Rule lines of the recorder note: a location pattern with `*` for the report date, and a date range."""
    out = []
    for pat, lo, hi in re.findall(r"^- rule `([^`]+)` \|[^|]*\|[^|]*\| (\d{4}-\d\d-\d\d) to (\d{4}-\d\d-\d\d)$",
                                  RULE_NOTE.read_text(encoding="utf-8"), re.M):
        out.append((re.compile("^" + re.escape(pat).replace(r"\*", r"(\d{4}-\d\d-\d\d)") + "$"), lo, hi))
    return out


def covered(loc, rs):
    for rx, lo, hi in rs:
        m = rx.match(loc)
        if m and lo <= m.group(1) <= hi:
            return True
    return False


def unlisted(hits):
    ok, rs = listed(), rules()
    return sorted(loc for loc in {h[0] for h in hits} - ok if not covered(loc, rs))


class HoldoutObservations(unittest.TestCase):
    """R6-19: no tracked file or forward-log row may carry an observation inside an R3 holdout window unless the
    deviation note lists it."""

    def test_no_unlisted_holdout_observation(self):
        hits, have_log = holdout_scan.scan_all()
        self.assertEqual(unlisted(hits), [], "holdout-window observation not listed in DEVIATION-2026-11-12.md")
        if not have_log:
            print("note: origin/forward-log not fetched; only tracked files scanned", file=sys.stderr)

    def test_planted_log_row_is_caught(self):
        row = {"hash": "x", "record": {"series_id": "recorder/us-treasury-bill-rates", "event_time": "2026-11-13T04:00:00Z",
                                       "value": {"payload": {"observations": {"2025-06-02|13 WEEKS BANK DISCOUNT": 4.1,
                                                                              "2026-11-12|13 WEEKS BANK DISCOUNT": 3.9}}}}}
        hits = holdout_scan.scan_log([json.dumps(row)])
        self.assertEqual([(h[1], h[2], h[3]) for h in hits], [("R3-02", 1, "2025-06-02")])
        self.assertEqual(unlisted(hits), ["forward-log:actions/log.jsonl#row1:us-treasury-bill-rates"])

    def test_planted_page_is_caught_and_forward_page_is_not(self):
        bad = holdout_scan.scan_text("docs/x.md", "SOFR fixing on 2026-10-15: 4.20%")
        good = holdout_scan.scan_text("docs/y.md", "SOFR fixing on 2026-11-12: 3.90%")
        self.assertEqual(unlisted(bad), ["docs/x.md"])
        self.assertEqual(good, [])

    def test_data_log_blanks_only_url_and_hash(self):
        head = "name,window,url,utc_retrieved,sha256\n"
        name = "R3-01_daily_treasury_yield_curve_2012.csv,in,"
        ok = head + name + "https://home.treasury.gov/x?startDate=2018-04-02,2026-11-14T10:00:00Z,ab\n"
        bad = head + name + "https://home.treasury.gov/x,2015-06-01T10:00:00Z,ab\n"
        self.assertEqual(holdout_scan.scan_text("l", holdout_scan.strip_log_columns(ok)), [])
        self.assertEqual(holdout_scan.scan_text("l", holdout_scan.strip_log_columns(bad))[0][1], "R3-01")
        # the same row in any other file is not blanked and is caught
        self.assertTrue(holdout_scan.scan_text("docs/z.csv", ok))

    def test_recorder_rule_covers_only_its_files_and_dates(self):
        rs = rules()
        self.assertEqual(len(rs), 2)
        self.assertTrue(covered("forward-log:reports/2026-11-12/sofr-check.json", rs))
        self.assertTrue(covered("forward-log:reports/2026-11-12/sofr-check.md", rs))
        self.assertFalse(covered("forward-log:reports/2026-11-05/sofr-check.json", rs))  # before the rule's range
        self.assertFalse(covered("forward-log:reports/2027-05-03/sofr-check.json", rs))  # after it
        self.assertFalse(covered("forward-log:reports/2026-11-12/p&l-explain.json", rs))  # another report
        self.assertEqual(unlisted([("forward-log:reports/2026-11-12/sofr-check.json",), ("docs/x.md",)]), ["docs/x.md"])

class ForwardSignals(unittest.TestCase):
    """Amendment 3 rule 5 (amendment 6 Change 5): no study row may carry a signal or position written before the
    study's holdout run, from a tree without its run line, or dated before the run without the back-fill marks."""

    def test_no_early_or_unmarked_signal(self):
        self.assertEqual(holdout_scan.signal_scan_all(), [])

    def test_planted_early_signal_is_caught(self):
        row = {"record": {"series_id": "study/R3-01", "event_time": "2026-11-12T21:00:00Z",
                          "knowledge_time": "2026-11-12T21:00:00Z", "value": {"commit": "nope", "payload": {"signal": 0.1}}}}
        bad = holdout_scan.signal_check([row], {"R3-01": "2026-11-14"}, show=lambda c: None)
        self.assertEqual([b[1][0] for b in bad], ["b", "c", "d"])



class Q6Prereg(unittest.TestCase):
    def test_q6_churn_bound_matches_its_recorded_hash(self):
        b = (D / "Q6-01-churn-bound.md").read_bytes()
        self.assertIn(body_sha(b), b[:b.index(MARK)].decode())

    def test_q6_02_matches_its_recorded_hashes(self):
        b = (D / "Q6-02-robust-shape-penalty.md").read_bytes()
        head = b[:b.index(MARK)].decode()
        self.assertIn(body_sha(b), head)
        m = re.search(r"`Q6-01-churn-bound.md` \(whole file\): `([0-9a-f]{64})`", head)
        self.assertEqual(hashlib.sha256((D / "Q6-01-churn-bound.md").read_bytes()).hexdigest(), m.group(1))
        for name in ("q6_02_method_test.py", "q6_method_test.py"):
            m = re.search(rf"`{name}` \(whole file\): `([0-9a-f]{{64}})`", head)
            self.assertEqual(hashlib.sha256((D.parent / "q6" / name).read_bytes()).hexdigest(), m.group(1), name)

if __name__ == "__main__":
    unittest.main()
