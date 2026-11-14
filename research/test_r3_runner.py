"""Synthetic-data tests for the R3 runner. No market data is read."""
import subprocess
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import r3_runner as r


def bdays(start: date, n: int) -> list[date]:
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


class Guard(unittest.TestCase):
    def g(self, last: date, commit: str | None = "abc1234") -> r.GuardInputs:
        return r.GuardInputs("R3-01", last, commit, "f" * 64)

    def test_in_sample_needs_nothing(self):
        r.holdout_guard(self.g(date(2012, 12, 31), None), git=lambda *a: self.fail("git called"))

    def test_holdout_without_commit_refused(self):
        with self.assertRaises(r.HoldoutRefused):
            r.holdout_guard(self.g(date(2013, 1, 2), None))

    def test_holdout_without_committed_line_refused(self):
        def git(*a):
            if a[0] == "show":
                raise subprocess.CalledProcessError(128, "git")
            return ""
        with self.assertRaises(r.HoldoutRefused):
            r.holdout_guard(self.g(date(2013, 1, 2)), git=git)

    def test_line_for_other_script_refused(self):
        log = "study,utc_date,script,script_sha256,commit\nR3-01,2026-11-20,x,{},abc1234\n"
        with self.assertRaises(r.HoldoutRefused):
            r.holdout_guard(self.g(date(2013, 1, 2)), git=lambda *a: log.format("e" * 64))

    def test_matching_committed_line_allows(self):
        log = "study,utc_date,script,script_sha256,commit\nR3-01,2026-11-20,x,{},abc1234\n"
        r.holdout_guard(self.g(date(2013, 1, 2)), git=lambda *a: log.format("f" * 64))

    def test_real_repo_has_no_line_so_refuses(self):
        with self.assertRaises(r.HoldoutRefused):
            r.holdout_guard(r.GuardInputs("R3-02", date(2023, 1, 3), "HEAD", r.script_sha256()))


class Stats(unittest.TestCase):
    def test_holm(self):
        self.assertEqual(r.holm({"a": 0.01, "b": 0.02, "c": 0.04}), {"a": True, "b": True, "c": True})
        self.assertEqual(r.holm({"a": 0.02, "b": 0.03, "c": 0.04}), {"a": False, "b": False, "c": False})

    def test_decision_uses_family_benchmark(self):
        d = r.decision(1.0, 0.5)
        self.assertAlmostEqual(d["sr0"], 0.9899)
        self.assertLess(d["p2"], d["p"])

    def test_select_ties_to_lower(self):
        self.assertEqual(r.select([0.1, 0.3, 0.3]), 1)

    def test_pbo_one_trial_not_applicable(self):
        self.assertIsNone(r.pbo([np.zeros(32)]))

    def test_pbo_noise_runs(self):
        g = np.random.default_rng(1)
        v = r.pbo([g.standard_normal(70) for _ in range(4)])
        self.assertIsNotNone(v)

    def test_boot_reproducible(self):
        x = np.random.default_rng(2).standard_normal(46)
        self.assertEqual(r.boot(x, draws=200), r.boot(x, draws=200))


class Fly(unittest.TestCase):
    def test_par_dv01_plausible(self):
        d5 = r.par_dv01(0.04, 5, date(2005, 6, 1))
        self.assertTrue(4e-4 < d5 < 5e-4)

    def test_no_look_ahead(self):
        g = np.random.default_rng(3)
        f = np.cumsum(g.standard_normal(600))
        a = r.fly_returns(f, np.full(600, 1e4), 60, 1.0)["net"]
        f2 = f.copy()
        f2[400:] += 50.0  # a future shock changes nothing before it
        b = r.fly_returns(f2, np.full(600, 1e4), 60, 1.0)["net"]
        np.testing.assert_array_equal(a[:400], b[:400])

    def test_noise_sharpe_near_zero(self):
        g = np.random.default_rng(4)
        f = np.cumsum(g.standard_normal(40_000))  # random walk: no reversion
        net = r.fly_returns(f, np.full(40_000, 1e4), 120, 1.0, cost_mult=0.0)["net"]
        sr, se = r.lo(net, 252, 20)
        self.assertLess(abs(sr), 3 * se)

    def test_reverting_fly_earns(self):
        g = np.random.default_rng(5)
        f = np.zeros(6000)
        for t in range(1, 6000):
            f[t] = 0.9 * f[t - 1] + g.standard_normal()
        net = r.fly_returns(f, np.full(6000, 1e4), 60, 1.0, cost_mult=0.0)["net"]
        self.assertGreater(net.mean(), 0)


class Bill(unittest.TestCase):
    def test_basis(self):
        self.assertEqual(r.bill_basis(date(2019, 6, 1)), 366)
        self.assertEqual(r.bill_basis(date(2021, 6, 1)), 365)

    def test_noise_funding_near_zero(self):
        days = bdays(date(1800, 1, 1), 30_000)
        g = np.random.default_rng(6)
        fund = 0.04 + 0.001 * g.standard_normal(len(days))
        bill = np.array([0.04 * r.bill_basis(d) / 360 for d in days])
        _, net = r.bill_month_returns(days, bill, fund, 60, 1.0, cost_mult=0.0)
        self.assertLess(abs(net.mean() / net.std(ddof=1) * np.sqrt(12)),
                        3 * np.sqrt(12 / len(net)) + 0.05)

    def test_exit_dates_are_month_starts(self):
        days = bdays(date(2018, 4, 2), 400)
        d, _ = r.bill_month_returns(days, np.full(400, 0.02), np.full(400, 0.02) +
                                    np.linspace(0, 1e-3, 400), 60, 1.0)
        self.assertTrue(all(x.day <= 3 for x in d))


class Seasonal(unittest.TestCase):
    def test_planted_seasonal_found_and_shrink_irrelevant(self):
        ends = [date(2003 + i // 12, i % 12 + 1, 28) for i in range(120)]
        b = np.cumsum([5.0 if e.month == 3 else -1.0 for e in ends])
        dates, net = r.seasonal_returns(ends, b, np.full(120, 4.5e-4), np.full(120, 4.6e-4),
                                        date(2007, 12, 31), cost_mult=0.0)
        self.assertTrue((net > 0).all())
        self.assertEqual(len(dates), 119)


if __name__ == "__main__":
    unittest.main()


class ClosedDv01(unittest.TestCase):
    def test_matches_library_on_coupon_date_and_zero_limit(self):
        for y, n in ((0.03, 2), (0.045, 5), (0.06, 10)):
            self.assertAlmostEqual(r.par_dv01_closed(y, n) / r.par_dv01(y, n, date(2010, 6, 15)), 1.0, places=9)
        self.assertEqual(r.par_dv01_closed(0.0, 5), 5e-4)
        self.assertAlmostEqual(r.par_dv01_closed(1e-9, 5), 5e-4, places=10)
