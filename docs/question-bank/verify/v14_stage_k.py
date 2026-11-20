"""Recompute every worked-example number in docs/question-bank/14-stage-k-risk-platform.md and check the strings.

Stage K round 1 is on lane branches (k-w1, k-k8, k-w1b, k-paper) that are not merged yet, so this script restates
the spec formulas with the standard library and compares them with golden values copied from those branches (each
constant names its golden file). After the merge the constants can be replaced by reads of
datasets/golden/stage_k/*.json (program/STAGE_K_DOCS_PENDING.md).

Run: python docs/question-bank/verify/v14_stage_k.py   (no package needed)
"""
from __future__ import annotations

import hashlib
import json
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
assert 5 + 7 == 12 and f"{12 / 19:.1%}" == "63.2%"
has("12 of 19 value cases, 63.2%")

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
fills = -(D("37.5") + D("44.53125") + D("42.1875"))
assert 4800 * (D("100.0078125") - 100) == D("37.5") and 3800 * (D("100.01171875") - 100) == D("44.53125")
assert 2700 * (D("100.015625") - 100) == D("42.1875") and (D("2.405") / 181).quantize(D("0.000001")) == acc
assert (carry, roll, curve) == (D("1213.9355"), D("16.5625"), D("-1993.7275"))
assert carry + roll + curve + fills == D("-887.44825") == D("9998826.61425") - D("9999714.0625")
has("sum -887.44825, equal to NAV 9,998,826.61425 minus 9,999,714.0625")

# Q14.33 to Q14.52: the second pass (added 2026-11-20). Golden values are read from datasets/golden/stage_k/.

GOLD = Path(__file__).resolve().parents[3] / "datasets" / "golden" / "stage_k"


def golden(suite: str, case_id: str) -> dict:
    for c in json.loads((GOLD / f"{suite}.json").read_text(encoding="utf-8"))["cases"]:
        if c["case_id"] == case_id:
            return c
    raise KeyError(case_id)


def out(suite: str, case_id: str) -> dict:
    return golden(suite, case_id)["expected"]["outputs"]


# Q14.33: NONE before the first knowledge time.
assert out("bt_k", "bt_k-0006")["status"] == "NONE" and out("bt_k", "bt_k-0002")["row"]["value"] == 105
has("the answer is `NONE` with no row (`bt_k-0006`)")

# Q14.34: n - j pillars.
assert [out("inc_k", f"inc_k-000{i}")["recomputed"] for i in (2, 3, 4)] == [2, 1, 0]
assert out("inc_k", "inc_k-0004")["first_changed_index"] is None
has("a move at index 1 gives `recomputed` 2 (`inc_k-0002`), a move at index 2 gives 1 (`inc_k-0003`)")


# Q14.35 and Q14.36: the contract's bootstrap, and the stale cache one unit in the last place above.
def boot(quotes: list[float]) -> list[float]:
    acc, dfs = 0.0, []
    for s in quotes:
        p = (1.0 - s * acc) / (1.0 + s)
        dfs.append(p)
        acc = acc + p
    return dfs


assert boot([0.02, 0.026, 0.03]) == [0.9803921568627451, 0.9498146237052325, 0.9146541714397676]
has("`[0.9803921568627451, 0.9498146237052325, 0.9146541714397676]`")
base = boot([0.02, 0.025, 0.03])
assert base[2] == 0.9145993230349208 and math.nextafter(base[2], math.inf) == 0.9145993230349209
has("from `0.9145993230349208` to the next binary64 above it, `...9209`")

