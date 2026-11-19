# Tutorial 57: the backtesting traffic light, from the binomial distribution

<!-- tutorial:only python -->

The plain idea: a bank that uses its own model for market risk capital checks every day whether the loss it made was bigger than the model's one-day 99% value at risk. A correct model should be beaten about 2.5 days in 250. The regulator turns the count into a colour: green (nothing to see), amber (suspicious; capital goes up) and red (the model is almost certainly wrong). The boundaries are not judgement: amber starts at the count that a correct model stays at or under 95% of the time, red at 99.99%.

You will rebuild the published table of cumulative probabilities from the binomial distribution, find the zone boundaries for 250 and 500 days, see a literal reading of the rule give an odd answer for five days, and apply the desk exception limits. Budget 10 minutes.

<p class="note">Stage K. The operations <code>risk.frtb.backtest.zone</code>, <code>.desk</code> and <code>.count</code> are on the integration branch <code>k-r1</code> in all four builds (merged 2026-11-19; not in a tag) and registered in the CLI contract 1.17.0 (spec <code>specifications/06-risk/frtb-ima-backtest.md</code> 0.1.0, rulings KR-40 to KR-47). The published table (MAR99 Table 2) matches for the new operation and for the existing stage F <code>risk.backtest.traffic_light</code>. Outside share of <code>btk_k</code>: 23 of 24 value cases, 12 against the printed table and 11 by blind re-derivation (<code>program/STAGE_K_BLIND_BTK.md</code>). Step 1 uses the standard library in exact rational arithmetic; Step 2 calls the library, and CI checks that it prints the lines shown under Step 1.</p>

Terms, defined here. An **exception** is a day whose loss exceeds the VaR (strictly: a loss equal to VaR is not one; a missing P&L or VaR counts as one). **Actual** P&L includes the day's trading; **hypothetical** P&L revalues the start-of-day positions only; the count used is the larger of the two. `X ~ Binomial(n, 0.01)` is the exception count of a correct 99% model over `n` days, and `cdf(k) = P(X <= k)`.

## What you need

