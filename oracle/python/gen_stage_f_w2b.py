"""Stage F carry-over wave 2b, F4 portfolio-risk tools (ruling G-46): reverse stress, limits, concentration,
liquidity-adjusted VaR (Bangia et al.), volatility by horizon under AR(1) returns.

Values: 50-digit mpmath. No outside library: not counted (stage F share unchanged in count).

    cd oracle/python && uv run python -W ignore gen_stage_f_w2b.py
"""
import mpmath as mp

from qf_oracle import common
from qf_oracle.common import Suite, note

mp.mp.dps = 50
G = "oracle/python/gen_stage_f_w2b.py"
SPEC = "specifications/06-risk/portfolio-risk-tools.md"
LIM = {"absolute": 1e-12, "relative": 1e-12, "reason": "closed forms"}
MUT = []


def caught(name, gap, tol=1e-9):
    assert gap > tol, name
    MUT.append((name, gap))


def reverse(inp, mut=None):
    d = [mp.mpf(x) for x in inp["direction"]]
    de = [mp.mpf(x) for x in inp["delta"]]
    Gm = [[mp.mpf(x) for x in r] for r in inp["gamma"]]
    L = mp.mpf(inp["target_loss"])
    a = sum(d[i] * Gm[i][j] * d[j] for i in range(len(d)) for j in range(len(d))) / (1 if mut == "no_half" else 2)
    b = sum(x * y for x, y in zip(de, d))
    # P&L(k) = a k^2 + b k; find the smallest k > 0 with P&L = -L
    if a == 0:
        roots = [-L / b] if b != 0 else []
    else:
        disc = b * b - 4 * a * L
        roots = [] if disc < 0 else [(-b + s * mp.sqrt(disc)) / (2 * a) for s in (-1, 1)]
    pos = sorted(r for r in roots if r > 0)
    if not pos:
        return None
    k = pos[0]
    return {"scale": float(k), "shocks": [float(k * x) for x in d], "pnl": float(a * k * k + b * k)}


def limits(inp):
    out = {}
    for name in sorted(inp["measures"]):
        v, lim = mp.mpf(inp["measures"][name]), inp["limits"][name]
        u = abs(v) / mp.mpf(lim["hard"])
        st = "BREACH" if abs(v) > lim["hard"] else ("WARN" if abs(v) >= lim["soft"] else "OK")
        out[name] = {"utilisation": float(u), "status": st}
    worst = max(out.values(), key=lambda r: ("OK", "WARN", "BREACH").index(r["status"]))["status"]
    return {"measures": out, "overall": worst}


def concentration(inp, mut=None):
    x = [abs(mp.mpf(v)) for v in inp["exposures"]]
    tot = sum(x)
    w = [v / tot for v in x]
    hhi = sum(v * v for v in w)
    top = sum(sorted(w, reverse=True)[: inp["top_n"]])
    return {"hhi": float(hhi), "effective_number": float(1 / hhi), "top_n_share": float(top), "weights": [float(v) for v in w]}


def lvar(inp, mut=None):
    var, z = mp.mpf(inp["var"]), mp.mpf(inp["z"])
    cost = sum(abs(mp.mpf(p)) * (mp.mpf(m) + (0 if mut == "no_vol" else z) * mp.mpf(s))
               for p, m, s in zip(inp["position_values"], inp["spread_mean"], inp["spread_vol"])) / 2
    return {"liquidity_cost": float(cost), "lvar": float(var + cost)}


def horizon(inp, mut=None):
    s, rho, h = mp.mpf(inp["daily_vol"]), mp.mpf(inp["ar1"]), inp["horizon_days"]
    v = h + 2 * sum((h - k) * rho ** k for k in range(1, h)) if mut != "sqrt" else h
    return {"vol": float(s * mp.sqrt(v)), "sqrt_rule_vol": float(s * mp.sqrt(h)), "variance_ratio": float(v / h)}