# Q14.37 to Q14.39: Student-t tails with 1, 2 and 3 degrees of freedom in closed form; the goldens for 29 and 249.
t1 = 2 / math.pi * math.atan(1 / 3)
t2 = 1 - 3 / math.sqrt(11)
t3 = 1 - 2 * (math.atan(3 / math.sqrt(3)) + 3 * math.sqrt(3) / (3 + 9)) / math.pi  # nu = 3 closed form
close(t1, out("trig_k", "trig_k-0010")["false_alarm_rate"], 1e-14)
close(t2, out("trig_k", "trig_k-0011")["false_alarm_rate"], 1e-14)
close(t3, out("trig_k", "trig_k-0001")["false_alarm_rate"], 1e-12)
has("`(2/pi) atan(1/3) = 0.20483276469913345`")
has("`1 - 3/sqrt(11) = 0.0954660`, the golden's 0.09546596626670913")
has("Four changes (3 degrees of freedom) give 0.0576689")
nominal = math.erfc(3 / math.sqrt(2))
r30, r250 = out("trig_k", "trig_k-0013")["false_alarm_rate"], out("trig_k", "trig_k-0014")["false_alarm_rate"]
assert f"{t3 / nominal:.1f}" == "21.4" and f"{r30 / nominal:.2f}" == "2.04" and f"{r250 / nominal:.2f}" == "1.10"
assert f"{nominal:.7f}" == "0.0026998" and f"{r30:.7f}" == "0.0054992" and f"{r250:.7f}" == "0.0029738"
has("`n = 30`: 0.0054992 (`trig_k-0013`), 2.04 times. `n = 250`: 0.0029738 (`trig_k-0014`), 1.10 times")

# Q14.40: an exact tie.
ch = [0.5, -1.0, 1.5, -0.5, 0.0, 1.0, -1.5, 0.0]
assert statistics.stdev(ch) == 1.0 and out("trig_k", "trig_k-0004")["fire"] is False
has("so `sigma = sqrt(7/7) = 1` exactly; at `k = 2.5` the threshold is exactly 2.5")

# Q14.41: the error codes.
assert golden("trig_k", "trig_k-0017")["expected"]["error_code"] == "E_DOMAIN"
assert golden("trig_k", "trig_k-0019")["expected"]["error_code"] == "E_DOMAIN"

# Q14.42 to Q14.44: the Lagrange bounds.
v = 1e6 * math.exp(-0.2)
L1 = 0.01 ** 3 * 125 * v / 6
L2 = 0.01 ** 3 * 8 * 500_000 * math.exp(-0.06) / 6
b1, b5 = out("idr_k", "idr_k-0001")["bound"], out("idr_k", "idr_k-0005")["bound"]
assert f"{v:,.3f}" == "818,730.753" and f"{b1 - L1:.1e}" == "1.8e-10" and f"{(b1 - L1) / b1:.1e}" == "1.1e-11"
close(L1, 17.05689068912462, 1e-15)
exact = 1e6 * (math.exp(-0.25) - math.exp(-0.2))
est = out("idr_k", "idr_k-0001")["estimate_pnl"]
assert f"{exact:,.3f}" == "-39,929.970" and f"{est - exact:.3f}" == "16.846" and f"{(est - exact) / b1:.1%}" == "98.8%"
has("`L = 0.01^3 x 125 x 818,730.753 / 6 = 17.05689068912462`")
assert f"{L2:.5f}" == "0.62784" and f"{L1 + L2:.5f}" == "17.68473" and f"{16.221077702973727 / b5:.1%}" == "91.7%"
has("so `L_1 + L_2 = 17.68473`, and the golden's `bound` is 17.684733711514124")
small = 1e-27 * 125 * v / 6
roundoff = 2 ** -53 * v * 5 * 1e-9
assert f"{small:.1e}" == "1.7e-20" and f"{roundoff:.1e}" == "4.5e-19" and 26 <= roundoff / small <= 27
has("`eps |V| T |h| = 1.1e-16 x 818,730.753 x 5 x 1e-9 = 4.5e-19`, about 26 times larger")

