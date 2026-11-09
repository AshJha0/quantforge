import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import r3_power as p  # noqa: E402


class PowerTest(unittest.TestCase):
    def test_size_at_most_5_percent_at_sr_zero(self):
        for study in p.STUDIES:
            for phi in (0.0, 0.2):
                lenient, strict = p.pass_probability(study, 0.0, sims=2000, phi=phi)
                self.assertLessEqual(lenient, 0.05, (study, phi))
                self.assertLessEqual(strict, lenient)

    def test_power_rises_with_true_sharpe(self):
        lo = p.pass_probability("R3-03", 0.5, sims=2000)[0]
        hi = p.pass_probability("R3-03", 2.0, sims=2000)[0]
        self.assertLess(lo, hi)
        self.assertGreater(hi, 0.8)

    def test_expected_max_and_ppf(self):
        self.assertAlmostEqual(p.norm_ppf(0.95), 1.6448536269514722, places=9)
        self.assertEqual(p.expected_max_z(1), 0.0)
        self.assertAlmostEqual(p.expected_max_z(24), 1.9798, places=3)

    def test_lo_se_matches_iid_formula_without_lags(self):
        import numpy as np
        x = np.random.default_rng(1).standard_normal((1, 1200))
        sr, se = p.lo_sharpe(x, 12, 0)
        self.assertAlmostEqual(se[0], math.sqrt((1 + (sr[0] / math.sqrt(12)) ** 2 / 2) / 1200) * math.sqrt(12), places=12)

    def test_forward_rule_size(self):
        # true SR 0: the rule passes about half the time (sign), so the forward log alone confirms nothing
        self.assertLess(p.forward_pass_probability(0.0, 0.67, sims=5000), 0.55)


if __name__ == "__main__":
    unittest.main()
