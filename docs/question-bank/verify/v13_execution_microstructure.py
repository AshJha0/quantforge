"""Recompute every worked-example number in docs/question-bank/13-execution-microstructure.md and check the strings.

The stage H operations are specified but not merged, so this script restates the spec formulas with the standard
library and checks them against the spec goldens and the page. Once the operations are merged it should call
quantforge_core instead, like the other sets.

Run: python docs/question-bank/verify/v13_execution_microstructure.py   (no package needed)
"""
from __future__ import annotations

import math
from pathlib import Path

TEXT = (Path(__file__).resolve().parents[1] / "13-execution-microstructure.md").read_text(encoding="utf-8")
checks = 0


def has(s: str) -> None:
    global checks
    assert s in TEXT, f"missing in 13-execution-microstructure.md: {s!r}"
    checks += 1


def close(a: float, b: float, tol: float = 1e-9) -> None:
    assert abs(a - b) <= tol * max(1.0, abs(b)), (a, b)


# Q13.2 sched_h-0001
base, rem = divmod(1000, 3)
twap = [base + (1 if i < rem else 0) for i in range(3)]
assert twap == [334, 333, 333] and sum(twap) == 1000
has("`[334, 333, 333]`")

# Q13.3 sched_h-0003, 0004
assert [1000 * w / 10 for w in (1, 2, 3, 4)] == [100, 200, 300, 400]
has("`[100, 200, 300, 400]`")
raw = [10 / 3] * 3
out = [int(r) for r in raw]
for i in sorted(range(3), key=lambda i: (-(raw[i] - out[i]), i))[: 10 - sum(out)]:
    out[i] += 1
assert out == [4, 3, 3]
has("`[4, 3, 3]`")

# Q13.4 sched_h-0005
p, left, sl = 0.2, 1000, []
for v in (1000, 2000, 4000):
    s = min(left, int(p * v / (1 - p)))
    sl.append(s)
    left -= s
assert sl == [250, 500, 250] and left == 0
has("`[250, 500, 250]`, residual 0")
has("`250 / 1250 = 0.2`")
close(200 / 1200, 0.16667, 1e-4)
has("`200 / 1200 = 16.7 %`")

# Q13.5 sched_h-0006
close(0.1 / 0.9 * 900, 100)
has("filled 200, residual 800")

# Q13.7 ac_h-0001
X, T, N, sigma, eps, eta, gamma = 1e6, 5.0, 5, 0.95, 0.0625, 2.5e-6, 2.5e-7
eta_t = eta - gamma * 1.0 / 2
close(eta_t, 2.375e-6)
E0 = 0.5 * gamma * X**2 + eps * X + eta_t * X**2 / T
close(E0, 662500)
has("`E = 1/2 gamma X^2 + epsilon X + eta_tilde X^2 / T = 125,000 + 62,500 + 475,000 = 662,500`")
V0 = sigma**2 * X**2 * (N - 1) * (2 * N - 1) / (6 * N)
close(V0, 1.083e12)
has("= 0.9025e12 x 1.2 = 1.083e12`")
close(sigma**2 * X**2 * T / 3, 1.504e12, 1e-3)
has("which gives 1.504e12 here")

# Q13.8 ac_h-0002, ac_h-0005
lam = 1e-6
close(1 + lam * sigma**2 / (2 * eta_t), 1.19)
kappa = math.acosh(1.19)
close(kappa, 0.6070761632, 1e-10)
x = [X * math.sinh(kappa * (T - j)) / math.sinh(kappa * T) for j in range(N + 1)]
close(x[1], 541955.5544, 1e-9)
E = 0.5 * gamma * X**2 + eps * X + eta_t * sum((x[j] - x[j + 1]) ** 2 for j in range(N))
V = sigma**2 * sum(h * h for h in x[1:])
close(E, 911226.986, 1e-9)
close(V, 3.641285721e11, 1e-9)
has("`kappa = 0.6070761632`; after day 1, 541,955.5544 shares")
has("`E = 911,226.986`, `V = 3.641285721e11`")
close(kappa * T, 3.0353808, 1e-7)
has("`kappa T = 3.0353808`")
assert 240000 < E - E0 < 250000 and abs(V / V0 - 1 / 3) < 0.01
has("about 249,000 dollars of expected cost buys a variance one third as large")

# Q13.9 ac_h-0004
eta5 = eta - gamma * 5 / 2
close(eta5, 1.875e-6)
close(0.5 * gamma * X**2 + eps * X + eta5 * X**2 / 5, 562500)
has("`E = 125,000 + 62,500 + 375,000 = 562,500`")

# Q13.11 tca_h-0001, 0002
fills = [(600, 100.20), (200, 100.30)]
Q = sum(q for q, _ in fills)
d, e, o = Q * 0.10, sum(q * (px - 100.10) for q, px in fills), (1000 - Q) * 1.0
close(d, 80)
close(e, 100)
close(o, 200)
close((d + e + o + 5) / (1000 * 100) * 1e4, 38.5)
has("total `80 + 100 + 200 + 5 = 385`, which is `385 / (1000 x 100) x 1e4 = 38.5` bp")
has("total -380 (`tca_h-0002`)")

# Q13.12 imp_h-0001, 0002
close(0.02 * math.sqrt(1e5 / 1e7), 0.002)
close(0.02 * math.sqrt(4e5 / 1e7), 0.004)
has("`0.02 x sqrt(0.01) = 0.002`, 20 bp")

# Q13.13 imp_h-0003, 0004
close(1000 / 10, 100)
close(8 * 1000 / 10, 800)
has("blocks of 100, rate 800")
close(1e5 / 4.231, 23635.0744504845, 1e-13)
close(2.231e5 / 4.231, 52729.8510990310, 1e-13)
has("blocks of 23,635.0744504845 and rate 52,729.8510990310")


# Q13.14, Q13.15 as_h-0001, 0005..0007
def spread(g: float, t: float, k: float = 1.5, sig: float = 2.0) -> float:
    return g * sig**2 * t + (2 / g) * math.log(1 + g / k)


r = 100 - 2 * 0.1 * 4
close(r, 99.2)
sp = spread(0.1, 1.0)
close(sp, 1.6907704228, 1e-10)
close(r - sp / 2, 98.3546147886, 1e-11)
close(r + sp / 2, 100.0453852114, 1e-11)
has("spread `0.4 + 20 ln(16/15) = 1.6907704228`; bid 98.3546147886, ask 100.0453852114")
for g, val, printed in ((0.1, 1.4907704228, 1.49), (0.01, 1.3489085437, 1.35), (1.0, 3.0216512475, 3.02)):
    close(spread(g, 0.5), val, 1e-10)
    assert abs(spread(g, 0.5) - printed) <= 0.005
has("1.4907704228, 1.3489085437 and 3.0216512475")

print(f"v13: {checks} strings checked")