- A clone of the repository, with commands run from its root.
- [uv](https://docs.astral.sh/uv/): `uv sync --locked --project python`. Step 1 uses the Python standard library only.

## Step 1: the table, the zones and the desk limits

```python
# FRTB backtesting zones (risk.frtb.backtest.zone, MAR32 and MAR99) by the binomial rule, standard library only.
from fractions import Fraction as F
from math import comb

MULT = {0: 1.50, 1: 1.50, 2: 1.50, 3: 1.50, 4: 1.50, 5: 1.70, 6: 1.76, 7: 1.83, 8: 1.88, 9: 1.92}  # MAR32 Table 1


def cdf(n, p=F(1, 100)):  # exact P(X <= k) for X ~ Binomial(n, p), k = 0..n
    out, run = [], F(0)
    for k in range(n + 1):
        run += comb(n, k) * p**k * (1 - p) ** (n - k)
        out.append(run)
    return out


def zone(n, actual, hypothetical):
    c, x = cdf(n), max(actual, hypothetical)  # MAR99.8: the greater of the two counts
    amber = next(k for k in range(n + 1) if c[k] >= F(95, 100))
    red = next(k for k in range(n + 1) if c[k] >= F(9999, 10000))
    z = "RED" if x >= red else "AMBER" if x >= amber else "GREEN"
    m = (MULT.get(x, 2.00) if n == 250 else None)
    return x, float(c[x]), z, amber, red, m


c250 = cdf(250)
printed = ["8.11", "28.58", "54.32", "75.81", "89.22", "95.88", "98.63", "99.60", "99.89", "99.97", "99.99"]  # MAR99 Table 2
row = [f"{100 * float(c250[k]):.2f}" for k in range(11)]
print("cumulative % at 250, 0 to 10 exceptions:", " ".join(row))
print("equal to MAR99 Table 2:", row == printed)
x, prob, z, amber, red, m = zone(250, 3, 5)
print(f"250 days, 3 actual and 5 hypothetical: exceptions {x} cumulative {prob:.6f} zone {z} amber from {amber} red from {red} multiplier {m:.2f}")
x, prob, z, amber, red, m = zone(500, 3, 5)
print(f"500 days, same counts: zone {z} amber from {amber} red from {red} multiplier {m}")
x, prob, z, amber, red, m = zone(5, 0, 0)
print(f"5 days, no exceptions: P(X = 0) = 0.99^5 = {prob:.6f}, zone {z} (KR-42, the rule as written)")
for x99, x975 in ((12, 30), (13, 30), (12, 31)):  # MAR32.19: "more than 12" at 99 %, "30" at 97.5 % (KR-44)
    print(f"desk, 250 days: 99% exceptions {x99}, 97.5% exceptions {x975}: eligible {not (x99 > 12 or x975 > 30)}")
```

Output (CI checks that Step 2 prints these lines):

<!-- tutorial:expect -->
```text
cumulative % at 250, 0 to 10 exceptions: 8.11 28.58 54.32 75.81 89.22 95.88 98.63 99.60 99.89 99.97 99.99
equal to MAR99 Table 2: True
250 days, 3 actual and 5 hypothetical: exceptions 5 cumulative 0.958817 zone AMBER amber from 5 red from 10 multiplier 1.70
500 days, same counts: zone GREEN amber from 9 red from 15 multiplier None
5 days, no exceptions: P(X = 0) = 0.99^5 = 0.950990, zone AMBER (KR-42, the rule as written)
desk, 250 days: 99% exceptions 12, 97.5% exceptions 30: eligible True
desk, 250 days: 99% exceptions 13, 97.5% exceptions 30: eligible False
desk, 250 days: 99% exceptions 12, 97.5% exceptions 31: eligible False
```

### Reading the numbers: the binomial reasoning

- **Where the table comes from.** For a correct model each day is an independent coin with probability 1% of an exception, so over 250 days `P(X = k) = C(250, k) 0.01^k 0.99^(250 - k)`. `P(X = 0) = 0.99^250 = 8.11%`; adding up gives 28.58% for at most one, and so on. Rounded to two decimals the eleven values equal MAR99 Table 2 exactly (MAR99.17, p.758, read by the k-w1b lane).
- **The boundaries.** `cdf(4) = 89.22% < 95% <= cdf(5) = 95.88%`, so amber starts at 5, the first count at which the cumulative probability reaches 95% (MAR99.17's rule). Read the other way: a correct model shows 5 or more exceptions with probability `1 - cdf(4) = 10.78%`, which is the chance of wrongly leaving green. `cdf(9) = 99.97% < 99.99% <= cdf(10)`, so red starts at 10; a correct model reaches 10 or more with probability `1 - cdf(9) = 0.025%`.
- **The greater count.** With 3 actual and 5 hypothetical exceptions the count is 5 (MAR99.8): amber, multiplier 1.70 (MAR32 Table 1). Using only the actual count would hide a model that is wrong on the static book.
- **Other sample sizes.** The same rule at 500 days gives amber from 9 and red from 15, so 5 exceptions in 500 days is green. No multiplier is published for 500 days, so the operation returns none (KR-42).
- **A literal reading.** For `n <= 5`, `P(X = 0) = 0.99^n >= 0.95`, so by the rule as written zero exceptions is already amber. The spec applies the rule as written and states it (KR-42) rather than inventing a fix.
- **Desk limits.** A trading desk loses permission to use its model with more than 12 exceptions at 99% or more than 30 at 97.5% in the last 12 months (MAR32.19). 12 and 30 are still eligible; 13 or 31 is not. "More than ... 30" is a reading of ambiguous text (KR-44), pinned by goldens and flagged inferred.

### The formal statement, checked against the spec

From `specifications/06-risk/frtb-ima-backtest.md` 0.1.0 (MAR32 pp.658 to 668 and MAR99 pp.753 to 761 of the Basel Framework PDF of 11/11/2026, read 2026-11-19).

- `amber_from = min{k : cdf(k) >= 0.95}`, `red_from = min{k : cdf(k) >= 0.9999}`. Exceptions `x = max(x_actual, x_hypothetical)`. RED if `x >= red_from`, AMBER if `x >= amber_from`, else GREEN. Multiplier at `n = 250`: 1.50 for 0 to 4, 1.70, 1.76, 1.83, 1.88, 1.92 for 5 to 9, 2.00 from 10; null for any other `n`.
- Desk: `breach_99 = x99 > 12`, `breach_975 = x975 > 30`, `eligible` = neither.
- Count: day `t` is an exception when VaR or P&L is null, or when `-P&L_t > VaR_t` (strict; KR-45).
- Relation to stage F (KR-40): `risk.backtest.traffic_light` implements the 1996 framework (zones GREEN, YELLOW, RED and a plus factor on a multiplier of 3). The FRTB operations are new operations, not an extension, because the output, the count rule and the desk test all differ. Both agree on the zone and the cumulative probability at every count; suite `tlk_k` checks the existing operation against MAR99 Table 2 (YELLOW = amber).
- Acceptance (fixed before the goldens): Table 2 rows 0 to 10 for both operations, and every value within 1e-12 relative of `scipy.stats.binom.cdf`. Result (measured by the k-w1b lane, 2026-11-19): all rows match; MAR99 Table 1 (176 printed numbers) also matches SciPy at one decimal.
- Outside share (handover table): `btk_k` 23 of 24 value cases (96%), `tlk_k` 11 of 11, if `binom.cdf` counts as a library check. Whether it does, when `binom.cdf` is itself the compared quantity, is the coordinator's classification decision (handover, "Outside-check share").
- Not covered (KR-47): the P&L attribution test, the 10% eligibility criterion, the NMRF waiver, the qualitative add-on and capital.

## Step 2: the same questions through the library

This block calls the library on the goldens in `datasets/golden/stage_k/`. It was turned on at integration (2026-11-19) and printed the same lines as Step 1; CI now checks them.

<!-- tutorial:run python -->
```python
# MAR99 Table 2 from golden tlk_k (existing operation), then risk.frtb.backtest.zone and .desk.
import json

from quantforge_core.cli.main import run_case


def call(op, inputs):
    r = run_case(json.dumps({"schema_version": "1.0", "case_id": "t57", "operation": op, "inputs": inputs}))
    return r["outputs"]


tlk = json.load(open("datasets/golden/stage_k/tlk_k.json", encoding="utf-8"))["cases"]
row = [f"{100 * call(c['operation'], c['inputs'])['cumulative_probability']:.2f}" for c in tlk]
printed = ["8.11", "28.58", "54.32", "75.81", "89.22", "95.88", "98.63", "99.60", "99.89", "99.97", "99.99"]
print("cumulative % at 250, 0 to 10 exceptions:", " ".join(row))
print("equal to MAR99 Table 2:", row == printed)


def zone(n, a, h):
    o = call("risk.frtb.backtest.zone", {"observations": n, "exceptions_actual": a, "exceptions_hypothetical": h})
    return o["exceptions"], o["cumulative_probability"], o["zone"], o["amber_from"], o["red_from"], o["multiplier"]


x, prob, z, amber, red, m = zone(250, 3, 5)
print(f"250 days, 3 actual and 5 hypothetical: exceptions {x} cumulative {prob:.6f} zone {z} amber from {amber} red from {red} multiplier {m:.2f}")
x, prob, z, amber, red, m = zone(500, 3, 5)
print(f"500 days, same counts: zone {z} amber from {amber} red from {red} multiplier {m}")
x, prob, z, amber, red, m = zone(5, 0, 0)
print(f"5 days, no exceptions: P(X = 0) = 0.99^5 = {prob:.6f}, zone {z} (KR-42, the rule as written)")
for x99, x975 in ((12, 30), (13, 30), (12, 31)):
    o = call("risk.frtb.backtest.desk", {"observations": 250, "exceptions_99_actual": x99, "exceptions_99_hypothetical": 0,
                                         "exceptions_975_actual": x975, "exceptions_975_hypothetical": 0})
    print(f"desk, 250 days: 99% exceptions {x99}, 97.5% exceptions {x975}: eligible {o['eligible']}")
```

## For practitioners

- **Green is not proof.** A model that is too conservative also stays green. The traffic light tests one side only; the Kupiec and Christoffersen tests ([Tutorial 5](tutorial-5-risk.md)) and the ES backtest ([Tutorial 26](tutorial-26-test-es-and-fit-regimes.md)) look at more.
- **A wrong verdict is built in.** About one correct model in nine (10.78%) leaves green in a given year by chance. Amber is a reason to look and to hold more capital, not proof of a bad model.
- **Missing data counts against you.** A day with no P&L or no VaR is an exception (MAR32.5(2)); a data gap is not neutral.

## Common mistakes

- **Reading `cdf(k) >= 95%` as "a correct model reaches k with probability 5%".** The amber boundary is where the cumulative probability of *at most* `k` first reaches 95%. The chance of `k` or more is `1 - cdf(k - 1)`: 10.78% for 5, 4.12% for 6.
- **Using only the actual P&L count.** The rule takes the larger of actual and hypothetical.

## What you just did

You rebuilt the Basel backtesting table from the binomial distribution in exact arithmetic, found where amber and red start for two sample sizes, saw a literal reading of the rule at five days, and applied the desk exception limits.

## Try next

- Find `amber_from` and `red_from` for 1,000 days with the same rule, by hand first (golden `btk_k-0016`).

## References and further reading

- This project: `specifications/06-risk/frtb-ima-backtest.md`, `specifications/06-risk/frtb-ima-backtest-tables.json`, `specifications/stage-k-rulings-w1b.md`; the stage F traffic light in [`var-es-and-backtests.md`](../../specifications/06-risk/var-es-and-backtests.md) and [Tutorial 5](tutorial-5-risk.md).
- Basel Committee on Banking Supervision, *The Basel Framework*, MAR32 (backtesting and P&L attribution) and MAR99 (guidance on the internal models approach, Tables 1 and 2), consolidated PDF generated 11/11/2026 (read by the k-w1b lane, 2026-11-19).
