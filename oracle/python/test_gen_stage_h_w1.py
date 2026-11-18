"""Unit tests for gen_stage_h_w1.py: the spec property tests and the committed goldens.

    wsl: cd oracle/python && ~/qf-oracle-venv/bin/python -m unittest test_gen_stage_h_w1
"""
import json
import unittest
from fractions import Fraction as Fr

import mpmath as mp

import gen_stage_h_w1 as g
from qf_oracle.common import ROOT


class Schedules(unittest.TestCase):
    def test_largest_remainder_sums_and_ties_to_earliest(self):
        self.assertEqual(g.largest_remainder(10, [Fr(1)] * 3), [4, 3, 3])
        self.assertEqual(g.largest_remainder(7, [Fr(1), Fr(1), Fr(5)]), [1, 1, 5])
        for n in range(1, 40):
            self.assertEqual(sum(g.largest_remainder(1001, [Fr(i + 1) for i in range(n)])), 1001)

    def test_pov_participation_where_not_capped(self):
        r = g.pov({"quantity": 1e9, "participation": 0.3, "market_volume": [700.0, 1400.0], "mode": "CONTINUOUS"})
        for s, v in zip(r["slices"], [700.0, 1400.0]):
            self.assertAlmostEqual(s / (s + v), 0.3, places=12)

    def test_errors(self):
        self.assertEqual(g.run(g.pov, {"quantity": 1, "participation": 0.0, "market_volume": [1.0],
                                       "mode": "UNITS"})[1], "E_DOMAIN")
        self.assertEqual(g.run(g.twap, {"quantity": 0, "n_buckets": 2, "mode": "UNITS"})[1], "E_INPUT")


class AlmgrenChriss(unittest.TestCase):
    def test_tiny_lambda_is_near_linear(self):
        r = g.ac_trajectory(dict(g.P, risk_aversion=1e-15))
        for x, lin in zip(r["holdings"], [1e6, 8e5, 6e5, 4e5, 2e5, 0.0]):
            self.assertLessEqual(abs(x - lin), 1e-9 * 1e6)

    def test_holdings_below_linear_and_trades_sum(self):
        r = g.ac_trajectory(dict(g.P, risk_aversion=1e-6))
        self.assertTrue(all(x < lin for x, lin in zip(r["holdings"][1:-1], [8e5, 6e5, 4e5, 2e5])))
        self.assertAlmostEqual(sum(r["trades"]) / 1e6, 1.0, places=12)

    def test_kappa_tends_to_continuum_limit(self):
        lim = mp.sqrt(mp.mpf(1e-6) * mp.mpf(0.95) ** 2 / mp.mpf(2.5e-6))
        errs = [abs(g.ac_core(dict(g.P, n_steps=n), mp.mpf(1e-6))[2] - lim) for n in (10, 100, 1000)]
        self.assertTrue(errs[0] > errs[1] > errs[2])

    def test_large_kappa_t_finite_and_decreasing(self):
        x = g.ac_trajectory(dict(g.P, n_steps=50, risk_aversion=1e-1))["holdings"]
        self.assertTrue(all(a > b for a, b in zip(x, x[1:])) and all(v == v for v in x))


class Quotes(unittest.TestCase):
    def test_spread_tends_to_two_over_k(self):
        r = g.as_quotes(dict(g.AS_BASE, risk_aversion=1e-12, time_left=0.0))
        self.assertAlmostEqual(r["spread"], 2 / 1.5, places=9)

    def test_tca_components_sum(self):
        r = g.tca(g.TCA_BASE)
        self.assertAlmostEqual(r["delay"] + r["execution"] + r["opportunity"] + 5.0, r["total"], places=9)


class Goldens(unittest.TestCase):
    def test_committed_goldens_match_generator(self):
        suites, _ = g.build()
        for s in suites:
            doc = json.loads((ROOT / "datasets/golden/stage_h" / f"{s.name}.json").read_text(encoding="utf-8"))
            self.assertEqual(doc["cases"], json.loads(json.dumps(s.cases)), s.name)


if __name__ == "__main__":
    unittest.main()
