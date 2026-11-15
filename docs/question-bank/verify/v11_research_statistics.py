"""Recompute every worked-example number in docs/question-bank/11-research-statistics.md and check the strings.

Run from python/: PYTHONPATH=. <venv python> ../docs/question-bank/verify/v11_research_statistics.py
"""
from __future__ import annotations

import math
import statistics
from pathlib import Path

from quantforge_core import research as rs
from quantforge_core import research_w2 as r2
from quantforge_core.errors import QfError

TEXT = (Path(__file__).resolve().parents[1] / "11-research-statistics.md").read_text(encoding="utf-8")
checks = 0


def has(s: str) -> None:
    global checks
    assert s in TEXT, f"missing in 11-research-statistics.md: {s!r}"
    checks += 1


def f(v: float, p: int) -> str:
    return f"{round(v, p) + 0.0:.{p}f}"


def ints(xs) -> str:
    return "[" + ", ".join(f"{x:.0f}" for x in xs) + "]"


# Q11.2
prices, targets = [100, 102, 101, 104, 103], [1, 1, -1, 0, 0]
b = rs.backtest_run(prices, targets, lag=1)
has(f"Positions are `{ints(b['positions'])}` and trades `{ints(b['trades'])}`")
has(f"Gross P&L per bar is `{ints(b['pnl_gross'])}`")
has(f"Total gross {f(b['total_gross'], 0)}.")

# Q11.3, Q11.6
c = rs.backtest_run(prices, targets, lag=1, half_spread_bps=10, commission_per_unit=0.05, fixed_per_trade=1)
has(f"= {f(c['cost'][3], 3)}. Totals: gross {f(c['total_gross'], 3)}, spread {f(c['total_spread_cost'], 3)}, "
    f"commission {f(c['total_commission'], 3)}, fixed {f(c['total_fixed_cost'], 3)} ({c['trade_count']} trades), "
    f"net {f(c['total_net'], 3)}. Turnover is {f(c['turnover'], 0)}.")
ident = c["total_gross"] - c["total_spread_cost"] - c["total_commission"] - c["total_fixed_cost"]
assert abs(ident - c["total_net"]) < 1e-12
has("equity `[" + ", ".join(f(e, 3) for e in c["equity"]) + "]`")
has(f"maximum drawdown is {f(c['max_drawdown'], 3)}, at bar 2")

# Q11.4
p = [100, 101, 100.5, 102, 101, 101.5, 103, 102.5]
sig = [(1 if p[t + 1] > p[t] else -1) for t in range(len(p) - 1)] + [0]
g0 = rs.backtest_run(p, sig, lag=0)["total_gross"]
g1 = rs.backtest_run(p, sig, lag=1)["total_gross"]
assert abs(g0 - sum(abs(p[t + 1] - p[t]) for t in range(len(p) - 1))) < 1e-12
has(f"At `lag = 0` the gross P&L is {g0:g}, the sum")
has(f"At `lag = 1` it is {g1:g}.")
assert rs.backtest_run(p, sig, lag=1, engine="VECTOR")["total_gross"] == g1

# Q11.8
cv = rs.cv_purged_kfold(list(range(8)), [t + 1 for t in range(8)], 2, 0.125)
tr0, tr1 = cv["folds"][0]["train"], cv["folds"][1]["train"]
has(f"Train: {', '.join(map(str, tr0))}. Fold 1")
has(f"Train: {', '.join(map(str, tr1))}. `embargo_count` = {cv['embargo_count']}.")

# Q11.11
for n, k in ((6, 2), (10, 2), (10, 3)):
    r = rs.cv_cpcv_paths(n, k)
    has(f"`N = {n}, k = {k}`: {r['n_splits']} splits, {r['n_paths']} paths")

# Q11.12, Q11.13
p1 = rs.stats_psr(0.1, 252)
has(f"`z = {f(p1['z'], 5)}`, `psr = {f(p1['psr'], 6)}`")
p2 = rs.stats_psr(0.1, 252, skew=-1, kurtosis=6)
has(f"`z = {f(p2['z'], 5)}`, `psr = {f(p2['psr'], 6)}`, down from {f(p1['psr'], 6)}")

# Q11.14
sr = 2.5 / math.sqrt(250)
has(f"`2.5 / sqrt(250)` = {f(sr, 6)}")

# Q11.15
try:
    rs.stats_psr(1.0, 100, skew=3, kurtosis=3)
    raise AssertionError("expected E_DOMAIN")
except QfError as e:
    assert e.code == "E_DOMAIN"
has("the library returns `E_DOMAIN`")

# Q11.16, Q11.17
d = rs.stats_dsr(sr, 1250, 100, 0.5 / 250, skew=-3, kurtosis=10)
has(f"`SR0` = {f(d['sr0'], 4)} per period and `DSR` = {f(d['dsr'], 4)}")
d46 = rs.stats_dsr(sr, 1250, 46, 0.5 / 250, skew=-3, kurtosis=10)
has(f"With `N = 46` the DSR is {f(d46['dsr'], 4)}")
d1 = rs.stats_dsr(sr, 1250, 1, 0.5 / 250, skew=-3, kurtosis=10)
assert d1["sr0"] == 0.0
has(f"`SR0 = 0` and DSR {f(d1['dsr'], 6)}, against {f(d['dsr'], 4)}")

# Q11.18
pb = rs.stats_pbo([[1, 0], [1, 0], [0, 2], [0, 2]], 2, "MEAN")
has(f"both logits are {f(pb['logits'][0], 6)}, and `PBO = {pb['pbo']:g}`")
pb0 = rs.stats_pbo([[2, 0], [2, 1], [3, 0], [2, 1]], 2, "MEAN")
has(f"logits {f(pb0['logits'][0], 6)}, `PBO = {pb0['pbo']:g}`")

# Q11.19
has(f"`C(16, 8)` = {math.comb(16, 8)} combinations")

# Q11.20, Q11.21
pw = rs.stats_power(13.83)
has(f"`z_sum` = {f(pw['z_sum'], 4)}")
has(f"`mds` = {f(pw['mds'], 4)}")
pw2 = rs.stats_power(5, sr_target=0.5)
has(f"`years_required` = {f(pw2['years_required'], 4)}; with only 5 years the MDS is {pw2['mds']:.6g}, "
    f"and the standard error at 0.5 is {f(pw2['se_at_target'], 6)}")

# Q11.26
E = [[0.5, 0.4, 0.1], [0.1, 0.3, 0.6]]
vt = rs.regime_viterbi([0.6, 0.4], [[0.7, 0.3], [0.4, 0.6]], emission=[[E[0][o], E[1][o]] for o in (0, 1, 2)])
has(f"The path is `{vt['states']}`")
has(f"log-probability {f(vt['log_probability'], 5)}, i.e. joint probability {math.exp(vt['log_probability']):.5f}")

# Q11.27
y = [0.01, -0.02, 0.015, 0.005, 0.02]
bw = r2.regime_baum_welch(y, [1.0], [[1.0]], [0.0], [0.02])
assert abs(bw["means"][0] - statistics.mean(y)) < 1e-15 and abs(bw["sds"][0] - statistics.pstdev(y)) < 1e-15
has(f"The fit gives mean {bw['means'][0]:g} and sd {bw['sds'][0]:.6g} (the population sd; the sample sd would be "
    f"{statistics.stdev(y):.6g}), with `iterations` = {bw['iterations']} and `converged` {str(bw['converged']).lower()}")

assert ("inter" + "view") not in TEXT.lower()
print(f"v11 OK: {checks} checks")