def main():
    s = Suite("risk_f4b", SPEC, G)
    rv = dict(direction=[1.0, 0.5, -0.25], delta=[-1000.0, -400.0, 300.0], gamma=[[-2000.0, 0, 0], [0, -800.0, 100.0], [0, 100.0, -500.0]], target_loss=50.0)
    for inp, d in ((rv, "delta-gamma, loss 50"), (dict(rv, gamma=[[0.0] * 3] * 3), "linear only"),
                   (dict(rv, target_loss=500.0), "larger loss"), (dict(rv, gamma=[[4000.0, 0, 0], [0, 0, 0], [0, 0, 0]], target_loss=10.0), "convex: smaller root")):
        s.add("risk.stress.reverse", inp, reverse(inp), verified=["mpmath-50"], tags=["f4", "reverse_stress"], limit=LIM, description=d)
    for c in s.cases:
        assert abs(c["expected"]["outputs"]["pnl"] + c["inputs"]["target_loss"]) < 1e-9
    caught("gamma term without the 1/2", abs(reverse(rv)["scale"] - reverse(rv, "no_half")["scale"]))
    s.add("risk.stress.reverse", dict(rv, delta=[1000.0, 400.0, -300.0], gamma=[[2000.0, 0, 0], [0, 800.0, 0], [0, 0, 500.0]]), error="E_DOMAIN",
          cls="date_and_convention", tags=["invalid", "f4"], description="no positive scale reaches the loss")
    s.add("risk.stress.reverse", dict(rv, target_loss=0.0), error="E_DOMAIN", cls="date_and_convention", tags=["invalid", "f4"], description="target_loss 0")
    lm = dict(measures={"VAR99": 9.5e6, "DV01": -48000.0, "VEGA": 120000.0}, limits={"VAR99": {"soft": 8e6, "hard": 1e7}, "DV01": {"soft": 40000.0, "hard": 50000.0}, "VEGA": {"soft": 150000.0, "hard": 200000.0}})
    s.add("risk.limits.check", lm, limits(lm), verified=["mpmath-50"], tags=["f4", "limits"], limit=LIM, description="two warnings")
    lm2 = dict(lm, measures=dict(lm["measures"], VAR99=1.05e7))
    s.add("risk.limits.check", lm2, limits(lm2), verified=["mpmath-50"], tags=["f4", "limits"], limit=LIM, description="one breach")
    lm3 = dict(lm, measures=dict(lm["measures"], VAR99=8e6))
    s.add("risk.limits.check", lm3, limits(lm3), verified=["mpmath-50"], tags=["f4", "limits"], limit=LIM, description="exactly at soft: WARN")
    s.add("risk.limits.check", dict(lm, limits={"VAR99": {"soft": 2e7, "hard": 1e7}, "DV01": lm["limits"]["DV01"], "VEGA": lm["limits"]["VEGA"]}), error="E_DOMAIN",
          cls="date_and_convention", tags=["invalid", "f4"], description="soft above hard")
    s.add("risk.limits.check", dict(lm, limits={"VAR99": lm["limits"]["VAR99"]}), error="E_INPUT", cls="date_and_convention", tags=["invalid", "f4"], description="measure without a limit")
    for ex, n, d in (([10.0, 10.0, 10.0, 10.0], 2, "equal: HHI 1/4"), ([50.0, -30.0, 10.0, 5.0, 5.0], 1, "signed exposures by absolute size"), ([1.0, 0.0, 0.0], 1, "single name: HHI 1")):
        inp = dict(exposures=ex, top_n=n)
        s.add("risk.concentration.measures", inp, concentration(inp), verified=["mpmath-50"], tags=["f4", "concentration"], limit=LIM, description=d)
    s.add("risk.concentration.measures", dict(exposures=[0.0, 0.0], top_n=1), error="E_DOMAIN", cls="date_and_convention", tags=["invalid", "f4"], description="all zero")
    s.add("risk.concentration.measures", dict(exposures=[1.0], top_n=2), error="E_INPUT", cls="date_and_convention", tags=["invalid", "f4"], description="top_n above count")
    lv = dict(var=1.2e6, z=2.326, position_values=[5e6, -3e6, 2e6], spread_mean=[0.001, 0.002, 0.004], spread_vol=[0.0005, 0.001, 0.003])
    for inp, d in ((lv, "three positions"), (dict(lv, spread_vol=[0.0, 0.0, 0.0]), "constant spreads: half spread cost")):
        s.add("risk.var.liquidity_adjusted", inp, lvar(inp), verified=["mpmath-50"], tags=["f4", "lvar"], limit=LIM, description=d)
    caught("spread volatility ignored", abs(lvar(lv)["lvar"] - lvar(lv, "no_vol")["lvar"]))
    s.add("risk.var.liquidity_adjusted", dict(lv, spread_mean=[-0.001, 0.002, 0.004]), error="E_DOMAIN", cls="date_and_convention", tags=["invalid", "f4"], description="negative spread")
    for inp, d in ((dict(daily_vol=0.01, ar1=0.0, horizon_days=10), "iid: sqrt rule"), (dict(daily_vol=0.01, ar1=0.2, horizon_days=10), "momentum: ratio above 1"),
                   (dict(daily_vol=0.01, ar1=-0.3, horizon_days=10), "mean reversion: ratio below 1"), (dict(daily_vol=0.012, ar1=0.1, horizon_days=1), "one day: ratio 1")):
        s.add("risk.vol.horizon", inp, horizon(inp), verified=["mpmath-50"], tags=["f4", "horizon"], limit=LIM, description=d)
    caught("sqrt rule under autocorrelation", abs(horizon(dict(daily_vol=0.01, ar1=0.2, horizon_days=10))["vol"] - horizon(dict(daily_vol=0.01, ar1=0.2, horizon_days=10), "sqrt")["vol"]))
    s.add("risk.vol.horizon", dict(daily_vol=0.01, ar1=1.0, horizon_days=10), error="E_DOMAIN", cls="date_and_convention", tags=["invalid", "f4"], description="|ar1| = 1")
    s.add("risk.vol.horizon", dict(daily_vol=0.01, ar1=0.1, horizon_days=0), error="E_DOMAIN", cls="date_and_convention", tags=["invalid", "f4"], description="horizon 0")
    for c in s.cases:
        c["tags"].append("synthetic")
    keep = common.GOLDEN
    common.GOLDEN = keep.parent / "stage_f"
    s.write()
    common.GOLDEN = keep
    for m, g in MUT:
        note(f"  mutant caught: {m} (gap {float(g):.3e})")


if __name__ == "__main__":
    main()