# Q14.45 to Q14.47: the two-swap netting set (not a golden; the Python build's output is quoted as observed).
s10 = sd(0, 10)
dn = 10_000 * s10 - 5_000 * s10
add = 0.005 * dn
assert f"{s10:.6f}" == "7.869387" and f"{dn:,.2f}" == "39,346.93" and f"{add:.2f}" == "196.73"
close(1.4 * (20 + add), 303.4285382011566, 1e-12)
close(1.4 * (30 + 0.005 * 10_000 * s10), 592.8570764023132, 1e-12)
m = min(1.0, 0.05 + 0.95 * math.exp(-310 / (2 * 0.95 * add)))
close(m, 0.4645246062932369, 1e-12)
close(1.4 * m * add, 127.94333326981402, 1e-12)
assert f"{2 * 0.95 * add:.2f}" == "373.80" and f"{1.4 * 0.05 * add:.2f}" == "13.77"
has("`EAD = 1.4 x 216.73 = 303.43`")
has("`m = 0.05 + 0.95 exp(-310 / 373.80) = 0.4645`")
assert f"{math.sqrt(2 - 1.4):.4f}" == "0.7746" and f"{math.sqrt(2 - 0.6):.4f}" == "1.1832"
has("in adjacent buckets `EN = X sqrt(2 - 1.4) = 0.7746 X`; in buckets 1 and 3 `EN = X sqrt(2 - 0.6) = 1.1832 X`")

# Q14.48: power of the 250-day zone test.
pw = {p: cdf(250, F(p, 100)) for p in (1, 2, 3)}
assert f"{float(1 - pw[1][4]):.2%}" == "10.78%"
assert f"{float(1 - pw[2][4]):.2%}" == "56.13%" and f"{float(1 - pw[2][9]):.2%}" == "3.04%" and f"{float(pw[2][4]):.2%}" == "43.87%"
assert f"{float(1 - pw[3][4]):.2%}" == "87.18%" and f"{float(1 - pw[3][9]):.2%}" == "22.10%"
has("`p = 2%`: 56.13%, and red (10 or more) only 3.04%. `p = 3%`: 87.18%, red 22.10%")

# Q14.49: the n = 1 edges.
edges = [(out("tlk_k", f"tlk_k-00{i}")["cumulative_probability"], out("tlk_k", f"tlk_k-00{i}")["zone"]) for i in (16, 17, 18)]
assert edges == [(0.95, "YELLOW"), (0.99, "YELLOW"), (0.9999, "RED")]

# Q14.50: the two hashes (stage H paper canonical rule, HR-45).
row = {"body": {"limit_price": "101", "order_id": "O1", "quantity": "3", "side": "BUY", "symbol": "BTC-USD", "type": "LIMIT"},
       "kind": "ORDER", "label": "crypto venue; simulated", "prev": "0" * 64, "seq": 0, "ts": "2026-11-18T00:00:01Z"}
hashes = []
for price in ("101", "102"):
    row["body"]["limit_price"] = price
    hashes.append(hashlib.sha256(json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest())
assert hashes[0].startswith("72c85984") and hashes[0].endswith("7e81") and hashes[1].startswith("937f6a4d") and hashes[1].endswith("4e90")
has('"101" hashes to `72c85984...7e81` and "102" to `937f6a4d...4e90`')

# Q14.51: telescoping.
assert 26500 * (D("100.000625") - 100) + 26500 * (D("99.925390") - D("100.000625")) == D("-1977.165") == 26500 * (D("99.925390") - 100)
has("sum -1,977.165 = `26,500 x (99.925390 - 100)`")

# Q14.52: the placeholder-weight margin.
cs = golden("sbim_alias_k", "sbim_alias_k-0001")["inputs"]
ws = [rw * s for rw, s in zip(cs["risk_weights"], cs["sensitivities"])]
mg = math.sqrt(sum(cs["correlations"][i][j] * ws[i] * ws[j] for i in range(6) for j in range(6)))
assert ws == [10_000, -10_000, 75_000, 160_000, -60_000, 18_000] and cs["risk_weights"] == [10 * k for k in range(1, 7)]
assert all(cs["correlations"][i][j] == round(1 - 0.1 * abs(i - j), 10) for i in range(6) for j in range(6))
close(mg, 190937.1624383268, 1e-12)
has("margin 190,937.16 (`sbim_alias_k-0001`")

print(f"v14: {checks} strings checked")
