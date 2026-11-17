"""Recompute every worked-example number in docs/question-bank/10-hedging.md and check the printed strings.

Run from python/: PYTHONPATH=. <venv python> ../docs/question-bank/verify/v10_hedging.py
"""
from __future__ import annotations

import math
from pathlib import Path

from quantforge_core import cross_asset_hedge as xa
from quantforge_core import dynamic_hedge as dh
from quantforge_core import hedge_solvers as hs
from quantforge_core import slippage as sl
from quantforge_core.errors import QfError

TEXT = (Path(__file__).resolve().parents[1] / "10-hedging.md").read_text(encoding="utf-8")
checks = 0


def has(s: str) -> None:
    global checks
    assert s in TEXT, f"missing in 10-hedging.md: {s!r}"
    checks += 1


def f(v: float, p: int) -> str:
    return f"{round(v, p) + 0.0:.{p}f}"


def code(fn) -> str:
    try:
        fn()
    except QfError as e:
        return e.code
    return "ok"


S, R, Q, V = 100.0, 0.03, 0.01, 0.25
book = [("CALL", 100.0, 0.5, -100.0)]

# Q10.2, Q10.4
r = hs.greeks_neutralise(S, R, Q, V, book, [("UNDERLYING", None, None)], ["DELTA"])
has(f"Book delta = {f(r['greeks_before']['delta'], 4)}")
has(f"buys {f(r['quantities'][0], 4)} shares")
has(f"gamma stays at {f(r['greeks_before']['gamma'], 4)}")
has(f"vega at {f(r['greeks_before']['vega'], 2)} per unit")
has(f"Per volatility point (0.01) that is {f(r['greeks_before']['vega'] / 100, 4)}")
assert r["greeks_after"]["delta"] == 0.0

# Q10.3
r = hs.greeks_neutralise(S, R, Q, V, book, [("UNDERLYING", None, None), ("CALL", 110.0, 0.25)], ["DELTA", "GAMMA"])
has(f"Result: {f(r['quantities'][0], 4)} shares and {f(r['quantities'][1], 4)} of the 110 calls")
has(f"vega after is {f(r['greeks_after']['vega'], 2)} per unit")

# Q10.5
assert code(lambda: hs.greeks_neutralise(S, R, Q, V, book, [("CALL", 105.0, 0.5), ("CALL", 105.0, 0.5)],
                                         ["DELTA", "GAMMA"])) == "E_SINGULAR"
has("The library returns `E_SINGULAR`.")

# Q10.6
r = hs.qp_solve([[2.0], [1.0]], [-3.0, -1.0], [1.0, 1.0])
has(f"Then `x = {f(r['x'][0], 6)}`, residual `({f(r['residual'][0], 1)}, {f(r['residual'][1], 1)})` and objective {f(r['objective'], 6)}")

# Q10.7
a7, b7 = [[1.0, 0.5], [0.5, 1.0]], [-2.0, 0.5]
free = hs.qp_solve(a7, b7, [1, 1])
has(f"free solution is `x = ({f(free['x'][0], 0)}, {f(free['x'][1], 0)})`")
clip = [max(free["x"][0], 0.0), max(free["x"][1], 0.0)]
clip_obj = sum((sum(a7[i][j] * clip[j] for j in range(2)) + b7[i]) ** 2 for i in range(2))
has(f"Clipping gives `(3, 0)` with objective {f(clip_obj, 6)}")
bd = hs.qp_solve(a7, b7, [1, 1], lower=[0.0, 0.0], upper=[None, None])
has(f"`x = ({f(bd['x'][0], 1)}, {f(bd['x'][1], 0)})` with objective {f(bd['objective'], 6)}")

# Q10.8
assert code(lambda: hs.qp_solve(a7, [-2.0, -1.0], [1, 1], eq_matrix=[[1.0, 1.0]], eq_rhs=[5.0],
                                lower=[0.0, 0.0], upper=[2.0, 2.0])) == "E_INFEASIBLE"
