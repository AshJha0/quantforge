"""Recompute every worked-example number in docs/question-bank/14-stage-k-risk-platform.md and check the strings.

Stage K round 1 is on lane branches (k-w1, k-k8, k-w1b, k-paper) that are not merged yet, so this script restates
the spec formulas with the standard library and compares them with golden values copied from those branches (each
constant names its golden file). After the merge the constants can be replaced by reads of
datasets/golden/stage_k/*.json (program/STAGE_K_DOCS_PENDING.md).

Run: python docs/question-bank/verify/v14_stage_k.py   (no package needed)
"""
from __future__ import annotations

import math
import statistics
from decimal import ROUND_HALF_EVEN, Decimal as D
from fractions import Fraction as F
from math import comb
from pathlib import Path

TEXT = (Path(__file__).resolve().parents[1] / "14-stage-k-risk-platform.md").read_text(encoding="utf-8")
checks = 0


def has(s: str) -> None:
    global checks
    assert s in TEXT, f"missing in 14-stage-k-risk-platform.md: {s!r}"
    checks += 1


def close(a: float, b: float, tol: float = 1e-9) -> None:
    assert abs(a - b) <= tol * max(1.0, abs(b)), (a, b)


# Q14.1, 14.2, 14.4: the KR-2 rule on the shared log of bt_k (k-w1: datasets/golden/stage_k/bt_k.json).
LOG = [(1, (1, 1), None, (1, 2), 100, False), (2, (3, 1), None, (3, 2), 110, False),
       (3, (2, 1), (3, 1), (4, 1), 105, False), (4, (3, 1), None, (4, 2), None, True)]  # (month, day) of 2026


def bt(k, v):
    c = [r for r in LOG if r[3] <= k and r[1] <= v and (r[2] is None or v < r[2])]
    if not c:
        return "NONE", None
    w = max(c, key=lambda r: r[0])
    return ("WITHDRAWN", None) if w[5] else ("FOUND", (w[0], w[4]))


assert bt((3, 15), (2, 15)) == ("FOUND", (1, 100)) and bt((4, 1), (2, 15)) == ("FOUND", (3, 105))
assert bt((4, 5), (3, 10)) == ("WITHDRAWN", None) and bt((4, 5), (1, 15)) == ("FOUND", (1, 100))
assert bt((4, 1), (3, 1)) == ("FOUND", (2, 110)) and bt((4, 1), (2, 28.99)) == ("FOUND", (3, 105))
has("record 4 has the largest sequence, so the answer is `WITHDRAWN`")
has("record 2 answers 110 (`bt_k-0007`)")

# Q14.5 to 14.7: inc_k (k-w1).
def boot(q):
    p, t = [], 0.0
    for s in q:
        p.append((1 - s * t) / (1 + s))
        t += p[-1]
    return p


p0, p2 = boot([0.02, 0.025, 0.03]), boot([0.02, 0.026, 0.03])
for a, b in zip(p0, [0.980392156862745098, 0.951697752271640363, 0.914599323034920812]):
    close(a, b, 1e-15)
assert repr(p0[1]) == "0.9516977522716404" and repr(p0[2]) == "0.9145993230349208"
close(p2[1], 0.949814623705232580, 1e-15)
close(p2[2], 0.914654171439767640, 1e-15)
has("`P_2 = 0.949815`, `P_3 = 0.914654`")
has("binary64 gives 0.9516977522716404")

# Q14.9 to 14.12: trig_k (k-w1).
a, b = [1, -1, 1, -1], [0.5, -1.0, 1.5, -0.5, 0.0, 1.0, -1.5, 0.0]
close(statistics.stdev(a), 1.1547005383792515, 1e-14)
close(3 * statistics.stdev(a), 3.4641016151377544, 1e-14)
close(3 * statistics.stdev(a) * 2, 6.928203230275509, 1e-14)
assert statistics.stdev(b) == 1.0 and statistics.pstdev(a) == 1.0
close(math.erfc(3 / math.sqrt(2)), 0.002699796063260189, 1e-14)
close(math.erfc(2.5 / math.sqrt(2)), 0.012419330651552265, 1e-14)
assert not abs(2.5 - 0) > 2.5 * 1.0 and abs(-2.5000001) > 2.5
has("threshold at `k = 3`, `d = 1` is 3.4641")
has("`3 x 1.1547 x 2 = 6.9282`")
has("`alpha = 0.012419`")


