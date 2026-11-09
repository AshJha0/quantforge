"""R3-02 outcome as a P&L (amendment 1, item R2). numpy only.

Position +1 = long a 13-week bill financed overnight; -1 = the reverse. Per unit of bill price at entry:

    pnl = (P_exit - P_entry) / P_entry  -  (F - 1)
        = carry + price change, with
    carry        = y_mm,entry * h / 360 - (F - 1)                  (bill yield earned less realised funding)
    price change = (P_exit - P_entry) / P_entry - y_mm,entry * h / 360

where h is the holding period in calendar days and F = prod_i (1 + r_i * n_i / 360) is realised
compounded overnight funding (SOFR, TGCR or BGCR are ACT/360; NY Fed methodology).

Day-count conversion. Treasury publishes the 13-week rate as a coupon-equivalent (bond-equivalent)
yield, y_ce = 365 d / (360 - d t) for discount rate d and t days to maturity (Treasury, "Daily Treasury
Bill Rates" interpretation note; 366 replaces 365 when the year after issue contains 29 February).
The money-market (ACT/360) yield on the same price is y_mm = 360 d / (360 - d t), so

    y_mm = y_ce * 360 / B,   B = 365 or 366,   and   P = 1 / (1 + y_mm t / 360).

The exit price uses the 13-week rate on the exit day for the remaining t - h days: no roll-down
(a stated limit: the 9-week point is not in the same series).
"""
import math

import numpy as np


def ce_to_mm(y_ce, basis=365):
    """Coupon-equivalent bill yield (decimal) to ACT/360 money-market yield."""
    if basis not in (365, 366):
        raise ValueError("basis is 365 or 366")
    return np.asarray(y_ce, dtype=float) * 360.0 / basis


def bill_price(y_mm, days):
    return 1.0 / (1.0 + np.asarray(y_mm, dtype=float) * days / 360.0)


def realised_funding(rates, day_counts):
    """F - 1 for overnight ACT/360 fixings `rates` (decimal), each accruing `day_counts` calendar days."""
    return float(np.prod(1.0 + np.asarray(rates, dtype=float) * np.asarray(day_counts, dtype=float) / 360.0) - 1.0)


def holding_pnl(y_mm_entry, y_mm_exit, rates, day_counts, maturity=91):
    """(carry, price change) for a long bill financed overnight, per unit of entry price."""
    h = int(np.sum(day_counts))
    p0 = bill_price(y_mm_entry, maturity)
    p1 = bill_price(y_mm_exit, maturity - h)
    carry = y_mm_entry * h / 360.0 - realised_funding(rates, day_counts)
    price = (p1 - p0) / p0 - y_mm_entry * h / 360.0
    return float(carry), float(price)


def calendar_days(n):
    """Calendar days accrued per business-day fixing in a Mon-Fri week with no holidays: 1,1,1,1,3."""
    return np.array([3 if i % 5 == 4 else 1 for i in range(n)])


def strategy_returns(bill_mm, funding, L=60, k=1.0, trail=20, hold=21, outcome="pnl"):
    """Monthly non-overlapping entries every `hold` business days, signal as preregistered:
    s_t = bill_mm_t - trailing `trail`-day mean of funding, z over trailing `L` days of s.
    outcome="pnl" is the amended outcome; outcome="spread" is the original (change in s), kept only so
    tests can show its spurious predictability."""
    bill_mm = np.asarray(bill_mm, dtype=float)
    funding = np.asarray(funding, dtype=float)
    n = len(funding)
    dc = calendar_days(n)
    trailing = np.convolve(funding, np.ones(trail) / trail, mode="full")[:n]
    s = bill_mm - trailing
    out = []
    t = trail + L
    while t + hold < n:
        win = s[t - L + 1:t + 1]
        z = (s[t] - win.mean()) / win.std(ddof=1)
        pos = 1.0 if z > k else (-1.0 if z < -k else 0.0)
        if outcome == "pnl":
            c, pr = holding_pnl(bill_mm[t], bill_mm[t + hold], funding[t:t + hold], dc[t:t + hold])
            out.append(pos * (c + pr))
        else:
            out.append(pos * (s[t + hold] - s[t]))
        t += hold
    return np.array(out)


def annual_sharpe(r, per_year=12):
    r = np.asarray(r, dtype=float)
    return float(r.mean() / r.std(ddof=1) * math.sqrt(per_year))