has("so the library returns `E_INFEASIBLE`")

# Q10.9, Q10.11
a9, b9 = [[1.0, 1.0], [0.5, 0.5]], [-2.0, -1.0]
assert code(lambda: hs.qp_solve(a9, b9, [1, 1])) == "E_SINGULAR"
mn = hs.qp_solve(a9, b9, [1, 1], singular="MIN_NORM")
has(f"`MIN_NORM`: `x = ({f(mn['x'][0], 0)}, {f(mn['x'][1], 0)})`, rank {mn['rank']}")
rg = hs.qp_solve(a9, b9, [1, 1], ridge=0.01)
has(f"gives {f(rg['x'][0], 6)} of each")
has(f"solves to {f(rg['x'][0], 6)} in each instrument, with objective {f(rg['objective'], 6)}")

# Q10.12
a12, b12 = [[1.0, 0.95], [0.95, 1.0]], [-1.265, -1.27]
it = hs.integer_solve(a12, b12, [1, 1], [1, 1])
cont = hs.qp_solve(a12, b12, [1, 1])
has(f"continuous answer is `({f(cont['x'][0], 1)}, {f(cont['x'][1], 1)})`")
rnd_obj = sum((a12[i][0] + a12[i][1] + b12[i]) ** 2 for i in range(2))
has(f"Rounding gives `(1, 1)` with objective {f(rnd_obj, 6)}")
has(f"returns lots `{it['lots']}` with objective {f(it['objective'], 6)}")
has(f"`rounding_cost = objective - continuous_objective` = {f(it['rounding_cost'], 6)}")

# Q10.14
mv = hs.minvar_ratio(covariance=[[0.0004, 0.9 * 0.02 * 0.019], [0.9 * 0.02 * 0.019, 0.019 ** 2]])
has(f"The hedge is {f(mv['hedge'][0], 6)} units")
has(f"from 0.0004 to {f(mv['variance_after'], 6)}")
has(f"effectiveness is {f(mv['effectiveness'], 6)}")

# Q10.16
bf = hs.beta_futures(5050000, 1.5, 0.0, 1010, 250)
assert bf["contracts_held"] == -30.0 and bf["beta_after"] == 0.0
has("= -30, so sell 30 contracts")

# Q10.17
has(f"`1.0 - 1.2` is {1.0 - 1.2!r}")
bf = hs.beta_futures(1000000, 1.2, 1.0, 1000, 80)
has(f"`contracts` = {bf['contracts']!r}")
has(f"`contracts_held` = {f(bf['contracts_held'], 0)}")
has(f"`beta_after` = {f(bf['beta_after'], 4)}")

# Q10.18
rr = hs.residual_report([[1.0], [0.5]], [-1.0, -1.0], [1.2], [[0.0001, 0.00005], [0.00005, 0.0004]])
has(f"Residual `({f(rr['residual'][0], 1)}, {f(rr['residual'][1], 1)})`")
has(f"variance {rr['variance_before']:.4f} before, {rr['variance_after']:.5f} after")
has(f"effectiveness {f(rr['effectiveness'], 6)}")
assert abs(rr["contributions"][0]) < 1e-18 and abs(rr["contributions"][1] - 0.00006) < 1e-15

# Q10.20
times = [k / 365 for k in range(6)]
spots = [100.0, 101.0, 99.5, 100.5, 101.5, 100.8]
bt = dh.backtest_delta("CALL", 100.0, 30 / 365, -10.0, 0.03, 0.0, 0.2, times, spots)
has(f"`final_pnl` = {f(bt['final_pnl'], 4)}, dollar offset {f(bt['dollar_offset'], 4)} and R² {f(bt['regression_r2'], 4)}")
lr = [math.log(spots[i + 1] / spots[i]) for i in range(5)]
rv = math.sqrt(sum(x * x for x in lr) / len(lr) * 365)  # scratch formula, not the library
has(f"is {f(rv * 100, 2)}%, just above the 20% sold")
assert rv > 0.2 and bt["final_pnl"] < 0