def binom_interval(n, p, level=0.99):
    lo, hi, cdf, first = (1 - level) / 2, (1 + level) / 2, 0.0, None
    for x in range(n + 1):
        cdf += math.exp(math.lgamma(n + 1) - math.lgamma(x + 1) - math.lgamma(n - x + 1) + x * math.log(p) + (n - x) * math.log1p(-p))
        if first is None and cdf >= lo:
            first = x
        if cdf >= hi:
            return first, x


assert binom_interval(100_000, 0.0030306) == (259, 349)
has("The interval is [259, 349]; Python fired 291 times and Java 287")

# Q14.13 to 14.15: idr_k (k-w1).
def pos(n, t, y, h):
    v = n * math.exp(-y * t)
    return v * (-t * h + t * t * h * h / 2), t**3 * abs(n) * math.exp(-t * min(y, y + h)) * abs(h) ** 3 / 6, n * math.exp(-(y + h) * t) - v


e, bd, ex = pos(1e6, 5, 0.04, 0.01)
close(e, -39913.124212551616)
close(bd, 17.05689068912462)
assert f"{1e6 * math.exp(-0.2):,.2f}" == "818,730.75" and f"{ex:,.2f}" == "-39,929.97" and f"{e - ex:.2f}" == "16.85"
has("estimate -39,913.12, exact -39,929.97, error 16.85, bound 17.06")
e, bd, ex = pos(1e6, 5, 0.04, -0.01)
close(bd, 17.93141617552204)
assert f"{e - ex:.2f}" == "-17.27"
has("the bound is 17.93 against 17.06")
parts = [pos(1e6, 5, 0.04, 0.01), pos(-5e5, 2, 0.03, 0.01)]
e, bd, ex = (sum(p[i] for p in parts) for i in range(3))
close(e, -30589.655330067555)
close(bd, 17.684733711514124)
assert f"{(e - ex) / bd:.3f}" == "0.917"
has("estimate -30,589.66, exact -30,605.88, error 16.22, bound 17.68, error over bound 0.917")

# Q14.17, 14.20: K-8 (k-k8: oracle/K8_ACCEPTANCE_W2.json; program/K8_DIAGNOSIS.md).
assert f"{math.log((-337.0 + 104.9) / (-104.9 - 11.1)) / math.log(2):.2f}" == "1.00"
has("differences -232.1 and -116.0, ratio 2, order 1.00")
f1, f2, f3, ref = 222756.97927658106, 223121.2511211628, 223212.47798442983, 223243.7217182066
assert f"{math.log((f1 - f2) / (f2 - f3)) / math.log(2):.3f}" == "1.997" and f"{100 * abs(f1 / ref - 1):.3f}" == "0.218"
has("222,756.98, 223,121.25, 223,212.48, order 1.997, 0.218% from the QuantLib reference")


def m(p, q):
    if p >= 0 and q >= 0:
        return p / 3 + q / 6
    if p > 0 > q:
        t = p * p / (2 * (p - q))
        return t - t * (p / (p - q)) / 3
    if p < 0 < q:
        r = q / (q - p)
        return q * r * r / 6
    return F(0)


ext = [F(-2), F(-1), F(0), F(1), F(2)]
h = [m(ext[i + 1], ext[i]) + m(ext[i + 1], ext[i + 2]) for i in range(3)]
assert h == [0, F(1, 6), 1] and h[1] - (h[0] - 2 * h[1] + h[2]) / 6 == F(1, 18)
has("`h = (0, 1/6, 1)`, `S_1 = 1/6 - (0 - 1/3 + 1)/6 = 1/18`")

