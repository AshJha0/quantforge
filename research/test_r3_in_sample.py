"""Synthetic tests for the R3 in-sample helpers. No market data."""
import sys
import unittest
from datetime import date
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import r3_in_sample as s


class Helpers(unittest.TestCase):
    def test_aligned_drops_any_missing_input(self):
        ser = {"a": {date(2020, 1, 2): {"x": 1.0}, date(2020, 1, 3): {"x": 2.0}},
               "b": {date(2020, 1, 3): {"y": 5.0}, date(2020, 1, 6): {"y": 6.0}}}
        days, v = s.aligned(ser, [("a", "x"), ("b", "y")])
        self.assertEqual(days, [date(2020, 1, 3)])
        np.testing.assert_array_equal(v, [[2.0, 5.0]])

    def test_common_keeps_shared_exit_dates(self):
        d1, d2, d3 = date(2020, 2, 3), date(2020, 3, 2), date(2020, 4, 1)
        keep, nets = s.common([([d1, d2, d3], np.array([1.0, 2.0, 3.0])), ([d2, d3], np.array([5.0, 6.0]))])
        self.assertEqual(keep, [d2, d3])
        np.testing.assert_array_equal(nets[0], [2.0, 3.0])

    def test_sharpe_row_iid(self):
        x = np.array([1.0, -1.0, 2.0, 0.0])
        row = s.sharpe_row(x, 12, None)
        self.assertAlmostEqual(row["sharpe_net_1x"], round(0.5 / x.std(ddof=1) * 12 ** 0.5, 6))
        self.assertEqual(row["nonzero"], 3)


if __name__ == "__main__":
    unittest.main()
