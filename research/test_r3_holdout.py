"""The holdout script must refuse before reading any holdout value when no committed run line exists."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import r3_holdout
import r3_runner


class Refuses(unittest.TestCase):
    def test_unlogged_commit_refused(self):
        with self.assertRaises(r3_runner.HoldoutRefused):
            r3_holdout.merged("R3-01", "0000000")

    def test_in_holdout_bounds(self):
        from datetime import date
        self.assertFalse(r3_holdout.in_holdout("R3-02", date(2022, 12, 30)))
        self.assertTrue(r3_holdout.in_holdout("R3-02", date(2023, 1, 3)))


if __name__ == "__main__":
    unittest.main()