# Q14.21 to 14.23: saccr_k-0001 (k-w1b: datasets/golden/stage_k/saccr_k.json; CRE99 Example 1).
def sd(s, e):
    return max((math.exp(-0.05 * s) - math.exp(-0.05 * e)) / 0.05, 10 / 250)


d1 = (math.log(1.2) + 0.125) / 0.5
delta = -0.5 * math.erfc(d1 / math.sqrt(2))
assert f"{d1:.4f}" == "0.6146" and f"{delta:.4f}" == "-0.2694"
D1, D2, D3 = 0.0, -10_000 * sd(0, 4), 10_000 * sd(0, 10)
en = math.sqrt(D1 * D1 + D2 * D2 + D3 * D3 + 1.4 * D1 * D2 + 1.4 * D2 * D3 + 0.6 * D1 * D3)
eur = abs(5_000 * sd(1, 11) * delta)
addon = 0.005 * (en + eur)
ead = 1.4 * (60 + addon)
close(ead, 569.4701409373457, 1e-12)
assert f"{en:,.0f}" == "59,270" and f"{-D2 + D3:,.0f}" == "114,948" and f"{eur:,.0f}" == "10,083" and f"{addon:.2f}" == "346.76"
assert f"{ead:.2f}" == "569.47" and f"{1.4 * 407:.1f}" == "569.8"
has("`EN = 59,270` against 114,948 gross; add-on `0.005 x 59,270 = 296.35`")
has("`EAD = 1.4 x 406.76 = 569.47`, printed 569")
has("`d1 = (ln 1.2 + 0.125)/0.5 = 0.6146`, `delta = -0.2694`")
assert 5 + 7 == 12 and f"{12 / 16:.0%}" == "75%"
has("12 of 16 value cases, 75%")

# Q14.25 to 14.28: binomial zones (k-w1b: MAR99 Table 2, btk_k).
def cdf(n, p=F(1, 100)):
    out, run = [], F(0)
    for k in range(n + 1):
        run += comb(n, k) * p**k * (1 - p) ** (n - k)
        out.append(run)
    return out


c = cdf(250)
assert [f"{100 * float(c[k]):.2f}" for k in (4, 5, 9, 10)] == ["89.22", "95.88", "99.97", "99.99"]
assert f"{100 * float(1 - c[4]):.2f}" == "10.78" and f"{float(c[5]):.6f}" == "0.958817"
has("`1 - P(X <= 4) = 10.78%`")
has("count 5, amber, cumulative 0.958817, multiplier 1.70")
c5 = cdf(5)
assert c5[0] >= F(95, 100) and f"{float(c5[0]):.6f}" == "0.950990"
c500 = cdf(500)
assert next(k for k in range(501) if c500[k] >= F(95, 100)) == 9 and next(k for k in range(501) if c500[k] >= F(9999, 10000)) == 15
has("`P(X = 0) = 0.99^5 = 0.950990 >= 0.95`")
has("amber from 9 and red from 15")

# Q14.29: the paper ledger worked day (k-paper: specifications/12-platform/paper-ledger-daily.md).
u, acc = D(26500), D("0.013287")
interest = (D("7349714.0625") * D("0.0428") / 365).quantize(D("0.01"), ROUND_HALF_EVEN)
carry = u * acc + interest
roll = u * (D("100.000625") - 100)
curve = u * (D("99.925390") - D("100.000625"))
fills = -(D("32.8125") + D("25.78125") + D("73.4375"))
assert 4200 * (D("100.0078125") - 100) == D("32.8125") and 2200 * (D("100.01171875") - 100) == D("25.78125")
assert 4700 * (D("100.015625") - 100) == D("73.4375") and (D("2.405") / 181).quantize(D("0.000001")) == acc
assert (carry, roll, curve) == (D("1213.9355"), D("16.5625"), D("-1993.7275"))
assert carry + roll + curve + fills == D("-895.26075") == D("9998818.80175") - D("9999714.0625")
has("sum -895.26075, equal to NAV 9,998,818.80175 minus 9,999,714.0625")

print(f"v14: {checks} strings checked")