# Q10.21
ef = dh.effectiveness([10, -8, 5, -6], [-9, 7.5, -5.5, 6.2])
has(f"The dollar offset is {f(ef['dollar_offset'], 4)}")
has(f"slope is {f(ef['regression_slope'], 6)}, R² {f(ef['regression_r2'], 6)} and the variance reduction {f(ef['variance_reduction'], 6)}")

# Q10.23
a23, b23 = [[1.0, 0.9], [0.5, 1.0]], [-2.0, -1.0]
c = hs.qp_solve(a23, b23, [1, 1], half_spreads=[0.01, 0.5])
assert c["x"][1] == 0.0
has(f"`x = ({c['x'][0]:.3f}, 0)`")
has(f"risk {c['risk']:.1e}, cost {c['cost']:.5f}")
c2 = hs.qp_solve(a23, b23, [1, 1], half_spreads=[0.01, 0.01])
has(f"comes back at {f(c2['x'][1], 6)}")

# Q10.25
fr = hs.frontier_solve(a23, b23, [1, 1], [0, 1, 4], half_spreads=[0.1, 0.1], impact=[0.05, 0.05])
pts = fr["points"]
has(f"| 0 | 0 | {f(pts[0]['cost'], 6)} |")
has(f"| 1 | {pts[1]['risk']:.6g} | {f(pts[1]['cost'], 6)} |")
has(f"| 4 | {pts[2]['risk']:.6g} | {f(pts[2]['cost'], 6)} |")
assert pts[0]["risk"] < 1e-20 and pts[0]["risk"] <= pts[1]["risk"] <= pts[2]["risk"]

# Q10.27
s = sl.slippage_report([(1000, 50.0, 50.6, 0.02, 0.00001, [(600, 50.05), (300, 50.12)])])["orders"][0]
has(f"Average price {f(s['average_price'], 4)}; execution cost {f(s['execution_cost'], 2)}; "
    f"opportunity cost {f(s['opportunity_cost'], 2)}; shortfall {f(s['shortfall'], 2)}; "
    f"model cost {f(s['model_cost'], 2)}; slippage {f(s['slippage'], 2)}")

# Q10.28
a28, b28 = [[1, 1, 0], [1, 0, 1], [1, 0, 0]], [-1, -1, 0]
s1 = hs.select_solve(a28, b28, [1, 1, 1], 1)
s2 = hs.select_solve(a28, b28, [1, 1, 1], 2)
has(f"With `K = 1` the best is instrument {s1['selected'][0]}, objective {f(s1['objective'], 6)}")
has(f"With `K = 2` the best is `{s2['selected']}`, objective {f(s2['objective'], 0)}")

# Q10.29 (scratch formula from the spec)
eps = 1e-4 / (1 - 0.4)
has(f"`eps` = {eps * 1e4:.5f}e-4")

# Q10.31
x = xa.crossasset_solve(100, 0.01, 0.2, [2.0, 5.0], [0.03, 0.03],
                        [("FORWARD", {"strike": 100.0, "expiry_years": 2.0, "quantity": 5.0}),
                         ("ZCB", {"expiry_years": 5.0, "notional": 100.0, "quantity": -10.0})],
                        [("UNDERLYING", {}), ("ZCB", {"expiry_years": 2.0, "notional": 100.0}),
                         ("ZCB", {"expiry_years": 5.0, "notional": 100.0})], [1, 1, 1])
br, pos = x["book_risk"], x["positions"]
has(f"Book risk: EQ01 {br[0]:.6g}, KR01 at 2 years {br[1]:.6g}, at 5 years {br[2]:.6g}")
has(f"Positions {pos[0]:.6g}, {pos[1]:.6g} and {pos[2]:.6g}, residual 0")
assert max(abs(v) for v in x["residual_risk"]) < 1e-12

assert ("inter" + "view") not in TEXT.lower()
print(f"v10 OK: {checks} checks")
