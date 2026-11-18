# Tutorial 47: adaptive algorithms, a pre-trade estimate and a cost split that adds up

<!-- tutorial:only python -->

The plain idea: the schedules of [Tutorial 36](tutorial-36-slice-an-order.md) slice an order without looking at the market. An adaptive algorithm reacts to something. Arrival price trades early because waiting costs risk; a close algorithm puts what it can into the closing auction; liquidity seeking takes a share of the depth inside its limit; a pair keeps two legs in step so the cash stays balanced. Before trading, a pre-trade model estimates the cost; afterwards, attribution splits what it did cost into delay, impact and spread, which add up exactly.

You will rebuild five algorithm goldens, one pre-trade estimate and two attributions. Budget 15 minutes. All inputs are synthetic.

<p class="note">Available from v0.10.0 (unreleased). The operations `exec.algo.arrival`, `exec.algo.close`, `exec.algo.liquidity_seek`, `exec.algo.pair`, `exec.algo.basket` (H-14), `exec.tca.pretrade` and `exec.tca.attribution` (H-17) are specified and implemented on a branch not yet merged, so this page restates the spec formulas in plain Python. Every number is a golden from <code>specifications/10-execution/adaptive-algos.md</code> or <code>tca-pretrade.md</code>; a second lane re-derived them blind from the inputs alone (25 of 25 and 11 of 11 agree, <code>program/STAGE_H_BLIND_EXEC.md</code> on that branch).</p>

Terms, defined here. `X` is the order, `N` the number of buckets, `kappa` the urgency per bucket. The **close auction** takes `min(X, p_c V_c)` for participation cap `p_c` and forecast closing volume `V_c`. `alpha` is the share of in-limit depth liquidity seeking takes. For pre-trade, **I-star** is `a1 (X/ADV)^a2 sigma^a3` in bp, with parameters as inputs (the textbook form is recalled from [Kis13], not verified); **timing risk** is one standard deviation of the price move over the trading time, not added to the expected cost. For attribution, `m_0` is the mid at arrival and `m_i` the mid at fill `i`.

## What you need

