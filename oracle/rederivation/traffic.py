"""Backtesting traffic light from the Basel Framework PDF: MAR32.8-32.9 Table 1 (PDF p. 661), MAR99.9-99.17 and Table 2
(PDF pp. 758-759), MAR33.42 (PDF p. 684-685: plus factor ranges 0 to 0.5 on a base multiplier of 1.5)."""
from scipy.stats import binom
from math import comb

# MAR32.9 Table 1 "Backtesting dependent multiplier" for 250 observations (99%): exceptions -> multiplier
MULT = {0: 1.50, 1: 1.50, 2: 1.50, 3: 1.50, 4: 1.50, 5: 1.70, 6: 1.76, 7: 1.83, 8: 1.88, 9: 1.92}  # 10 or more: 2.00
BASE = 1.5  # MAR33.42: mc fixed at 1.5, plus added

def cum_prob(n, x, c):
    p = 1 - c
    return float(sum(comb(n, k) * p**k * (1 - p)**(n - k) for k in range(x + 1)))

def traffic_light(inp):
    n, x, c = inp['observations'], inp['exceptions'], inp['confidence']
    cp = cum_prob(n, x, c)
    # MAR99.17: amber begins where cumulative probability >= 95%; red where >= 99.99%
    zone = 'GREEN' if cp < 0.95 else ('YELLOW' if cp < 0.9999 else 'RED')
    pf = None
    if n == 250 and abs(c - 0.99) < 1e-12:
        m = MULT.get(x, 2.00)
        pf = round(m - BASE, 2)
    return dict(cumulative_probability=cp, plus_factor=pf, zone=zone,
                _cross_check_scipy=float(binom.cdf(x, n, 1 - c)))
