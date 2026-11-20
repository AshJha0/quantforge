"""Tests for the K-6 soak analyser and process counters. Standard library only.

Run: python -m unittest benchmarks/soak/test_soak.py   (or pytest benchmarks/soak)
"""

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import analyse
import procstat

MIB = 1024 * 1024


def rows(minutes=120, base=400 * MIB, slope_mib_h=0.0, noise=0, step=10, java=False, cases=50):
    out = []
    for i in range(1, int(minutes * 60 / step) + 1):
        t = i * step
        v = base + slope_mib_h * MIB * t / 3600 + (noise if i % 2 else -noise)
        judged = "" if java and i % 3 else int(v)
        out.append(
            {
                "t_s": str(t),
                "judged_bytes": str(judged),
                "cases_window": str(cases),
                "passes": "1" if t >= 300 else "0",
                "alive": "1",
            }
        )
    return out


SUMMARY = {"implementation": "python", "drift": 0, "golden_failures": 0, "errors": 0, "stderr_bytes": 0, "exit_code": 0}


class AnalyseTest(unittest.TestCase):
    def test_flat_series_passes(self):
        v = analyse.analyse(rows(noise=64 * 1024), SUMMARY)
        self.assertEqual(v["verdict"], "PASS", v["reasons"])
        lo, hi = v["slope_ci95_mib_per_h"]
        self.assertLessEqual(lo, 0.0)
        self.assertGreaterEqual(hi, 0.0)

    def test_planted_leak_rate_is_flagged_in_twenty_minutes(self):
        # 1 KiB per 100 cases at 500 cases a second is about 17.6 MiB an hour.
        v = analyse.analyse(rows(minutes=20, slope_mib_h=17.6, noise=64 * 1024), SUMMARY, planted=True)
        self.assertEqual(v["verdict"], "LEAK CAUGHT")
        self.assertIn("SLOPE", v["reasons"])

    def test_slow_climb_just_over_bound_is_a_miss(self):
        v = analyse.analyse(rows(slope_mib_h=1.2), SUMMARY)
        self.assertEqual(v["verdict"], "MISS")
        self.assertIn("SLOPE", v["reasons"])

    def test_wandering_series_misses_on_range(self):
        r = rows()
        r[200]["judged_bytes"] = str(500 * MIB)
        v = analyse.analyse(r, SUMMARY)
        self.assertEqual(v["reasons"], ["RANGE"])

    def test_warmup_is_dropped(self):
        r = rows()
        for x in r[:50]:  # first 500 s much higher, then flat
            x["judged_bytes"] = str(900 * MIB)
        self.assertEqual(analyse.analyse(r, SUMMARY)["verdict"], "PASS")

    def test_warmup_waits_for_first_full_pass(self):
        r = rows(minutes=130)
        for x in r:
            x["passes"] = "1" if float(x["t_s"]) >= 900 else "0"
        for x in r[:85]:  # high until 850 s, before the first pass ends
            x["judged_bytes"] = str(900 * MIB)
        v = analyse.analyse(r, SUMMARY)
        self.assertEqual(v["warmup_end_s"], 900.0)
        self.assertEqual(v["verdict"], "PASS")

    def test_each_process_failure_is_a_miss(self):
        for key, val, reason in [
            ("drift", 1, "DRIFT"),
            ("golden_failures", 2, "GOLDEN"),
            ("errors", 1, "ERRORS"),
            ("stderr_bytes", 10, "STDERR"),
            ("exit_code", 1, "EXIT"),
            ("died", True, "DIED"),
        ]:
            v = analyse.analyse(rows(), dict(SUMMARY, **{key: val}))
            self.assertEqual(v["verdict"], "MISS")
            self.assertIn(reason, v["reasons"])

    def test_short_run_and_stall(self):
        self.assertIn("SHORT", analyse.analyse(rows(minutes=60), SUMMARY)["reasons"])
        r = rows()
        for x in r[300:340]:
            x["cases_window"] = "0"
        self.assertIn("STALL", analyse.analyse(r, SUMMARY)["reasons"])

    def test_java_needs_200_heap_samples(self):
        v = analyse.analyse(rows(java=True), dict(SUMMARY, implementation="java"))
        self.assertEqual(v["verdict"], "PASS", v["reasons"])
        self.assertGreaterEqual(v["samples_after_warmup"], 200)
        v = analyse.analyse(rows(java=True, minutes=100), dict(SUMMARY, implementation="java"))
        self.assertIn("SHORT", v["reasons"])

    def test_no_full_pass(self):
        r = rows()
        for x in r:
            x["passes"] = "0"
        self.assertIn("NO_FULL_PASS", analyse.analyse(r, SUMMARY)["reasons"])


class ProcstatTest(unittest.TestCase):
    def test_samples_this_process(self):
        s = procstat.sample(os.getpid())
        self.assertIsNotNone(s)
        self.assertGreater(s["rss_bytes"], 1 * MIB)
        self.assertGreater(s[procstat.judged_key()], 0)
        self.assertGreaterEqual(s["threads"], 1)
        self.assertGreater(s["handles"], 0)

    def test_gone_process_is_none(self):
        self.assertIsNone(procstat.sample(2**22 + 7))


if __name__ == "__main__":
    unittest.main()