- A clone of the repository, with commands run from its root.
- [uv](https://docs.astral.sh/uv/): `uv sync --locked --project python`. The script uses the Python standard library only.

## Step 1: check the numbers

<!-- tutorial:run python -->
```python
# Adaptive algorithms and TCA restated from the specs, goldens alg_h-0002, 0004, 0007, 0012, 0019 and tcx_h-0001, 0006, 0008.
import math
from fractions import Fraction as F

# Arrival price: holdings x_j = X sinh(kappa (N - j)) / sinh(kappa N); with kappa = ln 2, sinh is rational.
sinh = {0: F(0), 1: F(3, 4), 2: F(15, 8), 3: F(63, 16)}  # sinh(n ln 2)
for case, x, n in (("alg_h-0002", 1000, 2), ("alg_h-0004", 2100, 3)):
    hold = [x * sinh[n - j] / sinh[n] for j in range(n + 1)]
    print(case, "arrival slices", [str(hold[j - 1] - hold[j]) for j in range(1, n + 1)])

# Close: the auction takes min(X, p_c V_c); the rest follows the profile.
x, auction, profile = 10000, min(10000, F(1, 10) * 50000), [1, 1, 2, 4]
print("alg_h-0007 close auction", auction, "slices", [str((x - auction) * w / sum(profile)) for w in profile])

# Liquidity seeking: take alpha of the depth inside the limit, walking the levels best first.
remaining, notional, slices = F(1000), F(0), []
for book in ([("100.0", 400), ("100.1", 400), ("100.3", 1000)], [("100.1", 600), ("100.2", 600)]):
    inside = [(F(p), q) for p, q in book if F(p) <= F("100.2")]
    child = min(remaining, F(1, 2) * sum(q for _, q in inside))
    left = child
    for p, q in inside:
        take = min(left, q)
        notional, left = notional + take * p, left - take
    slices.append(str(child))
    remaining -= child
print("alg_h-0012 liquidity seek slices", slices, "avg fill price", float(notional / 1000))

# Cash-balanced pair in units: leg B follows leg A's cumulative quantity times P_A / P_B, rounded half up.
a = [334, 333, 333]
cum_a = [sum(a[: j + 1]) for j in range(3)]
cum_b = [math.floor(F(3, 7) * c + F(1, 2)) for c in cum_a]
print("alg_h-0019 pair slices_b", [cum_b[0], cum_b[1] - cum_b[0], cum_b[2] - cum_b[1]],
      "cash imbalance", [ca * 30 - cb * 70 for ca, cb in zip(cum_a, cum_b)])

# Pre-trade estimate: I* = a1 (X/ADV)^a2 sigma^a3, impact b1 I* p^a4 + (1 - b1) I*, timing risk 1e4 sigma sqrt(T/3).
istar = 700 * (40000 / 1000000) ** 0.5 * 0.02
impact = 0.9 * istar * 0.25 ** 0.5 + 0.1 * istar
days = 40000 / (0.25 * 1000000)
print(f"tcx_h-0001 pretrade istar {istar:.12g} impact {impact:.12g} expected {1.5 + impact:.12g} bp,"
      f" duration {days:g} days, timing risk {1e4 * 0.02 * math.sqrt(days / 3):.12g} bp")


def attribution(s, x, p_d, m0, p_c, fills, fees):
    q = sum(f[0] for f in fills)
    parts = {"delay": s * q * (m0 - p_d),
             "impact": s * sum(fq * (m - m0) for fq, _, m in fills),
             "spread": s * sum(fq * (p - m) for fq, p, m in fills),
             "opportunity": s * (x - q) * (p_c - p_d), "fees": fees}
    total = sum(parts.values())
    assert parts["delay"] + parts["impact"] + parts["spread"] == s * sum(fq * (p - p_d) for fq, p, _ in fills)
    return {k: str(v) for k, v in parts.items()}, str(total), f"{float(total / (x * p_d) * 10000):.12g}"


print("tcx_h-0006", *attribution(1, 1000, F(100), F("100.10"), F(101),
                                  [(600, F("100.20"), F("100.15")), (200, F("100.30"), F("100.25"))], 5))
print("tcx_h-0008", *attribution(1, 100, F("99.5"), F(100), F(100), [(100, F(100), F("100.05"))], 0))
```

Output (CI checks these lines):

<!-- tutorial:expect -->
```text
alg_h-0002 arrival slices ['600', '400']
alg_h-0004 arrival slices ['1100', '600', '400']
alg_h-0007 close auction 5000 slices ['625', '625', '1250', '2500']
alg_h-0012 liquidity seek slices ['400', '600'] avg fill price 100.06
alg_h-0019 pair slices_b [143, 143, 143] cash imbalance [10, -10, -30]
tcx_h-0001 pretrade istar 2.8 impact 1.54 expected 3.04 bp, duration 0.16 days, timing risk 46.1880215352 bp
tcx_h-0006 {'delay': '80', 'impact': '60', 'spread': '40', 'opportunity': '200', 'fees': '5'} 385 38.5
tcx_h-0008 {'delay': '50', 'impact': '5', 'spread': '-5', 'opportunity': '0', 'fees': '0'} 50 50.2512562814
```

### Reading the numbers

- **Arrival price.** With `kappa = ln 2` every `sinh` ratio is rational, so the front-loading is exact: 1,000 over two buckets is 600 then 400; 2,100 over three is 1,100, 600, 400 (`alg_h-0002`, `0004`). With `kappa = 0` it is TWAP.
- **Close.** A 10 % cap on 50,000 of closing volume puts 5,000 in the auction; the other 5,000 follow the profile 1, 1, 2, 4 (`alg_h-0007`).
- **Liquidity seeking.** Bucket 1 has 800 inside the 100.2 limit (the 100.3 level is outside), so the child is 400, all at 100.0; bucket 2 has 1,200, and the child is the 600 left, at 100.1. Average 100.06 (`alg_h-0012`).
- **Pair.** Buying 1,000 at 30 against selling at 70 needs 3/7 of a share of B per share of A. Rounding the cumulative target keeps the cash imbalance within half a B price (35) in every bucket: 10, -10, -30 (`alg_h-0019`).
- **Pre-trade.** 4 % of ADV at 2 % daily volatility: I-star 2.8 bp, impact at 25 % participation 1.54 bp, plus 1.5 bp half spread, 3.04 bp expected. The order takes 0.16 days, and the price may wander 46.2 bp (one SD) in that time: risk dwarfs expected cost (`tcx_h-0001`).
- **Attribution.** The buy of [Tutorial 38](tutorial-38-implementation-shortfall.md) again: delay 80, then the execution cost of 100 splits into impact 60 (the mid rose while we traded) and spread 40 (what we paid over the mid); total 385, 38.5 bp, the same total as `exec.tca.shortfall` (`tcx_h-0006`). A fill below the mid gives a negative spread, price improvement (`tcx_h-0008`).

### The formal statement, checked against the spec

From `specifications/10-execution/adaptive-algos.md` and `tca-pretrade.md` (available from v0.10.0; rulings HR-59 to HR-67).

- Arrival holdings `x_j = X sinh(kappa (N - j)) / sinh(kappa N)` ([AC00] eq. (17) with one bucket per step); UNITS allocation by largest remainder, ties to the earliest bucket (HR-67), so `kappa = 0` equals TWAP in units too.
- Pre-trade: `impact_bps = b1 I* p^a4 + (1 - b1) I*`, `T = X / (p ADV)`, `timing_risk_bps = 1e4 sigma sqrt(T / 3)` (the [AC00] eq. (10) straight-line variance as N grows).
- Attribution: delay `s Q (m_0 - P_d)`, impact `s sum q_i (m_i - m_0)`, spread `s sum q_i (p_i - m_i)`, opportunity `s (X - Q)(P_c - P_d)`. Acceptance H-17: delay + impact + spread equals `s sum q_i (p_i - P_d)` within 1e-10; the script asserts it exactly.

## For practitioners

- **No forecasting.** Closing volume, the profile and the books are inputs; the algorithms are only as good as those forecasts.
- **The pre-trade parameters fit nothing yet.** `a1` to `a4` and `b1` are inputs, and the spec makes no claim that they match any venue; calibration is the research lane's job.
- **Attribution needs the mid at each fill.** With a stale mid, the impact/spread split is wrong even though the total stays right.

## Common mistakes

- **Adding timing risk to expected cost.** One is a mean, the other a standard deviation; the spec keeps them apart.
- **Rounding each leg-B slice on its own.** Rounding the cumulative target is what bounds the cash imbalance.

## What you just did

You rebuilt five adaptive schedules, estimated an order's cost and risk before trading, and split a trade's cost into parts that sum to the shortfall total.

## Try next

- Set `alpha` to 1 in the liquidity-seeking case and predict both slices.

## References and further reading

- R. Almgren, N. Chriss, "Optimal execution of portfolio transactions", *Journal of Risk* 3(2), 2000/01.
- R. Kissell, *The Science of Algorithmic Trading and Portfolio Management*, 2013 (recalled, not verified in the spec).
- This project: the two specs above and [`tca.md`](../../specifications/10-execution/tca.md); all sources in [References](../references.md).
