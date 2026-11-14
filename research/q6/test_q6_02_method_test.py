"""Checks for Q6-02 (plan J-11). Never draws seed 20261113: that seed is the one guarded real run."""
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import q6_02_method_test as q


class Loss(unittest.TestCase):
    def test_rho_is_square_inside_and_linear_outside(self):
        e = np.array([-3.0, -1.0, 0.0, 0.5, 1.0, 2.0])
        np.testing.assert_allclose(q.rho(e), [5.0, 1.0, 0.0, 0.25, 1.0, 3.0])

    def test_penalty_ignores_a_pure_level_move(self):
        _, qs = q.draw(2, 5)
        x = np.asarray(q.g.x_start(qs[0]), dtype=float)
        sig = np.ones(45)
        prev = (q.grid_vols(x), q.atm_on_grid(x), sig)
        self.assertAlmostEqual(q.day_loss(x, qs[1], 1.0, prev), q.day_loss(x, qs[1], 0.0, None))
        prev_shift = (q.grid_vols(x) + 0.01, q.atm_on_grid(x) + 0.01, sig)  # same move at every node and at the ATM
        self.assertAlmostEqual(q.day_loss(x, qs[1], 3.0, prev_shift), q.day_loss(x, qs[1], 0.0, None))
        prev_tilt = (q.grid_vols(x) + 0.01, q.atm_on_grid(x), sig)  # a shape change is penalised
        self.assertGreater(q.day_loss(x, qs[1], 1.0, prev_tilt), q.day_loss(x, qs[1], 0.0, None))

    def test_sigma_is_positive_and_near_quote_noise_scale(self):
        _, qs = q.draw(1, 6)
        x = np.asarray(q.g.x_start(qs[0]), dtype=float)
        s = q.sigma_grid(x, qs[0])
        self.assertEqual(s.shape, (45,))
        self.assertTrue(np.all(s >= q.SIGMA_FLOOR))
        self.assertLess(float(np.median(s)), 0.01)  # quote noise sd is h/2 = 0.001 at the money

    def test_draw_order_matches_q6_01(self):
        _t1, qs1 = q.draw(3, 11)
        rng = np.random.default_rng(11)
        t2 = q.g.truth_path(3, rng)
        q0 = q.g.quotes(t2[0], rng, None)
        np.testing.assert_array_equal(qs1[0]["mid"], q0["mid"])


class Run(unittest.TestCase):
    def test_short_run_with_known_answer(self):
        out = q.main(days=15, seed=7)
        self.assertEqual([t["lambda"] for t in out["trials"]], [0, 1, 3])
        self.assertIn(out["result"], ("PASS", "FAIL"))
        self.assertLess(out["rms_error_to_truth_on_grid_vol"], 0.005)


class Guard(unittest.TestCase):
    def test_refuses_unsigned_missing_edited_or_second_run(self):
        with tempfile.TemporaryDirectory() as d:
            p, o = Path(d) / "p.md", Path(d) / "o.json"
            with self.assertRaises(SystemExit):
                q.guard(p, o)  # missing
            p.write_text("Status: draft, unsigned.\n<!-- body -->\nx\n", encoding="utf-8")
            with self.assertRaises(SystemExit):
                q.guard(p, o)  # unsigned
            p.write_text("Status: **signed**\n- body `0000`\n<!-- body -->\nx\n", encoding="utf-8")
            with self.assertRaises(SystemExit):
                q.guard(p, o)  # body hash wrong
            o.write_text("{}", encoding="utf-8")
            with self.assertRaises(SystemExit):
                q.guard(q.PREREG, o)  # output exists: run once

    def test_refuses_when_a_frozen_file_hash_differs(self):
        import hashlib
        with tempfile.TemporaryDirectory() as d:
            body = b"x\n"
            head = (f"Status: **signed**\n- `{hashlib.sha256(body).hexdigest()}`\n"
                    f"- `q6_02_method_test.py` (whole file): `{'0' * 64}`\n").encode()
            p = Path(d) / "p.md"
            p.write_bytes(head + q.MARK + body)
            with self.assertRaisesRegex(SystemExit, "q6_02_method_test.py differs"):
                q.guard(p, Path(d) / "o.json")


if __name__ == "__main__":
    unittest.main()
