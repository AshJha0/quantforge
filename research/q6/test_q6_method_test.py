"""Checks for the Q6 synthetic method test (R6-24). Each gate is shown failing on a planted fault (plan 14.10 rule 1)."""
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import q6_method_test as q  # noqa: E402


class Gates(unittest.TestCase):
    def test_true_surface_is_arbitrage_free(self):
        t = q.truth_path(3, np.random.default_rng(1))[0]
        self.assertEqual(q.arbitrage_ok(q.unpack_truth(t)), (True, True))

    def test_planted_calendar_arbitrage_is_caught(self):
        theta = np.array([0.004, 0.008, 0.006, 0.02, 0.04])  # total variance falls from 60 to 91 days
        self.assertFalse(q.arbitrage_ok((theta, -0.5, 1.0))[0])

    def test_planted_butterfly_arbitrage_is_caught(self):
        # eta * (1 + |rho|) far above 2 at short expiry: Durrleman g < 0 in the wings
        theta = np.array([0.0005, 0.008, 0.012, 0.02, 0.04])
        self.assertFalse(q.arbitrage_ok((theta, -0.95, 6.0))[1])

    def test_churn_bound_fails_on_planted_jitter(self):
        self.assertTrue(q.churn_ok(np.array([1.0] * 20)))
        self.assertFalse(q.churn_ok(np.array([2.0] * 20)))
        self.assertFalse(q.churn_ok(np.array([1.0] * 18 + [5.0, 5.0])))

    def test_fit_parameterisation_is_arbitrage_free_for_any_input(self):
        rng = np.random.default_rng(2)
        for _ in range(50):
            x = np.concatenate([rng.normal(0.05, 0.02, 5), rng.normal(0, 1, 2)])
            self.assertEqual(q.arbitrage_ok(q.unpack(x)), (True, True))

    def test_short_run_passes_with_known_answer(self):
        out = q.main(days=15, seed=7)
        self.assertEqual(out["result"], "PASS", out)
        self.assertLess(out["rms_error_to_truth_on_grid_vol"], 0.005)


if __name__ == "__main__":
    unittest.main()
