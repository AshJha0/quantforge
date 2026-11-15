"""A3 runner: the guard refuses an unsigned prereg; the study runs end to end on other seeds and few paths."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import a3_drift_study as a3


class Guard(unittest.TestCase):
    def test_refuses_unsigned_prereg(self) -> None:
        with self.assertRaises(SystemExit) as e:
            a3.guard(output=Path(__file__).with_name("does-not-exist.json"))
        self.assertIn("not signed", str(e.exception))


class SmallStudy(unittest.TestCase):
    def test_runs_on_other_seeds(self) -> None:
        r = a3.study(seed_null=11, seed_break=12, paths=20)
        self.assertEqual(set(r["verdicts"]), {"cusum", "page_hinkley", "psi", "ks"})
        self.assertGreater(r["cusum"]["arl0"], 0)


if __name__ == "__main__":
    unittest.main()
