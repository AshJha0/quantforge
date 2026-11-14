"""Synthetic-data tests for the R3 loader. No network, no market data."""
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import r3_data as d
import r3_runner

TSY = b'Date,"2 Yr","5 Yr","10 Yr"\n01/03/2012,0.25,0.89,1.97\n12/31/2012,0.25,0.72,1.78\n'
NYF = b"Effective Date,Rate Type,Rate (%)\n2022-12-29,SOFR,4.30\n2022-12-30,SOFR,4.31\n2023-01-03,SOFR,4.33\n"


class Loader(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data, self.log = Path(self.tmp.name) / "data", Path(self.tmp.name) / "log.csv"
        self.calls: list[str] = []

    def tearDown(self):
        self.tmp.cleanup()

    def fake(self, url: str) -> bytes:
        self.calls.append(url)
        return NYF if "newyorkfed" in url else TSY

    def fetch_study(self, study):
        for s in d.SOURCES[study]:
            d.fetch(s, self.fake, self.data, self.log)

    def test_fetch_once_then_verify(self):
        s = d.SOURCES["R3-01"][0]
        h1 = d.fetch(s, self.fake, self.data, self.log)
        h2 = d.fetch(s, self.fake, self.data, self.log)
        self.assertEqual((h1, len(self.calls)), (h2, 1))
        self.assertEqual(d.read_log(self.log)[s.name]["window"], "in")

    def test_tampered_file_refused(self):
        s = d.SOURCES["R3-01"][0]
        d.fetch(s, self.fake, self.data, self.log)
        (self.data / s.name).write_bytes(TSY + b"01/04/2012,9,9,9\n")
        with self.assertRaises(ValueError):
            d.fetch(s, self.fake, self.data, self.log)

    def test_in_sample_never_parses_holdout_files(self):
        self.fetch_study("R3-01")
        hold = [s for s in d.SOURCES["R3-01"] if s.window == "holdout"]
        self.assertEqual(min(int(s.name[-8:-4]) for s in hold), 2013)
        for s in hold:  # corrupt every holdout file: the in-sample load must not touch them
            (self.data / s.name).write_bytes(b"garbage")
        out = d.load_in_sample("R3-01", self.data, self.log)
        self.assertEqual(sorted(out[d.NOMINAL][date(2012, 12, 31)]), ["10 YR", "2 YR", "5 YR"])

    def test_in_sample_rows_capped_at_end(self):
        self.fetch_study("R3-02")
        out = d.load_in_sample("R3-02", self.data, self.log)
        self.assertEqual(max(out["SOFR"]), date(2022, 12, 30))
        self.assertTrue(all(x <= r3_runner.IN_SAMPLE_END["R3-02"] for x in out[d.BILL]))

    def test_r3_03_never_sees_2y(self):
        self.fetch_study("R3-03")
        out = d.load_in_sample("R3-03", self.data, self.log)
        self.assertNotIn("2 YR", next(iter(out[d.NOMINAL].values())))

    def test_holdout_refused_without_guard(self):
        self.fetch_study("R3-02")
        with self.assertRaises(r3_runner.HoldoutRefused):
            d.load_holdout("R3-02", "", self.data, self.log)

    def test_holdout_loads_when_guard_passes(self):
        self.fetch_study("R3-02")
        line = f"study,utc_date,script,script_sha256,commit\nR3-02,x,y,{r3_runner.script_sha256()},abc1234\n"
        out = d.load_holdout("R3-02", "abc1234", self.data, self.log, git=lambda *a: line)
        self.assertEqual(sorted(out["SOFR"]), [date(2023, 1, 3)])

    def test_log_mismatch_refused(self):
        s = d.SOURCES["R3-01"][0]
        d.fetch(s, self.fake, self.data, self.log)
        other = d.Source(s.name, s.url + "x", s.window, s.kind, s.key)
        with self.assertRaises(ValueError):
            d.fetch(other, self.fake, self.data, self.log)

    def test_parse_mdy_nyfed(self):
        out = d.parse_nyfed(b"Effective Date,Rate Type,Rate (%)\n01/03/2023,TGCR,4.2\n01/04/2023,TGCR,\n")
        self.assertEqual(out, {date(2023, 1, 3): {"TGCR": 4.2}})


if __name__ == "__main__":
    unittest.main()
