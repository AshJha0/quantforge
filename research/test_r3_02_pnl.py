import math
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import r3_02_pnl as m  # noqa: E402


class R302PnlTest(unittest.TestCase):
    def test_day_count_conversion_round_trips_price(self):
        d, t = 0.05, 91  # discount rate, days
        price = 1 - d * t / 360
        y_ce = 365 * d / (360 - d * t)
        self.assertAlmostEqual(float(m.bill_price(m.ce_to_mm(y_ce), t)), price, places=14)
        self.assertAlmostEqual(float(m.ce_to_mm(0.0366, basis=366)), 0.036, places=14)

    def test_constant_rates_give_zero_pnl_when_bill_equals_funding(self):
        dc = m.calendar_days(21)
        h = dc.sum()
        y = 0.04
        # daily funding chosen so compounded funding equals simple bill accrual over h days
        r = (math.exp(math.log(1 + y * h / 360) / len(dc)) - 1) * 360 / dc  # not constant, but exact
        c, p = m.holding_pnl(y, y, r, dc)
        self.assertAlmostEqual(c, 0.0, places=12)
        self.assertLess(abs(p), 1e-4)  # flat yield: price term is only the second-order compounding gap
        total = float(m.bill_price(y, 91 - h) / m.bill_price(y, 91)) - 1 - m.realised_funding(r, dc)
        self.assertAlmostEqual(c + p, total, places=12)

    def test_iid_funding_constant_bill_has_sharpe_about_zero(self):
        # 400 years of business days; i.i.d. SOFR around 4% (sd 10 bp); bill fixed at the funding mean.
        rng = np.random.default_rng(20261109)
        n = 252 * 400
        funding = 0.04 + 0.001 * rng.standard_normal(n)
        bill = np.full(n, 0.04)  # already on ACT/360
        r = m.strategy_returns(bill, funding)
        nobs = (r != 0).sum()
        self.assertGreater(nobs, 1000)
        sr = m.annual_sharpe(r)
        band = 3 * math.sqrt(12 / len(r))  # 3 SE of an annualised SR from len(r) monthly outcomes
        self.assertLess(abs(sr), band, (sr, band))
        # the original outcome (change in the spread against a trailing mean) shows spurious
        # predictability on the same noise: |SR| far outside the band (about -1.7 with this seed)
        self.assertGreater(abs(m.annual_sharpe(m.strategy_returns(bill, funding, outcome="spread"))), 1.0)


if __name__ == "__main__":
    unittest.main()
